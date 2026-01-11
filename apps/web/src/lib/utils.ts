import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(date: Date | string | number): string {
  if (!date) return '';
  const d = new Date(date);
  return new Intl.DateTimeFormat('pt-BR', {
    day: 'numeric',
    month: 'short',
    year: 'numeric'
  }).format(d);
}

export function formatDateTime(date: Date | string | number): string {
  if (!date) return '';
  const d = new Date(date);
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(d);
}

export function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'] as const;
  const idx = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / Math.pow(1024, idx);
  const decimals = idx === 0 ? 0 : value < 10 ? 1 : 0;
  return `${value.toFixed(decimals)} ${units[idx]}`;
}
