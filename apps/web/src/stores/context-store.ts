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

export interface ContextItem {
  id: string;
  type: 'file' | 'folder' | 'model' | 'legislation' | 'audio' | 'link' | 'jurisprudence';
  name: string;
  meta?: string;
}

interface ContextState {
  search: string;
  sources: ContextSource[];
  items: ContextItem[];
  activeTab: string;
  setSearch: (value: string) => void;
  setActiveTab: (value: string) => void;
  toggleSource: (id: ContextSourceId) => void;
  toggleMeta: (id: ContextSourceId, key: 'ocr' | 'rigorous') => void;
  setSourceCounts: (counts: Partial<Record<ContextSourceId, number>>) => void;
  addItem: (item: ContextItem) => void;
  removeItem: (id: string) => void;
}

export const useContextStore = create<ContextState>((set) => ({
  search: '',
  sources: [
    {
      id: 'documents',
      label: 'Documentos',
      description: 'Integra PDF, DOCX, ZIP e imagens',
      enabled: true,
      count: 0,
      meta: { ocr: true },
    },
    {
      id: 'models',
      label: 'Modelos',
      description: 'Siga pareceres e referências',
      enabled: true,
      count: 0,
      meta: { rigorous: true },
    },
    {
      id: 'jurisprudence',
      label: 'Jurisprudência',
      description: 'Inclua precedentes STF/STJ',
      enabled: false,
      count: 0,
    },
    {
      id: 'legislation',
      label: 'Legislação',
      description: 'Adicione artigos oficiais',
      enabled: false,
      count: 0,
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
  setSourceCounts: (counts) =>
    set((state) => ({
      sources: state.sources.map((source) =>
        counts[source.id] === undefined ? source : { ...source, count: counts[source.id] ?? source.count }
      ),
    })),
  items: [],
  activeTab: 'files',
  setActiveTab: (value) => set({ activeTab: value }),
  addItem: (item) => set((state) => ({ items: [...state.items, item] })),
  removeItem: (id) => set((state) => ({ items: state.items.filter((i) => i.id !== id) })),
}));
