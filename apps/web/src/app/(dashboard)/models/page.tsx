'use client';

import { Button } from '@/components/ui/button';
import { Plus } from 'lucide-react';
import { ModelsBoard } from '@/components/dashboard';

export default function ModelsPage() {
  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase text-muted-foreground">Modelos</p>
          <h1 className="font-display text-3xl text-foreground">Padronize a escrita jurídica.</h1>
          <p className="text-sm text-muted-foreground">
            Gerencie modelos, siga referências rígidas e reutilize estruturas aprovadas.
          </p>
        </div>
        <Button className="rounded-full bg-primary text-primary-foreground">
          <Plus className="mr-2 h-4 w-4" />
          Novo Modelo
        </Button>
      </div>

      <ModelsBoard />
    </div>
  );
}

