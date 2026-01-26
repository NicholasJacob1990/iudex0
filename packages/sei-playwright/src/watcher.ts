/**
 * SEI Watcher - Monitor de novos processos, documentos e comunicações
 * Usa SOAP quando disponível, fallback para Playwright
 */

import { EventEmitter } from 'events';
import type { SEIClient } from './client.js';

export interface WatcherOptions {
  /** Intervalo de polling em ms (padrão: 30000 = 30s) */
  interval?: number;
  /** Tipos para monitorar */
  types?: WatchType[];
  /** Máximo de itens para comparar por tipo */
  maxItems?: number;
  /** Usar SOAP quando disponível */
  preferSoap?: boolean;
}

export type WatchType =
  | 'processos_recebidos'   // Novos processos recebidos na unidade
  | 'processos_gerados'     // Processos gerados pela unidade
  | 'documentos'            // Novos documentos em processos abertos
  | 'blocos_assinatura'     // Blocos de assinatura pendentes
  | 'retornos_programados'  // Processos com retorno programado
  | 'prazos';               // Processos com prazo vencendo

export interface WatchEvent {
  type: WatchType;
  timestamp: Date;
  items: WatchItem[];
  source: 'soap' | 'browser';
}

export interface WatchItem {
  id: string;
  numero?: string;
  tipo?: string;
  descricao?: string;
  unidade?: string;
  data?: string;
  urgente?: boolean;
  metadata?: Record<string, unknown>;
}

export interface ProcessoRecebido extends WatchItem {
  remetente: string;
  dataRecebimento: string;
  anotacao?: string;
}

export interface DocumentoNovo extends WatchItem {
  processoNumero: string;
  processoId: string;
  tipoDocumento: string;
  assinado: boolean;
}

export interface BlocoAssinatura extends WatchItem {
  quantidadeDocumentos: number;
  unidadeOrigem: string;
}

type WatcherEvents = {
  'processos_recebidos': (event: WatchEvent) => void;
  'processos_gerados': (event: WatchEvent) => void;
  'documentos': (event: WatchEvent) => void;
  'blocos_assinatura': (event: WatchEvent) => void;
  'retornos_programados': (event: WatchEvent) => void;
  'prazos': (event: WatchEvent) => void;
  'error': (error: Error) => void;
  'started': () => void;
  'stopped': () => void;
  'check': (type: WatchType, source: 'soap' | 'browser') => void;
};

/**
 * Monitor de eventos do SEI
 *
 * @example
 * ```typescript
 * const sei = new SEIClient({ ... });
 * await sei.init();
 * await sei.login();
 *
 * const watcher = new SEIWatcher(sei, {
 *   interval: 30000, // 30 segundos
 *   types: ['processos_recebidos', 'blocos_assinatura'],
 * });
 *
 * watcher.on('processos_recebidos', (event) => {
 *   console.log('Novos processos:', event.items);
 *   // Enviar notificação, atualizar UI, etc.
 * });
 *
 * watcher.on('blocos_assinatura', (event) => {
 *   console.log('Blocos para assinar:', event.items);
 * });
 *
 * watcher.start();
 *
 * // Parar quando necessário
 * // watcher.stop();
 * ```
 */
export class SEIWatcher extends EventEmitter {
  private client: SEIClient;
  private options: Required<WatcherOptions>;
  private intervalId: NodeJS.Timeout | null = null;
  private isRunning = false;
  private lastState: Map<WatchType, Map<string, WatchItem>> = new Map();

  constructor(client: SEIClient, options: WatcherOptions = {}) {
    super();
    this.client = client;
    this.options = {
      interval: options.interval ?? 30000,
      types: options.types ?? ['processos_recebidos'],
      maxItems: options.maxItems ?? 100,
      preferSoap: options.preferSoap ?? true,
    };

    // Inicializar estado para cada tipo
    for (const type of this.options.types) {
      this.lastState.set(type, new Map());
    }
  }

  /** Inicia o monitoramento */
  start(): void {
    if (this.isRunning) return;

    this.isRunning = true;
    this.emit('started');

    // Primeira verificação imediata
    this.check();

    // Configurar polling
    this.intervalId = setInterval(() => {
      this.check();
    }, this.options.interval);
  }

  /** Para o monitoramento */
  stop(): void {
    if (!this.isRunning) return;

    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }

    this.isRunning = false;
    this.emit('stopped');
  }

  /** Verifica se está rodando */
  get running(): boolean {
    return this.isRunning;
  }

  /** Força uma verificação imediata */
  async check(): Promise<void> {
    for (const type of this.options.types) {
      try {
        await this.checkType(type);
      } catch (error) {
        this.emit('error', error instanceof Error ? error : new Error(String(error)));
      }
    }
  }

  /** Verifica um tipo específico */
  private async checkType(type: WatchType): Promise<void> {
    let items: WatchItem[] = [];
    let source: 'soap' | 'browser' = 'browser';

    // Tentar SOAP primeiro se preferido e disponível
    if (this.options.preferSoap && this.client.hasSoap) {
      try {
        items = await this.fetchViaSoap(type);
        source = 'soap';
      } catch {
        // Fallback para browser
        items = await this.fetchViaBrowser(type);
        source = 'browser';
      }
    } else {
      items = await this.fetchViaBrowser(type);
      source = 'browser';
    }

    this.emit('check', type, source);

    // Comparar com estado anterior
    const previousState = this.lastState.get(type) ?? new Map();
    const newItems: WatchItem[] = [];

    for (const item of items) {
      if (!previousState.has(item.id)) {
        newItems.push(item);
      }
    }

    // Atualizar estado
    const newState = new Map<string, WatchItem>();
    for (const item of items.slice(0, this.options.maxItems)) {
      newState.set(item.id, item);
    }
    this.lastState.set(type, newState);

    // Emitir evento se houver novos itens
    // (ignorar primeira execução quando não há estado anterior)
    if (newItems.length > 0 && previousState.size > 0) {
      const event: WatchEvent = {
        type,
        timestamp: new Date(),
        items: newItems,
        source,
      };
      this.emit(type, event);
    }
  }

  /** Busca dados via SOAP */
  private async fetchViaSoap(type: WatchType): Promise<WatchItem[]> {
    const soapClient = this.client.getSoapClient();
    if (!soapClient) throw new Error('SOAP client não disponível');

    // Nota: Precisaria do idUnidade configurado
    // Por enquanto, lança erro para usar browser
    throw new Error('SOAP fetch não implementado para este tipo');

    // Implementação futura:
    // switch (type) {
    //   case 'processos_recebidos':
    //     const result = await soapClient.listarAndamentos(...);
    //     return this.mapAndamentosToItems(result);
    //   ...
    // }
  }

  /** Busca dados via Playwright/Browser */
  private async fetchViaBrowser(type: WatchType): Promise<WatchItem[]> {
    const browserClient = this.client.getBrowserClient();
    if (!browserClient) throw new Error('Browser client não disponível');

    const page = browserClient.getPage();

    switch (type) {
      case 'processos_recebidos':
        return this.fetchProcessosRecebidos(page);

      case 'processos_gerados':
        return this.fetchProcessosGerados(page);

      case 'blocos_assinatura':
        return this.fetchBlocosAssinatura(page);

      case 'documentos':
        return this.fetchDocumentosNovos(page);

      case 'retornos_programados':
        return this.fetchRetornosProgramados(page);

      case 'prazos':
        return this.fetchPrazos(page);

      default:
        return [];
    }
  }

  /** Busca processos recebidos */
  private async fetchProcessosRecebidos(page: import('playwright').Page): Promise<WatchItem[]> {
    // Navegar para controle de processos - recebidos
    await page.goto(await this.buildUrl('procedimento_controlar', { acao_origem: 'procedimento_recebido' }));
    await page.waitForLoadState('networkidle');

    const items: WatchItem[] = [];

    // Extrair da tabela de processos
    const rows = await page.$$('table#tblProcessosRecebidos tbody tr, #divProcessos .processo-item, .infraTable tbody tr');

    for (const row of rows.slice(0, this.options.maxItems)) {
      try {
        const cells = await row.$$('td');
        const link = await row.$('a[href*="procedimento"]');

        const numero = await link?.textContent() ?? await cells[0]?.textContent() ?? '';
        const href = await link?.getAttribute('href') ?? '';
        const idMatch = href.match(/id_procedimento=(\d+)/);

        if (!idMatch) continue;

        const item: ProcessoRecebido = {
          id: idMatch[1],
          numero: numero.trim(),
          tipo: await cells[1]?.textContent() ?? '',
          remetente: await cells[2]?.textContent() ?? '',
          dataRecebimento: await cells[3]?.textContent() ?? '',
          anotacao: await cells[4]?.textContent() ?? '',
          urgente: (await row.$('.marcador-urgente, [class*="urgente"], img[title*="Urgente"]')) !== null,
        };

        items.push(item);
      } catch {
        // Ignorar erros de parsing individual
      }
    }

    return items;
  }

  /** Busca processos gerados */
  private async fetchProcessosGerados(page: import('playwright').Page): Promise<WatchItem[]> {
    await page.goto(await this.buildUrl('procedimento_controlar', { acao_origem: 'procedimento_gerado' }));
    await page.waitForLoadState('networkidle');

    const items: WatchItem[] = [];
    const rows = await page.$$('table tbody tr, .infraTable tbody tr');

    for (const row of rows.slice(0, this.options.maxItems)) {
      try {
        const link = await row.$('a[href*="procedimento"]');
        const href = await link?.getAttribute('href') ?? '';
        const idMatch = href.match(/id_procedimento=(\d+)/);

        if (!idMatch) continue;

        const cells = await row.$$('td');

        items.push({
          id: idMatch[1],
          numero: (await link?.textContent())?.trim() ?? '',
          tipo: await cells[1]?.textContent() ?? '',
          descricao: await cells[2]?.textContent() ?? '',
          data: await cells[3]?.textContent() ?? '',
        });
      } catch {
        // Ignorar erros
      }
    }

    return items;
  }

  /** Busca blocos de assinatura */
  private async fetchBlocosAssinatura(page: import('playwright').Page): Promise<WatchItem[]> {
    await page.goto(await this.buildUrl('bloco_assinatura_listar'));
    await page.waitForLoadState('networkidle');

    const items: WatchItem[] = [];
    const rows = await page.$$('table#tblBlocos tbody tr, .bloco-item');

    for (const row of rows.slice(0, this.options.maxItems)) {
      try {
        const link = await row.$('a[href*="bloco"]');
        const href = await link?.getAttribute('href') ?? '';
        const idMatch = href.match(/id_bloco=(\d+)/);

        if (!idMatch) continue;

        const cells = await row.$$('td');
        const qtdText = await cells[2]?.textContent() ?? '0';

        const item: BlocoAssinatura = {
          id: idMatch[1],
          numero: (await link?.textContent())?.trim() ?? '',
          descricao: await cells[1]?.textContent() ?? '',
          quantidadeDocumentos: parseInt(qtdText.match(/\d+/)?.[0] ?? '0', 10),
          unidadeOrigem: await cells[3]?.textContent() ?? '',
        };

        items.push(item);
      } catch {
        // Ignorar erros
      }
    }

    return items;
  }

  /** Busca documentos novos (requer processo aberto) */
  private async fetchDocumentosNovos(page: import('playwright').Page): Promise<WatchItem[]> {
    // Este método é mais complexo - precisa verificar cada processo aberto
    // Por enquanto, retorna vazio - implementar conforme necessidade
    return [];
  }

  /** Busca retornos programados */
  private async fetchRetornosProgramados(page: import('playwright').Page): Promise<WatchItem[]> {
    await page.goto(await this.buildUrl('procedimento_controlar', { acao_origem: 'retorno_programado' }));
    await page.waitForLoadState('networkidle');

    const items: WatchItem[] = [];
    const rows = await page.$$('table tbody tr');

    for (const row of rows.slice(0, this.options.maxItems)) {
      try {
        const link = await row.$('a[href*="procedimento"]');
        const href = await link?.getAttribute('href') ?? '';
        const idMatch = href.match(/id_procedimento=(\d+)/);

        if (!idMatch) continue;

        const cells = await row.$$('td');

        items.push({
          id: idMatch[1],
          numero: (await link?.textContent())?.trim() ?? '',
          data: await cells[1]?.textContent() ?? '', // Data de retorno
          unidade: await cells[2]?.textContent() ?? '',
        });
      } catch {
        // Ignorar erros
      }
    }

    return items;
  }

  /** Busca processos com prazo */
  private async fetchPrazos(page: import('playwright').Page): Promise<WatchItem[]> {
    await page.goto(await this.buildUrl('procedimento_controlar', { acao_origem: 'prazo' }));
    await page.waitForLoadState('networkidle');

    const items: WatchItem[] = [];
    const rows = await page.$$('table tbody tr, .processo-prazo');

    for (const row of rows.slice(0, this.options.maxItems)) {
      try {
        const link = await row.$('a[href*="procedimento"]');
        const href = await link?.getAttribute('href') ?? '';
        const idMatch = href.match(/id_procedimento=(\d+)/);

        if (!idMatch) continue;

        const cells = await row.$$('td');
        const prazoText = await cells[1]?.textContent() ?? '';

        items.push({
          id: idMatch[1],
          numero: (await link?.textContent())?.trim() ?? '',
          data: prazoText,
          urgente: prazoText.includes('VENCIDO') || prazoText.includes('HOJE'),
          metadata: {
            diasRestantes: parseInt(prazoText.match(/-?\d+/)?.[0] ?? '0', 10),
          },
        });
      } catch {
        // Ignorar erros
      }
    }

    return items;
  }

  /** Constrói URL do SEI */
  private async buildUrl(acao: string, params: Record<string, string> = {}): Promise<string> {
    const browserClient = this.client.getBrowserClient();
    if (!browserClient) throw new Error('Browser client não disponível');

    const page = browserClient.getPage();
    const currentUrl = page.url();
    const baseUrl = currentUrl.match(/^(https?:\/\/[^/]+)/)?.[1] ?? '';

    const searchParams = new URLSearchParams({ acao, ...params });
    return `${baseUrl}/sei/controlador.php?${searchParams.toString()}`;
  }

  // Typed event emitter overloads
  on<K extends keyof WatcherEvents>(event: K, listener: WatcherEvents[K]): this {
    return super.on(event, listener);
  }

  emit<K extends keyof WatcherEvents>(event: K, ...args: Parameters<WatcherEvents[K]>): boolean {
    return super.emit(event, ...args);
  }
}

export default SEIWatcher;
