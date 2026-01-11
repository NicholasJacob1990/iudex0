'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
import { TRANSCRIPTION_PRESETS } from '@/data/prompts';
import type { CustomPrompt } from '@/components/dashboard/prompt-customization';

interface TranscriptionPromptPickerProps {
  className?: string;
  onReplace: (template: string) => void;
  onAppend?: (template: string) => void;
}

export function TranscriptionPromptPicker({ className, onReplace, onAppend }: TranscriptionPromptPickerProps) {
  const [customPrompts, setCustomPrompts] = useState<CustomPrompt[]>([]);
  const [selectedId, setSelectedId] = useState<string>('');

  useEffect(() => {
    const stored = localStorage.getItem('iudex_custom_prompts');
    if (!stored) {
      setCustomPrompts([]);
      return;
    }
    try {
      const parsed = JSON.parse(stored);
      setCustomPrompts(Array.isArray(parsed) ? parsed : []);
    } catch {
      setCustomPrompts([]);
    }
  }, []);

  const selected = useMemo(() => {
    // Check custom prompts first
    const custom = customPrompts.find((p) => p.id === selectedId);
    if (custom) return custom;
    // Check presets
    return TRANSCRIPTION_PRESETS.find((p) => p.id === selectedId) || null;
  }, [customPrompts, selectedId]);

  return (
    <div className={cn('space-y-2', className)}>
      <div className="flex items-center justify-between gap-2">
        <Label>Usar Prompt Salvo</Label>
        <Link href="/prompts" className="text-xs text-muted-foreground hover:underline">
          Gerenciar prompts
        </Link>
      </div>

      <div className="flex gap-2">
        <select
          className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
        >
          <option value="">Selecione um prompt...</option>

          <optgroup label="Presets do Sistema">
            {TRANSCRIPTION_PRESETS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} — {p.category}
              </option>
            ))}
          </optgroup>

          {customPrompts.length > 0 && (
            <optgroup label="Seus Prompts Personalizados">
              {customPrompts.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} — {p.category}
                </option>
              ))}
            </optgroup>
          )}
        </select>

        <Button
          variant="outline"
          disabled={!selected}
          onClick={() => selected && onReplace(selected.template)}
          title="Substitui o texto do prompt customizado pelo template selecionado"
        >
          Carregar
        </Button>

        {onAppend && (
          <Button
            variant="outline"
            disabled={!selected}
            onClick={() => selected && onAppend(selected.template)}
            title="Insere o template no final do prompt customizado"
          >
            Inserir
          </Button>
        )}
      </div>

      {selected?.description ? (
        <div className="text-xs text-muted-foreground">{selected.description}</div>
      ) : (
        <div className="text-xs text-muted-foreground">
          Dica: prompts salvos em <span className="font-medium">/prompts</span> também podem ser usados aqui.
        </div>
      )}
    </div>
  );
}








