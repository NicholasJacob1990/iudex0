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

        {/* Aviso de Demonstração */}
        <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm">
          <div className="flex items-start gap-3">
            <span className="text-amber-600 text-lg">⚠️</span>
            <div>
              <p className="font-semibold text-amber-900">Modo de Demonstração</p>
              <p className="text-amber-700 mt-1">
                Esta funcionalidade está exibindo resultados de exemplo. A integração com motores de busca reais será implementada em breve.
              </p>
            </div>
          </div>
        </div>
      </div>

      <WebSearchPanel />
    </div>
  );
}

