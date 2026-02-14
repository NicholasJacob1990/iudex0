'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Document as PdfDocument, Page, pdfjs } from 'react-pdf';
import { AlertCircle, Download, ExternalLink, Loader2, RefreshCw, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import apiClient from '@/lib/api-client';

pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

type ViewerKind = 'pdf_native' | 'office_html' | 'external' | 'unavailable';
type PreviewStatus = 'ready' | 'processing' | 'failed' | 'not_supported';

interface ViewerManifest {
  document_id: string;
  viewer_kind: ViewerKind;
  viewer_url: string | null;
  download_url: string | null;
  source_url: string | null;
  page_count: number | null;
  supports_highlight: boolean;
  supports_page_jump: boolean;
  preview_status: PreviewStatus;
  metadata: Record<string, any> | null;
}

interface CorpusSourceViewerProps {
  documentId: string;
  initialPage?: number;
  highlightText?: string;
  chunk?: string;
  openExternally?: boolean;
}

const escapeRegExp = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const normalizedPage = (value: number | undefined): number => {
  if (!value || !Number.isFinite(value) || value < 1) return 1;
  return Math.floor(value);
};

export function CorpusSourceViewer({
  documentId,
  initialPage,
  highlightText,
  chunk,
  openExternally = false,
}: CorpusSourceViewerProps) {
  const [manifest, setManifest] = useState<ViewerManifest | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(normalizedPage(initialPage));
  const [numPages, setNumPages] = useState<number | null>(null);
  const [pdfWidth, setPdfWidth] = useState(960);
  const pdfContainerRef = useRef<HTMLDivElement | null>(null);

  const refreshManifest = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await apiClient.getCorpusDocumentViewerManifest(documentId);
      setManifest(response as ViewerManifest);
    } catch {
      setManifest(null);
      setError('Não foi possível carregar o manifesto do documento.');
    } finally {
      setIsLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    void refreshManifest();
  }, [refreshManifest]);

  useEffect(() => {
    setCurrentPage(normalizedPage(initialPage));
  }, [initialPage, documentId]);

  useEffect(() => {
    const root = pdfContainerRef.current;
    if (!root) return;

    const updateWidth = () => {
      const next = Math.max(320, Math.min(1200, Math.floor(root.clientWidth - 24)));
      setPdfWidth(next);
    };

    updateWidth();
    const obs = new ResizeObserver(updateWidth);
    obs.observe(root);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (!manifest || !openExternally) return;
    const target =
      (manifest.viewer_url && String(manifest.viewer_url).trim()) ||
      (manifest.source_url && String(manifest.source_url).trim()) ||
      '';
    if (!target) return;
    window.open(target, '_blank', 'noopener,noreferrer');
  }, [manifest, openExternally]);

  const pageLimit = useMemo(() => {
    if (numPages && numPages > 0) return numPages;
    if (manifest?.page_count && manifest.page_count > 0) return manifest.page_count;
    return null;
  }, [manifest?.page_count, numPages]);

  const clampedPage = useMemo(() => {
    if (!pageLimit) return Math.max(1, currentPage);
    return Math.max(1, Math.min(currentPage, pageLimit));
  }, [currentPage, pageLimit]);

  useEffect(() => {
    if (clampedPage !== currentPage) setCurrentPage(clampedPage);
  }, [clampedPage, currentPage]);

  const normalizedHighlight = useMemo(() => String(highlightText || '').trim(), [highlightText]);
  const highlightRenderer = useMemo(() => {
    if (!normalizedHighlight) return undefined;
    const regex = new RegExp(`(${escapeRegExp(normalizedHighlight)})`, 'gi');
    return ({ str }: { str: string }) =>
      String(str || '').replace(regex, '<mark style="background:#fde68a;padding:0 1px;border-radius:2px;">$1</mark>');
  }, [normalizedHighlight]);

  const sourceUrl = manifest?.source_url || null;
  const downloadUrl =
    manifest?.download_url || (manifest ? apiClient.getCorpusDocumentContentUrl(documentId, { download: true }) : null);
  const pdfUrl = apiClient.getCorpusDocumentContentUrl(documentId);
  const officePreviewUrl = apiClient.getCorpusDocumentPreviewUrl(documentId, {
    page: clampedPage,
    q: normalizedHighlight || undefined,
    chunk: chunk || undefined,
  });

  if (isLoading) {
    return (
      <div className="flex min-h-[360px] items-center justify-center rounded-2xl border bg-white/80">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Carregando viewer...
        </div>
      </div>
    );
  }

  if (error || !manifest) {
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50/70 p-6">
        <div className="flex items-start gap-2 text-rose-700">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="text-sm font-medium">Viewer indisponível</p>
            <p className="text-xs opacity-90">{error || 'Manifesto de viewer não encontrado.'}</p>
          </div>
        </div>
      </div>
    );
  }

  const statusLabel: Record<PreviewStatus, string> = {
    ready: 'Pronto',
    processing: 'Processando',
    failed: 'Falhou',
    not_supported: 'Não suportado',
  };

  return (
    <div className="space-y-4">
      <style jsx global>{`
        .react-pdf__Page {
          position: relative;
        }
        .react-pdf__Page__canvas {
          margin: 0 auto;
          max-width: 100%;
          height: auto !important;
        }
        .react-pdf__Page__textContent {
          position: absolute;
          inset: 0;
          overflow: hidden;
          line-height: 1;
          opacity: 0.2;
        }
        .react-pdf__Page__textContent span,
        .react-pdf__Page__textContent mark {
          position: absolute;
          white-space: pre;
          transform-origin: 0 0;
        }
        .react-pdf__Page__annotations.annotationLayer {
          position: absolute;
          inset: 0;
        }
      `}</style>
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-white/90 px-3 py-2">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="rounded-full text-[10px]">
            {manifest.viewer_kind}
          </Badge>
          <Badge variant="secondary" className="rounded-full text-[10px]">
            {statusLabel[manifest.preview_status]}
          </Badge>
          {pageLimit ? (
            <span className="text-xs text-muted-foreground">{pageLimit} página(s)</span>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="h-8 rounded-full gap-1 text-xs" onClick={() => void refreshManifest()}>
            <RefreshCw className="h-3 w-3" />
            Atualizar
          </Button>
          {sourceUrl ? (
            <Button
              variant="outline"
              size="sm"
              className="h-8 rounded-full gap-1 text-xs"
              onClick={() => window.open(sourceUrl, '_blank', 'noopener,noreferrer')}
            >
              <ExternalLink className="h-3 w-3" />
              Origem
            </Button>
          ) : null}
          {downloadUrl ? (
            <Button
              variant="outline"
              size="sm"
              className="h-8 rounded-full gap-1 text-xs"
              onClick={() => window.open(downloadUrl, '_blank', 'noopener,noreferrer')}
            >
              <Download className="h-3 w-3" />
              Download
            </Button>
          ) : null}
        </div>
      </div>

      {manifest.viewer_kind === 'pdf_native' ? (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 rounded-xl border bg-white/90 px-3 py-2">
            <Button
              variant="outline"
              size="sm"
              className="h-8 rounded-full text-xs"
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={clampedPage <= 1}
            >
              Anterior
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-8 rounded-full text-xs"
              onClick={() => setCurrentPage((p) => Math.min(pageLimit || p + 1, p + 1))}
              disabled={!!pageLimit && clampedPage >= pageLimit}
            >
              Próxima
            </Button>
            <span className="text-xs text-muted-foreground">
              Página {clampedPage}{pageLimit ? ` de ${pageLimit}` : ''}
            </span>
            {normalizedHighlight ? (
              <span className="inline-flex items-center gap-1 rounded-full border bg-amber-50 px-2 py-1 text-[11px] text-amber-700">
                <Search className="h-3 w-3" />
                Highlight ativo
              </span>
            ) : null}
          </div>

          <div ref={pdfContainerRef} className="min-h-[640px] overflow-auto rounded-xl border bg-slate-50 p-3">
            <div className="mx-auto w-fit">
              <PdfDocument
                file={pdfUrl}
                loading={
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Carregando PDF...
                  </div>
                }
                onLoadSuccess={({ numPages: totalPages }) => setNumPages(totalPages)}
                onLoadError={() => setError('Falha ao carregar PDF.')}
              >
                <Page
                  key={`pdf-page-${clampedPage}-${pdfWidth}`}
                  pageNumber={clampedPage}
                  width={pdfWidth}
                  renderAnnotationLayer
                  renderTextLayer
                  customTextRenderer={highlightRenderer as any}
                />
              </PdfDocument>
            </div>
          </div>
        </div>
      ) : null}

      {manifest.viewer_kind === 'office_html' ? (
        <div className="rounded-xl border bg-white/95">
          {manifest.preview_status === 'ready' ? (
            <iframe
              title="Office preview"
              src={officePreviewUrl}
              className="h-[72vh] w-full rounded-xl"
            />
          ) : manifest.preview_status === 'processing' ? (
            <div className="flex min-h-[360px] items-center justify-center p-6 text-center">
              <div className="space-y-2">
                <p className="text-sm font-medium">Preview em processamento</p>
                <p className="text-xs text-muted-foreground">
                  O documento foi ingerido, mas a visualização Office ainda está sendo gerada.
                </p>
              </div>
            </div>
          ) : (
            <div className="flex min-h-[360px] items-center justify-center p-6 text-center">
              <div className="space-y-2">
                <p className="text-sm font-medium">Preview indisponível</p>
                <p className="text-xs text-muted-foreground">
                  Use o download para abrir o arquivo no aplicativo nativo.
                </p>
              </div>
            </div>
          )}
        </div>
      ) : null}

      {manifest.viewer_kind === 'external' ? (
        <div className="rounded-xl border bg-white/95 p-6">
          <p className="text-sm font-medium">Fonte externa</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Este documento é referenciado por URL externa.
          </p>
          {manifest.viewer_url ? (
            <Button
              className="mt-3 rounded-full gap-1"
              onClick={() => window.open(manifest.viewer_url || '', '_blank', 'noopener,noreferrer')}
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Abrir fonte
            </Button>
          ) : null}
        </div>
      ) : null}

      {manifest.viewer_kind === 'unavailable' ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-6">
          <p className="text-sm font-medium text-amber-800">Arquivo original não está disponível</p>
          <p className="mt-1 text-xs text-amber-700">
            O documento possui apenas metadados/chunks no corpus para busca.
          </p>
        </div>
      ) : null}
    </div>
  );
}
