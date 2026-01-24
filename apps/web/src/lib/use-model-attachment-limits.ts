'use client';

import { useEffect, useMemo } from 'react';
import { useConfigStore } from '@/stores';
import { buildAttachmentLimits } from '@/lib/attachment-limits';

export function useModelAttachmentLimits(modelIds: string[]) {
  const { limits, loaded, fetchLimits } = useConfigStore();

  useEffect(() => {
    if (!loaded) {
      fetchLimits();
    }
  }, [loaded, fetchLimits]);

  return useMemo(() => buildAttachmentLimits(modelIds, limits), [modelIds, limits]);
}
