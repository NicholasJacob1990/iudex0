/**
 * React context para autenticacao Microsoft SSO.
 *
 * Fluxo:
 * 1. Inicializa MSAL
 * 2. Adquire token Microsoft via acquireToken()
 * 3. Envia token para POST /auth/microsoft-sso do backend
 * 4. Recebe JWT Iudex e armazena
 * 5. Expoe estado de autenticacao para a aplicacao
 */

import {
  createContext,
  useContext,
  useCallback,
  useEffect,
  useState,
  type ReactNode,
} from 'react';
import { acquireToken, msalLogout } from './msal-config';
import { microsoftSSOLogin, logout as apiLogout, type AuthResponse } from '@/api/client';

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

interface AuthContextValue {
  isAuthenticated: boolean;
  isLoading: boolean;
  user: User | null;
  error: string | null;
  login: () => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Verifica se ja tem token armazenado ao montar
  useEffect(() => {
    const token = localStorage.getItem('vorbium_access_token');
    const storedUser = localStorage.getItem('vorbium_user');
    if (token && storedUser) {
      try {
        setUser(JSON.parse(storedUser));
        setIsAuthenticated(true);
      } catch {
        // Token invalido, limpa
        localStorage.removeItem('vorbium_access_token');
        localStorage.removeItem('vorbium_user');
      }
    }
  }, []);

  const login = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      // 1. Adquire token Microsoft
      const msalResult = await acquireToken();
      const microsoftToken = msalResult.accessToken;

      // 2. Envia para o backend Iudex
      const response: AuthResponse = await microsoftSSOLogin(microsoftToken);

      // 3. Armazena usuario
      setUser(response.user);
      setIsAuthenticated(true);
      localStorage.setItem('vorbium_user', JSON.stringify(response.user));
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Erro ao fazer login com Microsoft';
      setError(message);
      console.error('[AuthProvider] Login error:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    apiLogout();
    msalLogout().catch(console.error);
    setUser(null);
    setIsAuthenticated(false);
    setError(null);
    localStorage.removeItem('vorbium_user');
  }, []);

  return (
    <AuthContext.Provider
      value={{ isAuthenticated, isLoading, user, error, login, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth deve ser usado dentro de um AuthProvider');
  }
  return context;
}
