/**
 * Rotas da API de tribunais
 */

import { Router, Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import { CredentialService } from '../services/credentials.js';
import { TribunalService } from '../services/tribunal.js';
import { tribunaisQueue } from '../queue/worker.js';
import { logger } from '../utils/logger.js';
import type { TribunalJob, TribunalType, AuthType, OperationType } from '../types/index.js';
import { randomUUID } from 'crypto';

const router = Router();

// Helper para extrair parâmetro (Express v5 retorna string | string[])
function getParam(req: Request, name: string): string {
  const value = req.params[name];
  return Array.isArray(value) ? value[0] : value;
}

// Serviços (injetados via middleware)
let credentialService: CredentialService;
let tribunalService: TribunalService;

export function initRoutes(encryptionKey: string): Router {
  credentialService = new CredentialService(encryptionKey);
  tribunalService = new TribunalService();
  return router;
}

// Schemas de validação
const TribunalSchema = z.enum(['pje', 'eproc', 'esaj']);
const AuthTypeSchema = z.enum(['password', 'certificate_a1', 'certificate_a3_physical', 'certificate_a3_cloud']);
const OperationSchema = z.enum([
  'consultar_processo',
  'listar_documentos',
  'listar_movimentacoes',
  'baixar_documento',
  'baixar_processo',
  'peticionar',
]);

// ===== CREDENCIAIS =====

/**
 * POST /credentials/password
 * Salva credencial de login com senha
 */
router.post('/credentials/password', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const schema = z.object({
      userId: z.string(),
      tribunal: TribunalSchema,
      tribunalUrl: z.string().url(),
      name: z.string(),
      cpf: z.string().regex(/^\d{11}$/),
      password: z.string().min(1),
    });

    const data = schema.parse(req.body);
    const credential = await credentialService.savePasswordCredential(data);

    res.status(201).json(credential);
  } catch (error) {
    next(error);
  }
});

/**
 * POST /credentials/certificate-a1
 * Upload de certificado A1 (.pfx)
 */
router.post('/credentials/certificate-a1', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const schema = z.object({
      userId: z.string(),
      tribunal: TribunalSchema,
      tribunalUrl: z.string().url(),
      name: z.string(),
      pfxBase64: z.string(), // Arquivo em base64
      pfxPassword: z.string(),
      expiresAt: z.string().datetime().optional(),
    });

    const data = schema.parse(req.body);
    const credential = await credentialService.saveCertificateA1({
      ...data,
      expiresAt: data.expiresAt ? new Date(data.expiresAt) : undefined,
    });

    res.status(201).json(credential);
  } catch (error) {
    next(error);
  }
});

/**
 * POST /credentials/certificate-a3-cloud
 * Registra certificado A3 na nuvem
 */
router.post('/credentials/certificate-a3-cloud', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const schema = z.object({
      userId: z.string(),
      tribunal: TribunalSchema,
      tribunalUrl: z.string().url(),
      name: z.string(),
      provider: z.enum(['certisign', 'serasa', 'safeweb']),
    });

    const data = schema.parse(req.body);
    const credential = await credentialService.saveCertificateA3Cloud(data);

    res.status(201).json(credential);
  } catch (error) {
    next(error);
  }
});

/**
 * POST /credentials/certificate-a3-physical
 * Registra certificado A3 físico (token USB)
 */
router.post('/credentials/certificate-a3-physical', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const schema = z.object({
      userId: z.string(),
      tribunal: TribunalSchema,
      tribunalUrl: z.string().url(),
      name: z.string(),
    });

    const data = schema.parse(req.body);
    const credential = await credentialService.saveCertificateA3Physical(data);

    res.status(201).json(credential);
  } catch (error) {
    next(error);
  }
});

/**
 * GET /credentials/:userId
 * Lista credenciais do usuário
 */
router.get('/credentials/:userId', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const userId = getParam(req, 'userId');
    const credentials = await credentialService.listCredentials(userId);
    res.json(credentials);
  } catch (error) {
    next(error);
  }
});

/**
 * DELETE /credentials/:credentialId
 * Remove credencial
 */
router.delete('/credentials/:credentialId', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { userId } = req.body;
    if (!userId) {
      res.status(400).json({ error: 'userId é obrigatório' });
      return;
    }

    const credentialId = getParam(req, 'credentialId');
    const deleted = await credentialService.deleteCredential(credentialId, userId);
    if (!deleted) {
      res.status(404).json({ error: 'Credencial não encontrada' });
      return;
    }

    res.status(204).send();
  } catch (error) {
    next(error);
  }
});

// ===== OPERAÇÕES =====

/**
 * POST /operations/sync
 * Executa operação de forma síncrona (para consultas rápidas)
 */
router.post('/operations/sync', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const schema = z.object({
      credentialId: z.string(),
      operation: OperationSchema,
      params: z.record(z.unknown()),
    });

    const data = schema.parse(req.body);

    // Descriptografar credencial
    const credential = await credentialService.decryptCredential(data.credentialId);
    if (!credential) {
      res.status(404).json({ error: 'Credencial não encontrada' });
      return;
    }

    // Verificar se precisa de interação
    if (tribunalService.needsUserInteraction(credential.authType)) {
      res.status(400).json({
        error: 'Esta credencial requer interação do usuário. Use /operations/async.',
        requiresInteraction: true,
        authType: credential.authType,
      });
      return;
    }

    // Executar operação
    const result = await tribunalService.executeOperation(
      credential,
      data.operation as OperationType,
      data.params
    );

    if (result.success) {
      res.json(result);
    } else {
      res.status(500).json(result);
    }
  } catch (error) {
    next(error);
  }
});

/**
 * POST /operations/async
 * Adiciona operação à fila (para operações longas ou que requerem interação)
 */
router.post('/operations/async', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const schema = z.object({
      userId: z.string(),
      credentialId: z.string(),
      operation: OperationSchema,
      params: z.record(z.unknown()),
      webhookUrl: z.string().url().optional(),
    });

    const data = schema.parse(req.body);

    // Buscar credencial para validar
    const credential = await credentialService.getCredential(data.credentialId);
    if (!credential) {
      res.status(404).json({ error: 'Credencial não encontrada' });
      return;
    }

    // Criar job
    const job: TribunalJob = {
      id: randomUUID(),
      userId: data.userId,
      credentialId: data.credentialId,
      tribunal: credential.tribunal,
      tribunalUrl: credential.tribunalUrl,
      operation: data.operation as OperationType,
      params: data.params,
      status: 'pending',
      webhookUrl: data.webhookUrl,
      createdAt: new Date(),
      updatedAt: new Date(),
    };

    // Adicionar à fila
    const queueJob = await tribunaisQueue.add(job.operation, job, {
      jobId: job.id,
    });

    res.status(202).json({
      jobId: job.id,
      queueId: queueJob.id,
      status: 'pending',
      message: 'Operação adicionada à fila',
    });
  } catch (error) {
    next(error);
  }
});

/**
 * GET /operations/:jobId
 * Consulta status de operação
 */
router.get('/operations/:jobId', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const jobId = getParam(req, 'jobId');
    const job = await tribunaisQueue.getJob(jobId);

    if (!job) {
      res.status(404).json({ error: 'Job não encontrado' });
      return;
    }

    const state = await job.getState();
    const progress = job.progress;

    res.json({
      jobId: job.id,
      status: state,
      progress,
      data: job.data,
      result: job.returnvalue,
      failedReason: job.failedReason,
      createdAt: job.timestamp,
      processedAt: job.processedOn,
      finishedAt: job.finishedOn,
    });
  } catch (error) {
    next(error);
  }
});

// ===== ATALHOS PARA OPERAÇÕES COMUNS =====

/**
 * GET /processo/:credentialId/:numero
 * Consulta processo (atalho)
 */
router.get('/processo/:credentialId/:numero', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const credentialId = getParam(req, 'credentialId');
    const numero = getParam(req, 'numero');

    const credential = await credentialService.decryptCredential(credentialId);
    if (!credential) {
      res.status(404).json({ error: 'Credencial não encontrada' });
      return;
    }

    if (tribunalService.needsUserInteraction(credential.authType)) {
      res.status(400).json({
        error: 'Esta credencial requer interação do usuário',
        requiresInteraction: true,
      });
      return;
    }

    const result = await tribunalService.executeOperation(
      credential,
      'consultar_processo',
      { processo: numero }
    );

    if (result.success) {
      res.json(result.data);
    } else {
      res.status(500).json({ error: result.error });
    }
  } catch (error) {
    next(error);
  }
});

/**
 * GET /processo/:credentialId/:numero/documentos
 * Lista documentos (atalho)
 */
router.get('/processo/:credentialId/:numero/documentos', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const credentialId = getParam(req, 'credentialId');
    const numero = getParam(req, 'numero');

    const credential = await credentialService.decryptCredential(credentialId);
    if (!credential) {
      res.status(404).json({ error: 'Credencial não encontrada' });
      return;
    }

    if (tribunalService.needsUserInteraction(credential.authType)) {
      res.status(400).json({ error: 'Credencial requer interação', requiresInteraction: true });
      return;
    }

    const result = await tribunalService.executeOperation(
      credential,
      'listar_documentos',
      { processo: numero }
    );

    if (result.success) {
      res.json(result.data);
    } else {
      res.status(500).json({ error: result.error });
    }
  } catch (error) {
    next(error);
  }
});

/**
 * GET /processo/:credentialId/:numero/movimentacoes
 * Lista movimentações (atalho)
 */
router.get('/processo/:credentialId/:numero/movimentacoes', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const credentialId = getParam(req, 'credentialId');
    const numero = getParam(req, 'numero');

    const credential = await credentialService.decryptCredential(credentialId);
    if (!credential) {
      res.status(404).json({ error: 'Credencial não encontrada' });
      return;
    }

    if (tribunalService.needsUserInteraction(credential.authType)) {
      res.status(400).json({ error: 'Credencial requer interação', requiresInteraction: true });
      return;
    }

    const result = await tribunalService.executeOperation(
      credential,
      'listar_movimentacoes',
      { processo: numero }
    );

    if (result.success) {
      res.json(result.data);
    } else {
      res.status(500).json({ error: result.error });
    }
  } catch (error) {
    next(error);
  }
});

/**
 * POST /peticionar
 * Protocola petição (sempre assíncrono)
 */
router.post('/peticionar', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const schema = z.object({
      userId: z.string(),
      credentialId: z.string(),
      processo: z.string(),
      tipo: z.enum(['peticao_inicial', 'peticao_intermediaria', 'recurso', 'outros']),
      arquivos: z.array(z.object({
        name: z.string(),
        path: z.string().optional(),
        base64: z.string().optional(),
        mimeType: z.string(),
        tipoDocumento: z.string().optional(),
      })),
      webhookUrl: z.string().url().optional(),
    });

    const data = schema.parse(req.body);

    const credential = await credentialService.getCredential(data.credentialId);
    if (!credential) {
      res.status(404).json({ error: 'Credencial não encontrada' });
      return;
    }

    // Criar job
    const job: TribunalJob = {
      id: randomUUID(),
      userId: data.userId,
      credentialId: data.credentialId,
      tribunal: credential.tribunal,
      tribunalUrl: credential.tribunalUrl,
      operation: 'peticionar',
      params: {
        processo: data.processo,
        tipo: data.tipo,
        arquivos: data.arquivos,
      },
      status: 'pending',
      webhookUrl: data.webhookUrl,
      createdAt: new Date(),
      updatedAt: new Date(),
    };

    const queueJob = await tribunaisQueue.add('peticionar', job, {
      jobId: job.id,
    });

    res.status(202).json({
      jobId: job.id,
      status: 'pending',
      message: 'Petição adicionada à fila de processamento',
      requiresInteraction: credential.authType.includes('a3'),
    });
  } catch (error) {
    next(error);
  }
});

export { router };
