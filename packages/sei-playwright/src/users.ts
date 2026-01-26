/**
 * Gerenciador de Usuários SEI
 * Armazena credenciais criptografadas e configurações de notificação
 */

import { readFile, writeFile, mkdir } from 'fs/promises';
import { existsSync } from 'fs';
import { join } from 'path';
import { encrypt, decrypt, decryptJson, type EncryptedData } from './crypto.js';

export interface SEIUserConfig {
  /** ID único do usuário */
  id: string;
  /** Nome do usuário */
  nome: string;
  /** Email para notificações */
  email: string;
  /** URL do SEI (ex: https://sei.mg.gov.br) */
  seiUrl: string;
  /** Órgão (se necessário) */
  orgao?: string;
  /** Configurações de notificação */
  notifications: NotificationConfig;
  /** Ativo */
  active: boolean;
  /** Data de criação */
  createdAt: string;
  /** Última verificação */
  lastCheck?: string;
}

export interface SEICredentials {
  usuario: string;
  senha: string;
}

export interface NotificationConfig {
  /** Enviar email */
  email: boolean;
  /** Enviar push (webhook) */
  push: boolean;
  /** URL do webhook para push */
  webhookUrl?: string;
  /** Tipos de eventos para notificar */
  events: {
    processos_recebidos: boolean;
    blocos_assinatura: boolean;
    prazos: boolean;
    retornos_programados: boolean;
  };
  /** Incluir teor do documento no email */
  includeContent: boolean;
  /** Anexar documentos ao email */
  attachDocuments: boolean;
  /** Baixar processo completo */
  downloadProcess: boolean;
}

interface StoredUser {
  config: SEIUserConfig;
  credentials: EncryptedData;
}

interface UsersStore {
  version: number;
  users: StoredUser[];
}

const DEFAULT_NOTIFICATION_CONFIG: NotificationConfig = {
  email: true,
  push: false,
  events: {
    processos_recebidos: true,
    blocos_assinatura: true,
    prazos: true,
    retornos_programados: true,
  },
  includeContent: true,
  attachDocuments: false,
  downloadProcess: false,
};

/**
 * Gerenciador de usuários do SEI
 *
 * @example
 * ```typescript
 * const manager = new SEIUserManager({
 *   storagePath: './data',
 *   masterPassword: process.env.MASTER_PASSWORD!,
 * });
 *
 * await manager.init();
 *
 * // Adicionar usuário
 * await manager.addUser({
 *   id: 'user-123',
 *   nome: 'João Silva',
 *   email: 'joao@email.com',
 *   seiUrl: 'https://sei.mg.gov.br',
 *   credentials: { usuario: 'joao.silva', senha: 'senha123' },
 * });
 *
 * // Listar usuários ativos
 * const users = await manager.getActiveUsers();
 *
 * // Obter credenciais para uso
 * const creds = await manager.getCredentials('user-123');
 * ```
 */
export class SEIUserManager {
  private storagePath: string;
  private masterPassword: string;
  private store: UsersStore | null = null;
  private storeFile: string;

  constructor(options: { storagePath: string; masterPassword: string }) {
    this.storagePath = options.storagePath;
    this.masterPassword = options.masterPassword;
    this.storeFile = join(this.storagePath, 'sei-users.encrypted.json');
  }

  /** Inicializa o gerenciador */
  async init(): Promise<void> {
    // Criar diretório se não existir
    if (!existsSync(this.storagePath)) {
      await mkdir(this.storagePath, { recursive: true });
    }

    // Carregar store existente ou criar novo
    if (existsSync(this.storeFile)) {
      const data = await readFile(this.storeFile, 'utf-8');
      this.store = JSON.parse(data);
    } else {
      this.store = { version: 1, users: [] };
      await this.save();
    }
  }

  /** Salva o store em disco */
  private async save(): Promise<void> {
    if (!this.store) throw new Error('Store não inicializado');
    await writeFile(this.storeFile, JSON.stringify(this.store, null, 2));
  }

  /** Adiciona um novo usuário */
  async addUser(options: {
    id: string;
    nome: string;
    email: string;
    seiUrl: string;
    orgao?: string;
    credentials: SEICredentials;
    notifications?: Partial<NotificationConfig>;
  }): Promise<SEIUserConfig> {
    if (!this.store) throw new Error('Store não inicializado');

    // Verificar se já existe
    const existing = this.store.users.find((u) => u.config.id === options.id);
    if (existing) {
      throw new Error(`Usuário ${options.id} já existe`);
    }

    // Criptografar credenciais
    const encryptedCreds = encrypt(options.credentials, this.masterPassword);

    // Criar config
    const config: SEIUserConfig = {
      id: options.id,
      nome: options.nome,
      email: options.email,
      seiUrl: options.seiUrl,
      orgao: options.orgao,
      notifications: {
        ...DEFAULT_NOTIFICATION_CONFIG,
        ...options.notifications,
      },
      active: true,
      createdAt: new Date().toISOString(),
    };

    // Adicionar ao store
    this.store.users.push({
      config,
      credentials: encryptedCreds,
    });

    await this.save();
    return config;
  }

  /** Atualiza um usuário existente */
  async updateUser(
    id: string,
    updates: Partial<Omit<SEIUserConfig, 'id' | 'createdAt'>>
  ): Promise<SEIUserConfig> {
    if (!this.store) throw new Error('Store não inicializado');

    const userIndex = this.store.users.findIndex((u) => u.config.id === id);
    if (userIndex === -1) {
      throw new Error(`Usuário ${id} não encontrado`);
    }

    // Atualizar config
    this.store.users[userIndex].config = {
      ...this.store.users[userIndex].config,
      ...updates,
    };

    await this.save();
    return this.store.users[userIndex].config;
  }

  /** Atualiza credenciais de um usuário */
  async updateCredentials(id: string, credentials: SEICredentials): Promise<void> {
    if (!this.store) throw new Error('Store não inicializado');

    const userIndex = this.store.users.findIndex((u) => u.config.id === id);
    if (userIndex === -1) {
      throw new Error(`Usuário ${id} não encontrado`);
    }

    // Criptografar novas credenciais
    this.store.users[userIndex].credentials = encrypt(credentials, this.masterPassword);
    await this.save();
  }

  /** Remove um usuário */
  async removeUser(id: string): Promise<void> {
    if (!this.store) throw new Error('Store não inicializado');

    const userIndex = this.store.users.findIndex((u) => u.config.id === id);
    if (userIndex === -1) {
      throw new Error(`Usuário ${id} não encontrado`);
    }

    this.store.users.splice(userIndex, 1);
    await this.save();
  }

  /** Obtém configuração de um usuário */
  getUser(id: string): SEIUserConfig | null {
    if (!this.store) throw new Error('Store não inicializado');

    const user = this.store.users.find((u) => u.config.id === id);
    return user?.config ?? null;
  }

  /** Obtém credenciais descriptografadas */
  getCredentials(id: string): SEICredentials | null {
    if (!this.store) throw new Error('Store não inicializado');

    const user = this.store.users.find((u) => u.config.id === id);
    if (!user) return null;

    return decryptJson<SEICredentials>(user.credentials, this.masterPassword);
  }

  /** Lista todos os usuários */
  getAllUsers(): SEIUserConfig[] {
    if (!this.store) throw new Error('Store não inicializado');
    return this.store.users.map((u) => u.config);
  }

  /** Lista usuários ativos */
  getActiveUsers(): SEIUserConfig[] {
    return this.getAllUsers().filter((u) => u.active);
  }

  /** Atualiza timestamp da última verificação */
  async updateLastCheck(id: string): Promise<void> {
    await this.updateUser(id, { lastCheck: new Date().toISOString() });
  }

  /** Ativa/desativa um usuário */
  async setActive(id: string, active: boolean): Promise<void> {
    await this.updateUser(id, { active });
  }
}

export default SEIUserManager;
