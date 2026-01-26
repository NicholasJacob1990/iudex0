/**
 * API REST para tribunais-playwright
 *
 * Endpoints:
 *   POST /sessions          - Criar sessão
 *   GET  /sessions          - Listar sessões ativas
 *   GET  /sessions/:id      - Status da sessão
 *   DELETE /sessions/:id    - Encerrar sessão
 *
 *   POST /sessions/:id/login    - Fazer login
 *   POST /sessions/:id/logout   - Fazer logout
 *
 *   POST /sessions/:id/window/minimize  - Minimizar janela
 *   POST /sessions/:id/window/restore   - Restaurar janela
 *   POST /sessions/:id/window/focus     - Trazer para frente
 *
 *   GET  /sessions/:id/processo/:numero        - Consultar processo
 *   GET  /sessions/:id/processo/:numero/docs   - Listar documentos
 *   GET  /sessions/:id/processo/:numero/movs   - Listar movimentações
 *   POST /sessions/:id/processo/:numero/peticao - Peticionar
 *
 *   POST /sessions/:id/screenshot - Capturar tela
 */

import express, { Request, Response, NextFunction } from 'express';
import type { Express } from 'express';
import type { Server } from 'http';
import { randomUUID } from 'crypto';
import { EprocClient, type EprocClientConfig } from '../eproc/client.js';
import type { AuthConfig, PeticaoOpcoes } from '../types/index.js';

// Helper para extrair param como string
function getParam(req: Request, name: string): string {
  const value = req.params[name];
  return Array.isArray(value) ? value[0] : value;
}

// ============================================
// Types
// ============================================

interface Session {
  id: string;
  client: EprocClient;
  tribunal: string;
  instancia: string;
  status: 'initializing' | 'ready' | 'logged_in' | 'error';
  createdAt: Date;
  lastActivity: Date;
  cdpEndpoint?: string;
  error?: string;
}

interface CreateSessionRequest {
  tribunal: string;
  instancia?: '1g' | '2g';
  auth: AuthConfig;
  headless?: boolean;
  persistent?: boolean;
  keepAlive?: boolean;
}

interface ApiError extends Error {
  statusCode?: number;
}

// ============================================
// Session Store
// ============================================

const sessions = new Map<string, Session>();

// Cleanup de sessões inativas (30 min)
setInterval(() => {
  const now = Date.now();
  for (const [id, session] of sessions) {
    if (now - session.lastActivity.getTime() > 30 * 60 * 1000) {
      console.log(`[API] Limpando sessão inativa: ${id}`);
      session.client.close().catch(() => {});
      sessions.delete(id);
    }
  }
}, 60000);

// ============================================
// Helpers
// ============================================

function getSession(id: string): Session {
  const session = sessions.get(id);
  if (!session) {
    const error: ApiError = new Error(`Sessão não encontrada: ${id}`);
    error.statusCode = 404;
    throw error;
  }
  session.lastActivity = new Date();
  return session;
}

function getBaseUrl(tribunal: string, instancia: string): string {
  const urls: Record<string, Record<string, string>> = {
    tjmg: {
      '1g': 'https://eproc1g.tjmg.jus.br/eproc/',
      '2g': 'https://eproc2g.tjmg.jus.br/eproc/',
    },
    trf4: {
      '1g': 'https://eproc.trf4.jus.br/eproc2trf4',
      '2g': 'https://eproc.trf4.jus.br/eproc2trf4',
    },
    tjrs: {
      '1g': 'https://eproc1g.tjrs.jus.br/eproc/',
      '2g': 'https://eproc2g.tjrs.jus.br/eproc/',
    },
  };

  const tribunalUrls = urls[tribunal.toLowerCase()];
  if (!tribunalUrls) {
    throw new Error(`Tribunal não suportado: ${tribunal}`);
  }

  return tribunalUrls[instancia] ?? tribunalUrls['1g'];
}

// ============================================
// Express App
// ============================================

interface ApiServerResult {
  app: Express;
  server: Server;
}

export function createApiServer(port = 3000): ApiServerResult {
  const app = express();

  app.use(express.json());

  // Logging
  app.use((req, _res, next) => {
    console.log(`[API] ${req.method} ${req.path}`);
    next();
  });

  // ==========================================
  // Sessions
  // ==========================================

  // Criar sessão
  app.post('/sessions', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const body = req.body as CreateSessionRequest;

      if (!body.tribunal) {
        return res.status(400).json({ error: 'tribunal é obrigatório' });
      }
      if (!body.auth) {
        return res.status(400).json({ error: 'auth é obrigatório' });
      }

      const sessionId = randomUUID();
      const instancia = body.instancia ?? '1g';
      const baseUrl = getBaseUrl(body.tribunal, instancia);

      // Aloca porta CDP única
      const cdpPort = 9222 + sessions.size;

      const config: EprocClientConfig = {
        baseUrl,
        auth: body.auth,
        tribunal: body.tribunal,
        instancia,
        playwright: {
          headless: body.headless ?? true,
          persistent: body.persistent ?? false,
          keepAlive: body.keepAlive ?? true,
          cdpPort,
          timeout: 60000,
        },
        onNotification: async (notification) => {
          console.log(`[Session ${sessionId}] ${notification.type}: ${notification.message}`);
        },
      };

      const client = new EprocClient(config);

      const session: Session = {
        id: sessionId,
        client,
        tribunal: body.tribunal,
        instancia,
        status: 'initializing',
        createdAt: new Date(),
        lastActivity: new Date(),
      };

      sessions.set(sessionId, session);

      // Inicializa em background
      client.init()
        .then(() => {
          session.status = 'ready';
          session.cdpEndpoint = client.getCdpEndpoint() ?? undefined;
          console.log(`[Session ${sessionId}] Pronta`);
        })
        .catch((err) => {
          session.status = 'error';
          session.error = err.message;
          console.error(`[Session ${sessionId}] Erro:`, err.message);
        });

      res.status(201).json({
        id: sessionId,
        status: 'initializing',
        tribunal: body.tribunal,
        instancia,
        cdpPort,
        message: 'Sessão criada. Aguarde status "ready" para usar.',
      });
    } catch (err) {
      next(err);
    }
  });

  // Listar sessões
  app.get('/sessions', (_req: Request, res: Response) => {
    const list = Array.from(sessions.values()).map((s) => ({
      id: s.id,
      tribunal: s.tribunal,
      instancia: s.instancia,
      status: s.status,
      createdAt: s.createdAt,
      lastActivity: s.lastActivity,
      cdpEndpoint: s.cdpEndpoint,
    }));
    res.json(list);
  });

  // Status da sessão
  app.get('/sessions/:id', (req: Request, res: Response, next: NextFunction) => {
    try {
      const session = getSession(getParam(req, 'id'));
      res.json({
        id: session.id,
        tribunal: session.tribunal,
        instancia: session.instancia,
        status: session.status,
        createdAt: session.createdAt,
        lastActivity: session.lastActivity,
        cdpEndpoint: session.cdpEndpoint,
        currentUrl: session.client.getCurrentUrl?.() ?? null,
        error: session.error,
      });
    } catch (err) {
      next(err);
    }
  });

  // Encerrar sessão
  app.delete('/sessions/:id', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const session = getSession(getParam(req, 'id'));
      await session.client.close();
      sessions.delete(session.id);
      res.json({ message: 'Sessão encerrada' });
    } catch (err) {
      next(err);
    }
  });

  // ==========================================
  // Login/Logout
  // ==========================================

  // Login
  app.post('/sessions/:id/login', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const session = getSession(getParam(req, 'id'));

      if (session.status === 'initializing') {
        return res.status(400).json({ error: 'Sessão ainda inicializando. Aguarde.' });
      }

      if (session.status === 'logged_in') {
        return res.json({ message: 'Já está logado', status: 'logged_in' });
      }

      const success = await session.client.login();

      if (success) {
        session.status = 'logged_in';
        res.json({
          success: true,
          message: 'Login realizado com sucesso',
          currentUrl: session.client.getCurrentUrl(),
        });
      } else {
        res.status(401).json({
          success: false,
          message: 'Login falhou',
        });
      }
    } catch (err) {
      next(err);
    }
  });

  // Logout
  app.post('/sessions/:id/logout', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const session = getSession(getParam(req, 'id'));
      await session.client.logout();
      session.status = 'ready';
      res.json({ message: 'Logout realizado' });
    } catch (err) {
      next(err);
    }
  });

  // ==========================================
  // Window Control
  // ==========================================

  // Minimizar
  app.post('/sessions/:id/window/minimize', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const session = getSession(getParam(req, 'id'));
      await session.client.minimizeWindow();
      res.json({ message: 'Janela minimizada' });
    } catch (err) {
      next(err);
    }
  });

  // Restaurar
  app.post('/sessions/:id/window/restore', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const session = getSession(getParam(req, 'id'));
      await session.client.restoreWindow();
      res.json({ message: 'Janela restaurada' });
    } catch (err) {
      next(err);
    }
  });

  // Trazer para frente
  app.post('/sessions/:id/window/focus', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const session = getSession(getParam(req, 'id'));
      await session.client.bringToFront();
      res.json({ message: 'Janela em foco' });
    } catch (err) {
      next(err);
    }
  });

  // ==========================================
  // Processos
  // ==========================================

  // Consultar processo
  app.get('/sessions/:id/processo/:numero', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const session = getSession(getParam(req, 'id'));

      if (session.status !== 'logged_in') {
        return res.status(400).json({ error: 'Faça login primeiro' });
      }

      const processo = await session.client.consultarProcesso(getParam(req, 'numero'));

      if (processo) {
        res.json(processo);
      } else {
        res.status(404).json({ error: 'Processo não encontrado' });
      }
    } catch (err) {
      next(err);
    }
  });

  // Listar documentos
  app.get('/sessions/:id/processo/:numero/docs', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const session = getSession(getParam(req, 'id'));

      if (session.status !== 'logged_in') {
        return res.status(400).json({ error: 'Faça login primeiro' });
      }

      const docs = await session.client.listarDocumentos(getParam(req, 'numero'));
      res.json(docs);
    } catch (err) {
      next(err);
    }
  });

  // Listar movimentações
  app.get('/sessions/:id/processo/:numero/movs', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const session = getSession(getParam(req, 'id'));

      if (session.status !== 'logged_in') {
        return res.status(400).json({ error: 'Faça login primeiro' });
      }

      const movs = await session.client.listarMovimentacoes(getParam(req, 'numero'));
      res.json(movs);
    } catch (err) {
      next(err);
    }
  });

  // Peticionar
  app.post('/sessions/:id/processo/:numero/peticao', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const session = getSession(getParam(req, 'id'));

      if (session.status !== 'logged_in') {
        return res.status(400).json({ error: 'Faça login primeiro' });
      }

      const body = req.body as Omit<PeticaoOpcoes, 'numeroProcesso'>;

      if (!body.tipo) {
        return res.status(400).json({ error: 'tipo é obrigatório' });
      }
      if (!body.arquivos || body.arquivos.length === 0) {
        return res.status(400).json({ error: 'arquivos é obrigatório' });
      }

      const resultado = await session.client.peticionar({
        numeroProcesso: getParam(req, 'numero'),
        ...body,
      });

      if (resultado.success) {
        res.json(resultado);
      } else {
        res.status(400).json(resultado);
      }
    } catch (err) {
      next(err);
    }
  });

  // ==========================================
  // Screenshot
  // ==========================================

  app.post('/sessions/:id/screenshot', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const session = getSession(getParam(req, 'id'));
      const buffer = await session.client.screenshot();

      res.set('Content-Type', 'image/png');
      res.send(buffer);
    } catch (err) {
      next(err);
    }
  });

  // ==========================================
  // Error Handler
  // ==========================================

  app.use((err: ApiError, _req: Request, res: Response, _next: NextFunction) => {
    console.error('[API] Erro:', err.message);
    const statusCode = err.statusCode ?? 500;
    res.status(statusCode).json({
      error: err.message,
      statusCode,
    });
  });

  // ==========================================
  // Start Server
  // ==========================================

  const server = app.listen(port, () => {
    console.log(`[API] Servidor rodando em http://localhost:${port}`);
    console.log('[API] Endpoints disponíveis:');
    console.log('  POST   /sessions                       - Criar sessão');
    console.log('  GET    /sessions                       - Listar sessões');
    console.log('  GET    /sessions/:id                   - Status da sessão');
    console.log('  DELETE /sessions/:id                   - Encerrar sessão');
    console.log('  POST   /sessions/:id/login             - Login');
    console.log('  POST   /sessions/:id/logout            - Logout');
    console.log('  POST   /sessions/:id/window/minimize   - Minimizar');
    console.log('  POST   /sessions/:id/window/restore    - Restaurar');
    console.log('  POST   /sessions/:id/window/focus      - Foco');
    console.log('  GET    /sessions/:id/processo/:num     - Consultar');
    console.log('  POST   /sessions/:id/processo/:num/peticao - Peticionar');
    console.log('  POST   /sessions/:id/screenshot        - Screenshot');
  });

  return { app, server };
}

// Se executado diretamente
if (import.meta.url === `file://${process.argv[1]}`) {
  const port = parseInt(process.env.PORT ?? '3000', 10);
  createApiServer(port);
}
