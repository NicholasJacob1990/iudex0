/**
 * Tipos principais do tribunais-playwright
 */

// ============================================
// Autenticação
// ============================================

export type AuthType = 'password' | 'certificate_a1' | 'certificate_a3_physical' | 'certificate_a3_cloud';

export interface PasswordAuth {
  type: 'password';
  cpf: string;
  senha: string;
}

export interface CertificateA1Auth {
  type: 'certificate_a1';
  pfxPath: string;
  passphrase: string;
}

export interface CertificateA3PhysicalAuth {
  type: 'certificate_a3_physical';
  /** Callback chamado quando PIN é necessário */
  onPinRequired?: () => Promise<void>;
  /** Timeout para aguardar PIN (ms) */
  pinTimeout?: number;
}

export interface CertificateA3CloudAuth {
  type: 'certificate_a3_cloud';
  provider: 'certisign' | 'serasa' | 'safeweb' | 'soluti' | 'other';
  /** Callback chamado quando aprovação no celular é necessária */
  onApprovalRequired?: (info: ApprovalInfo) => Promise<void>;
  /** Timeout para aguardar aprovação (ms) */
  approvalTimeout?: number;
}

export type AuthConfig = PasswordAuth | CertificateA1Auth | CertificateA3PhysicalAuth | CertificateA3CloudAuth;

export interface ApprovalInfo {
  type: 'signature' | 'login';
  message: string;
  expiresIn: number; // segundos
  provider: string;
}

// ============================================
// Captcha (Human-in-the-loop)
// ============================================

export type CaptchaType = 'image' | 'recaptcha_v2' | 'recaptcha_v3' | 'hcaptcha' | 'audio' | 'text' | 'unknown';

export interface CaptchaInfo {
  /** Tipo do captcha detectado */
  type: CaptchaType;

  /** Imagem do captcha em base64 (para captchas de imagem) */
  imageBase64?: string;

  /** Site key (para reCAPTCHA/hCaptcha) */
  siteKey?: string;

  /** URL da página */
  pageUrl: string;

  /** Timestamp de quando foi detectado */
  timestamp: Date;

  /** Tempo limite para resolução (segundos) */
  expiresIn: number;
}

export interface CaptchaSolution {
  /** Texto/token da solução */
  solution: string;

  /** Se foi resolvido por serviço externo */
  solvedBy?: 'user' | '2captcha' | 'anticaptcha' | 'capsolver' | 'manual';

  /** Tempo que levou para resolver (ms) */
  solveTime?: number;
}

export interface CaptchaConfig {
  /** Modo de resolução */
  mode: 'manual' | 'service' | 'hybrid';

  /** Timeout para resolução manual (ms) */
  manualTimeout?: number;

  /** Configuração do serviço de resolução */
  service?: {
    provider: '2captcha' | 'anticaptcha' | 'capsolver' | 'deathbycaptcha';
    apiKey: string;
    /** Timeout do serviço (ms) */
    timeout?: number;
  };

  /** Callback quando captcha é detectado */
  onCaptchaDetected?: (info: CaptchaInfo) => Promise<CaptchaSolution | void>;

  /** Callback para obter solução manual */
  onCaptchaRequired?: (info: CaptchaInfo) => Promise<string>;
}

// ============================================
// Notificações (Human-in-the-loop)
// ============================================

export type NotificationType =
  | 'pin_required'
  | 'approval_required'
  | 'signature_pending'
  | 'signature_success'
  | 'signature_error'
  | 'login_success'
  | 'login_error'
  | 'captcha_detected'
  | 'captcha_required'
  | 'captcha_solved'
  | 'captcha_failed';

export interface Notification {
  type: NotificationType;
  message: string;
  data?: ApprovalInfo | CaptchaInfo | Record<string, unknown>;
  expiresIn?: number;
  timestamp: Date;
}

export interface NotificationHandler {
  (notification: Notification): void | Promise<void>;
}

// ============================================
// Configuração do Cliente
// ============================================

export interface TribunalClientConfig {
  /** URL base do tribunal */
  baseUrl: string;

  /** Configuração de autenticação */
  auth: AuthConfig;

  /** Opções do Playwright */
  playwright?: {
    /** Navegador invisível (true) ou visível (false) */
    headless?: boolean;
    /** Delay entre ações (ms) - útil para debug */
    slowMo?: number;
    /** Timeout padrão para operações (ms) */
    timeout?: number;
    /** Usar contexto persistente (mantém cookies/sessão entre execuções) */
    persistent?: boolean;
    /** Diretório para dados do usuário (cookies, cache, etc.) */
    userDataDir?: string;
    /** Conectar a Chrome já aberto via CDP */
    cdpEndpoint?: string;
    /** Manter navegador aberto após operações (para sessões longas) */
    keepAlive?: boolean;
    /** Porta para servidor CDP (permite reconexão) */
    cdpPort?: number;
  };

  /** Handler de notificações */
  onNotification?: NotificationHandler;

  /** Webhook para notificações */
  webhookUrl?: string;

  /** Configuração de captcha */
  captcha?: CaptchaConfig;
}

// ============================================
// Tribunais Suportados
// ============================================

export type TribunalType = 'pje' | 'esaj' | 'eproc' | 'projudi' | 'tucujuris';

export interface TribunalInfo {
  type: TribunalType;
  name: string;
  baseUrl: string;
  region: string;
  /** Suporta login com senha */
  supportsPassword: boolean;
  /** Suporta certificado A1 */
  supportsA1: boolean;
  /** Suporta certificado A3 */
  supportsA3: boolean;
}

// ============================================
// Processo
// ============================================

export interface Processo {
  numero: string;
  tribunal: string;
  classe: string;
  assunto: string;
  dataDistribuicao: string;
  valorCausa?: number;
  partes: Parte[];
  movimentacoes: Movimentacao[];
  documentos: Documento[];
  status: string;
}

export interface Parte {
  tipo: 'autor' | 'reu' | 'terceiro' | 'advogado' | 'outro';
  nome: string;
  documento?: string; // CPF/CNPJ
  advogados?: Advogado[];
}

export interface Advogado {
  nome: string;
  oab: string;
  uf: string;
}

export interface Movimentacao {
  data: string;
  descricao: string;
  tipo?: string;
}

export interface Documento {
  id: string;
  nome: string;
  tipo: string;
  data: string;
  assinado: boolean;
  signatarios?: string[];
}

// ============================================
// Peticionamento
// ============================================

export interface PeticaoOpcoes {
  /** Número do processo */
  numeroProcesso: string;

  /** Tipo de petição */
  tipo: string;

  /** Descrição/assunto */
  descricao?: string;

  /** Arquivos para anexar (paths) */
  arquivos: string[];

  /** Tipos de documento para cada arquivo */
  tiposDocumento?: string[];

  /** Urgente */
  urgente?: boolean;

  /** Segredo de justiça */
  segredoJustica?: boolean;
}

export interface ProtocoloResultado {
  success: boolean;
  numeroProtocolo?: string;
  dataProtocolo?: string;
  mensagem?: string;
  error?: string;
}

// ============================================
// Assinatura
// ============================================

export interface AssinaturaOpcoes {
  /** IDs dos documentos a assinar */
  documentos: string[];

  /** Tipo de assinatura */
  tipo?: 'simples' | 'qualificada';

  /** Observação */
  observacao?: string;
}

export interface AssinaturaResultado {
  success: boolean;
  documentosAssinados: string[];
  error?: string;
}

// ============================================
// Eventos
// ============================================

export interface TribunalEvents {
  'login:success': { usuario: string };
  'login:error': { error: string };
  'login:pin_required': { timeout: number };
  'login:approval_required': ApprovalInfo;

  'peticao:started': { processo: string };
  'peticao:uploaded': { arquivo: string; index: number; total: number };
  'peticao:signature_required': ApprovalInfo;
  'peticao:success': ProtocoloResultado;
  'peticao:error': { error: string };

  'assinatura:started': { documentos: string[] };
  'assinatura:pin_required': { timeout: number };
  'assinatura:approval_required': ApprovalInfo;
  'assinatura:success': AssinaturaResultado;
  'assinatura:error': { error: string };

  'captcha:detected': CaptchaInfo;
  'captcha:required': CaptchaInfo;
  'captcha:solved': { captcha: CaptchaInfo; solution: CaptchaSolution };
  'captcha:failed': { captcha: CaptchaInfo; error: string };

  'session:expired': Record<string, never>;
  'error': { error: Error };
}

// ============================================
// Seletores Semânticos (ARIA)
// ============================================

export interface SemanticSelector {
  role: 'button' | 'textbox' | 'link' | 'combobox' | 'checkbox' | 'radio' | 'option' | 'row' | 'cell' | 'table' | 'dialog' | 'alert' | 'img';
  name?: RegExp | string;
  fallback?: string;
}

export interface TribunalSelectors {
  login: {
    cpfInput: SemanticSelector;
    senhaInput: SemanticSelector;
    certificadoBtn?: SemanticSelector;
    entrarBtn: SemanticSelector;
    logoutLink: SemanticSelector;
  };
  processo: {
    searchInput: SemanticSelector;
    searchBtn: SemanticSelector;
    resultTable: SemanticSelector;
    detailsLink: SemanticSelector;
  };
  peticao: {
    novaBtn: SemanticSelector;
    tipoSelect: SemanticSelector;
    descricaoInput?: SemanticSelector;
    anexarBtn: SemanticSelector;
    fileInput: SemanticSelector;
    assinarBtn: SemanticSelector;
    enviarBtn: SemanticSelector;
    protocoloText: SemanticSelector;
  };
  common: {
    loadingIndicator: SemanticSelector;
    successAlert: SemanticSelector;
    errorAlert: SemanticSelector;
    modalClose: SemanticSelector;
  };
  captcha?: {
    /** Container do captcha de imagem */
    imageContainer: SemanticSelector;
    /** Imagem do captcha */
    image: SemanticSelector;
    /** Input para resposta */
    input: SemanticSelector;
    /** Botão de refresh/novo captcha */
    refreshBtn?: SemanticSelector;
    /** Container do reCAPTCHA */
    recaptchaContainer?: SemanticSelector;
    /** Container do hCaptcha */
    hcaptchaContainer?: SemanticSelector;
  };
}
