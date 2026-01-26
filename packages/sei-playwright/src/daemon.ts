/**
 * SEI Daemon - Serviço de monitoramento contínuo
 *
 * Mantém o browser aberto em background e monitora:
 * - Novos processos recebidos
 * - Blocos de assinatura pendentes
 * - Prazos vencendo
 * - Retornos programados
 *
 * @example
 * ```typescript
 * const daemon = new SEIDaemon({
 *   baseUrl: 'https://sei.mg.gov.br',
 *   credentials: {
 *     usuario: 'meu.usuario',
 *     senha: 'minhaSenha',
 *     orgao: 'CODEMGE',
 *   },
 *   watch: {
 *     types: ['processos_recebidos', 'blocos_assinatura', 'prazos'],
 *     interval: 60000, // 1 minuto
 *   },
 *   notifications: {
 *     email: { ... },
 *     webhook: 'https://meu-sistema.com/webhook/sei',
 *   },
 * });
 *
 * await daemon.start();
 * // Roda indefinidamente...
 * ```
 */

import { SEIClient } from './client.js';
import { SEIWatcher, type WatchType, type WatchEvent } from './watcher.js';
import { SEINotificationService, type EmailConfig, type NotificationPayload, type EnrichedItem } from './notifications.js';
import { EventEmitter } from 'events';

export interface DaemonConfig {
  /** URL base do SEI */
  baseUrl: string;

  /** Credenciais de login (não necessário se usar CDP com sessão já autenticada) */
  credentials?: {
    usuario: string;
    senha: string;
    orgao?: string;
  };

  /** Configurações de monitoramento */
  watch?: {
    /** Tipos para monitorar */
    types?: WatchType[];
    /** Intervalo de polling em ms (padrão: 60000 = 1 min) */
    interval?: number;
    /** Máximo de itens */
    maxItems?: number;
  };

  /** Configurações de notificação */
  notifications?: {
    /** Configuração de email */
    email?: EmailConfig;
    /** URL do webhook */
    webhook?: string;
    /** Destinatários (para email) */
    recipients?: Array<{
      userId: string;
      email: string;
      nome: string;
    }>;
  };

  /** Configurações do browser */
  browser?: {
    /** Executar headless (ignorado se usar CDP) */
    headless?: boolean;
    /** Timeout */
    timeout?: number;

    // ===== CDP Mode =====
    /** Endpoint CDP para conectar ao Chrome já aberto */
    cdpEndpoint?: string;
    /** Tentar reconectar automaticamente se perder conexão CDP */
    cdpAutoReconnect?: boolean;
  };

  /** Intervalo para verificar sessão (padrão: 5 min) */
  sessionCheckInterval?: number;

  /** Intervalo para manter sessão ativa (padrão: 2 min, desabilitado em CDP) */
  keepAliveInterval?: number;
}

type DaemonEvents = {
  started: () => void;
  stopped: () => void;
  login: () => void;
  relogin: () => void;
  sessionExpired: () => void;
  event: (event: WatchEvent) => void;
  notification: (payload: NotificationPayload) => void;
  error: (error: Error) => void;
};

/**
 * Daemon de monitoramento contínuo do SEI
 */
export class SEIDaemon extends EventEmitter {
  private config: DaemonConfig;
  private client: SEIClient | null = null;
  private watcher: SEIWatcher | null = null;
  private notifier: SEINotificationService | null = null;

  private isRunning = false;
  private sessionCheckTimer: NodeJS.Timeout | null = null;
  private keepAliveTimer: NodeJS.Timeout | null = null;
  private loginAttempts = 0;
  private maxLoginAttempts = 3;

  constructor(config: DaemonConfig) {
    super();
    this.config = {
      ...config,
      watch: {
        types: config.watch?.types ?? ['processos_recebidos', 'blocos_assinatura', 'prazos'],
        interval: config.watch?.interval ?? 60000,
        maxItems: config.watch?.maxItems ?? 100,
      },
      sessionCheckInterval: config.sessionCheckInterval ?? 300000, // 5 min
      keepAliveInterval: config.keepAliveInterval ?? 120000, // 2 min
    };
  }

  /** Modo CDP ativo */
  private isCdpMode = false;

  /** Inicia o daemon */
  async start(): Promise<void> {
    if (this.isRunning) {
      console.log('⚠️ Daemon já está rodando');
      return;
    }

    const cdpEndpoint = this.config.browser?.cdpEndpoint;
    this.isCdpMode = !!cdpEndpoint;

    console.log('🚀 Iniciando SEI Daemon...');
    console.log(`   URL: ${this.config.baseUrl}`);
    console.log(`   Modo: ${this.isCdpMode ? 'CDP (Chrome já aberto)' : 'Browser próprio'}`);
    if (this.isCdpMode) {
      console.log(`   CDP Endpoint: ${cdpEndpoint}`);
    } else {
      console.log(`   Usuário: ${this.config.credentials?.usuario || '(não configurado)'}`);
    }
    console.log(`   Monitorando: ${this.config.watch!.types!.join(', ')}`);
    console.log(`   Intervalo: ${this.config.watch!.interval! / 1000}s`);

    try {
      // Inicializa cliente
      this.client = new SEIClient({
        baseUrl: this.config.baseUrl,
        browser: this.config.credentials,
        playwright: {
          headless: this.config.browser?.headless ?? true,
          timeout: this.config.browser?.timeout ?? 60000,
          cdpEndpoint: cdpEndpoint,
        },
      });

      await this.client.init();

      // Verifica se já está logado (CDP mode) ou faz login
      if (this.isCdpMode) {
        const loggedIn = await this.client.isLoggedIn();
        if (loggedIn) {
          console.log('   ✅ Já logado no Chrome');
          this.emit('login');
        } else {
          console.log('   ⚠️ Não está logado no Chrome!');
          if (this.config.credentials?.usuario && this.config.credentials?.senha) {
            console.log('   🔐 Fazendo login...');
            await this.doLogin();
          } else {
            throw new Error('Chrome não está logado no SEI. Faça login manualmente e reinicie o daemon.');
          }
        }
      } else {
        // Modo normal: faz login
        await this.doLogin();
      }

      // Inicializa notificador
      if (this.config.notifications?.email) {
        this.notifier = new SEINotificationService({
          email: this.config.notifications.email,
        });
      }

      // Inicializa watcher
      this.watcher = new SEIWatcher(this.client, {
        interval: this.config.watch!.interval,
        types: this.config.watch!.types,
        maxItems: this.config.watch!.maxItems,
      });

      // Configura handlers de eventos
      this.setupEventHandlers();

      // Inicia watcher
      this.watcher.start();

      // Inicia verificação de sessão
      this.startSessionCheck();

      // Inicia keep-alive (apenas em modo não-CDP)
      if (!this.isCdpMode) {
        this.startKeepAlive();
      }

      this.isRunning = true;
      this.emit('started');

      console.log('✅ SEI Daemon iniciado com sucesso!');
      console.log('   Pressione Ctrl+C para parar');

    } catch (error) {
      console.error('❌ Erro ao iniciar daemon:', error);
      this.emit('error', error instanceof Error ? error : new Error(String(error)));
      throw error;
    }
  }

  /** Para o daemon */
  async stop(): Promise<void> {
    if (!this.isRunning) return;

    console.log('🛑 Parando SEI Daemon...');

    // Para timers
    if (this.sessionCheckTimer) {
      clearInterval(this.sessionCheckTimer);
      this.sessionCheckTimer = null;
    }
    if (this.keepAliveTimer) {
      clearInterval(this.keepAliveTimer);
      this.keepAliveTimer = null;
    }

    // Para watcher
    this.watcher?.stop();

    // Fecha cliente (mas não fecha o Chrome em modo CDP!)
    if (this.isCdpMode) {
      console.log('   💡 Chrome não fechado (modo CDP)');
      this.client = null;
    } else {
      await this.client?.close();
    }

    this.isRunning = false;
    this.emit('stopped');

    console.log('✅ SEI Daemon parado');
  }

  /** Realiza login */
  private async doLogin(): Promise<void> {
    if (!this.client) throw new Error('Cliente não inicializado');
    if (!this.config.credentials?.usuario || !this.config.credentials?.senha) {
      throw new Error('Credenciais não configuradas');
    }

    console.log('🔐 Fazendo login...');

    const success = await this.client.login(
      this.config.credentials!.usuario,
      this.config.credentials!.senha,
      this.config.credentials!.orgao
    );

    if (!success) {
      this.loginAttempts++;
      if (this.loginAttempts >= this.maxLoginAttempts) {
        throw new Error(`Falha no login após ${this.maxLoginAttempts} tentativas`);
      }
      console.log(`   ⚠️ Tentativa ${this.loginAttempts}/${this.maxLoginAttempts} falhou, tentando novamente em 10s...`);
      await this.sleep(10000);
      return this.doLogin();
    }

    this.loginAttempts = 0;
    console.log('   ✅ Login OK');
    this.emit('login');
  }

  /** Configura handlers de eventos do watcher */
  private setupEventHandlers(): void {
    if (!this.watcher) return;

    const types = this.config.watch!.types!;

    for (const type of types) {
      this.watcher.on(type, async (event) => {
        console.log(`📬 Novo evento: ${type} (${event.items.length} itens)`);
        this.emit('event', event);

        // Envia notificações
        await this.sendNotifications(event);
      });
    }

    this.watcher.on('error', (error) => {
      console.error('❌ Erro no watcher:', error.message);
      this.emit('error', error);
    });

    this.watcher.on('check', (type, source) => {
      const timestamp = new Date().toLocaleTimeString('pt-BR');
      console.log(`   [${timestamp}] Verificando ${type} via ${source}...`);
    });
  }

  /** Envia notificações */
  private async sendNotifications(event: WatchEvent): Promise<void> {
    const recipients = this.config.notifications?.recipients ?? [];
    const webhook = this.config.notifications?.webhook;

    // Enriquece itens com links
    const enrichedItems: EnrichedItem[] = event.items.map(item => ({
      ...item,
      linkProcesso: `${this.config.baseUrl}/sei/controlador.php?acao=procedimento_trabalhar&id_procedimento=${item.id}`,
    }));

    // Envia para cada destinatário
    for (const recipient of recipients) {
      const payload: NotificationPayload = {
        type: event.type,
        userId: recipient.userId,
        email: recipient.email,
        nome: recipient.nome,
        items: enrichedItems,
        timestamp: event.timestamp,
        seiUrl: this.config.baseUrl,
      };

      // Email
      if (this.notifier) {
        const sent = await this.notifier.sendEmail(payload);
        if (sent) {
          console.log(`   📧 Email enviado para ${recipient.email}`);
        }
      }

      this.emit('notification', payload);
    }

    // Webhook
    if (webhook && this.notifier) {
      const payload: NotificationPayload = {
        type: event.type,
        userId: 'system',
        email: '',
        nome: 'Sistema',
        items: enrichedItems,
        timestamp: event.timestamp,
        seiUrl: this.config.baseUrl,
      };

      const sent = await this.notifier.sendWebhook(webhook, payload);
      if (sent) {
        console.log(`   🔗 Webhook enviado para ${webhook}`);
      }
    }
  }

  /** Inicia verificação periódica de sessão */
  private startSessionCheck(): void {
    this.sessionCheckTimer = setInterval(async () => {
      try {
        const loggedIn = await this.client?.isLoggedIn();
        if (!loggedIn) {
          console.log('⚠️ Sessão expirada, fazendo relogin...');
          this.emit('sessionExpired');
          await this.doLogin();
          this.emit('relogin');
        }
      } catch (error) {
        console.error('❌ Erro ao verificar sessão:', error);
      }
    }, this.config.sessionCheckInterval!);
  }

  /** Inicia keep-alive (mantém sessão ativa) */
  private startKeepAlive(): void {
    this.keepAliveTimer = setInterval(async () => {
      try {
        // Navega para página principal para manter sessão ativa
        const browserClient = this.client?.getBrowserClient();
        if (browserClient) {
          const page = browserClient.getPage();
          // Refresh suave - apenas recarrega a página atual
          await page.reload({ waitUntil: 'domcontentloaded' });
        }
      } catch (error) {
        // Ignora erros de keep-alive
      }
    }, this.config.keepAliveInterval!);
  }

  /** Verifica se está rodando */
  get running(): boolean {
    return this.isRunning;
  }

  /** Acesso ao cliente */
  getClient(): SEIClient | null {
    return this.client;
  }

  /** Acesso ao watcher */
  getWatcher(): SEIWatcher | null {
    return this.watcher;
  }

  /** Sleep helper */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  // Typed event emitter
  on<K extends keyof DaemonEvents>(event: K, listener: DaemonEvents[K]): this {
    return super.on(event, listener);
  }

  emit<K extends keyof DaemonEvents>(event: K, ...args: Parameters<DaemonEvents[K]>): boolean {
    return super.emit(event, ...args);
  }
}

export default SEIDaemon;
