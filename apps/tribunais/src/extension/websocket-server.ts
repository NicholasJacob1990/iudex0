/**
 * Servidor WebSocket para extensões do navegador
 *
 * Permite que extensões Chrome conectem e executem operações
 * em tribunais diretamente no navegador do usuário.
 *
 * Usado para:
 * - Certificado A3 físico (token USB)
 * - Certificado A3 nuvem (Certisign, Serasa, etc.)
 */

import { WebSocketServer, WebSocket } from 'ws';
import { Redis } from 'ioredis';
import { randomUUID } from 'crypto';
import { logger } from '../utils/logger.js';
import type { ExtensionMessage, CaptchaRequiredEvent, CaptchaSolutionResponse } from '../types/index.js';

interface ConnectedClient {
  ws: WebSocket;
  userId: string;
  sessionId: string;
  tribunal?: string;
  connectedAt: Date;
  lastPing: Date;
}

export class ExtensionWebSocketServer {
  private wss: WebSocketServer | null = null;
  private clients = new Map<string, ConnectedClient>();
  private userSessions = new Map<string, Set<string>>(); // userId -> Set<sessionId>
  private redis: Redis | null = null;
  private subscriber: Redis | null = null;

  constructor(
    private port: number,
    private redisUrl?: string
  ) {}

  async start(): Promise<void> {
    // Iniciar WebSocket server
    this.wss = new WebSocketServer({ port: this.port });

    this.wss.on('listening', () => {
      logger.info(`Extension WebSocket server listening on port ${this.port}`);
    });

    this.wss.on('connection', (ws, req) => {
      this.handleConnection(ws, req);
    });

    this.wss.on('error', (error) => {
      logger.error('WebSocket server error:', error);
    });

    // Conectar ao Redis para pub/sub (se disponível)
    if (this.redisUrl) {
      this.redis = new Redis(this.redisUrl);
      this.subscriber = new Redis(this.redisUrl);

      // Escutar eventos de interação necessária
      await this.subscriber.subscribe(
        'tribunais:interaction_required',
        'tribunais:captcha_required'
      );
      this.subscriber.on('message', (channel, message) => {
        const data = JSON.parse(message);
        switch (channel) {
          case 'tribunais:interaction_required':
            this.handleInteractionRequired(data);
            break;
          case 'tribunais:captcha_required':
            this.handleCaptchaRequired(data);
            break;
        }
      });
    }

    // Heartbeat a cada 30s
    setInterval(() => this.checkHeartbeats(), 30000);
  }

  private handleConnection(ws: WebSocket, req: any): void {
    const sessionId = randomUUID();

    logger.info(`New extension connection: ${sessionId}`);

    // Aguardar autenticação
    ws.on('message', (data) => {
      try {
        const message = JSON.parse(data.toString()) as ExtensionMessage;
        this.handleMessage(ws, sessionId, message);
      } catch (error) {
        logger.error('Failed to parse message:', error);
        ws.send(JSON.stringify({
          type: 'error',
          id: 'parse_error',
          error: 'Invalid message format',
        }));
      }
    });

    ws.on('close', () => {
      this.handleDisconnect(sessionId);
    });

    ws.on('error', (error) => {
      logger.error(`WebSocket error for ${sessionId}:`, error);
    });

    ws.on('pong', () => {
      const client = this.clients.get(sessionId);
      if (client) {
        client.lastPing = new Date();
      }
    });

    // Enviar solicitação de autenticação
    ws.send(JSON.stringify({
      type: 'event',
      id: 'auth_required',
      action: 'authenticate',
      params: { sessionId },
    }));
  }

  private handleMessage(ws: WebSocket, sessionId: string, message: ExtensionMessage): void {
    switch (message.type) {
      case 'command':
        this.handleCommand(ws, sessionId, message);
        break;

      case 'response':
        this.handleResponse(sessionId, message);
        break;

      case 'event':
        this.handleEvent(ws, sessionId, message);
        break;
    }
  }

  private handleCommand(ws: WebSocket, sessionId: string, message: ExtensionMessage): void {
    const { action, params } = message;

    switch (action) {
      case 'authenticate':
        // Registrar cliente autenticado
        const userId = params?.userId as string;
        if (!userId) {
          ws.send(JSON.stringify({
            type: 'error',
            id: message.id,
            error: 'userId é obrigatório',
          }));
          return;
        }

        this.clients.set(sessionId, {
          ws,
          userId,
          sessionId,
          connectedAt: new Date(),
          lastPing: new Date(),
        });

        // Mapear sessão ao usuário
        if (!this.userSessions.has(userId)) {
          this.userSessions.set(userId, new Set());
        }
        this.userSessions.get(userId)!.add(sessionId);

        ws.send(JSON.stringify({
          type: 'response',
          id: message.id,
          success: true,
          data: { sessionId, message: 'Autenticado com sucesso' },
        }));

        logger.info(`User ${userId} authenticated (session: ${sessionId})`);
        break;

      case 'set_tribunal':
        // Definir tribunal da sessão
        const client = this.clients.get(sessionId);
        if (client) {
          client.tribunal = params?.tribunal as string;
          ws.send(JSON.stringify({
            type: 'response',
            id: message.id,
            success: true,
          }));
        }
        break;

      default:
        ws.send(JSON.stringify({
          type: 'error',
          id: message.id,
          error: `Comando desconhecido: ${action}`,
        }));
    }
  }

  private handleResponse(sessionId: string, message: ExtensionMessage): void {
    // Resposta de operação executada pela extensão
    logger.info(`Response from ${sessionId}:`, message);

    // Publicar resposta no Redis para o worker
    if (this.redis && message.params?.jobId) {
      this.redis.publish('tribunais:operation_response', JSON.stringify({
        sessionId,
        jobId: message.params.jobId,
        success: message.success,
        data: message.data,
        error: message.error,
      }));
    }
  }

  private handleEvent(ws: WebSocket, sessionId: string, message: ExtensionMessage): void {
    const { action, params } = message;

    switch (action) {
      case 'signature_complete':
        // Assinatura concluída pelo usuário
        logger.info(`Signature complete from ${sessionId}:`, params);
        if (this.redis) {
          this.redis.publish('tribunais:signature_complete', JSON.stringify({
            sessionId,
            ...params,
          }));
        }
        break;

      case 'captcha_solved':
        // CAPTCHA resolvido pelo usuário
        logger.info(`CAPTCHA solved from ${sessionId}:`, params);
        if (params?.captchaId && params?.jobId) {
          this.handleCaptchaSolution(sessionId, {
            captchaId: params.captchaId as string,
            jobId: params.jobId as string,
            success: params.success as boolean ?? true,
            solution: params.solution as CaptchaSolutionResponse['solution'],
            error: params.error as string | undefined,
          });
        }
        break;

      case 'login_complete':
        // Login concluído
        const client = this.clients.get(sessionId);
        if (client) {
          client.tribunal = params?.tribunal as string;
        }
        break;

      default:
        logger.debug(`Unknown event from ${sessionId}:`, action);
    }
  }

  /**
   * Handler para eventos de CAPTCHA pendente do worker
   */
  private async handleCaptchaRequired(data: CaptchaRequiredEvent): Promise<void> {
    logger.info(`CAPTCHA required for job ${data.jobId}, user ${data.userId}`);

    const sent = await this.sendToUser(data.userId, {
      type: 'command',
      id: `captcha_${data.captchaId}`,
      action: 'request_captcha_solution',
      params: {
        jobId: data.jobId,
        captchaId: data.captchaId,
        tribunal: data.tribunal,
        tribunalUrl: data.tribunalUrl,
        captcha: data.captcha,
        expiresAt: data.expiresAt,
      },
    });

    if (!sent) {
      logger.warn(`Could not send CAPTCHA request to user ${data.userId} - no extension connected`);
      // Publicar falha no Redis para o worker saber
      if (this.redis) {
        this.redis.publish('tribunais:captcha_solution', JSON.stringify({
          captchaId: data.captchaId,
          jobId: data.jobId,
          success: false,
          error: 'Nenhuma extensão conectada para resolver CAPTCHA',
        }));
      }
    }
  }

  /**
   * Handler para solução de CAPTCHA recebida do cliente
   */
  private handleCaptchaSolution(sessionId: string, response: CaptchaSolutionResponse): void {
    if (!this.redis) {
      logger.error('Redis not connected, cannot publish CAPTCHA solution');
      return;
    }

    logger.info(`CAPTCHA solution received from ${sessionId}:`, {
      captchaId: response.captchaId,
      jobId: response.jobId,
      success: response.success,
    });

    // Publicar solução no Redis para o worker continuar
    this.redis.publish('tribunais:captcha_solution', JSON.stringify({
      captchaId: response.captchaId,
      jobId: response.jobId,
      sessionId,
      success: response.success,
      solution: response.solution,
      error: response.error,
    }));
  }

  private handleDisconnect(sessionId: string): void {
    const client = this.clients.get(sessionId);
    if (client) {
      // Remover da lista de sessões do usuário
      const sessions = this.userSessions.get(client.userId);
      if (sessions) {
        sessions.delete(sessionId);
        if (sessions.size === 0) {
          this.userSessions.delete(client.userId);
        }
      }
    }

    this.clients.delete(sessionId);
    logger.info(`Extension disconnected: ${sessionId}`);
  }

  private checkHeartbeats(): void {
    const now = Date.now();
    const timeout = 60000; // 1 minuto

    for (const [sessionId, client] of this.clients) {
      if (now - client.lastPing.getTime() > timeout) {
        logger.warn(`Client ${sessionId} timed out, disconnecting`);
        client.ws.terminate();
        this.handleDisconnect(sessionId);
      } else {
        client.ws.ping();
      }
    }
  }

  /**
   * Envia comando para extensão do usuário
   */
  async sendToUser(userId: string, command: ExtensionMessage): Promise<boolean> {
    const sessions = this.userSessions.get(userId);
    if (!sessions || sessions.size === 0) {
      return false;
    }

    // Enviar para a primeira sessão disponível
    for (const sessionId of sessions) {
      const client = this.clients.get(sessionId);
      if (client && client.ws.readyState === WebSocket.OPEN) {
        client.ws.send(JSON.stringify(command));
        return true;
      }
    }

    return false;
  }

  /**
   * Verifica se usuário tem extensão conectada
   */
  isUserConnected(userId: string): boolean {
    const sessions = this.userSessions.get(userId);
    if (!sessions) return false;

    for (const sessionId of sessions) {
      const client = this.clients.get(sessionId);
      if (client && client.ws.readyState === WebSocket.OPEN) {
        return true;
      }
    }

    return false;
  }

  /**
   * Lista sessões ativas de um usuário
   */
  getUserSessions(userId: string): ConnectedClient[] {
    const sessions = this.userSessions.get(userId);
    if (!sessions) return [];

    const clients: ConnectedClient[] = [];
    for (const sessionId of sessions) {
      const client = this.clients.get(sessionId);
      if (client) {
        clients.push(client);
      }
    }
    return clients;
  }

  /**
   * Handler para eventos de interação necessária do worker
   */
  private async handleInteractionRequired(data: {
    jobId: string;
    userId: string;
    operation: string;
    tribunal: string;
    message: string;
  }): Promise<void> {
    const sent = await this.sendToUser(data.userId, {
      type: 'command',
      id: `interaction_${data.jobId}`,
      action: 'request_interaction',
      params: {
        jobId: data.jobId,
        operation: data.operation,
        tribunal: data.tribunal,
        message: data.message,
      },
    });

    if (!sent) {
      logger.warn(`Could not send interaction request to user ${data.userId} - no extension connected`);
    }
  }

  async stop(): Promise<void> {
    // Fechar todas as conexões
    for (const [sessionId, client] of this.clients) {
      client.ws.close();
    }

    // Fechar Redis
    if (this.redis) {
      await this.redis.quit();
    }
    if (this.subscriber) {
      await this.subscriber.quit();
    }

    // Fechar WebSocket server
    if (this.wss) {
      this.wss.close();
    }

    logger.info('Extension WebSocket server stopped');
  }
}
