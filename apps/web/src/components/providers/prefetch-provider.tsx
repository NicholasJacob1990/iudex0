'use client';

/**
 * PrefetchProvider
 *
 * Escuta mudancas de rota no Next.js App Router e dispara prefetches
 * de dados para a rota de destino, reduzindo latencia percebida.
 */

import { useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { prefetchForRoute } from '@/lib/prefetch';

export function PrefetchProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const prevPathRef = useRef<string | null>(null);

  useEffect(() => {
    // Evita prefetch na mesma rota
    if (pathname === prevPathRef.current) return;
    prevPathRef.current = pathname;

    // Executa prefetch dos dados da rota atual (dados adjacentes)
    prefetchForRoute(queryClient, pathname);
  }, [pathname, queryClient]);

  return <>{children}</>;
}
