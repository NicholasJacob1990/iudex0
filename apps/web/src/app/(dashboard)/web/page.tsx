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

        <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm">
          <div className="flex items-start gap-3">
            <span className="text-slate-600 text-lg">ℹ️</span>
            <div>
              <p className="font-semibold text-slate-900">Pesquisa Ativa</p>
              <p className="text-slate-700 mt-1">
                Resultados obtidos via motores de busca com cache inteligente. Valide sempre as fontes antes de citar.
              </p>
            </div>
          </div>
        </div>
      </div>

      <WebSearchPanel />
    </div>
  );
}
