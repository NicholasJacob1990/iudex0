'use client';

import { Button } from '@/components/ui/button';
import { Plus, Share2 } from 'lucide-react';
import { LibraryTable } from '@/components/dashboard';

export default function LibraryPage() {
  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase text-muted-foreground">Biblioteca</p>
          <h1 className="font-display text-3xl text-foreground">Todos os ativos jurídicos num só lugar.</h1>
          <p className="text-sm text-muted-foreground">
            Pastas inteligentes, bibliotecários temáticos e compartilhamentos com granularidade.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" className="rounded-full">
            <Plus className="mr-2 h-4 w-4" />
            Nova pasta
          </Button>
          <Button className="rounded-full bg-primary text-primary-foreground">
            <Share2 className="mr-2 h-4 w-4" />
            Compartilhar
          </Button>
        </div>
      </div>

      <LibraryTable />
    </div>
  );
}

