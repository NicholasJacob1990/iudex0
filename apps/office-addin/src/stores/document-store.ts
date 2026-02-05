import { create } from 'zustand';
import {
  getDocumentText,
  getSelectedText,
  getDocumentMetadata,
  type DocumentMetadata,
} from '@/office/document-bridge';

interface DocumentState {
  /** Texto completo do documento */
  fullText: string;
  /** Texto selecionado pelo usuário */
  selectedText: string;
  /** Metadata do documento */
  metadata: DocumentMetadata | null;
  /** Se está carregando dados do documento */
  isLoading: boolean;
  /** Último erro */
  error: string | null;

  /** Carrega texto completo do documento */
  loadFullText: () => Promise<void>;
  /** Carrega texto selecionado */
  loadSelection: () => Promise<void>;
  /** Carrega metadata do documento */
  loadMetadata: () => Promise<void>;
  /** Carrega tudo (texto + seleção + metadata) */
  refresh: () => Promise<void>;
}

export const useDocumentStore = create<DocumentState>()((set) => ({
  fullText: '',
  selectedText: '',
  metadata: null,
  isLoading: false,
  error: null,

  loadFullText: async () => {
    try {
      set({ isLoading: true });
      const text = await getDocumentText();
      set({ fullText: text, isLoading: false, error: null });
    } catch (err: unknown) {
      set({
        isLoading: false,
        error:
          err instanceof Error ? err.message : 'Erro ao ler documento',
      });
    }
  },

  loadSelection: async () => {
    try {
      const selection = await getSelectedText();
      set({ selectedText: selection.text, error: null });
    } catch (err: unknown) {
      set({
        error:
          err instanceof Error ? err.message : 'Erro ao ler seleção',
      });
    }
  },

  loadMetadata: async () => {
    try {
      const metadata = await getDocumentMetadata();
      set({ metadata, error: null });
    } catch (err: unknown) {
      set({
        error:
          err instanceof Error ? err.message : 'Erro ao ler metadata',
      });
    }
  },

  refresh: async () => {
    set({ isLoading: true });
    try {
      const [text, selection, metadata] = await Promise.all([
        getDocumentText(),
        getSelectedText(),
        getDocumentMetadata(),
      ]);
      set({
        fullText: text,
        selectedText: selection.text,
        metadata,
        isLoading: false,
        error: null,
      });
    } catch (err: unknown) {
      set({
        isLoading: false,
        error: err instanceof Error ? err.message : 'Erro ao atualizar',
      });
    }
  },
}));
