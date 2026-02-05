import { create } from 'zustand';
import { streamEditContent } from '@/api/sse-client';
import { useDocumentStore } from './document-store';

export type EditMode = 'rewrite' | 'insert-after' | 'improve' | 'simplify' | 'formalize' | 'custom';
export type DraftState = 'idle' | 'editing' | 'preview';

export interface HistoryEntry {
  id: string;
  instruction: string;
  mode: EditMode;
  original: string;
  edited: string;
  applied: boolean;
  timestamp: number;
}

interface DraftingStore {
  // State
  state: DraftState;
  instruction: string;
  editMode: EditMode;
  originalContent: string;
  editedContent: string;
  streamingContent: string;
  isStreaming: boolean;
  error: string | null;

  // History
  history: HistoryEntry[];

  // Abort
  abortController: AbortController | null;

  // Actions
  setInstruction: (text: string) => void;
  setEditMode: (mode: EditMode) => void;
  startEdit: () => Promise<void>;
  abort: () => void;
  accept: () => void;
  reject: () => void;
  clearError: () => void;
  replayHistoryEntry: (entry: HistoryEntry) => void;
}

let historyCounter = 0;

function modeToInstruction(mode: EditMode, custom: string): string {
  switch (mode) {
    case 'improve':
      return 'Melhore a redacao deste texto mantendo o sentido original. Corrija erros gramaticais e torne mais claro.';
    case 'simplify':
      return 'Simplifique este texto juridico para que um leigo possa entender, mantendo a precisao legal.';
    case 'formalize':
      return 'Torne este texto mais formal e adequado para uso em documentos juridicos oficiais.';
    case 'rewrite':
      return custom || 'Reescreva este texto conforme a instrucao.';
    case 'insert-after':
      return custom || 'Gere conteudo complementar para inserir apos este trecho.';
    case 'custom':
      return custom;
    default:
      return custom;
  }
}

export const useDraftingStore = create<DraftingStore>((set, get) => ({
  state: 'idle',
  instruction: '',
  editMode: 'custom',
  originalContent: '',
  editedContent: '',
  streamingContent: '',
  isStreaming: false,
  error: null,
  history: [],
  abortController: null,

  setInstruction: (text) => set({ instruction: text }),
  setEditMode: (mode) => set({ editMode: mode }),

  startEdit: async () => {
    const { instruction, editMode, isStreaming: alreadyStreaming } = get();

    // Guard against concurrent edits
    if (alreadyStreaming) {
      get().abort();
    }

    const finalInstruction = modeToInstruction(editMode, instruction);

    if (!finalInstruction.trim()) {
      set({ error: 'Digite uma instrucao de edicao.' });
      return;
    }

    // Get current selection from document
    try {
      await useDocumentStore.getState().loadSelection();
    } catch {
      set({ error: 'Erro ao ler selecao do documento.' });
      return;
    }

    const sel = useDocumentStore.getState().selectedText;

    if (!sel.trim()) {
      set({ error: 'Selecione um trecho no documento Word primeiro.' });
      return;
    }

    const controller = new AbortController();

    set({
      originalContent: sel,
      editedContent: '',
      streamingContent: '',
      state: 'editing',
      isStreaming: true,
      error: null,
      abortController: controller,
    });

    let accumulated = '';

    try {
      await streamEditContent({
        content: sel,
        instruction: finalInstruction,
        onContent: (text) => {
          accumulated += text;
          set({ streamingContent: accumulated });
        },
        onDone: () => {
          const { originalContent, editMode: mode, instruction: inst } = get();
          const entry: HistoryEntry = {
            id: `draft-${++historyCounter}`,
            instruction: mode === 'custom' ? inst : `[${mode}] ${inst}`.trim(),
            mode,
            original: originalContent,
            edited: accumulated,
            applied: false,
            timestamp: Date.now(),
          };

          set({
            editedContent: accumulated,
            streamingContent: '',
            isStreaming: false,
            state: 'preview',
            abortController: null,
            history: [entry, ...get().history].slice(0, 20),
          });
        },
        onError: (err) => {
          set({
            error: err,
            isStreaming: false,
            state: 'idle',
            abortController: null,
          });
        },
        signal: controller.signal,
      });
    } catch (err: unknown) {
      if ((err as Error).name !== 'AbortError') {
        set({
          error: err instanceof Error ? err.message : 'Erro no stream de edicao',
          isStreaming: false,
          state: 'idle',
          abortController: null,
        });
      }
    }
  },

  abort: () => {
    const { abortController } = get();
    abortController?.abort();
    set({
      isStreaming: false,
      state: 'idle',
      abortController: null,
      streamingContent: '',
    });
  },

  accept: () => {
    const { history } = get();
    const updated = [...history];
    if (updated.length > 0) {
      updated[0] = { ...updated[0], applied: true };
    }
    set({
      state: 'idle',
      instruction: '',
      editedContent: '',
      originalContent: '',
      streamingContent: '',
      history: updated,
    });
  },

  reject: () => {
    set({
      state: 'idle',
      editedContent: '',
      originalContent: '',
      streamingContent: '',
    });
  },

  clearError: () => set({ error: null }),

  replayHistoryEntry: (entry) => {
    set({
      instruction: entry.instruction,
      originalContent: entry.original,
      editedContent: entry.edited,
      state: 'preview',
    });
  },
}));
