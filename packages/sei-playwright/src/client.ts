/**
 * Cliente híbrido SEI - usa SOAP quando disponível, fallback para browser
 */

import { SEISoapClient, type SOAPConfig } from './soap/client.js';
import { SEIBrowserClient } from './browser/client.js';
import type {
  SEIConfig,
  CreateProcessOptions,
  CreateDocumentOptions,
  ForwardOptions,
  RetornoGerarProcedimento,
  RetornoConsultaProcedimento,
  Serie,
  TipoProcedimento,
  Unidade,
  Usuario,
} from './types.js';

export type SEIClientMode = 'auto' | 'soap' | 'browser';

export interface SEIClientOptions extends SEIConfig {
  /** Modo de operação: auto (tenta SOAP, fallback browser), soap, browser */
  mode?: SEIClientMode;
}

/**
 * Cliente principal do SEI - híbrido (SOAP + Browser)
 *
 * @example
 * ```typescript
 * // Modo automático (recomendado)
 * const sei = new SEIClient({
 *   baseUrl: 'https://sei.mg.gov.br',
 *   soap: {
 *     siglaSistema: 'MEU_SISTEMA',
 *     identificacaoServico: 'MinhaChave123',
 *   },
 *   browser: {
 *     usuario: 'meu.usuario',
 *     senha: 'minhaSenha',
 *   },
 *   playwright: { headless: true },
 * });
 *
 * await sei.init();
 *
 * // Operações - usa SOAP quando possível, browser como fallback
 * const tipos = await sei.listProcessTypes();
 * await sei.openProcess('5030.01.0002527/2025-32');
 * await sei.createDocument({ idSerie: 'Despacho', descricao: 'Teste' });
 *
 * await sei.close();
 * ```
 */
export class SEIClient {
  private config: SEIClientOptions;
  private soapClient: SEISoapClient | null = null;
  private browserClient: SEIBrowserClient | null = null;
  private soapAvailable = false;
  private currentIdUnidade: string | null = null;

  constructor(config: SEIClientOptions) {
    this.config = {
      mode: 'auto',
      ...config,
    };
  }

  /** Modo de operação atual */
  get mode(): SEIClientMode {
    return this.config.mode ?? 'auto';
  }

  /** SOAP está disponível */
  get hasSoap(): boolean {
    return this.soapAvailable;
  }

  /** Browser está disponível */
  get hasBrowser(): boolean {
    return this.browserClient?.isReady ?? false;
  }

  /** Inicializa clientes */
  async init(): Promise<void> {
    const mode = this.mode;

    // Inicializa SOAP se configurado
    if ((mode === 'auto' || mode === 'soap') && this.config.soap) {
      try {
        this.soapClient = new SEISoapClient({
          baseUrl: this.config.baseUrl,
          ...this.config.soap,
        });
        await this.soapClient.connect();
        this.soapAvailable = true;
      } catch (err) {
        console.warn('SOAP não disponível:', err);
        this.soapAvailable = false;
      }
    }

    // Inicializa Browser se necessário
    if (mode === 'auto' || mode === 'browser' || !this.soapAvailable) {
      this.browserClient = new SEIBrowserClient(this.config);
      await this.browserClient.init();
    }
  }

  /** Fecha todos os clientes */
  async close(): Promise<void> {
    await this.browserClient?.close();
    this.browserClient = null;
    this.soapClient = null;
    this.soapAvailable = false;
  }

  /** Define a unidade atual para operações SOAP */
  setUnidade(idUnidade: string): void {
    this.currentIdUnidade = idUnidade;
  }

  // ============================================
  // Autenticação (Browser only)
  // ============================================

  /** Login no SEI via browser */
  async login(usuario?: string, senha?: string, orgao?: string): Promise<boolean> {
    if (!this.browserClient) {
      throw new Error('Browser client não disponível');
    }
    return this.browserClient.login(usuario, senha, orgao);
  }

  /** Logout do SEI */
  async logout(): Promise<void> {
    await this.browserClient?.logout();
  }

  /** Verifica se está logado */
  async isLoggedIn(): Promise<boolean> {
    return (await this.browserClient?.isLoggedIn()) ?? false;
  }

  // ============================================
  // Listagens
  // ============================================

  /** Lista tipos de processo */
  async listProcessTypes(): Promise<TipoProcedimento[]> {
    // Tenta SOAP primeiro
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      try {
        return await this.soapClient.listarTiposProcedimento(this.currentIdUnidade);
      } catch (err) {
        console.warn('SOAP listarTiposProcedimento falhou, tentando browser:', err);
      }
    }

    // Fallback browser
    if (this.browserClient) {
      const tipos = await this.browserClient.listProcessTypes();
      return tipos.map((t) => ({
        IdTipoProcedimento: t.id,
        Nome: t.nome,
      }));
    }

    throw new Error('Nenhum cliente disponível');
  }

  /** Lista tipos de documento (séries) */
  async listDocumentTypes(idTipoProcedimento?: string): Promise<Serie[]> {
    // Tenta SOAP primeiro
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      try {
        return await this.soapClient.listarSeries(this.currentIdUnidade, idTipoProcedimento);
      } catch (err) {
        console.warn('SOAP listarSeries falhou, tentando browser:', err);
      }
    }

    // Fallback browser
    if (this.browserClient) {
      const tipos = await this.browserClient.listDocumentTypes();
      return tipos.map((t) => ({
        IdSerie: t.id,
        Nome: t.nome,
      }));
    }

    throw new Error('Nenhum cliente disponível');
  }

  /** Lista unidades */
  async listUnits(idTipoProcedimento?: string): Promise<Unidade[]> {
    // Tenta SOAP primeiro
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      try {
        return await this.soapClient.listarUnidades(this.currentIdUnidade, idTipoProcedimento);
      } catch (err) {
        console.warn('SOAP listarUnidades falhou, tentando browser:', err);
      }
    }

    // Fallback browser
    if (this.browserClient) {
      const unidades = await this.browserClient.listUnits();
      return unidades.map((u) => ({
        IdUnidade: u.id,
        Sigla: u.sigla,
        Descricao: u.descricao,
      }));
    }

    throw new Error('Nenhum cliente disponível');
  }

  /** Lista usuários da unidade */
  async listUsers(): Promise<Usuario[]> {
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      return this.soapClient.listarUsuarios(this.currentIdUnidade);
    }

    // Browser não tem acesso à lista de usuários diretamente
    throw new Error('Listagem de usuários requer SOAP');
  }

  /** Lista andamentos do processo */
  async listAndamentos(
    numeroProcesso: string,
    options?: { retornarAtributos?: boolean }
  ): Promise<Array<{ data: string; unidade: string; usuario: string; descricao: string }>> {
    // Tenta SOAP primeiro
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      try {
        const andamentos = await this.soapClient.listarAndamentos(
          this.currentIdUnidade,
          numeroProcesso,
          options?.retornarAtributos
        );
        return andamentos.map((a) => ({
          data: a.DataHora,
          unidade: a.Unidade?.Sigla ?? '',
          usuario: a.Usuario?.Nome ?? '',
          descricao: a.Descricao,
        }));
      } catch (err) {
        console.warn('SOAP listarAndamentos falhou, tentando browser:', err);
      }
    }

    // Fallback browser
    if (this.browserClient) {
      return this.browserClient.listAndamentos(numeroProcesso);
    }

    throw new Error('Nenhum cliente disponível');
  }

  // ============================================
  // Processos
  // ============================================

  /** Abre processo */
  async openProcess(numeroProcesso: string): Promise<boolean> {
    if (this.browserClient) {
      return this.browserClient.openProcess(numeroProcesso);
    }
    throw new Error('Browser client não disponível');
  }

  /** Consulta processo */
  async getProcess(
    protocoloProcedimento: string,
    options?: {
      assuntos?: boolean;
      interessados?: boolean;
      observacoes?: boolean;
      andamentos?: boolean;
      relacionados?: boolean;
    }
  ): Promise<RetornoConsultaProcedimento> {
    // Tenta SOAP primeiro
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      try {
        return await this.soapClient.consultarProcedimento(
          this.currentIdUnidade,
          protocoloProcedimento,
          options?.assuntos,
          options?.interessados,
          options?.observacoes,
          true, // andamento geração
          true, // andamento conclusão
          true, // último andamento
          true, // unidades aberto
          options?.relacionados,
          true // anexados
        );
      } catch (err) {
        console.warn('SOAP consultarProcedimento falhou, tentando browser:', err);
      }
    }

    // Fallback browser
    if (this.browserClient) {
      const details = await this.browserClient.getProcessDetails(protocoloProcedimento);
      if (details) {
        return {
          IdProcedimento: details.id,
          ProcedimentoFormatado: details.numero,
          Especificacao: details.especificacao,
          DataAutuacao: details.dataAutuacao,
          LinkAcesso: `${this.config.baseUrl}/sei/controlador.php?acao=procedimento_trabalhar&id_procedimento=${details.id}`,
          TipoProcedimento: { IdTipoProcedimento: '', Nome: details.tipo },
          AndamentoGeracao: { IdAndamento: '', IdTarefa: '', IdTarefaModulo: '', Descricao: '', DataHora: '', Unidade: { IdUnidade: '', Sigla: '', Descricao: '' }, Usuario: { IdUsuario: '', Sigla: '', Nome: '' } },
          UltimoAndamento: { IdAndamento: '', IdTarefa: '', IdTarefaModulo: '', Descricao: '', DataHora: '', Unidade: { IdUnidade: '', Sigla: '', Descricao: '' }, Usuario: { IdUsuario: '', Sigla: '', Nome: '' } },
          UnidadesProcedimentoAberto: details.unidadesAbertas.map((u) => ({ IdUnidade: '', Sigla: u, Descricao: u })),
          Assuntos: [],
          Interessados: details.interessados.map((i) => ({ Sigla: i, Nome: i })),
        };
      }
    }

    throw new Error('Nenhum cliente disponível');
  }

  /** Cria processo */
  async createProcess(options: CreateProcessOptions): Promise<RetornoGerarProcedimento | null> {
    // Tenta SOAP primeiro
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      try {
        return await this.soapClient.gerarProcedimento(this.currentIdUnidade, {
          IdTipoProcedimento: options.tipoProcedimento,
          Especificacao: options.especificacao,
          Assuntos: options.assuntos.map((a) => ({ CodigoEstruturado: a })),
          Interessados: options.interessados?.map((i) => ({ Sigla: i, Nome: i })),
          Observacao: options.observacao,
          NivelAcesso: options.nivelAcesso ?? 0,
          IdHipoteseLegal: options.hipoteseLegal,
        });
      } catch (err) {
        console.warn('SOAP gerarProcedimento falhou, tentando browser:', err);
      }
    }

    // Fallback browser
    if (this.browserClient) {
      const result = await this.browserClient.createProcess({
        tipoProcedimento: options.tipoProcedimento,
        especificacao: options.especificacao,
        assuntos: options.assuntos,
        interessados: options.interessados,
        observacao: options.observacao,
        nivelAcesso: options.nivelAcesso,
        hipoteseLegal: options.hipoteseLegal,
      });

      if (result) {
        return {
          IdProcedimento: result.id,
          ProcedimentoFormatado: result.numero,
          LinkAcesso: `${this.config.baseUrl}/sei/controlador.php?acao=procedimento_trabalhar&id_procedimento=${result.id}`,
        };
      }
    }

    throw new Error('Nenhum cliente disponível para criar processo');
  }

  /** Tramita processo */
  async forwardProcess(
    numeroProcesso: string,
    options: ForwardOptions
  ): Promise<boolean> {
    // Tenta SOAP primeiro
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      try {
        return await this.soapClient.enviarProcesso(
          this.currentIdUnidade,
          numeroProcesso,
          options.unidadesDestino,
          options.manterAberto,
          options.removerAnotacoes,
          options.enviarEmailNotificacao,
          options.dataRetornoProgramado,
          options.diasRetornoProgramado,
          undefined, // diasUteis
          options.sinReabrir
        );
      } catch (err) {
        console.warn('SOAP enviarProcesso falhou, tentando browser:', err);
      }
    }

    // Fallback browser
    if (this.browserClient) {
      await this.browserClient.openProcess(numeroProcesso);
      return this.browserClient.forwardProcess(options);
    }

    throw new Error('Nenhum cliente disponível');
  }

  /** Conclui processo */
  async concludeProcess(numeroProcesso: string): Promise<boolean> {
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      return this.soapClient.concluirProcesso(this.currentIdUnidade, numeroProcesso);
    }

    if (this.browserClient) {
      await this.browserClient.openProcess(numeroProcesso);
      return this.browserClient.concludeProcess();
    }

    throw new Error('Nenhum cliente disponível');
  }

  /** Reabre processo */
  async reopenProcess(numeroProcesso: string): Promise<boolean> {
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      return this.soapClient.reabrirProcesso(this.currentIdUnidade, numeroProcesso);
    }

    if (this.browserClient) {
      await this.browserClient.openProcess(numeroProcesso);
      return this.browserClient.reopenProcess();
    }

    throw new Error('Nenhum cliente disponível');
  }

  /** Anexa processo a outro */
  async anexarProcesso(
    processoPrincipal: string,
    processoAnexado: string
  ): Promise<boolean> {
    // Tenta SOAP primeiro
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      try {
        return await this.soapClient.anexarProcesso(
          this.currentIdUnidade,
          processoPrincipal,
          processoAnexado
        );
      } catch (err) {
        console.warn('SOAP anexarProcesso falhou, tentando browser:', err);
      }
    }

    // Fallback browser
    if (this.browserClient) {
      return this.browserClient.anexarProcesso(processoPrincipal, processoAnexado);
    }

    throw new Error('Nenhum cliente disponível');
  }

  /** Relaciona dois processos */
  async relacionarProcesso(
    processo1: string,
    processo2: string
  ): Promise<boolean> {
    // Tenta SOAP primeiro
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      try {
        return await this.soapClient.relacionarProcesso(
          this.currentIdUnidade,
          processo1,
          processo2
        );
      } catch (err) {
        console.warn('SOAP relacionarProcesso falhou, tentando browser:', err);
      }
    }

    // Fallback browser
    if (this.browserClient) {
      return this.browserClient.relacionarProcesso(processo1, processo2);
    }

    throw new Error('Nenhum cliente disponível');
  }

  /** Atribui processo a um usuário */
  async atribuirProcesso(
    numeroProcesso: string,
    usuario: string,
    sinReabrir?: boolean
  ): Promise<boolean> {
    // Tenta SOAP primeiro
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      try {
        return await this.soapClient.atribuirProcesso(
          this.currentIdUnidade,
          numeroProcesso,
          usuario,
          sinReabrir
        );
      } catch (err) {
        console.warn('SOAP atribuirProcesso falhou, tentando browser:', err);
      }
    }

    // Fallback browser
    if (this.browserClient) {
      return this.browserClient.atribuirProcesso(numeroProcesso, usuario);
    }

    throw new Error('Nenhum cliente disponível');
  }

  // ============================================
  // Documentos
  // ============================================

  /** Lista documentos do processo atual */
  async listDocuments(): Promise<Array<{ id: string; titulo: string; tipo: string }>> {
    if (this.browserClient) {
      return this.browserClient.listDocuments();
    }
    throw new Error('Browser client não disponível');
  }

  /** Cria documento interno */
  async createDocument(
    numeroProcesso: string,
    options: CreateDocumentOptions
  ): Promise<string | null> {
    // SOAP para documento gerado
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      const doc = await this.soapClient.incluirDocumento(this.currentIdUnidade, {
        Tipo: options.tipo ?? 'G',
        IdProcedimento: numeroProcesso,
        IdSerie: options.idSerie,
        Numero: options.numero,
        Descricao: options.descricao,
        Interessados: options.interessados?.map((i) => ({ Sigla: i, Nome: i })),
        Destinatarios: options.destinatarios?.map((d) => ({ Sigla: d, Nome: d })),
        Observacao: options.observacao,
        NivelAcesso: options.nivelAcesso ?? 0,
        IdHipoteseLegal: options.hipoteseLegal,
        NomeArquivo: options.nomeArquivo,
        Conteudo: options.conteudoBase64,
      });
      return doc.IdDocumento;
    }

    // Fallback browser
    if (this.browserClient) {
      await this.browserClient.openProcess(numeroProcesso);
      return this.browserClient.createDocument(options);
    }

    throw new Error('Nenhum cliente disponível');
  }

  /** Upload de documento externo */
  async uploadDocument(
    numeroProcesso: string,
    nomeArquivo: string,
    conteudoBase64: string,
    options?: Partial<CreateDocumentOptions>
  ): Promise<string | null> {
    // SOAP
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      const doc = await this.soapClient.incluirDocumento(this.currentIdUnidade, {
        Tipo: 'R', // Recebido/Externo
        IdProcedimento: numeroProcesso,
        IdSerie: options?.idSerie ?? 'Externo',
        Descricao: options?.descricao,
        Observacao: options?.observacao,
        NivelAcesso: options?.nivelAcesso ?? 0,
        IdHipoteseLegal: options?.hipoteseLegal,
        NomeArquivo: nomeArquivo,
        Conteudo: conteudoBase64,
      });
      return doc.IdDocumento;
    }

    // Fallback browser
    if (this.browserClient) {
      await this.browserClient.openProcess(numeroProcesso);
      return this.browserClient.uploadDocument(nomeArquivo, conteudoBase64, options);
    }

    throw new Error('Nenhum cliente disponível');
  }

  /** Assina documento */
  async signDocument(senha: string, cargo?: string): Promise<boolean> {
    if (this.browserClient) {
      return this.browserClient.signDocument(senha, cargo);
    }
    throw new Error('Assinatura requer browser client');
  }

  /** Cancela documento */
  async cancelDocument(idDocumento: string, motivo: string): Promise<boolean> {
    // Tenta SOAP primeiro
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      try {
        return await this.soapClient.cancelarDocumento(
          this.currentIdUnidade,
          idDocumento,
          motivo
        );
      } catch (err) {
        console.warn('SOAP cancelarDocumento falhou, tentando browser:', err);
      }
    }

    // Fallback browser
    if (this.browserClient) {
      return this.browserClient.cancelDocument(idDocumento, motivo);
    }

    throw new Error('Nenhum cliente disponível');
  }

  /** Consulta detalhes do documento */
  async getDocumentDetails(idDocumento: string): Promise<{
    id: string;
    numero: string;
    tipo: string;
    data: string;
    assinaturas: Array<{ nome: string; cargo: string; data: string }>;
  } | null> {
    // SOAP
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      try {
        const doc = await this.soapClient.consultarDocumento(
          this.currentIdUnidade,
          idDocumento,
          true, // andamento geração
          true, // assinaturas
          true, // publicação
          true  // campos
        );
        return {
          id: doc.IdDocumento,
          numero: doc.DocumentoFormatado,
          tipo: doc.Serie?.Nome ?? '',
          data: doc.Data,
          assinaturas: doc.Assinaturas?.map((a) => ({
            nome: a.Nome,
            cargo: a.CargoFuncao,
            data: a.DataHora,
          })) ?? [],
        };
      } catch (err) {
        console.warn('SOAP consultarDocumento falhou, tentando browser:', err);
      }
    }

    // Fallback browser
    if (this.browserClient) {
      return this.browserClient.getDocumentDetails(idDocumento);
    }

    throw new Error('Nenhum cliente disponível');
  }

  // ============================================
  // Blocos de Assinatura
  // ============================================

  /** Lista blocos de assinatura */
  async listBlocos(): Promise<
    Array<{
      id: string;
      descricao: string;
      quantidade: number;
      unidade: string;
    }>
  > {
    if (this.browserClient) {
      return this.browserClient.listBlocos();
    }
    throw new Error('Browser client não disponível');
  }

  /** Cria bloco de assinatura */
  async createBloco(
    descricao: string,
    tipo: 'assinatura' | 'reuniao' | 'interno' = 'assinatura',
    unidades?: string[],
    documentos?: string[]
  ): Promise<string | null> {
    // SOAP
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      try {
        const tipoMap = { assinatura: 'A' as const, reuniao: 'R' as const, interno: 'I' as const };
        const bloco = await this.soapClient.gerarBloco(
          this.currentIdUnidade,
          tipoMap[tipo],
          descricao,
          unidades,
          documentos,
          false
        );
        return bloco.IdBloco;
      } catch (err) {
        console.warn('SOAP gerarBloco falhou, tentando browser:', err);
      }
    }

    // Fallback browser
    if (this.browserClient) {
      return this.browserClient.createBloco(descricao, tipo);
    }

    throw new Error('Nenhum cliente disponível');
  }

  /** Consulta bloco */
  async getBloco(idBloco: string): Promise<{
    id: string;
    descricao: string;
    documentos: string[];
  } | null> {
    // SOAP
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      try {
        const bloco = await this.soapClient.consultarBloco(
          this.currentIdUnidade,
          idBloco,
          true
        );
        return {
          id: bloco.IdBloco,
          descricao: bloco.Descricao,
          documentos: bloco.Documentos?.map((d) => d.IdProtocolo) ?? [],
        };
      } catch (err) {
        console.warn('SOAP consultarBloco falhou:', err);
      }
    }

    // Browser não tem consulta direta de bloco
    return null;
  }

  /** Adiciona documento ao bloco */
  async addDocumentoToBloco(idBloco: string, idDocumento: string): Promise<boolean> {
    // SOAP
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      try {
        return await this.soapClient.incluirDocumentoBloco(
          this.currentIdUnidade,
          idBloco,
          idDocumento
        );
      } catch (err) {
        console.warn('SOAP incluirDocumentoBloco falhou, tentando browser:', err);
      }
    }

    // Fallback browser
    if (this.browserClient) {
      return this.browserClient.addDocumentoToBloco(idBloco, idDocumento);
    }

    throw new Error('Nenhum cliente disponível');
  }

  /** Remove documento do bloco */
  async removeDocumentoFromBloco(idBloco: string, idDocumento: string): Promise<boolean> {
    // SOAP
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      try {
        return await this.soapClient.excluirDocumentoBloco(
          this.currentIdUnidade,
          idBloco,
          idDocumento
        );
      } catch (err) {
        console.warn('SOAP excluirDocumentoBloco falhou, tentando browser:', err);
      }
    }

    // Fallback browser
    if (this.browserClient) {
      return this.browserClient.removeDocumentoFromBloco(idBloco, idDocumento);
    }

    throw new Error('Nenhum cliente disponível');
  }

  /** Disponibiliza bloco para outras unidades */
  async disponibilizarBloco(idBloco: string, unidades?: string[]): Promise<boolean> {
    // SOAP
    if (this.soapAvailable && this.soapClient && this.currentIdUnidade) {
      try {
        return await this.soapClient.disponibilizarBloco(this.currentIdUnidade, idBloco);
      } catch (err) {
        console.warn('SOAP disponibilizarBloco falhou, tentando browser:', err);
      }
    }

    // Fallback browser
    if (this.browserClient) {
      return this.browserClient.disponibilizarBloco(idBloco, unidades);
    }

    throw new Error('Nenhum cliente disponível');
  }

  // ============================================
  // Utilitários
  // ============================================

  /** Captura screenshot (retorna base64) */
  async screenshot(fullPage = false): Promise<string> {
    if (this.browserClient) {
      return this.browserClient.screenshot(fullPage);
    }
    throw new Error('Screenshot requer browser client');
  }

  /** Acesso direto ao cliente browser */
  getBrowserClient(): SEIBrowserClient | null {
    return this.browserClient;
  }

  /** Acesso direto ao cliente SOAP */
  getSoapClient(): SEISoapClient | null {
    return this.soapClient;
  }

  // ============================================
  // Session Management & Window Control
  // ============================================

  /**
   * Retorna o endpoint CDP para reconexão futura
   * Útil para manter sessão entre execuções do agente
   */
  getCdpEndpoint(): string | null {
    return this.browserClient?.getCdpEndpoint() ?? null;
  }

  /**
   * Minimiza a janela do navegador (via CDP)
   * Útil quando se quer manter o navegador aberto mas fora do caminho
   */
  async minimizeWindow(): Promise<void> {
    if (this.browserClient) {
      await this.browserClient.minimizeWindow();
    }
  }

  /**
   * Restaura a janela do navegador (via CDP)
   */
  async restoreWindow(): Promise<void> {
    if (this.browserClient) {
      await this.browserClient.restoreWindow();
    }
  }

  /**
   * Traz a janela para frente
   */
  async bringToFront(): Promise<void> {
    if (this.browserClient) {
      await this.browserClient.bringToFront();
    }
  }

  /**
   * Maximiza a janela do navegador
   */
  async maximizeWindow(): Promise<void> {
    if (this.browserClient) {
      await this.browserClient.maximizeWindow();
    }
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
    return this.browserClient?.getWindowBounds() ?? null;
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
    if (this.browserClient) {
      await this.browserClient.setWindowBounds(bounds);
    }
  }

  /**
   * Verifica se a sessão ainda está ativa
   */
  async isSessionActive(): Promise<boolean> {
    if (this.browserClient) {
      return this.browserClient.isSessionActive();
    }
    return false;
  }
}

export default SEIClient;
