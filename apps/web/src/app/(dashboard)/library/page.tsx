'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Plus, Share2 } from 'lucide-react';
import { LibraryTable, LibrarySidebar, ShareDialog } from '@/components/dashboard';
import { CrossFileDuplicatesModal } from '@/components/dashboard/cross-file-duplicates-modal';
import { AnimatedContainer } from '@/components/ui/animated-container';

export default function LibraryPage() {
  const [shareDialogOpen, setShareDialogOpen] = useState(false);

  return (
    <div className="space-y-8">
      <AnimatedContainer>
      <div className="flex flex-col gap-4 rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase text-muted-foreground">Biblioteca</p>
          <h1 className="font-display text-3xl text-foreground">Todos os ativos jurídicos num só lugar.</h1>
          <p className="text-sm text-muted-foreground">
            Pastas inteligentes, bibliotecários temáticos e compartilhamentos com granularidade.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <CrossFileDuplicatesModal
            availableFiles={[
              'documento_auditoria_01.md',
              'documento_auditoria_02_copia.md',
              'relatorio_final_v1.md'
            ]}
          />
          <Button variant="outline" className="rounded-full">
            <Plus className="mr-2 h-4 w-4" />
            Nova pasta
          </Button>
          <Button
            className="rounded-full bg-primary text-primary-foreground"
            onClick={() => setShareDialogOpen(true)}
          >
            <Share2 className="mr-2 h-4 w-4" />
            Compartilhar
          </Button>
        </div>
      </div>
      </AnimatedContainer>

      <div className="flex gap-6">
        <div className="hidden lg:block flex-shrink-0">
          <LibrarySidebar />
        </div>
        <div className="flex-1 min-w-0">
          <LibraryTable />
        </div>
      </div>

      <ShareDialog
        open={shareDialogOpen}
        onOpenChange={setShareDialogOpen}
        itemName="Biblioteca"
        itemType="pasta"
      />
    </div>
  );
}

