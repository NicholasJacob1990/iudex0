'use client';

import * as React from 'react';
import { Sparkles, Edit3, MessageSquare } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

export type QueryMode = 'auto' | 'edit' | 'answer';

export interface AskModeToggleProps {
  mode: QueryMode;
  onChange: (mode: QueryMode) => void;
}

interface ModeOption {
  value: QueryMode;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  tooltip: string;
}

const modeOptions: ModeOption[] = [
  {
    value: 'auto',
    label: 'Automático',
    icon: Sparkles,
    tooltip: 'Claude decide automaticamente se deve editar ou responder',
  },
  {
    value: 'edit',
    label: 'Editar',
    icon: Edit3,
    tooltip: 'Edita diretamente o documento no canvas',
  },
  {
    value: 'answer',
    label: 'Responder',
    icon: MessageSquare,
    tooltip: 'Responde com análise sem editar',
  },
];

export function AskModeToggle({ mode, onChange }: AskModeToggleProps) {
  return (
    <TooltipProvider delayDuration={300}>
      <div
        className="inline-flex h-10 items-center justify-center rounded-md bg-muted p-1 text-muted-foreground"
        role="tablist"
        aria-label="Modo de consulta"
      >
        {modeOptions.map((option) => {
          const Icon = option.icon;
          const isActive = mode === option.value;

          return (
            <Tooltip key={option.value}>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  aria-label={option.label}
                  onClick={() => onChange(option.value)}
                  className={cn(
                    "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
                    isActive
                      ? "bg-background text-foreground shadow-sm"
                      : "hover:bg-background/50 hover:text-foreground"
                  )}
                >
                  <Icon className="h-4 w-4" />
                  <span className="hidden sm:inline">{option.label}</span>
                </button>
              </TooltipTrigger>
              <TooltipContent>
                <p className="max-w-[200px]">{option.tooltip}</p>
              </TooltipContent>
            </Tooltip>
          );
        })}
      </div>
    </TooltipProvider>
  );
}
