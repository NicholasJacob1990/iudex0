/**
 * SEI Service - Serviço completo de monitoramento e notificações
 * Integra: Usuários + Watcher + Notificações + Download
 */

import { EventEmitter } from 'events';
import { mkdir, writeFile } from 'fs/promises';
import { join } from 'path';
import { SEIClient } from './client.js';
import { SEIWatcher, type WatchEvent, type WatchItem, type WatchType } from './watcher.js';
import { SEIUserManager, type SEIUserConfig, type SEICredentials } from './users.js';
import {
  SEINotificationService,
  type EmailConfig,
  type NotificationPayload,
  type EnrichedItem,
  type PrazoInfo,
  type DocumentoDownload,
} from './notifications.js';

export interface SEIServiceConfig {
  /** Diretório para dados (usuários, downloads) */
  dataPath: string;
  /** Senha mestre para criptografia */
  masterPassword: string;
  /** Configuração de email (opcional) */
  email?: EmailConfig;
  /** Intervalo de polling em ms (padrão: 60000 = 1 min) */
  pollInterval?: number;
  /** Tipos para monitorar */
  watchTypes?: WatchType[];
  /** Opções do Playwright */
  playwright?: {
    headless?: boolean;
    timeout?: number;
  };
}

interface UserSession {
  client: SEIClient;
  watcher: SEIWatcher;
  config: SEIUserConfig;
}

type ServiceEvents = {
  'user:added': (user: SEIUserConfig) => void;
  'user:removed': (userId: string) => void;
  'user:error': (userId: string, error: Error) => void;
  'notification:sent': (userId: string, type: string) => void;
  'notification:error': (userId: string, error: Error) => void;
  'started': () => void;
  'stopped': () => void;
};

/**
 * Serviço completo de monitoramento SEI
 *
 * @example
 * ```typescript
 * const service = new SEIService({
 *   dataPath: './data',
 *   masterPassword: process.env.MASTER_PASSWORD!,
 *   email: {
 *     host: 'smtp.gmail.com',
 *     port: 587,
 *     secure: false,
 *     auth: { user: 'x', pass: 'y' },
 *     from: 'noreply@iudex.com',
 *   },
 *   pollInterval: 60000,
 *   watchTypes: ['processos_recebidos', 'blocos_assinatura', 'prazos'],
 * });
 *
 * await service.init();
 *
 * // Adicionar usuário
 * await service.addUser({
 *   id: 'user-123',
 *   nome: 'João Silva',
 *   email: 'joao@email.com',
 *   seiUrl: 'https://sei.mg.gov.br',
 *   credentials: { usuario: 'joao.silva', senha: 'senha123' },
 * });
 *
 * // Iniciar monitoramento de todos os usuários
 * await service.startAll();
 * ```
 */
export class SEIService extends EventEmitter {
  private config: SEIServiceConfig;
  private userManager: SEIUserManager;
  private notifier: SEINotificationService;
  private sessions: Map<string, UserSession> = new Map();
  private isRunning = false;

  constructor(config: SEIServiceConfig) {
    super();
    this.config = {
      pollInterval: 60000,
      watchTypes: ['processos_recebidos', 'blocos_assinatura', 'prazos', 'retornos_programados'],
      playwright: { headless: true, timeout: 30000 },
      ...config,
    };

    this.userManager = new SEIUserManager({
      storagePath: config.dataPath,
      masterPassword: config.masterPassword,
    });

    this.notifier = new SEINotificationService({
      email: config.email,
    });
  }

  /** Inicializa o serviço */
  async init(): Promise<void> {
    await this.userManager.init();

    // Criar diretório de downloads
    await mkdir(join(this.config.dataPath, 'downloads'), { recursive: true });
  }

  // ============================================
  // Gestão de Usuários
  // ============================================

  /** Adiciona um novo usuário */
  async addUser(options: {
    id: string;
    nome: string;
    email: string;
    seiUrl: string;
    orgao?: string;
    credentials: SEICredentials;
    notifications?: Partial<SEIUserConfig['notifications']>;
  }): Promise<SEIUserConfig> {
    const user = await this.userManager.addUser(options);
    this.emit('user:added', user);
    return user;
  }

  /** Remove um usuário */
  async removeUser(userId: string): Promise<void> {
    // Parar sessão se ativa
    await this.stopUser(userId);
    await this.userManager.removeUser(userId);
    this.emit('user:removed', userId);
  }

  /** Obtém configuração de usuário */
  getUser(userId: string): SEIUserConfig | null {
    return this.userManager.getUser(userId);
  }

  /** Lista todos os usuários */
  getAllUsers(): SEIUserConfig[] {
    return this.userManager.getAllUsers();
  }

  /** Atualiza configurações de usuário */
  async updateUser(
    userId: string,
    updates: Partial<Omit<SEIUserConfig, 'id' | 'createdAt'>>
  ): Promise<SEIUserConfig> {
    return this.userManager.updateUser(userId, updates);
  }

  /** Atualiza credenciais */
  async updateCredentials(userId: string, credentials: SEICredentials): Promise<void> {
    await this.userManager.updateCredentials(userId, credentials);

    // Reiniciar sessão se ativa
    if (this.sessions.has(userId)) {
      await this.stopUser(userId);
      await this.startUser(userId);
    }
  }

  // ============================================
  // Monitoramento
  // ============================================

  /** Inicia monitoramento de um usuário */
  async startUser(userId: string): Promise<boolean> {
    const user = this.userManager.getUser(userId);
    if (!user) {
      throw new Error(`Usuário ${userId} não encontrado`);
    }

    if (!user.active) {
      throw new Error(`Usuário ${userId} está inativo`);
    }

    if (this.sessions.has(userId)) {
      return true; // Já está rodando
    }

    const credentials = this.userManager.getCredentials(userId);
    if (!credentials) {
      throw new Error(`Credenciais de ${userId} não encontradas`);
    }

    try {
      // Criar cliente SEI
      const client = new SEIClient({
        baseUrl: user.seiUrl,
        browser: {
          usuario: credentials.usuario,
          senha: credentials.senha,
          orgao: user.orgao,
        },
        playwright: this.config.playwright,
      });

      await client.init();

      // Login
      const loggedIn = await client.login();
      if (!loggedIn) {
        await client.close();
        throw new Error('Falha no login');
      }

      // Criar watcher
      const watcher = new SEIWatcher(client, {
        interval: this.config.pollInterval,
        types: this.config.watchTypes,
      });

      // Configurar handlers
      this.setupWatcherHandlers(watcher, user);

      // Iniciar
      watcher.start();

      // Salvar sessão
      this.sessions.set(userId, { client, watcher, config: user });

      await this.userManager.updateLastCheck(userId);

      return true;
    } catch (error) {
      this.emit('user:error', userId, error instanceof Error ? error : new Error(String(error)));
      return false;
    }
  }

  /** Para monitoramento de um usuário */
  async stopUser(userId: string): Promise<void> {
    const session = this.sessions.get(userId);
    if (!session) return;

    session.watcher.stop();
    await session.client.close();
    this.sessions.delete(userId);
  }

  /** Inicia monitoramento de todos os usuários ativos */
  async startAll(): Promise<void> {
    const users = this.userManager.getActiveUsers();

    for (const user of users) {
      try {
        await this.startUser(user.id);
      } catch (error) {
        console.error(`Erro ao iniciar ${user.id}:`, error);
      }
    }

    this.isRunning = true;
    this.emit('started');
  }

  /** Para monitoramento de todos os usuários */
  async stopAll(): Promise<void> {
    for (const userId of this.sessions.keys()) {
      await this.stopUser(userId);
    }

    this.isRunning = false;
    this.emit('stopped');
  }

  /** Verifica se está rodando */
  get running(): boolean {
    return this.isRunning;
  }

  /** Lista sessões ativas */
  getActiveSessions(): string[] {
    return Array.from(this.sessions.keys());
  }

  // ============================================
  // Handlers do Watcher
  // ============================================

  private setupWatcherHandlers(watcher: SEIWatcher, user: SEIUserConfig): void {
    const types: WatchType[] = ['processos_recebidos', 'blocos_assinatura', 'prazos', 'retornos_programados'];

    for (const type of types) {
      if (!user.notifications.events[type as keyof typeof user.notifications.events]) {
        continue;
      }

      watcher.on(type, async (event: WatchEvent) => {
        try {
          await this.handleWatchEvent(user, event);
        } catch (error) {
          this.emit('notification:error', user.id, error instanceof Error ? error : new Error(String(error)));
        }
      });
    }

    watcher.on('error', (error) => {
      this.emit('user:error', user.id, error);
    });
  }

  /** Processa evento do watcher */
  private async handleWatchEvent(user: SEIUserConfig, event: WatchEvent): Promise<void> {
    const session = this.sessions.get(user.id);
    if (!session) return;

    // Enriquecer itens com teor, prazos e documentos
    const enrichedItems = await this.enrichItems(session, user, event);

    // Criar payload
    const payload: NotificationPayload = {
      type: event.type,
      userId: user.id,
      email: user.email,
      nome: user.nome,
      items: enrichedItems,
      timestamp: event.timestamp,
      seiUrl: user.seiUrl,
    };

    // Enviar email
    if (user.notifications.email) {
      const sent = await this.notifier.sendEmail(payload);
      if (sent) {
        this.emit('notification:sent', user.id, event.type);
      }
    }

    // Enviar webhook
    if (user.notifications.push && user.notifications.webhookUrl) {
      await this.notifier.sendWebhook(user.notifications.webhookUrl, payload);
    }

    // Atualizar lastCheck
    await this.userManager.updateLastCheck(user.id);
  }

  /** Enriquece itens com informações adicionais */
  private async enrichItems(
    session: UserSession,
    user: SEIUserConfig,
    event: WatchEvent
  ): Promise<EnrichedItem[]> {
    const enriched: EnrichedItem[] = [];

    for (const item of event.items) {
      const enrichedItem: EnrichedItem = { ...item };

      try {
        // Abrir processo
        const browserClient = session.client.getBrowserClient();
        if (!browserClient) continue;

        const opened = await browserClient.openProcess(item.numero ?? item.id);
        if (!opened) continue;

        // Extrair prazo se existir
        enrichedItem.prazo = await this.extractPrazo(browserClient);

        // Extrair teor do documento se configurado
        if (user.notifications.includeContent) {
          enrichedItem.teor = await this.extractTeor(browserClient, item);
        }

        // Listar documentos da data atual
        const docs = await browserClient.listDocuments();
        const hoje = new Date().toLocaleDateString('pt-BR');
        enrichedItem.documentos = docs
          .filter((d) => d.tipo && d.titulo)
          .slice(0, 10) // Limitar a 10 documentos
          .map((d) => ({
            id: d.id,
            nome: d.titulo,
            tipo: d.tipo,
            data: hoje,
          }));

        // Download de documentos se configurado
        if (user.notifications.attachDocuments && enrichedItem.documentos) {
          enrichedItem.documentos = await this.downloadDocuments(
            session,
            user,
            enrichedItem.documentos
          );
        }

        // Download do processo completo se configurado
        if (user.notifications.downloadProcess) {
          const processPath = await this.downloadProcess(session, user, item);
          if (processPath) {
            enrichedItem.documentos = enrichedItem.documentos ?? [];
            enrichedItem.documentos.push({
              id: 'processo-completo',
              nome: `Processo_${item.numero?.replace(/[^0-9]/g, '') ?? item.id}.pdf`,
              tipo: 'Processo Completo',
              data: hoje,
              filePath: processPath,
            });
          }
        }

        // Link do processo
        enrichedItem.linkProcesso = `${user.seiUrl}/sei/controlador.php?acao=procedimento_trabalhar&id_procedimento=${item.id}`;
      } catch (error) {
        console.error(`Erro ao enriquecer item ${item.id}:`, error);
      }

      enriched.push(enrichedItem);
    }

    return enriched;
  }

  /** Extrai informações de prazo */
  private async extractPrazo(
    browserClient: import('./browser/client.js').SEIBrowserClient
  ): Promise<PrazoInfo | undefined> {
    try {
      const page = browserClient.getPage();

      // Procurar indicador de prazo na página
      const prazoEl = await page.$('[class*="prazo"], .marcador-prazo, [title*="Prazo"]');
      if (!prazoEl) return undefined;

      const prazoText = await prazoEl.textContent();
      if (!prazoText) return undefined;

      // Extrair data e dias
      const dataMatch = prazoText.match(/(\d{2}\/\d{2}\/\d{4})/);
      const diasMatch = prazoText.match(/(-?\d+)\s*(dias?|úteis?|corridos?)/i);

      if (!dataMatch) return undefined;

      const diasRestantes = diasMatch ? parseInt(diasMatch[1], 10) : 0;
      const tipo = prazoText.toLowerCase().includes('úteis') ? 'util' : 'corrido';

      let status: PrazoInfo['status'] = 'normal';
      if (diasRestantes < 0) {
        status = 'vencido';
      } else if (diasRestantes === 0) {
        status = 'vencendo_hoje';
      } else if (diasRestantes <= 3) {
        status = 'proximo';
      }

      return {
        dataLimite: dataMatch[1],
        diasRestantes,
        tipo,
        status,
      };
    } catch {
      return undefined;
    }
  }

  /** Extrai teor do documento */
  private async extractTeor(
    browserClient: import('./browser/client.js').SEIBrowserClient,
    item: WatchItem
  ): Promise<string | undefined> {
    try {
      const page = browserClient.getPage();

      // Clicar no primeiro documento se houver
      const docLink = await page.$('#divArvore a[href*="documento"], .arvore a[href*="documento"]');
      if (docLink) {
        await docLink.click();
        await page.waitForLoadState('networkidle');
      }

      // Tentar extrair conteúdo do iframe
      const iframe = page.frameLocator('iframe[name="ifrVisualizacao"], iframe[name="ifrConteudo"]');
      const body = iframe.locator('body');

      const text = await body.textContent({ timeout: 5000 });
      return text?.trim().substring(0, 2000); // Limitar a 2000 caracteres
    } catch {
      return undefined;
    }
  }

  /** Baixa documentos */
  private async downloadDocuments(
    session: UserSession,
    user: SEIUserConfig,
    docs: DocumentoDownload[]
  ): Promise<DocumentoDownload[]> {
    const downloadPath = join(this.config.dataPath, 'downloads', user.id);
    await mkdir(downloadPath, { recursive: true });

    for (const doc of docs) {
      try {
        const page = session.client.getBrowserClient()?.getPage();
        if (!page) continue;

        // Clicar no link de download
        const downloadLink = await page.$(`a[href*="documento_download"][href*="${doc.id}"]`);
        if (!downloadLink) continue;

        const downloadPromise = page.waitForEvent('download', { timeout: 10000 });
        await downloadLink.click();

        const download = await downloadPromise;
        const filePath = join(downloadPath, doc.nome);
        await download.saveAs(filePath);

        doc.filePath = filePath;
      } catch {
        // Ignorar erros de download individual
      }
    }

    return docs;
  }

  /** Baixa processo completo */
  private async downloadProcess(
    session: UserSession,
    user: SEIUserConfig,
    item: WatchItem
  ): Promise<string | undefined> {
    try {
      const browserClient = session.client.getBrowserClient();
      if (!browserClient) return undefined;

      const downloadPath = join(this.config.dataPath, 'downloads', user.id);
      await mkdir(downloadPath, { recursive: true });

      const page = browserClient.getPage();

      // Clicar em gerar PDF
      const pdfBtn = await page.$('a[href*="gerar_pdf"], a[href*="procedimento_gerar_pdf"]');
      if (!pdfBtn) return undefined;

      const downloadPromise = page.waitForEvent('download', { timeout: 30000 });
      await pdfBtn.click();

      // Aguardar modal e confirmar se necessário
      await page.waitForTimeout(1000);
      const confirmBtn = await page.$('input[value*="Gerar"], #btnGerar');
      if (confirmBtn) {
        await confirmBtn.click();
      }

      const download = await downloadPromise;
      const filePath = join(downloadPath, `Processo_${item.numero?.replace(/[^0-9]/g, '') ?? item.id}.pdf`);
      await download.saveAs(filePath);

      return filePath;
    } catch {
      return undefined;
    }
  }

  // ============================================
  // Event Emitter Typed
  // ============================================

  on<K extends keyof ServiceEvents>(event: K, listener: ServiceEvents[K]): this {
    return super.on(event, listener);
  }

  emit<K extends keyof ServiceEvents>(event: K, ...args: Parameters<ServiceEvents[K]>): boolean {
    return super.emit(event, ...args);
  }
}

export default SEIService;
