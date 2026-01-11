import { create } from 'zustand';
import apiClient from '@/lib/api-client';

interface Document {
  id: string;
  name: string;
  file_type: string;
  file_size: number;
  status: 'pending' | 'processing' | 'completed' | 'error';
  content?: string;
  metadata?: any;
  created_at: string;
}

interface DocumentState {
  documents: Document[];
  currentDocument: Document | null;
  isLoading: boolean;
  isUploading: boolean;
  fetchDocuments: () => Promise<void>;
  uploadDocument: (file: File, metadata?: any) => Promise<Document>;
  deleteDocument: (id: string) => Promise<void>;
  setCurrentDocument: (id: string | null) => Promise<void>;
  processDocument: (id: string, options?: any) => Promise<void>;
}

export const useDocumentStore = create<DocumentState>((set, get) => ({
  documents: [],
  currentDocument: null,
  isLoading: false,
  isUploading: false,

  fetchDocuments: async () => {
    set({ isLoading: true });
    try {
      const { documents } = await apiClient.getDocuments();
      const normalized = (documents || []).map((doc: any) => ({
        ...doc,
        file_size: doc.file_size ?? doc.size ?? 0,
        created_at: doc.created_at ?? new Date().toISOString(),
      }));
      set({ documents: normalized, isLoading: false });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  uploadDocument: async (file: File, metadata?: any) => {
    set({ isUploading: true });
    try {
      const document = await apiClient.uploadDocument(file, metadata);
      const normalized = {
        ...document,
        file_size: document.file_size ?? document.size ?? 0,
      };
      set((state) => ({
        documents: [normalized, ...state.documents],
        isUploading: false,
      }));
      return normalized as Document;
    } catch (error) {
      set({ isUploading: false });
      throw error;
    }
  },

  deleteDocument: async (id: string) => {
    try {
      await apiClient.deleteDocument(id);
      set((state) => ({
        documents: state.documents.filter((d) => d.id !== id),
        currentDocument: state.currentDocument?.id === id ? null : state.currentDocument,
      }));
    } catch (error) {
      throw error;
    }
  },

  setCurrentDocument: async (id: string | null) => {
    if (!id) {
      set({ currentDocument: null });
      return;
    }

    set({ isLoading: true });
    try {
      const document = await apiClient.getDocument(id);
      set({ currentDocument: document, isLoading: false });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  processDocument: async (id: string, options?: any) => {
    try {
      await apiClient.processDocument(id, options);
      // Atualizar status do documento
      set((state) => ({
        documents: state.documents.map((d) =>
          d.id === id ? { ...d, status: 'processing' as const } : d
        ),
      }));
    } catch (error) {
      throw error;
    }
  },
}));
