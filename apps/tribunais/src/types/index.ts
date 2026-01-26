/**
 * Tipos para o serviço de tribunais
 *
 * Suporta:
 * - Consultas (login com senha ou certificado)
 * - Peticionamento (requer certificado)
 * - Download de documentos
 * - Acompanhamento de processos
 */

// Tipos de tribunal suportados
export type TribunalType = 'pje' | 'eproc' | 'esaj';

// Tipos de autenticação
export type AuthType = 'password' | 'certificate_a1' | 'certificate_a3_physical' | 'certificate_a3_cloud';

// Tipos de operação
export type OperationType =
  | 'consultar_processo'
  | 'listar_documentos'
  | 'listar_movimentacoes'
  | 'baixar_documento'
  | 'baixar_processo'
  | 'peticionar'
  | 'acompanhar';

// Tipos de certificado (para certificados armazenados)
export type CertificateType = 'a1' | 'a3_physical' | 'a3_cloud';

// Status de petição
export type PetitionStatus =
  | 'pending'        // Aguardando processamento
  | 'processing'     // Em processamento
  | 'waiting_sign'   // Aguardando assinatura (A3)
  | 'completed'      // Concluído com sucesso
  | 'failed';        // Falhou

// Credenciais armazenadas (senha ou certificado)
export interface StoredCredential {
  id: string;
  userId: string;
  tribunal: TribunalType;
  tribunalUrl: string;
  authType: AuthType;
  name: string;  // Nome amigável (ex: "PJe TRF1 - Dr. Silva")

  // Para login com senha
  encryptedCpf?: string;
  encryptedPassword?: string;

  // Para certificado A1
  encryptedPfx?: string;
  encryptedPfxPassword?: string;

  // Para A3 cloud
  cloudProvider?: 'certisign' | 'serasa' | 'safeweb';

  // Metadados
  expiresAt?: Date;
  lastUsedAt?: Date;
  createdAt: Date;
  updatedAt: Date;
}

// Certificado A1 armazenado (legado, manter compatibilidade)
export interface StoredCertificate extends StoredCredential {
  type: CertificateType;
}

// Petição na fila
export interface PetitionJob {
  id: string;
  userId: string;
  certificateId: string;
  tribunal: TribunalType;
  tribunalUrl: string;
  processo: string;
  tipo: 'peticao_inicial' | 'peticao_intermediaria' | 'recurso' | 'outros';
  arquivos: PetitionFile[];
  metadata?: Record<string, unknown>;
  status: PetitionStatus;
  protocolo?: string;
  error?: string;
  createdAt: Date;
  updatedAt: Date;
  completedAt?: Date;
}

// Arquivo para petição
export interface PetitionFile {
  name: string;
  path?: string;           // Caminho no storage
  base64?: string;         // Ou conteúdo base64
  mimeType: string;
  tipoDocumento?: string;  // Tipo no tribunal
}

// Resultado do peticionamento
export interface PetitionResult {
  success: boolean;
  protocolo?: string;
  dataProtocolo?: Date;
  error?: string;
  details?: Record<string, unknown>;
}

// Evento de assinatura pendente (A3)
export interface SignatureRequiredEvent {
  petitionId: string;
  userId: string;
  processo: string;
  tribunal: TribunalType;
  message: string;
  expiresAt: Date;
}

// Mensagem WebSocket para extensão
export interface ExtensionMessage {
  type: 'command' | 'response' | 'event';
  id: string;
  action?: string;
  params?: Record<string, unknown>;
  success?: boolean;
  data?: unknown;
  error?: string;
}

// Configuração do serviço
export interface ServiceConfig {
  port: number;
  redisUrl: string;
  encryptionKey: string;
  storagePath: string;
  webhookUrl?: string;
}

// Request de upload de certificado
export interface CertificateUploadRequest {
  userId: string;
  type: CertificateType;
  name: string;
  // Para A1
  pfxBase64?: string;
  pfxPassword?: string;
  // Para A3 cloud
  provider?: 'certisign' | 'serasa' | 'safeweb';
}

// Request de petição
export interface PetitionRequest {
  userId: string;
  credentialId: string;
  tribunal: TribunalType;
  tribunalUrl: string;
  processo: string;
  tipo: 'peticao_inicial' | 'peticao_intermediaria' | 'recurso' | 'outros';
  arquivos: PetitionFile[];
  metadata?: Record<string, unknown>;
  webhookUrl?: string;
}

// === CONSULTAS ===

// Request de consulta genérica
export interface QueryRequest {
  userId: string;
  credentialId: string;
  tribunal: TribunalType;
  tribunalUrl: string;
  operation: OperationType;
  params: Record<string, unknown>;
  webhookUrl?: string;
}

// Request de consulta de processo
export interface ConsultaProcessoRequest extends Omit<QueryRequest, 'operation' | 'params'> {
  processo: string;
  incluirDocumentos?: boolean;
  incluirMovimentacoes?: boolean;
}

// Request de download de documento
export interface DownloadDocumentoRequest extends Omit<QueryRequest, 'operation' | 'params'> {
  processo: string;
  documentoId: string;
}

// Resultado de consulta de processo
export interface ProcessoInfo {
  numero: string;
  classe?: string;
  assunto?: string;
  vara?: string;
  comarca?: string;
  dataDistribuicao?: Date;
  valorCausa?: number;
  partes?: {
    polo: 'ativo' | 'passivo';
    nome: string;
    documento?: string;
    advogados?: string[];
  }[];
  situacao?: string;
  ultimaMovimentacao?: Date;
}

// Resultado de lista de documentos
export interface DocumentoInfo {
  id: string;
  numero?: string;
  tipo: string;
  descricao?: string;
  dataJuntada: Date;
  tamanho?: number;
  assinado?: boolean;
  signatarios?: string[];
}

// Resultado de movimentação
export interface MovimentacaoInfo {
  id: string;
  data: Date;
  tipo: string;
  descricao: string;
  responsavel?: string;
  documentos?: string[];
}

// Resultado genérico de operação
export interface OperationResult {
  success: boolean;
  operation: OperationType;
  data?: ProcessoInfo | DocumentoInfo[] | MovimentacaoInfo[] | Buffer | unknown;
  error?: string;
  executedAt: Date;
}

// Job genérico na fila
export interface TribunalJob {
  id: string;
  userId: string;
  credentialId: string;
  tribunal: TribunalType;
  tribunalUrl: string;
  operation: OperationType;
  params: Record<string, unknown>;
  status: PetitionStatus;
  result?: OperationResult;
  error?: string;
  webhookUrl?: string;
  createdAt: Date;
  updatedAt: Date;
  completedAt?: Date;
}

// Credencial para uso (descriptografada em memória)
export interface DecryptedCredential {
  id: string;
  authType: AuthType;
  tribunal: TribunalType;
  tribunalUrl: string;
  // Para senha
  cpf?: string;
  password?: string;
  // Para A1
  pfxBuffer?: Buffer;
  pfxPassword?: string;
  // Para A3 cloud
  cloudProvider?: 'certisign' | 'serasa' | 'safeweb';
}

// === CAPTCHA HIL ===

// Tipos de CAPTCHA suportados
export type CaptchaType = 'image' | 'recaptcha_v2' | 'recaptcha_v3' | 'hcaptcha' | 'unknown';

// Informações do CAPTCHA detectado
export interface CaptchaInfo {
  type: CaptchaType;
  siteKey?: string;           // Para reCAPTCHA/hCaptcha
  imageBase64?: string;       // Para CAPTCHA de imagem
  imageUrl?: string;          // URL da imagem (alternativa)
  instructions?: string;      // Instruções para o usuário
  metadata?: Record<string, unknown>;
}

// Solução do CAPTCHA
export interface CaptchaSolution {
  token?: string;             // Token reCAPTCHA/hCaptcha
  text?: string;              // Texto digitado (CAPTCHA imagem)
  clicked?: boolean;          // Para checkbox reCAPTCHA
}

// Evento de CAPTCHA pendente
export interface CaptchaRequiredEvent {
  jobId: string;
  userId: string;
  captchaId: string;
  tribunal: TribunalType;
  tribunalUrl: string;
  captcha: CaptchaInfo;
  expiresAt: Date;
}

// Resposta do CAPTCHA (do cliente)
export interface CaptchaSolutionResponse {
  captchaId: string;
  jobId: string;
  success: boolean;
  solution?: CaptchaSolution;
  error?: string;
}
