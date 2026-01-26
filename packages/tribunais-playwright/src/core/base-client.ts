/**
 * Cliente base para automação de tribunais
 * Implementa lógica comum de autenticação e navegação
 */

import {
  Browser,
  BrowserContext,
  Page,
  chromium,
  type LaunchOptions,
} from 'playwright';
import { EventEmitter } from 'eventemitter3';
import type {
  TribunalClientConfig,
  AuthConfig,
  TribunalEvents,
  TribunalSelectors,
  Notification,
  ApprovalInfo,
  SemanticSelector,
  CaptchaInfo,
  CaptchaSolution,
} from '../types/index.js';
import { CaptchaHandler } from './captcha-handler.js';

export abstract class BaseTribunalClient extends EventEmitter<TribunalEvents> {
  protected config: TribunalClientConfig;
  protected browser: Browser | null = null;
  protected context: BrowserContext | null = null;
  protected page: Page | null = null;
  protected isInitialized = false;
  protected isLoggedIn = false;
  protected captchaHandler: CaptchaHandler | null = null;

  /** Seletores específicos do tribunal - implementar nas subclasses */
  protected abstract selectors: TribunalSelectors;

  /** Nome do tribunal para logs */
  protected abstract tribunalName: string;

  constructor(config: TribunalClientConfig) {
    super();
    this.config = config;

    // Inicializa handler de captcha se configurado
    if (config.captcha) {
      this.captchaHandler = new CaptchaHandler(config.captcha);
    }
  }

  // ============================================
  // Inicialização
  // ============================================

  /** Endpoint CDP para reconexão */
  private cdpEndpoint: string | null = null;

  async init(): Promise<void> {
    if (this.isInitialized) return;

    const playwrightOpts = this.config.playwright ?? {};

    // Modo CDP - conectar a Chrome já aberto
    if (playwrightOpts.cdpEndpoint) {
      this.browser = await chromium.connectOverCDP(playwrightOpts.cdpEndpoint);
      this.cdpEndpoint = playwrightOpts.cdpEndpoint;
      const contexts = this.browser.contexts();
      this.context = contexts[0] ?? await this.browser.newContext();
      const pages = this.context.pages();
      this.page = pages[0] ?? await this.context.newPage();
    }
    // Modo persistente com CDP para reconexão
    else if (playwrightOpts.persistent) {
      const userDataDir = playwrightOpts.userDataDir ?? `${process.env.HOME}/.tribunais-playwright/chrome-profile`;
      const args: string[] = [];

      // Se definir porta CDP, permite reconexão futura
      if (playwrightOpts.cdpPort) {
        args.push(`--remote-debugging-port=${playwrightOpts.cdpPort}`);
        this.cdpEndpoint = `http://127.0.0.1:${playwrightOpts.cdpPort}`;
      }

      this.context = await chromium.launchPersistentContext(userDataDir, {
        headless: playwrightOpts.headless ?? false,
        slowMo: playwrightOpts.slowMo,
        channel: 'chrome',
        args,
      });
      this.page = this.context.pages()[0] ?? await this.context.newPage();
    }
    // Modo normal com certificado A1
    else if (this.config.auth.type === 'certificate_a1') {
      const args: string[] = [];
      if (playwrightOpts.cdpPort) {
        args.push(`--remote-debugging-port=${playwrightOpts.cdpPort}`);
        this.cdpEndpoint = `http://127.0.0.1:${playwrightOpts.cdpPort}`;
      }

      const launchOpts: LaunchOptions = {
        headless: playwrightOpts.headless ?? true,
        slowMo: playwrightOpts.slowMo,
        args,
      };
      this.browser = await chromium.launch(launchOpts);

      // Contexto com certificado cliente
      this.context = await this.browser.newContext({
        clientCertificates: [{
          origin: new URL(this.config.baseUrl).origin,
          pfxPath: this.config.auth.pfxPath,
          passphrase: this.config.auth.passphrase,
        }],
      });
      this.page = await this.context.newPage();
    }
    // Modo normal sem certificado
    else {
      const args: string[] = [];
      if (playwrightOpts.cdpPort) {
        args.push(`--remote-debugging-port=${playwrightOpts.cdpPort}`);
        this.cdpEndpoint = `http://127.0.0.1:${playwrightOpts.cdpPort}`;
      }

      const launchOpts: LaunchOptions = {
        headless: playwrightOpts.headless ?? true,
        slowMo: playwrightOpts.slowMo,
        args,
      };
      this.browser = await chromium.launch(launchOpts);
      this.context = await this.browser.newContext();
      this.page = await this.context.newPage();
    }

    // Timeout padrão
    this.page.setDefaultTimeout(playwrightOpts.timeout ?? 30000);

    this.isInitialized = true;
    this.log('Cliente inicializado');

    if (this.cdpEndpoint) {
      this.log(`CDP endpoint: ${this.cdpEndpoint}`);
    }
  }

  /**
   * Retorna o endpoint CDP para reconexão futura
   */
  getCdpEndpoint(): string | null {
    return this.cdpEndpoint;
  }

  /**
   * Minimiza a janela do navegador (via CDP)
   */
  async minimizeWindow(): Promise<void> {
    if (!this.page) return;
    const cdp = await this.page.context().newCDPSession(this.page);
    const { windowId } = await cdp.send('Browser.getWindowForTarget');
    await cdp.send('Browser.setWindowBounds', {
      windowId,
      bounds: { windowState: 'minimized' },
    });
    this.log('Janela minimizada');
  }

  /**
   * Restaura a janela do navegador (via CDP)
   */
  async restoreWindow(): Promise<void> {
    if (!this.page) return;
    const cdp = await this.page.context().newCDPSession(this.page);
    const { windowId } = await cdp.send('Browser.getWindowForTarget');
    await cdp.send('Browser.setWindowBounds', {
      windowId,
      bounds: { windowState: 'normal' },
    });
    this.log('Janela restaurada');
  }

  /**
   * Traz a janela para frente
   */
  async bringToFront(): Promise<void> {
    if (!this.page) return;
    await this.page.bringToFront();
    this.log('Janela trazida para frente');
  }

  async close(): Promise<void> {
    // Se keepAlive, não fecha o navegador
    if (this.config.playwright?.keepAlive) {
      this.log('keepAlive ativo - navegador mantido aberto');
      this.page = null;
      this.context = null;
      this.browser = null;
      this.isInitialized = false;
      this.isLoggedIn = false;
      return;
    }

    if (this.context) {
      await this.context.close();
      this.context = null;
    }
    if (this.browser) {
      await this.browser.close();
      this.browser = null;
    }
    this.page = null;
    this.isInitialized = false;
    this.isLoggedIn = false;
  }

  // ============================================
  // Autenticação
  // ============================================

  async login(): Promise<boolean> {
    this.ensureInitialized();
    const page = this.getPage();

    await this.navigateToLogin();

    switch (this.config.auth.type) {
      case 'password':
        return await this.loginWithPassword();

      case 'certificate_a1':
        return await this.loginWithCertificateA1();

      case 'certificate_a3_physical':
        return await this.loginWithCertificateA3Physical();

      case 'certificate_a3_cloud':
        return await this.loginWithCertificateA3Cloud();

      default:
        throw new Error(`Tipo de autenticação não suportado: ${(this.config.auth as AuthConfig).type}`);
    }
  }

  /** Navegar para página de login - pode ser sobrescrito */
  protected async navigateToLogin(): Promise<void> {
    const page = this.getPage();
    await page.goto(this.config.baseUrl);
    await this.waitForLoad();
  }

  /** Login com CPF e senha */
  protected async loginWithPassword(): Promise<boolean> {
    const page = this.getPage();
    const auth = this.config.auth as { type: 'password'; cpf: string; senha: string };

    this.log('Fazendo login com CPF e senha...');

    try {
      // Preenche CPF
      await this.fillSmart(this.selectors.login.cpfInput, auth.cpf);

      // Preenche senha
      await this.fillSmart(this.selectors.login.senhaInput, auth.senha);

      // Clica em entrar
      await this.clickSmart(this.selectors.login.entrarBtn);

      await this.waitForLoad();

      // Verifica sucesso
      const loggedIn = await this.checkLoggedIn();

      if (loggedIn) {
        this.isLoggedIn = true;
        this.emit('login:success', { usuario: auth.cpf });
        this.log('Login realizado com sucesso');
        return true;
      } else {
        this.emit('login:error', { error: 'Login falhou - credenciais inválidas ou erro no sistema' });
        return false;
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      this.emit('login:error', { error: msg });
      throw error;
    }
  }

  /** Login com certificado A1 (automático) */
  protected async loginWithCertificateA1(): Promise<boolean> {
    const page = this.getPage();

    this.log('Fazendo login com certificado A1...');

    try {
      // Clica no botão de certificado (se existir)
      if (this.selectors.login.certificadoBtn) {
        await this.clickSmart(this.selectors.login.certificadoBtn);
      }

      // O certificado é enviado automaticamente pelo contexto do Playwright
      await this.waitForLoad();

      // Aguarda redirecionamento/login
      await page.waitForTimeout(3000);

      const loggedIn = await this.checkLoggedIn();

      if (loggedIn) {
        this.isLoggedIn = true;
        this.emit('login:success', { usuario: 'certificado_a1' });
        this.log('Login com certificado A1 realizado');
        return true;
      } else {
        this.emit('login:error', { error: 'Login com certificado A1 falhou' });
        return false;
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      this.emit('login:error', { error: msg });
      throw error;
    }
  }

  /** Login com certificado A3 físico (token USB) - aguarda PIN */
  protected async loginWithCertificateA3Physical(): Promise<boolean> {
    const page = this.getPage();
    const auth = this.config.auth as { type: 'certificate_a3_physical'; onPinRequired?: () => Promise<void>; pinTimeout?: number };
    const timeout = auth.pinTimeout ?? 300000; // 5 minutos

    this.log('Fazendo login com certificado A3 físico...');

    try {
      // Clica no botão de certificado
      if (this.selectors.login.certificadoBtn) {
        await this.clickSmart(this.selectors.login.certificadoBtn);
      }

      // Notifica que PIN é necessário
      this.emit('login:pin_required', { timeout });
      await this.notify({
        type: 'pin_required',
        message: 'Insira o token USB e digite o PIN na janela do sistema',
        expiresIn: timeout / 1000,
        timestamp: new Date(),
      });

      // Callback personalizado
      if (auth.onPinRequired) {
        await auth.onPinRequired();
      }

      // Aguarda login (polling)
      const loggedIn = await this.waitForLoginSuccess(timeout);

      if (loggedIn) {
        this.isLoggedIn = true;
        this.emit('login:success', { usuario: 'certificado_a3_fisico' });
        this.log('Login com certificado A3 físico realizado');
        return true;
      } else {
        this.emit('login:error', { error: 'Timeout aguardando PIN do certificado' });
        return false;
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      this.emit('login:error', { error: msg });
      throw error;
    }
  }

  /** Login com certificado A3 na nuvem - aguarda aprovação no celular */
  protected async loginWithCertificateA3Cloud(): Promise<boolean> {
    const page = this.getPage();
    const auth = this.config.auth as {
      type: 'certificate_a3_cloud';
      provider: string;
      onApprovalRequired?: (info: ApprovalInfo) => Promise<void>;
      approvalTimeout?: number;
    };
    const timeout = auth.approvalTimeout ?? 120000; // 2 minutos

    this.log(`Fazendo login com certificado A3 na nuvem (${auth.provider})...`);

    try {
      // Clica no botão de certificado
      if (this.selectors.login.certificadoBtn) {
        await this.clickSmart(this.selectors.login.certificadoBtn);
      }

      // Aguarda popup/redirecionamento do provider de nuvem
      await this.waitForLoad();
      await page.waitForTimeout(2000);

      // Notifica que aprovação é necessária
      const approvalInfo: ApprovalInfo = {
        type: 'login',
        message: `Aprove o login no app ${auth.provider} do seu celular`,
        expiresIn: timeout / 1000,
        provider: auth.provider,
      };

      this.emit('login:approval_required', approvalInfo);
      await this.notify({
        type: 'approval_required',
        message: approvalInfo.message,
        expiresIn: approvalInfo.expiresIn,
        data: approvalInfo,
        timestamp: new Date(),
      });

      // Callback personalizado
      if (auth.onApprovalRequired) {
        await auth.onApprovalRequired(approvalInfo);
      }

      // Aguarda login (polling)
      const loggedIn = await this.waitForLoginSuccess(timeout);

      if (loggedIn) {
        this.isLoggedIn = true;
        this.emit('login:success', { usuario: 'certificado_a3_nuvem' });
        this.log('Login com certificado A3 na nuvem realizado');
        return true;
      } else {
        this.emit('login:error', { error: 'Timeout aguardando aprovação no celular' });
        return false;
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      this.emit('login:error', { error: msg });
      throw error;
    }
  }

  /** Verifica se está logado */
  protected async checkLoggedIn(): Promise<boolean> {
    const page = this.getPage();
    try {
      const logoutEl = await this.findSmart(this.selectors.login.logoutLink, 3000);
      return logoutEl !== null;
    } catch {
      return false;
    }
  }

  /** Aguarda login com sucesso (polling) */
  protected async waitForLoginSuccess(timeout: number): Promise<boolean> {
    const start = Date.now();

    while (Date.now() - start < timeout) {
      const loggedIn = await this.checkLoggedIn();
      if (loggedIn) return true;

      // Verifica erro
      const page = this.getPage();
      const errorEl = await page.$('[class*="erro"], [class*="error"], .alert-danger');
      if (errorEl) {
        const errorText = await errorEl.textContent();
        throw new Error(`Erro no login: ${errorText}`);
      }

      await page.waitForTimeout(2000);
    }

    return false;
  }

  async logout(): Promise<void> {
    if (!this.isLoggedIn) return;

    const page = this.getPage();

    try {
      await this.clickSmart(this.selectors.login.logoutLink);
      await this.waitForLoad();
      this.isLoggedIn = false;
      this.log('Logout realizado');
    } catch {
      // Ignora erro se já estiver deslogado
    }
  }

  // ============================================
  // Captcha (Human-in-the-loop)
  // ============================================

  /**
   * Detecta e resolve captcha na página
   * Retorna true se captcha foi resolvido, false se não havia captcha
   */
  protected async handleCaptchaIfPresent(): Promise<boolean> {
    if (!this.captchaHandler) return false;

    const page = this.getPage();
    const captchaInfo = await this.captchaHandler.detectCaptcha(page);

    if (!captchaInfo) return false;

    this.log(`Captcha detectado: ${captchaInfo.type}`);
    this.emit('captcha:detected', captchaInfo);

    // Notifica usuário
    await this.notify({
      type: 'captcha_detected',
      message: this.getCaptchaMessage(captchaInfo),
      data: captchaInfo,
      expiresIn: captchaInfo.expiresIn,
      timestamp: new Date(),
    });

    // Emite evento para resolução
    this.emit('captcha:required', captchaInfo);
    await this.notify({
      type: 'captcha_required',
      message: this.getCaptchaMessage(captchaInfo),
      data: captchaInfo,
      expiresIn: captchaInfo.expiresIn,
      timestamp: new Date(),
    });

    // Tenta resolver
    const solution = await this.captchaHandler.solveCaptcha(page, captchaInfo);

    if (solution) {
      // Aplica solução
      if (captchaInfo.type === 'image') {
        await this.captchaHandler.fillCaptchaSolution(page, solution.solution);
      } else if (captchaInfo.type === 'recaptcha_v2' || captchaInfo.type === 'hcaptcha') {
        await this.captchaHandler.injectCaptchaToken(page, solution.solution, captchaInfo.type);
      }

      this.log(`Captcha resolvido em ${solution.solveTime}ms por ${solution.solvedBy}`);
      this.emit('captcha:solved', { captcha: captchaInfo, solution });
      await this.notify({
        type: 'captcha_solved',
        message: `Captcha resolvido com sucesso`,
        timestamp: new Date(),
      });

      return true;
    } else {
      this.log('Falha ao resolver captcha');
      this.emit('captcha:failed', { captcha: captchaInfo, error: 'Timeout ou falha na resolução' });
      await this.notify({
        type: 'captcha_failed',
        message: 'Falha ao resolver captcha',
        timestamp: new Date(),
      });

      return false;
    }
  }

  /**
   * Aguarda resolução de captcha (para uso externo)
   */
  async waitForCaptchaResolution(timeout?: number): Promise<CaptchaSolution | null> {
    if (!this.captchaHandler) return null;

    const page = this.getPage();
    const captchaInfo = await this.captchaHandler.detectCaptcha(page);

    if (!captchaInfo) return null;

    return await this.captchaHandler.solveCaptcha(page, captchaInfo);
  }

  /**
   * Resolve captcha manualmente (para uso via API)
   */
  async solveCaptchaManually(solution: string): Promise<void> {
    if (!this.captchaHandler) {
      throw new Error('Captcha handler não configurado');
    }

    const page = this.getPage();
    const captchaInfo = await this.captchaHandler.detectCaptcha(page);

    if (!captchaInfo) {
      throw new Error('Nenhum captcha detectado na página');
    }

    if (captchaInfo.type === 'image') {
      await this.captchaHandler.fillCaptchaSolution(page, solution);
    } else if (captchaInfo.type === 'recaptcha_v2' || captchaInfo.type === 'hcaptcha') {
      await this.captchaHandler.injectCaptchaToken(page, solution, captchaInfo.type);
    }
  }

  /**
   * Retorna mensagem apropriada para o tipo de captcha
   */
  private getCaptchaMessage(captcha: CaptchaInfo): string {
    switch (captcha.type) {
      case 'image':
        return 'Resolva o captcha de imagem exibido na tela';
      case 'recaptcha_v2':
        return 'Complete o reCAPTCHA "Não sou um robô"';
      case 'recaptcha_v3':
        return 'Aguardando verificação do reCAPTCHA v3';
      case 'hcaptcha':
        return 'Complete o hCaptcha exibido na tela';
      case 'audio':
        return 'Resolva o captcha de áudio';
      default:
        return 'Resolva o captcha exibido na tela';
    }
  }

  // ============================================
  // Helpers de Navegação com Seletores Semânticos
  // ============================================

  /** Encontra elemento usando seletor semântico */
  protected async findSmart(selector: SemanticSelector, timeout?: number): Promise<ReturnType<Page['$']>> {
    const page = this.getPage();

    try {
      // Tenta primeiro pelo role ARIA
      const locator = page.getByRole(selector.role as Parameters<Page['getByRole']>[0], {
        name: selector.name,
      });

      await locator.first().waitFor({ timeout: timeout ?? 5000, state: 'visible' });
      return await locator.first().elementHandle();
    } catch {
      // Fallback para CSS
      if (selector.fallback) {
        const el = await page.waitForSelector(selector.fallback, { timeout: timeout ?? 5000 });
        return el;
      }
      return null;
    }
  }

  /** Clica usando seletor semântico */
  protected async clickSmart(selector: SemanticSelector): Promise<void> {
    const page = this.getPage();

    try {
      const locator = page.getByRole(selector.role as Parameters<Page['getByRole']>[0], {
        name: selector.name,
      });
      await locator.first().click();
    } catch {
      if (selector.fallback) {
        await page.click(selector.fallback);
      } else {
        throw new Error(`Elemento não encontrado: ${JSON.stringify(selector)}`);
      }
    }
  }

  /** Preenche campo usando seletor semântico */
  protected async fillSmart(selector: SemanticSelector, value: string): Promise<void> {
    const page = this.getPage();

    try {
      const locator = page.getByRole(selector.role as Parameters<Page['getByRole']>[0], {
        name: selector.name,
      });
      await locator.first().fill(value);
    } catch {
      if (selector.fallback) {
        await page.fill(selector.fallback, value);
      } else {
        throw new Error(`Campo não encontrado: ${JSON.stringify(selector)}`);
      }
    }
  }

  /** Seleciona opção usando seletor semântico */
  protected async selectSmart(selector: SemanticSelector, option: { label?: string; value?: string }): Promise<void> {
    const page = this.getPage();

    try {
      const locator = page.getByRole(selector.role as Parameters<Page['getByRole']>[0], {
        name: selector.name,
      });
      await locator.first().selectOption(option);
    } catch {
      if (selector.fallback) {
        await page.selectOption(selector.fallback, option);
      } else {
        throw new Error(`Select não encontrado: ${JSON.stringify(selector)}`);
      }
    }
  }

  /** Aguarda carregamento da página */
  protected async waitForLoad(): Promise<void> {
    const page = this.getPage();

    // Aguarda rede estabilizar
    await page.waitForLoadState('networkidle').catch(() => {});

    // Aguarda loading indicator sumir (se existir)
    try {
      const loadingSelector = this.selectors.common.loadingIndicator;
      if (loadingSelector.fallback) {
        await page.waitForSelector(loadingSelector.fallback, { state: 'hidden', timeout: 10000 });
      }
    } catch {
      // Ignora se não existir
    }
  }

  // ============================================
  // Notificações
  // ============================================

  protected async notify(notification: Notification): Promise<void> {
    // Callback local
    if (this.config.onNotification) {
      await this.config.onNotification(notification);
    }

    // Webhook
    if (this.config.webhookUrl) {
      try {
        await fetch(this.config.webhookUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(notification),
        });
      } catch (err) {
        this.log(`Erro ao enviar webhook: ${err}`);
      }
    }
  }

  // ============================================
  // Utilitários
  // ============================================

  protected getPage(): Page {
    if (!this.page) {
      throw new Error('Cliente não inicializado. Chame init() primeiro.');
    }
    return this.page;
  }

  protected ensureInitialized(): void {
    if (!this.isInitialized) {
      throw new Error('Cliente não inicializado. Chame init() primeiro.');
    }
  }

  protected ensureLoggedIn(): void {
    if (!this.isLoggedIn) {
      throw new Error('Usuário não logado. Chame login() primeiro.');
    }
  }

  protected log(message: string): void {
    console.log(`[${this.tribunalName}] ${message}`);
  }

  /** Captura screenshot */
  async screenshot(path?: string): Promise<Buffer> {
    const page = this.getPage();
    return await page.screenshot({ path, fullPage: true });
  }

  /** Retorna URL atual */
  getCurrentUrl(): string {
    return this.getPage().url();
  }

  /** Verifica se sessão está ativa */
  async isSessionActive(): Promise<boolean> {
    return await this.checkLoggedIn();
  }
}
