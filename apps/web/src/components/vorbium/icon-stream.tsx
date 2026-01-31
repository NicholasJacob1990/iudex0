'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  FileText,
  Shield,
  Search,
  Sparkles,
  Scale,
  FolderOpen,
  Workflow,
  ListChecks,
  BookOpenCheck,
  Link2,
  ChevronRight,
} from 'lucide-react';

type IconStreamProps = {
  className?: string;
};

export function IconStream({ className = '' }: IconStreamProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(false);

  const icons = useMemo(
    () => [
      { Icon: FileText, label: 'Documentos' },
      { Icon: ListChecks, label: 'Revisao' },
      { Icon: Search, label: 'Pesquisa' },
      { Icon: Shield, label: 'Controle' },
      { Icon: FolderOpen, label: 'Vault' },
      { Icon: Scale, label: 'Juridico' },
      { Icon: Workflow, label: 'Fluxos' },
      { Icon: Link2, label: 'Integracoes' },
      { Icon: BookOpenCheck, label: 'Padroes' },
      { Icon: Sparkles, label: 'Agentes' },
    ],
    []
  );

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const io = new IntersectionObserver(
      (entries) => {
        const e = entries[0];
        if (!e) return;
        if (e.isIntersecting) {
          setActive(true);
          io.disconnect();
        }
      },
      { rootMargin: '-10% 0px -60% 0px', threshold: 0.1 }
    );

    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={[
        'relative -mx-6 md:mx-0 md:rounded-3xl border-y md:border border-white/10 bg-white/[0.02] overflow-hidden',
        className,
      ].join(' ')}
      aria-hidden="true"
    >
      <div className="absolute inset-0 noise-overlay" />
      <div className="absolute inset-0 opacity-50 bg-gradient-to-r from-indigo-500/10 via-transparent to-purple-500/10" />

      <div
        className={[
          'relative flex items-center gap-3 px-6 py-6 md:px-8 md:py-7',
          active ? 'animate-stream-in' : 'opacity-0 translate-x-10',
        ].join(' ')}
      >
        {icons.map(({ Icon }, i) => (
          <div
            key={i}
            className="h-12 w-12 md:h-14 md:w-14 rounded-full border border-white/10 bg-white/5 backdrop-blur flex items-center justify-center"
            style={{
              animation: `float 5.5s ease-in-out ${-i * 0.6}s infinite`,
            }}
          >
            <Icon className="h-5 w-5 md:h-6 md:w-6 text-white/75" />
          </div>
        ))}

        <div className="ml-auto hidden md:flex items-center gap-2 text-xs uppercase tracking-[0.25em] text-white/40">
          <span className="whitespace-nowrap">Fluxo continuo</span>
          <ChevronRight className="h-4 w-4" />
        </div>
      </div>
    </div>
  );
}

