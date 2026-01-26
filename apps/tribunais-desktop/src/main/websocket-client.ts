/**
 * Cliente WebSocket para comunicação com servidor Iudex
 */

import WebSocket from 'ws';
import { EventEmitter } from 'events';
import { randomUUID } from 'crypto';

interface WSMessage {
  type: 'command' | 'response' | 'event';
  id: string;
  action?: string;
  params?: Record<string, unknown>;
  success?: boolean;
  data?: unknown;
  error?: string;
}

export class WebSocketClient extends EventEmitter {
  private ws: WebSocket | null = null;
  private sessionId: string | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectDelay = 2000;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private pingInterval: NodeJS.Timeout | null = null;
  private pendingResponses = new Map<string, {
    resolve: (value: unknown) => void;
    reject: (error: Error) => void;
    timeout: NodeJS.Timeout;
  }>();

  constructor(
    private serverUrl: string,
    private userId: string
  ) {
    super();
  }

  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.serverUrl);

        this.ws.on('open', () => {
          console.log('WebSocket conectado');
          this.reconnectAttempts = 0;
          this.startPingInterval();
        });

        this.ws.on('message', (data) => {
          this.handleMessage(data.toString());
        });

        this.ws.on('close', () => {
          console.log('WebSocket desconectado');
          this.stopPingInterval();
          this.emit('disconnected');
          this.scheduleReconnect();
        });

        this.ws.on('error', (error) => {
          console.error('WebSocket erro:', error);
          this.emit('error', error.message);
          reject(error);
        });

        this.ws.on('pong', () => {
          // Pong recebido, conexão está viva
        });

        // Aguardar autenticação
        const authTimeout = setTimeout(() => {
          reject(new Error('Timeout na autenticação'));
        }, 10000);

        this.once('authenticated', () => {
          clearTimeout(authTimeout);
          resolve();
        });
      } catch (error) {
        reject(error);
      }
    });
  }

  disconnect(): void {
    this.stopPingInterval();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.sessionId = null;
  }

  reconnect(): void {
    this.disconnect();
    this.reconnectAttempts = 0;
    this.connect().catch((error) => {
      console.error('Erro ao reconectar:', error);
    });
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  private handleMessage(data: string): void {
    try {
      const message = JSON.parse(data) as WSMessage;

      switch (message.type) {
        case 'event':
          this.handleEvent(message);
          break;

        case 'command':
          this.handleCommand(message);
          break;

        case 'response':
          this.handleResponse(message);
          break;
      }
    } catch (error) {
      console.error('Erro ao processar mensagem:', error);
    }
  }

  private handleEvent(message: WSMessage): void {
    switch (message.action) {
      case 'authenticate':
        // Servidor solicitou autenticação
        this.sessionId = message.params?.sessionId as string;
        this.sendAuthentication();
        break;

      default:
        console.log('Evento desconhecido:', message.action);
    }
  }

  private handleCommand(message: WSMessage): void {
    switch (message.action) {
      case 'request_interaction':
        // Servidor solicita interação do usuário
        this.emit('operation', {
          operationId: message.id,
          jobId: message.params?.jobId,
          operation: message.params?.operation,
          tribunal: message.params?.tribunal,
          message: message.params?.message,
        });
        break;

      case 'request_signature':
        // Servidor solicita assinatura
        this.emit('signature-required', {
          operationId: message.id,
          jobId: message.params?.jobId,
          dataToSign: message.params?.dataToSign,
          message: message.params?.message,
        });
        break;

      case 'execute_browser_action':
        // Servidor solicita ação no navegador (para login A3)
        this.emit('browser-action', {
          operationId: message.id,
          action: message.params?.action,
          url: message.params?.url,
          params: message.params,
        });
        break;

      case 'request_captcha_solution':
        // Servidor solicita resolução de CAPTCHA
        this.emit('captcha-required', {
          operationId: message.id,
          captchaId: message.params?.captchaId,
          jobId: message.params?.jobId,
          tribunal: message.params?.tribunal,
          tribunalUrl: message.params?.tribunalUrl,
          captcha: message.params?.captcha,
          expiresAt: message.params?.expiresAt,
        });
        break;

      default:
        console.log('Comando desconhecido:', message.action);
    }
  }

  /**
   * Envia solução de CAPTCHA para o servidor
   */
  sendCaptchaSolution(
    captchaId: string,
    jobId: string,
    success: boolean,
    solution?: { token?: string; text?: string },
    error?: string
  ): void {
    this.send({
      type: 'event',
      id: randomUUID(),
      action: 'captcha_solved',
      params: {
        captchaId,
        jobId,
        success,
        solution,
        error,
      },
    });
  }

  private handleResponse(message: WSMessage): void {
    const pending = this.pendingResponses.get(message.id);
    if (pending) {
      clearTimeout(pending.timeout);
      this.pendingResponses.delete(message.id);

      if (message.success) {
        pending.resolve(message.data);
      } else {
        pending.reject(new Error(message.error || 'Erro desconhecido'));
      }
    }

    // Resposta de autenticação
    if (message.id === 'auth' && message.success) {
      this.emit('authenticated');
      this.emit('connected');
    }
  }

  private sendAuthentication(): void {
    this.send({
      type: 'command',
      id: 'auth',
      action: 'authenticate',
      params: {
        userId: this.userId,
        clientType: 'desktop',
        platform: process.platform,
        version: '0.1.0',
      },
    });
  }

  send(message: WSMessage): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.error('WebSocket não conectado');
      return;
    }

    this.ws.send(JSON.stringify(message));
  }

  sendResponse(
    operationId: string,
    status: 'approved' | 'rejected' | 'signed' | 'error',
    data?: Record<string, unknown>
  ): void {
    this.send({
      type: 'response',
      id: operationId,
      success: status === 'approved' || status === 'signed',
      data: {
        status,
        ...data,
      },
      error: status === 'error' ? data?.error as string : undefined,
    });
  }

  async request(action: string, params: Record<string, unknown>, timeout = 30000): Promise<unknown> {
    return new Promise((resolve, reject) => {
      const id = randomUUID();

      const timeoutHandle = setTimeout(() => {
        this.pendingResponses.delete(id);
        reject(new Error('Timeout na requisição'));
      }, timeout);

      this.pendingResponses.set(id, {
        resolve,
        reject,
        timeout: timeoutHandle,
      });

      this.send({
        type: 'command',
        id,
        action,
        params,
      });
    });
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log('Máximo de tentativas de reconexão atingido');
      this.emit('max-reconnect-attempts');
      return;
    }

    const delay = this.reconnectDelay * Math.pow(2, Math.min(this.reconnectAttempts, 5));
    console.log(`Reconectando em ${delay}ms...`);

    this.reconnectTimer = setTimeout(() => {
      this.reconnectAttempts++;
      this.connect().catch((error) => {
        console.error('Erro ao reconectar:', error);
      });
    }, delay);
  }

  private startPingInterval(): void {
    this.pingInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.ping();
      }
    }, 30000);
  }

  private stopPingInterval(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }
}
