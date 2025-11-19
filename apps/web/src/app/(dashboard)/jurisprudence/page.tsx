'use client';

import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Search, Gavel } from 'lucide-react';

const courts = ['STF', 'STJ', 'TST', 'TSE', 'STM', 'TRFs'];

export default function JurisprudencePage() {
  const [searchTerm, setSearchTerm] = useState('');
  const [activeCourt, setActiveCourt] = useState('STF');

  return (
    <div className="space-y-8">
      <div className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft">
        <p className="text-xs font-semibold uppercase text-muted-foreground">Jurisprudência</p>
        <h1 className="font-display text-3xl text-foreground">
          Busque precedentes com repercussão geral.
        </h1>
        <p className="text-sm text-muted-foreground">
          Pesquise em STF, STJ e tribunais superiores com filtros inteligentes e sumários automáticos.
        </p>
      </div>

      <section className="rounded-3xl border border-white/70 bg-white/90 p-5 shadow-soft">
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-2">
            {courts.map((court) => (
              <Button
                key={court}
                variant={court === activeCourt ? 'default' : 'outline'}
                size="sm"
                className="rounded-full"
                onClick={() => setActiveCourt(court)}
              >
                {court}
              </Button>
            ))}
          </div>

          <div className="relative">
            <Search className="absolute left-4 top-3 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Ex: danos morais por negativação, execução fiscal..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="h-12 rounded-2xl border-transparent bg-sand pl-11"
            />
          </div>

          <div className="flex flex-col items-center justify-center rounded-3xl border border-dashed border-outline/60 bg-sand/50 py-12 text-muted-foreground">
            <Gavel className="mb-3 h-10 w-10" />
            <p>Selecione um tribunal e pesquise para visualizar os precedentes.</p>
          </div>
        </div>
      </section>
    </div>
  );
}

