/**
 * Componente de biblioteca de prompts curados.
 *
 * Gap 10: Permite ao usuario selecionar prompts pre-definidos
 * para edicao de documentos no DraftPanel.
 */

import { useState, useMemo, useCallback } from 'react';
import {
  PROMPT_LIBRARY,
  CATEGORY_LABELS,
  searchPrompts,
  type PromptTemplate,
  type PromptCategory,
} from '@/data/prompt-library';

interface PromptLibraryProps {
  /** Callback quando um prompt e selecionado */
  onSelect: (prompt: PromptTemplate) => void;
  /** Categoria inicial selecionada */
  initialCategory?: PromptCategory | 'all';
  /** Se deve mostrar em modo compacto */
  compact?: boolean;
}

const ALL_CATEGORIES: Array<PromptCategory | 'all'> = [
  'all',
  'editing',
  'drafting',
  'analysis',
  'translation',
  'compliance',
];

export function PromptLibrary({
  onSelect,
  initialCategory = 'all',
  compact = false,
}: PromptLibraryProps) {
  const [category, setCategory] = useState<PromptCategory | 'all'>(initialCategory);
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    let result = PROMPT_LIBRARY;

    // Filtrar por categoria
    if (category !== 'all') {
      result = result.filter((p) => p.category === category);
    }

    // Filtrar por busca
    if (search.trim()) {
      result = searchPrompts(search);
      // Se tem categoria selecionada, filtrar tambem
      if (category !== 'all') {
        result = result.filter((p) => p.category === category);
      }
    }

    return result;
  }, [category, search]);

  const handleSelect = useCallback(
    (prompt: PromptTemplate) => {
      onSelect(prompt);
    },
    [onSelect]
  );

  return (
    <div className="prompt-library flex flex-col">
      {/* Search */}
      <div className="mb-3">
        <input
          type="text"
          placeholder="Buscar prompts..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="office-input w-full text-office-sm"
        />
      </div>

      {/* Categories */}
      <div className="mb-3 flex flex-wrap gap-1.5">
        {ALL_CATEGORIES.map((cat) => (
          <button
            key={cat}
            onClick={() => setCategory(cat)}
            className={`rounded-full px-2.5 py-1 text-office-xs font-medium transition-colors ${
              category === cat
                ? 'bg-brand text-white'
                : 'bg-surface-tertiary text-text-secondary hover:bg-gray-200'
            }`}
          >
            {cat === 'all' ? 'Todos' : CATEGORY_LABELS[cat]}
          </button>
        ))}
      </div>

      {/* Prompts list */}
      <div className={`space-y-2 ${compact ? 'max-h-[300px]' : 'max-h-[400px]'} overflow-y-auto`}>
        {filtered.length === 0 && (
          <p className="py-4 text-center text-office-xs text-text-tertiary">
            Nenhum prompt encontrado.
          </p>
        )}

        {filtered.map((prompt) => (
          <PromptCard
            key={prompt.id}
            prompt={prompt}
            onSelect={handleSelect}
            compact={compact}
          />
        ))}
      </div>

      {/* Count */}
      <div className="mt-2 text-office-xs text-text-tertiary">
        {filtered.length} prompt{filtered.length !== 1 ? 's' : ''} disponivel
        {filtered.length !== 1 ? 'is' : ''}
      </div>
    </div>
  );
}

// ── PromptCard ──────────────────────────────────────────────────

interface PromptCardProps {
  prompt: PromptTemplate;
  onSelect: (prompt: PromptTemplate) => void;
  compact?: boolean;
}

function PromptCard({ prompt, onSelect, compact = false }: PromptCardProps) {
  const categoryLabel = CATEGORY_LABELS[prompt.category];

  return (
    <button
      onClick={() => onSelect(prompt)}
      className="office-card w-full cursor-pointer text-left transition-all hover:border-brand hover:shadow-sm"
    >
      <div className="flex items-start justify-between gap-2">
        <h4 className="text-office-sm font-medium text-text-primary">{prompt.name}</h4>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-office-xs ${getCategoryStyle(
            prompt.category
          )}`}
        >
          {categoryLabel}
        </span>
      </div>

      <p className="mt-1 text-office-xs text-text-secondary">{prompt.description}</p>

      {!compact && prompt.tags && prompt.tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {prompt.tags.slice(0, 3).map((tag) => (
            <span
              key={tag}
              className="rounded bg-surface-tertiary px-1.5 py-0.5 text-office-xs text-text-tertiary"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </button>
  );
}

/**
 * Retorna classes de estilo para badge de categoria.
 */
function getCategoryStyle(category: PromptCategory): string {
  switch (category) {
    case 'editing':
      return 'bg-blue-100 text-blue-700';
    case 'drafting':
      return 'bg-green-100 text-green-700';
    case 'analysis':
      return 'bg-purple-100 text-purple-700';
    case 'translation':
      return 'bg-orange-100 text-orange-700';
    case 'compliance':
      return 'bg-red-100 text-red-700';
    default:
      return 'bg-gray-100 text-gray-700';
  }
}

// ── PromptLibraryModal ──────────────────────────────────────────

interface PromptLibraryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (prompt: PromptTemplate) => void;
}

export function PromptLibraryModal({ isOpen, onClose, onSelect }: PromptLibraryModalProps) {
  const handleSelect = useCallback(
    (prompt: PromptTemplate) => {
      onSelect(prompt);
      onClose();
    },
    [onSelect, onClose]
  );

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-md rounded-lg bg-white p-4 shadow-xl">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-office-base font-semibold">Biblioteca de Prompts</h3>
          <button
            onClick={onClose}
            className="rounded p-1 text-text-tertiary hover:bg-surface-tertiary"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <PromptLibrary onSelect={handleSelect} />
      </div>
    </div>
  );
}

// ── QuickPromptSelector ─────────────────────────────────────────

interface QuickPromptSelectorProps {
  onSelect: (prompt: PromptTemplate) => void;
  category?: PromptCategory;
  limit?: number;
}

/**
 * Seletor rapido de prompts para exibicao inline.
 * Mostra os prompts mais usados de uma categoria.
 */
export function QuickPromptSelector({
  onSelect,
  category = 'editing',
  limit = 5,
}: QuickPromptSelectorProps) {
  const prompts = useMemo(() => {
    return PROMPT_LIBRARY.filter((p) => p.category === category).slice(0, limit);
  }, [category, limit]);

  return (
    <div className="space-y-1">
      {prompts.map((prompt) => (
        <button
          key={prompt.id}
          onClick={() => onSelect(prompt)}
          className="block w-full rounded border border-gray-200 px-3 py-1.5 text-left text-office-xs text-text-secondary hover:border-brand hover:bg-blue-50"
        >
          <span className="font-medium">{prompt.name}</span>
          <span className="ml-1 text-text-tertiary">- {prompt.description}</span>
        </button>
      ))}
    </div>
  );
}
