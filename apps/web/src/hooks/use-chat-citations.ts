'use client';

import { useMemo, useCallback } from 'react';
import { useChatStore } from '@/stores';
import type { AskCitationItem } from '@/components/ask/ask-sources-panel';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';

/**
 * Extracts citations, streaming status, and routed metadata from the current chat.
 */
export function useChatCitations() {
  const currentChat = useChatStore((s) => s.currentChat);
  const isSending = useChatStore((s) => s.isSending);

  const { citations, streamingStatus, stepsCount, routedPages, routedDocumentRoute } = useMemo(() => {
    const msgs = currentChat?.messages || [];

    // Find last assistant message
    let lastMsg = null;
    for (let i = msgs.length - 1; i >= 0; i -= 1) {
      if (msgs[i]?.role === 'assistant') {
        lastMsg = msgs[i];
        break;
      }
    }

    // Extract activity steps
    const steps = lastMsg?.metadata?.activity?.steps || [];

    // Extract citations and normalize with provenance/viewer metadata.
    const rawCitations = Array.isArray(lastMsg?.metadata?.citations) ? lastMsg.metadata.citations : [];
    const formattedCitations: AskCitationItem[] = rawCitations.map((cit: any, idx: number) => {
      const provenance = cit?.provenance && typeof cit.provenance === 'object' ? cit.provenance : {};
      const viewer = cit?.viewer && typeof cit.viewer === 'object' ? cit.viewer : {};
      const pageNumberRaw = viewer?.source_page ?? provenance?.page_number ?? cit?.source_page ?? cit?.page_number;
      const chunkIndexRaw = provenance?.chunk_index ?? cit?.chunk_index;
      const lineStartRaw = provenance?.line_start ?? cit?.line_start;
      const lineEndRaw = provenance?.line_end ?? cit?.line_end;

      const pageNumber = Number.isFinite(Number(pageNumberRaw)) ? Number(pageNumberRaw) : undefined;
      const chunkIndex = Number.isFinite(Number(chunkIndexRaw)) ? Number(chunkIndexRaw) : undefined;
      const lineStart = Number.isFinite(Number(lineStartRaw)) ? Number(lineStartRaw) : undefined;
      const lineEnd = Number.isFinite(Number(lineEndRaw)) ? Number(lineEndRaw) : undefined;

      const viewerSourceUrl =
        typeof viewer?.source_url === 'string' ? viewer.source_url : undefined;
      const rawUrl = typeof cit?.url === 'string' ? cit.url : undefined;
      const fallbackUrl = viewerSourceUrl || rawUrl;

      let source = 'Fonte';
      try {
        if (fallbackUrl) {
          source = new URL(fallbackUrl).hostname;
        }
      } catch {
        source =
          String(provenance?.source_file || '').trim() ||
          String(cit?.source || '').trim() ||
          'Fonte';
      }

      return {
        id: String(cit?.number || cit?.id || idx + 1),
        title: String(cit?.title || fallbackUrl || `Fonte ${idx + 1}`),
        source,
        snippet:
          (typeof cit?.quote === 'string' && cit.quote) ||
          (typeof viewer?.highlight_text === 'string' && viewer.highlight_text) ||
          (typeof cit?.excerpt === 'string' && cit.excerpt) ||
          undefined,
        signal: cit?.signal || 'neutral',
        url: rawUrl,
        documentId: String(provenance?.doc_id || cit?.document_id || '').trim() || undefined,
        chunkUid: String(provenance?.chunk_uid || cit?.chunk_uid || '').trim() || undefined,
        chunkIndex,
        pageNumber,
        lineStart,
        lineEnd,
        sourceFile: String(provenance?.source_file || cit?.source_file || '').trim() || undefined,
        viewerKind: String(viewer?.viewer_kind || cit?.viewer_kind || '').trim() || undefined,
        viewerUrl: String(viewer?.viewer_url || cit?.viewer_url || '').trim() || undefined,
        downloadUrl: String(viewer?.download_url || cit?.download_url || '').trim() || undefined,
        sourceUrl: viewerSourceUrl || (typeof cit?.source_url === 'string' ? cit.source_url : undefined),
        highlightText:
          (typeof viewer?.highlight_text === 'string' && viewer.highlight_text) ||
          (typeof cit?.highlight_text === 'string' && cit.highlight_text) ||
          undefined,
      };
    });

    // Determine streaming status from steps
    const runningStep = steps.find((s: any) => s?.status === 'running');
    const completedSteps = steps.filter((s: any) => s?.status === 'done').length;

    let status = '';
    if (runningStep) {
      status = runningStep.title || 'Processando...';
    } else if (completedSteps > 0 && !isSending) {
      status = `Concluido em ${completedSteps} etapa${completedSteps > 1 ? 's' : ''}`;
    }

    const route = String(lastMsg?.metadata?.document_route || '').trim() || undefined;
    const rawPages = Number(lastMsg?.metadata?.estimated_pages);
    const pages = Number.isFinite(rawPages) && rawPages > 0 ? Math.floor(rawPages) : undefined;

    return {
      citations: formattedCitations,
      streamingStatus: status,
      stepsCount: steps.length,
      routedPages: pages,
      routedDocumentRoute: route,
    };
  }, [currentChat?.messages, isSending]);

  const handleOpenCitationEvidence = useCallback(
    (citation: AskCitationItem) => {
      const documentId = String(citation.documentId || '').trim();
      if (documentId) {
        const route = apiClient.getCorpusViewerRouteUrl(documentId, {
          page: citation.pageNumber,
          q: citation.highlightText || citation.snippet,
          chunk: citation.chunkUid,
        });
        window.open(route, '_blank', 'noopener,noreferrer');
        return;
      }

      const fallbackUrl =
        String(citation.viewerUrl || '').trim() ||
        String(citation.sourceUrl || '').trim() ||
        String(citation.url || '').trim();

      if (fallbackUrl) {
        window.open(fallbackUrl, '_blank', 'noopener,noreferrer');
        return;
      }

      toast.error('Não há origem disponível para esta citação.');
    },
    []
  );

  return {
    citations,
    streamingStatus,
    stepsCount,
    routedPages,
    routedDocumentRoute,
    handleOpenCitationEvidence,
  };
}
