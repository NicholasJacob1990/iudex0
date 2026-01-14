'use client';

import { cn } from '@/lib/utils';
import { DocumentEditor } from '@/components/editor/document-editor';
import { parseMarkdownToHtmlSync } from '@/lib/markdown-parser';
import { useMemo } from 'react';

interface DocumentCanvasProps {
  content: string;
}

export function DocumentCanvas({ content }: DocumentCanvasProps) {
  const hasContent = content.trim().length > 0;

  // Parse markdown to HTML for TipTap
  const htmlContent = useMemo(() => {
    if (!hasContent) return '';
    try {
      return parseMarkdownToHtmlSync(content);
    } catch (e) {
      console.error("Error parsing markdown for canvas:", e);
      return content; // Fallback
    }
  }, [content, hasContent]);

  return (
    <div className="relative h-full overflow-hidden rounded-[32px] border border-outline/50 bg-sand/70 shadow-soft">
      <div className="absolute inset-0 -z-10 rounded-[32px] bg-dotted-grid opacity-60" />
      <div className="h-full w-full overflow-auto p-8">
        <div className="mx-auto flex min-h-full max-w-[980px] flex-col items-center gap-6 pb-16">
          {hasContent ? (
            <DocumentEditor content={htmlContent} editable={true} />
          ) : (
            <div className="flex h-full flex-col items-center justify-center text-center text-muted-foreground mt-32">
              <p className="text-lg font-semibold">Nenhuma minuta gerada ainda.</p>
              <p className="text-sm max-w-md">
                Conduza o chat à direita para produzir um documento ilimitado. Quando finalizado, ele
                aparecerá aqui pronto para edição.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
