/**
 * Módulo de criptografia para credenciais
 * Usa AES-256-GCM para armazenamento seguro
 */

import { createCipheriv, createDecipheriv, randomBytes, scryptSync } from 'crypto';

const ALGORITHM = 'aes-256-gcm';
const IV_LENGTH = 16;
const SALT_LENGTH = 32;
const TAG_LENGTH = 16;
const KEY_LENGTH = 32;

export interface EncryptedData {
  /** Dados criptografados em base64 */
  encrypted: string;
  /** IV em base64 */
  iv: string;
  /** Auth tag em base64 */
  tag: string;
  /** Salt em base64 */
  salt: string;
}

/**
 * Deriva uma chave a partir de uma senha
 */
function deriveKey(password: string, salt: Buffer): Buffer {
  return scryptSync(password, salt, KEY_LENGTH);
}

/**
 * Criptografa dados sensíveis
 *
 * @param data - Dados a criptografar (string ou objeto)
 * @param masterPassword - Senha mestre para derivar a chave
 * @returns Dados criptografados
 */
export function encrypt(data: string | object, masterPassword: string): EncryptedData {
  const text = typeof data === 'string' ? data : JSON.stringify(data);

  const salt = randomBytes(SALT_LENGTH);
  const key = deriveKey(masterPassword, salt);
  const iv = randomBytes(IV_LENGTH);

  const cipher = createCipheriv(ALGORITHM, key, iv);

  let encrypted = cipher.update(text, 'utf8', 'base64');
  encrypted += cipher.final('base64');

  const tag = cipher.getAuthTag();

  return {
    encrypted,
    iv: iv.toString('base64'),
    tag: tag.toString('base64'),
    salt: salt.toString('base64'),
  };
}

/**
 * Descriptografa dados
 *
 * @param encryptedData - Dados criptografados
 * @param masterPassword - Senha mestre
 * @returns Dados originais
 */
export function decrypt(encryptedData: EncryptedData, masterPassword: string): string {
  const salt = Buffer.from(encryptedData.salt, 'base64');
  const key = deriveKey(masterPassword, salt);
  const iv = Buffer.from(encryptedData.iv, 'base64');
  const tag = Buffer.from(encryptedData.tag, 'base64');

  const decipher = createDecipheriv(ALGORITHM, key, iv);
  decipher.setAuthTag(tag);

  let decrypted = decipher.update(encryptedData.encrypted, 'base64', 'utf8');
  decrypted += decipher.final('utf8');

  return decrypted;
}

/**
 * Descriptografa e faz parse de JSON
 */
export function decryptJson<T = unknown>(encryptedData: EncryptedData, masterPassword: string): T {
  const decrypted = decrypt(encryptedData, masterPassword);
  return JSON.parse(decrypted) as T;
}

/**
 * Gera uma senha aleatória segura
 */
export function generateSecurePassword(length = 32): string {
  return randomBytes(length).toString('base64').slice(0, length);
}

export default { encrypt, decrypt, decryptJson, generateSecurePassword };
