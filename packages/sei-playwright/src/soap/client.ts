/**
 * Cliente SOAP para SEI WebServices
 * Baseado na documentação SEI-WebServices-v4.0-2.txt
 */

import * as soap from 'soap';
import type {
  Procedimento,
  Documento,
  RetornoGerarProcedimento,
  RetornoInclusaoDocumento,
  RetornoConsultaProcedimento,
  RetornoConsultaDocumento,
  Serie,
  TipoProcedimento,
  Unidade,
  Usuario,
  Bloco,
  Andamento,
} from '../types.js';

export interface SOAPConfig {
  /** URL base do SEI (ex: https://sei.mg.gov.br) */
  baseUrl: string;
  /** Sigla do sistema cadastrado no SEI */
  siglaSistema: string;
  /** Identificação do serviço */
  identificacaoServico: string;
}

export interface SOAPAuth {
  siglaSistema: string;
  identificacaoServico: string;
  idUnidade: string;
}

/**
 * Cliente SOAP para SEI WebServices
 *
 * @example
 * ```typescript
 * const client = new SEISoapClient({
 *   baseUrl: 'https://sei.mg.gov.br',
 *   siglaSistema: 'MEU_SISTEMA',
 *   identificacaoServico: 'MinhaChave123',
 * });
 *
 * await client.connect();
 * const tipos = await client.listarTiposProcedimento('110000001');
 * ```
 */
export class SEISoapClient {
  private config: SOAPConfig;
  private client: soap.Client | null = null;

  constructor(config: SOAPConfig) {
    this.config = config;
  }

  /** URL do WSDL do SEI */
  private get wsdlUrl(): string {
    const base = this.config.baseUrl.replace(/\/$/, '');
    return `${base}/sei/controlador_ws.php?servico=sei`;
  }

  /** Conecta ao serviço SOAP */
  async connect(): Promise<void> {
    this.client = await soap.createClientAsync(this.wsdlUrl);
  }

  /** Verifica se está conectado */
  get isConnected(): boolean {
    return this.client !== null;
  }

  /** Autentica requisição */
  private auth(idUnidade: string): SOAPAuth {
    return {
      siglaSistema: this.config.siglaSistema,
      identificacaoServico: this.config.identificacaoServico,
      idUnidade,
    };
  }

  /** Executa chamada SOAP */
  private async call<T>(method: string, args: Record<string, unknown>): Promise<T> {
    if (!this.client) {
      throw new Error('SOAP client não conectado. Chame connect() primeiro.');
    }

    const fn = this.client[`${method}Async`] as (args: unknown) => Promise<[T]>;
    if (!fn) {
      throw new Error(`Método SOAP '${method}' não encontrado`);
    }

    const [result] = await fn.call(this.client, args);
    return result;
  }

  // ============================================
  // Métodos de Listagem
  // ============================================

  /** Lista séries/tipos de documento */
  async listarSeries(idUnidade: string, idTipoProcedimento?: string): Promise<Serie[]> {
    return this.call<Serie[]>('listarSeries', {
      ...this.auth(idUnidade),
      IdTipoProcedimento: idTipoProcedimento,
    });
  }

  /** Lista tipos de procedimento/processo */
  async listarTiposProcedimento(idUnidade: string): Promise<TipoProcedimento[]> {
    return this.call<TipoProcedimento[]>('listarTiposProcedimento', {
      ...this.auth(idUnidade),
    });
  }

  /** Lista unidades */
  async listarUnidades(idUnidade: string, idTipoProcedimento?: string): Promise<Unidade[]> {
    return this.call<Unidade[]>('listarUnidades', {
      ...this.auth(idUnidade),
      IdTipoProcedimento: idTipoProcedimento,
    });
  }

  /** Lista usuários da unidade */
  async listarUsuarios(idUnidade: string): Promise<Usuario[]> {
    return this.call<Usuario[]>('listarUsuarios', {
      ...this.auth(idUnidade),
    });
  }

  /** Lista hipóteses legais */
  async listarHipotesesLegais(idUnidade: string, nivelAcesso?: number): Promise<unknown[]> {
    return this.call<unknown[]>('listarHipotesesLegais', {
      ...this.auth(idUnidade),
      NivelAcesso: nivelAcesso,
    });
  }

  // ============================================
  // Métodos de Procedimento (Processo)
  // ============================================

  /** Gera novo procedimento/processo */
  async gerarProcedimento(
    idUnidade: string,
    procedimento: Procedimento,
    documentos?: Documento[],
    procedimentosRelacionados?: string[],
    unidadesEnvio?: string[],
    sinManterAbertoUnidade?: boolean,
    sinEnviarEmailNotificacao?: boolean,
    dataRetornoProgramado?: string,
    idMarcador?: string,
    textoMarcador?: string
  ): Promise<RetornoGerarProcedimento> {
    return this.call<RetornoGerarProcedimento>('gerarProcedimento', {
      ...this.auth(idUnidade),
      Procedimento: procedimento,
      Documentos: documentos,
      ProcedimentosRelacionados: procedimentosRelacionados,
      UnidadesEnvio: unidadesEnvio,
      SinManterAbertoUnidade: sinManterAbertoUnidade ? 'S' : 'N',
      SinEnviarEmailNotificacao: sinEnviarEmailNotificacao ? 'S' : 'N',
      DataRetornoProgramado: dataRetornoProgramado,
      IdMarcador: idMarcador,
      TextoMarcador: textoMarcador,
    });
  }

  /** Consulta procedimento/processo */
  async consultarProcedimento(
    idUnidade: string,
    protocoloProcedimento: string,
    sinRetornarAssuntos?: boolean,
    sinRetornarInteressados?: boolean,
    sinRetornarObservacoes?: boolean,
    sinRetornarAndamentoGeracao?: boolean,
    sinRetornarAndamentoConclusao?: boolean,
    sinRetornarUltimoAndamento?: boolean,
    sinRetornarUnidadesProcedimentoAberto?: boolean,
    sinRetornarProcedimentosRelacionados?: boolean,
    sinRetornarProcedimentosAnexados?: boolean
  ): Promise<RetornoConsultaProcedimento> {
    return this.call<RetornoConsultaProcedimento>('consultarProcedimento', {
      ...this.auth(idUnidade),
      ProtocoloProcedimento: protocoloProcedimento,
      SinRetornarAssuntos: sinRetornarAssuntos ? 'S' : 'N',
      SinRetornarInteressados: sinRetornarInteressados ? 'S' : 'N',
      SinRetornarObservacoes: sinRetornarObservacoes ? 'S' : 'N',
      SinRetornarAndamentoGeracao: sinRetornarAndamentoGeracao ? 'S' : 'N',
      SinRetornarAndamentoConclusao: sinRetornarAndamentoConclusao ? 'S' : 'N',
      SinRetornarUltimoAndamento: sinRetornarUltimoAndamento ? 'S' : 'N',
      SinRetornarUnidadesProcedimentoAberto: sinRetornarUnidadesProcedimentoAberto ? 'S' : 'N',
      SinRetornarProcedimentosRelacionados: sinRetornarProcedimentosRelacionados ? 'S' : 'N',
      SinRetornarProcedimentosAnexados: sinRetornarProcedimentosAnexados ? 'S' : 'N',
    });
  }

  /** Envia processo para outras unidades */
  async enviarProcesso(
    idUnidade: string,
    protocoloProcedimento: string,
    unidadesDestino: string[],
    sinManterAbertoUnidade?: boolean,
    sinRemoverAnotacao?: boolean,
    sinEnviarEmailNotificacao?: boolean,
    dataRetornoProgramado?: string,
    diasRetornoProgramado?: number,
    sinDiasUteisRetornoProgramado?: boolean,
    sinReabrir?: boolean
  ): Promise<boolean> {
    return this.call<boolean>('enviarProcesso', {
      ...this.auth(idUnidade),
      ProtocoloProcedimento: protocoloProcedimento,
      UnidadesDestino: unidadesDestino,
      SinManterAbertoUnidade: sinManterAbertoUnidade ? 'S' : 'N',
      SinRemoverAnotacao: sinRemoverAnotacao ? 'S' : 'N',
      SinEnviarEmailNotificacao: sinEnviarEmailNotificacao ? 'S' : 'N',
      DataRetornoProgramado: dataRetornoProgramado,
      DiasRetornoProgramado: diasRetornoProgramado,
      SinDiasUteisRetornoProgramado: sinDiasUteisRetornoProgramado ? 'S' : 'N',
      SinReabrir: sinReabrir ? 'S' : 'N',
    });
  }

  /** Conclui processo na unidade */
  async concluirProcesso(idUnidade: string, protocoloProcedimento: string): Promise<boolean> {
    return this.call<boolean>('concluirProcesso', {
      ...this.auth(idUnidade),
      ProtocoloProcedimento: protocoloProcedimento,
    });
  }

  /** Reabre processo na unidade */
  async reabrirProcesso(idUnidade: string, protocoloProcedimento: string): Promise<boolean> {
    return this.call<boolean>('reabrirProcesso', {
      ...this.auth(idUnidade),
      ProtocoloProcedimento: protocoloProcedimento,
    });
  }

  /** Atribui processo a um usuário */
  async atribuirProcesso(
    idUnidade: string,
    protocoloProcedimento: string,
    idUsuario: string,
    sinReabrir?: boolean
  ): Promise<boolean> {
    return this.call<boolean>('atribuirProcesso', {
      ...this.auth(idUnidade),
      ProtocoloProcedimento: protocoloProcedimento,
      IdUsuario: idUsuario,
      SinReabrir: sinReabrir ? 'S' : 'N',
    });
  }

  /** Anexa processo a outro */
  async anexarProcesso(
    idUnidade: string,
    protocoloProcedimentoPrincipal: string,
    protocoloProcedimentoAnexado: string
  ): Promise<boolean> {
    return this.call<boolean>('anexarProcesso', {
      ...this.auth(idUnidade),
      ProtocoloProcedimentoPrincipal: protocoloProcedimentoPrincipal,
      ProtocoloProcedimentoAnexado: protocoloProcedimentoAnexado,
    });
  }

  /** Relaciona processos */
  async relacionarProcesso(
    idUnidade: string,
    protocoloProcedimento1: string,
    protocoloProcedimento2: string
  ): Promise<boolean> {
    return this.call<boolean>('relacionarProcesso', {
      ...this.auth(idUnidade),
      ProtocoloProcedimento1: protocoloProcedimento1,
      ProtocoloProcedimento2: protocoloProcedimento2,
    });
  }

  // ============================================
  // Métodos de Documento
  // ============================================

  /** Inclui documento em processo */
  async incluirDocumento(idUnidade: string, documento: Documento): Promise<RetornoInclusaoDocumento> {
    return this.call<RetornoInclusaoDocumento>('incluirDocumento', {
      ...this.auth(idUnidade),
      Documento: documento,
    });
  }

  /** Consulta documento */
  async consultarDocumento(
    idUnidade: string,
    protocoloDocumento: string,
    sinRetornarAndamentoGeracao?: boolean,
    sinRetornarAssinaturas?: boolean,
    sinRetornarPublicacao?: boolean,
    sinRetornarCampos?: boolean
  ): Promise<RetornoConsultaDocumento> {
    return this.call<RetornoConsultaDocumento>('consultarDocumento', {
      ...this.auth(idUnidade),
      ProtocoloDocumento: protocoloDocumento,
      SinRetornarAndamentoGeracao: sinRetornarAndamentoGeracao ? 'S' : 'N',
      SinRetornarAssinaturas: sinRetornarAssinaturas ? 'S' : 'N',
      SinRetornarPublicacao: sinRetornarPublicacao ? 'S' : 'N',
      SinRetornarCampos: sinRetornarCampos ? 'S' : 'N',
    });
  }

  /** Cancela documento */
  async cancelarDocumento(idUnidade: string, protocoloDocumento: string, motivo: string): Promise<boolean> {
    return this.call<boolean>('cancelarDocumento', {
      ...this.auth(idUnidade),
      ProtocoloDocumento: protocoloDocumento,
      Motivo: motivo,
    });
  }

  /** Adiciona arquivo para upload em partes (arquivos grandes) */
  async adicionarArquivo(
    idUnidade: string,
    nome: string,
    tamanho: number,
    hash: string,
    conteudo: string
  ): Promise<string> {
    return this.call<string>('adicionarArquivo', {
      ...this.auth(idUnidade),
      Nome: nome,
      Tamanho: tamanho,
      Hash: hash,
      Conteudo: conteudo,
    });
  }

  // ============================================
  // Métodos de Bloco
  // ============================================

  /** Gera bloco de assinatura */
  async gerarBloco(
    idUnidade: string,
    tipo: 'A' | 'R' | 'I', // A=Assinatura, R=Reunião, I=Interno
    descricao: string,
    unidadesDisponibilizacao?: string[],
    documentos?: string[],
    sinDisponibilizar?: boolean
  ): Promise<Bloco> {
    return this.call<Bloco>('gerarBloco', {
      ...this.auth(idUnidade),
      Tipo: tipo,
      Descricao: descricao,
      UnidadesDisponibilizacao: unidadesDisponibilizacao,
      Documentos: documentos,
      SinDisponibilizar: sinDisponibilizar ? 'S' : 'N',
    });
  }

  /** Consulta bloco */
  async consultarBloco(
    idUnidade: string,
    idBloco: string,
    sinRetornarProtocolos?: boolean
  ): Promise<Bloco> {
    return this.call<Bloco>('consultarBloco', {
      ...this.auth(idUnidade),
      IdBloco: idBloco,
      SinRetornarProtocolos: sinRetornarProtocolos ? 'S' : 'N',
    });
  }

  /** Inclui documento em bloco */
  async incluirDocumentoBloco(
    idUnidade: string,
    idBloco: string,
    protocoloDocumento: string
  ): Promise<boolean> {
    return this.call<boolean>('incluirDocumentoBloco', {
      ...this.auth(idUnidade),
      IdBloco: idBloco,
      ProtocoloDocumento: protocoloDocumento,
    });
  }

  /** Exclui documento de bloco */
  async excluirDocumentoBloco(
    idUnidade: string,
    idBloco: string,
    protocoloDocumento: string
  ): Promise<boolean> {
    return this.call<boolean>('excluirDocumentoBloco', {
      ...this.auth(idUnidade),
      IdBloco: idBloco,
      ProtocoloDocumento: protocoloDocumento,
    });
  }

  /** Disponibiliza bloco para outras unidades */
  async disponibilizarBloco(idUnidade: string, idBloco: string): Promise<boolean> {
    return this.call<boolean>('disponibilizarBloco', {
      ...this.auth(idUnidade),
      IdBloco: idBloco,
    });
  }

  // ============================================
  // Métodos de Andamento
  // ============================================

  /** Lista andamentos */
  async listarAndamentos(
    idUnidade: string,
    protocoloProcedimento: string,
    sinRetornarAtributos?: boolean,
    andamentos?: string[]
  ): Promise<Andamento[]> {
    return this.call<Andamento[]>('listarAndamentos', {
      ...this.auth(idUnidade),
      ProtocoloProcedimento: protocoloProcedimento,
      SinRetornarAtributos: sinRetornarAtributos ? 'S' : 'N',
      Andamentos: andamentos,
    });
  }
}

export default SEISoapClient;
