import type { ConfigLimits } from '@/stores/config-store';
import { getModelConfig, type ModelId } from '@/config/models';
import { formatFileSize } from '@/lib/utils';

const MB = 1024 * 1024;
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
