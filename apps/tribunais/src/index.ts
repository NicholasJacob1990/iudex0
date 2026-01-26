/**
 * Serviço de Tribunais para Iudex
 *
 * Suporta 3 modos de autenticação:
 * 1. Certificado A1 - Upload do .pfx, 100% automático
 * 2. Certificado A3 Físico - Token USB, requer extensão no browser
 * 3. Certificado A3 Nuvem - Certisign/Serasa, requer extensão
 *
 * Componentes:
 * - API HTTP (Express) - Para integração com backend Python
 * - Worker (BullMQ) - Processamento assíncrono
 * - WebSocket - Comunicação com extensão Chrome
 */

import 'dotenv/config';
import { startApiServer } from './api/server.js';
import { ExtensionWebSocketServer } from './extension/websocket-server.js';
import { logger } from './utils/logger.js';

// Configuração
const config = {
  apiPort: parseInt(process.env.API_PORT || '3100', 10),
  wsPort: parseInt(process.env.WS_PORT || '3101', 10),
  redisUrl: process.env.REDIS_URL || 'redis://localhost:6379',
  encryptionKey: process.env.ENCRYPTION_KEY || 'dev-key-change-in-production-32chars!',
  corsOrigins: process.env.CORS_ORIGINS?.split(',') || ['http://localhost:3000'],
};

async function main() {
  logger.info('Iniciando serviço de tribunais...');

  // Iniciar API HTTP
  await startApiServer({
    port: config.apiPort,
    encryptionKey: config.encryptionKey,
    corsOrigins: config.corsOrigins,
  });

  // Iniciar WebSocket para extensões
  const wsServer = new ExtensionWebSocketServer(config.wsPort, config.redisUrl);
  await wsServer.start();

  logger.info('='.repeat(50));
  logger.info('Serviço de Tribunais iniciado!');
  logger.info(`API HTTP: http://localhost:${config.apiPort}`);
  logger.info(`WebSocket: ws://localhost:${config.wsPort}`);
  logger.info('='.repeat(50));

  // Graceful shutdown
  const shutdown = async () => {
    logger.info('Encerrando serviço...');
    await wsServer.stop();
    process.exit(0);
  };

  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);
}

main().catch((error) => {
  logger.error('Erro ao iniciar serviço:', error);
  process.exit(1);
});

// Exports para uso como biblioteca
export * from './types/index.js';
export { CredentialService } from './services/credentials.js';
export { TribunalService } from './services/tribunal.js';
export { tribunaisQueue } from './queue/worker.js';
export { ExtensionWebSocketServer } from './extension/websocket-server.js';
