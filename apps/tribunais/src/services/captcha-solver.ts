/**
 * Serviço de resolução de CAPTCHA híbrido
 *
 * Estratégia:
 * 1. Tenta resolver via serviço (2Captcha, Anti-Captcha, CapMonster)
 * 2. Se falhar ou timeout, envia para usuário resolver (HIL)
 *
 * Suporta:
 * - CAPTCHA de imagem
 * - reCAPTCHA v2/v3
 * - hCaptcha
 */

import { Redis } from 'ioredis';
import { randomUUID } from 'crypto';
import { logger } from '../utils/logger.js';
import type { CaptchaInfo, CaptchaSolution, CaptchaSolutionResponse } from '../types/index.js';

// Provedores suportados
export type CaptchaProvider = '2captcha' | 'anticaptcha' | 'capmonster' | 'manual';

// Configuração do solver
export interface CaptchaSolverConfig {
  provider: CaptchaProvider;
  apiKey?: string;
  // Timeouts
  serviceTimeout?: number;      // Timeout para serviço (default: 120s)
  manualTimeout?: number;       // Timeout para resolução manual (default: 120s)
  // Fallback
  fallbackToManual?: boolean;   // Fallback para manual se serviço falhar (default: true)
  // Redis para HIL
  redisUrl?: string;
}

// Status do CAPTCHA
interface CaptchaTask {
  id: string;
  jobId: string;
  userId: string;
  captcha: CaptchaInfo;
  status: 'pending' | 'solving' | 'solved' | 'failed' | 'timeout';
  provider: CaptchaProvider;
  solution?: CaptchaSolution;
  error?: string;
  createdAt: Date;
  solvedAt?: Date;
}

// Callbacks pendentes para HIL
const pendingManualSolutions = new Map<string, {
  resolve: (solution: CaptchaSolution | null) => void;
  reject: (error: Error) => void;
  timeout: NodeJS.Timeout;
}>();

export class CaptchaSolverService {
  private config: Required<CaptchaSolverConfig>;
  private redis: Redis | null = null;
  private subscriber: Redis | null = null;

  constructor(config: CaptchaSolverConfig) {
    this.config = {
      provider: config.provider,
      apiKey: config.apiKey || '',
      serviceTimeout: config.serviceTimeout || 120000,
      manualTimeout: config.manualTimeout || 120000,
      fallbackToManual: config.fallbackToManual !== false,
      redisUrl: config.redisUrl || '',
    };

    // Inicializar Redis para HIL se configurado
    if (this.config.redisUrl) {
      this.initRedis();
    }
  }

  private async initRedis(): Promise<void> {
    this.redis = new Redis(this.config.redisUrl);
    this.subscriber = new Redis(this.config.redisUrl);

    // Escutar soluções de CAPTCHA do usuário
    await this.subscriber.subscribe('tribunais:captcha_solution');
    this.subscriber.on('message', (channel, message) => {
      if (channel === 'tribunais:captcha_solution') {
        const response: CaptchaSolutionResponse = JSON.parse(message);
        this.handleManualSolution(response);
      }
    });
  }

  /**
   * Resolve CAPTCHA usando estratégia híbrida
   */
  async solve(
    jobId: string,
    userId: string,
    captcha: CaptchaInfo,
    tribunalUrl: string,
    tribunal: string
  ): Promise<CaptchaSolution> {
    const captchaId = randomUUID();

    logger.info(`Resolvendo CAPTCHA ${captchaId}`, {
      type: captcha.type,
      provider: this.config.provider,
      jobId,
    });

    // Se provider é manual, vai direto para HIL
    if (this.config.provider === 'manual') {
      return this.solveManual(captchaId, jobId, userId, captcha, tribunalUrl, tribunal);
    }

    // Tenta resolver via serviço
    try {
      const solution = await this.solveViaService(captcha);
      logger.info(`CAPTCHA ${captchaId} resolvido via serviço`);
      return solution;
    } catch (error) {
      logger.warn(`Falha ao resolver CAPTCHA via serviço: ${error}`);

      // Fallback para manual se configurado
      if (this.config.fallbackToManual) {
        logger.info(`Fallback para resolução manual do CAPTCHA ${captchaId}`);
        return this.solveManual(captchaId, jobId, userId, captcha, tribunalUrl, tribunal);
      }

      throw error;
    }
  }

  /**
   * Resolve via serviço de CAPTCHA
   */
  private async solveViaService(captcha: CaptchaInfo): Promise<CaptchaSolution> {
    switch (this.config.provider) {
      case '2captcha':
        return this.solve2Captcha(captcha);
      case 'anticaptcha':
        return this.solveAntiCaptcha(captcha);
      case 'capmonster':
        return this.solveCapMonster(captcha);
      default:
        throw new Error(`Provider não suportado: ${this.config.provider}`);
    }
  }

  /**
   * 2Captcha integration
   * https://2captcha.com/2captcha-api
   */
  private async solve2Captcha(captcha: CaptchaInfo): Promise<CaptchaSolution> {
    const apiKey = this.config.apiKey;
    if (!apiKey) throw new Error('API key não configurada para 2Captcha');

    const baseUrl = 'https://2captcha.com';

    // Enviar CAPTCHA
    let taskId: string;

    if (captcha.type === 'image' && captcha.imageBase64) {
      // CAPTCHA de imagem
      const response = await fetch(`${baseUrl}/in.php`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          key: apiKey,
          method: 'base64',
          body: captcha.imageBase64,
          json: '1',
        }),
      });
      const data = await response.json();
      if (data.status !== 1) throw new Error(data.request);
      taskId = data.request;

    } else if (captcha.type === 'recaptcha_v2' && captcha.siteKey) {
      // reCAPTCHA v2
      const pageUrl = captcha.metadata?.pageUrl as string || '';
      const response = await fetch(`${baseUrl}/in.php`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          key: apiKey,
          method: 'userrecaptcha',
          googlekey: captcha.siteKey,
          pageurl: pageUrl,
          json: '1',
        }),
      });
      const data = await response.json();
      if (data.status !== 1) throw new Error(data.request);
      taskId = data.request;

    } else if (captcha.type === 'recaptcha_v3' && captcha.siteKey) {
      // reCAPTCHA v3
      const pageUrl = captcha.metadata?.pageUrl as string || '';
      const action = captcha.metadata?.action as string || 'verify';
      const response = await fetch(`${baseUrl}/in.php`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          key: apiKey,
          method: 'userrecaptcha',
          googlekey: captcha.siteKey,
          pageurl: pageUrl,
          version: 'v3',
          action,
          min_score: '0.3',
          json: '1',
        }),
      });
      const data = await response.json();
      if (data.status !== 1) throw new Error(data.request);
      taskId = data.request;

    } else if (captcha.type === 'hcaptcha' && captcha.siteKey) {
      // hCaptcha
      const pageUrl = captcha.metadata?.pageUrl as string || '';
      const response = await fetch(`${baseUrl}/in.php`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          key: apiKey,
          method: 'hcaptcha',
          sitekey: captcha.siteKey,
          pageurl: pageUrl,
          json: '1',
        }),
      });
      const data = await response.json();
      if (data.status !== 1) throw new Error(data.request);
      taskId = data.request;

    } else {
      throw new Error(`Tipo de CAPTCHA não suportado: ${captcha.type}`);
    }

    // Aguardar solução (polling)
    const startTime = Date.now();
    while (Date.now() - startTime < this.config.serviceTimeout) {
      await new Promise(r => setTimeout(r, 5000)); // Poll a cada 5s

      const response = await fetch(
        `${baseUrl}/res.php?key=${apiKey}&action=get&id=${taskId}&json=1`
      );
      const data = await response.json();

      if (data.status === 1) {
        // Resolvido
        if (captcha.type === 'image') {
          return { text: data.request };
        } else {
          return { token: data.request };
        }
      } else if (data.request !== 'CAPCHA_NOT_READY') {
        throw new Error(data.request);
      }
    }

    throw new Error('Timeout ao resolver CAPTCHA via 2Captcha');
  }

  /**
   * Anti-Captcha integration
   * https://anti-captcha.com/apidoc
   */
  private async solveAntiCaptcha(captcha: CaptchaInfo): Promise<CaptchaSolution> {
    const apiKey = this.config.apiKey;
    if (!apiKey) throw new Error('API key não configurada para Anti-Captcha');

    const baseUrl = 'https://api.anti-captcha.com';

    // Criar task
    let task: Record<string, unknown>;

    if (captcha.type === 'image' && captcha.imageBase64) {
      task = {
        type: 'ImageToTextTask',
        body: captcha.imageBase64,
      };
    } else if (captcha.type === 'recaptcha_v2' && captcha.siteKey) {
      task = {
        type: 'RecaptchaV2TaskProxyless',
        websiteURL: captcha.metadata?.pageUrl || '',
        websiteKey: captcha.siteKey,
      };
    } else if (captcha.type === 'recaptcha_v3' && captcha.siteKey) {
      task = {
        type: 'RecaptchaV3TaskProxyless',
        websiteURL: captcha.metadata?.pageUrl || '',
        websiteKey: captcha.siteKey,
        minScore: 0.3,
        pageAction: captcha.metadata?.action || 'verify',
      };
    } else if (captcha.type === 'hcaptcha' && captcha.siteKey) {
      task = {
        type: 'HCaptchaTaskProxyless',
        websiteURL: captcha.metadata?.pageUrl || '',
        websiteKey: captcha.siteKey,
      };
    } else {
      throw new Error(`Tipo de CAPTCHA não suportado: ${captcha.type}`);
    }

    // Enviar task
    const createResponse = await fetch(`${baseUrl}/createTask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clientKey: apiKey, task }),
    });
    const createData = await createResponse.json();
    if (createData.errorId !== 0) {
      throw new Error(createData.errorDescription);
    }
    const taskId = createData.taskId;

    // Aguardar solução
    const startTime = Date.now();
    while (Date.now() - startTime < this.config.serviceTimeout) {
      await new Promise(r => setTimeout(r, 5000));

      const resultResponse = await fetch(`${baseUrl}/getTaskResult`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clientKey: apiKey, taskId }),
      });
      const resultData = await resultResponse.json();

      if (resultData.errorId !== 0) {
        throw new Error(resultData.errorDescription);
      }

      if (resultData.status === 'ready') {
        if (captcha.type === 'image') {
          return { text: resultData.solution.text };
        } else {
          return { token: resultData.solution.gRecaptchaResponse || resultData.solution.token };
        }
      }
    }

    throw new Error('Timeout ao resolver CAPTCHA via Anti-Captcha');
  }

  /**
   * CapMonster integration
   * https://capmonster.cloud/documentation
   */
  private async solveCapMonster(captcha: CaptchaInfo): Promise<CaptchaSolution> {
    const apiKey = this.config.apiKey;
    if (!apiKey) throw new Error('API key não configurada para CapMonster');

    const baseUrl = 'https://api.capmonster.cloud';

    // Criar task (mesmo formato do Anti-Captcha)
    let task: Record<string, unknown>;

    if (captcha.type === 'image' && captcha.imageBase64) {
      task = {
        type: 'ImageToTextTask',
        body: captcha.imageBase64,
      };
    } else if (captcha.type === 'recaptcha_v2' && captcha.siteKey) {
      task = {
        type: 'NoCaptchaTaskProxyless',
        websiteURL: captcha.metadata?.pageUrl || '',
        websiteKey: captcha.siteKey,
      };
    } else if (captcha.type === 'recaptcha_v3' && captcha.siteKey) {
      task = {
        type: 'RecaptchaV3TaskProxyless',
        websiteURL: captcha.metadata?.pageUrl || '',
        websiteKey: captcha.siteKey,
        minScore: 0.3,
        pageAction: captcha.metadata?.action || 'verify',
      };
    } else if (captcha.type === 'hcaptcha' && captcha.siteKey) {
      task = {
        type: 'HCaptchaTaskProxyless',
        websiteURL: captcha.metadata?.pageUrl || '',
        websiteKey: captcha.siteKey,
      };
    } else {
      throw new Error(`Tipo de CAPTCHA não suportado: ${captcha.type}`);
    }

    // Enviar task
    const createResponse = await fetch(`${baseUrl}/createTask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clientKey: apiKey, task }),
    });
    const createData = await createResponse.json();
    if (createData.errorId !== 0) {
      throw new Error(createData.errorDescription);
    }
    const taskId = createData.taskId;

    // Aguardar solução
    const startTime = Date.now();
    while (Date.now() - startTime < this.config.serviceTimeout) {
      await new Promise(r => setTimeout(r, 3000)); // CapMonster é mais rápido

      const resultResponse = await fetch(`${baseUrl}/getTaskResult`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clientKey: apiKey, taskId }),
      });
      const resultData = await resultResponse.json();

      if (resultData.errorId !== 0) {
        throw new Error(resultData.errorDescription);
      }

      if (resultData.status === 'ready') {
        if (captcha.type === 'image') {
          return { text: resultData.solution.text };
        } else {
          return { token: resultData.solution.gRecaptchaResponse || resultData.solution.token };
        }
      }
    }

    throw new Error('Timeout ao resolver CAPTCHA via CapMonster');
  }

  /**
   * Resolve via HIL (Human-in-the-Loop)
   */
  private async solveManual(
    captchaId: string,
    jobId: string,
    userId: string,
    captcha: CaptchaInfo,
    tribunalUrl: string,
    tribunal: string
  ): Promise<CaptchaSolution> {
    if (!this.redis) {
      throw new Error('Redis não configurado para resolução manual');
    }

    const expiresAt = new Date(Date.now() + this.config.manualTimeout);

    return new Promise<CaptchaSolution>((resolve, reject) => {
      // Timeout
      const timeout = setTimeout(() => {
        pendingManualSolutions.delete(captchaId);
        reject(new Error('Timeout: usuário não resolveu o CAPTCHA'));
      }, this.config.manualTimeout);

      // Registrar callback
      pendingManualSolutions.set(captchaId, {
        resolve: (solution) => {
          if (solution) {
            resolve(solution);
          } else {
            reject(new Error('CAPTCHA cancelado pelo usuário'));
          }
        },
        reject,
        timeout,
      });

      // Publicar evento para WebSocket server
      this.redis!.publish('tribunais:captcha_required', JSON.stringify({
        jobId,
        userId,
        captchaId,
        tribunal,
        tribunalUrl,
        captcha,
        expiresAt,
      }));

      logger.info(`CAPTCHA ${captchaId} enviado para resolução manual`, { userId, tribunal });
    });
  }

  /**
   * Handler para soluções manuais recebidas
   */
  private handleManualSolution(response: CaptchaSolutionResponse): void {
    const pending = pendingManualSolutions.get(response.captchaId);
    if (!pending) return;

    clearTimeout(pending.timeout);
    pendingManualSolutions.delete(response.captchaId);

    if (response.success && response.solution) {
      pending.resolve(response.solution);
    } else {
      pending.resolve(null);
    }
  }

  /**
   * Cleanup
   */
  async close(): Promise<void> {
    // Cancelar pendentes
    for (const [id, pending] of pendingManualSolutions) {
      clearTimeout(pending.timeout);
      pending.reject(new Error('Serviço fechando'));
    }
    pendingManualSolutions.clear();

    // Fechar Redis
    if (this.redis) await this.redis.quit();
    if (this.subscriber) await this.subscriber.quit();
  }
}

// Singleton para uso global
let solverInstance: CaptchaSolverService | null = null;

export function getCaptchaSolver(config?: CaptchaSolverConfig): CaptchaSolverService {
  if (!solverInstance && config) {
    solverInstance = new CaptchaSolverService(config);
  }
  if (!solverInstance) {
    throw new Error('CaptchaSolverService não inicializado');
  }
  return solverInstance;
}

export function initCaptchaSolver(config: CaptchaSolverConfig): CaptchaSolverService {
  solverInstance = new CaptchaSolverService(config);
  return solverInstance;
}
