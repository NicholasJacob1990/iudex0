import { create } from 'zustand';
import apiClient from '@/lib/api-client';

export interface ConfigLimits {
  max_upload_size_mb: number;
  max_upload_size_bytes?: number;
  audio_max_size_mb?: number;
  attachment_injection_max_chars?: number;
  attachment_injection_max_chars_per_doc?: number;
  attachment_injection_max_files?: number;
  attachment_rag_local_max_files?: number;
  attachment_rag_local_top_k?: number;
  rag_context_max_chars?: number;
  rag_context_max_chars_prompt_injection?: number;
  upload_cache_min_bytes?: number;
  upload_cache_min_files?: number;
  provider_upload_limits_mb?: Record<string, number>;
}

const DEFAULT_LIMITS: ConfigLimits = {
  max_upload_size_mb: 4096,
  max_upload_size_bytes: 4096 * 1024 * 1024,
  provider_upload_limits_mb: {
    openai: 512,
    anthropic: 30,
    google: 2048,
  },
};

interface ConfigState {
  limits: ConfigLimits;
  isLoading: boolean;
  loaded: boolean;
  fetchLimits: () => Promise<void>;
}

export const useConfigStore = create<ConfigState>((set, get) => ({
  limits: DEFAULT_LIMITS,
  isLoading: false,
  loaded: false,

  fetchLimits: async () => {
    if (get().loaded || get().isLoading) return;
    set({ isLoading: true });
    try {
      const limits = await apiClient.getConfigLimits();
      set({
        limits: { ...DEFAULT_LIMITS, ...(limits || {}) },
        loaded: true,
        isLoading: false,
      });
    } catch {
      set({ isLoading: false });
    }
  },
}));
