'use client';

import { WebSearchPanel } from '@/components/dashboard';

export default function WebPage() {
  return (
    <div className="space-y-8">
      <div className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft">
        <p className="text-xs font-semibold uppercase text-muted-foreground">Pesquisa Web</p>
        <h1 className="font-display text-3xl text-foreground">Atualize minutas com dados recentes.</h1>
        <p className="text-sm text-muted-foreground">
          O Iudex consulta fontes confiáveis automaticamente antes de gerar uma minuta.
        </p>
      </div>

      <WebSearchPanel />
    </div>
  );
}

