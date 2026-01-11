import { create } from 'zustand';
import apiClient from '@/lib/api-client';

interface LibraryItem {
  id: string;
  name: string;
  description?: string;
  type: string;
  tags: string[];
  folder_id?: string;
  resource_id: string;
  is_shared: boolean;
  created_at: string;
  updated_at: string;
}

interface Librarian {
  id: string;
  name: string;
  description: string;
  icon?: string;
  resources: string[];
  is_shared: boolean;
  created_at: string;
  updated_at: string;
}

interface LibraryState {
  items: LibraryItem[];
  total: number;
  librarians: Librarian[];
  isLoading: boolean;
  fetchItems: () => Promise<void>;
  fetchLibrarians: () => Promise<void>;
  deleteItem: (itemId: string) => Promise<void>;
  activateLibrarian: (librarianId: string) => Promise<any>;
}


export const useLibraryStore = create<LibraryState>((set, get) => ({
  items: [],
  total: 0,
  librarians: [],
  isLoading: false,

  fetchItems: async () => {
    set({ isLoading: true });
    try {
      const response = await apiClient.getLibraryItems();
      set({
        items: response.items || [],
        total: response.total || 0,
        isLoading: false,
      });
    } catch (error) {
      console.error('Erro ao buscar biblioteca', error);
      set({ isLoading: false });
      throw error;
    }
  },

  fetchLibrarians: async () => {
    set({ isLoading: true });
    try {
      const response = await apiClient.getLibrarians();
      set({
        librarians: response?.librarians || [],
        isLoading: false,
      });
    } catch (error) {
      console.error('Erro ao buscar bibliotecários', error);
      set({ isLoading: false });
    }
  },

  deleteItem: async (itemId: string) => {
    await apiClient.deleteLibraryItem(itemId);
    set((state) => ({
      items: state.items.filter((item) => item.id !== itemId),
      total: Math.max(0, state.total - 1),
    }));
  },

  activateLibrarian: async (librarianId: string) => {
    try {
      const response = await fetch(`/api/library/librarians/${librarianId}/activate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error('Erro ao ativar bibliotecário');
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Erro ao ativar bibliotecário:', error);
      throw error;
    }
  },
}));

