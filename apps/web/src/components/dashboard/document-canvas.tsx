'use client';

import { cn } from '@/lib/utils';

interface DocumentCanvasProps {
  content: string;
}

export function DocumentCanvas({ content }: DocumentCanvasProps) {
  const hasContent = content.trim().length > 0;

  return (
    <div className="relative h-full overflow-auto rounded-[32px] border border-outline/50 bg-sand/70 p-8 shadow-soft">
      <div className="absolute inset-0 -z-10 rounded-[32px] bg-dotted-grid opacity-60" />
      <div className="mx-auto flex min-h-full max-w-[980px] flex-col items-center gap-6 pb-16">
        <article
          className={cn(
            'w-full min-h-[1200px] rounded-[28px] border border-white/80 bg-white px-12 py-14 shadow-soft',
            'prose prose-slate max-w-none text-base leading-relaxed'
          )}
        >
          {hasContent ? (
            <div dangerouslySetInnerHTML={{ __html: content }} />
          ) : (
            <div className="flex h-full flex-col items-center justify-center text-center text-muted-foreground">
              <p className="text-lg font-semibold">Nenhuma minuta gerada ainda.</p>
              <p className="text-sm">
                Conduza o chat à direita para produzir um documento ilimitado. Quando finalizado, ele
                aparecerá aqui sem restrição de páginas ou tokens.
              </p>
            </div>
          )}
        </article>
      </div>
    </div>
  );
}

