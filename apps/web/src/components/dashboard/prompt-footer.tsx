'use client';

import { useMemo, useState } from 'react';
import { Sparkles, Send, Mic, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useChatStore, useContextStore } from '@/stores';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

export function PromptFooter() {
  const { currentChat, sendMessage, isSending } = useChatStore();
  const { sources } = useContextStore();
  const [prompt, setPrompt] = useState('');
  const [effort, setEffort] = useState(5);
  const [mode, setMode] = useState<'curto' | 'longo'>('curto');

  const tokenPreview = useMemo(() => {
    const tokens = prompt.split(/\s+/).filter(Boolean).length * 1.3;
    return Math.min(50000, Math.round(tokens));
  }, [prompt]);

  const handleSubmit = async () => {
    if (!prompt.trim()) {
      toast.info('Digite instruções para gerar a minuta.');
      return;
    }

    if (!currentChat) {
      toast.info('Abra uma conversa para enviar instruções.');
      return;
    }

    try {
      await sendMessage(prompt);
      setPrompt('');
    } catch (error) {
      // erros tratados no interceptor
    }
  };

  return (
    <footer className="sticky bottom-0 z-30 w-full border-t border-outline/60 bg-panel/90 px-6 py-4 backdrop-blur-2xl">
      <div className="rounded-3xl border border-white/80 bg-white/90 p-4 shadow-soft">
        <div className="flex flex-col gap-3 md:flex-row md:items-center">
          <div className="flex-1 rounded-2xl border border-outline/40 bg-white/80 shadow-inner">
            <textarea
              rows={2}
              className="w-full resize-none rounded-2xl bg-transparent px-4 py-3 text-sm focus-visible:outline-none"
              placeholder="Instruções ao Iudex para geração da minuta..."
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
            />
          </div>

        <div className="flex items-center gap-2">
            <Button variant="outline" size="icon" className="rounded-2xl border-white/70 bg-white">
              <Mic className="h-4 w-4" />
            </Button>
            <Button
              className="rounded-2xl bg-gradient-to-r from-primary to-rose-400 px-6 font-semibold text-primary-foreground shadow-soft"
              onClick={handleSubmit}
              disabled={isSending}
            >
              {isSending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Gerando
                </>
              ) : (
                <>
                  <Sparkles className="mr-2 h-4 w-4" />
                  Gerar minuta
                </>
              )}
            </Button>
            <Button variant="ghost" size="icon" onClick={handleSubmit} disabled={isSending}>
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3 text-xs font-medium text-muted-foreground">
          <div className="flex items-center gap-2">
            <span className="chip bg-sand text-foreground">
              Tokens <strong className="ml-1 text-primary">{tokenPreview}/50000</strong>
            </span>
            <span className="chip bg-lavender/60 text-foreground">
              Esforço{' '}
              <input
                type="range"
                min={1}
                max={5}
                value={effort}
                onChange={(e) => setEffort(Number(e.target.value))}
                className="ml-2 h-1 w-20 cursor-pointer accent-primary"
              />
              <span className="ml-1 text-primary">{effort}</span>
            </span>
          </div>

          <ModeToggle label="Saída" options={['curto', 'longo']} value={mode} onChange={setMode} />
          <ModeToggle label="Perfil" options={['Sem perfil', 'Individual', 'Institucional']} />
          <ModeToggle label="Modo" options={['Chat', 'Minuta']} />
          <ContextSummary />
        </div>
      </div>
    </footer>
  );
}

interface ModeToggleProps {
  label: string;
  options: string[];
  value?: string;
  onChange?: (value: any) => void;
}

function ModeToggle({ label, options, value, onChange }: ModeToggleProps) {
  const [internalValue, setInternalValue] = useState(options[0]);
  const currentValue = value ?? internalValue;

  return (
    <div className="flex items-center gap-2">
      <span className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</span>
      <div className="flex gap-1 rounded-full border border-outline/50 bg-white/80 p-1">
        {options.map((option) => {
          const active = option === currentValue;
          return (
            <button
              key={option}
              type="button"
              className={cn(
                'rounded-full px-3 py-1 text-[11px] font-semibold capitalize transition',
                active ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'
              )}
              onClick={() => {
                if (onChange) {
                  onChange(option as any);
                } else {
                  setInternalValue(option);
                }
              }}
            >
              {option}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ContextSummary() {
  const { sources } = useContextStore();
  const active = sources.filter((source) => source.enabled);

  return (
    <span className="chip bg-white text-foreground">
      Contexto:{' '}
      {active.length > 0 ? active.map((source) => source.label).join(', ') : 'sem contexto'}
    </span>
  );
}

