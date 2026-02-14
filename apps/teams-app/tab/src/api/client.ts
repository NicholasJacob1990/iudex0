/**
 * Cliente HTTP para comunicacao com a API Vorbium.
 *
 * Gerencia autenticacao JWT, refresh de tokens e chamadas HTTP.
 * Adaptado do api-client.ts do apps/office-addin para o contexto do Teams Tab.
 */

import axios, {
  AxiosInstance,
  AxiosError,
  InternalAxiosRequestConfig,
} from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api';

const TOKEN_KEY = 'vorbium_teams_access_token';
const REFRESH_KEY = 'vorbium_teams_refresh_token';

function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

function setTokens(access: string, refresh: string): void {
  localStorage.setItem(TOKEN_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

function clearTokens(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

const api: AxiosInstance = axios.create({
  baseURL: API_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// Request interceptor: attach JWT
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken();
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor: auto-refresh on 401
let isRefreshing = false;
let refreshQueue: Array<{
  resolve: (token: string) => void;
  reject: (err: unknown) => void;
}> = [];

function processQueue(error: unknown, token: string | null) {
  refreshQueue.forEach(({ resolve, reject }) => {
    if (error) {
      reject(error);
    } else if (token) {
      resolve(token);
    }
  });
  refreshQueue = [];
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    if (error.response?.status === 401 && !originalRequest._retry) {
      const refreshToken = getRefreshToken();
      if (!refreshToken) {
        clearTokens();
        return Promise.reject(error);
      }

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          refreshQueue.push({
            resolve: (token: string) => {
              if (originalRequest.headers) {
                originalRequest.headers.Authorization = `Bearer ${token}`;
              }
              resolve(api(originalRequest));
            },
            reject,
          });
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const { data } = await axios.post(`${API_URL}/auth/refresh`, {
          refresh_token: refreshToken,
        });
        setTokens(data.access_token, data.refresh_token);
        processQueue(null, data.access_token);

        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
        }
        return api(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        clearTokens();
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

// -- Auth (Teams SSO) -------------------------------------------------------

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: {
    id: string;
    email: string;
    name: string;
    role: string;
    plan: string;
    account_type: string;
    organization_id?: string | null;
    created_at: string;
  };
}

/**
 * Login via Teams SSO token exchange.
 * Envia o token do Teams para o backend que troca por JWT Vorbium.
 */
export async function teamsSSOLogin(teamsToken: string): Promise<AuthResponse> {
  const { data } = await api.post<AuthResponse>('/auth/teams-sso', {
    teams_token: teamsToken,
  });
  setTokens(data.access_token, data.refresh_token);
  return data;
}

export function logout(): void {
  clearTokens();
}

// -- Workflows ---------------------------------------------------------------

export interface Workflow {
  id: string;
  name: string;
  type: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  created_at: string;
  updated_at: string;
  progress?: number;
}

export interface WorkflowListResponse {
  items: Workflow[];
  total: number;
}

export async function getWorkflows(
  limit = 20,
  offset = 0
): Promise<WorkflowListResponse> {
  const { data } = await api.get<WorkflowListResponse>('/workflows/', {
    params: { limit, offset },
  });
  return data;
}

export async function getWorkflowById(workflowId: string): Promise<Workflow> {
  const { data } = await api.get<Workflow>(`/workflows/${workflowId}`);
  return data;
}

// -- Corpus ------------------------------------------------------------------

export interface CorpusResult {
  id: string;
  title: string;
  content: string;
  score: number;
  source?: string;
  metadata?: Record<string, unknown>;
}

export interface CorpusSearchResponse {
  results: CorpusResult[];
  total: number;
  query: string;
}

export async function searchCorpus(
  query: string,
  limit = 10
): Promise<CorpusSearchResponse> {
  const { data } = await api.post<CorpusSearchResponse>('/corpus/search', {
    query,
    limit,
  });
  return data;
}

// -- Notifications -----------------------------------------------------------

export interface Notification {
  id: string;
  title: string;
  message: string;
  type: 'info' | 'warning' | 'success' | 'error';
  read: boolean;
  created_at: string;
}

export async function getNotifications(limit = 10): Promise<Notification[]> {
  const { data } = await api.get<Notification[]>('/notifications/', {
    params: { limit },
  });
  return data;
}

// -- Exports -----------------------------------------------------------------

export { api, getAccessToken, clearTokens, API_URL };
