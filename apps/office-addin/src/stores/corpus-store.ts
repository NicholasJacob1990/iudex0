import { create } from 'zustand';
import { searchCorpus, type CorpusResult } from '@/api/client';
import { useDocumentStore } from './document-store';

type SortBy = 'relevance' | 'title';

interface SearchHistoryEntry {
  query: string;
  resultCount: number;
  timestamp: number;
}

interface CorpusStore {
  // State
  query: string;
  results: CorpusResult[];
  isSearching: boolean;
  error: string | null;
  totalResults: number;

  // Filters
  minScore: number;
  sortBy: SortBy;

  // UI state
  expandedResultId: string | null;
  selectedResults: Set<string>;

  // History
  searchHistory: SearchHistoryEntry[];

  // Actions
  setQuery: (q: string) => void;
  search: (q?: string) => Promise<void>;
  searchFromSelection: () => Promise<void>;
  setMinScore: (score: number) => void;
  setSortBy: (sort: SortBy) => void;
  toggleExpanded: (id: string) => void;
  toggleSelected: (id: string) => void;
  clearSelection: () => void;
  clearResults: () => void;

  // Computed
  filteredResults: () => CorpusResult[];
  selectedResultsList: () => CorpusResult[];
}

export const useCorpusStore = create<CorpusStore>((set, get) => ({
  query: '',
  results: [],
  isSearching: false,
  error: null,
  totalResults: 0,
  minScore: 0,
  sortBy: 'relevance',
  expandedResultId: null,
  selectedResults: new Set(),
  searchHistory: [],

  setQuery: (q) => set({ query: q }),

  search: async (q?: string) => {
    const query = q || get().query;
    if (!query.trim()) return;

    set({ isSearching: true, error: null, query });

    try {
      const response = await searchCorpus(query.trim(), 20);
      const entry: SearchHistoryEntry = {
        query: query.trim(),
        resultCount: response.results.length,
        timestamp: Date.now(),
      };

      const history = [entry, ...get().searchHistory.filter((h) => h.query !== query.trim())].slice(0, 10);

      set({
        results: response.results,
        totalResults: response.total,
        isSearching: false,
        searchHistory: history,
        selectedResults: new Set(),
        expandedResultId: null,
      });
    } catch (err: unknown) {
      set({
        error: err instanceof Error ? err.message : 'Erro na busca',
        isSearching: false,
      });
    }
  },

  searchFromSelection: async () => {
    await useDocumentStore.getState().loadSelection();
    const sel = useDocumentStore.getState().selectedText;
    if (sel.trim()) {
      const q = sel.trim().slice(0, 200);
      set({ query: q });
      await get().search(q);
    }
  },

  setMinScore: (score) => set({ minScore: score }),
  setSortBy: (sort) => set({ sortBy: sort }),

  toggleExpanded: (id) => {
    set({ expandedResultId: get().expandedResultId === id ? null : id });
  },

  toggleSelected: (id) => {
    const next = new Set(get().selectedResults);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    set({ selectedResults: next });
  },

  clearSelection: () => set({ selectedResults: new Set() }),

  clearResults: () =>
    set({
      results: [],
      totalResults: 0,
      error: null,
      expandedResultId: null,
      selectedResults: new Set(),
    }),

  filteredResults: () => {
    const { results, minScore, sortBy } = get();
    let filtered = results.filter((r) => r.score >= minScore);

    if (sortBy === 'title') {
      filtered = [...filtered].sort((a, b) => a.title.localeCompare(b.title));
    }

    return filtered;
  },

  selectedResultsList: () => {
    const { results, selectedResults } = get();
    return results.filter((r) => selectedResults.has(r.id));
  },
}));
