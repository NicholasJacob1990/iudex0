'use client';

import { LegislationPanel } from '@/components/dashboard';

export default function LegislationPage() {
  return (
    <div className="space-y-8">
      <div className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft">
        <p className="text-xs font-semibold uppercase text-muted-foreground">Legislação</p>
        <h1 className="font-display text-3xl text-foreground">Integre leis oficiais instantaneamente.</h1>
        <p className="text-sm text-muted-foreground">
          Pesquise por número, assunto ou trecho e salve artigos favoritos em bibliotecas.
        </p>
      </div>

      <LegislationPanel />
    </div>
  );
}

