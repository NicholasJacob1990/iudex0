/**
 * Cliente HTTP para comunicação com a API Backend
 * 
 * Gerencia autenticação, refresh de tokens e chamadas HTTP
 */

import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios';
import { toast } from 'sonner';

const DEFAULT_API_URL =
  typeof window !== 'undefined'
    ? `${window.location.origin}/api`
    : 'http://localhost:8000/api';

const normalizeApiUrl = (url: string): string => {
  const trimmed = url.replace(/\/+$/, '');
  if (!trimmed) return DEFAULT_API_URL;
  if (trimmed.endsWith('/api')) return trimmed;
  return `${trimmed}/api`;
};

// In the browser, prefer same-origin `/api` (via Next rewrites) to avoid CORS/credentials issues in dev.
// If an env points to a different origin (e.g. http://localhost:8000/api), we still route through `/api`.
const resolveApiUrl = (): string => {
  const env = (process.env.NEXT_PUBLIC_API_URL || '').trim();
  if (typeof window === 'undefined') {
    return normalizeApiUrl(env || DEFAULT_API_URL);
  }
  if (!env) return normalizeApiUrl(DEFAULT_API_URL);
  try {
    const u = new URL(env);
    const sameOrigin = u.origin === window.location.origin;
    if (!sameOrigin) {
      return normalizeApiUrl(DEFAULT_API_URL);
    }
  } catch {
    // allow relative URLs like "/api" or "https://example.com/api"
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

interface GenerateDocumentRequest {
  prompt: string;
  context?: any;
  case_id?: string;
  effort_level?: number;
  use_profile?: 'full' | 'basic' | 'none';
  document_type?: string;
  model?: string;
  chat_personality?: 'juridico' | 'geral';
  context_documents?: string[];
  attachment_mode?: 'rag_local' | 'prompt_injection';

  // Agent Mode
  use_multi_agent?: boolean;
  model_gpt?: string;
  model_claude?: string;
  strategist_model?: string;
  drafter_models?: string[];
  reviewer_models?: string[];
  reasoning_level?: 'low' | 'medium' | 'high';

  web_search?: boolean;
  search_mode?: 'shared' | 'native' | 'hybrid';
  multi_query?: boolean;
  breadth_first?: boolean;
  dense_research?: boolean;
  thinking_level?: 'low' | 'medium' | 'high';
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
  hyde_enabled?: boolean;
  graph_rag_enabled?: boolean;
  graph_hops?: number;
  include_signature?: boolean;
  language?: string;
  tone?: string;
  template_id?: string;
  template_document_id?: string;
  variables?: Record<string, any>;
  hil_outline_enabled?: boolean;
  hil_target_sections?: string[];
  audit_mode?: 'sei_only' | 'research';
  quality_profile?: 'rapido' | 'padrao' | 'rigoroso' | 'auditoria';
  target_section_score?: number;
  target_final_score?: number;
  max_rounds?: number;
  strict_document_gate?: boolean;
  hil_section_policy?: 'none' | 'optional' | 'required';
  hil_final_required?: boolean;
  recursion_limit?: number;
  document_checklist_hint?: Array<{
    id?: string;
    label: string;
    critical: boolean;
  }>;
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
  thesis?: string;
  model?: string;
  min_pages?: number;
  max_pages?: number;
}

interface OutlineResponse {
  outline: string[];
  model?: string;
}

class ApiClient {
  private axios: AxiosInstance;
  private isRefreshing = false;
  private refreshSubscribers: ((token: string) => void)[] = [];

  constructor() {
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
        if (token && config.headers) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Interceptor de respostas - trata erros e refresh de token
    this.axios.interceptors.response.use(
      (response) => response,
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

  private clearTokens(): void {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user');
    }
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
    console.log('[API Client] Login Test - Base URL:', this.axios.defaults.baseURL);
    try {
      const response = await this.axios.post<AuthResponse>('/auth/login-test');
      console.log('[API Client] Login Test - Success:', response.status);
      const { access_token, refresh_token } = response.data;

      this.setAccessToken(access_token);
      this.setRefreshToken(refresh_token);

      return response.data;
    } catch (error: any) {
      console.error('[API Client] Login Test - Error:', error.response?.status, error.response?.data);
      console.error('[API Client] Login Test - Full URL:', this.axios.defaults.baseURL + '/auth/login-test');
      throw error;
    }
  }

  async logout(): Promise<void> {
    try {
      await this.axios.post('/auth/logout');
    } catch (error) {
      console.error('Logout error:', error);
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
    data: { message: string; candidates: { model: string; text: string }[] }
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
              console.error('Failed to parse SSE event:', line);
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

    return fetch(url, {
      ...options,
      headers,
    });
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
    const formData = new FormData();
    formData.append('file', file);
    if (metadata) {
      formData.append('metadata', JSON.stringify(metadata));
    }

    const response = await this.axios.post('/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  }

  async getDocument(documentId: string): Promise<any> {
    const response = await this.axios.get(`/documents/${documentId}`);
    return response.data;
  }

  async deleteDocument(documentId: string): Promise<void> {
    await this.axios.delete(`/documents/${documentId}`);
  }

  async createDocumentFromText(data: { title: string; content: string; tags?: string; folder_id?: string }): Promise<any> {
    const formData = new FormData();
    formData.append('title', data.title);
    formData.append('content', data.content);
    if (data.tags) formData.append('tags', data.tags);
    if (data.folder_id) formData.append('folder_id', data.folder_id);

    const response = await this.axios.post('/documents/from-text', formData, {
      headers: { 'Content-Type': 'multipart/form-data' } // Browser sets boundary automatically
    });
    return response.data;
  }

  async createDocumentFromUrl(data: { url: string; tags?: string; folder_id?: string }): Promise<any> {
    const formData = new FormData();
    formData.append('url', data.url);
    if (data.tags) formData.append('tags', data.tags);
    if (data.folder_id) formData.append('folder_id', data.folder_id);

    const response = await this.axios.post('/documents/from-url', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return response.data;
  }

  async processDocument(documentId: string, options?: any): Promise<any> {
    const response = await this.axios.post(`/documents/${documentId}/process`, options);
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

    const response = await this.axios.get('/library', {
      params,
    });
    return response.data;
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


  async getLibrarians(skip = 0, limit = 50): Promise<any> {
    const response = await this.axios.get('/library/librarians', {
      params: { skip, limit },
    });
    return response.data;
  }

  async createLibraryItem(data: any): Promise<any> {
    const response = await this.axios.post('/library', data);
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
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return response.data;
  }

  async extractTemplateVariables(file: File): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    const response = await this.axios.post('/templates/extract-variables', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return response.data;
  }

  async applyTemplate(file: File, variables: Record<string, any>): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('variables', JSON.stringify(variables));
    const response = await this.axios.post('/templates/apply', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
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

  async searchWeb(query: string): Promise<any> {
    const response = await this.axios.get('/knowledge/web/search', { params: { query } });
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
    }
  ): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('mode', options.mode);
    formData.append('thinking_level', options.thinking_level);
    if (options.custom_prompt) formData.append('custom_prompt', options.custom_prompt);
    if (options.model_selection) formData.append('model_selection', options.model_selection);
    if (options.high_accuracy) formData.append('high_accuracy', 'true');

    const response = await this.axios.post('/transcription/vomo', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      // Aumentar timeout para transcrições longas (10 min)
      timeout: 600000,
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
    },
    onProgress: (stage: string, progress: number, message: string) => void,
    onComplete: (content: string) => void,
    onError: (error: string) => void
  ): Promise<void> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('mode', options.mode);
    formData.append('thinking_level', options.thinking_level);
    if (options.custom_prompt) formData.append('custom_prompt', options.custom_prompt);
    if (options.model_selection) formData.append('model_selection', options.model_selection);
    if (options.high_accuracy) formData.append('high_accuracy', 'true');

    const token = this.getAccessToken();

    try {
      const response = await fetch(`${API_URL}/transcription/vomo/stream`, {
        method: 'POST',
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          Accept: 'text/event-stream',
        },
        body: formData,
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
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        for (const line of lines) {
          console.log('[SSE Raw Line]', line);
          if (line.startsWith('data:')) {
            try {
              const data = JSON.parse(line.slice(5).trim());
              console.log('[SSE Parsed]', data);

              if (data.stage !== undefined) {
                // Progress event
                onProgress(data.stage, data.progress, data.message);
              } else if (data.content !== undefined) {
                // Complete event
                onComplete(data.content);
              } else if (data.error !== undefined) {
                // Error event
                onError(data.error);
              }
            } catch (parseError) {
              console.warn('Failed to parse SSE data:', line);
            }
          }
        }
      }

      // Process any remaining buffer content after stream ends
      if (buffer.trim().startsWith('data:')) {
        try {
          const data = JSON.parse(buffer.trim().slice(5).trim());
          if (data.content !== undefined) {
            onComplete(data.content);
          } else if (data.error !== undefined) {
            onError(data.error);
          }
        } catch (parseError) {
          console.warn('Failed to parse final SSE data:', buffer);
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
    },
    onProgress: (stage: string, progress: number, message: string) => void,
    onComplete: (content: string, filenames: string[], totalFiles: number) => void,
    onError: (error: string) => void
  ): Promise<void> {
    const formData = new FormData();
    files.forEach(f => formData.append('files', f));
    formData.append('mode', options.mode);
    formData.append('thinking_level', options.thinking_level);
    if (options.custom_prompt) formData.append('custom_prompt', options.custom_prompt);
    if (options.model_selection) formData.append('model_selection', options.model_selection);
    if (options.high_accuracy) formData.append('high_accuracy', 'true');

    const token = this.getAccessToken();

    try {
      const response = await fetch(`${API_URL}/transcription/vomo/batch/stream`, {
        method: 'POST',
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          Accept: 'text/event-stream',
        },
        body: formData,
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
              const data = JSON.parse(line.slice(5).trim());

              if (data.stage !== undefined) {
                onProgress(data.stage, data.progress, data.message);
              } else if (data.content !== undefined) {
                onComplete(data.content, data.filenames || [], data.total_files || 1);
              } else if (data.error !== undefined) {
                onError(data.error);
              }
            } catch (parseError) {
              console.warn('Failed to parse SSE data:', line);
            }
          }
        }
      }

      // Process any remaining buffer content after stream ends
      if (buffer.trim().startsWith('data:')) {
        try {
          const data = JSON.parse(buffer.trim().slice(5).trim());
          if (data.content !== undefined) {
            onComplete(data.content, data.filenames || [], data.total_files || 1);
          } else if (data.error !== undefined) {
            onError(data.error);
          }
        } catch (parseError) {
          console.warn('Failed to parse final SSE data:', buffer);
        }
      }
    } catch (error: any) {
      onError(error.message || 'Network error');
    }
  }

  async exportDocx(content: string, filename: string): Promise<Blob> {
    const response = await this.axios.post('/transcription/export/docx',
      { content, filename },
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
    },
    onProgress: (stage: string, progress: number, message: string) => void,
    onComplete: (payload: any) => void,
    onError: (error: string) => void
  ): Promise<void> {
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

    const token = this.getAccessToken();

    try {
      const response = await fetch(`${API_URL}/transcription/hearing/stream`, {
        method: 'POST',
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          Accept: 'text/event-stream',
        },
        body: formData,
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
              const data = JSON.parse(line.slice(5).trim());
              if (data.stage !== undefined) {
                onProgress(data.stage, data.progress, data.message);
              } else if (data.payload !== undefined) {
                onComplete(data.payload);
              } else if (data.error !== undefined) {
                onError(data.error);
              }
            } catch (parseError) {
              console.warn('Failed to parse SSE data:', line);
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
          console.warn('Failed to parse final SSE data:', buffer);
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

  async enrollHearingSpeaker(
    file: File,
    payload: { case_id: string; name: string; role: string }
  ): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('case_id', payload.case_id);
    formData.append('name', payload.name);
    formData.append('role', payload.role);
    const response = await this.axios.post('/transcription/hearing/enroll', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  }

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
    const response = await axios.get(`${API_URL.replace('/api', '')}/health`);
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
    const response = await this.axios.post('/quality/validate', data);
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
  }): Promise<{
    document_name: string;
    analyzed_at: string;
    total_issues: number;
    pending_fixes: Array<{
      id: string;
      type: string;
      description: string;
      action: string;
      severity: string;
      fingerprint?: string;
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
    const response = await this.axios.post('/advanced/audit-structure-rigorous', data); // Updated to advanced endpoint
    return response.data;
  }

  async applyApprovedFixes(data: {
    content: string;
    approved_fix_ids: string[];
  }): Promise<{
    success: boolean;
    fixed_content?: string;
    fixes_applied: string[];
    size_reduction?: string;
    error?: string;
  }> {
    const response = await this.axios.post('/quality/apply-approved', data);
    return response.data;
  }
}

// Exportar instância singleton
const apiClient = new ApiClient();
export { apiClient };
export default apiClient;
