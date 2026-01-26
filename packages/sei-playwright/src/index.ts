/**
 * sei-playwright - Biblioteca para automação do SEI!
 *
 * @example
 * ```typescript
 * import { SEIClient } from 'sei-playwright';
 *
 * const sei = new SEIClient({
 *   baseUrl: 'https://sei.mg.gov.br',
 *   browser: {
 *     usuario: 'meu.usuario',
 *     senha: 'minhaSenha',
 *   },
 *   playwright: { headless: true },
 * });
 *
 * await sei.init();
 * await sei.login();
 * await sei.openProcess('5030.01.0002527/2025-32');
 * const docs = await sei.listDocuments();
 * await sei.close();
 * ```
 */

// Cliente principal (híbrido)
export { SEIClient, type SEIClientMode, type SEIClientOptions } from './client.js';
export { default } from './client.js';

// Clientes específicos
export { SEIBrowserClient } from './browser/client.js';
export { SEISoapClient, type SOAPConfig, type SOAPAuth } from './soap/client.js';

// Seletores CSS
export { SEI_SELECTORS } from './browser/selectors.js';

// Watcher/Monitor
export {
  SEIWatcher,
  type WatcherOptions,
  type WatchType,
  type WatchEvent,
  type WatchItem,
  type ProcessoRecebido,
  type DocumentoNovo,
  type BlocoAssinatura,
} from './watcher.js';

// Serviço completo
export { SEIService, type SEIServiceConfig } from './service.js';

// API HTTP
export { SEIServiceAPI, type APIConfig } from './api.js';

// Gestão de usuários
export {
  SEIUserManager,
  type SEIUserConfig,
  type SEICredentials,
  type NotificationConfig,
} from './users.js';

// Notificações
export {
  SEINotificationService,
  type EmailConfig,
  type NotificationPayload,
  type EnrichedItem,
  type PrazoInfo,
  type DocumentoDownload,
} from './notifications.js';

// Daemon (monitoramento contínuo)
export { SEIDaemon, type DaemonConfig } from './daemon.js';

// Criptografia
export { encrypt, decrypt, decryptJson, generateSecurePassword } from './crypto.js';

// Tipos
export * from './types.js';
