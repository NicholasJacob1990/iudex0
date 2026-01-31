import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import apiClient from '@/lib/api-client';

interface User {
  id: string;
  name: string;
  email: string;
  role: string;
  plan: string;
  account_type: string;
  organization_id?: string | null;
  created_at: string;
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  loginTest: () => Promise<void>;
  register: (data: { name: string; email: string; password: string; account_type: string;[key: string]: any }) => Promise<void>;
  logout: () => void;
  updateUser: (data: Partial<User>) => void;
  fetchProfile: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      isLoading: false,

      login: async (email: string, password: string) => {
        set({ isLoading: true });
        try {
          const response = await apiClient.login(email, password);
          set({
            user: response.user,
            isAuthenticated: true,
            isLoading: false,
          });
        } catch (error) {
          set({ isLoading: false });
          throw error;
        }
      },

      loginTest: async () => {
        console.log('[Auth Store] loginTest iniciado');
        set({ isLoading: true });
        // Limpar estado anterior para evitar conflitos
        apiClient.clearTokens();
        set({ user: null, isAuthenticated: false });

        try {
          console.log('[Auth Store] Chamando API login-test...');
          const response = await apiClient.loginTest();
          console.log('[Auth Store] Resposta recebida. User:', response.user?.email);

          set({
            user: response.user,
            isAuthenticated: true,
            isLoading: false,
          });
          console.log('[Auth Store] Estado atualizado (isAuthenticated: true)');
        } catch (error) {
          console.error('[Auth Store] Erro grave em loginTest:', error);
          set({ isLoading: false });
          throw error;
        }
      },

      register: async (data) => {
        set({ isLoading: true });
        try {
          const response = await apiClient.register(data);
          set({
            user: response.user,
            isAuthenticated: true,
            isLoading: false,
          });
        } catch (error) {
          set({ isLoading: false });
          throw error;
        }
      },

      logout: () => {
        apiClient.logout();
        set({
          user: null,
          isAuthenticated: false,
        });
      },

      updateUser: (data) => {
        set((state) => ({
          user: state.user ? { ...state.user, ...data } : null,
        }));
      },

      fetchProfile: async () => {
        try {
          const user = await apiClient.getProfile();
          set({ user, isAuthenticated: true });
        } catch (error) {
          apiClient.logout();
          set({ user: null, isAuthenticated: false });
        }
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
