'use client';

/**
 * Utilitarios de prefetch para React Query.
 *
 * Permite pre-carregar dados ao passar o mouse sobre links de navegacao,
 * reduzindo o tempo percebido de carregamento ao trocar de pagina.
 */

import { useCallback, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import apiClient from '@/lib/api-client';
import { corpusKeys } from '@/app/(dashboard)/corpus/hooks/use-corpus';

// =============================================================================
// QUERY KEYS CENTRALIZADOS (para rotas sem hooks dedicados)
// =============================================================================

export const workflowKeys = {
  all: ['workflows'] as const,
  list: () => [...workflowKeys.all, 'list'] as const,
  detail: (id: string) => [...workflowKeys.all, 'detail', id] as const,
};

export const libraryKeys = {
  all: ['library'] as const,
  items: () => [...libraryKeys.all, 'items'] as const,
};

export const skillsKeys = {
  all: ['skills'] as const,
  list: () => [...skillsKeys.all, 'list'] as const,
};

export const playbookKeys = {
  all: ['playbooks'] as const,
  list: (filters?: Record<string, unknown>) => ['playbooks', filters] as const,
  detail: (id: string) => ['playbook', id] as const,
  rules: (id: string) => ['playbook-rules', id] as const,
};

// =============================================================================
// PREFETCH FUNCTIONS (cada uma encapsula a chamada API correspondente)
// =============================================================================

export const prefetchFns = {
  corpusStats: (qc: ReturnType<typeof useQueryClient>) =>
    qc.prefetchQuery({
      queryKey: corpusKeys.stats(),
      queryFn: () => apiClient.getCorpusStats(),
      staleTime: 1000 * 60 * 2,
    }),

  corpusCollections: (qc: ReturnType<typeof useQueryClient>) =>
    qc.prefetchQuery({
      queryKey: corpusKeys.collections(),
      queryFn: () => apiClient.getCorpusCollections(),
      staleTime: 1000 * 60 * 5,
    }),

  playbooksList: (qc: ReturnType<typeof useQueryClient>) =>
    qc.prefetchQuery({
      queryKey: ['playbooks', undefined],
      queryFn: async () => {
        const response = await apiClient.request('/playbooks');
        return response.items ?? response;
      },
      staleTime: 1000 * 60 * 1,
    }),

  playbookDetail: (qc: ReturnType<typeof useQueryClient>, id: string) =>
    qc.prefetchQuery({
      queryKey: playbookKeys.detail(id),
      queryFn: () => apiClient.request(`/playbooks/${id}`),
      staleTime: 1000 * 60 * 1,
    }),

  workflowsList: (qc: ReturnType<typeof useQueryClient>) =>
    qc.prefetchQuery({
      queryKey: workflowKeys.list(),
      queryFn: () => apiClient.listWorkflows(),
      staleTime: 1000 * 60 * 1,
    }),

  workflowDetail: (qc: ReturnType<typeof useQueryClient>, id: string) =>
    qc.prefetchQuery({
      queryKey: workflowKeys.detail(id),
      queryFn: () => apiClient.getWorkflow(id),
      staleTime: 1000 * 60 * 1,
    }),

  libraryItems: (qc: ReturnType<typeof useQueryClient>) =>
    qc.prefetchQuery({
      queryKey: libraryKeys.items(),
      queryFn: () => apiClient.getLibraryItems(),
      staleTime: 1000 * 60 * 2,
    }),

  skillsList: (qc: ReturnType<typeof useQueryClient>) =>
    qc.prefetchQuery({
      queryKey: skillsKeys.list(),
      queryFn: () => apiClient.listSkillsFromLibrary(),
      staleTime: 1000 * 60 * 2,
    }),
};

// =============================================================================
// HOOK: usePrefetchOnHover
// =============================================================================

/**
 * Hook que retorna handlers onMouseEnter/onFocus para prefetch com debounce.
 *
 * @param prefetchFn - Funcao que executa o prefetch (recebe queryClient).
 *                     Deve ser estavel (useCallback ou referencia externa).
 * @param debounceMs - Tempo de debounce em ms (padrao: 200).
 *
 * Uso:
 * ```tsx
 * const handlers = usePrefetchOnHover((qc) => prefetchFns.corpusStats(qc));
 * <Link href="/corpus" {...handlers}>Corpus</Link>
 * ```
 */
export function usePrefetchOnHover(
  prefetchFn: (qc: ReturnType<typeof useQueryClient>) => void,
  debounceMs = 200
) {
  const queryClient = useQueryClient();
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const trigger = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      try {
        prefetchFn(queryClient);
      } catch {
        // Prefetch falhou silenciosamente — nao bloquear UX
      }
    }, debounceMs);
  }, [prefetchFn, queryClient, debounceMs]);

  const cancel = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  return {
    onMouseEnter: trigger,
    onFocus: trigger,
    onMouseLeave: cancel,
    onBlur: cancel,
  };
}

// =============================================================================
// HOOK: usePrefetchRoute
// =============================================================================

/**
 * Dado um pathname, executa os prefetches correspondentes.
 * Util para pre-carregar dados ao detectar navegacao iminente.
 */
export function prefetchForRoute(
  qc: ReturnType<typeof useQueryClient>,
  pathname: string
) {
  try {
    if (pathname.startsWith('/corpus')) {
      prefetchFns.corpusStats(qc);
      prefetchFns.corpusCollections(qc);
    } else if (pathname.startsWith('/playbooks')) {
      prefetchFns.playbooksList(qc);
    } else if (pathname.startsWith('/workflows')) {
      prefetchFns.workflowsList(qc);
    } else if (pathname.startsWith('/library')) {
      prefetchFns.libraryItems(qc);
    } else if (pathname.startsWith('/skills')) {
      prefetchFns.skillsList(qc);
    }
  } catch {
    // Falha silenciosa
  }
}
