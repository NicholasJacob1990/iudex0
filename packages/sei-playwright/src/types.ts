/**
 * Tipos baseados na documentação SEI WebServices v4.0
 * Fonte: SEI-WebServices-v4.0-2.txt
 */

// ============================================
// Estruturas de Dados do SEI WebServices
// ============================================

/** Nível de acesso do documento/processo */
export type NivelAcesso = 0 | 1 | 2; // 0=Público, 1=Restrito, 2=Sigiloso

/** Tipo de documento */
export type TipoDocumento = 'G' | 'R'; // G=Gerado, R=Recebido (externo)

/** Andamento/histórico de um processo */
export interface Andamento {
  IdAndamento: string;
  IdTarefa: string;
  IdTarefaModulo: string;
  Descricao: string;
  DataHora: string;
  Unidade: Unidade;
  Usuario: Usuario;
  Atributos?: AtributoAndamento[];
}

/** Atributo de andamento */
export interface AtributoAndamento {
  Nome: string;
  Valor: string;
  IdOrigem?: string;
}

/** Documento do SEI */
export interface Documento {
  Tipo: TipoDocumento;
  IdProcedimento?: string;
  IdSerie: string;
  Numero?: string;
  Data?: string;
  Descricao?: string;
  Remetente?: Remetente;
  Interessados?: Interessado[];
  Destinatarios?: Destinatario[];
  Observacao?: string;
  NomeArquivo?: string;
  Conteudo?: string; // Base64
  ConteudoMTOM?: string;
  IdArquivo?: string; // Para upload em partes
  NivelAcesso: NivelAcesso;
  IdHipoteseLegal?: string;
  IdTipoConferencia?: string;
  Campos?: Campo[];
}

/** Retorno da consulta de documento */
export interface RetornoConsultaDocumento {
  IdProcedimento: string;
  ProcedimentoFormatado: string;
  IdDocumento: string;
  DocumentoFormatado: string;
  LinkAcesso: string;
  Serie: Serie;
  Numero?: string;
  Data: string;
  UnidadeElaboradora: Unidade;
  AndamentoGeracao: Andamento;
  Assinaturas?: Assinatura[];
  Campos?: Campo[];
}

/** Assinatura de documento */
export interface Assinatura {
  Nome: string;
  CargoFuncao: string;
  DataHora: string;
  IdUsuario: string;
  IdOrigem: string;
  IdOrgao: string;
  Sigla: string;
}

/** Processo/Procedimento do SEI */
export interface Procedimento {
  IdTipoProcedimento: string;
  Especificacao: string;
  Assuntos: Assunto[];
  Interessados?: Interessado[];
  Observacao?: string;
  NivelAcesso: NivelAcesso;
  IdHipoteseLegal?: string;
}

/** Retorno da consulta de procedimento */
export interface RetornoConsultaProcedimento {
  IdProcedimento: string;
  ProcedimentoFormatado: string;
  Especificacao: string;
  DataAutuacao: string;
  LinkAcesso: string;
  TipoProcedimento: TipoProcedimento;
  AndamentoGeracao: Andamento;
  AndamentoConclusao?: Andamento;
  UltimoAndamento: Andamento;
  UnidadesProcedimentoAberto: Unidade[];
  Assuntos: Assunto[];
  Interessados: Interessado[];
  Observacoes?: Observacao[];
  ProcedimentosRelacionados?: ProcedimentoRelacionado[];
  ProcedimentosAnexados?: ProcedimentoAnexado[];
}

/** Retorno de geração de procedimento */
export interface RetornoGerarProcedimento {
  IdProcedimento: string;
  ProcedimentoFormatado: string;
  LinkAcesso: string;
  RetornoInclusaoDocumentos?: RetornoInclusaoDocumento[];
}

/** Retorno de inclusão de documento */
export interface RetornoInclusaoDocumento {
  IdDocumento: string;
  DocumentoFormatado: string;
  LinkAcesso: string;
}

/** Série/Tipo de documento */
export interface Serie {
  IdSerie: string;
  Nome: string;
  Aplicabilidade?: 'T' | 'I' | 'E' | 'F'; // T=Todos, I=Interno, E=Externo/Recebido, F=Formulário
}

/** Tipo de procedimento/processo */
export interface TipoProcedimento {
  IdTipoProcedimento: string;
  Nome: string;
}

/** Unidade organizacional */
export interface Unidade {
  IdUnidade: string;
  Sigla: string;
  Descricao: string;
}

/** Usuário do SEI */
export interface Usuario {
  IdUsuario: string;
  Sigla: string;
  Nome: string;
}

/** Interessado do processo */
export interface Interessado {
  Sigla: string;
  Nome: string;
}

/** Destinatário do documento */
export interface Destinatario {
  Sigla: string;
  Nome: string;
}

/** Remetente do documento externo */
export interface Remetente {
  Sigla: string;
  Nome: string;
}

/** Assunto do processo */
export interface Assunto {
  CodigoEstruturado: string;
  Descricao?: string;
}

/** Campo de formulário */
export interface Campo {
  Nome: string;
  Valor: string;
}

/** Observação do processo */
export interface Observacao {
  Descricao: string;
  Unidade: Unidade;
}

/** Procedimento relacionado */
export interface ProcedimentoRelacionado {
  IdProcedimento: string;
  ProcedimentoFormatado: string;
}

/** Procedimento anexado */
export interface ProcedimentoAnexado {
  IdProcedimento: string;
  ProcedimentoFormatado: string;
}

/** Bloco de assinatura */
export interface Bloco {
  IdBloco: string;
  Descricao: string;
  UnidadesDisponibilizacao?: Unidade[];
  Documentos?: DocumentoBloco[];
}

/** Documento em bloco de assinatura */
export interface DocumentoBloco {
  IdProtocolo: string;
  ProtocoloFormatado: string;
}

// ============================================
// Resiliência e Self-Healing
// ============================================

export interface ResilienceConfig {
  /** Timeout curto para fail-fast antes de tentar próximo método (ms) */
  failFastTimeout?: number;
  /** Número máximo de retries para erros transitórios */
  maxRetries?: number;
  /** Backoff base entre retries (ms), cresce exponencialmente */
  retryBackoff?: number;
  /** Execução especulativa: roda script e agent em paralelo */
  speculative?: boolean;
}

export interface AgentFallbackConfig {
  /** Ativa agent fallback via Claude API */
  enabled?: boolean;
  /** Anthropic API key (ou usa ANTHROPIC_API_KEY do env) */
  apiKey?: string;
  /** Modelo a usar */
  model?: string;
  /** Max tokens na resposta */
  maxTokens?: number;
}

export interface SelectorStoreEntry {
  discoveredSelector: string;
  discoveredAt: string;
  successCount: number;
  lastSuccess: string;
}

// ============================================
// Configuração do Cliente
// ============================================

/** Configuração do SEI Client */
export interface SEIConfig {
  /** URL base do SEI (ex: https://sei.mg.gov.br) */
  baseUrl: string;

  /** Credenciais de autenticação via WebServices */
  soap?: {
    /** Sigla do sistema cadastrado no SEI */
    siglaSistema: string;
    /** Identificação do serviço */
    identificacaoServico: string;
  };

  /** Credenciais de autenticação via browser */
  browser?: {
    /** Usuário para login */
    usuario?: string;
    /** Senha para login */
    senha?: string;
    /** Órgão (se necessário) */
    orgao?: string;
  };

  /** Opções do Playwright */
  playwright?: {
    /** Executar em modo headless */
    headless?: boolean;
    /** Timeout padrão em ms */
    timeout?: number;

    // ===== Persistent Context (recomendado) =====
    /** Habilita persistent context - mantém sessão entre execuções */
    persistent?: boolean;
    /** Diretório para persistir sessão (default: ~/.sei-playwright/chrome-profile) */
    userDataDir?: string;
    /** Canal do navegador: 'chrome' usa Chrome instalado, 'chromium' usa Chromium do Playwright */
    channel?: 'chrome' | 'chromium' | 'msedge';

    // ===== CDP Connection (avançado) =====
    /** Endpoint CDP para conectar a Chrome já aberto (ex: http://localhost:9222) */
    cdpEndpoint?: string;
    /** Porta para servidor CDP - permite reconexão futura */
    cdpPort?: number;

    // ===== Session Management =====
    /** Manter navegador aberto após close() - útil para sessões longas */
    keepAlive?: boolean;
  };

  /** Configuração de resiliência (fail-fast, retry, speculative) */
  resilience?: ResilienceConfig;

  /** Configuração de agent fallback (Claude API) para self-healing */
  agentFallback?: AgentFallbackConfig;
}

/** Opções para criação de processo */
export interface CreateProcessOptions {
  tipoProcedimento: string;
  especificacao: string;
  assuntos: string[];
  interessados?: string[];
  observacao?: string;
  nivelAcesso?: NivelAcesso;
  hipoteseLegal?: string;
  documentos?: CreateDocumentOptions[];
}

/** Opções para criação de documento */
export interface CreateDocumentOptions {
  tipo?: TipoDocumento;
  idSerie: string;
  numero?: string;
  descricao?: string;
  interessados?: string[];
  destinatarios?: string[];
  observacao?: string;
  nivelAcesso?: NivelAcesso;
  hipoteseLegal?: string;

  /** Para documento gerado (tipo G) */
  conteudoHtml?: string;

  /** Para documento externo (tipo R) */
  nomeArquivo?: string;
  conteudoBase64?: string;

  /** Para upload em partes (arquivos grandes) */
  idArquivo?: string;
}

/** Opções para tramitação */
export interface ForwardOptions {
  unidadesDestino: string[];
  manterAberto?: boolean;
  removerAnotacoes?: boolean;
  enviarEmailNotificacao?: boolean;
  dataRetornoProgramado?: string;
  diasRetornoProgramado?: number;
  sinReabrir?: boolean;
  sinEnviarEmailNotificacao?: boolean;
}

/** Opções para bloco de assinatura */
export interface BlockOptions {
  descricao: string;
  unidadesDisponibilizacao?: string[];
  documentos?: string[];
}
