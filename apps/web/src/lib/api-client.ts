/**
 * Cliente HTTP para comunicação com a API Backend
 * 
 * Gerencia autenticação, refresh de tokens e chamadas HTTP
 */

import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios';
import { toast } from 'sonner';

const DEFAULT_API_URL =
  typeof window !== 'undefined'
    ? (/^https?:\/\//i.test(window.location.origin)
      ? `${window.location.origin}/api`
      : 'http://127.0.0.1:8000/api')
    : 'http://127.0.0.1:8000/api';

const normalizeApiUrl = (url: string): string => {
  const trimmed = url.replace(/\/+$/, '');
  if (!trimmed) return DEFAULT_API_URL;
  if (trimmed.endsWith('/api')) return trimmed;
  return `${trimmed}/api`;
};

const coerceAbsoluteUrl = (value: string): string => {
  const trimmed = value.trim();
  if (!trimmed) return '';
  if (trimmed.startsWith('/')) return trimmed;
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `http://${trimmed}`;
};

// In the browser, prefer same-origin `/api` (via Next rewrites) to avoid CORS/credentials issues in dev.
// If an env points to a different origin (e.g. http://localhost:8000/api), we still route through `/api`.
const resolveApiUrl = (): string => {
  const envRaw = (process.env.NEXT_PUBLIC_API_URL || '').trim();
  const env = coerceAbsoluteUrl(envRaw);
  if (typeof window === 'undefined') {
    return normalizeApiUrl(env || DEFAULT_API_URL);
  }
  if (!envRaw) return normalizeApiUrl(DEFAULT_API_URL);
  if (envRaw.startsWith('/')) {
    // Only works when the app is served over HTTP(S) (Next proxy route `/api/*`).
    // In packaged/webview contexts (origin may be "null" or a custom scheme),
    // fall back to a direct backend URL.
    if (!/^https?:\/\//i.test(window.location.origin)) {
      return normalizeApiUrl(DEFAULT_API_URL);
    }
    return `${window.location.origin}${normalizeApiUrl(envRaw)}`;
  }
  try {
    const u = new URL(env);
    const sameOrigin = u.origin === window.location.origin;
    if (!sameOrigin) {
      return normalizeApiUrl(DEFAULT_API_URL);
    }
  } catch {
    return normalizeApiUrl(DEFAULT_API_URL);
  }
  return normalizeApiUrl(env);
};

const API_URL = resolveApiUrl();

interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

interface User {
  id: string;
  email: string;
  name: string;
  role: string;
  plan: string;
  account_type: string;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  updated_at: string;
  oab?: string;
  oab_state?: string;
  cpf?: string;
  phone?: string;
  institution_name?: string;
  cnpj?: string;
  position?: string;
  avatar?: string;
  organization_id?: string | null;
}

interface Chat {
  id: string;
  title: string;
  mode?: string;
  context?: any;
  created_at: string;
  updated_at: string;
  is_active?: boolean;
}

interface TokenTelemetry {
  provider: string;
  model: string;
  usage: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
  limits: {
    context_window: number;
    percent_used: number;
  };
}

interface Message {
  id: string;
  chat_id: string;
  role: 'user' | 'assistant';
  content: string;
  attachments?: any[];
  thinking?: string;
  metadata?: {
    mentions?: any[];
    token_usage?: TokenTelemetry;
    [key: string]: any;
  };
  created_at: string;
}

interface AgentTask {
  task_id: string;
  user_id: string;
  prompt: string;
  status: 'queued' | 'running' | 'completed' | 'error' | 'cancelled';
  result: string | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  model: string;
  metadata: Record<string, any>;
}

interface WorkflowResponse {
  id: string;
  user_id: string;
  name: string;
  description: string | null;
  graph_json: { nodes: any[]; edges: any[] };
  is_active: boolean;
  is_template: boolean;
  tags: string[];
  status: string;
  published_version: number | null;
  submitted_at: string | null;
  approved_at: string | null;
  rejection_reason: string | null;
  published_slug: string | null;
  published_config: Record<string, any> | null;
  created_at: string;
  updated_at: string;
}

interface WorkflowRunResponse {
  id: string;
  workflow_id: string;
  status: string;
  input_data: Record<string, any>;
  output_data: Record<string, any> | null;
  current_node: string | null;
  logs: Array<Record<string, any>>;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

interface GenerateDocumentRequest {
  prompt: string;
  context?: any;
  case_id?: string;
  effort_level?: number;
  use_profile?: 'full' | 'basic' | 'none';
  document_type?: string;
  doc_kind?: string;
  doc_subtype?: string;
  model?: string;
  chat_personality?: 'juridico' | 'geral';
  context_documents?: string[];
  attachment_mode?: 'auto' | 'rag_local' | 'prompt_injection';

  // Agent Mode
  use_multi_agent?: boolean;
  model_gpt?: string;
  model_claude?: string;
  strategist_model?: string;
  drafter_models?: string[];
  reviewer_models?: string[];
  reasoning_level?: 'none' | 'minimal' | 'low' | 'medium' | 'high' | 'xhigh';
  temperature?: number;

  web_search?: boolean;
  search_mode?: 'shared' | 'native' | 'hybrid' | 'perplexity';
  perplexity_search_mode?: 'web' | 'academic' | 'sec';
  perplexity_search_type?: 'fast' | 'pro' | 'auto';
  perplexity_search_context_size?: 'low' | 'medium' | 'high';
  perplexity_search_classifier?: boolean;
  perplexity_disable_search?: boolean;
  perplexity_stream_mode?: 'full' | 'concise';
  perplexity_search_domain_filter?: string;
  perplexity_search_language_filter?: string;
  perplexity_search_recency_filter?: 'day' | 'week' | 'month' | 'year';
  perplexity_search_after_date?: string;
  perplexity_search_before_date?: string;
  perplexity_last_updated_after?: string;
  perplexity_last_updated_before?: string;
  perplexity_search_country?: string;
  perplexity_search_region?: string;
  perplexity_search_city?: string;
  perplexity_search_latitude?: string;
  perplexity_search_longitude?: string;
  perplexity_return_images?: boolean;
  perplexity_return_videos?: boolean;
  multi_query?: boolean;
  breadth_first?: boolean;
  research_policy?: 'auto' | 'force';
  dense_research?: boolean;
  deep_research_search_focus?: 'web' | 'academic' | 'sec';
  deep_research_domain_filter?: string;
  deep_research_search_after_date?: string;
  deep_research_search_before_date?: string;
  deep_research_last_updated_after?: string;
  deep_research_last_updated_before?: string;
  deep_research_country?: string;
  deep_research_latitude?: string;
  deep_research_longitude?: string;
  thinking_level?: 'none' | 'minimal' | 'low' | 'medium' | 'high' | 'xhigh';
  min_pages?: number;
  max_pages?: number;
  audit?: boolean;

  // RAG Global & Local
  use_templates?: boolean; // Maps to RAG enabled
  template_filters?: {
    area?: string;
    rito?: string;
    tipoPeca?: string;
    apenasClauseBank?: boolean;
  };

  // Context (v3.4)
  context_files?: string[];
  cache_ttl?: number;

  rag_sources?: string[];
  rag_top_k?: number;
  rag_jurisdictions?: string[];
  rag_source_ids?: string[];

  // Local RAG
  processo_local_path?: string;
  processo_id?: string;
  sistema_processo?: string;
  tenant_id?: string;

  // Formatting
  formatting_options?: {
    includeToc?: boolean;
    includeSummaries?: boolean;
    includeSummaryTable?: boolean;
  };
  citation_style?: 'forense' | 'abnt' | 'hibrido';

  // Other
  thesis?: string;
  prompt_extra?: string;
  adaptive_routing?: boolean;
  crag_gate?: boolean;
  crag_min_best_score?: number;
  crag_min_avg_score?: number;
  hyde_enabled?: boolean;
  graph_rag_enabled?: boolean;
  argument_graph_enabled?: boolean;
  graph_hops?: number;
  rag_scope?: 'case_only' | 'case_and_global' | 'global_only';
  rag_selected_groups?: string[];
  rag_allow_private?: boolean;
  rag_allow_groups?: boolean;
  include_signature?: boolean;
  language?: string;
  tone?: string;
  template_id?: string;
  template_document_id?: string;
  variables?: Record<string, any>;
  hil_outline_enabled?: boolean;
  hil_target_sections?: string[];
  outline_override?: string[];
  audit_mode?: 'sei_only' | 'research';
  quality_profile?: 'rapido' | 'padrao' | 'rigoroso' | 'auditoria';
  target_section_score?: number;
  target_final_score?: number;
  max_rounds?: number;
  style_refine_max_rounds?: number;
  strict_document_gate?: boolean;
  hil_section_policy?: 'none' | 'optional' | 'required';
  hil_final_required?: boolean;
  auto_approve_hil?: boolean;
  recursion_limit?: number;
  max_research_verifier_attempts?: number;
  max_rag_retries?: number;
  rag_retry_expand_scope?: boolean;
  document_checklist_hint?: Array<{
    id?: string;
    label: string;
    critical: boolean;
  }>;

  // Poe-like billing
  budget_override_points?: number;
}

interface GenerateDocumentResponse {
  content: string;
  reviews?: any[];
  consensus?: boolean;
  conflicts?: any[];
  total_tokens?: number;
  total_cost?: number;
  processing_time?: number;
  metadata?: any;
}

interface OutlineRequest {
  prompt: string;
  document_type?: string;
  doc_kind?: string;
  doc_subtype?: string;
  thesis?: string;
  model?: string;
  min_pages?: number;
  max_pages?: number;
}

interface OutlineResponse {
  outline: string[];
  model?: string;
}

export interface GenerateSkillRequestPayload {
  directive: string;
  name?: string;
  description?: string;
  version?: string;
  audience?: 'beginner' | 'advanced' | 'both';
  triggers?: string[];
  tools_required?: string[];
  tools_denied?: string[];
  subagent_model?: string;
  citation_style?: string;
  output_format?: 'chat' | 'document' | 'checklist' | 'json';
  prefer_workflow?: boolean;
  prefer_agent?: boolean;
  guardrails?: string[];
  examples?: Array<string | { prompt: string; expected_behavior: string }>;
  negative_examples?: string[];
  tools_allowed?: string[];
}

export interface GenerateSkillResponsePayload {
  draft_id: string;
  status: string;
  version: number;
  schema_version: string;
  quality_score: number;
  warnings: string[];
  suggested_tests?: string[];
  skill_markdown: string;
}

export interface ValidateSkillRequestPayload {
  draft_id?: string;
  skill_markdown?: string;
  test_prompts?: {
    positive: string[];
    negative: string[];
  };
  strict?: boolean;
}

export interface ValidateSkillResponsePayload {
  valid: boolean;
  errors: string[];
  warnings: string[];
  quality_score?: number;
  tpr?: number;
  fpr?: number;
  security_violations?: string[];
  improvements?: string[];
  routing: Record<string, number>;
  parsed?: Record<string, unknown> | null;
}

export interface PublishSkillRequestPayload {
  draft_id?: string;
  skill_markdown?: string;
  activate?: boolean;
  visibility?: 'personal' | 'organization' | 'public';
  if_match_version?: number;
}

export interface PublishSkillResponsePayload {
  skill_id: string;
  status: string;
  version: number;
  indexed_triggers: number;
}

export interface SkillLibraryItem {
  id: string;
  name: string;
  description?: string | null;
  tags: string[];
  updated_at?: string;
}

class ApiClient {
  private axios: AxiosInstance;
  private baseUrl: string;
  private isRefreshing = false;
  private refreshSubscribers: ((token: string) => void)[] = [];

  constructor() {
    this.baseUrl = API_URL;
    this.axios = axios.create({
      baseURL: API_URL,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Interceptor de requisições - adiciona token
    this.axios.interceptors.request.use(
      (config: InternalAxiosRequestConfig) => {
        const token = this.getAccessToken();
        // Do not override an explicit Authorization header (e.g. refresh flow uses refresh_token).
        const hadAuthHeader = Boolean(config.headers && (config.headers as any).Authorization);
        if (token && config.headers && !hadAuthHeader) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Interceptor de respostas - trata erros e refresh de token
    this.axios.interceptors.response.use(
      (response) => {
        return response;
      },
      async (error: AxiosError) => {
        const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

        // Se erro 401 e não é retry, tenta refresh
        if (error.response?.status === 401 && !originalRequest._retry) {
          if (this.isRefreshing) {
            // Aguarda refresh em andamento
            return new Promise((resolve) => {
              this.refreshSubscribers.push((token: string) => {
                if (originalRequest.headers) {
                  originalRequest.headers.Authorization = `Bearer ${token}`;
                }
                resolve(this.axios(originalRequest));
              });
            });
          }

          originalRequest._retry = true;
          this.isRefreshing = true;

          try {
            const newToken = await this.refreshAccessToken();
            this.isRefreshing = false;
            this.onRefreshed(newToken);
            this.refreshSubscribers = [];

            if (originalRequest.headers) {
              originalRequest.headers.Authorization = `Bearer ${newToken}`;
            }
            return this.axios(originalRequest);
          } catch (refreshError) {
            this.isRefreshing = false;
            this.refreshSubscribers = [];
            this.clearTokens();

            // Redirecionar para login
            if (typeof window !== 'undefined') {
              window.location.href = '/login';
            }
            return Promise.reject(refreshError);
          }
        }

        return Promise.reject(error);
      }
    );
  }

  private onRefreshed(token: string) {
    this.refreshSubscribers.forEach((callback) => callback(token));
  }

  private getAccessToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('access_token');
  }

  private getRefreshToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('refresh_token');
  }

  private setAccessToken(token: string): void {
    if (typeof window !== 'undefined') {
      localStorage.setItem('access_token', token);
    }
  }

  private setRefreshToken(token: string): void {
    if (typeof window !== 'undefined') {
      localStorage.setItem('refresh_token', token);
    }
  }

  clearTokens(): void {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user');
    }
  }

  /**
   * Generic request method for any API endpoint.
   * Usage: apiClient.request('/marketplace?page=1') or apiClient.request('/marketplace/123/install', { method: 'POST' })
   */
  async request(path: string, options?: { method?: string; body?: unknown }): Promise<any> {
    const method = (options?.method || 'GET').toUpperCase();
    const config: Record<string, any> = {};
    if (options?.body) {
      config.data = options.body;
      // When sending FormData, let the browser set Content-Type with boundary
      if (typeof FormData !== 'undefined' && options.body instanceof FormData) {
        config.headers = { 'Content-Type': undefined };
      }
    }
    const response = await this.axios.request({
      url: path,
      method,
      ...config,
    });
    return response.data;
  }

  private async extractFetchErrorMessage(response: Response): Promise<string> {
    try {
      const contentType = response.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        const data = await response.json();
        if (data && typeof data.detail === 'string') {
          return data.detail;
        }
        if (data && typeof data.error === 'string') {
          return data.error;
        }
      } else {
        const text = await response.text();
        if (text) return text;
      }
    } catch {
      // ignore parsing errors
    }
    return response.statusText || 'Erro inesperado';
  }

  private getDirectApiUrl(): string | null {
    const envRaw = (process.env.NEXT_PUBLIC_API_URL || '').trim();
    const env = coerceAbsoluteUrl(envRaw);
    if (envRaw) {
      try {
        // Only allow absolute URLs for direct fallback.
        // Relative values like "/api" should defer to localhost in dev.
        new URL(env);
        return normalizeApiUrl(env);
      } catch {
        // Ignore relative env for direct fallback.
      }
    }
    if (process.env.NODE_ENV === 'development') {
      return 'http://127.0.0.1:8000/api';
    }
    return null;
  }

  private isLikelyHtmlNotFound(response: Response, detail: string): boolean {
    if (response.status !== 404) return false;
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('text/html')) return true;
    return /<!doctype html|next-error|this page could not be found/i.test(detail || '');
  }

  private isLikelyProxyFailure(response: Response, detail: string): boolean {
    if (response.status < 500) return false;
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('text/html')) return true;
    return /next-error|__next_data__|this page could not be found/i.test(detail || '');
  }

  private async fetchStreamingWithFallback(
    path: string,
    buildBody: () => BodyInit,
    headers: HeadersInit
  ): Promise<Response> {
    const directBase = this.getDirectApiUrl();
    const primaryUrl = `${API_URL}${path}`;

    // Prefer direct connection for streaming to avoid proxy buffering
    if (directBase && directBase !== API_URL) {
      try {
        const directUrl = `${directBase}${path}`;
        const directResponse = await fetch(directUrl, {
          method: 'POST',
          headers,
          body: buildBody(),
        });
        if (directResponse.ok) return directResponse;
        if (process.env.NODE_ENV === 'development') console.warn(`[Streaming] Direct connection failed with ${directResponse.status}, falling back to proxy`);
      } catch (err) {
        if (process.env.NODE_ENV === 'development') console.warn('[Streaming] Direct connection failed, falling back to proxy:', err);
      }
    }

    const primaryResponse = await fetch(primaryUrl, {
      method: 'POST',
      headers,
      body: buildBody(),
    });

    if (primaryResponse.ok) return primaryResponse;

    const detail = await this.extractFetchErrorMessage(primaryResponse);
    if (!this.isLikelyHtmlNotFound(primaryResponse, detail) && !this.isLikelyProxyFailure(primaryResponse, detail)) {
      throw new Error(`HTTP ${primaryResponse.status}: ${detail}`);
    }

    // If directBase was already tried and failed, don't try again unless logic above was skipped
    // But simplified: effectively we tried Direct -> Primary.
    // If Primary fails, we throw. 
    // The original logic tried Primary -> Direct. 
    // If we want to be exhaustive: Direct -> Primary -> Direct (Retry?) No, that's silly.

    // Original fallback logic was to handle "API_URL (Proxy) is down/bad, try Direct".
    // We already tried Direct. So just throw.

    // However, strictly adhering to "Fallback" name, we might want to ensure we hit Direct if we skipped it?
    // But we prioritize Direct now.

    throw new Error(`HTTP ${primaryResponse.status}: ${detail}`);
  }

  private async fetchStreamingGetWithFallback(
    path: string,
    headers: HeadersInit
  ): Promise<Response> {
    const directBase = this.getDirectApiUrl();
    const primaryUrl = `${API_URL}${path}`;

    // Prefer direct connection for streaming to avoid proxy buffering
    if (directBase && directBase !== API_URL) {
      try {
        const directUrl = `${directBase}${path}`;
        const directResponse = await fetch(directUrl, {
          method: 'GET',
          headers,
        });
        if (directResponse.ok) return directResponse;
        if (process.env.NODE_ENV === 'development') console.warn(`[Streaming] Direct connection failed with ${directResponse.status}, falling back to proxy`);
      } catch (err) {
        if (process.env.NODE_ENV === 'development') console.warn('[Streaming] Direct connection failed, falling back to proxy:', err);
      }
    }

    const primaryResponse = await fetch(primaryUrl, {
      method: 'GET',
      headers,
    });

    if (primaryResponse.ok) return primaryResponse;

    const detail = await this.extractFetchErrorMessage(primaryResponse);
    if (!this.isLikelyHtmlNotFound(primaryResponse, detail) && !this.isLikelyProxyFailure(primaryResponse, detail)) {
      throw new Error(`HTTP ${primaryResponse.status}: ${detail}`);
    }

    // Original fallback logic was to handle "API_URL (Proxy) is down/bad, try Direct".
    // We already tried Direct. So just throw.
    throw new Error(`HTTP ${primaryResponse.status}: ${detail}`);
  }

  private async postFormDataWithFallback(
    path: string,
    buildFormData: () => FormData,
    headers: HeadersInit
  ): Promise<Response> {
    const primaryUrl = `${API_URL}${path}`;
    const primaryResponse = await fetch(primaryUrl, {
      method: 'POST',
      headers,
      body: buildFormData(),
    });

    if (primaryResponse.ok) return primaryResponse;

    const detail = await this.extractFetchErrorMessage(primaryResponse);
    if (!this.isLikelyHtmlNotFound(primaryResponse, detail) && !this.isLikelyProxyFailure(primaryResponse, detail)) {
      throw new Error(`HTTP ${primaryResponse.status}: ${detail}`);
    }

    const directBase = this.getDirectApiUrl();
    if (!directBase || directBase === API_URL) {
      throw new Error(`HTTP ${primaryResponse.status}: ${detail}`);
    }

    const fallbackUrl = `${directBase}${path}`;
    const fallbackResponse = await fetch(fallbackUrl, {
      method: 'POST',
      headers,
      body: buildFormData(),
    });

    if (!fallbackResponse.ok) {
      const fallbackDetail = await this.extractFetchErrorMessage(fallbackResponse);
      throw new Error(`HTTP ${fallbackResponse.status}: ${fallbackDetail}`);
    }

    return fallbackResponse;
  }

  // ============= AUTH =============

  async register(data: {
    name: string;
    email: string;
    password: string;
    account_type: string;
    [key: string]: any;
  }): Promise<AuthResponse> {
    const response = await this.axios.post<AuthResponse>('/auth/register', data);
    const { access_token, refresh_token, user } = response.data;

    this.setAccessToken(access_token);
    this.setRefreshToken(refresh_token);

    return response.data;
  }

  async login(email: string, password: string): Promise<AuthResponse> {
    const response = await this.axios.post<AuthResponse>('/auth/login', { email, password });
    const { access_token, refresh_token } = response.data;

    this.setAccessToken(access_token);
    this.setRefreshToken(refresh_token);

    return response.data;
  }

  async loginTest(): Promise<AuthResponse> {
    if (process.env.NODE_ENV === 'development') {
      console.log('[API Client] Login Test - Base URL:', this.axios.defaults.baseURL);
    }

    // Retry logic for when API is still starting up
    const maxRetries = 3;
    const retryDelay = 2000; // 2 seconds

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const response = await this.axios.post<AuthResponse>('/auth/login-test');
        if (process.env.NODE_ENV === 'development') {
          console.log('[API Client] Login Test - Success:', response.status);
        }
        const { access_token, refresh_token } = response.data;

        this.setAccessToken(access_token);
        this.setRefreshToken(refresh_token);

        return response.data;
      } catch (error: any) {
        const isNetworkError = !error.response || error.code === 'ERR_NETWORK' || error.message === 'Network Error';

        if (process.env.NODE_ENV === 'development') {
          console.error(`[API Client] Login Test - Attempt ${attempt}/${maxRetries} Error:`, error.response?.status || error.message);
        }

        // Retry on network errors (API not ready yet)
        if (isNetworkError && attempt < maxRetries) {
          console.log(`[API Client] API not ready, retrying in ${retryDelay/1000}s... (${attempt}/${maxRetries})`);
          await new Promise(resolve => setTimeout(resolve, retryDelay));
          continue;
        }

        if (process.env.NODE_ENV === 'development') {
          console.error('[API Client] Login Test - Full URL:', this.axios.defaults.baseURL + '/auth/login-test');
        }
        throw error;
      }
    }

    throw new Error('API não disponível após várias tentativas');
  }

  async logout(): Promise<void> {
    try {
      await this.axios.post('/auth/logout');
    } catch (error) {
      if (process.env.NODE_ENV === 'development') {
        console.error('Logout error:', error);
      }
    } finally {
      this.clearTokens();
    }
  }

  async refreshAccessToken(): Promise<string> {
    const refreshToken = this.getRefreshToken();
    if (!refreshToken) {
      throw new Error('No refresh token available');
    }

    const response = await this.axios.post<AuthResponse>(
      '/auth/refresh',
      {},
      {
        headers: { Authorization: `Bearer ${refreshToken}` },
      }
    );

    const { access_token, refresh_token } = response.data;
    this.setAccessToken(access_token);
    this.setRefreshToken(refresh_token);

    return access_token;
  }

  async getProfile(): Promise<User> {
    const response = await this.axios.get<User>('/auth/me');
    return response.data;
  }

  async loginAsGuest(shareToken: string, displayName?: string): Promise<any> {
    const response = await this.axios.post(`/auth/guest/from-share/${shareToken}`, {
      display_name: displayName || undefined,
    });
    const { access_token } = response.data;
    this.setAccessToken(access_token);
    return response.data;
  }

  async createGuestSession(displayName?: string): Promise<any> {
    const response = await this.axios.post('/auth/guest', {
      display_name: displayName || undefined,
    });
    const { access_token } = response.data;
    this.setAccessToken(access_token);
    return response.data;
  }

  async getGuestInfo(): Promise<any> {
    const response = await this.axios.get('/auth/guest/me');
    return response.data;
  }

  async getPreferences(): Promise<any> {
    const response = await this.axios.get('/users/preferences');
    return response.data;
  }

  async updatePreferences(preferences: Record<string, any>, replace = false): Promise<any> {
    const response = await this.axios.put('/users/preferences', { preferences, replace });
    return response.data;
  }

  // ============= CHATS =============

  async getChats(skip = 0, limit = 20): Promise<{ chats: Chat[] }> {
    const response = await this.axios.get<Chat[]>('/chats/', {
      params: { skip, limit },
    });
    return { chats: response.data };
  }

  async getChat(chatId: string): Promise<Chat> {
    const response = await this.axios.get<Chat>(`/chats/${chatId}`);
    return response.data;
  }

  async createChat(data: { title?: string; mode?: string; context?: any }): Promise<Chat> {
    const response = await this.axios.post<Chat>('/chats/', {
      title: data.title || 'Nova Conversa',
      mode: data.mode || 'MINUTA',
      context: data.context || {},
    });
    return response.data;
  }

  async duplicateChat(chatId: string, title?: string): Promise<Chat> {
    const response = await this.axios.post<Chat>(`/chats/${chatId}/duplicate`, {
      title,
    });
    return response.data;
  }

  async createMultiChatThread(title?: string): Promise<Chat> {
    const response = await this.axios.post<Chat>('/multi-chat/threads', {
      title: title || 'Multi-Model Chat',
    });
    return response.data;
  }

  async consolidateMultiChatTurn(
    threadId: string,
    data: { message: string; candidates: { model: string; text: string }[]; mode?: 'merge' | 'debate' }
  ): Promise<{ content: string }> {
    const response = await this.axios.post<{ content: string }>(`/multi-chat/threads/${threadId}/consolidate`, data);
    return response.data;
  }

  /**
   * v5.4: Edit document via agent committee
   * 
   * Sends an edit command and document context to the committee.
   * GPT and Claude propose edits, Gemini Judge consolidates.
   * 
   * @returns SSE stream with agent responses and final edited text
   */
  async editDocumentWithCommittee(
    chatId: string, // Renamed from threadId to clarify it's a Chat ID
    data: {
      message: string;
      document: string;
      selection?: string;
      selection_start?: number;
      selection_end?: number;
      selection_context_before?: string;
      selection_context_after?: string;
      models?: string[];
      use_debate?: boolean;
    },
    onAgentResponse: (agent: string, text: string) => void,
    onComplete: (original: string, edited: string, agents: string[]) => void,
    onError: (error: string) => void
  ): Promise<void> {
    const token = this.getAccessToken();

    try {
      const response = await fetch(`${API_URL}/chats/${chatId}/edit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          Accept: 'text/event-stream',
        },
        body: JSON.stringify(data),
      });

      if (!response.ok) {
        onError(`HTTP ${response.status}: ${response.statusText}`);
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        onError('Response body is not readable');
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data:')) {
            try {
              const event = JSON.parse(line.slice(5).trim());

              if (event.type === 'agent_response') {
                onAgentResponse(event.agent, event.text);
              } else if (event.type === 'edit_complete') {
                onComplete(event.original, event.edited, event.agents_used);
              } else if (event.type === 'error') {
                onError(event.error);
              }
            } catch (e) {
              if (process.env.NODE_ENV === 'development') console.error('Failed to parse SSE event:', line);
            }
          }
        }
      }
    } catch (error: any) {
      onError(error.message || 'Unknown error');
    }
  }

  /**
   * Performs a native fetch with JWT authentication.
   * Used for SSE streaming requests that can't use axios.
   */
  async fetchWithAuth(endpoint: string, options: RequestInit = {}): Promise<Response> {
    const token = this.getAccessToken();
    const url = `${API_URL}${endpoint}`;

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    };

    if (token) {
      (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
    }

    const res = await fetch(url, {
      ...options,
      headers,
    });
    return res;
  }

  async deleteChat(chatId: string): Promise<void> {
    await this.axios.delete(`/chats/${chatId}`);
  }

  async getMessages(chatId: string, skip = 0, limit = 50): Promise<Message[]> {
    const response = await this.axios.get<Message[]>(`/chats/${chatId}/messages`, {
      params: { skip, limit },
    });
    return response.data;
  }

  async sendMessage(
    chatId: string,
    content: string,
    attachments?: any[],
    chat_personality?: 'juridico' | 'geral'
  ): Promise<Message> {
    const response = await this.axios.post<Message>(`/chats/${chatId}/messages`, {
      content,
      attachments,
      chat_personality,
    });
    return response.data;
  }

  async generateDocument(
    chatId: string,
    request: GenerateDocumentRequest
  ): Promise<GenerateDocumentResponse> {
    const response = await this.axios.post<GenerateDocumentResponse>(
      `/chats/${chatId}/generate`,
      request
    );
    return response.data;
  }

  async generateOutline(
    chatId: string,
    request: OutlineRequest
  ): Promise<OutlineResponse> {
    const response = await this.axios.post<OutlineResponse>(
      `/chats/${chatId}/outline`,
      request
    );
    return response.data;
  }

  // ============= DOCUMENTS =============

  async getDocuments(skip = 0, limit = 20, search?: string): Promise<{ documents: any[]; total: number }> {
    const params: any = { skip, limit };
    if (search) params.search = search;

    const response = await this.axios.get('/documents', {
      params,
    });
    return response.data;
  }

  async uploadDocument(file: File, metadata?: any): Promise<any> {
    const token = this.getAccessToken();
    const response = await this.postFormDataWithFallback(
      '/documents/upload',
      () => {
        const data = new FormData();
        data.append('file', file);
        if (metadata) {
          data.append('metadata', JSON.stringify(metadata));
        }
        return data;
      },
      {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      }
    );
    return response.json();
  }

  async getDocument(documentId: string): Promise<any> {
    const response = await this.axios.get(`/documents/${documentId}`);
    return response.data;
  }

  async deleteDocument(documentId: string): Promise<void> {
    await this.axios.delete(`/documents/${documentId}`);
  }

  async createDocumentFromText(data: { title: string; content: string; tags?: string; folder_id?: string }): Promise<any> {
    const token = this.getAccessToken();
    try {
      const response = await this.postFormDataWithFallback(
        '/documents/from-text',
        () => {
          const formData = new FormData();
          formData.append('title', data.title);
          formData.append('content', data.content);
          if (data.tags) formData.append('tags', data.tags);
          if (data.folder_id) formData.append('folder_id', data.folder_id);
          return formData;
        },
        {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        }
      );
      return response.json();
    } catch (error: any) {
      const message = String(error?.message || '');
      const canFallback = typeof window !== 'undefined' && typeof File !== 'undefined';
      const shouldFallbackToUpload = /expected pattern|invalid url|failed to construct 'url'/i.test(message);
      if (canFallback && shouldFallbackToUpload) {
        const safeName = String(data.title || 'documento')
          .replace(/[\\/:*?"<>|]+/g, '_')
          .slice(0, 80) || 'documento';
        const file = new File([data.content], `${safeName}.txt`, { type: 'text/plain' });
        const tags = (data.tags || '')
          .split(',')
          .map((tag) => tag.trim())
          .filter(Boolean);
        return this.uploadDocument(file, {
          tags,
          folder_id: data.folder_id,
          source: 'from_text_url_fallback',
        });
      }
      const status = error?.response?.status;
      if (canFallback && (status === 413 || (status >= 500 && status < 600))) {
        const safeName = String(data.title || 'documento')
          .replace(/[\\/:*?"<>|]+/g, '_')
          .slice(0, 80) || 'documento';
        const file = new File([data.content], `${safeName}.txt`, { type: 'text/plain' });
        const tags = (data.tags || '')
          .split(',')
          .map((tag) => tag.trim())
          .filter(Boolean);
        return this.uploadDocument(file, {
          tags,
          folder_id: data.folder_id,
          source: 'from_text_fallback',
        });
      }
      throw error;
    }
  }

  async createDocumentFromUrl(data: { url: string; tags?: string; folder_id?: string }): Promise<any> {
    const formData = new FormData();
    formData.append('url', data.url);
    if (data.tags) formData.append('tags', data.tags);
    if (data.folder_id) formData.append('folder_id', data.folder_id);

    const response = await this.axios.post('/documents/from-url', formData, {
      headers: { 'Content-Type': undefined },
    });
    return response.data;
  }

  async processDocument(documentId: string, options?: any): Promise<any> {
    const response = await this.axios.post(`/documents/${documentId}/process`, options);
    return response.data;
  }

  async getDocumentSummary(documentId: string): Promise<{ summary: string; document_id: string }> {
    const response = await this.axios.post(`/documents/${documentId}/summary`);
    return response.data;
  }

  async applyDocumentOcr(documentId: string): Promise<any> {
    const response = await this.axios.post(`/documents/${documentId}/ocr`);
    return response.data;
  }

  async getUserSignature(): Promise<any> {
    const response = await this.axios.get('/documents/signature');
    return response.data;
  }

  async updateUserSignature(data: { signature_image?: string; signature_text?: string }): Promise<any> {
    const response = await this.axios.put('/documents/signature', data);
    return response.data;
  }

  async shareDocument(documentId: string, expires_in_days = 7, access_level = 'VIEW'): Promise<any> {
    const response = await this.axios.post(`/documents/${documentId}/share`, null, {
      params: { expires_in_days, access_level }
    });
    return response.data;
  }

  async unshareDocument(documentId: string): Promise<any> {
    const response = await this.axios.delete(`/documents/${documentId}/share`);
    return response.data;
  }

  // ============= LIBRARY =============

  async getLibraryItems(
    skip = 0,
    limit = 20,
    search?: string,
    item_type?: string
  ): Promise<{ items: any[]; total: number }> {
    const params: any = { skip, limit };
    if (search) params.search = search;
    if (item_type) params.item_type = item_type;

    const response = await this.axios.get('/library/items', {
      params,
    });
    return response.data;
  }

  async generateSkill(data: GenerateSkillRequestPayload): Promise<GenerateSkillResponsePayload> {
    const response = await this.axios.post<GenerateSkillResponsePayload>('/skills/generate', data);
    return response.data;
  }

  async validateSkill(data: ValidateSkillRequestPayload): Promise<ValidateSkillResponsePayload> {
    const response = await this.axios.post<ValidateSkillResponsePayload>('/skills/validate', data);
    return response.data;
  }

  async publishSkill(data: PublishSkillRequestPayload): Promise<PublishSkillResponsePayload> {
    const response = await this.axios.post<PublishSkillResponsePayload>('/skills/publish', data);
    return response.data;
  }

  async listSkillsFromLibrary(): Promise<SkillLibraryItem[]> {
    const response = await this.axios.get<{ items: SkillLibraryItem[]; total: number }>('/library/items');
    const items = Array.isArray(response.data?.items) ? response.data.items : [];
    return items.filter((item) => Array.isArray(item.tags) && item.tags.includes('skill'));
  }




  // ============= CHAT WITH DOCS =============
  async chatWithDocs(data: {
    case_id?: string;
    message: string;
    conversation_history?: any[];
    document_ids?: string[];
    context_files?: string[];
    custom_prompt?: string;
    rag_config?: Record<string, any>;
  }): Promise<any> {
    const response = await this.axios.post('/chat/message', data);
    return response.data;
  }

  async exportChatToCase(conversationId: string): Promise<any> {
    const response = await this.axios.post('/chat/export-to-case', null, {
      params: { conversation_id: conversationId }
    });
    return response.data;
  }

  // ============= CASES =============

  async getCases(skip = 0, limit = 100): Promise<any> {
    const response = await this.axios.get('/cases', {
      params: { skip, limit },
    });
    return response.data;
  }

  async createCase(data: any): Promise<any> {
    const response = await this.axios.post('/cases', data);
    return response.data;
  }

  async getCase(caseId: string): Promise<any> {
    const response = await this.axios.get(`/cases/${caseId}`);
    return response.data;
  }

  async updateCase(caseId: string, data: any): Promise<any> {
    const response = await this.axios.put(`/cases/${caseId}`, data);
    return response.data;
  }

  async deleteCase(caseId: string): Promise<void> {
    await this.axios.delete(`/cases/${caseId}`);
  }

  // ============= CASE DOCUMENTS =============

  /**
   * Get all documents attached to a case
   */
  async getCaseDocuments(caseId: string): Promise<{
    documents: Array<{
      id: string;
      name: string;
      original_name: string;
      type: string;
      status: string;
      size: number;
      url: string;
      case_id: string;
      rag_ingested: boolean;
      rag_ingested_at: string | null;
      rag_scope: string | null;
      graph_ingested: boolean;
      graph_ingested_at: string | null;
      created_at: string;
      updated_at: string;
    }>;
    total: number;
    case_id: string;
  }> {
    const response = await this.axios.get(`/cases/${caseId}/documents`);
    return response.data;
  }

  /**
   * Upload a document directly to a case with auto RAG/Graph ingestion
   */
  async uploadDocumentToCase(
    caseId: string,
    file: File,
    options?: {
      auto_ingest_rag?: boolean;
      auto_ingest_graph?: boolean;
    }
  ): Promise<{
    success: boolean;
    document_id: string;
    case_id: string;
    rag_ingestion_triggered: boolean;
    graph_ingestion_triggered: boolean;
    message: string;
  }> {
    const token = this.getAccessToken();
    const formData = new FormData();
    formData.append('file', file);

    const params = new URLSearchParams();
    if (options?.auto_ingest_rag !== undefined) {
      params.append('auto_ingest_rag', String(options.auto_ingest_rag));
    }
    if (options?.auto_ingest_graph !== undefined) {
      params.append('auto_ingest_graph', String(options.auto_ingest_graph));
    }

    const url = `/cases/${caseId}/documents/upload${params.toString() ? '?' + params.toString() : ''}`;

    const response = await this.postFormDataWithFallback(
      url,
      () => {
        const data = new FormData();
        data.append('file', file);
        return data;
      },
      {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      }
    );
    return response.json();
  }

  /**
   * Attach an existing document to a case with optional RAG/Graph ingestion
   */
  async attachDocumentToCase(
    caseId: string,
    documentId: string,
    options?: {
      auto_ingest_rag?: boolean;
      auto_ingest_graph?: boolean;
    }
  ): Promise<{
    success: boolean;
    document_id: string;
    case_id: string;
    rag_ingestion_triggered: boolean;
    graph_ingestion_triggered: boolean;
    message: string;
  }> {
    const response = await this.axios.post(
      `/cases/${caseId}/documents/${documentId}/attach`,
      options || { auto_ingest_rag: true, auto_ingest_graph: true }
    );
    return response.data;
  }

  /**
   * Detach a document from a case (does not delete the document)
   */
  async detachDocumentFromCase(
    caseId: string,
    documentId: string
  ): Promise<{
    success: boolean;
    message: string;
  }> {
    const response = await this.axios.delete(`/cases/${caseId}/documents/${documentId}/detach`);
    return response.data;
  }

  // ============= MCP (Connectors) =============

  async getMcpServers(): Promise<{
    servers: Array<{ label: string; url: string; allowed_tools?: string[] | null }>;
  }> {
    const response = await this.axios.get('/mcp/servers');
    return response.data;
  }

  // ── User MCP Servers ──────────────────────────────────

  async getUserMcpServers(): Promise<{ servers: any[] }> {
    const response = await this.axios.get('/mcp/user-servers');
    return response.data;
  }

  async addUserMcpServer(data: {
    label: string;
    url: string;
    allowed_tools?: string[];
    auth_type?: string | null;
    auth_token?: string | null;
    auth_header_name?: string | null;
  }): Promise<{ status: string; label: string }> {
    const response = await this.axios.post('/mcp/user-servers', data);
    return response.data;
  }

  async removeUserMcpServer(label: string): Promise<{ status: string }> {
    const response = await this.axios.delete(`/mcp/user-servers/${label}`);
    return response.data;
  }

  async testUserMcpServer(label: string): Promise<{
    status: string;
    tools_count?: number;
    tools?: string[];
    message?: string;
  }> {
    const response = await this.axios.post(`/mcp/user-servers/${label}/test`);
    return response.data;
  }


  async getLibrarians(skip = 0, limit = 50): Promise<any> {
    const response = await this.axios.get('/library/librarians', {
      params: { skip, limit },
    });
    return response.data;
  }

  async createLibraryItem(data: any): Promise<any> {
    const response = await this.axios.post('/library/items', data);
    return response.data;
  }

  async deleteLibraryItem(itemId: string): Promise<void> {
    await this.axios.delete(`/library/${itemId}`);
  }

  // ============= TEMPLATES =============

  async getTemplates(skip = 0, limit = 20): Promise<any> {
    const response = await this.axios.get('/templates', {
      params: { skip, limit },
    });
    return response.data;
  }

  async createTemplate(data: any): Promise<any> {
    const response = await this.axios.post('/templates', data);
    return response.data;
  }

  async deleteTemplate(templateId: string): Promise<void> {
    await this.axios.delete(`/templates/${templateId}`);
  }

  async getTemplate(templateId: string): Promise<any> {
    const response = await this.axios.get(`/templates/${templateId}`);
    return response.data;
  }

  async updateTemplate(templateId: string, data: any): Promise<any> {
    const response = await this.axios.put(`/templates/${templateId}`, data);
    return response.data;
  }

  async duplicateTemplate(templateId: string, name?: string): Promise<any> {
    const response = await this.axios.post(`/templates/${templateId}/duplicate`, {
      name,
    });
    return response.data;
  }

  async getTemplateCatalogTypes(): Promise<any> {
    const response = await this.axios.get('/templates/catalog/types');
    return response.data;
  }

  async getTemplateCatalogDefaults(docKind: string, docSubtype: string): Promise<any> {
    const response = await this.axios.get(`/templates/catalog/defaults/${docKind}/${docSubtype}`);
    return response.data;
  }

  async validateTemplateCatalog(template: any): Promise<any> {
    const response = await this.axios.post('/templates/catalog/validate', { template });
    return response.data;
  }

  async parseTemplateDescription(data: {
    description: string;
    doc_kind?: string;
    doc_subtype?: string;
    model_id?: string;
  }): Promise<any> {
    const response = await this.axios.post('/templates/catalog/parse', data);
    return response.data;
  }

  // ============= CLAUSES =============

  async getClauses(skip = 0, limit = 20): Promise<any> {
    const response = await this.axios.get('/clauses', {
      params: { skip, limit },
    });
    return response.data;
  }

  async createClause(data: any): Promise<any> {
    const response = await this.axios.post('/clauses', data);
    return response.data;
  }

  async deleteClause(clauseId: string): Promise<void> {
    await this.axios.delete(`/clauses/${clauseId}`);
  }

  async indexRagModels(
    files: File[],
    options: {
      tipo_peca?: string;
      area?: string;
      rito?: string;
      tribunal_destino?: string;
      tese?: string;
      resultado?: string;
      versao?: string;
      aprovado?: boolean;
      chunk?: boolean;
      paths?: string[];
    } = {}
  ): Promise<any> {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));
    if (options.tipo_peca) formData.append('tipo_peca', options.tipo_peca);
    if (options.area) formData.append('area', options.area);
    if (options.rito) formData.append('rito', options.rito);
    if (options.tribunal_destino) formData.append('tribunal_destino', options.tribunal_destino);
    if (options.tese) formData.append('tese', options.tese);
    if (options.resultado) formData.append('resultado', options.resultado);
    if (options.versao) formData.append('versao', options.versao);
    if (typeof options.aprovado === 'boolean') formData.append('aprovado', String(options.aprovado));
    if (typeof options.chunk === 'boolean') formData.append('chunk', String(options.chunk));
    if (options.paths?.length) formData.append('paths', JSON.stringify(options.paths));

    const response = await this.axios.post('/rag/index', formData, {
      headers: { 'Content-Type': undefined },
    });
    return response.data;
  }

  async extractTemplateVariables(file: File): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    const response = await this.axios.post('/templates/extract-variables', formData, {
      headers: { 'Content-Type': undefined },
    });
    return response.data;
  }

  async applyTemplate(file: File, variables: Record<string, any>): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('variables', JSON.stringify(variables));
    const response = await this.axios.post('/templates/apply', formData, {
      headers: { 'Content-Type': undefined },
    });
    return response.data;
  }

  // ============= KNOWLEDGE (Legislação / Jurisprudência / Web) =============

  async searchLegislation(query: string): Promise<any> {
    const response = await this.axios.get('/knowledge/legislation/search', { params: { query } });
    return response.data;
  }

  async searchJurisprudence(query: string, court?: string): Promise<any> {
    const response = await this.axios.get('/knowledge/jurisprudence/search', {
      params: { query, court },
    });
    return response.data;
  }

  async searchWeb(
    query: string,
    options?: {
      limit?: number;
      multi_query?: boolean;
      use_cache?: boolean;
      country?: string;
      search_region?: string;
      search_city?: string;
      search_latitude?: string | number;
      search_longitude?: string | number;
      domain_filter?: string[];
      language_filter?: string[];
      recency_filter?: 'day' | 'week' | 'month' | 'year' | string;
      search_mode?: 'web' | 'academic' | 'sec';
      search_after_date?: string;
      search_before_date?: string;
      last_updated_after?: string;
      last_updated_before?: string;
      max_tokens?: number;
      max_tokens_per_page?: number;
      return_images?: boolean;
      return_videos?: boolean;
      return_snippets?: boolean;
    }
  ): Promise<any> {
    const params = new URLSearchParams();
    params.set('query', query);

    const append = (key: string, value: unknown) => {
      if (value === undefined || value === null) return;
      if (Array.isArray(value)) {
        value
          .map((item) => (item === undefined || item === null ? '' : String(item).trim()))
          .filter(Boolean)
          .forEach((item) => params.append(key, item));
        return;
      }
      const str = String(value).trim();
      if (!str) return;
      params.set(key, str);
    };

    Object.entries(options || {}).forEach(([key, value]) => append(key, value));
    const response = await this.axios.get(`/knowledge/web/search?${params.toString()}`);
    return response.data;
  }

  // ============= TRANSCRIPTION =============

  async transcribeVomo(
    file: File,
    options: {
      mode: string;
      thinking_level: string;
      custom_prompt?: string;
      model_selection?: string;
      high_accuracy?: boolean;
      diarization?: boolean;
      diarization_strict?: boolean;
      use_cache?: boolean;
      auto_apply_fixes?: boolean;
      auto_apply_content_fixes?: boolean;
      skip_legal_audit?: boolean;
      skip_audit?: boolean;
      skip_fidelity_audit?: boolean;
      skip_sources_audit?: boolean;
    }
  ): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('mode', options.mode);
    formData.append('thinking_level', options.thinking_level);
    if (options.custom_prompt) formData.append('custom_prompt', options.custom_prompt);
    if (options.model_selection) formData.append('model_selection', options.model_selection);
    if (options.high_accuracy) formData.append('high_accuracy', 'true');
    if (options.diarization !== undefined) formData.append('diarization', options.diarization ? 'true' : 'false');
    if (options.diarization_strict !== undefined) {
      formData.append('diarization_strict', options.diarization_strict ? 'true' : 'false');
    }
    if (options.use_cache !== undefined) formData.append('use_cache', options.use_cache ? 'true' : 'false');
    if (options.auto_apply_fixes !== undefined) {
      formData.append('auto_apply_fixes', options.auto_apply_fixes ? 'true' : 'false');
    }
    if (options.auto_apply_content_fixes !== undefined) {
      formData.append('auto_apply_content_fixes', options.auto_apply_content_fixes ? 'true' : 'false');
    }
    if (options.skip_legal_audit) formData.append('skip_legal_audit', 'true');
    if (options.skip_audit) formData.append('skip_audit', 'true');
    if (options.skip_fidelity_audit) formData.append('skip_fidelity_audit', 'true');
    if (options.skip_sources_audit) formData.append('skip_sources_audit', 'true');

    const response = await this.axios.post('/transcription/vomo', formData, {
      // Aumentar timeout para transcrições longas (10 min)
      timeout: 600000,
      // Remove Content-Type to let axios set multipart/form-data with boundary
      headers: { 'Content-Type': undefined },
    });
    return response.data;
  }

  async startTranscriptionJob(
    files: File[],
    options: {
      mode: string;
      thinking_level: string;
      custom_prompt?: string;
      disable_tables?: boolean;
      document_theme?: string;
      document_header?: string;
      document_footer?: string;
      document_margins?: string;
      document_page_frame?: boolean;
      document_show_header_footer?: boolean;
      document_font_family?: string;
      document_font_size?: number;
      document_table_font_size?: number;
      document_line_height?: number;
      document_paragraph_spacing?: number;
      document_table_header_bg?: string;
      document_table_header_text?: string;
      document_table_row_even_bg?: string;
      document_table_row_odd_bg?: string;
      document_table_cell_text?: string;
      document_table_border_color?: string;
      model_selection?: string;
      high_accuracy?: boolean;
      diarization?: boolean;
      diarization_strict?: boolean;
      use_cache?: boolean;
      auto_apply_fixes?: boolean;
      auto_apply_content_fixes?: boolean;
      skip_legal_audit?: boolean;
      skip_audit?: boolean;
      skip_fidelity_audit?: boolean;
      skip_sources_audit?: boolean;
      transcription_engine?: 'whisper' | 'assemblyai' | 'elevenlabs';
      language?: string;
      output_language?: string;
      speaker_roles?: string[];
      speakers_expected?: number;
      subtitle_format?: 'srt' | 'vtt' | 'both';
      area?: string;
      custom_keyterms?: string;
    }
  ): Promise<{ job_id: string; status: string }> {
    console.log('[API-CLIENT] startTranscriptionJob called with', files.length, 'files');
    console.log('[API-CLIENT] Files:', files.map(f => ({ name: f.name, size: f.size, type: f.type })));
    const formData = new FormData();
    files.forEach((f) => {
      console.log('[API-CLIENT] Appending file:', f.name, f.size, 'bytes');
      formData.append('files', f);
    });
    formData.append('mode', options.mode);
    formData.append('thinking_level', options.thinking_level);
    if (options.language) formData.append('language', options.language);
    if (options.output_language) formData.append('output_language', options.output_language);
    if (options.custom_prompt) formData.append('custom_prompt', options.custom_prompt);
    if (options.disable_tables !== undefined) {
      formData.append('disable_tables', options.disable_tables ? 'true' : 'false');
    }
    if (options.document_theme) formData.append('document_theme', options.document_theme);
    if (options.document_header) formData.append('document_header', options.document_header);
    if (options.document_footer) formData.append('document_footer', options.document_footer);
    if (options.document_margins) formData.append('document_margins', options.document_margins);
    if (options.document_page_frame !== undefined) {
      formData.append('document_page_frame', options.document_page_frame ? 'true' : 'false');
    }
    if (options.document_show_header_footer !== undefined) {
      formData.append('document_show_header_footer', options.document_show_header_footer ? 'true' : 'false');
    }
    if (options.document_font_family) formData.append('document_font_family', options.document_font_family);
    if (options.document_font_size !== undefined) {
      formData.append('document_font_size', String(options.document_font_size));
    }
    if (options.document_table_font_size !== undefined) {
      formData.append('document_table_font_size', String(options.document_table_font_size));
    }
    if (options.document_line_height !== undefined) {
      formData.append('document_line_height', String(options.document_line_height));
    }
    if (options.document_paragraph_spacing !== undefined) {
      formData.append('document_paragraph_spacing', String(options.document_paragraph_spacing));
    }
    if (options.document_table_header_bg) formData.append('document_table_header_bg', options.document_table_header_bg);
    if (options.document_table_header_text) formData.append('document_table_header_text', options.document_table_header_text);
    if (options.document_table_row_even_bg) formData.append('document_table_row_even_bg', options.document_table_row_even_bg);
    if (options.document_table_row_odd_bg) formData.append('document_table_row_odd_bg', options.document_table_row_odd_bg);
    if (options.document_table_cell_text) formData.append('document_table_cell_text', options.document_table_cell_text);
    if (options.document_table_border_color) formData.append('document_table_border_color', options.document_table_border_color);
    if (options.model_selection) formData.append('model_selection', options.model_selection);
    if (options.high_accuracy) formData.append('high_accuracy', 'true');
    if (options.diarization !== undefined) formData.append('diarization', options.diarization ? 'true' : 'false');
    if (options.diarization_strict) formData.append('diarization_strict', 'true');
    if (options.use_cache !== undefined) formData.append('use_cache', options.use_cache ? 'true' : 'false');
    if (options.transcription_engine) formData.append('transcription_engine', options.transcription_engine);
    if (options.auto_apply_fixes !== undefined) {
      formData.append('auto_apply_fixes', options.auto_apply_fixes ? 'true' : 'false');
    }
    if (options.auto_apply_content_fixes !== undefined) {
      formData.append('auto_apply_content_fixes', options.auto_apply_content_fixes ? 'true' : 'false');
    }
    if (options.skip_legal_audit) formData.append('skip_legal_audit', 'true');
    if (options.skip_audit) formData.append('skip_audit', 'true');
    if (options.skip_fidelity_audit) formData.append('skip_fidelity_audit', 'true');
    if (options.skip_sources_audit) formData.append('skip_sources_audit', 'true');
    if (options.speaker_roles?.length) {
      formData.append('speaker_roles', JSON.stringify(options.speaker_roles));
    }
    if (options.speakers_expected) {
      formData.append('speakers_expected', String(options.speakers_expected));
    }
    if (options.subtitle_format) {
      formData.append('subtitle_format', options.subtitle_format);
    }
    if (options.area) {
      formData.append('area', options.area);
    }
    if (options.custom_keyterms) {
      formData.append('custom_keyterms', options.custom_keyterms);
    }

    // For large files (>100MB), send directly to backend to avoid proxy memory issues
    const totalSize = files.reduce((sum, f) => sum + f.size, 0);
    const thresholdEnv = Number.parseFloat(process.env.NEXT_PUBLIC_DIRECT_UPLOAD_THRESHOLD_MB || '');
    const thresholdMb = Number.isFinite(thresholdEnv) && thresholdEnv > 0 ? thresholdEnv : 25;
    const LARGE_FILE_THRESHOLD = thresholdMb * 1024 * 1024;
    const forceDirect = options.transcription_engine === 'whisper';

    if (totalSize > LARGE_FILE_THRESHOLD || forceDirect) {
      const reason = totalSize > LARGE_FILE_THRESHOLD ? 'large_file' : 'whisper_engine';
      console.log(`[API-CLIENT] Direct upload (${reason}) ${(totalSize / 1024 / 1024).toFixed(1)}MB`);
      // Use direct backend URL to avoid Next.js proxy buffering issues
      const directUrl = process.env.NEXT_PUBLIC_API_DIRECT_URL || 'http://127.0.0.1:8000/api';
      const token = this.getAccessToken();
      const response = await fetch(`${directUrl}/transcription/vomo/jobs`, {
        method: 'POST',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
        body: formData,
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(error.detail || `Request failed with status ${response.status}`);
      }
      return response.json();
    }

    // Remove Content-Type to let axios set multipart/form-data with boundary
    const response = await this.axios.post('/transcription/vomo/jobs', formData, {
      headers: { 'Content-Type': undefined },
    });
    return response.data;
  }

  async startTranscriptionJobFromUrl(
    url: string,
    options: {
      mode: string;
      thinking_level: string;
      custom_prompt?: string;
      disable_tables?: boolean;
      document_theme?: string;
      document_header?: string;
      document_footer?: string;
      document_margins?: string;
      document_page_frame?: boolean;
      document_show_header_footer?: boolean;
      document_font_family?: string;
      document_font_size?: number;
      document_table_font_size?: number;
      document_line_height?: number;
      document_paragraph_spacing?: number;
      document_table_header_bg?: string;
      document_table_header_text?: string;
      document_table_row_even_bg?: string;
      document_table_row_odd_bg?: string;
      document_table_cell_text?: string;
      document_table_border_color?: string;
      model_selection?: string;
      high_accuracy?: boolean;
      diarization?: boolean | null;
      diarization_strict?: boolean;
      use_cache?: boolean;
      auto_apply_fixes?: boolean;
      auto_apply_content_fixes?: boolean;
      skip_legal_audit?: boolean;
      skip_audit?: boolean;
      skip_fidelity_audit?: boolean;
      skip_sources_audit?: boolean;
      transcription_engine?: 'whisper' | 'assemblyai' | 'elevenlabs';
      language?: string;
      output_language?: string;
      speaker_roles?: string[];
      speakers_expected?: number;
      subtitle_format?: 'srt' | 'vtt' | 'both';
      area?: string;
      custom_keyterms?: string;
    }
  ): Promise<{ job_id: string; status: string }> {
    const payload: any = {
      url,
      mode: options.mode,
      thinking_level: options.thinking_level,
      model_selection: options.model_selection || 'gemini-3-flash-preview',
      high_accuracy: !!options.high_accuracy,
      language: options.language || 'pt',
      output_language: options.output_language || '',
    };
    if (options.transcription_engine) payload.transcription_engine = options.transcription_engine;
    if (options.custom_prompt) payload.custom_prompt = options.custom_prompt;
    if (options.disable_tables !== undefined) payload.disable_tables = options.disable_tables;
    if (options.document_theme) payload.document_theme = options.document_theme;
    if (options.document_header) payload.document_header = options.document_header;
    if (options.document_footer) payload.document_footer = options.document_footer;
    if (options.document_margins) payload.document_margins = options.document_margins;
    if (options.document_page_frame !== undefined) payload.document_page_frame = options.document_page_frame;
    if (options.document_show_header_footer !== undefined) payload.document_show_header_footer = options.document_show_header_footer;
    if (options.document_font_family) payload.document_font_family = options.document_font_family;
    if (options.document_font_size !== undefined) payload.document_font_size = options.document_font_size;
    if (options.document_table_font_size !== undefined) payload.document_table_font_size = options.document_table_font_size;
    if (options.document_line_height !== undefined) payload.document_line_height = options.document_line_height;
    if (options.document_paragraph_spacing !== undefined) payload.document_paragraph_spacing = options.document_paragraph_spacing;
    if (options.document_table_header_bg) payload.document_table_header_bg = options.document_table_header_bg;
    if (options.document_table_header_text) payload.document_table_header_text = options.document_table_header_text;
    if (options.document_table_row_even_bg) payload.document_table_row_even_bg = options.document_table_row_even_bg;
    if (options.document_table_row_odd_bg) payload.document_table_row_odd_bg = options.document_table_row_odd_bg;
    if (options.document_table_cell_text) payload.document_table_cell_text = options.document_table_cell_text;
    if (options.document_table_border_color) payload.document_table_border_color = options.document_table_border_color;
    if (options.diarization !== undefined) payload.diarization = options.diarization;
    if (options.diarization_strict !== undefined) payload.diarization_strict = options.diarization_strict;
    if (options.use_cache !== undefined) payload.use_cache = options.use_cache;
    if (options.auto_apply_fixes !== undefined) payload.auto_apply_fixes = options.auto_apply_fixes;
    if (options.auto_apply_content_fixes !== undefined) payload.auto_apply_content_fixes = options.auto_apply_content_fixes;
    if (options.skip_legal_audit !== undefined) payload.skip_legal_audit = options.skip_legal_audit;
    if (options.skip_audit !== undefined) payload.skip_audit = options.skip_audit;
    if (options.skip_fidelity_audit !== undefined) payload.skip_fidelity_audit = options.skip_fidelity_audit;
    if (options.skip_sources_audit !== undefined) payload.skip_sources_audit = options.skip_sources_audit;
    if (options.speaker_roles?.length) payload.speaker_roles = JSON.stringify(options.speaker_roles);
    if (options.speakers_expected) payload.speakers_expected = options.speakers_expected;
    if (options.subtitle_format) payload.subtitle_format = options.subtitle_format;
    if (options.area) payload.area = options.area;
    if (options.custom_keyterms) payload.custom_keyterms = options.custom_keyterms;

    const response = await this.axios.post('/transcription/vomo/jobs/url', payload);
    return response.data;
  }

  async startTranscriptionJobFromUrls(
    urls: string[],
    options: {
      mode: string;
      thinking_level: string;
      custom_prompt?: string;
      disable_tables?: boolean;
      document_theme?: string;
      document_header?: string;
      document_footer?: string;
      document_margins?: string;
      document_page_frame?: boolean;
      document_show_header_footer?: boolean;
      document_font_family?: string;
      document_font_size?: number;
      document_table_font_size?: number;
      document_line_height?: number;
      document_paragraph_spacing?: number;
      document_table_header_bg?: string;
      document_table_header_text?: string;
      document_table_row_even_bg?: string;
      document_table_row_odd_bg?: string;
      document_table_cell_text?: string;
      document_table_border_color?: string;
      model_selection?: string;
      high_accuracy?: boolean;
      diarization?: boolean | null;
      diarization_strict?: boolean;
      use_cache?: boolean;
      auto_apply_fixes?: boolean;
      auto_apply_content_fixes?: boolean;
      skip_legal_audit?: boolean;
      skip_audit?: boolean;
      skip_fidelity_audit?: boolean;
      skip_sources_audit?: boolean;
      transcription_engine?: 'whisper' | 'assemblyai' | 'elevenlabs';
      language?: string;
      output_language?: string;
      speaker_roles?: string[];
      speakers_expected?: number;
      subtitle_format?: 'srt' | 'vtt' | 'both';
      area?: string;
      custom_keyterms?: string;
    }
  ): Promise<{ job_id: string; status: string }> {
    const payload: any = {
      urls,
      mode: options.mode,
      thinking_level: options.thinking_level,
      model_selection: options.model_selection || 'gemini-3-flash-preview',
      high_accuracy: !!options.high_accuracy,
      language: options.language || 'pt',
      output_language: options.output_language || '',
    };
    if (options.transcription_engine) payload.transcription_engine = options.transcription_engine;
    if (options.custom_prompt) payload.custom_prompt = options.custom_prompt;
    if (options.disable_tables !== undefined) payload.disable_tables = options.disable_tables;
    if (options.document_theme) payload.document_theme = options.document_theme;
    if (options.document_header) payload.document_header = options.document_header;
    if (options.document_footer) payload.document_footer = options.document_footer;
    if (options.document_margins) payload.document_margins = options.document_margins;
    if (options.document_page_frame !== undefined) payload.document_page_frame = options.document_page_frame;
    if (options.document_show_header_footer !== undefined) payload.document_show_header_footer = options.document_show_header_footer;
    if (options.document_font_family) payload.document_font_family = options.document_font_family;
    if (options.document_font_size !== undefined) payload.document_font_size = options.document_font_size;
    if (options.document_table_font_size !== undefined) payload.document_table_font_size = options.document_table_font_size;
    if (options.document_line_height !== undefined) payload.document_line_height = options.document_line_height;
    if (options.document_paragraph_spacing !== undefined) payload.document_paragraph_spacing = options.document_paragraph_spacing;
    if (options.document_table_header_bg) payload.document_table_header_bg = options.document_table_header_bg;
    if (options.document_table_header_text) payload.document_table_header_text = options.document_table_header_text;
    if (options.document_table_row_even_bg) payload.document_table_row_even_bg = options.document_table_row_even_bg;
    if (options.document_table_row_odd_bg) payload.document_table_row_odd_bg = options.document_table_row_odd_bg;
    if (options.document_table_cell_text) payload.document_table_cell_text = options.document_table_cell_text;
    if (options.document_table_border_color) payload.document_table_border_color = options.document_table_border_color;
    if (options.diarization !== undefined) payload.diarization = options.diarization;
    if (options.diarization_strict !== undefined) payload.diarization_strict = options.diarization_strict;
    if (options.use_cache !== undefined) payload.use_cache = options.use_cache;
    if (options.auto_apply_fixes !== undefined) payload.auto_apply_fixes = options.auto_apply_fixes;
    if (options.auto_apply_content_fixes !== undefined) payload.auto_apply_content_fixes = options.auto_apply_content_fixes;
    if (options.skip_legal_audit !== undefined) payload.skip_legal_audit = options.skip_legal_audit;
    if (options.skip_audit !== undefined) payload.skip_audit = options.skip_audit;
    if (options.skip_fidelity_audit !== undefined) payload.skip_fidelity_audit = options.skip_fidelity_audit;
    if (options.skip_sources_audit !== undefined) payload.skip_sources_audit = options.skip_sources_audit;
    if (options.speaker_roles?.length) payload.speaker_roles = JSON.stringify(options.speaker_roles);
    if (options.speakers_expected) payload.speakers_expected = options.speakers_expected;
    if (options.subtitle_format) payload.subtitle_format = options.subtitle_format;
    if (options.area) payload.area = options.area;
    if (options.custom_keyterms) payload.custom_keyterms = options.custom_keyterms;

    const response = await this.axios.post('/transcription/vomo/jobs/urls', payload);
    return response.data;
  }

  async startHearingJob(
    file: File,
    payload: {
      case_id: string;
      goal: string;
      thinking_level: string;
      model_selection?: string;
      high_accuracy?: boolean;
      format_mode?: string;
      custom_prompt?: string;
      document_theme?: string;
      document_header?: string;
      document_footer?: string;
      document_margins?: string;
      document_page_frame?: boolean;
      document_show_header_footer?: boolean;
      document_font_family?: string;
      document_font_size?: number;
      document_table_font_size?: number;
      document_line_height?: number;
      document_paragraph_spacing?: number;
      document_table_header_bg?: string;
      document_table_header_text?: string;
      document_table_row_even_bg?: string;
      document_table_row_odd_bg?: string;
      document_table_cell_text?: string;
      document_table_border_color?: string;
      format_enabled?: boolean;
      include_timestamps?: boolean;
      allow_indirect?: boolean;
      allow_summary?: boolean;
      output_style?: 'default' | 'ata_literal' | 'ata_resumida' | 'relatorio';
      use_cache?: boolean;
      auto_apply_fixes?: boolean;
      auto_apply_content_fixes?: boolean;
      skip_legal_audit?: boolean;
      skip_fidelity_audit?: boolean;
      skip_sources_audit?: boolean;
      language?: string;
      output_language?: string;
      speaker_roles?: string[];
      speakers_expected?: number;
      speaker_id_type?: 'name' | 'role';
      speaker_id_values?: string;
      area?: string;
      custom_keyterms?: string;
      transcription_engine?: 'whisper' | 'assemblyai' | 'elevenlabs';
    }
  ): Promise<{ job_id: string; status: string }> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('case_id', payload.case_id);
    if (payload.language) formData.append('language', payload.language);
    if (payload.transcription_engine) formData.append('transcription_engine', payload.transcription_engine);
    if (payload.output_language) formData.append('output_language', payload.output_language);
    formData.append('goal', payload.goal);
    formData.append('thinking_level', payload.thinking_level);
    if (payload.model_selection) formData.append('model_selection', payload.model_selection);
    if (payload.high_accuracy) formData.append('high_accuracy', 'true');
    if (payload.format_mode) formData.append('format_mode', payload.format_mode);
    if (payload.custom_prompt) formData.append('custom_prompt', payload.custom_prompt);
    if (payload.document_theme) formData.append('document_theme', payload.document_theme);
    if (payload.document_header) formData.append('document_header', payload.document_header);
    if (payload.document_footer) formData.append('document_footer', payload.document_footer);
    if (payload.document_margins) formData.append('document_margins', payload.document_margins);
    if (payload.document_page_frame !== undefined) {
      formData.append('document_page_frame', payload.document_page_frame ? 'true' : 'false');
    }
    if (payload.document_show_header_footer !== undefined) {
      formData.append('document_show_header_footer', payload.document_show_header_footer ? 'true' : 'false');
    }
    if (payload.document_font_family) formData.append('document_font_family', payload.document_font_family);
    if (payload.document_font_size !== undefined) {
      formData.append('document_font_size', String(payload.document_font_size));
    }
    if (payload.document_table_font_size !== undefined) {
      formData.append('document_table_font_size', String(payload.document_table_font_size));
    }
    if (payload.document_line_height !== undefined) {
      formData.append('document_line_height', String(payload.document_line_height));
    }
    if (payload.document_paragraph_spacing !== undefined) {
      formData.append('document_paragraph_spacing', String(payload.document_paragraph_spacing));
    }
    if (payload.document_table_header_bg) formData.append('document_table_header_bg', payload.document_table_header_bg);
    if (payload.document_table_header_text) formData.append('document_table_header_text', payload.document_table_header_text);
    if (payload.document_table_row_even_bg) formData.append('document_table_row_even_bg', payload.document_table_row_even_bg);
    if (payload.document_table_row_odd_bg) formData.append('document_table_row_odd_bg', payload.document_table_row_odd_bg);
    if (payload.document_table_cell_text) formData.append('document_table_cell_text', payload.document_table_cell_text);
    if (payload.document_table_border_color) formData.append('document_table_border_color', payload.document_table_border_color);
    if (payload.format_enabled !== undefined) {
      formData.append('format_enabled', payload.format_enabled ? 'true' : 'false');
    }
    if (payload.include_timestamps !== undefined) {
      formData.append('include_timestamps', payload.include_timestamps ? 'true' : 'false');
    }
    if (payload.allow_indirect) formData.append('allow_indirect', 'true');
    if (payload.allow_summary) formData.append('allow_summary', 'true');
    if (payload.output_style) formData.append('output_style', payload.output_style);
    if (payload.use_cache !== undefined) formData.append('use_cache', payload.use_cache ? 'true' : 'false');
    if (payload.auto_apply_fixes !== undefined) {
      formData.append('auto_apply_fixes', payload.auto_apply_fixes ? 'true' : 'false');
    }
    if (payload.auto_apply_content_fixes !== undefined) {
      formData.append('auto_apply_content_fixes', payload.auto_apply_content_fixes ? 'true' : 'false');
    }
    if (payload.skip_legal_audit) formData.append('skip_legal_audit', 'true');
    if (payload.skip_fidelity_audit) formData.append('skip_fidelity_audit', 'true');
    if (payload.skip_sources_audit) formData.append('skip_sources_audit', 'true');
    if (payload.speaker_roles?.length) {
      formData.append('speaker_roles', JSON.stringify(payload.speaker_roles));
    }
    if (payload.speakers_expected) {
      formData.append('speakers_expected', String(payload.speakers_expected));
    }
    if (payload.speaker_id_type) {
      formData.append('speaker_id_type', payload.speaker_id_type);
    }
    if (payload.speaker_id_values) {
      formData.append('speaker_id_values', payload.speaker_id_values);
    }
    if (payload.area) {
      formData.append('area', payload.area);
    }
    if (payload.custom_keyterms) {
      formData.append('custom_keyterms', payload.custom_keyterms);
    }

    // For large files (>100MB), send directly to backend to avoid proxy memory issues
    const fileSize = file.size;
    const LARGE_FILE_THRESHOLD = 100 * 1024 * 1024; // 100MB

    if (fileSize > LARGE_FILE_THRESHOLD) {
      console.log(`[API-CLIENT] Large hearing file upload (${(fileSize / 1024 / 1024).toFixed(1)}MB), using direct backend URL`);
      // Use direct backend URL to avoid Next.js proxy buffering issues
      const directUrl = process.env.NEXT_PUBLIC_API_DIRECT_URL || 'http://127.0.0.1:8000/api';
      const token = this.getAccessToken();
      const response = await fetch(`${directUrl}/transcription/hearing/jobs`, {
        method: 'POST',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
        body: formData,
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(error.detail || `Request failed with status ${response.status}`);
      }
      return response.json();
    }

    // Remove Content-Type to let axios set multipart/form-data with boundary
    const response = await this.axios.post('/transcription/hearing/jobs', formData, {
      headers: { 'Content-Type': undefined },
    });
    return response.data;
  }

  async startHearingJobFromUrl(
    url: string,
    payload: {
      case_id: string;
      goal: string;
      thinking_level: string;
      model_selection?: string;
      high_accuracy?: boolean;
      format_mode?: string;
      custom_prompt?: string;
      document_theme?: string;
      document_header?: string;
      document_footer?: string;
      document_margins?: string;
      document_page_frame?: boolean;
      document_show_header_footer?: boolean;
      document_font_family?: string;
      document_font_size?: number;
      document_table_font_size?: number;
      document_line_height?: number;
      document_paragraph_spacing?: number;
      document_table_header_bg?: string;
      document_table_header_text?: string;
      document_table_row_even_bg?: string;
      document_table_row_odd_bg?: string;
      document_table_cell_text?: string;
      document_table_border_color?: string;
      format_enabled?: boolean;
      include_timestamps?: boolean;
      allow_indirect?: boolean;
      allow_summary?: boolean;
      output_style?: 'default' | 'ata_literal' | 'ata_resumida' | 'relatorio';
      use_cache?: boolean;
      auto_apply_fixes?: boolean;
      auto_apply_content_fixes?: boolean;
      skip_legal_audit?: boolean;
      skip_fidelity_audit?: boolean;
      skip_sources_audit?: boolean;
      language?: string;
      output_language?: string;
      speaker_roles?: string[];
      speakers_expected?: number;
      speaker_id_type?: 'name' | 'role';
      speaker_id_values?: string;
      area?: string;
      custom_keyterms?: string;
      transcription_engine?: 'whisper' | 'assemblyai' | 'elevenlabs';
    }
  ): Promise<{ job_id: string; status: string }> {
    const body: any = {
      url,
      case_id: payload.case_id,
      goal: payload.goal,
      thinking_level: payload.thinking_level,
      model_selection: payload.model_selection || 'gemini-3-flash-preview',
      high_accuracy: !!payload.high_accuracy,
      format_mode: payload.format_mode || 'AUDIENCIA',
      format_enabled: payload.format_enabled !== undefined ? payload.format_enabled : true,
      include_timestamps: payload.include_timestamps !== undefined ? payload.include_timestamps : true,
      allow_indirect: !!payload.allow_indirect,
      allow_summary: !!payload.allow_summary,
      output_style: payload.output_style || 'default',
      language: payload.language || 'pt',
      output_language: payload.output_language || '',
      transcription_engine: payload.transcription_engine || 'whisper',
    };
    if (payload.custom_prompt) body.custom_prompt = payload.custom_prompt;
    if (payload.document_theme) body.document_theme = payload.document_theme;
    if (payload.document_header) body.document_header = payload.document_header;
    if (payload.document_footer) body.document_footer = payload.document_footer;
    if (payload.document_margins) body.document_margins = payload.document_margins;
    if (payload.document_page_frame !== undefined) body.document_page_frame = payload.document_page_frame;
    if (payload.document_show_header_footer !== undefined) body.document_show_header_footer = payload.document_show_header_footer;
    if (payload.document_font_family) body.document_font_family = payload.document_font_family;
    if (payload.document_font_size !== undefined) body.document_font_size = payload.document_font_size;
    if (payload.document_table_font_size !== undefined) body.document_table_font_size = payload.document_table_font_size;
    if (payload.document_line_height !== undefined) body.document_line_height = payload.document_line_height;
    if (payload.document_paragraph_spacing !== undefined) body.document_paragraph_spacing = payload.document_paragraph_spacing;
    if (payload.document_table_header_bg) body.document_table_header_bg = payload.document_table_header_bg;
    if (payload.document_table_header_text) body.document_table_header_text = payload.document_table_header_text;
    if (payload.document_table_row_even_bg) body.document_table_row_even_bg = payload.document_table_row_even_bg;
    if (payload.document_table_row_odd_bg) body.document_table_row_odd_bg = payload.document_table_row_odd_bg;
    if (payload.document_table_cell_text) body.document_table_cell_text = payload.document_table_cell_text;
    if (payload.document_table_border_color) body.document_table_border_color = payload.document_table_border_color;
    if (payload.use_cache !== undefined) body.use_cache = payload.use_cache;
    if (payload.auto_apply_fixes !== undefined) body.auto_apply_fixes = payload.auto_apply_fixes;
    if (payload.auto_apply_content_fixes !== undefined) body.auto_apply_content_fixes = payload.auto_apply_content_fixes;
    if (payload.skip_legal_audit !== undefined) body.skip_legal_audit = payload.skip_legal_audit;
    if (payload.skip_fidelity_audit !== undefined) body.skip_fidelity_audit = payload.skip_fidelity_audit;
    if (payload.skip_sources_audit !== undefined) body.skip_sources_audit = payload.skip_sources_audit;
    if (payload.speaker_roles?.length) body.speaker_roles = JSON.stringify(payload.speaker_roles);
    if (payload.speakers_expected) body.speakers_expected = payload.speakers_expected;
    if (payload.speaker_id_type) body.speaker_id_type = payload.speaker_id_type;
    if (payload.speaker_id_values) body.speaker_id_values = payload.speaker_id_values;
    if (payload.area) body.area = payload.area;
    if (payload.custom_keyterms) body.custom_keyterms = payload.custom_keyterms;

    const response = await this.axios.post('/transcription/hearing/jobs/url', body);
    return response.data;
  }

  async listTranscriptionJobs(limit: number = 20): Promise<{ jobs: any[] }> {
    const response = await this.axios.get('/transcription/jobs', { params: { limit } });
    return response.data;
  }

  async getTranscriptionJob(jobId: string): Promise<any> {
    const response = await this.axios.get(`/transcription/jobs/${jobId}`);
    return response.data;
  }

  async cancelTranscriptionJob(jobId: string): Promise<any> {
    const response = await this.axios.post(`/transcription/jobs/${jobId}/cancel`);
    return response.data;
  }

  async retryTranscriptionJob(jobId: string): Promise<any> {
    const token = this.getAccessToken();
    const tokenParam = token ? `?token=${encodeURIComponent(token)}` : '';
    const response = await this.axios.post(`/transcription/vomo/jobs/${jobId}/retry${tokenParam}`);
    return response.data;
  }

  async updateTranscriptionJobQuality(
    jobId: string,
    data: {
      validation_report?: any;
      analysis_result?: any;
      selected_fix_ids?: string[];
      applied_fixes?: string[];
      suggestions?: string | null;
      fixed_content?: string;
      needs_revalidate?: boolean;
      applied_issue_ids?: string[];
      rejected_preventive_issue_ids?: string[];
      rejected_preventive_reasons?: Record<string, string>;
    }
  ): Promise<{ success: boolean; quality?: any }> {
    const response = await this.axios.post(`/transcription/jobs/${jobId}/quality`, data);
    return response.data;
  }

  async updateTranscriptionJobContent(
    jobId: string,
    data: {
      content?: string;
      rich_text_html?: string | null;
      rich_text_json?: any;
      rich_text_meta?: any;
      needs_revalidate?: boolean;
    }
  ): Promise<{ success: boolean; content_updated?: boolean; quality?: any }> {
    const response = await this.axios.post(`/transcription/jobs/${jobId}/content`, data);
    return response.data;
  }

  async streamTranscriptionJob(
    jobId: string,
    onProgress: (stage: string, progress: number, message: string) => void,
    onComplete: (payload: any) => void,
    onError: (error: string) => void,
    maxRetries: number = 3
  ): Promise<void> {
    const token = this.getAccessToken();
    let retryCount = 0;
    let lastProgress = 0;
    let completed = false;

    const attemptStream = async (): Promise<boolean> => {
      try {
        const response = await this.fetchStreamingGetWithFallback(
          `/transcription/jobs/${jobId}/stream`,
          {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            Accept: 'text/event-stream',
          }
        );

        const reader = response.body?.getReader();
        if (!reader) {
          if (process.env.NODE_ENV === 'development') console.warn('[SSE] Response body is not readable');
          return false;
        }

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (!line.startsWith('data:')) continue;
            try {
              const data = JSON.parse(line.slice(5).trim());
              if (data.stage !== undefined) {
                lastProgress = data.progress || lastProgress;
                onProgress(data.stage, data.progress, data.message);
              } else if (data.job_type || data.payload || data.content !== undefined) {
                completed = true;
                onComplete(data);
                return true;
              } else if (data.error !== undefined) {
                onError(data.error);
                return true; // Don't retry on explicit errors
              }
            } catch (parseError) {
              if (process.env.NODE_ENV === 'development') console.warn('[SSE] Failed to parse SSE data:', line);
            }
          }
        }

        // Check remaining buffer
        if (buffer.trim().startsWith('data:')) {
          try {
            const data = JSON.parse(buffer.trim().slice(5).trim());
            if (data.job_type || data.payload || data.content !== undefined) {
              completed = true;
              onComplete(data);
              return true;
            } else if (data.error !== undefined) {
              onError(data.error);
              return true;
            }
          } catch (parseError) {
            if (process.env.NODE_ENV === 'development') console.warn('[SSE] Failed to parse final SSE data:', buffer);
          }
        }

        // Stream ended without completion - might need retry
        return completed;
      } catch (error: any) {
        if (process.env.NODE_ENV === 'development') console.warn(`[SSE] Stream error (attempt ${retryCount + 1}/${maxRetries}):`, error.message);
        return false;
      }
    };

    // Try SSE with retries
    while (retryCount < maxRetries && !completed) {
      const success = await attemptStream();
      if (success || completed) return;

      retryCount++;
      if (retryCount < maxRetries) {
        if (process.env.NODE_ENV === 'development') console.log(`[SSE] Retrying in ${retryCount * 2}s... (attempt ${retryCount + 1}/${maxRetries})`);
        onProgress('reconnecting', lastProgress, `Reconectando... (tentativa ${retryCount + 1}/${maxRetries})`);
        await new Promise(resolve => setTimeout(resolve, retryCount * 2000));
      }
    }

    // SSE failed - fall back to polling
    if (!completed) {
      if (process.env.NODE_ENV === 'development') console.log('[SSE] Falling back to polling...');
      onProgress('polling', lastProgress, 'Conexão SSE perdida, verificando status...');

      const pollForResult = async (): Promise<void> => {
        const maxPolls = 720; // 60 minutes max (5s intervals)
        for (let i = 0; i < maxPolls && !completed; i++) {
          try {
            const jobStatus = await this.getTranscriptionJobResult(jobId);
            if (jobStatus?.status === 'completed' && (jobStatus.content || jobStatus.payload)) {
              completed = true;
              onComplete(jobStatus);
              return;
            } else if (jobStatus?.status === 'canceled') {
              onError(jobStatus.message || 'Job cancelado');
              return;
            } else if (jobStatus?.status === 'error' || jobStatus?.status === 'failed') {
              onError(jobStatus.error || 'Job failed');
              return;
            }
            // Update progress from job status if available
            if (jobStatus?.progress !== undefined) {
              lastProgress = jobStatus.progress;
              onProgress('processing', jobStatus.progress, jobStatus.message || 'Processando...');
            }
          } catch (pollError: any) {
            if (process.env.NODE_ENV === 'development') console.warn('[Polling] Error:', pollError.message);
          }
          await new Promise(resolve => setTimeout(resolve, 5000));
        }
        if (!completed) {
          onError('Timeout: Unable to get transcription result');
        }
      };

      await pollForResult();
    }
  }

  async getTranscriptionJobResult(jobId: string): Promise<any> {
    try {
      // First get job status
      const statusResponse = await this.axios.get(`/transcription/jobs/${jobId}`);
      const jobStatus = statusResponse.data;

      // If completed, fetch the full result with content
      if (jobStatus?.status === 'completed') {
        try {
          const resultResponse = await this.axios.get(`/transcription/jobs/${jobId}/result`);
          return { ...jobStatus, ...resultResponse.data };
        } catch (resultError: any) {
          if (process.env.NODE_ENV === 'development') console.warn('[getTranscriptionJobResult] Could not fetch full result:', resultError.message);
          return jobStatus;
        }
      }

      return jobStatus;
    } catch (error: any) {
      if (process.env.NODE_ENV === 'development') console.warn('[getTranscriptionJobResult] Error:', error.message);
      return null;
    }
  }

  async deleteTranscriptionJob(jobId: string, deleteOutputs: boolean = true): Promise<void> {
    await this.axios.delete(`/transcription/jobs/${jobId}`, {
      params: { delete_outputs: deleteOutputs ? 'true' : 'false' },
    });
  }

  /**
   * Get the URL for a job's media file (audio/video)
   * Includes auth token as query param since <audio>/<video> elements can't set headers
   */
  getJobMediaUrl(jobId: string, index: number = 0): string {
    const token = this.getAccessToken();
    const tokenParam = token ? `&token=${encodeURIComponent(token)}` : '';
    return `${this.baseUrl}/transcription/jobs/${jobId}/media?index=${index}${tokenParam}`;
  }

  /**
   * List all media files for a job
   */
  async listJobMedia(jobId: string): Promise<{ files: Array<{ index: number; name: string; size: number; url: string }> }> {
    const response = await this.axios.get(`/transcription/jobs/${jobId}/media/list`);
    return response.data;
  }

  async downloadTranscriptionReport(jobId: string, reportKey: string): Promise<Blob> {
    const safeKey = encodeURIComponent(reportKey);
    const response = await this.axios.get(`/transcription/jobs/${jobId}/reports/${safeKey}`, {
      responseType: 'blob',
    });
    return response.data;
  }

  async recomputeTranscriptionPreventiveAudit(jobId: string): Promise<{ success: boolean; reports?: any; audit_summary?: any }> {
    const response = await this.axios.post(`/transcription/jobs/${jobId}/preventive-audit/recompute`);
    return response.data;
  }

  async listPendingTranscriptions(
    provider?: 'assemblyai' | 'whisper' | 'elevenlabs',
    syncStatus: boolean = true,
  ): Promise<Array<{
    transcript_id: string;
    file_name: string;
    file_hash: string;
    status: string;
    provider: string;
    submitted_at: string;
    completed_at?: string;
    audio_duration?: number;
    config_hash?: string;
    error?: string;
  }>> {
    const response = await this.axios.get('/transcription/pending', {
      params: {
        ...(provider ? { provider } : {}),
        sync_status: syncStatus ? 'true' : 'false',
      },
    });
    return response.data;
  }

  async resumePendingTranscription(payload: {
    transcript_id: string;
    provider?: 'assemblyai' | 'whisper' | 'elevenlabs';
    file_hash?: string;
    speaker_roles?: string[];
    mode?: string;
  }): Promise<{
    status: string;
    transcript_id: string;
    text?: string;
    segments?: any[];
    audio_duration?: number;
    error?: string;
    message?: string;
  }> {
    const token = this.getAccessToken();
    const tokenParam = token ? `?token=${encodeURIComponent(token)}` : '';
    const response = await this.axios.post(`/transcription/resume${tokenParam}`, payload);
    return response.data;
  }

  async deletePendingTranscriptionCache(
    fileHash: string,
    provider: 'assemblyai' | 'whisper' | 'elevenlabs' = 'assemblyai',
  ): Promise<{ status: string; file_hash: string; provider: string }> {
    const response = await this.axios.delete(`/transcription/cache/${encodeURIComponent(fileHash)}`, {
      params: { provider },
    });
    return response.data;
  }

  /**
   * SSE streaming transcription with real-time progress updates
   */
  async transcribeVomoStream(
    file: File,
    options: {
      mode: string;
      thinking_level: string;
      custom_prompt?: string;
      model_selection?: string;
      high_accuracy?: boolean;
      diarization?: boolean;
      diarization_strict?: boolean;
      use_cache?: boolean;
      auto_apply_fixes?: boolean;
      auto_apply_content_fixes?: boolean;
      skip_legal_audit?: boolean;
      skip_audit?: boolean;
      skip_fidelity_audit?: boolean;
      skip_sources_audit?: boolean;
      language?: string;
      output_language?: string;
    },
    onProgress: (stage: string, progress: number, message: string) => void,
    onComplete: (payload: { content: string; raw_content?: string | null; reports?: any }) => void,
    onError: (error: string) => void
  ): Promise<void> {
    const buildFormData = () => {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('mode', options.mode);
      formData.append('thinking_level', options.thinking_level);
      if (options.custom_prompt) formData.append('custom_prompt', options.custom_prompt);
      if (options.model_selection) formData.append('model_selection', options.model_selection);
      if (options.high_accuracy) formData.append('high_accuracy', 'true');
      if (options.diarization !== undefined) formData.append('diarization', options.diarization ? 'true' : 'false');
      if (options.diarization_strict !== undefined) {
        formData.append('diarization_strict', options.diarization_strict ? 'true' : 'false');
      }
      if (options.use_cache !== undefined) formData.append('use_cache', options.use_cache ? 'true' : 'false');
      if (options.auto_apply_fixes !== undefined) {
        formData.append('auto_apply_fixes', options.auto_apply_fixes ? 'true' : 'false');
      }
      if (options.auto_apply_content_fixes !== undefined) {
        formData.append('auto_apply_content_fixes', options.auto_apply_content_fixes ? 'true' : 'false');
      }
      if (options.skip_legal_audit) formData.append('skip_legal_audit', 'true');
      if (options.skip_audit) formData.append('skip_audit', 'true');
      if (options.skip_fidelity_audit) formData.append('skip_fidelity_audit', 'true');
      if (options.skip_sources_audit) formData.append('skip_sources_audit', 'true');
      if (options.language) formData.append('language', options.language);
      if (options.output_language) formData.append('output_language', options.output_language);
      return formData;
    };

    const token = this.getAccessToken();

    try {
      const response = await this.fetchStreamingWithFallback(
        '/transcription/vomo/stream',
        buildFormData,
        {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          Accept: 'text/event-stream',
        }
      );

      const reader = response.body?.getReader();
      if (!reader) {
        onError('Response body is not readable');
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data:')) {
            try {
              const data = JSON.parse(line.slice(5).trim());

              if (data.stage !== undefined) {
                // Progress event
                onProgress(data.stage, data.progress, data.message);
              } else if (data.content !== undefined) {
                // Complete event
                onComplete({
                  content: data.content,
                  raw_content: data.raw_content,
                  reports: data.reports,
                });
              } else if (data.error !== undefined) {
                // Error event
                onError(data.error);
              }
            } catch (parseError) {
              if (process.env.NODE_ENV === 'development') console.warn('Failed to parse SSE data:', line);
            }
          }
        }
      }

      // Process any remaining buffer content after stream ends
      if (buffer.trim().startsWith('data:')) {
        try {
          const data = JSON.parse(buffer.trim().slice(5).trim());
          if (data.content !== undefined) {
            onComplete({
              content: data.content,
              raw_content: data.raw_content,
              reports: data.reports,
            });
          } else if (data.error !== undefined) {
            onError(data.error);
          }
        } catch (parseError) {
          if (process.env.NODE_ENV === 'development') console.warn('Failed to parse final SSE data:', buffer);
        }
      }
    } catch (error: any) {
      onError(error.message || 'Network error');
    }
  }

  /**
   * SSE batch transcription for multiple files with real-time progress
   */
  async transcribeVomoBatchStream(
    files: File[],
    options: {
      mode: string;
      thinking_level: string;
      custom_prompt?: string;
      model_selection?: string;
      high_accuracy?: boolean;
      diarization?: boolean;
      diarization_strict?: boolean;
      use_cache?: boolean;
      auto_apply_fixes?: boolean;
      auto_apply_content_fixes?: boolean;
      skip_legal_audit?: boolean;
      skip_audit?: boolean;
      skip_fidelity_audit?: boolean;
      skip_sources_audit?: boolean;
      language?: string;
      output_language?: string;
    },
    onProgress: (stage: string, progress: number, message: string) => void,
    onComplete: (payload: { content: string; raw_content?: string | null; filenames: string[]; total_files: number; reports?: any }) => void,
    onError: (error: string) => void
  ): Promise<void> {
    const buildFormData = () => {
      const formData = new FormData();
      files.forEach(f => formData.append('files', f));
      formData.append('mode', options.mode);
      formData.append('thinking_level', options.thinking_level);
      if (options.custom_prompt) formData.append('custom_prompt', options.custom_prompt);
      if (options.model_selection) formData.append('model_selection', options.model_selection);
      if (options.high_accuracy) formData.append('high_accuracy', 'true');
      if (options.diarization !== undefined) formData.append('diarization', options.diarization ? 'true' : 'false');
      if (options.diarization_strict !== undefined) {
        formData.append('diarization_strict', options.diarization_strict ? 'true' : 'false');
      }
      if (options.use_cache !== undefined) formData.append('use_cache', options.use_cache ? 'true' : 'false');
      if (options.auto_apply_fixes !== undefined) {
        formData.append('auto_apply_fixes', options.auto_apply_fixes ? 'true' : 'false');
      }
      if (options.auto_apply_content_fixes !== undefined) {
        formData.append('auto_apply_content_fixes', options.auto_apply_content_fixes ? 'true' : 'false');
      }
      if (options.skip_legal_audit) formData.append('skip_legal_audit', 'true');
      if (options.skip_audit) formData.append('skip_audit', 'true');
      if (options.skip_fidelity_audit) formData.append('skip_fidelity_audit', 'true');
      if (options.skip_sources_audit) formData.append('skip_sources_audit', 'true');
      if (options.language) formData.append('language', options.language);
      if (options.output_language) formData.append('output_language', options.output_language);
      return formData;
    };

    const token = this.getAccessToken();

    try {
      const response = await this.fetchStreamingWithFallback(
        '/transcription/vomo/batch/stream',
        buildFormData,
        {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          Accept: 'text/event-stream',
        }
      );

      const reader = response.body?.getReader();
      if (!reader) {
        onError('Response body is not readable');
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data:')) {
            try {
              const data = JSON.parse(line.slice(5).trim());

              if (data.stage !== undefined) {
                onProgress(data.stage, data.progress, data.message);
              } else if (data.content !== undefined) {
                onComplete({
                  content: data.content,
                  raw_content: data.raw_content,
                  filenames: data.filenames || [],
                  total_files: data.total_files || 1,
                  reports: data.reports,
                });
              } else if (data.error !== undefined) {
                onError(data.error);
              }
            } catch (parseError) {
              if (process.env.NODE_ENV === 'development') console.warn('Failed to parse SSE data:', line);
            }
          }
        }
      }

      // Process any remaining buffer content after stream ends
      if (buffer.trim().startsWith('data:')) {
        try {
          const data = JSON.parse(buffer.trim().slice(5).trim());
          if (data.content !== undefined) {
            onComplete({
              content: data.content,
              raw_content: data.raw_content,
              filenames: data.filenames || [],
              total_files: data.total_files || 1,
              reports: data.reports,
            });
          } else if (data.error !== undefined) {
            onError(data.error);
          }
        } catch (parseError) {
          if (process.env.NODE_ENV === 'development') console.warn('Failed to parse final SSE data:', buffer);
        }
      }
    } catch (error: any) {
      onError(error.message || 'Network error');
    }
  }

  async exportDocx(
    content: string,
    filename: string,
    options?: {
      document_theme?: string;
      document_header?: string;
      document_footer?: string;
      document_margins?: string;
      document_page_frame?: boolean;
      document_show_header_footer?: boolean;
      document_font_family?: string;
      document_font_size?: number;
      document_table_font_size?: number;
      document_line_height?: number;
      document_paragraph_spacing?: number;
      document_table_header_bg?: string;
      document_table_header_text?: string;
      document_table_row_even_bg?: string;
      document_table_row_odd_bg?: string;
      document_table_cell_text?: string;
      document_table_border_color?: string;
    }
  ): Promise<Blob> {
    const response = await this.axios.post('/transcription/export/docx',
      {
        content,
        filename,
        document_theme: options?.document_theme,
        document_header: options?.document_header,
        document_footer: options?.document_footer,
        document_margins: options?.document_margins,
        document_page_frame: options?.document_page_frame,
        document_show_header_footer: options?.document_show_header_footer,
        document_font_family: options?.document_font_family,
        document_font_size: options?.document_font_size,
        document_table_font_size: options?.document_table_font_size,
        document_line_height: options?.document_line_height,
        document_paragraph_spacing: options?.document_paragraph_spacing,
        document_table_header_bg: options?.document_table_header_bg,
        document_table_header_text: options?.document_table_header_text,
        document_table_row_even_bg: options?.document_table_row_even_bg,
        document_table_row_odd_bg: options?.document_table_row_odd_bg,
        document_table_cell_text: options?.document_table_cell_text,
        document_table_border_color: options?.document_table_border_color,
      },
      { responseType: 'blob' }
    );
    return response.data;
  }

  // ============= HEARING TRANSCRIPTION =============

  /**
   * SSE streaming hearing transcription with structured payload.
   */
  async transcribeHearingStream(
    file: File,
    options: {
      case_id: string;
      goal: string;
      thinking_level: string;
      model_selection?: string;
      high_accuracy?: boolean;
      format_mode?: string;
      custom_prompt?: string;
      format_enabled?: boolean;
      allow_indirect?: boolean;
      allow_summary?: boolean;
      output_style?: 'default' | 'ata_literal' | 'ata_resumida' | 'relatorio';
      use_cache?: boolean;
      auto_apply_fixes?: boolean;
      auto_apply_content_fixes?: boolean;
      skip_legal_audit?: boolean;
      skip_fidelity_audit?: boolean;
      skip_sources_audit?: boolean;
      language?: string;
      output_language?: string;
    },
    onProgress: (stage: string, progress: number, message: string) => void,
    onComplete: (payload: any) => void,
    onError: (error: string) => void
  ): Promise<void> {
    const buildFormData = () => {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('case_id', options.case_id);
      formData.append('goal', options.goal);
      formData.append('thinking_level', options.thinking_level);
      if (options.model_selection) formData.append('model_selection', options.model_selection);
      if (options.high_accuracy) formData.append('high_accuracy', 'true');
      if (options.format_mode) formData.append('format_mode', options.format_mode);
      if (options.custom_prompt) formData.append('custom_prompt', options.custom_prompt);
      if (options.format_enabled === false) formData.append('format_enabled', 'false');
      if (options.allow_indirect) formData.append('allow_indirect', 'true');
      if (options.allow_summary) formData.append('allow_summary', 'true');
      if (options.output_style) formData.append('output_style', options.output_style);
      if (options.use_cache !== undefined) formData.append('use_cache', options.use_cache ? 'true' : 'false');
      if (options.auto_apply_fixes !== undefined) {
        formData.append('auto_apply_fixes', options.auto_apply_fixes ? 'true' : 'false');
      }
      if (options.auto_apply_content_fixes !== undefined) {
        formData.append('auto_apply_content_fixes', options.auto_apply_content_fixes ? 'true' : 'false');
      }
      if (options.skip_legal_audit) formData.append('skip_legal_audit', 'true');
      if (options.skip_fidelity_audit) formData.append('skip_fidelity_audit', 'true');
      if (options.skip_sources_audit) formData.append('skip_sources_audit', 'true');
      if (options.language) formData.append('language', options.language);
      if (options.output_language) formData.append('output_language', options.output_language);
      return formData;
    };

    const token = this.getAccessToken();

    try {
      const response = await this.fetchStreamingWithFallback(
        '/transcription/hearing/stream',
        buildFormData,
        {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          Accept: 'text/event-stream',
        }
      );

      const reader = response.body?.getReader();
      if (!reader) {
        onError('Response body is not readable');
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data:')) {
            try {
              const data = JSON.parse(line.slice(5).trim());
              if (data.stage !== undefined) {
                onProgress(data.stage, data.progress, data.message);
              } else if (data.payload !== undefined) {
                onComplete(data.payload);
              } else if (data.error !== undefined) {
                onError(data.error);
              }
            } catch (parseError) {
              if (process.env.NODE_ENV === 'development') console.warn('Failed to parse SSE data:', line);
            }
          }
        }
      }

      if (buffer.trim().startsWith('data:')) {
        try {
          const data = JSON.parse(buffer.trim().slice(5).trim());
          if (data.payload !== undefined) {
            onComplete(data.payload);
          } else if (data.error !== undefined) {
            onError(data.error);
          }
        } catch (parseError) {
          if (process.env.NODE_ENV === 'development') console.warn('Failed to parse final SSE data:', buffer);
        }
      }
    } catch (error: any) {
      onError(error.message || 'Network error');
    }
  }

  async updateHearingSpeakers(caseId: string, speakers: Array<{ speaker_id: string; name?: string; role?: string }>): Promise<any> {
    const response = await this.axios.post('/transcription/hearing/speakers', {
      case_id: caseId,
      speakers,
    });
    return response.data;
  }

  // REMOVIDO: enrollHearingSpeaker (substituído por inferência automática de papéis via LLM)

  async exportLegalDocx(content: string, filename: string, modo: string = 'GENERICO'): Promise<Blob> {
    const response = await this.axios.post(
      '/documents/export/docx',
      { content, filename, modo },
      { responseType: 'blob' }
    );
    return response.data;
  }

  // ============= HELPERS =============

  isAuthenticated(): boolean {
    return !!this.getAccessToken();
  }

  async runAudit(file: File): Promise<Blob> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await this.axios.post('/audit/run', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      responseType: 'blob', // Expecting binary file (DOCX)
    });
    return response.data;
  }

  async healthCheck(): Promise<{ status: string; version: string; environment: string }> {
    // Use the same-origin proxy (`/api/*`) so dev works across ports and avoids CORS/IPv6 issues.
    // The Next proxy maps `/api/health` to the backend root `/health`.
    const response = await this.axios.get('/health');
    return response.data;
  }

  async getConfigLimits(): Promise<Record<string, any>> {
    const response = await this.axios.get('/config/limits');
    return response.data;
  }

  async getBillingConfig(): Promise<Record<string, any>> {
    const response = await this.axios.get('/config/billing');
    return response.data;
  }

  async getBillingSummary(): Promise<Record<string, any>> {
    const response = await this.axios.get('/billing/summary');
    return response.data;
  }

  async startJob(data: any): Promise<{ job_id: string; status: string }> {
    const response = await this.axios.post('/jobs/start', data);
    return response.data;
  }

  async resumeJob(jobId: string, decision: any): Promise<any> {
    const response = await this.axios.post(`/jobs/${jobId}/resume`, decision);
    return response.data;
  }

  // ============= QUALITY CONTROL =============

  async validateDocumentQuality(data: {
    raw_content: string;
    formatted_content: string;
    document_name: string;
    mode?: string;
  }): Promise<{
    document_name: string;
    validated_at: string;
    approved: boolean;
    score: number;
    omissions: string[];
    distortions: string[];
    structural_issues: string[];
    observations: string;
    error?: string;
  }> {
    const response = await this.axios.post('/quality/validate', data, {
      timeout: 15 * 60 * 1000,
    });
    return response.data;
  }

  async applyQualityFix(data: {
    content: string;
    fix_type: 'structural' | 'semantic';
    document_name?: string;
    issues?: string[];
  }): Promise<{
    success: boolean;
    fixed_content?: string;
    fixes_applied: string[];
    size_reduction?: string;
    suggestions?: string;
    error?: string;
  }> {
    const response = await this.axios.post('/quality/fix', data);
    return response.data;
  }

  async regenerateWordDocument(data: {
    content: string;
    document_name: string;
    output_dir?: string;
  }): Promise<{
    success: boolean;
    output_path?: string;
    error?: string;
  }> {
    const response = await this.axios.post('/quality/regenerate-word', data);
    return response.data;
  }



  async getQualityServiceHealth(): Promise<{ status: string; service: string; mlx_available: boolean }> {
    const response = await this.axios.get('/quality/health');
    return response.data;
  }



  // HIL Quality Control Methods
  async analyzeDocumentHIL(data: {
    content: string;
    document_name: string;
    raw_content?: string;
    mode?: string;
  }): Promise<{
    document_name: string;
    analyzed_at: string;
    total_issues: number;
    mode?: string;
    pending_fixes: Array<{
      id: string;
      type: string;
      fix_type?: string;
      description: string;
      action: string;
      severity: string;
      table_heading?: string;
      strategy?: string;
      section_title?: string;
      subtopic_title?: string;
      subtopic_level?: number;
      before_section?: string;
      current_section?: string;
      target_section?: string;
      after_section?: string;
      fingerprint?: string;
      line_index?: number;
      duplicate_kind?: string;
      duplicate_of_index?: number;
      similarity_score?: number;
      jaccard_score?: number;
      heading_line?: number;
      heading_level?: number;
      old_title?: string;
      new_title?: string;
      old_raw?: string;
      new_raw?: string;
      rename_source?: string;
      diff_preview?: string;
      confidence?: number;
      reason?: string;
    }>;
    requires_approval: boolean;
    // v4.0 Content Validation Fields
    compression_ratio?: number;
    compression_warning?: string;
    missing_laws?: string[];
    missing_sumulas?: string[];
    missing_decretos?: string[];
    missing_julgados?: string[];
    total_content_issues?: number;
    error?: string;
  }> {
    const response = await this.axios.post('/advanced/audit-structure-rigorous', data, {
      timeout: 15 * 60 * 1000,
    }); // Updated to advanced endpoint
    return response.data;
  }

  async applyApprovedFixes(data: {
    content: string;
    approved_fix_ids: string[];
    mode?: string;
    approved_fixes?: Array<{
      id: string;
      type: string;
      fix_type?: string;
      description: string;
      action: string;
      severity: string;
      fingerprint?: string;
      title?: string;
      heading_line?: number;
      heading_level?: number;
      old_title?: string;
      new_title?: string;
      old_raw?: string;
      new_raw?: string;
      rename_source?: string;
      diff_preview?: string;
      table_heading?: string;
      strategy?: string;
      section_title?: string;
      subtopic_title?: string;
      subtopic_level?: number;
      before_section?: string;
      current_section?: string;
      target_section?: string;
      after_section?: string;
      line_index?: number;
      duplicate_kind?: string;
      duplicate_of_index?: number;
      similarity_score?: number;
      jaccard_score?: number;
      confidence?: number;
      reason?: string;
    }>;
  }): Promise<{
    success: boolean;
    fixed_content?: string;
    fixes_applied: string[];
    size_reduction?: string;
    error?: string;
  }> {
    const structuralTypes = new Set([
      "duplicate_paragraph",
      "duplicate_section",
      "heading_numbering",
      "table_misplacement",
      "heading_semantic_mismatch",
      "parent_child_topic_drift",
      "near_duplicate_heading",
    ]);
    const nonStructural = (data.approved_fixes || []).filter((fix) => {
      const explicitFixType = String(fix?.fix_type || "").trim().toLowerCase();
      if (explicitFixType) return explicitFixType !== "structural";
      const issueType = String(fix?.type || "").trim().toLowerCase();
      if (!issueType) return false;
      return !structuralTypes.has(issueType);
    });
    if (nonStructural.length > 0) {
      throw new Error(
        "applyApprovedFixes aceita apenas correções estruturais. Use applyTranscriptionRevisions ou applyUnifiedHilFixes para conteúdo/semântica."
      );
    }
    const response = await this.axios.post('/quality/apply-approved', data);
    return response.data;
  }

  /**
   * Apply transcription HIL revisions (structural + content fixes)
   */
  async applyTranscriptionRevisions(data: {
    job_id?: string;
    content?: string;
    raw_content?: string;
    approved_issues: any[];
    model_selection?: string;
  }): Promise<{
    revised_content: string;
    changes_made: number;
    issues_applied?: string[];
    applied_issue_ids?: string[];
    structural_fixes_applied?: string[];
    content_fixes_applied?: string[];
    structural_error?: string;
    content_error?: string;
    content_changed?: boolean;
    content_change?: {
      before_chars?: number;
      after_chars?: number;
      delta_chars?: number;
    };
    skipped_issue_ids?: string[];
    skipped_reason?: string;
    model_used?: string | null;
  }> {
    const response = await this.axios.post('/transcription/apply-revisions', data, {
      timeout: 15 * 60 * 1000,
    });
    return response.data;
  }

  /**
   * Persist conversion of preventive audit alerts into HIL issues for a job.
   * This updates the job snapshot (audit_issues.json + result.json) on the backend.
   */
  async convertPreventiveAlertsToHil(job_id: string): Promise<{
    job_id: string;
    added: number;
    total: number;
    audit_issues: any[];
  }> {
    const response = await this.axios.post(`/transcription/jobs/${job_id}/convert-preventive-to-hil`, null, {
      timeout: 2 * 60 * 1000,
    });
    return response.data;
  }

  /**
   * Persistently merge audit issues into a transcription job snapshot.
   * Useful for "sending" Quality content alerts to the HIL Corrections tab.
   */
  async mergeTranscriptionAuditIssues(job_id: string, issues: any[]): Promise<{
    job_id: string;
    added: number;
    total: number;
    audit_issues: any[];
  }> {
    const response = await this.axios.post(
      `/transcription/jobs/${job_id}/audit-issues/merge`,
      { issues },
      { timeout: 2 * 60 * 1000 }
    );
    return response.data;
  }

  /**
   * Apply AI-assisted revisions to a hearing/meeting job snapshot.
   * Persists updated hearing payload on the backend.
   */
  async applyHearingRevisions(job_id: string, data: {
    approved_issues: any[];
    model_selection?: string;
    regenerate_formatted?: boolean;
  }): Promise<{
    success: boolean;
    changes_made: number;
    issues_applied?: string[];
    segment_error?: string | null;
    content_error?: string | null;
    model_used?: string;
    mode?: string;
    payload?: any;
  }> {
    const response = await this.axios.post(`/transcription/jobs/${job_id}/hearing/apply-revisions`, data, {
      timeout: 15 * 60 * 1000,
    });
    return response.data;
  }

  // ============= UNIFIED HIL (Structural + Semantic) =============

  /**
   * Convert validation results to unified HIL issues with patches
   */
  async convertToHilIssues(data: {
    raw_content: string;
    formatted_content: string;
    document_name?: string;
    omissions?: string[];
    distortions?: string[];
    include_structural?: boolean;
    model_selection?: string;
  }): Promise<{
    document_name: string;
    converted_at: string;
    total_issues: number;
    hil_issues: Array<{
      id: string;
      type: string;
      description: string;
      action: string;
      severity: string;
      source?: string;
      fingerprint?: string;
      title?: string;
      old_title?: string;
      new_title?: string;
      old_raw?: string;
      new_raw?: string;
      rename_source?: string;
      diff_preview?: string;
      heading_line?: number;
      heading_level?: number;
      patch?: {
        anchor_text?: string;
        old_text?: string;
        new_text?: string;
        confidence?: string;
        confidence_score?: number;
        validation_notes?: string[];
      };
      evidence?: string[];
      confidence?: number;
      confidence_level?: string;
      validation_notes?: string[];
      can_auto_apply?: boolean;
    }>;
    structural_count: number;
    semantic_count: number;
    requires_approval: boolean;
    filtered_false_positives?: number;
    compression_analysis?: {
      ratio: number;
      adjusted_ratio?: number;
      status: string;
      is_intentional_summarization: boolean;
      notes: string[];
    };
    error?: string;
  }> {
    const response = await this.axios.post('/quality/convert-to-hil', data, {
      timeout: 5 * 60 * 1000, // 5 min for AI patch generation
    });
    return response.data;
  }

  /**
   * Generate legal checklist from document content
   */
  async generateLegalChecklist(data: {
    content: string;
    document_name?: string;
    include_counts?: boolean;
    append_to_content?: boolean;
  }): Promise<{
    document_name: string;
    total_references: number;
    checklist_markdown: string;
    content_with_checklist?: string;
    controle_concentrado: Array<{ identifier: string; count: number }>;
    sumulas_vinculantes: Array<{ identifier: string; count: number }>;
    sumulas_stf: Array<{ identifier: string; count: number }>;
    sumulas_stj: Array<{ identifier: string; count: number }>;
    recursos_repetitivos: Array<{ identifier: string; count: number }>;
    temas_repetitivos: Array<{ identifier: string; count: number }>;
    iac: Array<{ identifier: string; count: number }>;
    irdr: Array<{ identifier: string; count: number }>;
    constituicao: Array<{ identifier: string; count: number }>;
    leis_federais: Array<{ identifier: string; count: number }>;
    codigos: Array<{ identifier: string; count: number }>;
  }> {
    const response = await this.axios.post('/quality/generate-checklist', data);
    return response.data;
  }

  // =========================================================================
  // HEARING/MEETING QUALITY API
  // =========================================================================

  /**
   * Validate hearing/meeting transcription
   */
  async validateHearing(data: {
    segments: Array<{
      id?: string;
      text: string;
      speaker_id?: string;
      speaker_label?: string;
      speaker_role?: string;
      start?: number;
      end?: number;
      confidence?: number;
    }>;
    speakers?: Array<{
      speaker_id: string;
      name?: string;
      label?: string;
      role?: string;
      party?: string;
    }>;
    formatted_content?: string;
    raw_content?: string;
    document_name?: string;
    mode?: string;
  }): Promise<{
    document_name: string;
    validated_at: string;
    approved: boolean;
    score: number;
    mode: string;
    completude_rate: number;
    speaker_identification_rate: number;
    evidence_preservation_rate: number;
    chronology_valid: boolean;
    issues: Array<{
      id: string;
      type: string;
      description: string;
      severity: string;
      segment_id?: string;
      speaker_id?: string;
      timestamp?: string;
      suggestion?: string;
    }>;
    total_issues: number;
    requires_review: boolean;
    review_reason?: string;
    critical_areas: string[];
    error?: string;
  }> {
    const response = await this.axios.post('/quality/validate-hearing', data, {
      timeout: 15 * 60 * 1000,
    });
    return response.data;
  }

  /**
   * Analyze hearing segments for detailed issues
   */
  async analyzeHearingSegments(data: {
    segments: Array<{
      id?: string;
      text: string;
      speaker_id?: string;
      speaker_label?: string;
      start?: number;
      end?: number;
    }>;
    speakers?: Array<{
      speaker_id: string;
      name?: string;
      label?: string;
      role?: string;
    }>;
    document_name?: string;
    include_contradictions?: boolean;
  }): Promise<{
    document_name: string;
    analyzed_at: string;
    total_segments: number;
    segments_with_issues: number;
    issues_by_segment: Record<string, Array<{
      segment_id: string;
      type: string;
      description: string;
      severity: string;
      speaker_label?: string;
      timestamp_range?: string;
    }>>;
    summary: Record<string, number>;
  }> {
    const response = await this.axios.post('/quality/analyze-hearing-segments', data, {
      timeout: 15 * 60 * 1000,
    });
    return response.data;
  }

  /**
   * Generate hearing-specific legal checklist with speaker attribution
   */
  async generateHearingChecklist(data: {
    segments: Array<{
      id?: string;
      text: string;
      speaker_id?: string;
      speaker_label?: string;
      start?: number;
      end?: number;
    }>;
    speakers?: Array<{
      speaker_id: string;
      name?: string;
      label?: string;
      role?: string;
    }>;
    formatted_content?: string;
    document_name?: string;
    include_timeline?: boolean;
    group_by_speaker?: boolean;
  }): Promise<{
    document_name: string;
    total_references: number;
    by_speaker: Record<string, Array<{
      identifier: string;
      category: string;
      timestamp?: string;
      segment_id?: string;
      context?: string;
    }>>;
    by_category: Record<string, Array<{
      identifier: string;
      category: string;
      timestamp?: string;
      speaker?: string;
    }>>;
    timeline: Array<{
      timestamp: string;
      timestamp_seconds?: number;
      speaker: string;
      ref: string;
      category: string;
      segment_id?: string;
    }>;
    checklist_markdown: string;
  }> {
    const response = await this.axios.post('/quality/generate-hearing-checklist', data, {
      timeout: 15 * 60 * 1000,
    });
    return response.data;
  }

  /**
   * Apply unified HIL fixes (structural + semantic)
   */
  async applyUnifiedHilFixes(data: {
    content: string;
    raw_content?: string;
    approved_fixes: Array<{
      id: string;
      type: string;
      description: string;
      action: string;
      severity: string;
      fingerprint?: string;
      title?: string;
      heading_line?: number;
      heading_level?: number;
      old_title?: string;
      new_title?: string;
      old_raw?: string;
      new_raw?: string;
      rename_source?: string;
      diff_preview?: string;
      table_heading?: string;
      strategy?: string;
      section_title?: string;
      subtopic_title?: string;
      subtopic_level?: number;
      before_section?: string;
      current_section?: string;
      target_section?: string;
      after_section?: string;
      patch?: {
        anchor_text?: string;
        old_text?: string;
        new_text?: string;
      };
    }>;
    model_selection?: string;
    mode?: string;
  }): Promise<{
    success: boolean;
    fixed_content?: string;
    fixes_applied: string[];
    structural_applied: number;
    semantic_applied: number;
    size_reduction?: string;
    error?: string;
  }> {
    const response = await this.axios.post('/quality/apply-unified-hil', data, {
      timeout: 5 * 60 * 1000,
    });
    return response.data;
  }

  // =========================================================================
  // GRAPH VISUALIZATION METHODS
  // =========================================================================

  /**
   * Export graph data for visualization
   */
  async getGraphData(params: {
    entity_ids?: string;
    document_ids?: string;
    case_ids?: string;
    types?: string;
    groups?: string;
    max_nodes?: number;
    include_relationships?: boolean;
    include_global?: boolean;
  }): Promise<{
    nodes: Array<{
      id: string;
      label: string;
      type: string;
      group: 'legislacao' | 'jurisprudencia' | 'doutrina' | 'outros';
      metadata?: Record<string, unknown>;
      size?: number;
    }>;
    links: Array<{
      source: string;
      target: string;
      type: string;
      label?: string;
      description?: string;
      weight?: number;
      semantic?: boolean;
    }>;
  }> {
    const response = await this.axios.get('/graph/export', { params });
    return response.data;
  }

  /**
   * Get entity details with neighbors and chunks
   */
  async getGraphEntity(
    entityId: string,
    params?: {
      include_global?: boolean;
      document_ids?: string;
      case_ids?: string;
    }
  ): Promise<{
    id: string;
    name: string;
    type: string;
    normalized: string;
    metadata: Record<string, unknown>;
    neighbors: Array<{
      id: string;
      name: string;
      type: string;
      relationship: string;
      weight: number;
    }>;
    chunks: Array<{
      chunk_uid: string;
      text: string;
      doc_title: string;
      source_type: string;
    }>;
  }> {
    const response = await this.axios.get(`/graph/entity/${entityId}`, { params });
    return response.data;
  }

  /**
   * Get remissões (cross-references) for an entity
   */
  async getGraphRemissoes(
    entityId: string,
    params?: {
      include_global?: boolean;
      document_ids?: string;
      case_ids?: string;
    }
  ): Promise<{
    entity_id: string;
    total_remissoes: number;
    legislacao: Array<{
      id: string;
      name: string;
      type: string;
      co_occurrences: number;
      sample_text?: string;
    }>;
    jurisprudencia: Array<{
      id: string;
      name: string;
      type: string;
      co_occurrences: number;
      sample_text?: string;
    }>;
  }> {
    const response = await this.axios.get(`/graph/remissoes/${entityId}`, { params });
    return response.data;
  }

  /**
   * Get semantic neighbors for an entity
   */
  async getGraphSemanticNeighbors(
    entityId: string,
    params: {
      limit?: number;
      include_global?: boolean;
      document_ids?: string;
      case_ids?: string;
    } = {}
  ): Promise<{
    entity_id: string;
    total: number;
    neighbors: Array<{
      id: string;
      name: string;
      type: string;
      group: string;
      strength: number;
      relation: {
        type: string;
        label: string;
        description: string;
      };
      sample_contexts: string[];
      source_docs: string[];
    }>;
  }> {
    const { limit = 30, ...rest } = params;
    const response = await this.axios.get(`/graph/semantic-neighbors/${entityId}`, {
      params: { limit, ...rest },
    });
    return response.data;
  }

  /**
   * Get graph statistics
   */
  async getGraphStats(params?: {
    include_global?: boolean;
    document_ids?: string;
    case_ids?: string;
  }): Promise<{
    total_entities: number;
    total_chunks: number;
    total_documents: number;
    entities_by_type: Record<string, number>;
    relationships_count: number;
  }> {
    const response = await this.axios.get('/graph/stats', { params });
    return response.data;
  }

  /**
   * Find path between two entities
   */
  async getGraphPath(
    sourceId: string,
    targetId: string,
    params: {
      max_length?: number;
      include_global?: boolean;
      document_ids?: string;
      case_ids?: string;
    } = {}
  ): Promise<{
    found: boolean;
    source?: string;
    target?: string;
    paths?: Array<{
      path: string[];
      path_ids: string[];
      relationships: string[];
      length: number;
      nodes?: Array<{
        labels: string[];
        entity_id?: string;
        chunk_uid?: string;
        doc_hash?: string;
        name?: string;
        entity_type?: string;
        normalized?: string;
        chunk_index?: number;
        text_preview?: string;
      }>;
      edges?: Array<{
        type: string;
        from_id: string;
        to_id: string;
        properties: Record<string, unknown>;
      }>;
    }>;
    message?: string;
  }> {
    const { max_length = 4, ...rest } = params;
    const response = await this.axios.get('/graph/path', {
      params: { source_id: sourceId, target_id: targetId, max_length, ...rest },
    });
    return response.data;
  }

  /**
   * Search entities in the graph
   */
  async searchGraphEntities(params: {
    query?: string;
    include_global?: boolean;
    types?: string;
    group?: string;
    limit?: number;
  }): Promise<Array<{
    id: string;
    name: string;
    type: string;
    group: string;
    normalized: string;
    mention_count: number;
  }>> {
    const response = await this.axios.get('/graph/entities', { params });
    return response.data;
  }

  /**
   * Get available relation types
   */
  async getGraphRelationTypes(): Promise<{
    relations: Array<{
      type: string;
      label: string;
      description: string;
      semantic: boolean;
    }>;
    entity_groups: Record<string, string>;
  }> {
    const response = await this.axios.get('/graph/relation-types');
    return response.data;
  }

  /**
   * Lexical search for entities in the graph
   * Searches by terms, legal devices, and authors/tribunals
   */
  async graphLexicalSearch(params: {
    terms?: string[];
    devices?: string[];
    authors?: string[];
    matchMode?: 'any' | 'all';
    types?: string[];
    limit?: number;
    includeGlobal?: boolean;
  }): Promise<Array<{
    id: string;
    name: string;
    type: string;
    group: string;
    normalized: string;
    mention_count: number;
    metadata?: Record<string, unknown>;
  }>> {
    const response = await this.axios.post('/graph/lexical-search', {
      terms: params.terms || [],
      devices: params.devices || [],
      authors: params.authors || [],
      match_mode: params.matchMode || 'any',
      types: params.types || ['lei', 'artigo', 'sumula', 'jurisprudencia', 'tema', 'tribunal'],
      limit: params.limit || 100,
      include_global: params.includeGlobal ?? true,
    });
    return response.data;
  }

  /**
   * Add entities from RAG local documents to the graph
   * Extracts legal entities from specified documents and adds them to Neo4j
   */
  async graphAddFromRAG(params: {
    documentIds?: string[];
    caseIds?: string[];
    extractSemantic?: boolean;
  }): Promise<{
    documents_processed: number;
    chunks_processed: number;
    entities_extracted: number;
    entities_added: number;
    entities_existing: number;
    relationships_created: number;
    entities: Array<{
      entity_id: string;
      entity_type: string;
      name: string;
      normalized: string;
    }>;
  }> {
    const response = await this.axios.post('/graph/add-from-rag', {
      document_ids: params.documentIds || [],
      case_ids: params.caseIds || [],
      extract_semantic: params.extractSemantic ?? true,
    });
    return response.data;
  }

  /**
   * Content search (OpenSearch BM25) -> entity_ids to seed the graph visualization
   */
  async graphContentSearch(params: {
    query: string;
    types?: string[];
    groups?: string[];
    maxChunks?: number;
    maxEntities?: number;
    includeGlobal?: boolean;
    documentIds?: string[];
    caseIds?: string[];
  }): Promise<{
    query: string;
    chunks_count: number;
    entities_count: number;
    entity_ids: string[];
    entities: Array<{
      entity_id: string;
      entity_type: string;
      name: string;
      normalized: string;
      mentions_in_results: number;
      group: string;
    }>;
  }> {
    const response = await this.axios.post('/graph/content-search', {
      query: params.query,
      types: params.types || ['lei', 'artigo', 'sumula', 'jurisprudencia', 'tema', 'tribunal', 'tese', 'conceito'],
      groups: params.groups || ['legislacao', 'jurisprudencia', 'doutrina'],
      max_chunks: params.maxChunks ?? 15,
      max_entities: params.maxEntities ?? 30,
      include_global: params.includeGlobal ?? true,
      document_ids: params.documentIds || [],
      case_ids: params.caseIds || [],
    });
    return response.data;
  }

  // ============= ORGANIZATIONS =============

  async createOrganization(data: { name: string; cnpj?: string; oab_section?: string }): Promise<any> {
    const response = await this.axios.post('/organizations/', data);
    return response.data;
  }

  async getCurrentOrganization(): Promise<any> {
    const response = await this.axios.get('/organizations/current');
    return response.data;
  }

  async updateOrganization(data: { name?: string; cnpj?: string; oab_section?: string }): Promise<any> {
    const response = await this.axios.put('/organizations/current', data);
    return response.data;
  }

  async getOrgMembers(): Promise<any[]> {
    const response = await this.axios.get('/organizations/members');
    return response.data;
  }

  async inviteMember(email: string, role: string = 'advogado'): Promise<any> {
    const response = await this.axios.post('/organizations/members/invite', { email, role });
    return response.data;
  }

  async updateMemberRole(userId: string, role: string): Promise<any> {
    const response = await this.axios.put(`/organizations/members/${userId}/role`, { role });
    return response.data;
  }

  async removeMember(userId: string): Promise<void> {
    await this.axios.delete(`/organizations/members/${userId}`);
  }

  async getOrgTeams(): Promise<any[]> {
    const response = await this.axios.get('/organizations/teams');
    return response.data;
  }

  async getMyOrgTeams(): Promise<any[]> {
    const response = await this.axios.get('/organizations/teams/mine');
    return response.data;
  }

  async createTeam(data: { name: string; description?: string }): Promise<any> {
    const response = await this.axios.post('/organizations/teams', data);
    return response.data;
  }

  async addTeamMember(teamId: string, userId: string): Promise<any> {
    const response = await this.axios.post(`/organizations/teams/${teamId}/members`, { user_id: userId });
    return response.data;
  }

  async removeTeamMember(teamId: string, userId: string): Promise<void> {
    await this.axios.delete(`/organizations/teams/${teamId}/members/${userId}`);
  }

  // =========================================================================
  // Agent Tasks (Background Agents)
  // =========================================================================

  async spawnAgentTask(data: {
    prompt: string;
    model?: string;
    system_prompt?: string;
    context?: string;
    metadata?: Record<string, any>;
  }): Promise<{ task_id: string; status: string }> {
    const response = await this.axios.post('/agent/spawn', data);
    return response.data;
  }

  async listAgentTasks(): Promise<AgentTask[]> {
    const response = await this.axios.get<AgentTask[]>('/agent/tasks');
    return response.data;
  }

  async getAgentTask(taskId: string): Promise<AgentTask> {
    const response = await this.axios.get<AgentTask>(`/agent/tasks/${taskId}`);
    return response.data;
  }

  async cancelAgentTask(taskId: string): Promise<{ task_id: string; status: string }> {
    const response = await this.axios.delete(`/agent/tasks/${taskId}`);
    return response.data;
  }

  // =========================================================================
  // Context Bridge (Cross-layer transfers)
  // =========================================================================

  async promoteToAgent(data: {
    chat_id?: string;
    messages: Array<{ role: string; content: string }>;
    prompt: string;
    model?: string;
    system_prompt?: string;
  }): Promise<{ task_id: string; session_id: string; status: string }> {
    const response = await this.axios.post('/context/promote-to-agent', data);
    return response.data;
  }

  async exportToWorkflow(data: {
    agent_task_id: string;
    workflow_id?: string;
  }): Promise<{ session_id: string; agent_result: string | null; status: string }> {
    const response = await this.axios.post('/context/export-to-workflow', data);
    return response.data;
  }

  async getContextSession(sessionId: string): Promise<{
    session_id: string;
    items: Array<Record<string, any>>;
    meta: Record<string, any> | null;
  }> {
    const response = await this.axios.get(`/context/session/${sessionId}`);
    return response.data;
  }

  // =========================================================================
  // Workflows (Visual Workflow Builder)
  // =========================================================================

  async createWorkflow(data: {
    name: string;
    description?: string;
    graph_json: { nodes: any[]; edges: any[] };
    tags?: string[];
    is_template?: boolean;
  }): Promise<WorkflowResponse> {
    const response = await this.axios.post('/workflows', data);
    return response.data;
  }

  async generateWorkflowFromNL(description: string, model: string = 'claude'): Promise<{ graph_json: { nodes: any[]; edges: any[] } }> {
    const response = await this.axios.post('/workflows/generate-from-nl', { description, model });
    return response.data;
  }

  async listWorkflows(): Promise<WorkflowResponse[]> {
    const response = await this.axios.get<WorkflowResponse[]>('/workflows');
    return response.data;
  }

  async getWorkflow(workflowId: string): Promise<WorkflowResponse> {
    const response = await this.axios.get<WorkflowResponse>(`/workflows/${workflowId}`);
    return response.data;
  }

  async updateWorkflow(workflowId: string, data: {
    name?: string;
    description?: string;
    graph_json?: { nodes: any[]; edges: any[] };
    tags?: string[];
    is_active?: boolean;
  }): Promise<WorkflowResponse> {
    const response = await this.axios.put(`/workflows/${workflowId}`, data);
    return response.data;
  }

  async deleteWorkflow(workflowId: string): Promise<void> {
    await this.axios.delete(`/workflows/${workflowId}`);
  }

  async runWorkflow(workflowId: string, data: {
    input_data?: Record<string, any>;
    context_session_id?: string;
  }): Promise<Response> {
    const token = this.getAccessToken();
    return fetch(`${API_URL}/workflows/${workflowId}/run`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(data),
    });
  }

  async resumeWorkflowRun(runId: string, data: {
    approved: boolean;
    human_edits?: Record<string, any>;
  }): Promise<Response> {
    const token = this.getAccessToken();
    return fetch(`${API_URL}/workflows/runs/${runId}/resume`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(data),
    });
  }

  async listWorkflowRuns(workflowId: string): Promise<WorkflowRunResponse[]> {
    const response = await this.axios.get<WorkflowRunResponse[]>(`/workflows/${workflowId}/runs`);
    return response.data;
  }

  // ── Admin Monitoring Dashboard ────────────────────────────

  async getAdminDashboard(): Promise<{
    workflows: Array<{
      id: string;
      name: string;
      status: string;
      category: string | null;
      run_count: number;
      created_by: string;
      updated_at: string | null;
    }>;
    total: number;
    by_status: Record<string, number>;
  }> {
    const response = await this.axios.get('/workflows/admin/dashboard');
    return response.data;
  }

  async getApprovalQueue(): Promise<{
    pending: Array<{
      id: string;
      name: string;
      submitted_by: string | null;
      submitted_at: string | null;
      description: string | null;
    }>;
    count: number;
  }> {
    const response = await this.axios.get('/workflows/admin/approval-queue');
    return response.data;
  }

  // ── Publishing & Approval ──────────────────────────────────

  async submitWorkflowForApproval(workflowId: string, notes?: string): Promise<{ status: string; submitted_at: string }> {
    const response = await this.axios.post(`/workflows/${workflowId}/submit`, { notes });
    return response.data;
  }

  async approveWorkflow(workflowId: string, approved: boolean, reason?: string): Promise<{ status: string }> {
    const response = await this.axios.post(`/workflows/${workflowId}/approve`, { approved, reason });
    return response.data;
  }

  async publishWorkflow(workflowId: string): Promise<{ status: string; version: number }> {
    const response = await this.axios.post(`/workflows/${workflowId}/publish`);
    return response.data;
  }

  async archiveWorkflow(workflowId: string): Promise<{ status: string }> {
    const response = await this.axios.post(`/workflows/${workflowId}/archive`);
    return response.data;
  }

  // ── Follow-up & Sharing ──────────────────────────────────

  async followUpRun(runId: string, question: string): Promise<Response> {
    const token = this.getAccessToken();
    return fetch(`${API_URL}/workflows/runs/${runId}/follow-up`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ question }),
    });
  }

  async shareRun(runId: string, userIds: string[], message?: string): Promise<{ status: string; shared_with: string[] }> {
    const response = await this.axios.post(`/workflows/runs/${runId}/share`, {
      user_ids: userIds,
      message,
    });
    return response.data;
  }

  async shareRunWithOrg(runId: string, message?: string): Promise<{ status: string; organization_id: string }> {
    const response = await this.axios.post(`/workflows/runs/${runId}/share-org`, { message });
    return response.data;
  }

  async getWorkflowCatalog(params?: { category?: string; output_type?: string; search?: string }): Promise<any[]> {
    const searchParams = new URLSearchParams();
    if (params?.category) searchParams.set('category', params.category);
    if (params?.output_type) searchParams.set('output_type', params.output_type);
    if (params?.search) searchParams.set('search', params.search);
    const response = await this.axios.get(`/workflows/catalog?${searchParams.toString()}`);
    return response.data;
  }

  async cloneWorkflowTemplate(templateId: string): Promise<WorkflowResponse> {
    const response = await this.axios.post(`/workflows/${templateId}/clone`);
    return response.data;
  }

  async improveWorkflow(workflowId: string): Promise<{ suggestions: any[]; summary: string }> {
    const response = await this.axios.post(`/workflows/${workflowId}/improve`);
    return response.data;
  }

  // ===========================================================================
  // Corpus
  // ===========================================================================

  async getCorpusStats(): Promise<any> {
    const response = await this.axios.get('/corpus/stats');
    return response.data;
  }

  async getCorpusCollections(): Promise<any[]> {
    const response = await this.axios.get('/corpus/collections');
    return response.data;
  }

  async getCorpusDocuments(params?: {
    scope?: string;
    group_id?: string;
    collection?: string;
    status?: string;
    search?: string;
    page?: number;
    per_page?: number;
  }): Promise<any> {
    const response = await this.axios.get('/corpus/documents', { params });
    return response.data;
  }

  async getCorpusDocumentSource(documentId: string): Promise<{
    document_id: string;
    name: string;
    original_name: string;
    file_type: string | null;
    size_bytes: number | null;
    available: boolean;
    source_url: string | null;
    viewer_url: string | null;
    download_url: string | null;
    viewer_kind: 'pdf_native' | 'office_html' | 'external' | 'unavailable' | null;
    preview_status: 'ready' | 'processing' | 'failed' | 'not_supported' | null;
    page_count: number | null;
    metadata: Record<string, any> | null;
  }> {
    const response = await this.axios.get(`/corpus/documents/${documentId}/source`);
    return response.data;
  }

  async getCorpusDocumentViewerManifest(documentId: string): Promise<{
    document_id: string;
    viewer_kind: 'pdf_native' | 'office_html' | 'external' | 'unavailable';
    viewer_url: string | null;
    download_url: string | null;
    source_url: string | null;
    page_count: number | null;
    supports_highlight: boolean;
    supports_page_jump: boolean;
    preview_status: 'ready' | 'processing' | 'failed' | 'not_supported';
    metadata: Record<string, any> | null;
  }> {
    const response = await this.axios.get(`/corpus/documents/${documentId}/viewer-manifest`);
    return response.data;
  }

  getCorpusDocumentContentUrl(documentId: string, options?: { download?: boolean }): string {
    const search = options?.download ? '?download=true' : '';
    return `/api/corpus/documents/${encodeURIComponent(documentId)}/content${search}`;
  }

  getCorpusDocumentPreviewUrl(
    documentId: string,
    options?: { page?: number; q?: string; chunk?: string }
  ): string {
    const params = new URLSearchParams();
    if (options?.page && Number.isFinite(options.page)) params.set('page', String(options.page));
    if (options?.q) params.set('q', options.q);
    if (options?.chunk) params.set('chunk', options.chunk);
    const query = params.toString();
    return `/api/corpus/documents/${encodeURIComponent(documentId)}/preview${query ? `?${query}` : ''}`;
  }

  getCorpusViewerRouteUrl(
    documentId: string,
    options?: { page?: number; q?: string; chunk?: string; openExternally?: boolean }
  ): string {
    const params = new URLSearchParams();
    params.set('documentId', documentId);
    if (options?.page && Number.isFinite(options.page)) params.set('page', String(options.page));
    if (options?.q) params.set('q', options.q);
    if (options?.chunk) params.set('chunk', options.chunk);
    if (options?.openExternally) params.set('external', '1');
    const query = params.toString();
    return `/corpus/viewer${query ? `?${query}` : ''}`;
  }

  async ingestCorpusDocuments(data: {
    document_ids: string[];
    collection: string;
    scope: string;
    jurisdiction?: string;
    source_id?: string;
    group_ids?: string[];
  }): Promise<any> {
    const response = await this.axios.post('/corpus/ingest', data);
    return response.data;
  }

  async getCorpusRegionalSources(): Promise<{
    sources: Array<{
      id: string;
      label: string;
      jurisdiction: string;
      collections: string[];
      domains: string[];
      description?: string | null;
      status?: string | null;
      sync?: string | null;
    }>;
    jurisdictions: string[];
    updated_at?: string | null;
  }> {
    const response = await this.axios.get('/corpus/sources/regional');
    return response.data;
  }

  async deleteCorpusDocument(documentId: string): Promise<any> {
    const response = await this.axios.delete(`/corpus/documents/${documentId}`);
    return response.data;
  }

  async promoteCorpusDocument(documentId: string): Promise<any> {
    const response = await this.axios.post(`/corpus/documents/${documentId}/promote`);
    return response.data;
  }

  async extendCorpusDocumentTTL(documentId: string, days: number): Promise<any> {
    const response = await this.axios.post(`/corpus/documents/${documentId}/extend-ttl`, { days });
    return response.data;
  }

  // ===========================================================================
  // Corpus Projects
  // ===========================================================================

  async createCorpusProject(data: {
    name: string;
    description?: string;
    is_knowledge_base?: boolean;
    scope?: string;
    max_documents?: number;
    retention_days?: number | null;
    metadata?: Record<string, any>;
  }): Promise<any> {
    const response = await this.axios.post('/corpus/projects', data);
    return response.data;
  }

  async getCorpusProjects(params?: {
    scope?: string;
    is_knowledge_base?: boolean;
    search?: string;
    page?: number;
    per_page?: number;
  }): Promise<any> {
    const response = await this.axios.get('/corpus/projects', { params });
    return response.data;
  }

  async getCorpusProject(projectId: string): Promise<any> {
    const response = await this.axios.get(`/corpus/projects/${projectId}`);
    return response.data;
  }

  async updateCorpusProject(projectId: string, data: {
    name?: string;
    description?: string;
    is_knowledge_base?: boolean;
    max_documents?: number;
    retention_days?: number | null;
    metadata?: Record<string, any>;
  }): Promise<any> {
    const response = await this.axios.put(`/corpus/projects/${projectId}`, data);
    return response.data;
  }

  async deleteCorpusProject(projectId: string): Promise<any> {
    const response = await this.axios.delete(`/corpus/projects/${projectId}`);
    return response.data;
  }

  async addDocumentsToCorpusProject(projectId: string, documentIds: string[], folderPath?: string): Promise<any> {
    const response = await this.axios.post(`/corpus/projects/${projectId}/documents`, {
      document_ids: documentIds,
      folder_path: folderPath,
    });
    return response.data;
  }

  async removeDocumentFromCorpusProject(projectId: string, documentId: string): Promise<any> {
    const response = await this.axios.delete(`/corpus/projects/${projectId}/documents/${documentId}`);
    return response.data;
  }

  async getCorpusProjectFolders(projectId: string): Promise<any> {
    const response = await this.axios.get(`/corpus/projects/${projectId}/folders`);
    return response.data;
  }

  async createCorpusProjectFolder(projectId: string, folderPath: string): Promise<any> {
    const response = await this.axios.post(`/corpus/projects/${projectId}/folders`, {
      folder_path: folderPath,
    });
    return response.data;
  }

  async getCorpusProjectDocuments(projectId: string, params?: {
    folder?: string;
    status?: string;
    sort?: string;
    page?: number;
    per_page?: number;
  }): Promise<any> {
    const response = await this.axios.get(`/corpus/projects/${projectId}/documents`, { params });
    return response.data;
  }

  async moveCorpusProjectDocument(projectId: string, documentId: string, folderPath: string | null): Promise<any> {
    const response = await this.axios.patch(`/corpus/projects/${projectId}/documents/${documentId}/move`, {
      folder_path: folderPath,
    });
    return response.data;
  }

  async shareCorpusProject(projectId: string, data: {
    shared_with_user_id?: string;
    shared_with_org_id?: string;
    permission?: string;
  }): Promise<any> {
    const response = await this.axios.post(`/corpus/projects/${projectId}/share`, data);
    return response.data;
  }

  async unshareCorpusProject(projectId: string, shareId: string): Promise<any> {
    const response = await this.axios.delete(`/corpus/projects/${projectId}/share/${shareId}`);
    return response.data;
  }

  async transferCorpusProject(projectId: string, newOwnerId: string): Promise<any> {
    const response = await this.axios.post(`/corpus/projects/${projectId}/transfer`, {
      new_owner_id: newOwnerId,
    });
    return response.data;
  }

  // ===========================================================================
  // Corpus Admin
  // ===========================================================================

  async getCorpusAdminOverview(): Promise<any> {
    const response = await this.axios.get('/corpus/admin/overview');
    return response.data;
  }

  async getCorpusAdminUsers(params?: { skip?: number; limit?: number }): Promise<any> {
    const response = await this.axios.get('/corpus/admin/users', { params });
    return response.data;
  }

  async getCorpusAdminUserDocuments(
    userId: string,
    params?: { scope?: string; collection?: string; status?: string; skip?: number; limit?: number }
  ): Promise<any> {
    const response = await this.axios.get(`/corpus/admin/users/${userId}/documents`, { params });
    return response.data;
  }

  async transferCorpusDocument(documentId: string, newOwnerId: string): Promise<any> {
    const response = await this.axios.post(`/corpus/admin/transfer/${documentId}`, {
      new_owner_id: newOwnerId,
    });
    return response.data;
  }

  async getCorpusAdminActivity(params?: {
    skip?: number;
    limit?: number;
    user_id?: string;
    action?: string;
  }): Promise<any> {
    const response = await this.axios.get('/corpus/admin/activity', { params });
    return response.data;
  }

  // ---------------------------------------------------------------------------
  // DMS (Document Management System)
  // ---------------------------------------------------------------------------

  async getDMSProviders(): Promise<any> {
    const response = await this.axios.get('/dms/providers');
    return response.data;
  }

  async startDMSConnect(provider: string, displayName?: string, redirectUrl?: string): Promise<any> {
    const response = await this.axios.post('/dms/connect', {
      provider,
      display_name: displayName || '',
      redirect_url: redirectUrl,
    });
    return response.data;
  }

  async getDMSIntegrations(): Promise<any> {
    const response = await this.axios.get('/dms/integrations');
    return response.data;
  }

  async disconnectDMS(integrationId: string): Promise<void> {
    await this.axios.delete(`/dms/integrations/${integrationId}`);
  }

  async getDMSFiles(
    integrationId: string,
    params?: { folder_id?: string; page_token?: string; query?: string }
  ): Promise<any> {
    const response = await this.axios.get(`/dms/integrations/${integrationId}/files`, { params });
    return response.data;
  }

  async importDMSFiles(
    integrationId: string,
    body: { file_ids: string[]; target_corpus_project_id?: string }
  ): Promise<any> {
    const response = await this.axios.post(`/dms/integrations/${integrationId}/import`, body);
    return response.data;
  }

  async triggerDMSSync(integrationId: string, folderIds?: string[]): Promise<any> {
    const response = await this.axios.post(`/dms/integrations/${integrationId}/sync`, {
      folder_ids: folderIds || null,
    });
    return response.data;
  }

  // ── Dashboard ────────────────────────────────────────────────────────

  async getDashboardRecentActivity(): Promise<{
    recent_playbooks: Array<{ id: string; name: string; updated_at: string; rule_count: number }>;
    recent_corpus_projects: Array<{ id: string; name: string; document_count: number; updated_at: string }>;
    recent_chats: Array<{ id: string; title: string; updated_at: string }>;
    recent_review_tables: Array<{ id: string; name: string; status: string; processed_documents: number; total_documents: number }>;
    stats: { total_playbooks: number; total_corpus_docs: number; total_chats: number; total_review_tables: number };
  }> {
    const response = await this.axios.get('/dashboard/recent-activity');
    return response.data;
  }

  // ---------------------------------------------------------------------------
  // Audit Logs (Admin)
  // ---------------------------------------------------------------------------

  async getAuditLogs(params?: {
    user_id?: string;
    action?: string;
    resource_type?: string;
    resource_id?: string;
    date_from?: string;
    date_to?: string;
    search?: string;
    limit?: number;
    offset?: number;
  }): Promise<{
    items: Array<{
      id: string;
      user_id: string;
      user_name: string | null;
      user_email: string | null;
      action: string;
      resource_type: string;
      resource_id: string | null;
      details: Record<string, unknown> | null;
      ip_address: string | null;
      created_at: string;
    }>;
    total: number;
    limit: number;
    offset: number;
  }> {
    const response = await this.axios.get('/audit-logs', { params });
    return response.data;
  }

  async exportAuditLogsCsv(params?: {
    user_id?: string;
    action?: string;
    resource_type?: string;
    date_from?: string;
    date_to?: string;
  }): Promise<Blob> {
    const response = await this.axios.get('/audit-logs/export', {
      params,
      responseType: 'blob',
    });
    return response.data;
  }

  async getAuditLogStats(days?: number): Promise<{
    period_days: number;
    total: number;
    by_action: Record<string, number>;
    by_resource_type: Record<string, number>;
    top_users: Array<{ user_id: string; name: string; count: number }>;
  }> {
    const response = await this.axios.get('/audit-logs/stats', {
      params: { days: days || 30 },
    });
    return response.data;
  }

  // ---------------------------------------------------------------------------
  // Enhanced DMS (provider-level endpoints)
  // ---------------------------------------------------------------------------

  async connectDMSProvider(provider: string, params?: {
    display_name?: string;
    redirect_url?: string;
    server_url?: string;
    library?: string;
  }): Promise<{ auth_url: string; state: string }> {
    const response = await this.axios.post(`/dms/connect/${provider}`, {
      provider,
      ...params,
    });
    return response.data;
  }

  async getDMSFilesByProvider(
    provider: string,
    params?: { path?: string; page_token?: string; query?: string }
  ): Promise<any> {
    const response = await this.axios.get(`/dms/${provider}/files`, { params });
    return response.data;
  }

  async importDMSFilesByProvider(
    provider: string,
    body: { file_ids: string[]; target_corpus_project_id?: string }
  ): Promise<any> {
    const response = await this.axios.post(`/dms/${provider}/import`, body);
    return response.data;
  }

  // ---------------------------------------------------------------------------
  // Review Tables API
  // ---------------------------------------------------------------------------

  // Table operations
  async getReviewTable(tableId: string): Promise<any> {
    const response = await this.axios.get(`/review-tables/${tableId}`);
    return response.data;
  }

  async listReviewTables(skip = 0, limit = 50): Promise<{ tables: any[]; total: number }> {
    const response = await this.axios.get('/review-tables/', {
      params: { skip, limit },
    });
    // Backend returns { items: [...], total } but we normalize to { tables: [...], total }
    const data = response.data;
    return {
      tables: data.items || data.tables || [],
      total: data.total || 0,
    };
  }

  async createReviewTable(data: {
    name: string;
    description?: string;
    document_ids?: string[];
  }): Promise<any> {
    const response = await this.axios.post('/review-tables/', data);
    return response.data;
  }

  async deleteReviewTable(tableId: string): Promise<void> {
    await this.axios.delete(`/review-tables/${tableId}`);
  }

  async getReviewTableDocuments(tableId: string): Promise<any[]> {
    const response = await this.axios.get(`/review-tables/${tableId}/documents`);
    return response.data;
  }

  async addDocumentsToReviewTable(
    tableId: string,
    documentIds: string[]
  ): Promise<any> {
    const response = await this.axios.post(`/review-tables/${tableId}/documents`, {
      document_ids: documentIds,
    });
    return response.data;
  }

  async removeDocumentFromReviewTable(
    tableId: string,
    documentId: string
  ): Promise<void> {
    await this.axios.delete(`/review-tables/${tableId}/documents/${documentId}`);
  }

  // Dynamic Columns
  async createDynamicColumn(
    tableId: string,
    prompt: string,
    name?: string,
    extractionType?: string
  ): Promise<any> {
    const response = await this.axios.post(`/review-tables/${tableId}/dynamic-columns`, {
      prompt,
      name,
      extraction_type: extractionType,
    });
    return response.data;
  }

  async listDynamicColumns(tableId: string): Promise<any[]> {
    const response = await this.axios.get(`/review-tables/${tableId}/dynamic-columns`);
    return response.data?.items ?? response.data ?? [];
  }

  async updateDynamicColumn(
    tableId: string,
    columnId: string,
    data: { name?: string; is_visible?: boolean; order_index?: number }
  ): Promise<any> {
    const response = await this.axios.patch(
      `/review-tables/${tableId}/dynamic-columns/${columnId}`,
      data
    );
    return response.data;
  }

  async deleteDynamicColumn(tableId: string, columnId: string): Promise<void> {
    await this.axios.delete(`/review-tables/${tableId}/dynamic-columns/${columnId}`);
  }

  async reprocessColumn(tableId: string, columnId: string): Promise<any> {
    const response = await this.axios.post(
      `/review-tables/${tableId}/dynamic-columns/${columnId}/reprocess`
    );
    return response.data;
  }

  async reorderColumns(tableId: string, columnIds: string[]): Promise<void> {
    await this.axios.post(`/review-tables/${tableId}/dynamic-columns/reorder`, {
      column_ids: columnIds,
    });
  }

  // Cell operations
  async getReviewTableCells(
    tableId: string,
    options?: { column_id?: string; document_id?: string }
  ): Promise<any[]> {
    const response = await this.axios.get(`/review-tables/${tableId}/cells`, {
      params: options,
    });
    return response.data;
  }

  async verifyCell(
    tableId: string,
    cellId: string,
    verified: boolean,
    correction?: string
  ): Promise<any> {
    const response = await this.axios.patch(`/review-tables/${tableId}/cells/${cellId}/verify`, {
      verified,
      correction,
    });
    return response.data;
  }

  async bulkVerifyCells(
    tableId: string,
    cellIds: string[],
    verified: boolean
  ): Promise<number> {
    const response = await this.axios.post(`/review-tables/${tableId}/cells/bulk-verify`, {
      cell_ids: cellIds,
      verified,
    });
    return response.data.count;
  }

  async getVerificationStats(tableId: string): Promise<any> {
    const response = await this.axios.get(`/review-tables/${tableId}/verification-stats`);
    return response.data;
  }

  async getLowConfidenceCells(tableId: string, threshold = 0.5): Promise<any[]> {
    const response = await this.axios.get(`/review-tables/${tableId}/cells/low-confidence`, {
      params: { threshold },
    });
    return response.data;
  }

  // Ask Table (Chat)
  async askTable(
    tableId: string,
    question: string,
    includeSources = true
  ): Promise<any> {
    const response = await this.axios.post(`/review-tables/${tableId}/ask`, {
      question,
      include_sources: includeSources,
    });
    return response.data;
  }

  async getTableChatHistory(tableId: string, limit = 50): Promise<any[]> {
    const response = await this.axios.get(`/review-tables/${tableId}/chat-history`, {
      params: { limit },
    });
    return response.data;
  }

  async clearTableChatHistory(tableId: string): Promise<void> {
    await this.axios.delete(`/review-tables/${tableId}/chat-history`);
  }

  // Extraction Jobs
  async startExtraction(
    tableId: string,
    columnIds?: string[]
  ): Promise<any> {
    const response = await this.axios.post(`/review-tables/${tableId}/extract`, {
      column_ids: columnIds,
    });
    return response.data;
  }

  async getExtractionJob(tableId: string, jobId: string): Promise<any> {
    const response = await this.axios.get(`/review-tables/${tableId}/jobs/${jobId}`);
    return response.data;
  }

  async listExtractionJobs(tableId: string, limit = 10): Promise<any[]> {
    const response = await this.axios.get(`/review-tables/${tableId}/jobs`, {
      params: { limit },
    });
    return response.data;
  }

  async pauseExtractionJob(tableId: string, jobId: string): Promise<void> {
    await this.axios.post(`/review-tables/${tableId}/jobs/${jobId}/pause`);
  }

  async resumeExtractionJob(tableId: string, jobId: string): Promise<void> {
    await this.axios.post(`/review-tables/${tableId}/jobs/${jobId}/resume`);
  }

  async cancelExtractionJob(tableId: string, jobId: string): Promise<void> {
    await this.axios.post(`/review-tables/${tableId}/jobs/${jobId}/cancel`);
  }

  // Column preview (for testing extraction on sample)
  async previewColumnExtraction(
    tableId: string,
    prompt: string,
    sampleDocumentId?: string
  ): Promise<{ suggested_name: string; extraction_type: string; sample_value: any }> {
    const response = await this.axios.post(`/review-tables/${tableId}/columns/preview`, {
      prompt,
      sample_document_id: sampleDocumentId,
    });
    return response.data;
  }

  // Export
  async exportReviewTable(
    tableId: string,
    format: 'csv' | 'xlsx' | 'json' = 'csv'
  ): Promise<Blob> {
    const response = await this.axios.get(`/review-tables/${tableId}/export`, {
      params: { format },
      responseType: 'blob',
    });
    return response.data;
  }
}

// Exportar instância singleton
const apiClient = new ApiClient();
export const apiBaseUrl = API_URL;
export { apiClient };
export default apiClient;
