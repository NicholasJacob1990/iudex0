'use client';

import { Toaster } from 'sonner';
import { ThemeProvider } from './theme-provider';
import { QueryProvider } from './query-provider';
import { PrefetchProvider } from './prefetch-provider';
import { ServiceWorkerProvider } from './sw-provider';

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      <QueryProvider>
        <PrefetchProvider>
          {children}
        </PrefetchProvider>
        <Toaster position="top-right" richColors />
        <ServiceWorkerProvider />
      </QueryProvider>
    </ThemeProvider>
  );
}

export { ThemeProvider } from './theme-provider';
export { QueryProvider } from './query-provider';
export { PrefetchProvider } from './prefetch-provider';
export { ServiceWorkerProvider } from './sw-provider';

