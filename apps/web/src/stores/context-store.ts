import { create } from 'zustand';

export type ContextSourceId = 'documents' | 'models' | 'jurisprudence' | 'legislation';

interface ContextSource {
  id: ContextSourceId;
  label: string;
  description: string;
  enabled: boolean;
  count: number;
  meta?: {
    ocr?: boolean;
    rigorous?: boolean;
  };
}

interface ContextState {
  search: string;
  sources: ContextSource[];
  setSearch: (value: string) => void;
  toggleSource: (id: ContextSourceId) => void;
  toggleMeta: (id: ContextSourceId, key: 'ocr' | 'rigorous') => void;
}

export const useContextStore = create<ContextState>((set) => ({
  search: '',
  sources: [
    {
      id: 'documents',
      label: 'Documentos',
      description: 'Integra PDF, DOCX, ZIP e imagens',
      enabled: true,
      count: 112,
      meta: { ocr: true },
    },
    {
      id: 'models',
      label: 'Modelos',
      description: 'Siga pareceres e referências',
      enabled: true,
      count: 32,
      meta: { rigorous: true },
    },
    {
      id: 'jurisprudence',
      label: 'Jurisprudência',
      description: 'Inclua precedentes STF/STJ',
      enabled: false,
      count: 18,
    },
    {
      id: 'legislation',
      label: 'Legislação',
      description: 'Adicione artigos oficiais',
      enabled: false,
      count: 24,
    },
  ],
  setSearch: (value) => set({ search: value }),
  toggleSource: (id) =>
    set((state) => ({
      sources: state.sources.map((source) =>
        source.id === id ? { ...source, enabled: !source.enabled } : source
      ),
    })),
  toggleMeta: (id, key) =>
    set((state) => ({
      sources: state.sources.map((source) =>
        source.id === id
          ? {
              ...source,
              meta: {
                ...source.meta,
                [key]: !source.meta?.[key],
              },
            }
          : source
      ),
    })),
}));

