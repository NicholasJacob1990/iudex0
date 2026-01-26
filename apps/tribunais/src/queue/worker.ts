/**
 * Worker de processamento de fila
 *
 * Processa jobs de:
 * - Consultas de processo
 * - Peticionamento
 * - Downloads
 */

import { Worker, Queue, Job } from 'bullmq';
import { Redis } from 'ioredis';
import { TribunalService } from '../services/tribunal.js';
import { CredentialService } from '../services/credentials.js';
import { initCaptchaSolver, type CaptchaProvider } from '../services/captcha-solver.js';
import { logger } from '../utils/logger.js';
import type {
  TribunalJob,
  OperationResult,
  CaptchaInfo,
  CaptchaSolution,
} from '../types/index.js';

// Configuração
const REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';
const ENCRYPTION_KEY = process.env.ENCRYPTION_KEY || 'dev-key-change-in-production';
const QUEUE_NAME = 'tribunais';
const CONCURRENCY = parseInt(process.env.WORKER_CONCURRENCY || '3', 10);

// Configuração do CAPTCHA Solver
const CAPTCHA_PROVIDER = (process.env.CAPTCHA_PROVIDER || 'manual') as CaptchaProvider;
const CAPTCHA_API_KEY = process.env.CAPTCHA_API_KEY || '';
const CAPTCHA_SERVICE_TIMEOUT = parseInt(process.env.CAPTCHA_SERVICE_TIMEOUT || '120000', 10);
const CAPTCHA_FALLBACK_MANUAL = process.env.CAPTCHA_FALLBACK_MANUAL !== 'false';

// Serviços
const tribunalService = new TribunalService();
const credentialService = new CredentialService(ENCRYPTION_KEY);

// Inicializar CAPTCHA Solver
const captchaSolver = initCaptchaSolver({
  provider: CAPTCHA_PROVIDER,
  apiKey: CAPTCHA_API_KEY,
  serviceTimeout: CAPTCHA_SERVICE_TIMEOUT,
  manualTimeout: 120000,
  fallbackToManual: CAPTCHA_FALLBACK_MANUAL,
  redisUrl: REDIS_URL,
});

logger.info(`CAPTCHA Solver inicializado`, {
  provider: CAPTCHA_PROVIDER,
  fallbackToManual: CAPTCHA_FALLBACK_MANUAL,
});

// Conexão Redis
const connection = new Redis(REDIS_URL, {
  maxRetriesPerRequest: null,
});

// Nota: O CaptchaSolverService agora gerencia o pub/sub de CAPTCHA internamente

// Fila para adicionar jobs
export const tribunaisQueue = new Queue<TribunalJob>(QUEUE_NAME, {
  connection,
  defaultJobOptions: {
    attempts: 3,
    backoff: {
      type: 'exponential',
      delay: 5000,
    },
    removeOnComplete: {
      age: 24 * 3600, // 24 horas
      count: 1000,
    },
    removeOnFail: {
      age: 7 * 24 * 3600, // 7 dias
    },
  },
});

/**
 * Processa job de tribunal
 */
async function processJob(job: Job<TribunalJob>): Promise<OperationResult> {
  const { credentialId, operation, params } = job.data;

  logger.info(`Processando job ${job.id}: ${operation}`, {
    credentialId,
    params: Object.keys(params),
  });

  // Atualizar progresso
  await job.updateProgress(10);

  // Descriptografar credencial
  const credential = await credentialService.decryptCredential(credentialId);
  if (!credential) {
    throw new Error(`Credencial não encontrada: ${credentialId}`);
  }

  await job.updateProgress(20);

  // Verificar se precisa de interação do usuário
  if (tribunalService.needsUserInteraction(credential.authType)) {
    // Para A3, precisamos notificar o usuário e aguardar
    // Isso será tratado via WebSocket/extensão
    logger.info(`Job ${job.id} requer interação do usuário (${credential.authType})`);

    // Emitir evento para WebSocket
    await notifyUserInteractionRequired(job.data);

    // Aguardar confirmação (com timeout)
    // TODO: Implementar mecanismo de aguardar aprovação
    throw new Error('Interação do usuário necessária - aguardando aprovação via extensão');
  }

  await job.updateProgress(30);

  // Criar handler de CAPTCHA para esta job
  const onCaptchaRequired = async (captcha: CaptchaInfo): Promise<CaptchaSolution> => {
    return captchaHandler(job.data, captcha);
  };

  // Executar operação com suporte a CAPTCHA HIL
  const result = await tribunalService.executeOperation(
    credential,
    operation,
    params,
    { onCaptchaRequired }
  );

  await job.updateProgress(100);

  // Notificar webhook se configurado
  if (job.data.webhookUrl) {
    await notifyWebhook(job.data.webhookUrl, job.data, result);
  }

  return result;
}

/**
 * Notifica que interação do usuário é necessária
 */
async function notifyUserInteractionRequired(job: TribunalJob): Promise<void> {
  logger.info(`Notificação de interação necessária para job ${job.id}`);

  // Publicar no Redis pub/sub para WebSocket server
  const pubClient = new Redis(REDIS_URL);
  await pubClient.publish('tribunais:interaction_required', JSON.stringify({
    jobId: job.id,
    userId: job.userId,
    operation: job.operation,
    tribunal: job.tribunal,
    message: 'Aprovação necessária no seu certificado digital',
  }));
  await pubClient.quit();
}

/**
 * Handler de CAPTCHA para o TribunalService
 *
 * Esta função é passada para o tribunais-playwright
 * quando ele detecta um CAPTCHA durante a operação.
 *
 * Usa estratégia híbrida:
 * 1. Tenta resolver via serviço (2Captcha, Anti-Captcha, CapMonster)
 * 2. Se falhar, fallback para resolução manual (HIL)
 */
async function captchaHandler(
  job: TribunalJob,
  captcha: CaptchaInfo
): Promise<CaptchaSolution> {
  logger.info(`CAPTCHA detectado durante operação ${job.operation}`, {
    jobId: job.id,
    type: captcha.type,
    provider: CAPTCHA_PROVIDER,
  });

  try {
    // Usar o serviço híbrido
    const solution = await captchaSolver.solve(
      job.id,
      job.userId,
      captcha,
      job.tribunalUrl,
      job.tribunal
    );

    logger.info(`CAPTCHA resolvido para job ${job.id}`, {
      type: captcha.type,
      hasToken: !!solution.token,
      hasText: !!solution.text,
    });

    return solution;
  } catch (error) {
    logger.error(`Falha ao resolver CAPTCHA para job ${job.id}:`, error);
    throw error;
  }
}

/**
 * Notifica webhook com resultado
 */
async function notifyWebhook(
  webhookUrl: string,
  job: TribunalJob,
  result: OperationResult
): Promise<void> {
  try {
    await fetch(webhookUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        jobId: job.id,
        userId: job.userId,
        operation: job.operation,
        success: result.success,
        data: result.data,
        error: result.error,
        completedAt: result.executedAt,
      }),
    });
    logger.info(`Webhook notificado: ${webhookUrl}`);
  } catch (error) {
    logger.error(`Erro ao notificar webhook:`, error);
  }
}

// Criar worker
const worker = new Worker<TribunalJob, OperationResult>(
  QUEUE_NAME,
  processJob,
  {
    connection,
    concurrency: CONCURRENCY,
  }
);

// Event handlers
worker.on('completed', (job, result) => {
  logger.info(`Job ${job.id} completado:`, {
    operation: job.data.operation,
    success: result.success,
  });
});

worker.on('failed', (job, error) => {
  logger.error(`Job ${job?.id} falhou:`, error);
});

worker.on('error', (error) => {
  logger.error('Erro no worker:', error);
});

logger.info(`Worker iniciado (concurrency: ${CONCURRENCY})`);

// Graceful shutdown
async function shutdown(): Promise<void> {
  logger.info('Encerrando worker...');

  // Fechar CAPTCHA solver (cancela CAPTCHAs pendentes)
  await captchaSolver.close();

  await worker.close();
  await connection.quit();
  process.exit(0);
}

process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
