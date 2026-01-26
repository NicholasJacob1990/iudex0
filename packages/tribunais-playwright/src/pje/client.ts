/**
 * Cliente PJe (Processo Judicial Eletrônico)
 * Suporta login com senha e certificado digital
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
import { PJE_SELECTORS } from './selectors.js';

export interface PJeClientConfig extends TribunalClientConfig {
  /** Instância do PJe (ex: 1g, 2g) */
  instancia?: '1g' | '2g';
}

export class PJeClient extends BaseTribunalClient {
  protected tribunalName = 'PJe';
  protected selectors: TribunalSelectors = PJE_SELECTORS;

  constructor(config: PJeClientConfig) {
    super(config);
  }

  // ============================================
  // Consulta de Processos
  // ============================================

  /**
   * Consulta processo pelo número
   */
  async consultarProcesso(numeroProcesso: string): Promise<Processo | null> {
    this.ensureLoggedIn();
    const page = this.getPage();

    this.log(`Consultando processo ${numeroProcesso}...`);

    try {
      // Navega para consulta
      await this.navegarParaConsulta();

      // Preenche número do processo
      await this.fillSmart(this.selectors.processo.searchInput, numeroProcesso);

      // Clica em pesquisar
      await this.clickSmart(this.selectors.processo.searchBtn);

      await this.waitForLoad();

      // Verifica se encontrou
      const resultados = await page.$$('table tbody tr, .resultado-consulta');
      if (resultados.length === 0) {
        this.log('Processo não encontrado');
        return null;
      }

      // Clica no primeiro resultado
      await this.clickSmart(this.selectors.processo.detailsLink);
      await this.waitForLoad();

      // Extrai dados do processo
      return await this.extrairDadosProcesso();
    } catch (error) {
      this.log(`Erro ao consultar processo: ${error}`);
      throw error;
    }
  }

  /**
   * Lista documentos do processo
   */
  async listarDocumentos(numeroProcesso: string): Promise<Documento[]> {
    this.ensureLoggedIn();
    const page = this.getPage();

    await this.abrirProcesso(numeroProcesso);

    const documentos: Documento[] = [];

    // Busca na árvore de documentos
    const docElements = await page.$$('[class*="documento"], .arvore-documento a, .lista-documentos li');

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
            assinado: nome.includes('(Assinado)') || nome.includes('[A]'),
          });
        }
      } catch {
        // Ignora elementos inválidos
      }
    }

    return documentos;
  }

  /**
   * Lista movimentações do processo
   */
  async listarMovimentacoes(numeroProcesso: string): Promise<Movimentacao[]> {
    this.ensureLoggedIn();
    const page = this.getPage();

    await this.abrirProcesso(numeroProcesso);

    // Clica na aba de movimentações
    try {
      await page.getByRole('tab', { name: /movimenta/i }).click();
      await this.waitForLoad();
    } catch {
      // Pode já estar na aba
    }

    const movimentacoes: Movimentacao[] = [];

    const rows = await page.$$('table tbody tr, .lista-movimentacoes li, .movimentacao-item');

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
        } else {
          const texto = await row.textContent() ?? '';
          const match = texto.match(/(\d{2}\/\d{2}\/\d{4})\s*[-:]\s*(.*)/);
          if (match) {
            movimentacoes.push({
              data: match[1],
              descricao: match[2].trim(),
            });
          }
        }
      } catch {
        // Ignora linhas inválidas
      }
    }

    return movimentacoes;
  }

  // ============================================
  // Peticionamento
  // ============================================

  /**
   * Peticiona em um processo
   * Para certificado A3, aguarda aprovação do usuário
   */
  async peticionar(opcoes: PeticaoOpcoes): Promise<ProtocoloResultado> {
    this.ensureLoggedIn();
    const page = this.getPage();

    this.log(`Iniciando peticionamento no processo ${opcoes.numeroProcesso}...`);
    this.emit('peticao:started', { processo: opcoes.numeroProcesso });

    try {
      // 1. Abre o processo
      await this.abrirProcesso(opcoes.numeroProcesso);

      // 2. Clica em nova petição
      await this.clickSmart(this.selectors.peticao.novaBtn);
      await this.waitForLoad();

      // 3. Seleciona tipo de petição
      await this.selectSmart(this.selectors.peticao.tipoSelect, { label: opcoes.tipo });
      await this.waitForLoad();

      // 4. Preenche descrição (se disponível)
      if (opcoes.descricao && this.selectors.peticao.descricaoInput) {
        await this.fillSmart(this.selectors.peticao.descricaoInput, opcoes.descricao);
      }

      // 5. Anexa arquivos
      for (let i = 0; i < opcoes.arquivos.length; i++) {
        const arquivo = opcoes.arquivos[i];
        const tipoDoc = opcoes.tiposDocumento?.[i] ?? 'Petição';

        await this.anexarArquivo(arquivo, tipoDoc);

        this.emit('peticao:uploaded', {
          arquivo,
          index: i + 1,
          total: opcoes.arquivos.length,
        });
      }

      // 6. Assinar e enviar
      const resultado = await this.assinarEEnviar();

      if (resultado.success) {
        this.emit('peticao:success', resultado);
        this.log(`Petição protocolada: ${resultado.numeroProtocolo}`);
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

  /**
   * Anexa arquivo à petição
   */
  protected async anexarArquivo(filePath: string, tipoDocumento: string): Promise<void> {
    const page = this.getPage();

    // Clica em anexar
    await this.clickSmart(this.selectors.peticao.anexarBtn);
    await this.waitForLoad();

    // Seleciona tipo de documento
    try {
      await page.getByRole('combobox', { name: /tipo/i }).selectOption({ label: tipoDocumento });
    } catch {
      // Tenta fallback
      await page.selectOption('select[name*="tipo"], #tipoDocumento', { label: tipoDocumento });
    }

    // Upload do arquivo
    const fileInput = await page.$('input[type="file"]');
    if (fileInput) {
      await fileInput.setInputFiles(filePath);
    } else {
      throw new Error('Campo de upload não encontrado');
    }

    await this.waitForLoad();

    // Confirma anexo
    try {
      await page.getByRole('button', { name: /confirmar|adicionar|ok/i }).click();
      await this.waitForLoad();
    } catch {
      // Pode não ter botão de confirmação
    }
  }

  /**
   * Assina e envia a petição
   * Para A3, aguarda interação do usuário
   */
  protected async assinarEEnviar(): Promise<ProtocoloResultado> {
    const page = this.getPage();
    const authType = this.config.auth.type;

    // Clica em assinar
    await this.clickSmart(this.selectors.peticao.assinarBtn);

    // Para certificado A3, aguarda interação
    if (authType === 'certificate_a3_physical' || authType === 'certificate_a3_cloud') {
      const resultado = await this.aguardarAssinatura();
      if (!resultado) {
        return {
          success: false,
          error: 'Timeout aguardando assinatura',
        };
      }
    }

    await this.waitForLoad();

    // Clica em enviar (se separado de assinar)
    try {
      await this.clickSmart(this.selectors.peticao.enviarBtn);
      await this.waitForLoad();
    } catch {
      // Pode já ter enviado junto com assinar
    }

    // Captura protocolo
    return await this.capturarProtocolo();
  }

  /**
   * Aguarda assinatura do usuário (A3 físico ou nuvem)
   */
  protected async aguardarAssinatura(): Promise<boolean> {
    const page = this.getPage();
    const auth = this.config.auth;

    let timeout = 300000; // 5 min padrão
    let approvalInfo: ApprovalInfo;

    if (auth.type === 'certificate_a3_physical') {
      timeout = auth.pinTimeout ?? 300000;
      approvalInfo = {
        type: 'signature',
        message: 'Digite o PIN do seu token na janela do sistema',
        expiresIn: timeout / 1000,
        provider: 'token_fisico',
      };

      this.emit('peticao:signature_required', approvalInfo);
      await this.notify({
        type: 'signature_pending',
        message: approvalInfo.message,
        expiresIn: approvalInfo.expiresIn,
        data: approvalInfo,
        timestamp: new Date(),
      });

      if (auth.onPinRequired) {
        await auth.onPinRequired();
      }
    } else if (auth.type === 'certificate_a3_cloud') {
      timeout = auth.approvalTimeout ?? 120000;
      approvalInfo = {
        type: 'signature',
        message: `Aprove a assinatura no app ${auth.provider} do seu celular`,
        expiresIn: timeout / 1000,
        provider: auth.provider,
      };

      this.emit('peticao:signature_required', approvalInfo);
      await this.notify({
        type: 'signature_pending',
        message: approvalInfo.message,
        expiresIn: approvalInfo.expiresIn,
        data: approvalInfo,
        timestamp: new Date(),
      });

      if (auth.onApprovalRequired) {
        await auth.onApprovalRequired(approvalInfo);
      }
    }

    // Polling para verificar sucesso
    const start = Date.now();

    while (Date.now() - start < timeout) {
      // Verifica sucesso
      const sucesso = await page.$('[class*="sucesso"], .alert-success, .documento-assinado');
      if (sucesso) {
        await this.notify({
          type: 'signature_success',
          message: 'Documento assinado com sucesso',
          timestamp: new Date(),
        });
        return true;
      }

      // Verifica erro
      const erro = await page.$('[class*="erro"], .alert-danger, .alert-error');
      if (erro) {
        const msg = await erro.textContent();
        await this.notify({
          type: 'signature_error',
          message: `Erro na assinatura: ${msg}`,
          timestamp: new Date(),
        });
        throw new Error(`Erro na assinatura: ${msg}`);
      }

      await page.waitForTimeout(2000);
    }

    return false;
  }

  /**
   * Captura número do protocolo após envio
   */
  protected async capturarProtocolo(): Promise<ProtocoloResultado> {
    const page = this.getPage();

    try {
      // Tenta encontrar número do protocolo
      const protocoloEl = await this.findSmart(this.selectors.peticao.protocoloText, 10000);

      if (protocoloEl) {
        const texto = await protocoloEl.textContent() ?? '';
        const match = texto.match(/(\d{7,}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}|\d+)/);

        if (match) {
          return {
            success: true,
            numeroProtocolo: match[1],
            dataProtocolo: new Date().toISOString(),
          };
        }
      }

      // Fallback: busca na página
      const pageText = await page.textContent('body') ?? '';
      const protocoloMatch = pageText.match(/protocolo[:\s]*(\d+)/i);

      if (protocoloMatch) {
        return {
          success: true,
          numeroProtocolo: protocoloMatch[1],
          dataProtocolo: new Date().toISOString(),
        };
      }

      // Verifica se tem mensagem de sucesso
      const sucessoEl = await page.$('[class*="sucesso"], .alert-success');
      if (sucessoEl) {
        return {
          success: true,
          mensagem: await sucessoEl.textContent() ?? 'Petição enviada com sucesso',
          dataProtocolo: new Date().toISOString(),
        };
      }

      return {
        success: false,
        error: 'Não foi possível identificar o protocolo',
      };
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

  /**
   * Assina documentos no processo
   */
  async assinarDocumentos(opcoes: AssinaturaOpcoes): Promise<AssinaturaResultado> {
    this.ensureLoggedIn();
    const page = this.getPage();

    this.log(`Assinando ${opcoes.documentos.length} documento(s)...`);
    this.emit('assinatura:started', { documentos: opcoes.documentos });

    try {
      // Seleciona documentos
      for (const docId of opcoes.documentos) {
        const checkbox = await page.$(`input[value="${docId}"], input[data-id="${docId}"]`);
        if (checkbox) {
          await checkbox.check();
        }
      }

      // Clica em assinar
      await page.getByRole('button', { name: /assinar/i }).click();

      // Aguarda assinatura (para A3)
      if (this.config.auth.type.startsWith('certificate_a3')) {
        const sucesso = await this.aguardarAssinaturaDocumentos();
        if (!sucesso) {
          this.emit('assinatura:error', { error: 'Timeout aguardando assinatura' });
          return {
            success: false,
            documentosAssinados: [],
            error: 'Timeout aguardando assinatura',
          };
        }
      }

      await this.waitForLoad();

      this.emit('assinatura:success', {
        success: true,
        documentosAssinados: opcoes.documentos,
      });

      return {
        success: true,
        documentosAssinados: opcoes.documentos,
      };
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      this.emit('assinatura:error', { error: msg });
      return {
        success: false,
        documentosAssinados: [],
        error: msg,
      };
    }
  }

  protected async aguardarAssinaturaDocumentos(): Promise<boolean> {
    // Reutiliza lógica de aguardarAssinatura
    return await this.aguardarAssinatura();
  }

  // ============================================
  // Helpers
  // ============================================

  protected async navegarParaConsulta(): Promise<void> {
    const page = this.getPage();

    // Tenta menu de consulta
    try {
      await page.getByRole('link', { name: /consulta|pesquisa|processo/i }).first().click();
      await this.waitForLoad();
    } catch {
      // Navega diretamente
      const baseUrl = this.config.baseUrl.replace(/\/$/, '');
      await page.goto(`${baseUrl}/ConsultaProcesso/listView.seam`);
      await this.waitForLoad();
    }
  }

  protected async abrirProcesso(numeroProcesso: string): Promise<void> {
    const page = this.getPage();

    // Verifica se já está no processo
    const currentUrl = page.url();
    if (currentUrl.includes(numeroProcesso.replace(/[.\-\/]/g, ''))) {
      return;
    }

    await this.navegarParaConsulta();
    await this.fillSmart(this.selectors.processo.searchInput, numeroProcesso);
    await this.clickSmart(this.selectors.processo.searchBtn);
    await this.waitForLoad();

    // Clica no resultado
    await this.clickSmart(this.selectors.processo.detailsLink);
    await this.waitForLoad();
  }

  protected async extrairDadosProcesso(): Promise<Processo> {
    const page = this.getPage();

    // Extrai dados básicos
    const numero = await page.$eval('[class*="numero-processo"], .processo-numero', el => el.textContent?.trim() ?? '').catch(() => '');
    const classe = await page.$eval('[class*="classe"], .processo-classe', el => el.textContent?.trim() ?? '').catch(() => '');
    const assunto = await page.$eval('[class*="assunto"], .processo-assunto', el => el.textContent?.trim() ?? '').catch(() => '');

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

  protected inferirTipoDocumento(nome: string): string {
    const lower = nome.toLowerCase();
    if (lower.includes('petição')) return 'Petição';
    if (lower.includes('sentença')) return 'Sentença';
    if (lower.includes('despacho')) return 'Despacho';
    if (lower.includes('decisão')) return 'Decisão';
    if (lower.includes('acórdão')) return 'Acórdão';
    if (lower.includes('certidão')) return 'Certidão';
    if (lower.includes('ofício')) return 'Ofício';
    if (lower.includes('ata')) return 'Ata';
    return 'Documento';
  }
}
