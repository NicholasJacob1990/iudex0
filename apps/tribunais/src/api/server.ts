/**
 * Servidor API HTTP
 */

import express, { Request, Response, NextFunction } from 'express';
import cors from 'cors';
import helmet from 'helmet';
import { initRoutes } from './routes.js';
import { logger } from '../utils/logger.js';

export function createApiServer(config: {
  port: number;
  encryptionKey: string;
  corsOrigins?: string[];
}) {
  const app = express();

  // Middlewares de segurança
  app.use(helmet());
  app.use(cors({
    origin: config.corsOrigins || '*',
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'],
    allowedHeaders: ['Content-Type', 'Authorization'],
  }));

  // Parse JSON
  app.use(express.json({ limit: '50mb' })); // Para uploads de certificado

  // Logging
  app.use((req: Request, res: Response, next: NextFunction) => {
    const start = Date.now();
    res.on('finish', () => {
      const duration = Date.now() - start;
      logger.info(`${req.method} ${req.path} ${res.statusCode} ${duration}ms`);
    });
    next();
  });

  // Health check
  app.get('/health', (req: Request, res: Response) => {
    res.json({ status: 'ok', timestamp: new Date().toISOString() });
  });

  // Rotas principais
  app.use('/api', initRoutes(config.encryptionKey));

  // Error handler
  app.use((err: Error, req: Request, res: Response, next: NextFunction) => {
    logger.error('Erro na API:', err);

    // Erros de validação Zod
    if (err.name === 'ZodError') {
      res.status(400).json({
        error: 'Dados inválidos',
        details: (err as any).errors,
      });
      return;
    }

    res.status(500).json({
      error: 'Erro interno do servidor',
      message: process.env.NODE_ENV === 'development' ? err.message : undefined,
    });
  });

  // 404
  app.use((req: Request, res: Response) => {
    res.status(404).json({ error: 'Rota não encontrada' });
  });

  return app;
}

export async function startApiServer(config: {
  port: number;
  encryptionKey: string;
  corsOrigins?: string[];
}) {
  const app = createApiServer(config);

  return new Promise<void>((resolve) => {
    app.listen(config.port, () => {
      logger.info(`API server listening on port ${config.port}`);
      resolve();
    });
  });
}
