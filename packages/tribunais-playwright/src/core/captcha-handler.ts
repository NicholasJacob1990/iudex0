/**
 * Handler de Captcha para tribunais-playwright
 * Suporta resolução manual e via serviços externos
 */

import type { Page } from 'playwright';
import type {
  CaptchaConfig,
  CaptchaInfo,
  CaptchaSolution,
  CaptchaType,
} from '../types/index.js';

export interface CaptchaSelectors {
  /** Container do captcha de imagem */
  imageContainer?: string;
  /** Imagem do captcha */
  image?: string;
  /** Input para resposta */
  input?: string;
  /** Botão de refresh */
  refreshBtn?: string;
  /** Container do reCAPTCHA */
  recaptchaContainer?: string;
  /** Container do hCaptcha */
  hcaptchaContainer?: string;
}

const DEFAULT_SELECTORS: CaptchaSelectors = {
  imageContainer: '[class*="captcha"], #captcha, .captcha-container',
  image: 'img[src*="captcha"], img[id*="captcha"], img[class*="captcha"]',
  input: 'input[name*="captcha"], input[id*="captcha"], input[placeholder*="captcha" i]',
  refreshBtn: '[class*="refresh"], button[title*="novo" i], a[title*="atualizar" i]',
  recaptchaContainer: '.g-recaptcha, [data-sitekey], iframe[src*="recaptcha"]',
  hcaptchaContainer: '.h-captcha, iframe[src*="hcaptcha"]',
};

export class CaptchaHandler {
  private config: CaptchaConfig;
  private selectors: CaptchaSelectors;

  constructor(config: CaptchaConfig, selectors?: CaptchaSelectors) {
    this.config = config;
    this.selectors = { ...DEFAULT_SELECTORS, ...selectors };
  }

  /**
   * Detecta se há captcha na página
   */
  async detectCaptcha(page: Page): Promise<CaptchaInfo | null> {
    // Verifica reCAPTCHA
    const recaptcha = await page.$(this.selectors.recaptchaContainer ?? '');
    if (recaptcha) {
      const siteKey = await page.$eval(
        '[data-sitekey]',
        el => el.getAttribute('data-sitekey')
      ).catch(() => null);

      return {
        type: 'recaptcha_v2',
        siteKey: siteKey ?? undefined,
        pageUrl: page.url(),
        timestamp: new Date(),
        expiresIn: 120,
      };
    }

    // Verifica hCaptcha
    const hcaptcha = await page.$(this.selectors.hcaptchaContainer ?? '');
    if (hcaptcha) {
      const siteKey = await page.$eval(
        '.h-captcha[data-sitekey]',
        el => el.getAttribute('data-sitekey')
      ).catch(() => null);

      return {
        type: 'hcaptcha',
        siteKey: siteKey ?? undefined,
        pageUrl: page.url(),
        timestamp: new Date(),
        expiresIn: 120,
      };
    }

    // Verifica captcha de imagem
    const captchaImage = await page.$(this.selectors.image ?? '');
    if (captchaImage) {
      const imageBase64 = await this.captureImageAsBase64(page, captchaImage);

      return {
        type: 'image',
        imageBase64,
        pageUrl: page.url(),
        timestamp: new Date(),
        expiresIn: 300, // 5 minutos para captcha de imagem
      };
    }

    return null;
  }

  /**
   * Resolve captcha usando a estratégia configurada
   */
  async solveCaptcha(page: Page, captchaInfo: CaptchaInfo): Promise<CaptchaSolution | null> {
    const startTime = Date.now();

    switch (this.config.mode) {
      case 'manual':
        return await this.solveManually(page, captchaInfo);

      case 'service':
        return await this.solveViaService(captchaInfo);

      case 'hybrid':
        // Tenta serviço primeiro, fallback para manual
        try {
          const serviceSolution = await this.solveViaService(captchaInfo);
          if (serviceSolution) return serviceSolution;
        } catch {
          console.log('[Captcha] Serviço falhou, aguardando resolução manual...');
        }
        return await this.solveManually(page, captchaInfo);

      default:
        return null;
    }
  }

  /**
   * Aguarda resolução manual do usuário
   */
  private async solveManually(page: Page, captchaInfo: CaptchaInfo): Promise<CaptchaSolution | null> {
    const timeout = this.config.manualTimeout ?? 300000; // 5 minutos

    // Callback personalizado
    if (this.config.onCaptchaRequired) {
      const solution = await Promise.race([
        this.config.onCaptchaRequired(captchaInfo),
        new Promise<string>((_, reject) =>
          setTimeout(() => reject(new Error('Timeout')), timeout)
        ),
      ]).catch(() => null);

      if (solution) {
        return {
          solution,
          solvedBy: 'user',
          solveTime: Date.now() - captchaInfo.timestamp.getTime(),
        };
      }
    }

    // Fallback: aguarda input ser preenchido
    if (captchaInfo.type === 'image') {
      return await this.waitForManualImageCaptcha(page, timeout);
    }

    // Para reCAPTCHA/hCaptcha, aguarda token
    if (captchaInfo.type === 'recaptcha_v2' || captchaInfo.type === 'hcaptcha') {
      return await this.waitForCaptchaToken(page, timeout);
    }

    return null;
  }

  /**
   * Aguarda usuário preencher captcha de imagem
   */
  private async waitForManualImageCaptcha(page: Page, timeout: number): Promise<CaptchaSolution | null> {
    const startTime = Date.now();
    const inputSelector = this.selectors.input ?? 'input[name*="captcha"]';

    while (Date.now() - startTime < timeout) {
      const input = await page.$(inputSelector);
      if (input) {
        const value = await input.inputValue();
        if (value && value.length >= 3) {
          return {
            solution: value,
            solvedBy: 'manual',
            solveTime: Date.now() - startTime,
          };
        }
      }
      await page.waitForTimeout(1000);
    }

    return null;
  }

  /**
   * Aguarda token do reCAPTCHA/hCaptcha ser preenchido
   */
  private async waitForCaptchaToken(page: Page, timeout: number): Promise<CaptchaSolution | null> {
    const startTime = Date.now();

    while (Date.now() - startTime < timeout) {
      // Verifica g-recaptcha-response
      const recaptchaToken = await page.$eval(
        'textarea[name="g-recaptcha-response"]',
        el => (el as HTMLTextAreaElement).value
      ).catch(() => '');

      if (recaptchaToken) {
        return {
          solution: recaptchaToken,
          solvedBy: 'manual',
          solveTime: Date.now() - startTime,
        };
      }

      // Verifica h-captcha-response
      const hcaptchaToken = await page.$eval(
        'textarea[name="h-captcha-response"]',
        el => (el as HTMLTextAreaElement).value
      ).catch(() => '');

      if (hcaptchaToken) {
        return {
          solution: hcaptchaToken,
          solvedBy: 'manual',
          solveTime: Date.now() - startTime,
        };
      }

      await page.waitForTimeout(1000);
    }

    return null;
  }

  /**
   * Resolve via serviço externo (2captcha, anticaptcha, etc.)
   */
  private async solveViaService(captchaInfo: CaptchaInfo): Promise<CaptchaSolution | null> {
    if (!this.config.service) {
      throw new Error('Serviço de captcha não configurado');
    }

    const { provider, apiKey, timeout = 120000 } = this.config.service;

    switch (provider) {
      case '2captcha':
        return await this.solveWith2Captcha(captchaInfo, apiKey, timeout);

      case 'anticaptcha':
        return await this.solveWithAntiCaptcha(captchaInfo, apiKey, timeout);

      case 'capsolver':
        return await this.solveWithCapSolver(captchaInfo, apiKey, timeout);

      default:
        throw new Error(`Provedor de captcha não suportado: ${provider}`);
    }
  }

  /**
   * Resolve via 2captcha
   */
  private async solveWith2Captcha(
    captcha: CaptchaInfo,
    apiKey: string,
    timeout: number
  ): Promise<CaptchaSolution | null> {
    const startTime = Date.now();

    // Enviar captcha
    let taskId: string;

    if (captcha.type === 'image' && captcha.imageBase64) {
      const response = await fetch('https://2captcha.com/in.php', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          key: apiKey,
          method: 'base64',
          body: captcha.imageBase64,
          json: '1',
        }),
      });
      const data = await response.json() as { status: number; request: string };
      if (data.status !== 1) throw new Error(`2captcha error: ${data.request}`);
      taskId = data.request;
    } else if (captcha.type === 'recaptcha_v2' && captcha.siteKey) {
      const response = await fetch('https://2captcha.com/in.php', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          key: apiKey,
          method: 'userrecaptcha',
          googlekey: captcha.siteKey,
          pageurl: captcha.pageUrl,
          json: '1',
        }),
      });
      const data = await response.json() as { status: number; request: string };
      if (data.status !== 1) throw new Error(`2captcha error: ${data.request}`);
      taskId = data.request;
    } else {
      throw new Error(`Tipo de captcha não suportado para 2captcha: ${captcha.type}`);
    }

    // Polling para resultado
    while (Date.now() - startTime < timeout) {
      await new Promise(r => setTimeout(r, 5000));

      const response = await fetch(`https://2captcha.com/res.php?key=${apiKey}&action=get&id=${taskId}&json=1`);
      const data = await response.json() as { status: number; request: string };

      if (data.status === 1) {
        return {
          solution: data.request,
          solvedBy: '2captcha',
          solveTime: Date.now() - startTime,
        };
      }

      if (data.request !== 'CAPCHA_NOT_READY') {
        throw new Error(`2captcha error: ${data.request}`);
      }
    }

    return null;
  }

  /**
   * Resolve via Anti-Captcha
   */
  private async solveWithAntiCaptcha(
    captcha: CaptchaInfo,
    apiKey: string,
    timeout: number
  ): Promise<CaptchaSolution | null> {
    const startTime = Date.now();

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
        websiteURL: captcha.pageUrl,
        websiteKey: captcha.siteKey,
      };
    } else {
      throw new Error(`Tipo de captcha não suportado para AntiCaptcha: ${captcha.type}`);
    }

    const createResponse = await fetch('https://api.anti-captcha.com/createTask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        clientKey: apiKey,
        task,
      }),
    });
    const createData = await createResponse.json() as { errorId: number; taskId?: number; errorDescription?: string };

    if (createData.errorId !== 0) {
      throw new Error(`AntiCaptcha error: ${createData.errorDescription}`);
    }

    const taskId = createData.taskId;

    // Polling para resultado
    while (Date.now() - startTime < timeout) {
      await new Promise(r => setTimeout(r, 5000));

      const resultResponse = await fetch('https://api.anti-captcha.com/getTaskResult', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          clientKey: apiKey,
          taskId,
        }),
      });
      const resultData = await resultResponse.json() as {
        errorId: number;
        status: string;
        solution?: { text?: string; gRecaptchaResponse?: string };
        errorDescription?: string;
      };

      if (resultData.errorId !== 0) {
        throw new Error(`AntiCaptcha error: ${resultData.errorDescription}`);
      }

      if (resultData.status === 'ready' && resultData.solution) {
        const solution = resultData.solution.text ?? resultData.solution.gRecaptchaResponse ?? '';
        return {
          solution,
          solvedBy: 'anticaptcha',
          solveTime: Date.now() - startTime,
        };
      }
    }

    return null;
  }

  /**
   * Resolve via CapSolver
   */
  private async solveWithCapSolver(
    captcha: CaptchaInfo,
    apiKey: string,
    timeout: number
  ): Promise<CaptchaSolution | null> {
    const startTime = Date.now();

    let task: Record<string, unknown>;

    if (captcha.type === 'image' && captcha.imageBase64) {
      task = {
        type: 'ImageToTextTask',
        body: captcha.imageBase64,
      };
    } else if (captcha.type === 'recaptcha_v2' && captcha.siteKey) {
      task = {
        type: 'ReCaptchaV2TaskProxyLess',
        websiteURL: captcha.pageUrl,
        websiteKey: captcha.siteKey,
      };
    } else {
      throw new Error(`Tipo de captcha não suportado para CapSolver: ${captcha.type}`);
    }

    const createResponse = await fetch('https://api.capsolver.com/createTask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        clientKey: apiKey,
        task,
      }),
    });
    const createData = await createResponse.json() as { errorId: number; taskId?: string; errorDescription?: string };

    if (createData.errorId !== 0) {
      throw new Error(`CapSolver error: ${createData.errorDescription}`);
    }

    const taskId = createData.taskId;

    // Polling para resultado
    while (Date.now() - startTime < timeout) {
      await new Promise(r => setTimeout(r, 3000));

      const resultResponse = await fetch('https://api.capsolver.com/getTaskResult', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          clientKey: apiKey,
          taskId,
        }),
      });
      const resultData = await resultResponse.json() as {
        errorId: number;
        status: string;
        solution?: { text?: string; gRecaptchaResponse?: string };
        errorDescription?: string;
      };

      if (resultData.errorId !== 0) {
        throw new Error(`CapSolver error: ${resultData.errorDescription}`);
      }

      if (resultData.status === 'ready' && resultData.solution) {
        const solution = resultData.solution.text ?? resultData.solution.gRecaptchaResponse ?? '';
        return {
          solution,
          solvedBy: 'capsolver',
          solveTime: Date.now() - startTime,
        };
      }
    }

    return null;
  }

  /**
   * Captura imagem do captcha como base64
   */
  private async captureImageAsBase64(page: Page, imageElement: ReturnType<Page['$']> extends Promise<infer T> ? T : never): Promise<string> {
    if (!imageElement) return '';

    try {
      // Tenta pegar do src se for data URL
      const src = await imageElement.getAttribute('src');
      if (src?.startsWith('data:image')) {
        return src.split(',')[1] ?? '';
      }

      // Captura screenshot do elemento
      const buffer = await imageElement.screenshot();
      return buffer.toString('base64');
    } catch {
      return '';
    }
  }

  /**
   * Preenche o campo de captcha com a solução
   */
  async fillCaptchaSolution(page: Page, solution: string): Promise<void> {
    const inputSelector = this.selectors.input ?? 'input[name*="captcha"]';
    await page.fill(inputSelector, solution);
  }

  /**
   * Injeta token de reCAPTCHA/hCaptcha
   */
  async injectCaptchaToken(page: Page, token: string, type: CaptchaType): Promise<void> {
    if (type === 'recaptcha_v2') {
      await page.evaluate((t) => {
        const textarea = document.querySelector('textarea[name="g-recaptcha-response"]') as HTMLTextAreaElement;
        if (textarea) {
          textarea.value = t;
          textarea.dispatchEvent(new Event('change', { bubbles: true }));
        }
        // Callback do reCAPTCHA
        if (typeof (window as unknown as { grecaptcha?: { callback?: (t: string) => void } }).grecaptcha?.callback === 'function') {
          (window as unknown as { grecaptcha: { callback: (t: string) => void } }).grecaptcha.callback(t);
        }
      }, token);
    } else if (type === 'hcaptcha') {
      await page.evaluate((t) => {
        const textarea = document.querySelector('textarea[name="h-captcha-response"]') as HTMLTextAreaElement;
        if (textarea) {
          textarea.value = t;
          textarea.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }, token);
    }
  }
}
