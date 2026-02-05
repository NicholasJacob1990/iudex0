/**
 * Persistência de seletores descobertos pelo agent (self-healing)
 *
 * Armazena em JSON local para que seletores descobertos
 * sejam reutilizados sem precisar chamar o LLM novamente.
 */

import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import type { SelectorStoreEntry } from '../types/index.js';

const DEFAULT_DIR = path.join(os.homedir(), '.tribunais-playwright');
const DEFAULT_FILE = 'selector-cache.json';
const DEFAULT_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000; // 30 dias

export class SelectorStore {
  private filePath: string;
  private cache: Map<string, SelectorStoreEntry> = new Map();
  private dirty = false;

  constructor(storePath?: string) {
    this.filePath = storePath ?? path.join(DEFAULT_DIR, DEFAULT_FILE);
    this.load();
  }

  /**
   * Retorna selector descoberto para a chave, ou null se não existir.
   */
  get(key: string): string | null {
    const entry = this.cache.get(key);
    return entry?.discoveredSelector ?? null;
  }

  /**
   * Salva um selector descoberto.
   */
  set(key: string, selector: string): void {
    const now = new Date().toISOString();
    const existing = this.cache.get(key);

    this.cache.set(key, {
      discoveredSelector: selector,
      discoveredAt: existing?.discoveredAt ?? now,
      successCount: existing?.successCount ?? 0,
      lastSuccess: now,
    });

    this.dirty = true;
    this.save();
  }

  /**
   * Registra uso bem-sucedido de um selector do store.
   */
  recordSuccess(key: string): void {
    const entry = this.cache.get(key);
    if (!entry) return;

    entry.successCount++;
    entry.lastSuccess = new Date().toISOString();
    this.dirty = true;
    // Debounce save - não salva a cada hit
    this.debounceSave();
  }

  /**
   * Remove entradas mais antigas que maxAge (ms).
   */
  prune(maxAge: number = DEFAULT_MAX_AGE_MS): number {
    const cutoff = Date.now() - maxAge;
    let removed = 0;

    for (const [key, entry] of this.cache) {
      const lastUsed = new Date(entry.lastSuccess).getTime();
      if (lastUsed < cutoff) {
        this.cache.delete(key);
        removed++;
      }
    }

    if (removed > 0) {
      this.dirty = true;
      this.save();
    }

    return removed;
  }

  /**
   * Número de entradas no store.
   */
  get size(): number {
    return this.cache.size;
  }

  // ============================================
  // Persistência
  // ============================================

  private load(): void {
    try {
      if (fs.existsSync(this.filePath)) {
        const raw = fs.readFileSync(this.filePath, 'utf-8');
        const data = JSON.parse(raw) as Record<string, SelectorStoreEntry>;
        for (const [key, entry] of Object.entries(data)) {
          this.cache.set(key, entry);
        }
      }
    } catch {
      // Se falhar ao carregar, começa vazio
    }
  }

  private save(): void {
    if (!this.dirty) return;

    try {
      const dir = path.dirname(this.filePath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }

      const data: Record<string, SelectorStoreEntry> = {};
      for (const [key, entry] of this.cache) {
        data[key] = entry;
      }

      fs.writeFileSync(this.filePath, JSON.stringify(data, null, 2), 'utf-8');
      this.dirty = false;
    } catch {
      // Falha silenciosa - store é best-effort
    }
  }

  private saveTimer: ReturnType<typeof setTimeout> | null = null;

  private debounceSave(): void {
    if (this.saveTimer) return;
    this.saveTimer = setTimeout(() => {
      this.saveTimer = null;
      this.save();
    }, 5000);
  }
}
