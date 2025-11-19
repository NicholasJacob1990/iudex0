/**
 * Utilitários de formatação
 */

/**
 * Formata bytes para formato legível
 */
export function formatBytes(bytes: number, decimals = 2): string {
  if (bytes === 0) return '0 Bytes';

  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];

  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

/**
 * Formata número de tokens
 */
export function formatTokens(tokens: number): string {
  if (tokens < 1000) return `${tokens} tokens`;
  if (tokens < 1000000) return `${(tokens / 1000).toFixed(1)}K tokens`;
  return `${(tokens / 1000000).toFixed(2)}M tokens`;
}

/**
 * Formata custo em reais
 */
export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(value);
}

/**
 * Formata data relativa (ex: "há 2 horas")
 */
export function formatRelativeTime(date: Date): string {
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  const months = Math.floor(days / 30);
  const years = Math.floor(days / 365);

  if (seconds < 60) return 'agora mesmo';
  if (minutes < 60) return `há ${minutes} minuto${minutes > 1 ? 's' : ''}`;
  if (hours < 24) return `há ${hours} hora${hours > 1 ? 's' : ''}`;
  if (days < 30) return `há ${days} dia${days > 1 ? 's' : ''}`;
  if (months < 12) return `há ${months} ${months > 1 ? 'meses' : 'mês'}`;
  return `há ${years} ano${years > 1 ? 's' : ''}`;
}

/**
 * Formata data completa
 */
export function formatDate(date: Date): string {
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

/**
 * Trunca texto com reticências
 */
export function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return `${text.substring(0, maxLength)}...`;
}

/**
 * Remove acentos de uma string
 */
export function removeAccents(text: string): string {
  return text.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

/**
 * Converte para slug
 */
export function slugify(text: string): string {
  return removeAccents(text)
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, '')
    .replace(/[\s_-]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

/**
 * Extrai iniciais do nome
 */
export function getInitials(name: string): string {
  return name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .substring(0, 2);
}

/**
 * Formata número de processo CNJ
 */
export function formatProcessNumber(processNumber: string): string {
  // Remove tudo que não é número
  const numbers = processNumber.replace(/\D/g, '');

  // Formato: NNNNNNN-DD.AAAA.J.TR.OOOO
  if (numbers.length === 20) {
    return `${numbers.substring(0, 7)}-${numbers.substring(7, 9)}.${numbers.substring(9, 13)}.${numbers.substring(13, 14)}.${numbers.substring(14, 16)}.${numbers.substring(16, 20)}`;
  }

  return processNumber;
}

/**
 * Valida e formata OAB
 */
export function formatOAB(oab: string): string {
  const numbers = oab.replace(/\D/g, '');
  const letters = oab.replace(/[^A-Z]/gi, '').toUpperCase();

  if (numbers && letters) {
    return `${numbers}/${letters}`;
  }

  return oab;
}

