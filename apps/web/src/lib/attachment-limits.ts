import type { ConfigLimits } from '@/stores/config-store';
import { getModelConfig, MODEL_REGISTRY, type ModelId } from '@/config/models';
import { formatFileSize } from '@/lib/utils';

const MB = 1024 * 1024;

// Threshold constants for auto mode decision
const AUTO_MODE_MAX_FILES_FOR_INJECTION = 5;
const AUTO_MODE_MIN_CONTEXT_FOR_INJECTION = 200_000; // 200K tokens
const AUTO_MODE_LARGE_CONTEXT_THRESHOLD = 500_000; // 500K tokens
const AUTO_MODE_MAX_FILES_LARGE_CONTEXT = 10;
const DEFAULT_MAX_MB = 4096;
const DEFAULT_INJECTION_MAX_FILES = 20;
const DEFAULT_RAG_MAX_FILES = 200;

export const CHAT_ATTACHMENT_TYPES = [
  'PDF',
  'DOCX',
  'DOC',
  'TXT',
  'MD',
  'RTF',
  'ODT',
  'HTML',
  'ZIP',
  'PNG',
  'JPG',
  'JPEG',
  'GIF',
  'BMP',
  'TIFF',
  'TIF',
];

const normalizeProvider = (provider?: string): string => {
  if (!provider) return '';
  const normalized = provider.trim().toLowerCase();
  if (normalized === 'google' || normalized === 'vertex' || normalized === 'gemini') {
    return 'google';
  }
  if (normalized === 'anthropic' || normalized === 'claude') {
    return 'anthropic';
  }
  if (normalized === 'openai' || normalized === 'gpt') {
    return 'openai';
  }
  return normalized;
};

export const getProviderUploadLimitMb = (provider: string | undefined, limits: ConfigLimits): number => {
  const normalized = normalizeProvider(provider);
  const mapping = limits.provider_upload_limits_mb || {};
  if (normalized && mapping[normalized]) {
    return mapping[normalized];
  }
  if (limits.max_upload_size_mb) {
    return limits.max_upload_size_mb;
  }
  return DEFAULT_MAX_MB;
};

export const getAttachmentFileCountLimits = (limits: ConfigLimits) => {
  return {
    injectionMaxFiles: limits.attachment_injection_max_files ?? DEFAULT_INJECTION_MAX_FILES,
    ragLocalMaxFiles: limits.attachment_rag_local_max_files ?? DEFAULT_RAG_MAX_FILES,
  };
};

export type AttachmentLimitModelInfo = {
  id: string;
  label: string;
  provider: string;
  maxBytes: number;
  maxLabel: string;
};

export type AttachmentLimitSummary = {
  perModel: AttachmentLimitModelInfo[];
  effectiveMaxBytes: number;
  effectiveMaxLabel: string;
  injectionMaxFiles: number;
  ragLocalMaxFiles: number;
  typesLabel: string;
};

export const buildAttachmentLimits = (
  modelIds: string[],
  limits: ConfigLimits
): AttachmentLimitSummary => {
  const { injectionMaxFiles, ragLocalMaxFiles } = getAttachmentFileCountLimits(limits);
  const perModel = modelIds
    .map((id) => {
      const config = getModelConfig(id as ModelId);
      const provider = config?.provider || '';
      const maxMb = getProviderUploadLimitMb(provider, limits);
      const maxBytes = maxMb * MB;
      const label = config?.label || id;
      return {
        id,
        label,
        provider,
        maxBytes,
        maxLabel: formatFileSize(maxBytes),
      };
    })
    .filter((entry) => entry.id);

  const fallbackBytes = (limits.max_upload_size_mb ?? DEFAULT_MAX_MB) * MB;
  const effectiveMaxBytes = perModel.length
    ? Math.min(...perModel.map((entry) => entry.maxBytes))
    : fallbackBytes;

  return {
    perModel,
    effectiveMaxBytes,
    effectiveMaxLabel: formatFileSize(effectiveMaxBytes),
    injectionMaxFiles,
    ragLocalMaxFiles,
    typesLabel: CHAT_ATTACHMENT_TYPES.join(', '),
  };
};

/**
 * Resolves 'auto' attachment mode to either 'prompt_injection' or 'rag_local'
 * based on model context window and number of files.
 *
 * Decision logic:
 * - Large context (≥500K tokens) + few files (≤10): prompt_injection
 * - Medium context (≥200K tokens) + very few files (≤5): prompt_injection
 * - Otherwise: rag_local (safer for precision and cost)
 */
export const resolveAutoAttachmentMode = (
  modelIds: string[],
  fileCount: number
): 'prompt_injection' | 'rag_local' => {
  if (fileCount === 0) {
    return 'prompt_injection'; // No files, doesn't matter
  }

  // Get the smallest context window among selected models
  const contextWindows = modelIds
    .map((id) => {
      const config = MODEL_REGISTRY[id as ModelId];
      return config?.contextWindow ?? 0;
    })
    .filter((ctx) => ctx > 0);

  const minContextWindow = contextWindows.length > 0
    ? Math.min(...contextWindows)
    : AUTO_MODE_MIN_CONTEXT_FOR_INJECTION;

  // Large context models can handle more files via injection
  if (minContextWindow >= AUTO_MODE_LARGE_CONTEXT_THRESHOLD) {
    if (fileCount <= AUTO_MODE_MAX_FILES_LARGE_CONTEXT) {
      return 'prompt_injection';
    }
  }

  // Medium context models: only inject if very few files
  if (minContextWindow >= AUTO_MODE_MIN_CONTEXT_FOR_INJECTION) {
    if (fileCount <= AUTO_MODE_MAX_FILES_FOR_INJECTION) {
      return 'prompt_injection';
    }
  }

  // Default to RAG for safety (better precision, lower cost)
  return 'rag_local';
};
