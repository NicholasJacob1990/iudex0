/**
 * Zustand store para estado de autenticacao.
 *
 * Adaptado do apps/office-addin para suportar Microsoft SSO.
 * Usa microsoftSSOLogin em vez de login com email/password.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import {
  microsoftSSOLogin,
  logout as apiLogout,
  type AuthResponse,
} from '@/api/client';
import { acquireToken, msalLogout } from '@/auth/msal-config';

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
  error: string | null;
  login: () => Promise<void>;
  logout: () => void;
  clearError: () => void;
  checkAuth: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      /**
       * Login via Microsoft SSO:
       * 1. Adquire token Microsoft via MSAL
       * 2. Envia para backend /auth/microsoft-sso
       * 3. Armazena usuario e JWT
       */
      login: async () => {
        set({ isLoading: true, error: null });
        try {
          // Adquire token Microsoft
          const msalResult = await acquireToken();
          const microsoftToken = msalResult.accessToken;

          // Envia para o backend
          const response: AuthResponse = await microsoftSSOLogin(microsoftToken);

          set({
            user: response.user,
            isAuthenticated: true,
            isLoading: false,
            error: null,
          });
        } catch (err: unknown) {
          const message =
            err instanceof Error ? err.message : 'Erro ao fazer login com Microsoft';
          set({ isLoading: false, error: message });
          throw err;
        }
      },

      logout: () => {
        apiLogout();
        msalLogout().catch(console.error);
        set({
          user: null,
          isAuthenticated: false,
          error: null,
        });
      },

      clearError: () => set({ error: null }),

      /**
       * Verifica se o token armazenado ainda e valido.
       * Chamado ao montar a aplicacao.
       */
      checkAuth: () => {
        const token = localStorage.getItem('vorbium_access_token');
        if (!token) {
          set({ isAuthenticated: false, user: null });
        }
      },
    }),
    {
      name: 'vorbium-outlook-auth',
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
