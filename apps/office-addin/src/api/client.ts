/**
 * Cliente HTTP para comunicação com a API Vorbium.
 *
 * Gerencia autenticação JWT, refresh de tokens e chamadas HTTP.
 * Adaptado do api-client.ts do apps/web para o contexto do Office Add-in.
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

export async function microsoftSSOLogin(
  microsoftToken: string
): Promise<AuthResponse> {
  const { data } = await api.post<AuthResponse>('/auth/microsoft-sso', {
    microsoft_token: microsoftToken,
    source: 'word-addin',
  });
  setTokens(data.access_token, data.refresh_token);
  return data;
}

export function logout(): void {
  clearTokens();
}

// ── Chat ────────────────────────────────────────────────────────

export interface Chat {
  id: string;
  title: string;
  mode?: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  chat_id: string;
  role: 'user' | 'assistant';
  content: string;
  thinking?: string;
  created_at: string;
}

export async function createChat(title?: string): Promise<Chat> {
  const { data } = await api.post<Chat>('/chats/', {
    title: title || 'Word Add-in Chat',
    mode: 'juridico',
  });
  return data;
}

export async function getChats(): Promise<Chat[]> {
  const { data } = await api.get<Chat[]>('/chats/');
  return data;
}

export async function getChatMessages(chatId: string): Promise<Message[]> {
  const { data } = await api.get<Message[]>(`/chats/${chatId}/messages`);
  return data;
}

// ── Playbooks ───────────────────────────────────────────────────

export interface Playbook {
  id: string;
  name: string;
  description?: string;
  document_type?: string;
  rules_count: number;
  created_at: string;
}

export async function getPlaybooks(): Promise<Playbook[]> {
  const { data } = await api.get<Playbook[]>('/playbooks/');
  return data;
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

// ── Documents ───────────────────────────────────────────────────

export async function uploadDocument(
  file: File,
  title?: string
): Promise<{ id: string; title: string }> {
  const formData = new FormData();
  formData.append('file', file);
  if (title) formData.append('title', title);
  const { data } = await api.post('/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

// ── Word Add-in specific ────────────────────────────────────────

export interface InlineAnalyzeRequest {
  playbook_id: string;
  document_content: string;
  document_format?: 'text' | 'ooxml';
}

export interface ClauseAnalysis {
  id: string;
  text: string;
  classification: 'conforme' | 'nao_conforme' | 'ausente' | 'parcial';
  severity: 'critical' | 'warning' | 'info';
  rule_id: string;
  rule_name: string;
  explanation: string;
  suggested_redline?: string;
}

export interface InlineAnalyzeResponse {
  playbook_id: string;
  clauses: ClauseAnalysis[];
  summary: string;
  total_rules: number;
  compliant: number;
  non_compliant: number;
}

export async function analyzeInlineContent(
  request: InlineAnalyzeRequest
): Promise<InlineAnalyzeResponse> {
  const { data } = await api.post<InlineAnalyzeResponse>(
    '/word-addin/analyze-content',
    request
  );
  return data;
}

// ── Fase 2: Run Playbook + Redlines OOXML ─────────────────────

export interface RedlineData {
  redline_id: string;
  rule_id: string;
  rule_name: string;
  clause_type: string;
  classification: string;
  severity: string;
  original_text: string;
  suggested_text: string;
  explanation: string;
  comment?: string;
  confidence: number;
  applied: boolean;
  rejected: boolean;
  reviewed: boolean;
  created_at: string;
  ooxml?: string;
}

export interface ClauseData {
  rule_id: string;
  rule_name: string;
  clause_type: string;
  found_in_contract: boolean;
  original_text?: string;
  classification: string;
  severity: string;
  explanation: string;
  suggested_redline?: string;
  comment?: string;
  confidence: number;
  redline_id?: string;
}

export interface PlaybookRunStats {
  total_rules: number;
  compliant: number;
  needs_review: number;
  non_compliant: number;
  not_found: number;
  risk_score: number;
  total_redlines: number;
}

export interface RunPlaybookRequest {
  playbook_id: string;
  document_content: string;
  document_format?: 'text' | 'ooxml';
  include_ooxml?: boolean;
}

export interface RunPlaybookResponse {
  success: boolean;
  playbook_id: string;
  playbook_name: string;
  playbook_run_id?: string;
  redlines: RedlineData[];
  clauses: ClauseData[];
  stats: PlaybookRunStats;
  summary: string;
  ooxml_package?: string;
  error?: string;
}

export async function runPlaybook(
  request: RunPlaybookRequest
): Promise<RunPlaybookResponse> {
  const { data } = await api.post<RunPlaybookResponse>(
    '/word-addin/playbook/run',
    request,
    { timeout: 120000 }
  );
  return data;
}

export interface PlaybookListItem {
  id: string;
  name: string;
  description?: string;
  area?: string;
  rules_count: number;
  scope: string;
  party_perspective: string;
}

export interface PlaybookListApiResponse {
  items: PlaybookListItem[];
  total: number;
}

export async function getPlaybooksForAddin(
  search?: string
): Promise<PlaybookListItem[]> {
  const params: Record<string, string> = {};
  if (search) params.search = search;
  const { data } = await api.get<PlaybookListApiResponse>(
    '/word-addin/playbook/list',
    { params }
  );
  return data.items;
}

export interface ApplyRedlineRequest {
  redline_ids: string[];
  strategy?: 'ooxml' | 'comment' | 'replace';
}

export interface ApplyRedlineResponse {
  success: boolean;
  applied: string[];
  failed: string[];
  ooxml_data?: Record<string, string>;
}

export async function applyRedlines(
  request: ApplyRedlineRequest
): Promise<ApplyRedlineResponse> {
  const { data } = await api.post<ApplyRedlineResponse>(
    '/word-addin/redline/apply',
    request
  );
  return data;
}

export interface RejectRedlineResponse {
  success: boolean;
  rejected: string[];
  failed: string[];
}

export async function rejectRedlines(
  redlineIds: string[]
): Promise<RejectRedlineResponse> {
  const { data } = await api.post<RejectRedlineResponse>(
    '/word-addin/redline/reject',
    { redline_ids: redlineIds }
  );
  return data;
}

export interface ApplyAllRedlinesResponse {
  success: boolean;
  total: number;
  applied: number;
  failed: number;
  ooxml_package?: string;
}

export async function applyAllRedlines(
  redlineIds?: string[],
  strategy: 'ooxml' | 'comment' | 'replace' = 'ooxml'
): Promise<ApplyAllRedlinesResponse> {
  const { data } = await api.post<ApplyAllRedlinesResponse>(
    '/word-addin/redline/apply-all',
    { redline_ids: redlineIds, strategy }
  );
  return data;
}

// ── Anonymize ──────────────────────────────────────────────────

export interface AnonymizeRequest {
  content: string;
  entities_to_anonymize?: string[];
}

export interface AnonymizeResponse {
  anonymized_content: string;
  entities_found: Array<{ type: string; original: string; replacement: string }>;
  mapping: Record<string, string>;
}

export async function anonymizeContent(
  request: AnonymizeRequest
): Promise<AnonymizeResponse> {
  const { data } = await api.post<AnonymizeResponse>(
    '/word-addin/anonymize',
    request
  );
  return data;
}

// ── Gap 4: Redline State Persistence ────────────────────────────

export interface RedlineStateData {
  redline_id: string;
  status: 'pending' | 'applied' | 'rejected';
  applied_at?: string | null;
  rejected_at?: string | null;
}

export interface RedlineStateResponse {
  success: boolean;
  redline_id: string;
  status: string;
  message?: string;
}

export interface GetRedlineStatesResponse {
  success: boolean;
  playbook_run_id: string;
  states: RedlineStateData[];
  stats?: {
    total: number;
    pending: number;
    applied: number;
    rejected: number;
  };
}

/**
 * Persiste o estado de um redline como 'applied'.
 * Chamado apos o frontend marcar um redline como aplicado.
 */
export async function persistRedlineApplied(
  playbookRunId: string,
  redlineId: string
): Promise<RedlineStateResponse> {
  const { data } = await api.post<RedlineStateResponse>(
    `/word-addin/redline/state/${playbookRunId}/${redlineId}/applied`
  );
  return data;
}

/**
 * Persiste o estado de um redline como 'rejected'.
 * Chamado apos o frontend marcar um redline como rejeitado.
 */
export async function persistRedlineRejected(
  playbookRunId: string,
  redlineId: string
): Promise<RedlineStateResponse> {
  const { data } = await api.post<RedlineStateResponse>(
    `/word-addin/redline/state/${playbookRunId}/${redlineId}/rejected`
  );
  return data;
}

/**
 * Retorna todos os estados de redlines para um playbook run.
 * Usado para restaurar o progresso ao reabrir o Add-in.
 */
export async function getRedlineStates(
  playbookRunId: string
): Promise<GetRedlineStatesResponse> {
  const { data } = await api.get<GetRedlineStatesResponse>(
    `/word-addin/redline/state/${playbookRunId}`
  );
  return data;
}

// ── Gap 11: Historico de Analises ────────────────────────────────

export interface PlaybookRunHistoryItem {
  id: string;
  playbook_id: string;
  playbook_name: string;
  document_name?: string;
  created_at: string;
  stats: {
    total_rules: number;
    compliant: number;
    needs_review: number;
    non_compliant: number;
    not_found: number;
    risk_score: number;
    total_redlines: number;
  };
}

export interface PlaybookRunHistoryResponse {
  items: PlaybookRunHistoryItem[];
  total: number;
}

/**
 * Busca historico de execucoes de playbook do usuario.
 * Limitado aos ultimos N runs (default 10).
 */
export async function getPlaybookRunHistory(
  limit: number = 10
): Promise<PlaybookRunHistoryResponse> {
  const { data } = await api.get<PlaybookRunHistoryResponse>(
    '/word-addin/user/playbook-runs',
    { params: { limit } }
  );
  return data;
}

export interface RestorePlaybookRunResponse {
  success: boolean;
  playbook_run_id: string;
  playbook_id: string;
  playbook_name: string;
  redlines: RedlineData[];
  clauses: ClauseData[];
  stats: PlaybookRunStats;
  summary: string;
  expires_at?: string;
  error?: string;
}

/**
 * Restaura uma execucao de playbook do cache.
 * Permite continuar revisao de redlines sem re-executar analise.
 */
export async function restorePlaybookRun(
  runId: string
): Promise<RestorePlaybookRunResponse> {
  const { data } = await api.get<RestorePlaybookRunResponse>(
    `/word-addin/playbook/run/${runId}/restore`
  );
  return data;
}

// ── Gap 12: Recomendacao de Playbooks ────────────────────────────

export interface RecommendPlaybookRequest {
  document_excerpt: string;
}

export interface RecommendedPlaybook {
  id: string;
  name: string;
  description?: string;
  area?: string;
  relevance_score: number;
  reason: string;
}

export interface RecommendPlaybookResponse {
  document_type: string;
  confidence: number;
  recommended: RecommendedPlaybook[];
}

/**
 * Recomenda playbooks baseado no conteudo do documento.
 * Envia os primeiros ~2000 caracteres para classificacao.
 */
export async function recommendPlaybook(
  request: RecommendPlaybookRequest
): Promise<RecommendPlaybookResponse> {
  const { data } = await api.post<RecommendPlaybookResponse>(
    '/word-addin/playbook/recommend',
    request
  );
  return data;
}

// ── Exports ─────────────────────────────────────────────────────

export { api, getAccessToken, clearTokens, API_URL };
