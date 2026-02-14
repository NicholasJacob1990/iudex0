'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { CorpusSourceViewer } from '../components/corpus-source-viewer';

const parsePositiveInt = (value: string | null): number | undefined => {
  if (!value) return undefined;
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 1) return undefined;
  return Math.floor(parsed);
};

export default function CorpusViewerPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const documentId = useMemo(() => String(searchParams.get('documentId') || '').trim(), [searchParams]);
  const page = useMemo(() => parsePositiveInt(searchParams.get('page')), [searchParams]);
  const q = useMemo(() => String(searchParams.get('q') || '').trim(), [searchParams]);
  const chunk = useMemo(() => String(searchParams.get('chunk') || '').trim(), [searchParams]);
  const external = useMemo(
    () => ['1', 'true', 'yes'].includes(String(searchParams.get('external') || '').toLowerCase()),
    [searchParams]
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border bg-white/95 px-4 py-3 shadow-soft">
        <div>
          <p className="text-xs font-semibold uppercase text-muted-foreground">Corpus Viewer</p>
          <h1 className="text-lg font-semibold text-foreground">Fonte original e evidências</h1>
        </div>
        <Button variant="outline" size="sm" className="rounded-full gap-1" onClick={() => router.back()}>
          <ArrowLeft className="h-3.5 w-3.5" />
          Voltar
        </Button>
      </div>

      {!documentId ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50/70 p-5 text-sm text-rose-700">
          `documentId` é obrigatório para abrir o viewer.
        </div>
      ) : (
        <CorpusSourceViewer
          documentId={documentId}
          initialPage={page}
          highlightText={q || undefined}
          chunk={chunk || undefined}
          openExternally={external}
        />
      )}
    </div>
  );
}

