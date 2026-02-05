'use client';

import React, { useState } from 'react';
import { Database, X } from 'lucide-react';
import { Button } from '@/components/ui/button';

const CORPUS_COLLECTIONS = [
  { id: 'lei', label: 'Legislação', description: 'Leis, decretos, regulamentos' },
  { id: 'juris', label: 'Jurisprudência', description: 'Decisões de tribunais' },
  { id: 'pecas_modelo', label: 'Peças Modelo', description: 'Petições e modelos' },
  { id: 'doutrina', label: 'Doutrina', description: 'Livros e artigos' },
  { id: 'sei', label: 'SEI', description: 'Documentos do SEI' },
  { id: 'local', label: 'Documentos Locais', description: 'Uploads do usuário' },
];

const SCOPE_OPTIONS = [
  { id: 'global', label: 'Global (toda organização)' },
  { id: 'private', label: 'Privado (meus documentos)' },
];

interface CorpusPickerModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: (config: { type: 'corpus'; collections: string[]; scope: string; label: string }) => void;
  initialCollections?: string[];
  initialScope?: string;
}

export function CorpusPickerModal({ open, onClose, onConfirm, initialCollections = [], initialScope = 'global' }: CorpusPickerModalProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set(initialCollections));
  const [scope, setScope] = useState(initialScope);

  if (!open) return null;

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  const handleConfirm = () => {
    const collections = Array.from(selected);
    const label = collections.length === 0
      ? 'Corpus (todas)'
      : `Corpus: ${collections.map(c => CORPUS_COLLECTIONS.find(x => x.id === c)?.label || c).join(', ')}`;
    onConfirm({ type: 'corpus', collections, scope, label });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center">
      <div className="bg-white dark:bg-slate-900 rounded-xl shadow-xl w-full max-w-md p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Database className="h-5 w-5 text-cyan-500" />
            <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">Configurar Corpus</h3>
          </div>
          <button onClick={onClose}><X className="h-4 w-4 text-slate-400" /></button>
        </div>

        {/* Scope */}
        <label className="text-xs font-medium text-slate-500 mb-1 block">Escopo</label>
        <select
          value={scope}
          onChange={(e) => setScope(e.target.value)}
          className="w-full h-8 rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-2 text-sm mb-4"
        >
          {SCOPE_OPTIONS.map(s => (
            <option key={s.id} value={s.id}>{s.label}</option>
          ))}
        </select>

        {/* Collections */}
        <label className="text-xs font-medium text-slate-500 mb-2 block">
          Coleções {selected.size === 0 && '(todas serão buscadas)'}
        </label>
        <div className="space-y-1.5 mb-4">
          {CORPUS_COLLECTIONS.map(c => (
            <label
              key={c.id}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg border cursor-pointer transition-colors ${
                selected.has(c.id)
                  ? 'border-cyan-300 bg-cyan-50 dark:border-cyan-700 dark:bg-cyan-950'
                  : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'
              }`}
            >
              <input
                type="checkbox"
                checked={selected.has(c.id)}
                onChange={() => toggle(c.id)}
                className="rounded border-slate-300"
              />
              <div>
                <div className="text-xs font-medium text-slate-700 dark:text-slate-300">{c.label}</div>
                <div className="text-[10px] text-slate-400">{c.description}</div>
              </div>
            </label>
          ))}
        </div>

        <div className="flex gap-2">
          <Button variant="outline" size="sm" className="flex-1" onClick={onClose}>Cancelar</Button>
          <Button size="sm" className="flex-1 bg-cyan-600 hover:bg-cyan-500 text-white" onClick={handleConfirm}>
            Confirmar
          </Button>
        </div>
      </div>
    </div>
  );
}
