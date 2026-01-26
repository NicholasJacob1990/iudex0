/**
 * API HTTP completa para SEI
 * Expõe TODAS as funcionalidades da biblioteca via REST
 */

import { createServer, type IncomingMessage, type ServerResponse } from 'http';
import { SEIService, type SEIServiceConfig } from './service.js';
import { SEIClient } from './client.js';
import { SEIDaemon, type DaemonConfig } from './daemon.js';
import type { SEIUserConfig, SEICredentials } from './users.js';
import type { CreateProcessOptions, CreateDocumentOptions, ForwardOptions } from './types.js';
import type { WatchType } from './watcher.js';
import type { EmailConfig } from './notifications.js';

export interface APIConfig extends SEIServiceConfig {
  /** URL base do SEI (ex: https://sei.mg.gov.br) */
  baseUrl: string;
  /** Porta da API (padrão: 3001) */
  port?: number;
  /** Host (padrão: localhost) */
  host?: string;
  /** API Key para autenticação */
  apiKey?: string;
}

interface APIRequest {
  method: string;
  path: string;
  pathParts: string[];
  params: Record<string, string>;
  query: Record<string, string>;
  body: unknown;
}

interface APIResponse {
  status: number;
  data?: unknown;
  error?: string;
}

// Sessões ativas de clientes SEI
interface SEISession {
  client: SEIClient;
  userId: string;
  createdAt: Date;
  lastUsed: Date;
}

/**
 * API HTTP completa para SEI
 *
 * ## Endpoints
 *
 * ### Sessões
 * - `POST /sessions` - Criar sessão (login)
 * - `DELETE /sessions/:sessionId` - Encerrar sessão
 *
 * ### Usuários (monitoramento)
 * - `GET /users` - Lista usuários cadastrados
 * - `POST /users` - Cadastra usuário
 * - `GET /users/:id` - Obtém usuário
 * - `PUT /users/:id` - Atualiza usuário
 * - `DELETE /users/:id` - Remove usuário
 * - `POST /users/:id/start` - Inicia monitoramento
 * - `POST /users/:id/stop` - Para monitoramento
 *
 * ### Processos
 * - `GET /process/:number` - Consulta processo
 * - `POST /process` - Cria processo
 * - `POST /process/:number/forward` - Tramita processo
 * - `POST /process/:number/conclude` - Conclui processo
 * - `POST /process/:number/reopen` - Reabre processo
 * - `POST /process/:number/anexar` - Anexa processo
 * - `POST /process/:number/relacionar` - Relaciona processos
 * - `POST /process/:number/atribuir` - Atribui processo
 * - `GET /process/:number/andamentos` - Lista andamentos
 * - `GET /process/:number/documents` - Lista documentos
 * - `POST /process/:number/documents` - Cria documento
 * - `POST /process/:number/upload` - Upload documento
 *
 * ### Documentos
 * - `GET /document/:id` - Consulta documento
 * - `POST /document/:id/sign` - Assina documento
 * - `POST /document/:id/cancel` - Cancela documento
 *
 * ### Blocos
 * - `GET /blocos` - Lista blocos
 * - `POST /blocos` - Cria bloco
 * - `GET /bloco/:id` - Consulta bloco
 * - `POST /bloco/:id/documentos` - Adiciona documento
 * - `DELETE /bloco/:id/documentos/:docId` - Remove documento
 * - `POST /bloco/:id/disponibilizar` - Disponibiliza bloco
 *
 * ### Listagens
 * - `GET /tipos-processo` - Tipos de processo
 * - `GET /tipos-documento` - Tipos de documento
 * - `GET /unidades` - Unidades
 *
 * ### Status
 * - `GET /status` - Status do serviço
 * - `POST /start` - Inicia todos
 * - `POST /stop` - Para todos
 *
 * ### Daemon (Monitoramento Contínuo)
 * - `GET /daemon/status` - Status do daemon
 * - `POST /daemon/start` - Inicia daemon (headless ou CDP)
 * - `POST /daemon/stop` - Para daemon
 * - `GET /daemon/config` - Configuração atual
 * - `PUT /daemon/config` - Atualiza configuração
 *
 * ### Downloads
 * - `GET /process/:number/download` - Baixar processo (PDF/ZIP)
 * - `GET /document/:id/download` - Baixar documento
 *
 * ### Anotações
 * - `GET /process/:number/annotations` - Lista anotações
 * - `POST /process/:number/annotations` - Adiciona anotação
 *
 * ### Marcadores
 * - `POST /process/:number/markers` - Adiciona marcador
 * - `DELETE /process/:number/markers/:marcador` - Remove marcador
 *
 * ### Prazos
 * - `POST /process/:number/deadline` - Define prazo
 *
 * ### Acesso
 * - `POST /process/:number/access` - Concede acesso
 * - `DELETE /process/:number/access/:usuario` - Revoga acesso
 *
 * ### Ciência e Publicação
 * - `POST /document/:id/knowledge` - Registra ciência
 * - `POST /document/:id/publish` - Agenda publicação
 *
 * ### Assinatura em Lote
 * - `POST /documents/sign-multiple` - Assina múltiplos
 * - `POST /bloco/:id/sign` - Assina bloco inteiro
 *
 * ### Listagens Adicionais
 * - `GET /usuarios` - Lista usuários SEI
 * - `GET /hipoteses-legais` - Hipóteses legais
 * - `GET /marcadores` - Marcadores disponíveis
 * - `GET /meus-processos` - Processos do usuário
 *
 * ### Navegação/Debug
 * - `GET /screenshot` - Captura tela
 * - `GET /snapshot` - Estado ARIA
 * - `GET /current-page` - Página atual
 * - `POST /navigate` - Navega para destino
 * - `POST /click` - Clica em elemento
 * - `POST /type` - Digita texto
 * - `POST /select` - Seleciona opção
 * - `POST /wait` - Aguarda elemento
 */
export class SEIServiceAPI {
  private config: APIConfig;
  private service: SEIService;
  private server: ReturnType<typeof createServer> | null = null;
  private sessions: Map<string, SEISession> = new Map();
  private sessionTimeout = 30 * 60 * 1000; // 30 minutos
  private daemon: SEIDaemon | null = null;
  private daemonConfig: DaemonStartRequest | null = null;

  constructor(config: APIConfig) {
    this.config = {
      port: 3001,
      host: 'localhost',
      ...config,
    };

    this.service = new SEIService(config);
  }

  /** Inicia a API */
  async start(): Promise<void> {
    await this.service.init();

    // Limpar sessões expiradas periodicamente
    setInterval(() => this.cleanupSessions(), 5 * 60 * 1000);

    this.server = createServer(async (req, res) => {
      // CORS
      res.setHeader('Access-Control-Allow-Origin', '*');
      res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type, X-API-Key, X-Session-Id');

      if (req.method === 'OPTIONS') {
        res.writeHead(204);
        res.end();
        return;
      }

      // Autenticação por API Key
      if (this.config.apiKey) {
        const apiKey = req.headers['x-api-key'];
        if (apiKey !== this.config.apiKey) {
          this.sendResponse(res, { status: 401, error: 'Unauthorized' });
          return;
        }
      }

      try {
        const request = await this.parseRequest(req);
        const sessionId = req.headers['x-session-id'] as string | undefined;
        const response = await this.handleRequest(request, sessionId);
        this.sendResponse(res, response);
      } catch (error) {
        console.error('API Error:', error);
        this.sendResponse(res, {
          status: 500,
          error: error instanceof Error ? error.message : 'Internal Server Error',
        });
      }
    });

    return new Promise((resolve) => {
      this.server!.listen(this.config.port, this.config.host, () => {
        console.log(`SEI API rodando em http://${this.config.host}:${this.config.port}`);
        resolve();
      });
    });
  }

  /** Para a API */
  async stop(): Promise<void> {
    // Fechar todas as sessões
    for (const [, session] of this.sessions) {
      await session.client.close();
    }
    this.sessions.clear();

    await this.service.stopAll();

    if (this.server) {
      return new Promise((resolve) => {
        this.server!.close(() => resolve());
      });
    }
  }

  /** Acesso ao serviço interno */
  getService(): SEIService {
    return this.service;
  }

  /** Limpa sessões expiradas */
  private cleanupSessions(): void {
    const now = Date.now();
    for (const [id, session] of this.sessions) {
      if (now - session.lastUsed.getTime() > this.sessionTimeout) {
        session.client.close();
        this.sessions.delete(id);
      }
    }
  }

  /** Obtém ou cria sessão para usuário */
  private async getSession(sessionId?: string): Promise<SEISession | null> {
    if (!sessionId) return null;

    const session = this.sessions.get(sessionId);
    if (session) {
      session.lastUsed = new Date();
      return session;
    }

    return null;
  }

  /** Parse da requisição */
  private async parseRequest(req: IncomingMessage): Promise<APIRequest> {
    const url = new URL(req.url ?? '/', `http://${req.headers.host}`);
    const pathParts = url.pathname.split('/').filter(Boolean);

    // Query params
    const query: Record<string, string> = {};
    url.searchParams.forEach((value, key) => {
      query[key] = value;
    });

    // Path params
    const params: Record<string, string> = {};

    // Parse do body
    let body: unknown = {};
    if (req.method === 'POST' || req.method === 'PUT') {
      body = await this.parseBody(req);
    }

    return {
      method: req.method ?? 'GET',
      path: url.pathname,
      pathParts,
      params,
      query,
      body,
    };
  }

  /** Parse do body JSON */
  private parseBody(req: IncomingMessage): Promise<unknown> {
    return new Promise((resolve, reject) => {
      let data = '';
      req.on('data', (chunk) => (data += chunk));
      req.on('end', () => {
        try {
          resolve(data ? JSON.parse(data) : {});
        } catch {
          reject(new Error('Invalid JSON'));
        }
      });
      req.on('error', reject);
    });
  }

  /** Envia resposta */
  private sendResponse(res: ServerResponse, response: APIResponse): void {
    res.writeHead(response.status, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(response.error ? { error: response.error } : response.data));
  }

  /** Roteamento de requisições */
  private async handleRequest(req: APIRequest, sessionId?: string): Promise<APIResponse> {
    const { method, path, pathParts, body } = req;

    // ============================================
    // Status e Controle Global
    // ============================================

    if (path === '/status' && method === 'GET') {
      return this.handleGetStatus();
    }

    if (path === '/start' && method === 'POST') {
      return this.handleStartAll();
    }

    if (path === '/stop' && method === 'POST') {
      return this.handleStopAll();
    }

    // ============================================
    // Daemon (Monitoramento Contínuo)
    // ============================================

    if (path === '/daemon/status' && method === 'GET') {
      return this.handleDaemonStatus();
    }

    if (path === '/daemon/start' && method === 'POST') {
      return this.handleDaemonStart(body as DaemonStartRequest);
    }

    if (path === '/daemon/stop' && method === 'POST') {
      return this.handleDaemonStop();
    }

    if (path === '/daemon/config' && method === 'GET') {
      return this.handleDaemonGetConfig();
    }

    if (path === '/daemon/config' && method === 'PUT') {
      return this.handleDaemonUpdateConfig(body as Partial<DaemonStartRequest>);
    }

    // ============================================
    // Sessões
    // ============================================

    if (path === '/sessions' && method === 'POST') {
      return this.handleCreateSession(body as CreateSessionRequest);
    }

    if (pathParts[0] === 'sessions' && pathParts[1] && method === 'DELETE') {
      return this.handleDeleteSession(pathParts[1]);
    }

    // ============================================
    // Usuários (Monitoramento)
    // ============================================

    if (path === '/users' && method === 'GET') {
      return this.handleListUsers();
    }

    if (path === '/users' && method === 'POST') {
      return this.handleAddUser(body as AddUserRequest);
    }

    if (pathParts[0] === 'users' && pathParts[1]) {
      const userId = pathParts[1];

      if (!pathParts[2]) {
        if (method === 'GET') return this.handleGetUser(userId);
        if (method === 'PUT') return this.handleUpdateUser(userId, body as Partial<SEIUserConfig>);
        if (method === 'DELETE') return this.handleDeleteUser(userId);
      }

      if (pathParts[2] === 'credentials' && method === 'PUT') {
        return this.handleUpdateCredentials(userId, body as SEICredentials);
      }

      if (pathParts[2] === 'start' && method === 'POST') {
        return this.handleStartUser(userId);
      }

      if (pathParts[2] === 'stop' && method === 'POST') {
        return this.handleStopUser(userId);
      }
    }

    // ============================================
    // Listagens (requer sessão)
    // ============================================

    if (path === '/tipos-processo' && method === 'GET') {
      return this.handleWithSession(sessionId, (client) => this.handleListProcessTypes(client));
    }

    if (path === '/tipos-documento' && method === 'GET') {
      return this.handleWithSession(sessionId, (client) => this.handleListDocumentTypes(client));
    }

    if (path === '/unidades' && method === 'GET') {
      return this.handleWithSession(sessionId, (client) => this.handleListUnits(client, req.query));
    }

    if (path === '/usuarios' && method === 'GET') {
      return this.handleWithSession(sessionId, (client) => this.handleListUsuarios(client, req.query));
    }

    if (path === '/hipoteses-legais' && method === 'GET') {
      return this.handleWithSession(sessionId, (client) => this.handleListHipotesesLegais(client));
    }

    if (path === '/marcadores' && method === 'GET') {
      return this.handleWithSession(sessionId, (client) => this.handleListMarcadores(client));
    }

    if (path === '/meus-processos' && method === 'GET') {
      return this.handleWithSession(sessionId, (client) =>
        this.handleListMeusProcessos(client, req.query)
      );
    }

    // ============================================
    // Navegação e Debug (requer sessão)
    // ============================================

    if (path === '/screenshot' && method === 'GET') {
      return this.handleWithSession(sessionId, (client) =>
        this.handleScreenshot(client, req.query)
      );
    }

    if (path === '/snapshot' && method === 'GET') {
      return this.handleWithSession(sessionId, (client) =>
        this.handleSnapshot(client, req.query)
      );
    }

    if (path === '/current-page' && method === 'GET') {
      return this.handleWithSession(sessionId, (client) => this.handleGetCurrentPage(client));
    }

    if (path === '/navigate' && method === 'POST') {
      return this.handleWithSession(sessionId, (client) =>
        this.handleNavigate(client, body as NavigateRequest)
      );
    }

    if (path === '/click' && method === 'POST') {
      return this.handleWithSession(sessionId, (client) =>
        this.handleClick(client, body as ClickRequest)
      );
    }

    if (path === '/type' && method === 'POST') {
      return this.handleWithSession(sessionId, (client) =>
        this.handleType(client, body as TypeRequest)
      );
    }

    if (path === '/select' && method === 'POST') {
      return this.handleWithSession(sessionId, (client) =>
        this.handleSelect(client, body as SelectRequest)
      );
    }

    if (path === '/wait' && method === 'POST') {
      return this.handleWithSession(sessionId, (client) =>
        this.handleWait(client, body as WaitRequest)
      );
    }

    // ============================================
    // Assinatura em Lote (requer sessão)
    // ============================================

    if (path === '/documents/sign-multiple' && method === 'POST') {
      return this.handleWithSession(sessionId, (client) =>
        this.handleSignMultiple(client, body as SignMultipleRequest)
      );
    }

    // ============================================
    // Processos (requer sessão)
    // ============================================

    if (path === '/process/search' && method === 'GET') {
      return this.handleWithSession(sessionId, (client) =>
        this.handleSearchProcess(client, req.query)
      );
    }

    if (path === '/process' && method === 'POST') {
      return this.handleWithSession(sessionId, (client) =>
        this.handleCreateProcess(client, body as CreateProcessRequest)
      );
    }

    if (pathParts[0] === 'process' && pathParts[1]) {
      const processNumber = decodeURIComponent(pathParts[1]);

      if (!pathParts[2]) {
        if (method === 'GET') {
          return this.handleWithSession(sessionId, (client) =>
            this.handleGetProcess(client, processNumber)
          );
        }
      }

      if (pathParts[2] === 'open' && method === 'POST') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleOpenProcess(client, processNumber)
        );
      }

      if (pathParts[2] === 'status' && method === 'GET') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleGetProcessStatus(client, processNumber, req.query)
        );
      }

      if (pathParts[2] === 'download' && method === 'GET') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleDownloadProcess(client, processNumber, req.query)
        );
      }

      if (pathParts[2] === 'annotations') {
        if (method === 'GET') {
          return this.handleWithSession(sessionId, (client) =>
            this.handleListAnnotations(client, processNumber)
          );
        }
        if (method === 'POST') {
          return this.handleWithSession(sessionId, (client) =>
            this.handleAddAnnotation(client, processNumber, body as AddAnnotationRequest)
          );
        }
      }

      if (pathParts[2] === 'markers') {
        if (method === 'POST') {
          return this.handleWithSession(sessionId, (client) =>
            this.handleAddMarker(client, processNumber, body as AddMarkerRequest)
          );
        }
        if (method === 'DELETE' && pathParts[3]) {
          return this.handleWithSession(sessionId, (client) =>
            this.handleRemoveMarker(client, processNumber, decodeURIComponent(pathParts[3]))
          );
        }
      }

      if (pathParts[2] === 'deadline' && method === 'POST') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleSetDeadline(client, processNumber, body as SetDeadlineRequest)
        );
      }

      if (pathParts[2] === 'access') {
        if (method === 'POST') {
          return this.handleWithSession(sessionId, (client) =>
            this.handleGrantAccess(client, processNumber, body as GrantAccessRequest)
          );
        }
        if (method === 'DELETE' && pathParts[3]) {
          return this.handleWithSession(sessionId, (client) =>
            this.handleRevokeAccess(client, processNumber, decodeURIComponent(pathParts[3]))
          );
        }
      }

      if (pathParts[2] === 'forward' && method === 'POST') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleForwardProcess(client, processNumber, body as ForwardProcessRequest)
        );
      }

      if (pathParts[2] === 'conclude' && method === 'POST') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleConcludeProcess(client, processNumber)
        );
      }

      if (pathParts[2] === 'reopen' && method === 'POST') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleReopenProcess(client, processNumber)
        );
      }

      if (pathParts[2] === 'anexar' && method === 'POST') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleAnexarProcess(client, processNumber, body as AnexarProcessRequest)
        );
      }

      if (pathParts[2] === 'relacionar' && method === 'POST') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleRelacionarProcess(client, processNumber, body as RelacionarProcessRequest)
        );
      }

      if (pathParts[2] === 'atribuir' && method === 'POST') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleAtribuirProcess(client, processNumber, body as AtribuirProcessRequest)
        );
      }

      if (pathParts[2] === 'andamentos' && method === 'GET') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleListAndamentos(client, processNumber)
        );
      }

      if (pathParts[2] === 'documents') {
        if (method === 'GET') {
          return this.handleWithSession(sessionId, (client) =>
            this.handleListDocuments(client, processNumber)
          );
        }
        if (method === 'POST') {
          return this.handleWithSession(sessionId, (client) =>
            this.handleCreateDocument(client, processNumber, body as CreateDocumentRequest)
          );
        }
      }

      if (pathParts[2] === 'upload' && method === 'POST') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleUploadDocument(client, processNumber, body as UploadDocumentRequest)
        );
      }

      if (pathParts[2] === 'upload-base64' && method === 'POST') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleUploadDocumentBase64(client, processNumber, body as UploadDocumentBase64Request)
        );
      }

      if (pathParts[2] === 'relate' && method === 'POST') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleRelateProcess(client, processNumber, body as RelateProcessRequest)
        );
      }
    }

    // ============================================
    // Documentos (requer sessão)
    // ============================================

    if (pathParts[0] === 'document' && pathParts[1]) {
      const documentId = pathParts[1];

      if (!pathParts[2] && method === 'GET') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleGetDocument(client, documentId, req.query)
        );
      }

      if (pathParts[2] === 'sign' && method === 'POST') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleSignDocument(client, documentId, body as SignDocumentRequest)
        );
      }

      if (pathParts[2] === 'cancel' && method === 'POST') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleCancelDocument(client, documentId, body as CancelDocumentRequest)
        );
      }

      if (pathParts[2] === 'download' && method === 'GET') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleDownloadDocument(client, documentId, req.query)
        );
      }

      if (pathParts[2] === 'knowledge' && method === 'POST') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleRegisterKnowledge(client, documentId)
        );
      }

      if (pathParts[2] === 'publish' && method === 'POST') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleSchedulePublication(client, documentId, body as SchedulePublicationRequest)
        );
      }
    }

    // ============================================
    // Blocos (requer sessão)
    // ============================================

    if (path === '/blocos' && method === 'GET') {
      return this.handleWithSession(sessionId, (client) => this.handleListBlocos(client));
    }

    if (path === '/blocos' && method === 'POST') {
      return this.handleWithSession(sessionId, (client) =>
        this.handleCreateBloco(client, body as CreateBlocoRequest)
      );
    }

    if (pathParts[0] === 'bloco' && pathParts[1]) {
      const blocoId = pathParts[1];

      if (!pathParts[2] && method === 'GET') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleGetBloco(client, blocoId)
        );
      }

      if (pathParts[2] === 'documentos') {
        if (method === 'POST') {
          return this.handleWithSession(sessionId, (client) =>
            this.handleAddDocumentoToBloco(client, blocoId, body as AddDocumentoBlocoRequest)
          );
        }
        if (method === 'DELETE' && pathParts[3]) {
          return this.handleWithSession(sessionId, (client) =>
            this.handleRemoveDocumentoFromBloco(client, blocoId, pathParts[3])
          );
        }
      }

      if (pathParts[2] === 'disponibilizar' && method === 'POST') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleDisponibilizarBloco(client, blocoId, body as DisponibilizarBlocoRequest)
        );
      }

      if (pathParts[2] === 'release' && method === 'POST') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleReleaseBloco(client, blocoId)
        );
      }

      if (pathParts[2] === 'sign' && method === 'POST') {
        return this.handleWithSession(sessionId, (client) =>
          this.handleSignBloco(client, blocoId, body as SignBlocoRequest)
        );
      }

      // Alias: documents -> documentos
      if (pathParts[2] === 'documents') {
        if (method === 'POST') {
          return this.handleWithSession(sessionId, (client) =>
            this.handleAddDocumentoToBloco(client, blocoId, body as AddDocumentoBlocoRequest)
          );
        }
        if (method === 'DELETE' && pathParts[3]) {
          return this.handleWithSession(sessionId, (client) =>
            this.handleRemoveDocumentoFromBloco(client, blocoId, pathParts[3])
          );
        }
      }
    }

    return { status: 404, error: 'Not Found' };
  }

  /** Executa handler com sessão */
  private async handleWithSession(
    sessionId: string | undefined,
    handler: (client: SEIClient) => Promise<APIResponse>
  ): Promise<APIResponse> {
    const session = await this.getSession(sessionId);
    if (!session) {
      return { status: 401, error: 'Session required. Create session with POST /sessions' };
    }

    return handler(session.client);
  }

  // ============================================
  // Handlers - Status e Controle
  // ============================================

  private async handleGetStatus(): Promise<APIResponse> {
    return {
      status: 200,
      data: {
        running: this.service.running,
        activeSessions: this.service.getActiveSessions(),
        totalUsers: this.service.getAllUsers().length,
        apiSessions: this.sessions.size,
      },
    };
  }

  private async handleStartAll(): Promise<APIResponse> {
    await this.service.startAll();
    return { status: 200, data: { message: 'Started' } };
  }

  private async handleStopAll(): Promise<APIResponse> {
    await this.service.stopAll();
    return { status: 200, data: { message: 'Stopped' } };
  }

  // ============================================
  // Handlers - Sessões
  // ============================================

  private async handleCreateSession(body: CreateSessionRequest): Promise<APIResponse> {
    if (!body.seiUrl || !body.usuario || !body.senha) {
      return { status: 400, error: 'Missing required fields: seiUrl, usuario, senha' };
    }

    try {
      const client = new SEIClient({
        baseUrl: body.seiUrl,
        browser: {
          usuario: body.usuario,
          senha: body.senha,
          orgao: body.orgao,
        },
        soap: body.soap,
        playwright: { headless: true },
      });

      await client.init();
      const loggedIn = await client.login();

      if (!loggedIn) {
        await client.close();
        return { status: 401, error: 'Login failed' };
      }

      // Gerar ID de sessão
      const sessionId = `sess_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

      this.sessions.set(sessionId, {
        client,
        userId: body.usuario,
        createdAt: new Date(),
        lastUsed: new Date(),
      });

      return {
        status: 201,
        data: {
          sessionId,
          message: 'Session created',
          expiresIn: this.sessionTimeout / 1000,
        },
      };
    } catch (error) {
      return { status: 500, error: error instanceof Error ? error.message : 'Session creation failed' };
    }
  }

  private async handleDeleteSession(sessionId: string): Promise<APIResponse> {
    const session = this.sessions.get(sessionId);
    if (!session) {
      return { status: 404, error: 'Session not found' };
    }

    await session.client.close();
    this.sessions.delete(sessionId);

    return { status: 200, data: { message: 'Session closed' } };
  }

  // ============================================
  // Handlers - Usuários
  // ============================================

  private async handleListUsers(): Promise<APIResponse> {
    const users = this.service.getAllUsers();
    return { status: 200, data: { users } };
  }

  private async handleGetUser(id: string): Promise<APIResponse> {
    const user = this.service.getUser(id);
    if (!user) {
      return { status: 404, error: 'User not found' };
    }
    return { status: 200, data: user };
  }

  private async handleAddUser(body: AddUserRequest): Promise<APIResponse> {
    if (!body.id || !body.nome || !body.email || !body.seiUrl || !body.credentials) {
      return { status: 400, error: 'Missing required fields' };
    }

    try {
      const user = await this.service.addUser(body);
      return { status: 201, data: user };
    } catch (error) {
      return { status: 400, error: error instanceof Error ? error.message : 'Error' };
    }
  }

  private async handleUpdateUser(id: string, body: Partial<SEIUserConfig>): Promise<APIResponse> {
    try {
      const user = await this.service.updateUser(id, body);
      return { status: 200, data: user };
    } catch (error) {
      return { status: 400, error: error instanceof Error ? error.message : 'Error' };
    }
  }

  private async handleDeleteUser(id: string): Promise<APIResponse> {
    try {
      await this.service.removeUser(id);
      return { status: 200, data: { message: 'Deleted' } };
    } catch (error) {
      return { status: 400, error: error instanceof Error ? error.message : 'Error' };
    }
  }

  private async handleUpdateCredentials(id: string, body: SEICredentials): Promise<APIResponse> {
    if (!body.usuario || !body.senha) {
      return { status: 400, error: 'Missing credentials' };
    }

    try {
      await this.service.updateCredentials(id, body);
      return { status: 200, data: { message: 'Credentials updated' } };
    } catch (error) {
      return { status: 400, error: error instanceof Error ? error.message : 'Error' };
    }
  }

  private async handleStartUser(id: string): Promise<APIResponse> {
    try {
      const started = await this.service.startUser(id);
      return { status: 200, data: { started } };
    } catch (error) {
      return { status: 400, error: error instanceof Error ? error.message : 'Error' };
    }
  }

  private async handleStopUser(id: string): Promise<APIResponse> {
    try {
      await this.service.stopUser(id);
      return { status: 200, data: { message: 'Stopped' } };
    } catch (error) {
      return { status: 400, error: error instanceof Error ? error.message : 'Error' };
    }
  }

  // ============================================
  // Handlers - Listagens
  // ============================================

  private async handleListProcessTypes(client: SEIClient): Promise<APIResponse> {
    const tipos = await client.listProcessTypes();
    return { status: 200, data: { tipos } };
  }

  private async handleListDocumentTypes(client: SEIClient): Promise<APIResponse> {
    const tipos = await client.listDocumentTypes();
    return { status: 200, data: { tipos } };
  }

  // ============================================
  // Handlers - Processos
  // ============================================

  private async handleCreateProcess(client: SEIClient, body: CreateProcessRequest): Promise<APIResponse> {
    if (!body.tipoProcedimento || !body.especificacao || !body.assuntos?.length) {
      return { status: 400, error: 'Missing required fields: tipoProcedimento, especificacao, assuntos' };
    }

    const result = await client.createProcess(body);
    return { status: 201, data: result };
  }

  private async handleGetProcess(client: SEIClient, processNumber: string): Promise<APIResponse> {
    const process = await client.getProcess(processNumber);
    return { status: 200, data: process };
  }

  private async handleForwardProcess(
    client: SEIClient,
    processNumber: string,
    body: ForwardProcessRequest
  ): Promise<APIResponse> {
    if (!body.unidadesDestino?.length) {
      return { status: 400, error: 'Missing unidadesDestino' };
    }

    const success = await client.forwardProcess(processNumber, body);
    return { status: 200, data: { success } };
  }

  private async handleConcludeProcess(client: SEIClient, processNumber: string): Promise<APIResponse> {
    const success = await client.concludeProcess(processNumber);
    return { status: 200, data: { success } };
  }

  private async handleReopenProcess(client: SEIClient, processNumber: string): Promise<APIResponse> {
    const success = await client.reopenProcess(processNumber);
    return { status: 200, data: { success } };
  }

  private async handleAnexarProcess(
    client: SEIClient,
    processNumber: string,
    body: AnexarProcessRequest
  ): Promise<APIResponse> {
    if (!body.processoAnexado) {
      return { status: 400, error: 'Missing processoAnexado' };
    }

    const success = await client.anexarProcesso(processNumber, body.processoAnexado);
    return { status: 200, data: { success } };
  }

  private async handleRelacionarProcess(
    client: SEIClient,
    processNumber: string,
    body: RelacionarProcessRequest
  ): Promise<APIResponse> {
    if (!body.processoRelacionado) {
      return { status: 400, error: 'Missing processoRelacionado' };
    }

    const success = await client.relacionarProcesso(processNumber, body.processoRelacionado);
    return { status: 200, data: { success } };
  }

  private async handleAtribuirProcess(
    client: SEIClient,
    processNumber: string,
    body: AtribuirProcessRequest
  ): Promise<APIResponse> {
    if (!body.usuario) {
      return { status: 400, error: 'Missing usuario' };
    }

    const success = await client.atribuirProcesso(processNumber, body.usuario, body.reabrir);
    return { status: 200, data: { success } };
  }

  private async handleListAndamentos(client: SEIClient, processNumber: string): Promise<APIResponse> {
    const andamentos = await client.listAndamentos(processNumber);
    return { status: 200, data: { andamentos } };
  }

  // ============================================
  // Handlers - Documentos
  // ============================================

  private async handleListDocuments(client: SEIClient, processNumber: string): Promise<APIResponse> {
    await client.openProcess(processNumber);
    const documents = await client.listDocuments();
    return { status: 200, data: { documents } };
  }

  private async handleCreateDocument(
    client: SEIClient,
    processNumber: string,
    body: CreateDocumentRequest
  ): Promise<APIResponse> {
    if (!body.idSerie) {
      return { status: 400, error: 'Missing idSerie' };
    }

    const documentId = await client.createDocument(processNumber, body);
    return { status: 201, data: { documentId } };
  }

  private async handleUploadDocument(
    client: SEIClient,
    processNumber: string,
    body: UploadDocumentRequest
  ): Promise<APIResponse> {
    if (!body.nomeArquivo || !body.conteudoBase64) {
      return { status: 400, error: 'Missing nomeArquivo or conteudoBase64' };
    }

    const documentId = await client.uploadDocument(
      processNumber,
      body.nomeArquivo,
      body.conteudoBase64,
      body
    );
    return { status: 201, data: { documentId } };
  }

  private async handleSignDocument(
    client: SEIClient,
    documentId: string,
    body: SignDocumentRequest
  ): Promise<APIResponse> {
    if (!body.senha) {
      return { status: 400, error: 'Missing senha' };
    }

    // Precisa abrir o documento primeiro
    const browserClient = client.getBrowserClient();
    if (browserClient) {
      await browserClient.openDocument(documentId);
    }

    const success = await client.signDocument(body.senha, body.cargo);
    return { status: 200, data: { success } };
  }

  private async handleCancelDocument(
    client: SEIClient,
    documentId: string,
    body: CancelDocumentRequest
  ): Promise<APIResponse> {
    if (!body.motivo) {
      return { status: 400, error: 'Missing motivo' };
    }

    const success = await client.cancelDocument(documentId, body.motivo);
    return { status: 200, data: { success } };
  }

  // ============================================
  // Handlers - Blocos
  // ============================================

  private async handleListBlocos(client: SEIClient): Promise<APIResponse> {
    const blocos = await client.listBlocos();
    return { status: 200, data: { blocos } };
  }

  private async handleCreateBloco(client: SEIClient, body: CreateBlocoRequest): Promise<APIResponse> {
    if (!body.descricao) {
      return { status: 400, error: 'Missing descricao' };
    }

    const blocoId = await client.createBloco(
      body.descricao,
      body.tipo ?? 'assinatura',
      body.unidades,
      body.documentos
    );
    return { status: 201, data: { blocoId } };
  }

  private async handleGetBloco(client: SEIClient, blocoId: string): Promise<APIResponse> {
    const bloco = await client.getBloco(blocoId);
    if (!bloco) {
      return { status: 404, error: 'Bloco not found' };
    }
    return { status: 200, data: bloco };
  }

  private async handleAddDocumentoToBloco(
    client: SEIClient,
    blocoId: string,
    body: AddDocumentoBlocoRequest
  ): Promise<APIResponse> {
    if (!body.documentoId) {
      return { status: 400, error: 'Missing documentoId' };
    }

    const success = await client.addDocumentoToBloco(blocoId, body.documentoId);
    return { status: 200, data: { success } };
  }

  private async handleRemoveDocumentoFromBloco(
    client: SEIClient,
    blocoId: string,
    documentoId: string
  ): Promise<APIResponse> {
    const success = await client.removeDocumentoFromBloco(blocoId, documentoId);
    return { status: 200, data: { success } };
  }

  private async handleDisponibilizarBloco(
    client: SEIClient,
    blocoId: string,
    body: DisponibilizarBlocoRequest
  ): Promise<APIResponse> {
    const success = await client.disponibilizarBloco(blocoId, body.unidades);
    return { status: 200, data: { success } };
  }

  // ============================================
  // Handlers - Novos Endpoints (Paridade com MCP)
  // ============================================

  private async handleListUnits(client: SEIClient, query: Record<string, string>): Promise<APIResponse> {
    const unidades = await client.listUnits();
    const filtered = query.filter
      ? unidades.filter(u => {
          const filterLower = query.filter.toLowerCase();
          return u.Sigla.toLowerCase().includes(filterLower) ||
                 u.Descricao.toLowerCase().includes(filterLower);
        })
      : unidades;
    return { status: 200, data: { unidades: filtered } };
  }

  private async handleListUsuarios(client: SEIClient, query: Record<string, string>): Promise<APIResponse> {
    // Implementação depende do client - por enquanto retorna lista do service
    const browserClient = client.getBrowserClient();
    if (browserClient) {
      try {
        const usuarios = await browserClient.listUsuarios(query.filter);
        return { status: 200, data: { usuarios } };
      } catch {
        return { status: 200, data: { usuarios: [], message: 'Funcionalidade não disponível nesta versão do SEI' } };
      }
    }
    return { status: 200, data: { usuarios: [] } };
  }

  private async handleListHipotesesLegais(client: SEIClient): Promise<APIResponse> {
    const browserClient = client.getBrowserClient();
    if (browserClient) {
      try {
        const hipoteses = await browserClient.listHipotesesLegais();
        return { status: 200, data: { hipoteses } };
      } catch {
        return { status: 200, data: { hipoteses: [], message: 'Funcionalidade não disponível' } };
      }
    }
    return { status: 200, data: { hipoteses: [] } };
  }

  private async handleListMarcadores(client: SEIClient): Promise<APIResponse> {
    const browserClient = client.getBrowserClient();
    if (browserClient) {
      try {
        const marcadores = await browserClient.listMarcadores();
        return { status: 200, data: { marcadores } };
      } catch {
        return { status: 200, data: { marcadores: [], message: 'Funcionalidade não disponível' } };
      }
    }
    return { status: 200, data: { marcadores: [] } };
  }

  private async handleListMeusProcessos(client: SEIClient, query: Record<string, string>): Promise<APIResponse> {
    const browserClient = client.getBrowserClient();
    if (browserClient) {
      try {
        const processos = await browserClient.listMeusProcessos(
          query.status as 'abertos' | 'fechados' || 'abertos',
          parseInt(query.limit) || 50
        );
        return { status: 200, data: { processos } };
      } catch {
        return { status: 200, data: { processos: [], message: 'Funcionalidade não disponível' } };
      }
    }
    return { status: 200, data: { processos: [] } };
  }

  private async handleScreenshot(client: SEIClient, query: Record<string, string>): Promise<APIResponse> {
    const browserClient = client.getBrowserClient();
    if (!browserClient) {
      return { status: 400, error: 'Browser client não disponível' };
    }

    const screenshot = await browserClient.screenshot(query.fullPage === 'true');
    return { status: 200, data: { screenshot, format: 'base64' } };
  }

  private async handleSnapshot(client: SEIClient, query: Record<string, string>): Promise<APIResponse> {
    const browserClient = client.getBrowserClient();
    if (!browserClient) {
      return { status: 400, error: 'Browser client não disponível' };
    }

    const snapshot = await browserClient.snapshot(query.includeHidden === 'true');
    return { status: 200, data: { snapshot } };
  }

  private async handleGetCurrentPage(client: SEIClient): Promise<APIResponse> {
    const browserClient = client.getBrowserClient();
    if (!browserClient) {
      return { status: 400, error: 'Browser client não disponível' };
    }

    const page = browserClient.getPage();
    return { status: 200, data: { url: page?.url(), title: await page?.title() } };
  }

  private async handleNavigate(client: SEIClient, body: NavigateRequest): Promise<APIResponse> {
    const browserClient = client.getBrowserClient();
    if (!browserClient) {
      return { status: 400, error: 'Browser client não disponível' };
    }

    await browserClient.navigate(body.target);
    return { status: 200, data: { success: true } };
  }

  private async handleClick(client: SEIClient, body: ClickRequest): Promise<APIResponse> {
    const browserClient = client.getBrowserClient();
    if (!browserClient) {
      return { status: 400, error: 'Browser client não disponível' };
    }

    const page = browserClient.getPage();
    if (page) {
      await page.click(body.selector);
    }
    return { status: 200, data: { success: true } };
  }

  private async handleType(client: SEIClient, body: TypeRequest): Promise<APIResponse> {
    const browserClient = client.getBrowserClient();
    if (!browserClient) {
      return { status: 400, error: 'Browser client não disponível' };
    }

    const page = browserClient.getPage();
    if (page) {
      if (body.clear) {
        await page.fill(body.selector, '');
      }
      await page.fill(body.selector, body.text);
    }
    return { status: 200, data: { success: true } };
  }

  private async handleSelect(client: SEIClient, body: SelectRequest): Promise<APIResponse> {
    const browserClient = client.getBrowserClient();
    if (!browserClient) {
      return { status: 400, error: 'Browser client não disponível' };
    }

    const page = browserClient.getPage();
    if (page) {
      await page.selectOption(body.selector, body.value);
    }
    return { status: 200, data: { success: true } };
  }

  private async handleWait(client: SEIClient, body: WaitRequest): Promise<APIResponse> {
    const browserClient = client.getBrowserClient();
    if (!browserClient) {
      return { status: 400, error: 'Browser client não disponível' };
    }

    const page = browserClient.getPage();
    if (page) {
      await page.waitForSelector(body.selector, { timeout: body.timeout || 10000 });
    }
    return { status: 200, data: { success: true } };
  }

  private async handleSignMultiple(client: SEIClient, body: SignMultipleRequest): Promise<APIResponse> {
    if (!body.documentoIds?.length || !body.senha) {
      return { status: 400, error: 'Missing documentoIds or senha' };
    }

    const results: { documentoId: string; success: boolean; error?: string }[] = [];
    const browserClient = client.getBrowserClient();

    for (const docId of body.documentoIds) {
      try {
        if (browserClient) {
          await browserClient.openDocument(docId);
        }
        const success = await client.signDocument(body.senha, body.cargo);
        results.push({ documentoId: docId, success });
      } catch (error) {
        results.push({ documentoId: docId, success: false, error: String(error) });
      }
    }

    return { status: 200, data: { results } };
  }

  private async handleSearchProcess(client: SEIClient, query: Record<string, string>): Promise<APIResponse> {
    const browserClient = client.getBrowserClient();
    if (!browserClient) {
      return { status: 400, error: 'Browser client não disponível' };
    }

    try {
      const processos = await browserClient.searchProcessos(
        query.query,
        query.type as 'numero' | 'texto' | 'interessado' || 'numero',
        parseInt(query.limit) || 20
      );
      return { status: 200, data: { processos } };
    } catch (error) {
      return { status: 500, error: String(error) };
    }
  }

  private async handleOpenProcess(client: SEIClient, processNumber: string): Promise<APIResponse> {
    const success = await client.openProcess(processNumber);
    return { status: 200, data: { success } };
  }

  private async handleGetProcessStatus(
    client: SEIClient,
    processNumber: string,
    query: Record<string, string>
  ): Promise<APIResponse> {
    const process = await client.getProcess(processNumber);
    const includeHistory = query.includeHistory !== 'false';
    const includeDocuments = query.includeDocuments !== 'false';

    let andamentos: unknown[] = [];
    let documents: unknown[] = [];

    if (includeHistory) {
      andamentos = await client.listAndamentos(processNumber);
    }
    if (includeDocuments) {
      documents = await client.listDocuments();
    }

    return { status: 200, data: { ...process, andamentos, documents } };
  }

  private async handleDownloadProcess(
    client: SEIClient,
    processNumber: string,
    query: Record<string, string>
  ): Promise<APIResponse> {
    const browserClient = client.getBrowserClient();
    if (!browserClient) {
      return { status: 400, error: 'Browser client não disponível' };
    }

    try {
      const result = await browserClient.downloadProcess(
        processNumber,
        query.includeAttachments !== 'false',
        query.outputPath
      );
      return { status: 200, data: result };
    } catch (error) {
      return { status: 500, error: String(error) };
    }
  }

  private async handleListAnnotations(client: SEIClient, processNumber: string): Promise<APIResponse> {
    const browserClient = client.getBrowserClient();
    if (!browserClient) {
      return { status: 200, data: { annotations: [] } };
    }

    try {
      await client.openProcess(processNumber);
      const annotations = await browserClient.listAnnotations();
      return { status: 200, data: { annotations } };
    } catch {
      return { status: 200, data: { annotations: [] } };
    }
  }

  private async handleAddAnnotation(
    client: SEIClient,
    processNumber: string,
    body: AddAnnotationRequest
  ): Promise<APIResponse> {
    if (!body.texto) {
      return { status: 400, error: 'Missing texto' };
    }

    const browserClient = client.getBrowserClient();
    if (!browserClient) {
      return { status: 400, error: 'Browser client não disponível' };
    }

    try {
      await client.openProcess(processNumber);
      const success = await browserClient.addAnnotation(body.texto, body.prioridade);
      return { status: 200, data: { success } };
    } catch (error) {
      return { status: 500, error: String(error) };
    }
  }

  private async handleAddMarker(
    client: SEIClient,
    processNumber: string,
    body: AddMarkerRequest
  ): Promise<APIResponse> {
    if (!body.marcador) {
      return { status: 400, error: 'Missing marcador' };
    }

    const browserClient = client.getBrowserClient();
    if (!browserClient) {
      return { status: 400, error: 'Browser client não disponível' };
    }

    try {
      await client.openProcess(processNumber);
      const success = await browserClient.addMarker(body.marcador, body.texto);
      return { status: 200, data: { success } };
    } catch (error) {
      return { status: 500, error: String(error) };
    }
  }

  private async handleRemoveMarker(
    client: SEIClient,
    processNumber: string,
    marcador: string
  ): Promise<APIResponse> {
    const browserClient = client.getBrowserClient();
    if (!browserClient) {
      return { status: 400, error: 'Browser client não disponível' };
    }

    try {
      await client.openProcess(processNumber);
      const success = await browserClient.removeMarker(marcador);
      return { status: 200, data: { success } };
    } catch (error) {
      return { status: 500, error: String(error) };
    }
  }

  private async handleSetDeadline(
    client: SEIClient,
    processNumber: string,
    body: SetDeadlineRequest
  ): Promise<APIResponse> {
    if (!body.dias) {
      return { status: 400, error: 'Missing dias' };
    }

    const browserClient = client.getBrowserClient();
    if (!browserClient) {
      return { status: 400, error: 'Browser client não disponível' };
    }

    try {
      await client.openProcess(processNumber);
      const success = await browserClient.setDeadline(body.dias, body.tipo || 'util');
      return { status: 200, data: { success } };
    } catch (error) {
      return { status: 500, error: String(error) };
    }
  }

  private async handleGrantAccess(
    client: SEIClient,
    processNumber: string,
    body: GrantAccessRequest
  ): Promise<APIResponse> {
    if (!body.usuario) {
      return { status: 400, error: 'Missing usuario' };
    }

    const browserClient = client.getBrowserClient();
    if (!browserClient) {
      return { status: 400, error: 'Browser client não disponível' };
    }

    try {
      await client.openProcess(processNumber);
      const success = await browserClient.grantAccess(body.usuario, body.tipo || 'consulta');
      return { status: 200, data: { success } };
    } catch (error) {
      return { status: 500, error: String(error) };
    }
  }

  private async handleRevokeAccess(
    client: SEIClient,
    processNumber: string,
    usuario: string
  ): Promise<APIResponse> {
    const browserClient = client.getBrowserClient();
    if (!browserClient) {
      return { status: 400, error: 'Browser client não disponível' };
    }

    try {
      await client.openProcess(processNumber);
      const success = await browserClient.revokeAccess(usuario);
      return { status: 200, data: { success } };
    } catch (error) {
      return { status: 500, error: String(error) };
    }
  }

  private async handleGetDocument(
    client: SEIClient,
    documentId: string,
    query: Record<string, string>
  ): Promise<APIResponse> {
    const document = await client.getDocumentDetails(documentId);
    if (query.includeContent === 'true') {
      const browserClient = client.getBrowserClient();
      if (browserClient) {
        try {
          const content = await browserClient.getDocumentContent(documentId);
          return { status: 200, data: { ...document, content } };
        } catch {
          // Ignora erro ao obter conteúdo
        }
      }
    }
    return { status: 200, data: document };
  }

  private async handleDownloadDocument(
    client: SEIClient,
    documentId: string,
    query: Record<string, string>
  ): Promise<APIResponse> {
    const browserClient = client.getBrowserClient();
    if (!browserClient) {
      return { status: 400, error: 'Browser client não disponível' };
    }

    try {
      const result = await browserClient.downloadDocument(documentId, query.outputPath);
      return { status: 200, data: result };
    } catch (error) {
      return { status: 500, error: String(error) };
    }
  }

  private async handleRegisterKnowledge(client: SEIClient, documentId: string): Promise<APIResponse> {
    const browserClient = client.getBrowserClient();
    if (!browserClient) {
      return { status: 400, error: 'Browser client não disponível' };
    }

    try {
      await browserClient.openDocument(documentId);
      const success = await browserClient.registerKnowledge();
      return { status: 200, data: { success } };
    } catch (error) {
      return { status: 500, error: String(error) };
    }
  }

  private async handleSchedulePublication(
    client: SEIClient,
    documentId: string,
    body: SchedulePublicationRequest
  ): Promise<APIResponse> {
    if (!body.veiculo) {
      return { status: 400, error: 'Missing veiculo' };
    }

    const browserClient = client.getBrowserClient();
    if (!browserClient) {
      return { status: 400, error: 'Browser client não disponível' };
    }

    try {
      await browserClient.openDocument(documentId);
      const success = await browserClient.schedulePublication(
        body.veiculo,
        body.dataPublicacao,
        body.resumo
      );
      return { status: 200, data: { success } };
    } catch (error) {
      return { status: 500, error: String(error) };
    }
  }

  private async handleUploadDocumentBase64(
    client: SEIClient,
    processNumber: string,
    body: UploadDocumentBase64Request
  ): Promise<APIResponse> {
    if (!body.conteudoBase64 || !body.nomeArquivo) {
      return { status: 400, error: 'Missing conteudoBase64 or nomeArquivo' };
    }

    const documentId = await client.uploadDocument(
      processNumber,
      body.nomeArquivo,
      body.conteudoBase64,
      {
        idSerie: body.tipoDocumento,
        descricao: body.descricao,
        nivelAcesso: body.nivelAcesso === 'publico' ? 0 : body.nivelAcesso === 'restrito' ? 1 : 2,
      }
    );
    return { status: 201, data: { documentId } };
  }

  private async handleRelateProcess(
    client: SEIClient,
    processNumber: string,
    body: RelateProcessRequest
  ): Promise<APIResponse> {
    if (!body.processoRelacionado) {
      return { status: 400, error: 'Missing processoRelacionado' };
    }

    const success = await client.relacionarProcesso(processNumber, body.processoRelacionado);
    return { status: 200, data: { success } };
  }

  private async handleReleaseBloco(client: SEIClient, blocoId: string): Promise<APIResponse> {
    const success = await client.disponibilizarBloco(blocoId);
    return { status: 200, data: { success } };
  }

  private async handleSignBloco(
    client: SEIClient,
    blocoId: string,
    body: SignBlocoRequest
  ): Promise<APIResponse> {
    if (!body.senha) {
      return { status: 400, error: 'Missing senha' };
    }

    const browserClient = client.getBrowserClient();
    if (!browserClient) {
      return { status: 400, error: 'Browser client não disponível' };
    }

    try {
      const success = await browserClient.signBloco(blocoId, body.senha);
      return { status: 200, data: { success } };
    } catch (error) {
      return { status: 500, error: String(error) };
    }
  }

  // ============================================
  // Daemon Handlers
  // ============================================

  private handleDaemonStatus(): APIResponse {
    if (!this.daemon) {
      return {
        status: 200,
        data: {
          running: false,
          config: this.daemonConfig,
        },
      };
    }

    return {
      status: 200,
      data: {
        running: this.daemon.running,
        config: this.daemonConfig,
      },
    };
  }

  private async handleDaemonStart(body: DaemonStartRequest): Promise<APIResponse> {
    if (this.daemon?.running) {
      return { status: 400, error: 'Daemon já está rodando. Use /daemon/stop primeiro.' };
    }

    // Validação
    if (!body.browser?.cdpEndpoint && !body.credentials?.usuario) {
      return {
        status: 400,
        error: 'Forneça credentials (usuario/senha) ou browser.cdpEndpoint para modo CDP',
      };
    }

    try {
      const daemonConfig: DaemonConfig = {
        baseUrl: this.config.baseUrl,
        credentials: body.credentials,
        browser: {
          headless: body.browser?.headless ?? true,
          cdpEndpoint: body.browser?.cdpEndpoint,
          timeout: 60000,
        },
        watch: {
          types: body.watch?.types ?? ['processos_recebidos', 'blocos_assinatura', 'prazos'],
          interval: body.watch?.interval ?? 60000,
        },
        notifications: body.notifications ? {
          email: body.notifications.email,
          webhook: body.notifications.webhook,
          recipients: body.notifications.recipients,
        } : undefined,
      };

      this.daemonConfig = body;
      this.daemon = new SEIDaemon(daemonConfig);

      // Event handlers
      this.daemon.on('event', (event) => {
        console.log(`[Daemon] Evento: ${event.type} (${event.items.length} itens)`);
      });

      this.daemon.on('error', (error) => {
        console.error(`[Daemon] Erro: ${error.message}`);
      });

      await this.daemon.start();

      return {
        status: 200,
        data: {
          message: 'Daemon iniciado',
          running: true,
          config: {
            mode: body.browser?.cdpEndpoint ? 'CDP' : 'headless',
            watchTypes: daemonConfig.watch?.types,
            interval: daemonConfig.watch?.interval,
          },
        },
      };
    } catch (error) {
      return { status: 500, error: String(error) };
    }
  }

  private async handleDaemonStop(): Promise<APIResponse> {
    if (!this.daemon) {
      return { status: 400, error: 'Daemon não está rodando' };
    }

    try {
      await this.daemon.stop();
      this.daemon = null;

      return {
        status: 200,
        data: { message: 'Daemon parado', running: false },
      };
    } catch (error) {
      return { status: 500, error: String(error) };
    }
  }

  private handleDaemonGetConfig(): APIResponse {
    return {
      status: 200,
      data: {
        config: this.daemonConfig,
        defaults: {
          watchTypes: ['processos_recebidos', 'blocos_assinatura', 'prazos'],
          interval: 60000,
          headless: true,
        },
      },
    };
  }

  private handleDaemonUpdateConfig(body: Partial<DaemonStartRequest>): APIResponse {
    if (this.daemon?.running) {
      return {
        status: 400,
        error: 'Pare o daemon primeiro com /daemon/stop antes de atualizar a configuração',
      };
    }

    this.daemonConfig = { ...this.daemonConfig, ...body };

    return {
      status: 200,
      data: {
        message: 'Configuração atualizada',
        config: this.daemonConfig,
      },
    };
  }
}

// ============================================
// Request Types
// ============================================

interface CreateSessionRequest {
  seiUrl: string;
  usuario: string;
  senha: string;
  orgao?: string;
  soap?: {
    siglaSistema: string;
    identificacaoServico: string;
  };
}

interface AddUserRequest {
  id: string;
  nome: string;
  email: string;
  seiUrl: string;
  orgao?: string;
  credentials: SEICredentials;
  notifications?: Partial<SEIUserConfig['notifications']>;
}

interface CreateProcessRequest extends CreateProcessOptions {}

interface ForwardProcessRequest extends ForwardOptions {}

interface AnexarProcessRequest {
  processoAnexado: string;
}

interface RelacionarProcessRequest {
  processoRelacionado: string;
}

interface AtribuirProcessRequest {
  usuario: string;
  reabrir?: boolean;
}

interface CreateDocumentRequest extends CreateDocumentOptions {}

interface UploadDocumentRequest {
  nomeArquivo: string;
  conteudoBase64: string;
  idSerie?: string;
  descricao?: string;
  observacao?: string;
  nivelAcesso?: 0 | 1 | 2;
  hipoteseLegal?: string;
}

interface SignDocumentRequest {
  senha: string;
  cargo?: string;
}

interface CancelDocumentRequest {
  motivo: string;
}

interface CreateBlocoRequest {
  descricao: string;
  tipo?: 'assinatura' | 'reuniao' | 'interno';
  unidades?: string[];
  documentos?: string[];
}

interface AddDocumentoBlocoRequest {
  documentoId: string;
}

interface DisponibilizarBlocoRequest {
  unidades?: string[];
}

// Novos Request Types (Paridade com MCP)

interface NavigateRequest {
  target: string;
}

interface ClickRequest {
  selector: string;
}

interface TypeRequest {
  selector: string;
  text: string;
  clear?: boolean;
}

interface SelectRequest {
  selector: string;
  value: string;
}

interface WaitRequest {
  selector: string;
  timeout?: number;
}

interface SignMultipleRequest {
  documentoIds: string[];
  senha: string;
  cargo?: string;
}

interface AddAnnotationRequest {
  texto: string;
  prioridade?: 'normal' | 'alta';
}

interface AddMarkerRequest {
  marcador: string;
  texto?: string;
}

interface SetDeadlineRequest {
  dias: number;
  tipo?: 'util' | 'corrido';
}

interface GrantAccessRequest {
  usuario: string;
  tipo?: 'consulta' | 'acompanhamento';
}

interface SchedulePublicationRequest {
  veiculo: string;
  dataPublicacao?: string;
  resumo?: string;
}

interface UploadDocumentBase64Request {
  conteudoBase64: string;
  nomeArquivo: string;
  mimeType?: string;
  tipoDocumento?: string;
  descricao?: string;
  nivelAcesso?: 'publico' | 'restrito' | 'sigiloso';
}

interface RelateProcessRequest {
  processoRelacionado: string;
  tipoRelacao?: string;
}

interface SignBlocoRequest {
  senha: string;
}

// ============================================
// Daemon Types
// ============================================

interface DaemonStartRequest {
  /** Credenciais (opcionais se usar CDP com sessão já logada) */
  credentials?: {
    usuario: string;
    senha: string;
    orgao?: string;
  };

  /** Modo de browser */
  browser?: {
    /** Executar headless (oculto) */
    headless?: boolean;
    /** Endpoint CDP para conectar ao Chrome já aberto */
    cdpEndpoint?: string;
  };

  /** Configurações de monitoramento */
  watch?: {
    /** Tipos para monitorar */
    types?: WatchType[];
    /** Intervalo em ms (padrão: 60000) */
    interval?: number;
  };

  /** Notificações */
  notifications?: {
    /** Configuração de email */
    email?: EmailConfig;
    /** URL do webhook */
    webhook?: string;
    /** Destinatários */
    recipients?: Array<{
      userId: string;
      email: string;
      nome: string;
    }>;
  };
}

export default SEIServiceAPI;
