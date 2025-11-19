/**
 * Utilitários para manipulação de arquivos
 */

import {
  SUPPORTED_DOCUMENT_FORMATS,
  SUPPORTED_IMAGE_FORMATS,
  SUPPORTED_AUDIO_FORMATS,
  SUPPORTED_VIDEO_FORMATS,
} from '../constants';

/**
 * Extrai a extensão de um arquivo
 */
export function getFileExtension(filename: string): string {
  return filename.slice(((filename.lastIndexOf('.') - 1) >>> 0) + 2).toLowerCase();
}

/**
 * Verifica se é um documento suportado
 */
export function isDocumentFile(filename: string): boolean {
  const ext = getFileExtension(filename);
  return SUPPORTED_DOCUMENT_FORMATS.includes(ext);
}

/**
 * Verifica se é uma imagem suportada
 */
export function isImageFile(filename: string): boolean {
  const ext = getFileExtension(filename);
  return SUPPORTED_IMAGE_FORMATS.includes(ext);
}

/**
 * Verifica se é um áudio suportado
 */
export function isAudioFile(filename: string): boolean {
  const ext = getFileExtension(filename);
  return SUPPORTED_AUDIO_FORMATS.includes(ext);
}

/**
 * Verifica se é um vídeo suportado
 */
export function isVideoFile(filename: string): boolean {
  const ext = getFileExtension(filename);
  return SUPPORTED_VIDEO_FORMATS.includes(ext);
}

/**
 * Obtém o MIME type a partir da extensão
 */
export function getMimeType(filename: string): string {
  const ext = getFileExtension(filename);

  const mimeTypes: Record<string, string> = {
    pdf: 'application/pdf',
    docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    doc: 'application/msword',
    odt: 'application/vnd.oasis.opendocument.text',
    txt: 'text/plain',
    rtf: 'application/rtf',
    html: 'text/html',
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    png: 'image/png',
    gif: 'image/gif',
    webp: 'image/webp',
    mp3: 'audio/mpeg',
    wav: 'audio/wav',
    ogg: 'audio/ogg',
    mp4: 'video/mp4',
    avi: 'video/x-msvideo',
    zip: 'application/zip',
  };

  return mimeTypes[ext] || 'application/octet-stream';
}

/**
 * Sanitiza nome de arquivo
 */
export function sanitizeFilename(filename: string): string {
  // Remove caracteres especiais e substitui espaços por underscore
  return filename
    .replace(/[^a-zA-Z0-9.-_]/g, '_')
    .replace(/\s+/g, '_')
    .replace(/_+/g, '_')
    .toLowerCase();
}

/**
 * Gera nome único para arquivo
 */
export function generateUniqueFilename(originalName: string): string {
  const ext = getFileExtension(originalName);
  const nameWithoutExt = originalName.substring(0, originalName.lastIndexOf('.'));
  const sanitized = sanitizeFilename(nameWithoutExt);
  const timestamp = Date.now();
  const random = Math.random().toString(36).substring(2, 8);

  return `${sanitized}_${timestamp}_${random}.${ext}`;
}

