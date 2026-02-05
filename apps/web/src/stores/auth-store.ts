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
  is_guest?: boolean;
}

interface GuestSession {
  id: string;
  display_name: string;
  is_guest: boolean;
  expires_at: string;
  space_id: string | null;
  permissions: Record<string, unknown>;
  created_at: string;
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isGuest: boolean;
  guestSession: GuestSession | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  loginTest: () => Promise<void>;
  loginAsGuest: (token: string, displayName?: string) => Promise<void>;
  register: (data: { name: string; email: string; password: string; account_type: string;[key: string]: any }) => Promise<void>;
  logout: () => void;
  updateUser: (data: Partial<User>) => void;
  fetchProfile: () => Promise<void>;
  checkGuestExpiration: () => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      isAuthenticated: false,
      isGuest: false,
      guestSession: null,
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

      loginAsGuest: async (shareToken: string, displayName?: string) => {
        set({ isLoading: true });
        try {
          const API_URL = process.env.NEXT_PUBLIC_API_URL || '/api';
          const res = await fetch(`${API_URL}/auth/guest/from-share/${shareToken}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ display_name: displayName || undefined }),
          });

          if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.detail || 'Erro ao criar sessao de visitante');
          }

          const data = await res.json();

          // Salvar token no localStorage (apiClient ira pegar automaticamente)
          if (typeof window !== 'undefined') {
            localStorage.setItem('access_token', data.access_token);
            localStorage.setItem('guest_session', JSON.stringify(data.guest));
          }

          const guestUser: User = {
            id: data.guest.id,
            name: data.guest.display_name,
            email: '',
            role: 'GUEST',
            plan: 'FREE',
            account_type: 'GUEST',
            organization_id: null,
            created_at: data.guest.created_at,
            is_guest: true,
          };

          set({
            user: guestUser,
            isAuthenticated: true,
            isGuest: true,
            guestSession: data.guest,
            isLoading: false,
          });
        } catch (error) {
          set({ isLoading: false });
          throw error;
        }
      },

      logout: () => {
        // Limpar dados de guest tambem
        if (typeof window !== 'undefined') {
          localStorage.removeItem('guest_session');
        }
        apiClient.logout();
        set({
          user: null,
          isAuthenticated: false,
          isGuest: false,
          guestSession: null,
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
          set({ user, isAuthenticated: true, isGuest: false, guestSession: null });
        } catch (error) {
          apiClient.logout();
          set({ user: null, isAuthenticated: false, isGuest: false, guestSession: null });
        }
      },

      checkGuestExpiration: () => {
        const state = get();
        if (!state.isGuest || !state.guestSession) return false;

        const expiresAt = new Date(state.guestSession.expires_at).getTime();
        const now = Date.now();

        if (now >= expiresAt) {
          // Sessao expirada — fazer logout
          if (typeof window !== 'undefined') {
            localStorage.removeItem('guest_session');
          }
          apiClient.logout();
          set({
            user: null,
            isAuthenticated: false,
            isGuest: false,
            guestSession: null,
          });
          return true; // expirado
        }
        return false; // ainda valido
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
        isGuest: state.isGuest,
        guestSession: state.guestSession,
      }),
    }
  )
);
