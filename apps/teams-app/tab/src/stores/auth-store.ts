import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { logout as apiLogout } from '@/api/client';

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
  setAuth: (user: User, accessToken: string, refreshToken: string) => void;
  logout: () => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      setAuth: (user: User, accessToken: string, refreshToken: string) => {
        localStorage.setItem('vorbium_teams_access_token', accessToken);
        localStorage.setItem('vorbium_teams_refresh_token', refreshToken);
        set({
          user,
          isAuthenticated: true,
          isLoading: false,
          error: null,
        });
      },

      logout: () => {
        apiLogout();
        set({
          user: null,
          isAuthenticated: false,
          error: null,
        });
      },

      setLoading: (loading: boolean) => set({ isLoading: loading }),

      setError: (error: string | null) => set({ error, isLoading: false }),

      clearError: () => set({ error: null }),
    }),
    {
      name: 'vorbium-teams-auth',
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
