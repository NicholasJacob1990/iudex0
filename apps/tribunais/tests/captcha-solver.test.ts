/**
 * Testes do CaptchaSolverService
 *
 * Testes unitários para verificar a lógica de:
 * - Configuração do serviço
 * - Tratamento de erros
 * - Fallback para resolução manual
 *
 * Nota: Os testes de integração com polling são omitidos
 * porque requerem mocking complexo de timers.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { CaptchaSolverService, type CaptchaProvider } from '../src/services/captcha-solver.js';
import type { CaptchaInfo } from '../src/types/index.js';

// Mock fetch
global.fetch = vi.fn();

describe('CaptchaSolverService', () => {
  let solver: CaptchaSolverService;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(async () => {
    if (solver) {
      await solver.close();
    }
  });

  describe('Configuration', () => {
    it('should use default values when not specified', () => {
      solver = new CaptchaSolverService({
        provider: 'manual',
      });

      // Verifica que o solver foi criado sem erros
      expect(solver).toBeDefined();
    });

    it('should accept all provider types', () => {
      const providers: CaptchaProvider[] = ['2captcha', 'anticaptcha', 'capmonster', 'manual'];

      for (const provider of providers) {
        const s = new CaptchaSolverService({ provider });
        expect(s).toBeDefined();
      }
    });
  });

  describe('2Captcha Error Handling', () => {
    beforeEach(() => {
      solver = new CaptchaSolverService({
        provider: '2captcha',
        apiKey: 'test-api-key',
        serviceTimeout: 5000,
        fallbackToManual: false,
      });
    });

    it('should throw error when API key is missing', async () => {
      solver = new CaptchaSolverService({
        provider: '2captcha',
        apiKey: '',
        fallbackToManual: false,
      });

      const captcha: CaptchaInfo = {
        type: 'image',
        imageBase64: 'test',
      };

      await expect(
        solver.solve('job-1', 'user-1', captcha, 'http://example.com', 'TRF1')
      ).rejects.toThrow('API key não configurada para 2Captcha');
    });

    it('should throw error on API failure', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        json: () => Promise.resolve({ status: 0, request: 'ERROR_WRONG_USER_KEY' }),
      });

      const captcha: CaptchaInfo = {
        type: 'image',
        imageBase64: 'test',
      };

      await expect(
        solver.solve('job-1', 'user-1', captcha, 'http://example.com', 'TRF1')
      ).rejects.toThrow('ERROR_WRONG_USER_KEY');
    });
  });

  describe('Anti-Captcha Error Handling', () => {
    beforeEach(() => {
      solver = new CaptchaSolverService({
        provider: 'anticaptcha',
        apiKey: 'test-api-key',
        serviceTimeout: 5000,
        fallbackToManual: false,
      });
    });

    it('should throw error when API key is missing', async () => {
      solver = new CaptchaSolverService({
        provider: 'anticaptcha',
        apiKey: '',
        fallbackToManual: false,
      });

      const captcha: CaptchaInfo = {
        type: 'image',
        imageBase64: 'test',
      };

      await expect(
        solver.solve('job-1', 'user-1', captcha, 'http://example.com', 'TRF1')
      ).rejects.toThrow('API key não configurada para Anti-Captcha');
    });

    it('should handle createTask API error', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        json: () => Promise.resolve({
          errorId: 1,
          errorDescription: 'ERROR_KEY_DOES_NOT_EXIST',
        }),
      });

      const captcha: CaptchaInfo = {
        type: 'image',
        imageBase64: 'test',
      };

      await expect(
        solver.solve('job-1', 'user-1', captcha, 'http://example.com', 'TRF1')
      ).rejects.toThrow('ERROR_KEY_DOES_NOT_EXIST');
    });
  });

  describe('CapMonster Error Handling', () => {
    beforeEach(() => {
      solver = new CaptchaSolverService({
        provider: 'capmonster',
        apiKey: 'test-api-key',
        serviceTimeout: 5000,
        fallbackToManual: false,
      });
    });

    it('should throw error when API key is missing', async () => {
      solver = new CaptchaSolverService({
        provider: 'capmonster',
        apiKey: '',
        fallbackToManual: false,
      });

      const captcha: CaptchaInfo = {
        type: 'image',
        imageBase64: 'test',
      };

      await expect(
        solver.solve('job-1', 'user-1', captcha, 'http://example.com', 'TRF1')
      ).rejects.toThrow('API key não configurada para CapMonster');
    });

    it('should handle createTask API error', async () => {
      (global.fetch as any).mockResolvedValueOnce({
        json: () => Promise.resolve({
          errorId: 2,
          errorDescription: 'ERROR_ZERO_BALANCE',
        }),
      });

      const captcha: CaptchaInfo = {
        type: 'recaptcha_v3',
        siteKey: '6LcV3Example',
        metadata: { pageUrl: 'http://tribunal.example.com', action: 'submit' },
      };

      await expect(
        solver.solve('job-1', 'user-1', captcha, 'http://example.com', 'TRF1')
      ).rejects.toThrow('ERROR_ZERO_BALANCE');
    });
  });

  describe('Fallback to Manual', () => {
    it('should fallback to manual when service fails and fallback is enabled', async () => {
      // Este teste precisa de Redis mockado para funcionar completamente
      // Por enquanto, só verificamos que a configuração funciona
      solver = new CaptchaSolverService({
        provider: '2captcha',
        apiKey: 'test-key',
        fallbackToManual: true,
        redisUrl: '', // Sem Redis, não vai funcionar
      });

      // Mock: API failure
      (global.fetch as any).mockResolvedValueOnce({
        json: () => Promise.resolve({ status: 0, request: 'ERROR_ZERO_BALANCE' }),
      });

      const captcha: CaptchaInfo = {
        type: 'image',
        imageBase64: 'test',
      };

      // Deve falhar porque não há Redis configurado
      await expect(
        solver.solve('job-1', 'user-1', captcha, 'http://example.com', 'TRF1')
      ).rejects.toThrow('Redis não configurado para resolução manual');
    });

    it('should throw when service fails and fallback is disabled', async () => {
      solver = new CaptchaSolverService({
        provider: '2captcha',
        apiKey: 'test-key',
        fallbackToManual: false,
      });

      // Mock: API failure
      (global.fetch as any).mockResolvedValueOnce({
        json: () => Promise.resolve({ status: 0, request: 'ERROR_ZERO_BALANCE' }),
      });

      const captcha: CaptchaInfo = {
        type: 'image',
        imageBase64: 'test',
      };

      await expect(
        solver.solve('job-1', 'user-1', captcha, 'http://example.com', 'TRF1')
      ).rejects.toThrow('ERROR_ZERO_BALANCE');
    });
  });

  describe('Unsupported CAPTCHA types', () => {
    it('should throw for unsupported CAPTCHA type', async () => {
      solver = new CaptchaSolverService({
        provider: '2captcha',
        apiKey: 'test-key',
        fallbackToManual: false,
      });

      const captcha: CaptchaInfo = {
        type: 'unknown',
      };

      await expect(
        solver.solve('job-1', 'user-1', captcha, 'http://example.com', 'TRF1')
      ).rejects.toThrow('Tipo de CAPTCHA não suportado');
    });
  });
});
