/**
 * tribunais-playwright
 *
 * Biblioteca para automação de tribunais (PJe, e-SAJ, eproc)
 * com suporte a login por senha e certificado digital (A1, A3 físico, A3 nuvem)
 */

// Core
export { BaseTribunalClient } from './core/base-client.js';
export { CaptchaHandler, type CaptchaSelectors } from './core/captcha-handler.js';
export { SelectorStore } from './core/selector-store.js';
export { failFast, withRetry, classifyError, resolveResilienceConfig } from './core/resilience.js';
export { createAgentFallback } from './core/agent-fallback.js';

// PJe
export { PJeClient, type PJeClientConfig } from './pje/index.js';
export { PJE_SELECTORS, PJE_URLS } from './pje/selectors.js';

// e-SAJ
export { ESAJ_SELECTORS, ESAJ_URLS } from './esaj/selectors.js';

// eproc
export { EprocClient, type EprocClientConfig } from './eproc/client.js';
export { EPROC_SELECTORS, EPROC_URLS } from './eproc/selectors.js';

// API REST
export { createApiServer } from './api/server.js';

// Types
export type {
  // Auth
  AuthType,
  AuthConfig,
  PasswordAuth,
  CertificateA1Auth,
  CertificateA3PhysicalAuth,
  CertificateA3CloudAuth,
  ApprovalInfo,

  // Notifications
  NotificationType,
  Notification,
  NotificationHandler,

  // Config
  TribunalClientConfig,
  TribunalType,
  TribunalInfo,

  // Processo
  Processo,
  Parte,
  Advogado,
  Movimentacao,
  Documento,

  // Peticionamento
  PeticaoOpcoes,
  ProtocoloResultado,

  // Assinatura
  AssinaturaOpcoes,
  AssinaturaResultado,

  // Captcha
  CaptchaType,
  CaptchaInfo,
  CaptchaSolution,
  CaptchaConfig,

  // Eventos
  TribunalEvents,

  // Seletores
  SemanticSelector,
  TribunalSelectors,

  // Resiliência
  ResilienceConfig,
  AgentFallbackConfig,
  SelectorStoreEntry,
} from './types/index.js';
