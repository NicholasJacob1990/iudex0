/**
 * Motor de resiliência: fail-fast, retry com backoff, classificação de erros
 */

import type { ResilienceConfig } from '../types.js';

// ============================================
// Defaults
// ============================================

export const RESILIENCE_DEFAULTS: Required<ResilienceConfig> = {
  failFastTimeout: 3000,
  maxRetries: 2,
  retryBackoff: 500,
  speculative: false,
};

export function resolveResilienceConfig(config?: ResilienceConfig): Required<ResilienceConfig> {
  return { ...RESILIENCE_DEFAULTS, ...config };
}

// ============================================
// Classificação de erros
// ============================================

export type ErrorKind = 'transient' | 'selector_not_found' | 'permanent';

export function classifyError(error: unknown): ErrorKind {
  const msg = error instanceof Error ? error.message : String(error);
  const lower = msg.toLowerCase();

  if (
    lower.includes('timeout') ||
    lower.includes('etimedout') ||
    lower.includes('econnreset') ||
    lower.includes('econnrefused') ||
    lower.includes('epipe') ||
    lower.includes('navigation') ||
    lower.includes('net::err_')
  ) {
    return 'transient';
  }

  if (
    lower.includes('not found') ||
    lower.includes('não encontrado') ||
    lower.includes('waiting for selector') ||
    lower.includes('waiting for locator') ||
    lower.includes('strict mode violation')
  ) {
    return 'selector_not_found';
  }

  return 'permanent';
}

// ============================================
// Fail-Fast
// ============================================

export async function failFast<T>(
  fn: () => Promise<T>,
  timeout: number,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`Fail-fast: timeout de ${timeout}ms excedido`));
    }, timeout);

    fn()
      .then((result) => {
        clearTimeout(timer);
        resolve(result);
      })
      .catch((err) => {
        clearTimeout(timer);
        reject(err);
      });
  });
}

// ============================================
// Retry com Exponential Backoff
// ============================================

export interface RetryOptions {
  maxRetries: number;
  backoff: number;
  retryOn?: ErrorKind[];
}

export async function withRetry<T>(
  fn: () => Promise<T>,
  opts: RetryOptions,
): Promise<T> {
  const retryOn = opts.retryOn ?? ['transient'];
  let lastError: unknown;

  for (let attempt = 0; attempt <= opts.maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      if (attempt === opts.maxRetries) break;

      const kind = classifyError(error);
      if (!retryOn.includes(kind)) break;

      const delay = opts.backoff * Math.pow(2, attempt);
      const jitter = delay * (0.8 + Math.random() * 0.4);
      await new Promise((resolve) => setTimeout(resolve, jitter));
    }
  }

  throw lastError;
}
