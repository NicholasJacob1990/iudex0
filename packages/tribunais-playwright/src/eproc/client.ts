/**
 * Cliente eproc (Sistema de Processo Eletrônico)
 * Implementação para TJMG e outros tribunais que usam eproc
 */

import type { Page } from 'playwright';
import { BaseTribunalClient } from '../core/base-client.js';
import type {
  TribunalClientConfig,
  TribunalSelectors,
  Processo,
  PeticaoOpcoes,
  ProtocoloResultado,
  AssinaturaOpcoes,
  AssinaturaResultado,
  ApprovalInfo,
  Documento,
  Movimentacao,
} from '../types/index.js';
import { EPROC_TJMG_SELECTORS } from './selectors.js';

export interface EprocClientConfig extends TribunalClientConfig {
  /** Tribunal (tjmg, trf4, etc.) */
  tribunal?: string;
  /** Instância (1g, 2g) */
  instancia?: '1g' | '2g';
}

export class EprocClient extends BaseTribunalClient {
  protected tribunalName = 'eproc';
  protected selectors: TribunalSelectors = EPROC_TJMG_SELECTORS;
  private tribunal: string;
  private instancia: string;

  constructor(config: EprocClientConfig) {
    super(config);
    this.tribunal = config.tribunal ?? 'tjmg';
    this.instancia = config.instancia ?? '1g';
    this.tribunalName = `eproc-${this.tribunal}`;
  }

  // ============================================
  // Sobrescreve navegação para login
  // ============================================

  protected override async navigateToLogin(): Promise<void> {
    const page = this.getPage();
    await page.goto(this.config.baseUrl, { waitUntil: 'networkidle' });
    await this.waitForLoad();
  }

  // ============================================
  // Login específico do eproc
  // ============================================

  protected override async loginWithPassword(): Promise<boolean> {
    const page = this.getPage();
    const auth = this.config.auth as { type: 'password'; cpf: string; senha: string };

    this.log('Fazendo login com usuário e senha...');

    try {
      // Verifica se há captcha
      const hasCaptcha = await this.handleCaptchaIfPresent();
      if (hasCaptcha) {
        this.log('Captcha resolvido, continuando login...');
      }

      // Preenche usuário usando seletor ARIA
      await this.fillSmart(this.selectors.login.cpfInput, auth.cpf);
      this.log(`Usuário preenchido: ${auth.cpf}`);

      // Preenche senha usando seletor ARIA
      await this.fillSmart(this.selectors.login.senhaInput, auth.senha);
      this.log('Senha preenchida');

      // Verifica captcha novamente (pode aparecer após preencher campos)
      await this.handleCaptchaIfPresent();

      // Clica em entrar usando seletor ARIA
      await this.clickSmart(this.selectors.login.entrarBtn);
      this.log('Botão Entrar clicado');

      await this.waitForLoad();

      // Verifica se login foi bem sucedido
      // O eproc redireciona para a página principal após login
      const currentUrl = page.url();
      const loggedIn = !currentUrl.includes('login') &&
                       !currentUrl.includes('index.php') &&
                       (currentUrl.includes('usuario') ||
                        currentUrl.includes('painel') ||
                        await this.checkLoggedIn());

      if (loggedIn) {
        this.isLoggedIn = true;
        this.emit('login:success', { usuario: auth.cpf });
        this.log('Login realizado com sucesso');
        return true;
      }

      // Verifica mensagem de erro
      const errorMsg = await page.$eval('.alert-danger, .erro, [class*="erro"]', el => el.textContent).catch(() => null);
      if (errorMsg) {
        this.emit('login:error', { error: errorMsg });
        this.log(`Erro no login: ${errorMsg}`);
        return false;
      }

      // Pode ter 2FA
      const has2FA = await page.$('input[name*="codigo"], input[name*="token"], #txtCodigo2FA');
      if (has2FA) {
        this.log('Autenticação de dois fatores detectada');
        return await this.handle2FA();
      }

      this.emit('login:error', { error: 'Login falhou - credenciais inválidas' });
      return false;
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      this.emit('login:error', { error: msg });
      throw error;
    }
  }

  /**
   * Login com certificado digital
   */
  protected override async loginWithCertificateA1(): Promise<boolean> {
    const page = this.getPage();

    this.log('Fazendo login com certificado A1...');

    try {
      // Clica no botão de certificado digital usando seletor ARIA
      if (this.selectors.login.certificadoBtn) {
        await this.clickSmart(this.selectors.login.certificadoBtn);
        this.log('Botão Certificado Digital clicado');
      }

      await this.waitForLoad();

      // O certificado A1 é enviado automaticamente pelo contexto do Playwright
      await page.waitForTimeout(3000);

      const loggedIn = await this.checkLoggedIn();

      if (loggedIn) {
        this.isLoggedIn = true;
        this.emit('login:success', { usuario: 'certificado_a1' });
        this.log('Login com certificado A1 realizado');
        return true;
      }

      return false;
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      this.emit('login:error', { error: msg });
      throw error;
    }
  }

  /**
   * Login com certificado A3 (físico ou nuvem)
   */
  protected override async loginWithCertificateA3Physical(): Promise<boolean> {
    const page = this.getPage();
    const auth = this.config.auth as {
      type: 'certificate_a3_physical';
      onPinRequired?: () => Promise<void>;
      pinTimeout?: number;
    };
    const timeout = auth.pinTimeout ?? 300000;

    this.log('Fazendo login com certificado A3 físico...');

    try {
      // Clica no botão de certificado usando seletor ARIA
      if (this.selectors.login.certificadoBtn) {
        await this.clickSmart(this.selectors.login.certificadoBtn);
        this.log('Botão Certificado Digital clicado');
      }

      // Notifica que PIN é necessário
      this.emit('login:pin_required', { timeout });
      await this.notify({
        type: 'pin_required',
        message: 'Insira o token USB e digite o PIN na janela do sistema',
        expiresIn: timeout / 1000,
        timestamp: new Date(),
      });

      if (auth.onPinRequired) {
        await auth.onPinRequired();
      }

      // Aguarda login
      const loggedIn = await this.waitForLoginSuccess(timeout);

      if (loggedIn) {
        this.isLoggedIn = true;
        this.emit('login:success', { usuario: 'certificado_a3_fisico' });
        this.log('Login com certificado A3 físico realizado');
        return true;
      }

      return false;
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      this.emit('login:error', { error: msg });
      throw error;
    }
  }

  /**
   * Lida com autenticação de dois fatores
   */
  private async handle2FA(): Promise<boolean> {
    const page = this.getPage();
    const timeout = 300000; // 5 minutos

    this.emit('login:approval_required', {
      type: 'login',
      message: 'Digite o código de autenticação de dois fatores',
      expiresIn: timeout / 1000,
      provider: '2fa',
    });

    await this.notify({
      type: 'approval_required',
      message: 'Digite o código 2FA enviado para seu email/celular',
      expiresIn: timeout / 1000,
      timestamp: new Date(),
    });

    // Aguarda código ser preenchido
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const loggedIn = await this.checkLoggedIn();
      if (loggedIn) {
        this.isLoggedIn = true;
        this.emit('login:success', { usuario: '2fa' });
        return true;
      }
      await page.waitForTimeout(2000);
    }

    return false;
  }

  /**
   * Verifica se está logado
   */
  protected override async checkLoggedIn(): Promise<boolean> {
    const page = this.getPage();
    try {
      // O eproc mostra link de sair quando logado
      const sairLink = await page.$('a[href*="logout"], a:has-text("Sair"), #lnkSair');
      if (sairLink) return true;

      // Verifica se tem menu de usuário
      const userMenu = await page.$('#divUsuarioLogado, .usuario-logado, [class*="user-menu"]');
      if (userMenu) return true;

      // Verifica URL
      const url = page.url();
      return url.includes('usuario_') || url.includes('painel') || url.includes('processo_');
    } catch {
      return false;
    }
  }

  // ============================================
  // Consulta de Processos
  // ============================================

  async consultarProcesso(numeroProcesso: string): Promise<Processo | null> {
    this.ensureLoggedIn();
    const page = this.getPage();

    this.log(`Consultando processo ${numeroProcesso}...`);

    try {
      // Navega para consulta usando link ARIA
      await page.getByRole('link', { name: /consulta/i }).first().click();
      await this.waitForLoad();

      // Preenche número do processo usando seletor ARIA
      await this.fillSmart(this.selectors.processo.searchInput, numeroProcesso);

      // Clica em pesquisar usando seletor ARIA
      await this.clickSmart(this.selectors.processo.searchBtn);
      await this.waitForLoad();

      // Verifica se encontrou usando seletor ARIA da tabela
      const resultado = await this.findSmart(this.selectors.processo.resultTable, 5000);
      if (!resultado) {
        this.log('Processo não encontrado');
        return null;
      }

      // Clica para abrir detalhes usando seletor ARIA
      await this.clickSmart(this.selectors.processo.detailsLink);
      await this.waitForLoad();

      return await this.extrairDadosProcesso();
    } catch (error) {
      this.log(`Erro ao consultar processo: ${error}`);
      throw error;
    }
  }

  async listarDocumentos(numeroProcesso: string): Promise<Documento[]> {
    this.ensureLoggedIn();
    const page = this.getPage();

    await this.abrirProcesso(numeroProcesso);

    const documentos: Documento[] = [];

    // Busca documentos na árvore
    const docElements = await page.$$('.arvore-documentos a, .documento-item, tr[id*="doc"]');

    for (const el of docElements) {
      try {
        const nome = await el.textContent() ?? '';
        const id = await el.getAttribute('data-id') ?? await el.getAttribute('id') ?? '';

        if (nome.trim()) {
          documentos.push({
            id,
            nome: nome.trim(),
            tipo: this.inferirTipoDocumento(nome),
            data: '',
            assinado: nome.includes('(Assinado)') || nome.includes('[✓]'),
          });
        }
      } catch {
        // Ignora
      }
    }

    return documentos;
  }

  async listarMovimentacoes(numeroProcesso: string): Promise<Movimentacao[]> {
    this.ensureLoggedIn();
    const page = this.getPage();

    await this.abrirProcesso(numeroProcesso);

    // Clica na aba de movimentações
    try {
      await page.click('a:has-text("Movimentações"), a:has-text("Andamentos"), #tabMovimentacoes');
      await this.waitForLoad();
    } catch {
      // Pode já estar na aba
    }

    const movimentacoes: Movimentacao[] = [];

    const rows = await page.$$('table.movimentacoes tbody tr, .lista-movimentacoes li');

    for (const row of rows) {
      try {
        const cells = await row.$$('td');
        if (cells.length >= 2) {
          const data = await cells[0].textContent() ?? '';
          const descricao = await cells[1].textContent() ?? '';
          movimentacoes.push({
            data: data.trim(),
            descricao: descricao.trim(),
          });
        }
      } catch {
        // Ignora
      }
    }

    return movimentacoes;
  }

  // ============================================
  // Peticionamento
  // ============================================

  async peticionar(opcoes: PeticaoOpcoes): Promise<ProtocoloResultado> {
    this.ensureLoggedIn();
    const page = this.getPage();

    this.log(`Iniciando peticionamento no processo ${opcoes.numeroProcesso}...`);
    this.emit('peticao:started', { processo: opcoes.numeroProcesso });

    try {
      // Abre o processo
      await this.abrirProcesso(opcoes.numeroProcesso);

      // Clica em peticionar usando seletor ARIA
      await this.clickSmart(this.selectors.peticao.novaBtn);
      await this.waitForLoad();

      // Seleciona tipo usando seletor ARIA
      await this.selectSmart(this.selectors.peticao.tipoSelect, { label: opcoes.tipo });
      await this.waitForLoad();

      // Preenche descrição se disponível usando seletor ARIA
      if (opcoes.descricao && this.selectors.peticao.descricaoInput) {
        try {
          await this.fillSmart(this.selectors.peticao.descricaoInput, opcoes.descricao);
        } catch {
          // Campo opcional, pode não existir
        }
      }

      // Anexa arquivos
      for (let i = 0; i < opcoes.arquivos.length; i++) {
        await this.anexarArquivo(opcoes.arquivos[i], opcoes.tiposDocumento?.[i] ?? 'Petição');
        this.emit('peticao:uploaded', {
          arquivo: opcoes.arquivos[i],
          index: i + 1,
          total: opcoes.arquivos.length,
        });
      }

      // Assina e envia
      const resultado = await this.assinarEEnviar();

      if (resultado.success) {
        this.emit('peticao:success', resultado);
      } else {
        this.emit('peticao:error', { error: resultado.error ?? 'Erro desconhecido' });
      }

      return resultado;
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      this.emit('peticao:error', { error: msg });
      throw error;
    }
  }

  private async anexarArquivo(filePath: string, tipoDocumento: string): Promise<void> {
    const page = this.getPage();

    // Clica em anexar usando seletor ARIA
    await this.clickSmart(this.selectors.peticao.anexarBtn);
    await this.waitForLoad();

    // Seleciona tipo usando seletor ARIA
    await this.selectSmart(this.selectors.peticao.tipoSelect, { label: tipoDocumento });

    // Upload usando seletor ARIA com fallback
    const fileInput = await this.findSmart(this.selectors.peticao.fileInput, 5000);
    if (fileInput) {
      await fileInput.setInputFiles(filePath);
    }

    await this.waitForLoad();

    // Confirma usando ARIA
    try {
      await page.getByRole('button', { name: /confirmar|ok/i }).first().click();
      await this.waitForLoad();
    } catch {
      // Pode não ter confirmação
    }
  }

  private async assinarEEnviar(): Promise<ProtocoloResultado> {
    const page = this.getPage();
    const authType = this.config.auth.type;

    // Clica em assinar usando seletor ARIA (tenta primeiro assinar, depois enviar)
    try {
      await this.clickSmart(this.selectors.peticao.assinarBtn);
    } catch {
      await this.clickSmart(this.selectors.peticao.enviarBtn);
    }

    // Para A3, aguarda interação
    if (authType === 'certificate_a3_physical' || authType === 'certificate_a3_cloud') {
      await this.aguardarAssinatura();
    }

    await this.waitForLoad();

    // Captura protocolo
    return await this.capturarProtocolo();
  }

  private async aguardarAssinatura(): Promise<boolean> {
    const page = this.getPage();
    const auth = this.config.auth;
    let timeout = 300000;

    if (auth.type === 'certificate_a3_physical') {
      timeout = auth.pinTimeout ?? 300000;
      this.emit('peticao:signature_required', {
        type: 'signature',
        message: 'Digite o PIN do token',
        expiresIn: timeout / 1000,
        provider: 'token_fisico',
      });
    } else if (auth.type === 'certificate_a3_cloud') {
      timeout = auth.approvalTimeout ?? 120000;
      this.emit('peticao:signature_required', {
        type: 'signature',
        message: `Aprove no app ${auth.provider}`,
        expiresIn: timeout / 1000,
        provider: auth.provider,
      });
    }

    const start = Date.now();
    while (Date.now() - start < timeout) {
      // Verifica sucesso usando seletor ARIA
      const sucesso = await this.findSmart(this.selectors.common.successAlert, 1000);
      if (sucesso) return true;

      // Verifica erro usando seletor ARIA
      const erro = await this.findSmart(this.selectors.common.errorAlert, 1000);
      if (erro) {
        const msg = await erro.textContent();
        throw new Error(`Erro na assinatura: ${msg}`);
      }

      await page.waitForTimeout(2000);
    }

    return false;
  }

  private async capturarProtocolo(): Promise<ProtocoloResultado> {
    const page = this.getPage();

    try {
      // Verifica sucesso usando seletor ARIA
      const sucesso = await this.findSmart(this.selectors.peticao.protocoloText, 5000);
      if (sucesso) {
        const texto = await sucesso.textContent() ?? '';
        const match = texto.match(/protocolo[:\s]*(\d+)/i) || texto.match(/(\d{7,})/);

        return {
          success: true,
          numeroProtocolo: match?.[1],
          dataProtocolo: new Date().toISOString(),
          mensagem: texto,
        };
      }

      return { success: false, error: 'Protocolo não identificado' };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : String(error),
      };
    }
  }

  // ============================================
  // Assinatura de Documentos
  // ============================================

  async assinarDocumentos(opcoes: AssinaturaOpcoes): Promise<AssinaturaResultado> {
    this.ensureLoggedIn();
    const page = this.getPage();

    this.log(`Assinando ${opcoes.documentos.length} documento(s)...`);
    this.emit('assinatura:started', { documentos: opcoes.documentos });

    try {
      // Seleciona documentos usando checkboxes ARIA
      for (const docId of opcoes.documentos) {
        const checkbox = page.getByRole('checkbox', { name: new RegExp(docId, 'i') });
        try {
          await checkbox.first().check({ timeout: 2000 });
        } catch {
          // Fallback para CSS
          const cssCheckbox = await page.$(`input[value="${docId}"], input[data-id="${docId}"]`);
          if (cssCheckbox) await cssCheckbox.check();
        }
      }

      // Clica em assinar usando seletor ARIA
      await this.clickSmart(this.selectors.peticao.assinarBtn);

      if (this.config.auth.type.startsWith('certificate_a3')) {
        await this.aguardarAssinatura();
      }

      await this.waitForLoad();

      this.emit('assinatura:success', {
        success: true,
        documentosAssinados: opcoes.documentos,
      });

      return { success: true, documentosAssinados: opcoes.documentos };
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      this.emit('assinatura:error', { error: msg });
      return { success: false, documentosAssinados: [], error: msg };
    }
  }

  // ============================================
  // Helpers
  // ============================================

  private async abrirProcesso(numeroProcesso: string): Promise<void> {
    const page = this.getPage();

    const currentUrl = page.url();
    if (currentUrl.includes(numeroProcesso.replace(/[.\-\/]/g, ''))) {
      return;
    }

    // Navega para consulta usando ARIA
    await page.getByRole('link', { name: /consulta/i }).first().click();
    await this.waitForLoad();

    // Preenche e pesquisa usando seletores ARIA
    await this.fillSmart(this.selectors.processo.searchInput, numeroProcesso);
    await this.clickSmart(this.selectors.processo.searchBtn);
    await this.waitForLoad();

    // Abre detalhes usando seletor ARIA
    await this.clickSmart(this.selectors.processo.detailsLink);
    await this.waitForLoad();
  }

  private async extrairDadosProcesso(): Promise<Processo> {
    const page = this.getPage();

    const numero = await page.$eval('.numero-processo, #lblNumProcesso', el => el.textContent?.trim() ?? '').catch(() => '');
    const classe = await page.$eval('.classe-processo, #lblClasse', el => el.textContent?.trim() ?? '').catch(() => '');
    const assunto = await page.$eval('.assunto-processo, #lblAssunto', el => el.textContent?.trim() ?? '').catch(() => '');

    return {
      numero,
      tribunal: this.tribunalName,
      classe,
      assunto,
      dataDistribuicao: '',
      partes: [],
      movimentacoes: [],
      documentos: [],
      status: 'ativo',
    };
  }

  private inferirTipoDocumento(nome: string): string {
    const lower = nome.toLowerCase();
    if (lower.includes('petição')) return 'Petição';
    if (lower.includes('sentença')) return 'Sentença';
    if (lower.includes('despacho')) return 'Despacho';
    if (lower.includes('decisão')) return 'Decisão';
    return 'Documento';
  }
}
