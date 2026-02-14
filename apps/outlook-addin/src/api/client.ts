/**
 * Cliente HTTP para comunicacao com a API Vorbium.
 *
 * Gerencia autenticacao JWT, refresh de tokens e chamadas HTTP.
 * Adaptado do api-client.ts do apps/office-addin para o contexto do Outlook Add-in.
 * Inclui endpoint de Microsoft SSO e funcoes especificas para Outlook.
 */

import axios, {
  AxiosInstance,
  AxiosError,
  InternalAxiosRequestConfig,
} from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api';

const TOKEN_KEY = 'vorbium_access_token';
const REFRESH_KEY = 'vorbium_refresh_token';

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

// ── Auth ────────────────────────────────────────────────────────

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
 * Login via Microsoft SSO.
 * Envia o access_token da Microsoft para o backend que valida e retorna JWT Iudex.
 */
export async function microsoftSSOLogin(
  microsoftToken: string
): Promise<AuthResponse> {
  const { data } = await api.post<AuthResponse>('/auth/microsoft-sso', {
    microsoft_token: microsoftToken,
  });
  setTokens(data.access_token, data.refresh_token);
  return data;
}

export async function login(
  email: string,
  password: string
): Promise<AuthResponse> {
  const { data } = await api.post<AuthResponse>('/auth/login', {
    email,
    password,
  });
  setTokens(data.access_token, data.refresh_token);
  return data;
}

export function logout(): void {
  clearTokens();
}

// ── Corpus ──────────────────────────────────────────────────────

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

// ── Outlook Add-in specific ─────────────────────────────────────

export interface EmailSummarizeRequest {
  subject: string;
  body: string;
  sender: string;
  recipients: string[];
  date: string;
  attachments?: Array<{ name: string; contentType: string }>;
}

export interface ClassifyResult {
  tipo_juridico: string;
  subtipo?: string;
  confianca: number;
  tags: string[];
}

export interface DeadlineResult {
  descricao: string;
  data: string;
  urgencia: 'alta' | 'media' | 'baixa';
  fonte: string;
}

export interface SummarizeResponse {
  classificacao: ClassifyResult;
  resumo: string;
  prazos: DeadlineResult[];
  acoes_sugeridas: string[];
  workflows_recomendados: string[];
}

export async function classifyEmail(
  data: EmailSummarizeRequest
): Promise<ClassifyResult> {
  const { data: result } = await api.post<ClassifyResult>(
    '/outlook-addin/classify',
    data
  );
  return result;
}

export async function extractDeadlines(
  data: EmailSummarizeRequest
): Promise<DeadlineResult[]> {
  const { data: result } = await api.post<DeadlineResult[]>(
    '/outlook-addin/deadlines',
    data
  );
  return result;
}

// ── Workflows ───────────────────────────────────────────────────

export interface WorkflowTriggerRequest {
  workflow_id: string;
  email_data: EmailSummarizeRequest;
  parameters?: Record<string, unknown>;
}

export interface WorkflowRun {
  id: string;
  workflow_id: string;
  workflow_name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  result?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export async function triggerWorkflow(
  request: WorkflowTriggerRequest
): Promise<WorkflowRun> {
  const { data } = await api.post<WorkflowRun>(
    '/outlook-addin/workflow/trigger',
    request
  );
  return data;
}

export async function getWorkflowStatus(runId: string): Promise<WorkflowRun> {
  const { data } = await api.get<WorkflowRun>(
    `/outlook-addin/workflow/status/${runId}`
  );
  return data;
}

// ── Exports ─────────────────────────────────────────────────────

export { api, getAccessToken, clearTokens, API_URL };
