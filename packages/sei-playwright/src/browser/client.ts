/**
 * Cliente Playwright para automacao do SEI via navegador
 *
 * Refatorado para usar locators semanticos ARIA em vez de seletores CSS
 */

import { chromium, type Browser, type BrowserContext, type Page, type Locator, type FrameLocator } from 'playwright';
import { SEI_SELECTORS } from './selectors.js';
import type { SEIConfig, CreateDocumentOptions, ForwardOptions } from '../types.js';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';

export interface BrowserClientOptions {
  headless?: boolean;
  timeout?: number;
  userDataDir?: string;
}

/**
 * Cliente de automacao do SEI usando Playwright
 *
 * @example
 * ```typescript
 * const client = new SEIBrowserClient({
 *   baseUrl: 'https://sei.mg.gov.br',
 *   browser: { usuario: 'meu.usuario', senha: 'minhaSenha' },
 *   playwright: { headless: true },
 * });
 *
 * await client.init();
 * await client.login();
 * const docs = await client.listDocuments('5030.01.0002527/2025-32');
 * await client.close();
 * ```
 */
export class SEIBrowserClient {
  private config: SEIConfig;
  private browser: Browser | null = null;
  private context: BrowserContext | null = null;
  private page: Page | null = null;

  /** Endpoint CDP para reconexão */
  private cdpEndpoint: string | null = null;

  constructor(config: SEIConfig) {
    this.config = config;
  }

  /** URL base do SEI */
  private get baseUrl(): string {
    return this.config.baseUrl.replace(/\/$/, '');
  }

  /** Timeout padrao */
  private get timeout(): number {
    return this.config.playwright?.timeout ?? 30000;
  }

  /** Diretório padrão para persistent context */
  private get defaultUserDataDir(): string {
    return path.join(os.homedir(), '.sei-playwright', 'chrome-profile');
  }

  /** Inicializa o navegador */
  async init(): Promise<void> {
    const options = this.config.playwright ?? {};

    // Opção 1: Conectar a Chrome já aberto via CDP
    if (options.cdpEndpoint) {
      this.browser = await chromium.connectOverCDP(options.cdpEndpoint);
      this.cdpEndpoint = options.cdpEndpoint;
      const contexts = this.browser.contexts();
      if (contexts.length > 0) {
        this.context = contexts[0];
        const pages = this.context.pages();
        this.page = pages[0] ?? (await this.context.newPage());
      } else {
        this.context = await this.browser.newContext();
        this.page = await this.context.newPage();
      }
      this.page.setDefaultTimeout(this.timeout);
      return;
    }

    // Opção 2: Persistent context (mantém sessão)
    if (options.persistent || options.userDataDir) {
      const userDataDir = options.userDataDir ?? this.defaultUserDataDir;

      // Cria diretório se não existir
      if (!fs.existsSync(userDataDir)) {
        fs.mkdirSync(userDataDir, { recursive: true });
      }

      // Args para CDP port se definido
      const args: string[] = [];
      if (options.cdpPort) {
        args.push(`--remote-debugging-port=${options.cdpPort}`);
        this.cdpEndpoint = `http://127.0.0.1:${options.cdpPort}`;
      }

      this.context = await chromium.launchPersistentContext(userDataDir, {
        headless: options.headless ?? true,
        channel: options.channel, // 'chrome' usa Chrome instalado
        args: args.length > 0 ? args : undefined,
      });
      this.page = this.context.pages()[0] ?? (await this.context.newPage());
      this.page.setDefaultTimeout(this.timeout);
      return;
    }

    // Opção 3: Browser normal (sem persistência)
    const args: string[] = [];
    if (options.cdpPort) {
      args.push(`--remote-debugging-port=${options.cdpPort}`);
      this.cdpEndpoint = `http://127.0.0.1:${options.cdpPort}`;
    }

    this.browser = await chromium.launch({
      headless: options.headless ?? true,
      channel: options.channel,
      args: args.length > 0 ? args : undefined,
    });
    this.context = await this.browser.newContext();
    this.page = await this.context.newPage();
    this.page.setDefaultTimeout(this.timeout);
  }

  /** Verifica se esta inicializado */
  get isReady(): boolean {
    return this.page !== null;
  }

  /** Obtem a pagina atual */
  getPage(): Page {
    if (!this.page) {
      throw new Error('Cliente nao inicializado. Chame init() primeiro.');
    }
    return this.page;
  }

  /** Fecha o navegador */
  async close(): Promise<void> {
    // Se keepAlive está ativo, não fecha o navegador
    if (this.config.playwright?.keepAlive) {
      console.log('[SEI] keepAlive ativo - navegador mantido aberto');
      this.page = null;
      this.context = null;
      this.browser = null;
      return;
    }

    if (this.browser) {
      await this.browser.close();
    } else if (this.context) {
      await this.context.close();
    }
    this.browser = null;
    this.context = null;
    this.page = null;
  }

  // ============================================
  // Session Management & Window Control
  // ============================================

  /**
   * Retorna o endpoint CDP para reconexão futura
   * Útil para manter sessão entre execuções
   */
  getCdpEndpoint(): string | null {
    return this.cdpEndpoint;
  }

  /**
   * Minimiza a janela do navegador (via CDP)
   * Útil quando se quer manter o navegador aberto mas fora do caminho
   */
  async minimizeWindow(): Promise<void> {
    if (!this.page) return;
    try {
      const cdp = await this.page.context().newCDPSession(this.page);
      const { windowId } = await cdp.send('Browser.getWindowForTarget');
      await cdp.send('Browser.setWindowBounds', {
        windowId,
        bounds: { windowState: 'minimized' },
      });
      console.log('[SEI] Janela minimizada');
    } catch (err) {
      console.warn('[SEI] Erro ao minimizar janela:', err);
    }
  }

  /**
   * Restaura a janela do navegador (via CDP)
   */
  async restoreWindow(): Promise<void> {
    if (!this.page) return;
    try {
      const cdp = await this.page.context().newCDPSession(this.page);
      const { windowId } = await cdp.send('Browser.getWindowForTarget');
      await cdp.send('Browser.setWindowBounds', {
        windowId,
        bounds: { windowState: 'normal' },
      });
      console.log('[SEI] Janela restaurada');
    } catch (err) {
      console.warn('[SEI] Erro ao restaurar janela:', err);
    }
  }

  /**
   * Traz a janela para frente
   */
  async bringToFront(): Promise<void> {
    if (!this.page) return;
    await this.page.bringToFront();
    console.log('[SEI] Janela trazida para frente');
  }

  /**
   * Obtém as dimensões e posição da janela
   */
  async getWindowBounds(): Promise<{
    left: number;
    top: number;
    width: number;
    height: number;
    windowState: string;
  } | null> {
    if (!this.page) return null;
    try {
      const cdp = await this.page.context().newCDPSession(this.page);
      const { windowId } = await cdp.send('Browser.getWindowForTarget');
      const result = await cdp.send('Browser.getWindowBounds', { windowId });
      return result.bounds as {
        left: number;
        top: number;
        width: number;
        height: number;
        windowState: string;
      };
    } catch (err) {
      console.warn('[SEI] Erro ao obter bounds da janela:', err);
      return null;
    }
  }

  /**
   * Define as dimensões e posição da janela
   */
  async setWindowBounds(bounds: {
    left?: number;
    top?: number;
    width?: number;
    height?: number;
    windowState?: 'normal' | 'minimized' | 'maximized' | 'fullscreen';
  }): Promise<void> {
    if (!this.page) return;
    try {
      const cdp = await this.page.context().newCDPSession(this.page);
      const { windowId } = await cdp.send('Browser.getWindowForTarget');
      await cdp.send('Browser.setWindowBounds', {
        windowId,
        bounds,
      });
      console.log('[SEI] Bounds da janela atualizados');
    } catch (err) {
      console.warn('[SEI] Erro ao definir bounds da janela:', err);
    }
  }

  /**
   * Maximiza a janela do navegador
   */
  async maximizeWindow(): Promise<void> {
    await this.setWindowBounds({ windowState: 'maximized' });
    console.log('[SEI] Janela maximizada');
  }

  /**
   * Coloca a janela em tela cheia
   */
  async fullscreenWindow(): Promise<void> {
    await this.setWindowBounds({ windowState: 'fullscreen' });
    console.log('[SEI] Janela em tela cheia');
  }

  /**
   * Verifica se a sessão ainda está ativa
   */
  async isSessionActive(): Promise<boolean> {
    try {
      return await this.isLoggedIn();
    } catch {
      return false;
    }
  }

  /**
   * Obtém o contexto atual do browser
   */
  getContext(): BrowserContext | null {
    return this.context;
  }

  /**
   * Obtém o browser atual
   */
  getBrowser(): Browser | null {
    return this.browser;
  }

  /** Aguarda carregamento */
  private async waitForLoad(): Promise<void> {
    const page = this.getPage();
    await page.waitForLoadState('networkidle');

    // Aguarda spinner desaparecer usando locator semantico
    try {
      const spinner = page.locator('[class*="Carregando"], [class*="loading"], [aria-busy="true"]');
      await spinner.waitFor({ state: 'hidden', timeout: 5000 });
    } catch {
      // Ignora se nao encontrar spinner
    }
  }

  /** Navega para URL */
  async navigate(path: string): Promise<void> {
    const page = this.getPage();
    const url = path.startsWith('http') ? path : `${this.baseUrl}${path}`;
    await page.goto(url);
    await this.waitForLoad();
  }

  // ============================================
  // Helpers para Locators Semanticos
  // ============================================

  /** Obtem locator para campo de texto por label */
  private getTextbox(page: Page, namePattern: RegExp): Locator {
    return page.getByRole('textbox', { name: namePattern });
  }

  /** Obtem locator para botao por nome */
  private getButton(page: Page, namePattern: RegExp): Locator {
    return page.getByRole('button', { name: namePattern });
  }

  /** Obtem locator para link por nome */
  private getLink(page: Page, namePattern: RegExp): Locator {
    return page.getByRole('link', { name: namePattern });
  }

  /** Obtem locator para combobox/select */
  private getCombobox(page: Page, namePattern?: RegExp): Locator {
    if (namePattern) {
      return page.getByRole('combobox', { name: namePattern });
    }
    return page.getByRole('combobox');
  }

  /** Obtem locator para checkbox por nome */
  private getCheckbox(page: Page, namePattern: RegExp): Locator {
    return page.getByRole('checkbox', { name: namePattern });
  }

  /** Obtem locator para radio button por nome */
  private getRadio(page: Page, namePattern: RegExp): Locator {
    return page.getByRole('radio', { name: namePattern });
  }

  /** Obtem frame locator para iframe da arvore */
  private getTreeFrame(page: Page): FrameLocator {
    return page.frameLocator('iframe[name="ifrArvore"]');
  }

  /** Obtem frame locator para iframe de visualizacao */
  private getViewFrame(page: Page): FrameLocator {
    return page.frameLocator('iframe[name="ifrVisualizacao"], iframe[name="ifrConteudo"]');
  }

  /** Obtem frame locator para editor */
  private getEditorFrame(page: Page): FrameLocator {
    return page.frameLocator('iframe[name="ifrArvoreHtml"], #ifrArvoreHtml');
  }

  // ============================================
  // Smart Helpers (ARIA primeiro, CSS fallback)
  // ============================================

  /** Clica em elemento: tenta ARIA primeiro, fallback CSS */
  private async clickSmart(
    target: Page | FrameLocator,
    aria: { role: 'button' | 'link' | 'checkbox' | 'radio' | 'menuitem' | 'tab'; name: RegExp },
    cssFallback?: string
  ): Promise<void> {
    try {
      await target.getByRole(aria.role, { name: aria.name }).first().click();
    } catch {
      if (cssFallback) {
        if ('click' in target) {
          await (target as Page).click(cssFallback);
        } else {
          await (target as FrameLocator).locator(cssFallback).first().click();
        }
      } else {
        throw new Error(`Elemento não encontrado: ${aria.role} "${aria.name}"`);
      }
    }
  }

  /** Preenche campo: tenta ARIA primeiro, fallback CSS */
  private async fillSmart(
    target: Page | FrameLocator,
    aria: { role?: 'textbox' | 'combobox' | 'searchbox'; name?: RegExp; nth?: number },
    value: string,
    cssFallback?: string
  ): Promise<void> {
    try {
      let locator: Locator;
      if (aria.role && aria.name) {
        locator = target.getByRole(aria.role, { name: aria.name });
      } else if (aria.role) {
        locator = target.getByRole(aria.role);
      } else {
        throw new Error('role é obrigatório');
      }

      if (aria.nth !== undefined) {
        locator = locator.nth(aria.nth);
      } else {
        locator = locator.first();
      }

      await locator.fill(value);
    } catch {
      if (cssFallback) {
        if ('fill' in target) {
          await (target as Page).fill(cssFallback, value);
        } else {
          await (target as FrameLocator).locator(cssFallback).first().fill(value);
        }
      } else {
        throw new Error(`Campo não encontrado: ${aria.role} "${aria.name}"`);
      }
    }
  }

  /** Seleciona opção: tenta ARIA primeiro, fallback CSS */
  private async selectSmart(
    target: Page | FrameLocator,
    aria: { role?: 'combobox' | 'listbox'; name?: RegExp; nth?: number },
    value: string | { label: string },
    cssFallback?: string
  ): Promise<void> {
    try {
      let locator: Locator;
      if (aria.role && aria.name) {
        locator = target.getByRole(aria.role, { name: aria.name });
      } else if (aria.role) {
        locator = target.getByRole(aria.role);
      } else {
        throw new Error('role é obrigatório');
      }

      if (aria.nth !== undefined) {
        locator = locator.nth(aria.nth);
      } else {
        locator = locator.first();
      }

      await locator.selectOption(value);
    } catch {
      if (cssFallback) {
        if ('selectOption' in target) {
          await (target as Page).selectOption(cssFallback, value);
        } else {
          await (target as FrameLocator).locator(cssFallback).first().selectOption(value);
        }
      } else {
        throw new Error(`Select não encontrado: ${aria.role} "${aria.name}"`);
      }
    }
  }

  /** Marca checkbox/radio: tenta ARIA primeiro, fallback CSS */
  private async checkSmart(
    target: Page | FrameLocator,
    aria: { role: 'checkbox' | 'radio'; name: RegExp },
    cssFallback?: string
  ): Promise<void> {
    try {
      await target.getByRole(aria.role, { name: aria.name }).first().check();
    } catch {
      if (cssFallback) {
        if ('check' in target) {
          await (target as Page).check(cssFallback);
        } else {
          await (target as FrameLocator).locator(cssFallback).first().check();
        }
      } else {
        throw new Error(`${aria.role} não encontrado: "${aria.name}"`);
      }
    }
  }

  /** Aguarda elemento: tenta ARIA primeiro, fallback CSS */
  private async waitForSmart(
    target: Page | FrameLocator,
    aria: { role: string; name?: RegExp },
    cssFallback?: string,
    options?: { timeout?: number; state?: 'visible' | 'hidden' | 'attached' | 'detached' }
  ): Promise<void> {
    try {
      const locator = aria.name
        ? target.getByRole(aria.role as any, { name: aria.name })
        : target.getByRole(aria.role as any);
      await locator.first().waitFor({ timeout: options?.timeout ?? 5000, state: options?.state ?? 'visible' });
    } catch {
      if (cssFallback) {
        const locator = 'locator' in target
          ? (target as Page).locator(cssFallback)
          : (target as FrameLocator).locator(cssFallback);
        await locator.first().waitFor({ timeout: options?.timeout ?? 5000, state: options?.state ?? 'visible' });
      } else {
        throw new Error(`Elemento não encontrado: ${aria.role} "${aria.name}"`);
      }
    }
  }

  /** Obtém texto de elemento: tenta ARIA primeiro, fallback CSS */
  private async getTextSmart(
    target: Page | FrameLocator,
    aria: { role: string; name?: RegExp },
    cssFallback?: string
  ): Promise<string | null> {
    try {
      const locator = aria.name
        ? target.getByRole(aria.role as any, { name: aria.name })
        : target.getByRole(aria.role as any);
      return await locator.first().textContent();
    } catch {
      if (cssFallback) {
        const locator = 'locator' in target
          ? (target as Page).locator(cssFallback)
          : (target as FrameLocator).locator(cssFallback);
        return await locator.first().textContent();
      }
      return null;
    }
  }

  /** Verifica se elemento existe: tenta ARIA primeiro, fallback CSS */
  private async existsSmart(
    target: Page | FrameLocator,
    aria: { role: string; name?: RegExp },
    cssFallback?: string,
    timeout = 2000
  ): Promise<boolean> {
    try {
      const locator = aria.name
        ? target.getByRole(aria.role as any, { name: aria.name })
        : target.getByRole(aria.role as any);
      await locator.first().waitFor({ timeout, state: 'visible' });
      return true;
    } catch {
      if (cssFallback) {
        try {
          const locator = 'locator' in target
            ? (target as Page).locator(cssFallback)
            : (target as FrameLocator).locator(cssFallback);
          await locator.first().waitFor({ timeout, state: 'visible' });
          return true;
        } catch {
          return false;
        }
      }
      return false;
    }
  }

  // ============================================
  // Autenticacao
  // ============================================

  /** Realiza login no SEI */
  async login(usuario?: string, senha?: string, orgao?: string): Promise<boolean> {
    const page = this.getPage();
    const creds = this.config.browser ?? {};

    await this.navigate('/sei/');

    // Verifica se já está logado
    if (await this.existsSmart(page, { role: 'link', name: /sair|logout/i }, '#lnkUsuarioSistema, .usuario-logado')) {
      return true;
    }

    // Preenche formulário
    const userValue = usuario ?? creds.usuario ?? '';
    const passValue = senha ?? creds.senha ?? '';

    // Campo usuário (SEI MG: textbox SEM nome ARIA, usar primeiro)
    await this.fillSmart(page, { role: 'textbox', nth: 0 }, userValue, SEI_SELECTORS.login.usuario);

    // Campo senha (SEI MG: textbox com nome "Senha")
    await this.fillSmart(page, { role: 'textbox', name: /senha/i }, passValue, 'input#pwdSenha.masked, input#pwdSenha');

    // Seleciona órgão (SEI MG: combobox SEM nome ARIA)
    const orgaoValue = orgao ?? creds.orgao;
    if (orgaoValue) {
      await this.selectSmart(page, { role: 'combobox', nth: 0 }, { label: orgaoValue }, SEI_SELECTORS.login.orgao);
    }

    // Submete (botão com nome ARIA "Acessar")
    await this.clickSmart(page, { role: 'button', name: /acessar|entrar|login/i }, SEI_SELECTORS.login.submit);

    await this.waitForLoad();

    // Verifica sucesso
    return await this.existsSmart(page, { role: 'link', name: /sair|logout/i }, '#lnkUsuarioSistema', 5000);
  }

  /** Verifica se está logado */
  async isLoggedIn(): Promise<boolean> {
    const page = this.getPage();
    return await this.existsSmart(page, { role: 'link', name: /sair|logout/i }, '#lnkUsuarioSistema, .usuario-logado');
  }

  /** Realiza logout */
  async logout(): Promise<void> {
    const page = this.getPage();
    try {
      await this.clickSmart(page, { role: 'link', name: /sair|logout/i }, SEI_SELECTORS.nav.logout);
      await this.waitForLoad();
    } catch {
      // Ignora se ja estiver deslogado
    }
  }

  // ============================================
  // Processos
  // ============================================

  /** Abre processo pelo numero */
  async openProcess(numeroProcesso: string): Promise<boolean> {
    const page = this.getPage();

    // Pesquisa rapida usando smart helper
    await this.fillSmart(page, { role: 'textbox', name: /pesquis/i }, numeroProcesso, SEI_SELECTORS.nav.pesquisa);

    // Clica no botao de pesquisa
    try {
      await this.clickSmart(page, { role: 'button', name: /pesquis/i }, SEI_SELECTORS.nav.btnPesquisa);
    } catch {
      await this.clickSmart(page, { role: 'link', name: /pesquis/i }, SEI_SELECTORS.nav.btnPesquisa);
    }

    await this.waitForLoad();

    // Verifica se abriu o processo - aguarda arvore de documentos
    return await this.existsSmart(page, { role: 'tree' }, '#divArvore, #arvore, [class*="arvore"]', 5000);
  }

  /** Lista documentos do processo atual */
  async listDocuments(): Promise<Array<{ id: string; titulo: string; tipo: string }>> {
    const page = this.getPage();
    const docs: Array<{ id: string; titulo: string; tipo: string }> = [];

    try {
      // Tenta usar frame da arvore com locators semanticos
      const frame = this.getTreeFrame(page);

      // Busca todos os links que parecem documentos (tem numero entre parenteses)
      const docLinks = await frame.getByRole('link').filter({ hasText: /\(\d+\)/ }).all();

      for (const link of docLinks) {
        const href = (await link.getAttribute('href')) ?? '';
        const text = (await link.textContent()) ?? '';

        // Extrai ID do documento da URL
        const idMatch = href.match(/id_documento=(\d+)/);
        const id = idMatch?.[1] ?? '';

        // Extrai tipo e titulo do texto
        const parts = text.split(/\s+/);
        const tipo = parts[0] ?? '';
        const titulo = parts.slice(1).join(' ') || tipo;

        if (id) {
          docs.push({ id, titulo, tipo });
        }
      }
    } catch {
      // Fallback: tenta na pagina principal com seletores CSS
      const links = await page.$$(SEI_SELECTORS.processTree.documents);

      for (const link of links) {
        const href = (await link.getAttribute('href')) ?? '';
        const text = (await link.textContent()) ?? '';

        const idMatch = href.match(/id_documento=(\d+)/);
        const id = idMatch?.[1] ?? '';

        const parts = text.split(/\s+/);
        const tipo = parts[0] ?? '';
        const titulo = parts.slice(1).join(' ') || tipo;

        if (id) {
          docs.push({ id, titulo, tipo });
        }
      }
    }

    return docs;
  }

  /** Tramita processo para unidades */
  async forwardProcess(options: ForwardOptions): Promise<boolean> {
    const page = this.getPage();

    // Clica em Enviar Processo
    await this.clickSmart(page, { role: 'link', name: /enviar processo/i }, SEI_SELECTORS.processActions.enviarProcesso);
    await this.waitForLoad();

    // Adiciona unidades de destino
    for (const unidade of options.unidadesDestino) {
      await this.fillSmart(page, { role: 'textbox', name: /unidade/i }, unidade, SEI_SELECTORS.forward.unidadeInput);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(500);
    }

    // Opcoes - usando checkboxes
    if (options.manterAberto !== undefined) {
      try {
        const checkbox = page.getByRole('checkbox', { name: /manter.*aberto/i })
          .or(page.locator(SEI_SELECTORS.forward.manterAberto));
        const isChecked = await checkbox.first().isChecked();
        if (isChecked !== options.manterAberto) {
          await checkbox.first().click();
        }
      } catch {
        // Ignora se checkbox nao existir
      }
    }

    if (options.enviarEmailNotificacao !== undefined) {
      try {
        const checkbox = page.getByRole('checkbox', { name: /e-?mail|notifica/i })
          .or(page.locator(SEI_SELECTORS.forward.enviarEmail));
        const isChecked = await checkbox.first().isChecked();
        if (isChecked !== options.enviarEmailNotificacao) {
          await checkbox.first().click();
        }
      } catch {
        // Ignora se checkbox nao existir
      }
    }

    // Submete
    await this.clickSmart(page, { role: 'button', name: /enviar/i }, SEI_SELECTORS.forward.enviar);
    await this.waitForLoad();

    // Verifica sucesso
    return await this.existsSmart(page, { role: 'alert' }, '.msgSucesso, .alert-success, [class*="sucesso"]', 5000);
  }

  /** Conclui processo */
  async concludeProcess(): Promise<boolean> {
    const page = this.getPage();

    await this.clickSmart(page, { role: 'link', name: /concluir.*processo/i }, SEI_SELECTORS.processActions.concluirProcesso);
    await this.waitForLoad();

    // Confirma se necessario
    try {
      await this.clickSmart(page, { role: 'button', name: /confirmar|sim|ok/i });
      await this.waitForLoad();
    } catch {
      // Sem confirmacao necessaria
    }

    return true;
  }

  /** Reabre processo */
  async reopenProcess(): Promise<boolean> {
    const page = this.getPage();

    await this.clickSmart(page, { role: 'link', name: /reabrir.*processo/i }, SEI_SELECTORS.processActions.reabrirProcesso);
    await this.waitForLoad();

    return true;
  }

  /** Cria novo processo */
  async createProcess(options: {
    tipoProcedimento: string;
    especificacao: string;
    assuntos?: string[];
    interessados?: string[];
    observacao?: string;
    nivelAcesso?: 0 | 1 | 2;
    hipoteseLegal?: string;
  }): Promise<{ id: string; numero: string } | null> {
    const page = this.getPage();

    // Navega para iniciar processo
    await this.clickSmart(page, { role: 'link', name: /iniciar.*processo/i }, SEI_SELECTORS.nav.iniciarProcesso);
    await this.waitForLoad();

    // Pesquisa e seleciona o tipo de processo
    try {
      await this.fillSmart(page, { role: 'textbox', name: /pesquis.*tipo|tipo.*procedimento/i }, options.tipoProcedimento, SEI_SELECTORS.newProcess.tipoSearch);
      await page.waitForTimeout(500);
    } catch {
      // Ignora se nao tiver campo de pesquisa
    }

    // Tenta encontrar o tipo na lista
    let tipoEncontrado = false;
    try {
      if (await this.existsSmart(page, { role: 'link', name: new RegExp(options.tipoProcedimento, 'i') }, undefined, 2000)) {
        await this.clickSmart(page, { role: 'link', name: new RegExp(options.tipoProcedimento, 'i') });
        await this.waitForLoad();
        tipoEncontrado = true;
      }
    } catch {
      // Tenta fallback
    }

    // Se nao encontrou via link, tenta via select
    if (!tipoEncontrado) {
      try {
        await this.selectSmart(page, { role: 'combobox', name: /tipo.*procedimento/i }, { label: options.tipoProcedimento }, SEI_SELECTORS.newProcess.tipo);
        await this.waitForLoad();
      } catch {
        // Tenta por valor parcial
        try {
          const select = await page.$(SEI_SELECTORS.newProcess.tipo);
          if (select) {
            const optionValues = await select.$$eval('option', (opts) =>
              opts.map((o) => ({ value: o.value, text: o.textContent }))
            );
            const match = optionValues.find((o) =>
              o.text?.toLowerCase().includes(options.tipoProcedimento.toLowerCase())
            );
            if (match?.value) {
              await page.selectOption(SEI_SELECTORS.newProcess.tipo, match.value);
              await this.waitForLoad();
            }
          }
        } catch {
          // Ignora
        }
      }
    }

    // Preenche especificacao
    await this.fillSmart(page, { role: 'textbox', name: /especifica[cç][aã]o/i }, options.especificacao, SEI_SELECTORS.newProcess.especificacao);

    // Adiciona assuntos (se houver campo)
    if (options.assuntos?.length) {
      for (const assunto of options.assuntos) {
        try {
          // Clica no botao de pesquisar assunto
          await this.clickSmart(page, { role: 'button', name: /pesquis.*assunto|adicionar.*assunto/i });
          await this.waitForLoad();

          // Pesquisa o assunto
          await this.fillSmart(page, { role: 'textbox', name: /palavras|pesquis/i }, assunto);
          await this.clickSmart(page, { role: 'button', name: /pesquis/i });
          await this.waitForLoad();

          // Seleciona o primeiro resultado
          const resultado = page.getByRole('row').first().getByRole('link');
          await resultado.click();
          await this.waitForLoad();
        } catch {
          // Ignora erro de assunto
        }
      }
    }

    // Adiciona interessados
    if (options.interessados?.length) {
      for (const interessado of options.interessados) {
        try {
          await this.fillSmart(page, { role: 'textbox', name: /interessado/i }, interessado);
          await page.waitForTimeout(300);

          // Aguarda autocomplete e seleciona
          const autocomplete = page.locator('.autocomplete-item, .infraAjaxListaItens div').first();
          if (await autocomplete.isVisible({ timeout: 1000 })) {
            await autocomplete.click();
          } else {
            await page.keyboard.press('Tab');
          }

          // Clica no botao adicionar se existir
          try {
            await this.clickSmart(page, { role: 'button', name: /adicionar.*interessado/i });
          } catch {
            // Sem botao de adicionar
          }

          await page.waitForTimeout(200);
        } catch {
          // Ignora erro de interessado
        }
      }
    }

    // Observacao
    if (options.observacao) {
      try {
        await this.fillSmart(page, { role: 'textbox', name: /observa[cç]/i }, options.observacao, SEI_SELECTORS.newProcess.observacao);
      } catch {
        // Campo pode nao existir
      }
    }

    // Nivel de acesso
    if (options.nivelAcesso !== undefined) {
      const nivelLabel = options.nivelAcesso === 0 ? /p[uú]blico/i
        : options.nivelAcesso === 1 ? /restrito/i
        : /sigiloso/i;
      const selector = options.nivelAcesso === 0
        ? SEI_SELECTORS.newProcess.nivelAcesso.publico
        : options.nivelAcesso === 1
          ? SEI_SELECTORS.newProcess.nivelAcesso.restrito
          : SEI_SELECTORS.newProcess.nivelAcesso.sigiloso;

      try {
        await this.clickSmart(page, { role: 'radio', name: nivelLabel }, selector);

        // Se restrito/sigiloso, seleciona hipotese legal
        if ((options.nivelAcesso === 1 || options.nivelAcesso === 2) && options.hipoteseLegal) {
          await this.selectSmart(page, { role: 'combobox', name: /hip[oó]tese.*legal/i }, { label: options.hipoteseLegal }, SEI_SELECTORS.newProcess.hipoteseLegal);
        }
      } catch {
        // Ignora erro
      }
    }

    // Salva o processo
    await this.clickSmart(page, { role: 'button', name: /salvar|cadastrar|gerar/i }, SEI_SELECTORS.newProcess.salvar);
    await this.waitForLoad();

    // Verifica se foi criado com sucesso
    try {
      // Aguarda redirecionamento para a pagina do processo
      await this.waitForSmart(page, { role: 'tree' }, '#divArvore, #arvore', { timeout: 10000 });

      // Extrai numero e ID do processo
      const url = page.url();
      const idMatch = url.match(/id_procedimento=(\d+)/);

      // Extrai numero formatado da pagina
      const numeroElement = page.locator('#txtNumeroProcesso, .numero-processo, #anchor0').first();
      const numero = (await numeroElement.textContent())?.trim() ?? '';

      if (idMatch) {
        return {
          id: idMatch[1],
          numero: numero,
        };
      }
    } catch {
      // Verifica se ha mensagem de erro
      const erro = page.locator('.infraException, .msgErro, .alert-danger').first();
      if (await erro.isVisible({ timeout: 1000 })) {
        const mensagem = await erro.textContent();
        throw new Error(`Erro ao criar processo: ${mensagem}`);
      }
    }

    return null;
  }

  /** Gera PDF do processo */
  async downloadProcessPdf(): Promise<string | null> {
    const page = this.getPage();

    // Inicia download
    const downloadPromise = page.waitForEvent('download');

    await this.clickSmart(page, { role: 'link', name: /gerar.*pdf|download.*pdf/i }, SEI_SELECTORS.processActions.gerarPdf);

    try {
      const download = await downloadPromise;
      const path = await download.path();
      return path;
    } catch {
      return null;
    }
  }

  // ============================================
  // Documentos
  // ============================================

  /** Abre documento pelo ID */
  async openDocument(idDocumento: string): Promise<boolean> {
    const page = this.getPage();

    try {
      // Tenta na arvore (frame) primeiro
      const frame = this.getTreeFrame(page);
      const docLink = frame.getByRole('link').filter({ hasText: new RegExp(`\\(${idDocumento}\\)|${idDocumento}`) });

      if (await docLink.first().isVisible({ timeout: 2000 })) {
        await docLink.first().click();
        await this.waitForLoad();
        return true;
      }
    } catch {
      // Fallback para seletores CSS
    }

    // Fallback: procura link na pagina
    const links = await page.$$(SEI_SELECTORS.processTree.documents);

    for (const link of links) {
      const href = (await link.getAttribute('href')) ?? '';
      if (href.includes(`id_documento=${idDocumento}`) || href.includes(idDocumento)) {
        await link.click();
        await this.waitForLoad();
        return true;
      }
    }

    return false;
  }

  /** Cria documento interno */
  async createDocument(options: CreateDocumentOptions): Promise<string | null> {
    const page = this.getPage();

    // Clica em Incluir Documento
    await this.clickSmart(page, { role: 'link', name: /incluir.*documento/i }, SEI_SELECTORS.processActions.incluirDocumento);
    await this.waitForLoad();

    // Seleciona tipo de documento
    try {
      await this.clickSmart(page, { role: 'link', name: new RegExp(options.idSerie, 'i') });
      await this.waitForLoad();
    } catch {
      // Fallback CSS
      const tipoLinks = await page.$$(SEI_SELECTORS.newDocument.tipoLinks);
      for (const link of tipoLinks) {
        const text = (await link.textContent()) ?? '';
        if (text.toLowerCase().includes(options.idSerie.toLowerCase())) {
          await link.click();
          await this.waitForLoad();
          break;
        }
      }
    }

    // Preenche campos
    if (options.descricao) {
      await this.fillSmart(page, { role: 'textbox', name: /descri[cç][aã]o/i }, options.descricao, SEI_SELECTORS.newDocument.descricao);
    }

    if (options.numero) {
      try {
        await this.fillSmart(page, { role: 'textbox', name: /n[uú]mero/i }, options.numero, SEI_SELECTORS.newDocument.numero);
      } catch {
        // Campo nao disponivel para este tipo
      }
    }

    // Interessados
    if (options.interessados?.length) {
      for (const interessado of options.interessados) {
        try {
          await this.fillSmart(page, { role: 'textbox', name: /interessado/i }, interessado, SEI_SELECTORS.newDocument.interessadoInput);
          await page.keyboard.press('Tab');
          await page.waitForTimeout(300);
          try {
            await this.clickSmart(page, { role: 'button', name: /adicionar/i });
          } catch {
            // Sem botao de adicionar
          }
        } catch {
          // Campo nao disponivel
        }
      }
    }

    // Destinatarios
    if (options.destinatarios?.length) {
      for (const dest of options.destinatarios) {
        try {
          await this.fillSmart(page, { role: 'textbox', name: /destinat[aá]rio/i }, dest, SEI_SELECTORS.newDocument.destinatarioInput);
          await page.keyboard.press('Tab');
          await page.waitForTimeout(300);
          await this.clickSmart(page, { role: 'button', name: /adicionar/i }, SEI_SELECTORS.newDocument.destinatarioAdd);
        } catch {
          // Campo nao disponivel
        }
      }
    }

    // Observacao
    if (options.observacao) {
      await this.fillSmart(page, { role: 'textbox', name: /observa[cç]/i }, options.observacao, SEI_SELECTORS.newDocument.observacao);
    }

    // Nivel de acesso
    if (options.nivelAcesso !== undefined) {
      const nivelLabel = options.nivelAcesso === 0 ? /p[uú]blico/i
        : options.nivelAcesso === 1 ? /restrito/i
        : /sigiloso/i;
      const selector = options.nivelAcesso === 0
        ? SEI_SELECTORS.newDocument.nivelAcesso.publico
        : options.nivelAcesso === 1
          ? SEI_SELECTORS.newDocument.nivelAcesso.restrito
          : SEI_SELECTORS.newDocument.nivelAcesso.sigiloso;

      await this.clickSmart(page, { role: 'radio', name: nivelLabel }, selector);

      if ((options.nivelAcesso === 1 || options.nivelAcesso === 2) && options.hipoteseLegal) {
        await this.selectSmart(page, { role: 'combobox', name: /hip[oó]tese/i }, { label: options.hipoteseLegal }, SEI_SELECTORS.newDocument.hipoteseLegal);
      }
    }

    // Salva
    await this.clickSmart(page, { role: 'button', name: /salvar|confirmar|gerar/i }, SEI_SELECTORS.newDocument.salvar);
    await this.waitForLoad();

    // Preenche conteudo se fornecido
    if (options.conteudoHtml) {
      try {
        // Aguarda editor carregar
        const editorFrame = this.getEditorFrame(page);
        const editorBody = editorFrame.locator('body');
        await editorBody.fill(options.conteudoHtml);

        // Salva conteudo
        await this.clickSmart(page, { role: 'button', name: /salvar/i });
        await this.waitForLoad();
      } catch {
        // Editor nao disponivel
      }
    }

    // Retorna ID do documento criado (da URL)
    const url = page.url();
    const idMatch = url.match(/id_documento=(\d+)/);
    return idMatch?.[1] ?? null;
  }

  /** Upload de documento externo */
  async uploadDocument(
    nomeArquivo: string,
    conteudoBase64: string,
    options: Partial<CreateDocumentOptions> = {}
  ): Promise<string | null> {
    const page = this.getPage();

    // Clica em Incluir Documento
    await this.clickSmart(page, { role: 'link', name: /incluir.*documento/i }, SEI_SELECTORS.processActions.incluirDocumento);
    await this.waitForLoad();

    // Seleciona tipo "Documento Externo" ou o especificado
    const tipoDoc = options.idSerie ?? 'Externo';
    try {
      await this.clickSmart(page, { role: 'link', name: new RegExp(tipoDoc, 'i') });
      await this.waitForLoad();
    } catch {
      const tipoLinks = await page.$$(SEI_SELECTORS.newDocument.tipoLinks);
      for (const link of tipoLinks) {
        const text = (await link.textContent()) ?? '';
        if (text.toLowerCase().includes(tipoDoc.toLowerCase())) {
          await link.click();
          await this.waitForLoad();
          break;
        }
      }
    }

    // Decodifica Base64 e cria arquivo temporario
    const buffer = Buffer.from(conteudoBase64, 'base64');
    const tempPath = `/tmp/${nomeArquivo}`;
    const fs = await import('fs/promises');
    await fs.writeFile(tempPath, buffer);

    // Upload
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(tempPath);

    // Preenche campos opcionais
    if (options.descricao) {
      await this.fillSmart(page, { role: 'textbox', name: /descri[cç][aã]o/i }, options.descricao, SEI_SELECTORS.newDocument.descricao);
    }

    if (options.observacao) {
      await this.fillSmart(page, { role: 'textbox', name: /observa[cç]/i }, options.observacao, SEI_SELECTORS.newDocument.observacao);
    }

    // Nivel de acesso
    if (options.nivelAcesso !== undefined) {
      const nivelLabel = options.nivelAcesso === 0 ? /p[uú]blico/i
        : options.nivelAcesso === 1 ? /restrito/i
        : /sigiloso/i;
      const selector = options.nivelAcesso === 0
        ? SEI_SELECTORS.newDocument.nivelAcesso.publico
        : options.nivelAcesso === 1
          ? SEI_SELECTORS.newDocument.nivelAcesso.restrito
          : SEI_SELECTORS.newDocument.nivelAcesso.sigiloso;

      await this.clickSmart(page, { role: 'radio', name: nivelLabel }, selector);
    }

    // Salva
    await this.clickSmart(page, { role: 'button', name: /salvar|confirmar/i }, SEI_SELECTORS.upload.salvar);
    await this.waitForLoad();

    // Limpa arquivo temporario
    await fs.unlink(tempPath).catch(() => {});

    // Retorna ID do documento criado
    const url = page.url();
    const idMatch = url.match(/id_documento=(\d+)/);
    return idMatch?.[1] ?? null;
  }

  /** Assina documento */
  async signDocument(senha: string, cargo?: string): Promise<boolean> {
    const page = this.getPage();

    // Preenche senha
    await this.fillSmart(page, { role: 'textbox', name: /senha/i }, senha, SEI_SELECTORS.signature.senha);

    // Seleciona cargo se fornecido
    if (cargo) {
      try {
        await this.selectSmart(page, { role: 'combobox', name: /cargo|fun[cç][aã]o/i }, { label: cargo }, SEI_SELECTORS.signature.cargo);
      } catch {
        // Sem select de cargo
      }
    }

    // Assina
    await this.clickSmart(page, { role: 'button', name: /assinar/i }, SEI_SELECTORS.signature.assinar);
    await this.waitForLoad();

    // Verifica sucesso
    return await this.existsSmart(page, { role: 'alert' }, '.msgSucesso, .alert-success', 5000);
  }

  // ============================================
  // Listagens (via navegacao)
  // ============================================

  /** Lista tipos de processo disponiveis */
  async listProcessTypes(): Promise<Array<{ id: string; nome: string }>> {
    const page = this.getPage();

    await this.clickSmart(page, { role: 'link', name: /iniciar.*processo/i }, SEI_SELECTORS.nav.iniciarProcesso);
    await this.waitForLoad();

    const tipos: Array<{ id: string; nome: string }> = [];

    // Tenta extrair do select
    try {
      const select = page.getByRole('combobox', { name: /tipo/i }).or(page.locator(SEI_SELECTORS.newProcess.tipo));
      const selectEl = await select.first().elementHandle();
      if (selectEl) {
        const options = await selectEl.$$eval('option', (opts) =>
          opts.filter((o) => o.value).map((o) => ({ id: o.value, nome: o.textContent?.trim() ?? '' }))
        );
        return options;
      }
    } catch {
      // Tenta extrair dos links
    }

    // Tenta extrair dos links
    const links = await page.getByRole('link').filter({ hasText: /.+/ }).all();
    for (const link of links) {
      const href = (await link.getAttribute('href')) ?? '';
      const idMatch = href.match(/id_tipo_procedimento=(\d+)/);
      const nome = (await link.textContent())?.trim() ?? '';

      if (idMatch && nome) {
        tipos.push({ id: idMatch[1], nome });
      }
    }

    return tipos;
  }

  /** Lista tipos de documento (series) */
  async listDocumentTypes(): Promise<Array<{ id: string; nome: string }>> {
    const page = this.getPage();

    // Precisa estar em um processo para ver tipos de documento
    await this.clickSmart(page, { role: 'link', name: /incluir.*documento/i }, SEI_SELECTORS.processActions.incluirDocumento);
    await this.waitForLoad();

    const tipos: Array<{ id: string; nome: string }> = [];

    // Tenta extrair do select
    try {
      const select = page.getByRole('combobox', { name: /tipo|s[eé]rie/i }).or(page.locator(SEI_SELECTORS.newDocument.tipoSelect));
      const selectEl = await select.first().elementHandle();
      if (selectEl) {
        const options = await selectEl.$$eval('option', (opts) =>
          opts.filter((o) => o.value).map((o) => ({ id: o.value, nome: o.textContent?.trim() ?? '' }))
        );
        return options;
      }
    } catch {
      // Tenta extrair dos links
    }

    // Tenta extrair dos links
    const links = await page.$$(SEI_SELECTORS.newDocument.tipoLinks);
    for (const link of links) {
      const href = (await link.getAttribute('href')) ?? '';
      const idMatch = href.match(/id_serie=(\d+)/);
      const nome = (await link.textContent())?.trim() ?? '';

      if (idMatch && nome) {
        tipos.push({ id: idMatch[1], nome });
      }
    }

    // Fecha modal se aberto
    try {
      await this.clickSmart(page, { role: 'button', name: /fechar|cancelar/i }, SEI_SELECTORS.common.close);
    } catch {
      await page.goBack();
    }

    return tipos;
  }

  /** Lista unidades do orgao */
  async listUnits(): Promise<Array<{ id: string; sigla: string; descricao: string }>> {
    const page = this.getPage();
    const unidades: Array<{ id: string; sigla: string; descricao: string }> = [];

    // Extrai do select de unidades na navegacao
    try {
      const select = page.getByRole('combobox', { name: /unidade/i }).or(page.locator(SEI_SELECTORS.nav.unidade));
      const selectEl = await select.first().elementHandle();
      if (selectEl) {
        const options = await selectEl.$$eval('option', (opts) =>
          opts.filter((o) => o.value).map((o) => ({
            id: o.value,
            sigla: o.textContent?.trim() ?? '',
            descricao: o.textContent?.trim() ?? '',
          }))
        );
        return options;
      }
    } catch {
      // Ignora
    }

    return unidades;
  }

  /** Consulta andamentos/historico do processo */
  async listAndamentos(numeroProcesso?: string): Promise<Array<{
    data: string;
    unidade: string;
    usuario: string;
    descricao: string;
  }>> {
    const page = this.getPage();

    // Se passou numero, abre o processo
    if (numeroProcesso) {
      await this.openProcess(numeroProcesso);
    }

    // Clica em consultar andamento
    await this.clickSmart(page, { role: 'link', name: /consultar.*andamento|hist[oó]rico/i }, SEI_SELECTORS.processActions.consultarAndamento);
    await this.waitForLoad();

    const andamentos: Array<{
      data: string;
      unidade: string;
      usuario: string;
      descricao: string;
    }> = [];

    // Usa locator semantico para tabela
    const rows = await page.getByRole('row').all();
    for (const row of rows.slice(1)) { // Pula cabecalho
      try {
        const cells = await row.getByRole('cell').all();
        if (cells.length >= 4) {
          andamentos.push({
            data: (await cells[0]?.textContent())?.trim() ?? '',
            unidade: (await cells[1]?.textContent())?.trim() ?? '',
            usuario: (await cells[2]?.textContent())?.trim() ?? '',
            descricao: (await cells[3]?.textContent())?.trim() ?? '',
          });
        }
      } catch {
        // Ignora linhas invalidas
      }
    }

    return andamentos;
  }

  /** Consulta detalhes do processo */
  async getProcessDetails(numeroProcesso?: string): Promise<{
    id: string;
    numero: string;
    tipo: string;
    especificacao: string;
    interessados: string[];
    unidadesAbertas: string[];
    dataAutuacao: string;
  } | null> {
    const page = this.getPage();

    if (numeroProcesso) {
      const opened = await this.openProcess(numeroProcesso);
      if (!opened) return null;
    }

    // Extrai informacoes da pagina do processo
    const url = page.url();
    const idMatch = url.match(/id_procedimento=(\d+)/);

    const numeroEl = page.locator('#txtNumeroProcesso, .numero-processo, #anchor0').first();
    const numero = (await numeroEl.textContent())?.trim() ?? '';

    // Clica em consultar andamento para ver mais detalhes
    await this.clickSmart(page, { role: 'link', name: /consultar.*andamento/i }, SEI_SELECTORS.processActions.consultarAndamento);
    await this.waitForLoad();

    let tipo = '';
    let especificacao = '';
    let dataAutuacao = '';
    const interessados: string[] = [];
    const unidadesAbertas: string[] = [];

    // Extrai informacoes da tela de andamento
    try {
      // Usa getByText para encontrar labels e seus valores
      tipo = (await page.locator('text=Tipo').locator('xpath=following-sibling::*').first().textContent())?.trim() ?? '';
      especificacao = (await page.locator('text=Especificacao').locator('xpath=following-sibling::*').first().textContent())?.trim() ?? '';
      dataAutuacao = (await page.locator('text=Autuacao').locator('xpath=following-sibling::*').first().textContent())?.trim() ?? '';

      const interessadosItems = await page.locator('.interessado-item, [class*="interessado"] li').all();
      for (const el of interessadosItems) {
        const text = await el.textContent();
        if (text) interessados.push(text.trim());
      }

      const unidadesItems = await page.locator('.unidade-aberta, [class*="unidade"] li').all();
      for (const el of unidadesItems) {
        const text = await el.textContent();
        if (text) unidadesAbertas.push(text.trim());
      }
    } catch {
      // Ignora erros de extracao
    }

    return {
      id: idMatch?.[1] ?? '',
      numero,
      tipo,
      especificacao,
      interessados,
      unidadesAbertas,
      dataAutuacao,
    };
  }

  // ============================================
  // Operacoes com Processos
  // ============================================

  /** Anexa processo a outro */
  async anexarProcesso(processoPrincipal: string, processoAnexado: string): Promise<boolean> {
    const page = this.getPage();

    // Abre o processo principal
    await this.openProcess(processoPrincipal);

    // Clica em anexar
    await this.clickSmart(page, { role: 'link', name: /anexar.*processo/i }, SEI_SELECTORS.processActions.anexarProcesso);
    await this.waitForLoad();

    // Preenche o numero do processo a anexar
    await this.fillSmart(page, { role: 'textbox', name: /protocolo|processo/i }, processoAnexado, '#txtProtocoloAnexar, input[name="txtProtocoloAnexar"]');
    await this.clickSmart(page, { role: 'button', name: /pesquis/i }, '#btnPesquisar, button[name="sbmPesquisar"]');
    await this.waitForLoad();

    // Confirma a anexacao
    try {
      await this.clickSmart(page, { role: 'button', name: /confirmar/i });
      await this.waitForLoad();
      return await this.existsSmart(page, { role: 'alert' }, '.msgSucesso, .alert-success', 5000);
    } catch {
      return false;
    }
  }

  /** Relaciona dois processos */
  async relacionarProcesso(processo1: string, processo2: string): Promise<boolean> {
    const page = this.getPage();

    // Abre o primeiro processo
    await this.openProcess(processo1);

    // Clica em relacionar
    await this.clickSmart(page, { role: 'link', name: /relacionar.*processo/i }, SEI_SELECTORS.processActions.relacionarProcesso);
    await this.waitForLoad();

    // Preenche o numero do processo a relacionar
    await this.fillSmart(page, { role: 'textbox', name: /protocolo|processo/i }, processo2, '#txtProtocoloRelacionar, input[name="txtProtocoloRelacionar"]');
    await this.clickSmart(page, { role: 'button', name: /pesquis/i }, '#btnPesquisar, button[name="sbmPesquisar"]');
    await this.waitForLoad();

    // Confirma
    try {
      await this.clickSmart(page, { role: 'button', name: /confirmar/i });
      await this.waitForLoad();
      return await this.existsSmart(page, { role: 'alert' }, '.msgSucesso, .alert-success', 5000);
    } catch {
      return false;
    }
  }

  /** Atribui processo a um usuario */
  async atribuirProcesso(numeroProcesso: string, nomeUsuario: string): Promise<boolean> {
    const page = this.getPage();

    await this.openProcess(numeroProcesso);

    // Clica em atribuir
    await this.clickSmart(page, { role: 'link', name: /atribuir.*processo/i }, SEI_SELECTORS.processActions.atribuirProcesso);
    await this.waitForLoad();

    // Seleciona o usuario
    try {
      await this.selectSmart(page, { role: 'combobox', name: /usu[aá]rio|atribui[cç][aã]o/i }, { label: nomeUsuario }, '#selAtribuicao, select[name="selAtribuicao"]');
    } catch {
      // Tenta por valor parcial
      const select = await page.$('#selAtribuicao, select[name="selAtribuicao"]');
      if (select) {
        const options = await select.$$eval('option', (opts) =>
          opts.map((o) => ({ value: o.value, text: o.textContent }))
        );
        const match = options.find((o) => o.text?.toLowerCase().includes(nomeUsuario.toLowerCase()));
        if (match?.value) {
          await page.selectOption('#selAtribuicao, select[name="selAtribuicao"]', match.value);
        }
      }
    }

    // Confirma
    await this.clickSmart(page, { role: 'button', name: /salvar|confirmar/i }, '#btnSalvar, button[name="sbmSalvar"]');
    await this.waitForLoad();

    return await this.existsSmart(page, { role: 'alert' }, '.msgSucesso, .alert-success', 5000);
  }

  // ============================================
  // Operacoes com Documentos
  // ============================================

  /** Consulta detalhes do documento */
  async getDocumentDetails(idDocumento: string): Promise<{
    id: string;
    numero: string;
    tipo: string;
    data: string;
    assinaturas: Array<{ nome: string; cargo: string; data: string }>;
  } | null> {
    const page = this.getPage();

    // Abre o documento
    const opened = await this.openDocument(idDocumento);
    if (!opened) return null;

    // Extrai informacoes
    const numero = (await page.locator('.numero-documento, #txtNumeroDocumento').first().textContent())?.trim() ?? '';
    const tipo = (await page.locator('.tipo-documento, #txtTipoDocumento').first().textContent())?.trim() ?? '';
    const data = (await page.locator('.data-documento, #txtDataDocumento').first().textContent())?.trim() ?? '';

    const assinaturas: Array<{ nome: string; cargo: string; data: string }> = [];

    // Extrai assinaturas usando locator de tabela
    try {
      const rows = await page.getByRole('row').all();
      for (const row of rows) {
        const cells = await row.getByRole('cell').all();
        if (cells.length >= 3) {
          assinaturas.push({
            nome: (await cells[0]?.textContent())?.trim() ?? '',
            cargo: (await cells[1]?.textContent())?.trim() ?? '',
            data: (await cells[2]?.textContent())?.trim() ?? '',
          });
        }
      }
    } catch {
      // Ignora erros
    }

    return {
      id: idDocumento,
      numero,
      tipo,
      data,
      assinaturas,
    };
  }

  /** Cancela documento */
  async cancelDocument(idDocumento: string, motivo: string): Promise<boolean> {
    const page = this.getPage();

    // Abre o documento
    await this.openDocument(idDocumento);

    // Clica em cancelar/excluir
    await this.clickSmart(page, { role: 'link', name: /cancelar|excluir/i }, 'a[href*="documento_cancelar"], img[title*="Cancelar"], img[title*="Excluir"]');
    await this.waitForLoad();

    // Preenche motivo
    await this.fillSmart(page, { role: 'textbox', name: /motivo/i }, motivo, '#txaMotivo, textarea[name="txaMotivo"]');

    // Confirma
    await this.clickSmart(page, { role: 'button', name: /confirmar/i }, '#btnConfirmar, button[name="sbmConfirmar"]');
    await this.waitForLoad();

    return await this.existsSmart(page, { role: 'alert' }, '.msgSucesso, .alert-success', 5000);
  }

  // ============================================
  // Blocos de Assinatura
  // ============================================

  /** Lista blocos de assinatura */
  async listBlocos(): Promise<Array<{
    id: string;
    descricao: string;
    quantidade: number;
    unidade: string;
  }>> {
    const page = this.getPage();

    // Navega para lista de blocos
    await page.goto(`${this.baseUrl}/sei/controlador.php?acao=bloco_assinatura_listar`);
    await this.waitForLoad();

    const blocos: Array<{
      id: string;
      descricao: string;
      quantidade: number;
      unidade: string;
    }> = [];

    const rows = await page.getByRole('row').all();
    for (const row of rows.slice(1)) { // Pula cabecalho
      try {
        const link = await row.getByRole('link').first();
        const href = (await link.getAttribute('href')) ?? '';
        const idMatch = href.match(/id_bloco=(\d+)/);

        if (!idMatch) continue;

        const cells = await row.getByRole('cell').all();

        blocos.push({
          id: idMatch[1],
          descricao: (await cells[1]?.textContent())?.trim() ?? '',
          quantidade: parseInt((await cells[2]?.textContent())?.match(/\d+/)?.[0] ?? '0', 10),
          unidade: (await cells[3]?.textContent())?.trim() ?? '',
        });
      } catch {
        // Ignora erros
      }
    }

    return blocos;
  }

  /** Cria bloco de assinatura */
  async createBloco(descricao: string, tipo: 'assinatura' | 'reuniao' | 'interno' = 'assinatura'): Promise<string | null> {
    const page = this.getPage();

    // Navega para novo bloco
    await this.clickSmart(page, { role: 'link', name: /novo.*bloco|criar.*bloco/i }, SEI_SELECTORS.block.novo);
    await this.waitForLoad();

    // Seleciona tipo
    const tipoMap = { assinatura: 'A', reuniao: 'R', interno: 'I' };
    try {
      await this.selectSmart(page, { role: 'combobox', name: /tipo/i }, tipoMap[tipo], '#selTipo, select[name="selTipo"]');
    } catch {
      // Tipo pode ja estar selecionado
    }

    // Preenche descricao
    await this.fillSmart(page, { role: 'textbox', name: /descri[cç][aã]o/i }, descricao, SEI_SELECTORS.block.formNovo.descricao);

    // Salva
    await this.clickSmart(page, { role: 'button', name: /salvar/i }, SEI_SELECTORS.block.formNovo.salvar);
    await this.waitForLoad();

    // Extrai ID do bloco criado
    const url = page.url();
    const idMatch = url.match(/id_bloco=(\d+)/);

    return idMatch?.[1] ?? null;
  }

  /** Adiciona documento ao bloco */
  async addDocumentoToBloco(idBloco: string, idDocumento: string): Promise<boolean> {
    const page = this.getPage();

    // Abre o documento
    await this.openDocument(idDocumento);

    // Clica em incluir em bloco
    try {
      await this.clickSmart(page, { role: 'link', name: /bloco|incluir.*bloco/i }, 'a[href*="bloco_incluir"], img[title*="Bloco"]');
    } catch {
      return false;
    }
    await this.waitForLoad();

    // Seleciona o bloco
    try {
      await this.selectSmart(page, { role: 'combobox', name: /bloco/i }, idBloco, '#selBloco, select[name="selBloco"]');
      await this.clickSmart(page, { role: 'button', name: /adicionar/i }, '#btnAdicionar, button[name="sbmAdicionar"]');
      await this.waitForLoad();
      return await this.existsSmart(page, { role: 'alert' }, '.msgSucesso, .alert-success', 5000);
    } catch {
      return false;
    }
  }

  /** Remove documento do bloco */
  async removeDocumentoFromBloco(idBloco: string, idDocumento: string): Promise<boolean> {
    const page = this.getPage();

    // Navega para o bloco
    await page.goto(`${this.baseUrl}/sei/controlador.php?acao=bloco_protocolo_listar&id_bloco=${idBloco}`);
    await this.waitForLoad();

    // Encontra e remove o documento usando locators semanticos
    const rows = await page.getByRole('row').all();
    for (const row of rows) {
      const docLink = await row.getByRole('link').filter({ hasText: new RegExp(idDocumento) }).first();
      if (await docLink.isVisible({ timeout: 500 }).catch(() => false)) {
        try {
          await row.getByRole('link', { name: /remover|excluir/i })
            .or(row.locator('img[title*="Remover"], img[title*="Excluir"]').locator('xpath=..'))
            .first().click();
          await this.waitForLoad();

          // Confirma se necessario
          try {
            await page.getByRole('button', { name: /confirmar|sim/i }).click({ timeout: 2000 });
            await this.waitForLoad();
          } catch {
            // Sem confirmacao necessaria
          }

          return true;
        } catch {
          // Continua tentando
        }
      }
    }

    return false;
  }

  /** Disponibiliza bloco para outras unidades */
  async disponibilizarBloco(idBloco: string, unidades?: string[]): Promise<boolean> {
    const page = this.getPage();

    // Navega para o bloco
    await page.goto(`${this.baseUrl}/sei/controlador.php?acao=bloco_assinatura_disponibilizar&id_bloco=${idBloco}`);
    await this.waitForLoad();

    // Adiciona unidades se especificadas
    if (unidades?.length) {
      for (const unidade of unidades) {
        await this.fillSmart(page, { role: 'textbox', name: /unidade/i }, unidade, '#txtUnidade, input[name="txtUnidade"]');
        await page.waitForTimeout(300);
        await page.keyboard.press('Enter');
      }
    }

    // Confirma disponibilizacao
    await this.clickSmart(page, { role: 'button', name: /disponibilizar/i }, '#btnDisponibilizar, button[name="sbmDisponibilizar"]');
    await this.waitForLoad();

    return await this.existsSmart(page, { role: 'alert' }, '.msgSucesso, .alert-success', 5000);
  }

  // ============================================
  // Utilitarios
  // ============================================

  /** Captura screenshot */
  async screenshot(fullPage = false): Promise<string> {
    const page = this.getPage();
    const buffer = await page.screenshot({ fullPage });
    return buffer.toString('base64');
  }

  /** Captura arvore de acessibilidade (ARIA snapshot) */
  async snapshot(_includeHidden = false): Promise<string> {
    const page = this.getPage();
    // Obtem titulo e URL da pagina como snapshot simplificado
    const url = page.url();
    const title = await page.title();
    const text = await page.innerText('body').catch(() => '');

    const snapshot = {
      url,
      title,
      textContent: text.substring(0, 5000),
    };

    return JSON.stringify(snapshot, null, 2);
  }

  /** Obtem arvore de acessibilidade completa */
  async getAriaSnapshot(): Promise<object | null> {
    const page = this.getPage();
    try {
      // Usa ariaSnapshot do locator para obter estrutura ARIA
      const ariaTree = await page.locator('body').ariaSnapshot();
      return { ariaSnapshot: ariaTree };
    } catch {
      // Fallback: retorna informacoes basicas da pagina
      try {
        const url = page.url();
        const title = await page.title();
        return { url, title, note: 'ARIA snapshot nao disponivel' };
      } catch {
        return null;
      }
    }
  }

  /** Obtem texto visivel da pagina */
  async getVisibleText(): Promise<string> {
    const page = this.getPage();
    return page.innerText('body');
  }

  /** Executa JavaScript na pagina */
  async evaluate<T>(fn: () => T): Promise<T> {
    const page = this.getPage();
    return page.evaluate(fn);
  }

  // ============================================
  // Metodos Adicionais (Paridade com MCP)
  // ============================================

  /** Lista usuarios do SEI */
  async listUsuarios(filter?: string): Promise<Array<{ id: string; nome: string; sigla: string }>> {
    const page = this.getPage();
    const usuarios: Array<{ id: string; nome: string; sigla: string }> = [];

    // Tenta extrair do select de atribuicao
    try {
      await page.getByRole('link', { name: /atribuir/i })
        .or(page.locator('img[title*="Atribuir"]').locator('xpath=..'))
        .first().click();
      await this.waitForLoad();

      const select = page.getByRole('combobox', { name: /atribui[cç][aã]o|usu[aá]rio/i })
        .or(page.locator('#selAtribuicao, select[name="selAtribuicao"]'));
      const selectEl = await select.first().elementHandle();

      if (selectEl) {
        const options = await selectEl.$$eval('option', (opts) =>
          opts.filter((o) => o.value).map((o) => ({
            id: o.value,
            nome: o.textContent?.trim() ?? '',
            sigla: o.value,
          }))
        );

        if (filter) {
          return options.filter((u) => u.nome.toLowerCase().includes(filter.toLowerCase()));
        }
        return options;
      }
    } catch {
      // Ignora erro
    }

    return usuarios;
  }

  /** Lista hipoteses legais */
  async listHipotesesLegais(): Promise<Array<{ id: string; nome: string }>> {
    const page = this.getPage();
    const hipoteses: Array<{ id: string; nome: string }> = [];

    try {
      // Navega para criar documento para ver hipoteses legais
      await page.getByRole('link', { name: /incluir.*documento/i })
        .or(page.locator('img[title*="Incluir Documento"]').locator('xpath=..'))
        .first().click();
      await this.waitForLoad();

      // Seleciona nivel restrito para ver hipoteses
      await page.getByRole('radio', { name: /restrito/i }).click();
      await this.waitForLoad();

      const select = page.getByRole('combobox', { name: /hip[oó]tese/i })
        .or(page.locator(SEI_SELECTORS.newDocument.hipoteseLegal));
      const selectEl = await select.first().elementHandle();

      if (selectEl) {
        const options = await selectEl.$$eval('option', (opts) =>
          opts.filter((o) => o.value).map((o) => ({
            id: o.value,
            nome: o.textContent?.trim() ?? '',
          }))
        );
        return options;
      }
    } catch {
      // Ignora erro
    }

    return hipoteses;
  }

  /** Lista marcadores disponiveis */
  async listMarcadores(): Promise<Array<{ id: string; nome: string; cor: string }>> {
    const page = this.getPage();
    const marcadores: Array<{ id: string; nome: string; cor: string }> = [];

    try {
      // Navega para gerenciar marcadores
      await page.goto(`${this.baseUrl}/sei/controlador.php?acao=marcador_listar`);
      await this.waitForLoad();

      const rows = await page.getByRole('row').all();
      for (const row of rows.slice(1)) { // Pula cabecalho
        try {
          const link = await row.getByRole('link').first();
          const href = (await link.getAttribute('href')) ?? '';
          const idMatch = href.match(/id_marcador=(\d+)/);

          if (idMatch) {
            const cells = await row.getByRole('cell').all();
            const corElement = row.locator('.cor-marcador, span[style*="background"]').first();
            const cor = (await corElement.getAttribute('style'))?.match(/#[0-9A-Fa-f]{6}/)?.[0] ?? '#000000';

            marcadores.push({
              id: idMatch[1],
              nome: (await cells[1]?.textContent())?.trim() ?? '',
              cor,
            });
          }
        } catch {
          // Ignora
        }
      }
    } catch {
      // Ignora erro
    }

    return marcadores;
  }

  /** Lista processos do usuario */
  async listMeusProcessos(
    status: 'abertos' | 'fechados' = 'abertos',
    limit = 50
  ): Promise<Array<{ numero: string; tipo: string; especificacao: string }>> {
    const page = this.getPage();
    const processos: Array<{ numero: string; tipo: string; especificacao: string }> = [];

    try {
      // Navega para controle de processos
      await page.goto(`${this.baseUrl}/sei/controlador.php?acao=procedimento_controlar`);
      await this.waitForLoad();

      // Seleciona filtro
      if (status === 'fechados') {
        try {
          await page.getByRole('combobox', { name: /filtro|status/i }).selectOption('concluidos');
          await this.waitForLoad();
        } catch {
          // Ignora
        }
      }

      const rows = await page.getByRole('row').all();
      let count = 0;

      for (const row of rows.slice(1)) { // Pula cabecalho
        if (count >= limit) break;

        try {
          const cells = await row.getByRole('cell').all();
          const link = await cells[0]?.getByRole('link').first();
          const numero = (await link?.textContent())?.trim() ?? '';
          const tipo = (await cells[1]?.textContent())?.trim() ?? '';
          const especificacao = (await cells[2]?.textContent())?.trim() ?? '';

          if (numero) {
            processos.push({ numero, tipo, especificacao });
            count++;
          }
        } catch {
          // Ignora linha invalida
        }
      }
    } catch {
      // Ignora erro
    }

    return processos;
  }

  /** Busca processos */
  async searchProcessos(
    query: string,
    type: 'numero' | 'texto' | 'interessado' = 'numero',
    limit = 20
  ): Promise<Array<{ numero: string; tipo: string; especificacao: string }>> {
    const page = this.getPage();
    const processos: Array<{ numero: string; tipo: string; especificacao: string }> = [];

    try {
      // Navega para pesquisa
      await page.goto(`${this.baseUrl}/sei/controlador.php?acao=protocolo_pesquisa_rapida`);
      await this.waitForLoad();

      // Seleciona tipo de pesquisa
      const typeMap = { numero: '1', texto: '2', interessado: '3' };
      try {
        await page.getByRole('combobox', { name: /tipo.*pesquisa/i }).selectOption(typeMap[type]);
      } catch {
        try {
          await page.selectOption('#selTipoPesquisa, select[name="selTipoPesquisa"]', typeMap[type]);
        } catch {
          // Tipo pode nao existir
        }
      }

      // Preenche busca
      try {
        await page.getByRole('textbox', { name: /pesquis/i }).fill(query);
        await page.getByRole('button', { name: /pesquis/i }).click();
      } catch {
        await page.fill('#txtPesquisa, input[name="txtPesquisa"]', query);
        await page.click('#btnPesquisar, button[name="sbmPesquisar"]');
      }
      await this.waitForLoad();

      const rows = await page.getByRole('row').all();
      let count = 0;

      for (const row of rows.slice(1)) { // Pula cabecalho
        if (count >= limit) break;

        try {
          const cells = await row.getByRole('cell').all();
          const link = await cells[0]?.getByRole('link').first();
          const numero = (await link?.textContent())?.trim() ?? '';
          const tipo = (await cells[1]?.textContent())?.trim() ?? '';
          const especificacao = (await cells[2]?.textContent())?.trim() ?? '';

          if (numero) {
            processos.push({ numero, tipo, especificacao });
            count++;
          }
        } catch {
          // Ignora linha invalida
        }
      }
    } catch {
      // Ignora erro - retorna lista vazia
    }

    return processos;
  }

  /** Faz download do processo completo */
  async downloadProcess(
    numeroProcesso: string,
    _includeAttachments = true,
    outputPath?: string
  ): Promise<{ filePath: string; size: number }> {
    const page = this.getPage();
    await this.openProcess(numeroProcesso);

    // Inicia download
    const downloadPromise = page.waitForEvent('download');

    try {
      await page.getByRole('link', { name: /gerar.*pdf/i })
        .or(page.locator('img[title*="PDF"]').locator('xpath=..'))
        .first().click();
    } catch {
      await page.click(SEI_SELECTORS.processActions.gerarPdf);
    }

    const download = await downloadPromise;
    const suggestedPath = outputPath || `/tmp/${download.suggestedFilename()}`;
    await download.saveAs(suggestedPath);

    const fs = await import('fs/promises');
    const stats = await fs.stat(suggestedPath);

    return { filePath: suggestedPath, size: stats.size };
  }

  /** Faz download de documento especifico */
  async downloadDocument(
    idDocumento: string,
    outputPath?: string
  ): Promise<{ filePath: string; size: number }> {
    const page = this.getPage();
    await this.openDocument(idDocumento);

    // Procura botao de download
    const downloadPromise = page.waitForEvent('download');

    await this.clickSmart(page, { role: 'link', name: /download|pdf/i }, 'a[href*="documento_download"], img[title*="Download"], img[title*="PDF"]');

    const download = await downloadPromise;
    const suggestedPath = outputPath || `/tmp/${download.suggestedFilename()}`;
    await download.saveAs(suggestedPath);

    const fs = await import('fs/promises');
    const stats = await fs.stat(suggestedPath);

    return { filePath: suggestedPath, size: stats.size };
  }

  /** Lista anotacoes do processo */
  async listAnnotations(): Promise<Array<{ texto: string; data: string; usuario: string }>> {
    const page = this.getPage();
    const annotations: Array<{ texto: string; data: string; usuario: string }> = [];

    try {
      // Procura area de anotacoes
      const anotacoesEl = await page.locator('.anotacao-item, [class*="anotacao"]').all();
      for (const el of anotacoesEl) {
        const texto = (await el.locator('.texto, .conteudo').first().textContent())?.trim() ?? '';
        const data = (await el.locator('.data').first().textContent())?.trim() ?? '';
        const usuario = (await el.locator('.usuario').first().textContent())?.trim() ?? '';

        annotations.push({ texto, data, usuario });
      }
    } catch {
      // Pode nao ter anotacoes
    }

    return annotations;
  }

  /** Adiciona anotacao ao processo */
  async addAnnotation(texto: string, prioridade: 'normal' | 'alta' = 'normal'): Promise<boolean> {
    const page = this.getPage();

    try {
      // Clica no botao de anotacoes
      await this.clickSmart(page, { role: 'link', name: /anota[cç]/i }, 'img[title*="Anota"]');
      await this.waitForLoad();

      // Preenche texto
      await this.fillSmart(page, { role: 'textbox', name: /anota[cç][aã]o|texto/i }, texto, '#txaAnotacao, textarea[name="txaAnotacao"]');

      // Define prioridade se alta
      if (prioridade === 'alta') {
        try {
          await this.checkSmart(page, { role: 'checkbox', name: /prioridade|alta/i }, '#chkPrioridade, input[name="chkPrioridade"]');
        } catch {
          // Sem checkbox de prioridade
        }
      }

      // Salva
      await this.clickSmart(page, { role: 'button', name: /salvar/i }, '#btnSalvar, button[name="sbmSalvar"]');
      await this.waitForLoad();

      return true;
    } catch {
      return false;
    }
  }

  /** Adiciona marcador ao processo */
  async addMarker(marcador: string, texto?: string): Promise<boolean> {
    const page = this.getPage();

    try {
      // Clica no botao de marcador
      await this.clickSmart(page, { role: 'link', name: /marcador/i }, 'img[title*="Marcador"]');
      await this.waitForLoad();

      // Seleciona marcador
      await this.selectSmart(page, { role: 'combobox', name: /marcador/i }, { label: marcador }, '#selMarcador, select[name="selMarcador"]');

      // Preenche texto se fornecido
      if (texto) {
        await this.fillSmart(page, { role: 'textbox', name: /texto|observa[cç]/i }, texto, '#txaTexto, textarea[name="txaTexto"]');
      }

      // Salva
      await this.clickSmart(page, { role: 'button', name: /salvar/i }, '#btnSalvar, button[name="sbmSalvar"]');
      await this.waitForLoad();

      return true;
    } catch {
      return false;
    }
  }

  /** Remove marcador do processo */
  async removeMarker(marcador: string): Promise<boolean> {
    const page = this.getPage();

    try {
      // Clica no botao de marcador
      await this.clickSmart(page, { role: 'link', name: /marcador/i }, 'img[title*="Marcador"]');
      await this.waitForLoad();

      // Procura e remove o marcador
      const marcadorEl = page.getByText(marcador).first();
      if (await marcadorEl.isVisible({ timeout: 2000 })) {
        // Clica no link de excluir/remover dentro do elemento pai
        const parentEl = marcadorEl.locator('xpath=..');
        const removeLink = parentEl.getByRole('link', { name: /excluir|remover/i })
          .or(parentEl.locator('img[title*="Excluir"], img[title*="Remover"]').locator('xpath=..'));
        await removeLink.first().click();
        await this.waitForLoad();
        return true;
      }
    } catch {
      // Ignora erro
    }

    return false;
  }

  /** Define prazo no processo */
  async setDeadline(dias: number, tipo: 'util' | 'corrido' = 'util'): Promise<boolean> {
    const page = this.getPage();

    try {
      // Clica no botao de prazo
      await this.clickSmart(page, { role: 'link', name: /prazo/i }, 'img[title*="Prazo"]');
      await this.waitForLoad();

      // Preenche dias
      await this.fillSmart(page, { role: 'textbox', name: /dias/i }, String(dias), '#txtDias, input[name="txtDias"]');

      // Seleciona tipo
      if (tipo === 'corrido') {
        await this.clickSmart(page, { role: 'radio', name: /corrido/i }, '#rdoCorrido, input[value="corrido"]');
      } else {
        await this.clickSmart(page, { role: 'radio', name: /[uú]t/i }, '#rdoUtil, input[value="util"]');
      }

      // Salva
      await this.clickSmart(page, { role: 'button', name: /salvar/i }, '#btnSalvar, button[name="sbmSalvar"]');
      await this.waitForLoad();

      return true;
    } catch {
      return false;
    }
  }

  /** Concede acesso ao processo */
  async grantAccess(usuario: string, tipo: 'consulta' | 'acompanhamento' = 'consulta'): Promise<boolean> {
    const page = this.getPage();

    try {
      // Clica em gerenciar credenciais/acesso
      await this.clickSmart(page, { role: 'link', name: /credencial|acesso/i }, 'img[title*="Credencial"], img[title*="Acesso"]');
      await this.waitForLoad();

      // Preenche usuario
      await this.fillSmart(page, { role: 'textbox', name: /usu[aá]rio/i }, usuario, '#txtUsuario, input[name="txtUsuario"]');

      // Seleciona tipo de acesso
      const tipoValue = tipo === 'acompanhamento' ? '2' : '1';
      try {
        await this.selectSmart(page, { role: 'combobox', name: /tipo/i }, tipoValue, '#selTipo, select[name="selTipo"]');
      } catch {
        // Sem select de tipo
      }

      // Concede
      await this.clickSmart(page, { role: 'button', name: /conceder/i }, '#btnConceder, button[name="sbmConceder"]');
      await this.waitForLoad();

      return true;
    } catch {
      return false;
    }
  }

  /** Revoga acesso ao processo */
  async revokeAccess(usuario: string): Promise<boolean> {
    const page = this.getPage();

    try {
      // Clica em gerenciar credenciais/acesso
      await this.clickSmart(page, { role: 'link', name: /credencial|acesso/i }, 'img[title*="Credencial"], img[title*="Acesso"]');
      await this.waitForLoad();

      // Procura usuario na lista e revoga
      const rows = await page.getByRole('row').all();
      for (const row of rows) {
        const nomeEl = await row.getByRole('cell').first();
        const nome = await nomeEl?.textContent();

        if (nome?.toLowerCase().includes(usuario.toLowerCase())) {
          // Clica no link de revogar/excluir dentro da linha
          const revokeLink = row.getByRole('link', { name: /revogar|excluir/i })
            .or(row.locator('img[title*="Revogar"], img[title*="Excluir"]').locator('xpath=..'));
          await revokeLink.first().click();
          await this.waitForLoad();
          return true;
        }
      }
    } catch {
      // Ignora erro
    }

    return false;
  }

  /** Obtem conteudo HTML do documento */
  async getDocumentContent(idDocumento: string): Promise<string> {
    const page = this.getPage();
    await this.openDocument(idDocumento);

    try {
      // Tenta obter do iframe do editor
      const editorFrame = this.getEditorFrame(page);
      const content = await editorFrame.locator('body').innerHTML();
      return content;
    } catch {
      // Tenta obter do iframe de visualizacao
      try {
        const viewFrame = this.getViewFrame(page);
        const content = await viewFrame.locator('body').innerHTML();
        return content;
      } catch {
        return '';
      }
    }
  }

  /** Registra ciencia no documento */
  async registerKnowledge(): Promise<boolean> {
    const page = this.getPage();

    try {
      await page.getByRole('link', { name: /ci[eê]ncia|ciente/i })
        .or(page.locator('img[title*="Ciência"], img[title*="Ciente"]').locator('xpath=..'))
        .first().click();
      await this.waitForLoad();

      // Confirma se necessario
      try {
        await page.getByRole('button', { name: /confirmar|sim/i }).click({ timeout: 2000 });
        await this.waitForLoad();
      } catch {
        // Sem confirmacao necessaria
      }

      return true;
    } catch {
      return false;
    }
  }

  /** Agenda publicacao do documento */
  async schedulePublication(veiculo: string, dataPublicacao?: string, resumo?: string): Promise<boolean> {
    const page = this.getPage();

    try {
      await page.getByRole('link', { name: /publica[cç][aã]o|publicar/i })
        .or(page.locator('img[title*="Publicação"], img[title*="Publicar"]').locator('xpath=..'))
        .first().click();
      await this.waitForLoad();

      // Seleciona veiculo
      try {
        await page.getByRole('combobox', { name: /ve[ií]culo/i }).selectOption({ label: veiculo });
      } catch {
        await page.selectOption('#selVeiculo, select[name="selVeiculo"]', { label: veiculo });
      }

      // Data de publicacao
      if (dataPublicacao) {
        try {
          await page.getByRole('textbox', { name: /data.*publica[cç][aã]o/i }).fill(dataPublicacao);
        } catch {
          await page.fill('#txtDataPublicacao, input[name="txtDataPublicacao"]', dataPublicacao);
        }
      }

      // Resumo
      if (resumo) {
        try {
          await page.getByRole('textbox', { name: /resumo/i }).fill(resumo);
        } catch {
          await page.fill('#txaResumo, textarea[name="txaResumo"]', resumo);
        }
      }

      // Agendar
      try {
        await page.getByRole('button', { name: /agendar/i }).click();
      } catch {
        await page.click('#btnAgendar, button[name="sbmAgendar"]');
      }
      await this.waitForLoad();

      return true;
    } catch {
      return false;
    }
  }

  /** Assina todos os documentos de um bloco */
  async signBloco(idBloco: string, senha: string): Promise<boolean> {
    const page = this.getPage();

    try {
      // Navega para o bloco
      await page.goto(`${this.baseUrl}/sei/controlador.php?acao=bloco_protocolo_listar&id_bloco=${idBloco}`);
      await this.waitForLoad();

      // Clica em assinar bloco
      await page.getByRole('link', { name: /assinar.*bloco|assinar/i })
        .or(page.locator('img[title*="Assinar"]').locator('xpath=..'))
        .first().click();
      await this.waitForLoad();

      // Preenche senha
      try {
        await page.getByRole('textbox', { name: /senha/i }).fill(senha);
        await page.getByRole('button', { name: /assinar/i }).click();
      } catch {
        await page.fill(SEI_SELECTORS.signature.senha, senha);
        await page.click(SEI_SELECTORS.signature.assinar);
      }
      await this.waitForLoad();

      const success = page.locator('.msgSucesso, .alert-success');
      await success.first().waitFor({ timeout: 5000 });
      return true;
    } catch {
      return false;
    }
  }

  /** Obtem informacoes do bloco */
  async getBloco(idBloco: string): Promise<{
    id: string;
    descricao: string;
    tipo: string;
    documentos: Array<{ id: string; numero: string; processo: string }>;
  } | null> {
    const page = this.getPage();

    try {
      await page.goto(`${this.baseUrl}/sei/controlador.php?acao=bloco_protocolo_listar&id_bloco=${idBloco}`);
      await this.waitForLoad();

      const descricao = (await page.locator('#txtDescricao, .descricao-bloco').first().textContent())?.trim() ?? '';
      const tipo = (await page.locator('#txtTipo, .tipo-bloco').first().textContent())?.trim() ?? '';

      const documentos: Array<{ id: string; numero: string; processo: string }> = [];

      const rows = await page.getByRole('row').all();
      for (const row of rows.slice(1)) { // Pula cabecalho
        try {
          const link = await row.getByRole('link').first();
          const href = (await link.getAttribute('href')) ?? '';
          const idMatch = href.match(/id_documento=(\d+)/);

          if (idMatch) {
            const cells = await row.getByRole('cell').all();
            documentos.push({
              id: idMatch[1],
              numero: (await cells[1]?.textContent())?.trim() ?? '',
              processo: (await cells[2]?.textContent())?.trim() ?? '',
            });
          }
        } catch {
          // Ignora linha invalida
        }
      }

      return { id: idBloco, descricao, tipo, documentos };
    } catch {
      return null;
    }
  }
}

export default SEIBrowserClient;
