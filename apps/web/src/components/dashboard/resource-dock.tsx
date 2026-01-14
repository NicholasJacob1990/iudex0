'use client';

import { cn } from '@/lib/utils';
import { useState } from 'react';
import { Mic, Share2, Scale, Bot, Users } from 'lucide-react';

const dockIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  Podcasts: Mic,
  Diagramas: Share2,
  Compartilhamentos: Users,
  'Metadados CNJ': Scale,
  'Comunicações DJEN': Bot,
};

const resourceShortcuts = [
  { id: 'podcasts', label: 'Podcasts', description: 'Resumo em áudio de decisões', icon: 'Mic' },
  { id: 'diagrams', label: 'Diagramas', description: 'Mapas mentais automáticos', icon: 'Share2' },
  { id: 'sharing', label: 'Compartilhamentos', description: 'Pastas e grupos', icon: 'Users' },
  { id: 'cnj', label: 'Metadados CNJ', description: 'Processos oficiais', icon: 'Scale' },
  { id: 'djen', label: 'Comunicações DJEN', description: 'Diário de Justiça', icon: 'Newspaper' },
];

export function ResourceDock() {
  const [enabled, setEnabled] = useState({
    podcasts: true,
    diagrams: true,
    sharing: true,
    cnj: true,
    djen: false,
  });

  return (
    <aside className="hidden w-80 border-l border-outline/60 bg-panel/70 px-5 py-6 backdrop-blur-2xl xl:block">
      <div className="space-y-5">
        {resourceShortcuts.map((shortcut) => {
          const Icon = dockIcons[shortcut.label] ?? Share2;
          const toggleKey = shortcut.id as keyof typeof enabled;
          return (
            <div
              key={shortcut.id}
              className="rounded-3xl border border-white/60 bg-white/80 p-4 shadow-soft"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span
                    className={cn(
                      'flex h-10 w-10 items-center justify-center rounded-2xl',
                      'bg-gradient-to-br from-primary/10 to-rose-100 text-primary'
                    )}
                  >
                    <Icon className="h-4 w-4" />
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-foreground">{shortcut.label}</p>
                    <p className="text-xs text-muted-foreground">{shortcut.description}</p>
                  </div>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={enabled[toggleKey]}
                  onClick={() => setEnabled((prev) => ({ ...prev, [toggleKey]: !prev[toggleKey] }))}
                  className={cn(
                    enabled[toggleKey] ? 'bg-primary' : 'bg-outline',
                    'relative inline-flex h-6 w-11 items-center rounded-full transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary'
                  )}
                >
                  <span
                    className={cn(
                      enabled[toggleKey] ? 'translate-x-6' : 'translate-x-1',
                      'inline-block h-4 w-4 transform rounded-full bg-white transition'
                    )}
                  />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
}
