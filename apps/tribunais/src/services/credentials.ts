/**
 * Serviço de gerenciamento de credenciais
 *
 * Gerencia credenciais de tribunais:
 * - Login com senha (CPF + senha)
 * - Certificado A1 (arquivo .pfx)
 * - Certificado A3 físico (token USB)
 * - Certificado A3 nuvem (Certisign, Serasa, etc.)
 */

import { randomUUID } from 'crypto';
import { encrypt, decrypt, encryptBuffer, decryptBuffer } from './crypto.js';
import type {
  StoredCredential,
  DecryptedCredential,
  AuthType,
  TribunalType,
  CertificateUploadRequest,
} from '../types/index.js';

// Simula banco de dados (em produção, usar Postgres/Redis)
const credentialsStore = new Map<string, StoredCredential>();

export class CredentialService {
  constructor(private encryptionKey: string) {}

  /**
   * Salva credencial de login com senha
   */
  async savePasswordCredential(params: {
    userId: string;
    tribunal: TribunalType;
    tribunalUrl: string;
    name: string;
    cpf: string;
    password: string;
  }): Promise<StoredCredential> {
    const credential: StoredCredential = {
      id: randomUUID(),
      userId: params.userId,
      tribunal: params.tribunal,
      tribunalUrl: params.tribunalUrl,
      authType: 'password',
      name: params.name,
      encryptedCpf: encrypt(params.cpf, this.encryptionKey),
      encryptedPassword: encrypt(params.password, this.encryptionKey),
      createdAt: new Date(),
      updatedAt: new Date(),
    };

    credentialsStore.set(credential.id, credential);
    return this.sanitizeCredential(credential);
  }

  /**
   * Salva certificado A1 (.pfx)
   */
  async saveCertificateA1(params: {
    userId: string;
    tribunal: TribunalType;
    tribunalUrl: string;
    name: string;
    pfxBase64: string;
    pfxPassword: string;
    expiresAt?: Date;
  }): Promise<StoredCredential> {
    const credential: StoredCredential = {
      id: randomUUID(),
      userId: params.userId,
      tribunal: params.tribunal,
      tribunalUrl: params.tribunalUrl,
      authType: 'certificate_a1',
      name: params.name,
      encryptedPfx: encrypt(params.pfxBase64, this.encryptionKey),
      encryptedPfxPassword: encrypt(params.pfxPassword, this.encryptionKey),
      expiresAt: params.expiresAt,
      createdAt: new Date(),
      updatedAt: new Date(),
    };

    credentialsStore.set(credential.id, credential);
    return this.sanitizeCredential(credential);
  }

  /**
   * Salva referência para certificado A3 nuvem
   */
  async saveCertificateA3Cloud(params: {
    userId: string;
    tribunal: TribunalType;
    tribunalUrl: string;
    name: string;
    provider: 'certisign' | 'serasa' | 'safeweb';
  }): Promise<StoredCredential> {
    const credential: StoredCredential = {
      id: randomUUID(),
      userId: params.userId,
      tribunal: params.tribunal,
      tribunalUrl: params.tribunalUrl,
      authType: 'certificate_a3_cloud',
      name: params.name,
      cloudProvider: params.provider,
      createdAt: new Date(),
      updatedAt: new Date(),
    };

    credentialsStore.set(credential.id, credential);
    return this.sanitizeCredential(credential);
  }

  /**
   * Salva referência para certificado A3 físico (token)
   */
  async saveCertificateA3Physical(params: {
    userId: string;
    tribunal: TribunalType;
    tribunalUrl: string;
    name: string;
  }): Promise<StoredCredential> {
    const credential: StoredCredential = {
      id: randomUUID(),
      userId: params.userId,
      tribunal: params.tribunal,
      tribunalUrl: params.tribunalUrl,
      authType: 'certificate_a3_physical',
      name: params.name,
      createdAt: new Date(),
      updatedAt: new Date(),
    };

    credentialsStore.set(credential.id, credential);
    return this.sanitizeCredential(credential);
  }

  /**
   * Lista credenciais do usuário (sem dados sensíveis)
   */
  async listCredentials(userId: string): Promise<StoredCredential[]> {
    const credentials: StoredCredential[] = [];
    for (const credential of credentialsStore.values()) {
      if (credential.userId === userId) {
        credentials.push(this.sanitizeCredential(credential));
      }
    }
    return credentials;
  }

  /**
   * Busca credencial por ID
   */
  async getCredential(credentialId: string): Promise<StoredCredential | null> {
    const credential = credentialsStore.get(credentialId);
    return credential ? this.sanitizeCredential(credential) : null;
  }

  /**
   * Descriptografa credencial para uso
   */
  async decryptCredential(credentialId: string): Promise<DecryptedCredential | null> {
    const credential = credentialsStore.get(credentialId);
    if (!credential) return null;

    const decrypted: DecryptedCredential = {
      id: credential.id,
      authType: credential.authType,
      tribunal: credential.tribunal,
      tribunalUrl: credential.tribunalUrl,
    };

    // Descriptografar baseado no tipo
    switch (credential.authType) {
      case 'password':
        if (credential.encryptedCpf && credential.encryptedPassword) {
          decrypted.cpf = decrypt(credential.encryptedCpf, this.encryptionKey);
          decrypted.password = decrypt(credential.encryptedPassword, this.encryptionKey);
        }
        break;

      case 'certificate_a1':
        if (credential.encryptedPfx && credential.encryptedPfxPassword) {
          const pfxBase64 = decrypt(credential.encryptedPfx, this.encryptionKey);
          decrypted.pfxBuffer = Buffer.from(pfxBase64, 'base64');
          decrypted.pfxPassword = decrypt(credential.encryptedPfxPassword, this.encryptionKey);
        }
        break;

      case 'certificate_a3_cloud':
        decrypted.cloudProvider = credential.cloudProvider;
        break;

      case 'certificate_a3_physical':
        // Não há dados a descriptografar, PIN será solicitado ao usuário
        break;
    }

    // Atualizar último uso
    credential.lastUsedAt = new Date();
    credential.updatedAt = new Date();

    return decrypted;
  }

  /**
   * Deleta credencial
   */
  async deleteCredential(credentialId: string, userId: string): Promise<boolean> {
    const credential = credentialsStore.get(credentialId);
    if (!credential || credential.userId !== userId) {
      return false;
    }
    return credentialsStore.delete(credentialId);
  }

  /**
   * Remove dados sensíveis para retorno
   */
  private sanitizeCredential(credential: StoredCredential): StoredCredential {
    return {
      ...credential,
      encryptedCpf: undefined,
      encryptedPassword: undefined,
      encryptedPfx: undefined,
      encryptedPfxPassword: undefined,
    };
  }
}
