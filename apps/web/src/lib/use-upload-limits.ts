'use client';

import { useEffect, useMemo } from 'react';
import { useConfigStore } from '@/stores';
import { formatFileSize } from '@/lib/utils';

const FALLBACK_BYTES = 4096 * 1024 * 1024;

export function useUploadLimits() {
  const { limits, loaded, fetchLimits } = useConfigStore();

  useEffect(() => {
    if (!loaded) {
      fetchLimits();
    }
  }, [loaded, fetchLimits]);

  const maxUploadBytes = useMemo(() => {
    if (limits.max_upload_size_bytes && limits.max_upload_size_bytes > 0) {
      return limits.max_upload_size_bytes;
    }
    if (limits.max_upload_size_mb && limits.max_upload_size_mb > 0) {
      return limits.max_upload_size_mb * 1024 * 1024;
    }
    return FALLBACK_BYTES;
  }, [limits.max_upload_size_bytes, limits.max_upload_size_mb]);

  const maxUploadLabel = useMemo(() => formatFileSize(maxUploadBytes), [maxUploadBytes]);
  const maxUploadMb = useMemo(() => Math.round(maxUploadBytes / (1024 * 1024)), [maxUploadBytes]);

  return {
    maxUploadBytes,
    maxUploadLabel,
    maxUploadMb,
  };
}
