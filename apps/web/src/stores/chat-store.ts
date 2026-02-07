import { create } from 'zustand';
import { AISimulationService } from '@/services/ai-simulation';
import { AgentOrchestrator, AgentStep } from '@/services/agents/agent-orchestrator';
import { nanoid } from 'nanoid';
import apiClient, { apiBaseUrl } from '@/lib/api-client';
import { resolveAutoAttachmentMode } from '@/lib/attachment-limits';
import { toast } from 'sonner';
import { useCanvasStore } from '@/stores/canvas-store';
import { useBillingStore } from '@/stores/billing-store';

const MULTI_MODEL_VIEW_STORAGE_KEY = 'iudex_multi_model_view';
const CHAT_PERSONALITY_KEY = 'iudex_chat_personality';
const CHAT_DRAFTS_KEY_PREFIX = 'iudex_chat_drafts_';
const WEB_SEARCH_STORAGE_KEY = 'iudex_web_search';
const MCP_TOOL_CALLING_STORAGE_KEY = 'iudex_mcp_tool_calling';
const MCP_USE_ALL_SERVERS_STORAGE_KEY = 'iudex_mcp_use_all_servers';
const MCP_SERVER_LABELS_STORAGE_KEY = 'iudex_mcp_server_labels';
const LANGGRAPH_WEB_SEARCH_MODEL_STORAGE_KEY = 'iudex_langgraph_web_search_model';
const DENSE_RESEARCH_STORAGE_KEY = 'iudex_dense_research';
const RESEARCH_POLICY_STORAGE_KEY = 'iudex_research_policy';
const DEEP_RESEARCH_PROVIDER_STORAGE_KEY = 'iudex_deep_research_provider';
const DEEP_RESEARCH_MODEL_STORAGE_KEY = 'iudex_deep_research_model';
const DEEP_RESEARCH_EFFORT_STORAGE_KEY = 'iudex_deep_research_effort';
const DEEP_RESEARCH_SEARCH_FOCUS_STORAGE_KEY = 'iudex_deep_research_search_focus';
const DEEP_RESEARCH_DOMAIN_FILTER_STORAGE_KEY = 'iudex_deep_research_domain_filter';
const DEEP_RESEARCH_SEARCH_AFTER_DATE_STORAGE_KEY = 'iudex_deep_research_search_after_date';
const DEEP_RESEARCH_SEARCH_BEFORE_DATE_STORAGE_KEY = 'iudex_deep_research_search_before_date';
const DEEP_RESEARCH_LAST_UPDATED_AFTER_STORAGE_KEY = 'iudex_deep_research_last_updated_after';
const DEEP_RESEARCH_LAST_UPDATED_BEFORE_STORAGE_KEY = 'iudex_deep_research_last_updated_before';
const DEEP_RESEARCH_COUNTRY_STORAGE_KEY = 'iudex_deep_research_country';
const DEEP_RESEARCH_LATITUDE_STORAGE_KEY = 'iudex_deep_research_latitude';
const DEEP_RESEARCH_LONGITUDE_STORAGE_KEY = 'iudex_deep_research_longitude';
const PERPLEXITY_SEARCH_MODE_STORAGE_KEY = 'iudex_perplexity_search_mode';
const PERPLEXITY_SEARCH_TYPE_STORAGE_KEY = 'iudex_perplexity_search_type';
const PERPLEXITY_SEARCH_CONTEXT_SIZE_STORAGE_KEY = 'iudex_perplexity_search_context_size';
const PERPLEXITY_SEARCH_CLASSIFIER_STORAGE_KEY = 'iudex_perplexity_search_classifier';
const PERPLEXITY_DISABLE_SEARCH_STORAGE_KEY = 'iudex_perplexity_disable_search';
const PERPLEXITY_STREAM_MODE_STORAGE_KEY = 'iudex_perplexity_stream_mode';
const MULTI_MODEL_DEEP_DEBATE_STORAGE_KEY = 'iudex_multi_model_deep_debate';
const PERPLEXITY_SEARCH_DOMAIN_FILTER_STORAGE_KEY = 'iudex_perplexity_search_domain_filter';
const PERPLEXITY_SEARCH_LANGUAGE_FILTER_STORAGE_KEY = 'iudex_perplexity_search_language_filter';
const PERPLEXITY_SEARCH_RECENCY_FILTER_STORAGE_KEY = 'iudex_perplexity_search_recency_filter';
const PERPLEXITY_SEARCH_AFTER_DATE_STORAGE_KEY = 'iudex_perplexity_search_after_date';
const PERPLEXITY_SEARCH_BEFORE_DATE_STORAGE_KEY = 'iudex_perplexity_search_before_date';
const PERPLEXITY_LAST_UPDATED_AFTER_STORAGE_KEY = 'iudex_perplexity_last_updated_after';
const PERPLEXITY_LAST_UPDATED_BEFORE_STORAGE_KEY = 'iudex_perplexity_last_updated_before';
const PERPLEXITY_SEARCH_MAX_RESULTS_STORAGE_KEY = 'iudex_perplexity_search_max_results';
const PERPLEXITY_SEARCH_MAX_TOKENS_STORAGE_KEY = 'iudex_perplexity_search_max_tokens';
const PERPLEXITY_SEARCH_MAX_TOKENS_PER_PAGE_STORAGE_KEY =
  'iudex_perplexity_search_max_tokens_per_page';
const PERPLEXITY_SEARCH_COUNTRY_STORAGE_KEY = 'iudex_perplexity_search_country';
const PERPLEXITY_SEARCH_REGION_STORAGE_KEY = 'iudex_perplexity_search_region';
const PERPLEXITY_SEARCH_CITY_STORAGE_KEY = 'iudex_perplexity_search_city';
const PERPLEXITY_SEARCH_LATITUDE_STORAGE_KEY = 'iudex_perplexity_search_latitude';
const PERPLEXITY_SEARCH_LONGITUDE_STORAGE_KEY = 'iudex_perplexity_search_longitude';
const PERPLEXITY_RETURN_IMAGES_STORAGE_KEY = 'iudex_perplexity_return_images';
const PERPLEXITY_RETURN_VIDEOS_STORAGE_KEY = 'iudex_perplexity_return_videos';
const MINUTA_OUTLINE_TEMPLATE_STORAGE_KEY = 'iudex_minuta_outline_template';
const MINUTA_OUTLINE_TEMPLATES_BY_SUBTYPE_STORAGE_KEY = 'iudex_minuta_outline_templates_by_subtype';
const SOURCE_SELECTION_STORAGE_KEY = 'iudex_source_selection';
const RAG_SELECTED_GROUPS_STORAGE_KEY = 'iudex_rag_selected_groups';
const RAG_ALLOW_GROUPS_STORAGE_KEY = 'iudex_rag_allow_groups';
const RAG_GLOBAL_JURISDICTIONS_STORAGE_KEY = 'iudex_rag_global_jurisdictions';
const RAG_GLOBAL_SOURCE_IDS_STORAGE_KEY = 'iudex_rag_global_source_ids';
const DEFAULT_USD_PER_POINT = 0.00003;

const describeApiError = (error: unknown) => {
  const anyErr = error as any;
  const message = typeof anyErr?.message === 'string' ? anyErr.message : '';
  const status = anyErr?.response?.status;
  const data = anyErr?.response?.data;
  const method =
    typeof anyErr?.config?.method === 'string' ? anyErr.config.method.toUpperCase() : '';
  const baseURL = typeof anyErr?.config?.baseURL === 'string' ? anyErr.config.baseURL : '';
  const url = typeof anyErr?.config?.url === 'string' ? anyErr.config.url : '';

  const dataStr =
    typeof data === 'string'
      ? data
      : data
        ? (() => {
          try {
            return JSON.stringify(data);
          } catch {
            return String(data);
          }
        })()
        : '';

  if (status || dataStr) {
    const requestStr = [method, baseURL, url].filter(Boolean).join(' ');
    return `HTTP ${status ?? '?'}${dataStr ? `: ${dataStr}` : ''}${requestStr ? ` (${requestStr})` : ''}`;
  }
  return message || String(error || 'Erro desconhecido');
};

const getUsdPerPoint = () => {
  const billing = useBillingStore.getState().billing;
  const raw = billing?.points_anchor?.usd_per_point;
  const parsed = typeof raw === 'number' ? raw : Number(raw);
  return Number.isFinite(parsed) ? parsed : DEFAULT_USD_PER_POINT;
};

const DEFAULT_MINUTA_OUTLINE_TEMPLATES_BY_SUBTYPE: Record<string, string> = {
  PETICAO_INICIAL: ['I - DOS FATOS', 'II - DO DIREITO', 'III - DOS PEDIDOS'].join('\n'),
  CONTESTACAO: ['I - SÍNTESE DOS FATOS', 'II - PRELIMINARES', 'III - DO MÉRITO', 'IV - DOS PEDIDOS'].join('\n'),
  RECURSO: ['I - CABIMENTO E TEMPESTIVIDADE', 'II - SÍNTESE DOS FATOS', 'III - DO DIREITO', 'IV - DOS PEDIDOS'].join('\n'),
  PARECER: ['I - RELATÓRIO', 'II - FUNDAMENTAÇÃO JURÍDICA', 'III - CONCLUSÃO E OPINATIVO'].join('\n'),
};

const stripBaseMarker = (template: string): string => {
  const cleaned = String(template || '')
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line && line !== '{{BASE}}');
  return cleaned.join('\n');
};

const resolveMinutaOutlineTemplateForSubtype = (
  docSubtype: string | null | undefined,
  templatesBySubtype: Record<string, string>
): string => {
  const subtype = String(docSubtype || '').trim();
  const fallback = DEFAULT_MINUTA_OUTLINE_TEMPLATES_BY_SUBTYPE.PETICAO_INICIAL;
  if (!subtype) return fallback;
  const saved = templatesBySubtype?.[subtype];
  if (typeof saved === 'string' && saved.trim()) {
    const cleaned = stripBaseMarker(saved);
    if (cleaned.trim()) return cleaned;
  }
  return DEFAULT_MINUTA_OUTLINE_TEMPLATES_BY_SUBTYPE[subtype] || fallback;
};

const INITIAL_MINUTA_OUTLINE_TEMPLATES_BY_SUBTYPE = loadJsonPreference<Record<string, string>>(
  MINUTA_OUTLINE_TEMPLATES_BY_SUBTYPE_STORAGE_KEY,
  {}
);

const INITIAL_MINUTA_OUTLINE_TEMPLATE = (() => {
  const subtype = 'PETICAO_INICIAL';
  const fromMap = INITIAL_MINUTA_OUTLINE_TEMPLATES_BY_SUBTYPE?.[subtype];
  if (typeof fromMap === 'string' && fromMap.trim()) return fromMap;
  // Backward-compat: if the user had a global base stored, keep it as PETIÇÃO base.
  return loadStringPreference(
    MINUTA_OUTLINE_TEMPLATE_STORAGE_KEY,
    DEFAULT_MINUTA_OUTLINE_TEMPLATES_BY_SUBTYPE.PETICAO_INICIAL
  );
})();

// Source Selection Types
export interface CorpusGlobalSelection {
  legislacao: boolean;
  jurisprudencia: boolean;
  pecasModelo: boolean;
  doutrina: boolean;
  sei: boolean;
}

export interface SourceSelection {
  webSearch: boolean;
  attachments: Record<string, boolean>; // fileId -> enabled
  corpusGlobal: CorpusGlobalSelection;
  corpusPrivado: Record<string, boolean>; // projectId -> enabled
  mcpConnectors: Record<string, boolean>; // label -> enabled
}

export type SourceCategory = 'webSearch' | 'attachments' | 'corpusGlobal' | 'corpusPrivado' | 'mcpConnectors';

const DEFAULT_SOURCE_SELECTION: SourceSelection = {
  webSearch: false,
  attachments: {},
  corpusGlobal: {
    legislacao: true,
    jurisprudencia: true,
    pecasModelo: true,
    doutrina: true,
    sei: true,
  },
  corpusPrivado: {},
  mcpConnectors: {},
};

const SOURCE_ICONS: Record<string, string> = {
  webSearch: '🌐',
  attachments: '📎',
  legislacao: '📜',
  jurisprudencia: '⚖️',
  pecasModelo: '📄',
  doutrina: '📚',
  sei: '🏛️',
  corpusPrivado: '🔒',
  mcpConnectors: '🔌',
};

// CogGRAG Types
export type CogRAGNodeState = 'pending' | 'decomposing' | 'retrieving' | 'retrieved' | 'verifying' | 'verified' | 'rejected' | 'complete' | 'error';
export type CogRAGStatus = 'idle' | 'decomposing' | 'retrieving' | 'verifying' | 'integrating' | 'complete';

export interface CogRAGNode {
  nodeId: string;
  question: string;
  level: number;
  parentId: string | null;
  state: CogRAGNodeState;
  childrenCount: number;
  evidenceCount: number;
  confidence: number;
}

type DraftMetadata = {
  processed_sections?: any[];
  has_any_divergence?: boolean;
  divergence_summary?: string;
  full_document?: string;
  models?: string[];
  committee_config?: {
    judge_model?: string;
    strategist_model?: string;
    drafter_models?: string[];
    reviewer_models?: string[];
  };
  committee_participants?: string[];
  consensus?: boolean;
  audit?: any;
  committee_review_report?: any;
};

const getDraftStorageKey = (chatId: string) => `${CHAT_DRAFTS_KEY_PREFIX}${chatId}`;

function loadWebSearchModel(): string {
  if (typeof window === 'undefined') return 'auto';
  try {
    const raw = (localStorage.getItem(LANGGRAPH_WEB_SEARCH_MODEL_STORAGE_KEY) || '').trim();
    return raw || 'auto';
  } catch {
    return 'auto';
  }
}

const extractAuditIssuesFromMarkdown = (markdown: string): string[] => {
  if (!markdown) return [];
  const redMarker = '\uD83D\uDD34';
  return markdown
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line && line.includes(redMarker))
    .map((line) => line.replace(/^[-*]\s*/, '').trim())
    .filter(Boolean);
};

const normalizeAuditIssues = (value: any): string[] | null => {
  if (value == null) return null;
  if (Array.isArray(value)) {
    const list = value.map((item) => String(item || '').trim()).filter(Boolean);
    return list;
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed ? [trimmed] : [];
  }
  return null;
};

const mergeAuditMetadata = (
  metadata: any,
  input: {
    report?: any;
    status?: string | null;
    issues?: any;
    issuesCount?: number | null;
  }
) => {
  const base = metadata || {};
  const next: any = { ...base };
  const report = input.report && typeof input.report === 'object' ? input.report : null;
  const status = input.status ? String(input.status) : null;
  const issuesCount = typeof input.issuesCount === 'number' ? input.issuesCount : null;

  let nextAudit = { ...(base.audit || {}) };
  if (report) {
    nextAudit = { ...nextAudit, ...report };
    const reportMarkdown =
      typeof report.audit_report_markdown === 'string'
        ? report.audit_report_markdown
        : typeof report.markdown === 'string'
          ? report.markdown
          : null;
    if (reportMarkdown && typeof nextAudit.audit_report_markdown !== 'string') {
      nextAudit.audit_report_markdown = reportMarkdown;
    }
  }
  if (status) {
    nextAudit = { ...nextAudit, status, audit_status: status };
    next.audit_status = status;
  }

  let issues = normalizeAuditIssues(input.issues);
  if (!issues) {
    const reportMarkdown =
      typeof report?.markdown === 'string'
        ? report.markdown
        : typeof report?.audit_report_markdown === 'string'
          ? report.audit_report_markdown
          : '';
    const parsed = extractAuditIssuesFromMarkdown(reportMarkdown);
    if (parsed.length) issues = parsed;
  }
  if (!issues && issuesCount === 0) issues = [];
  if (issues) {
    next.audit_issues = issues;
    nextAudit = { ...nextAudit, audit_issues: issues };
  }

  if (Object.keys(nextAudit).length > 0) {
    next.audit = nextAudit;
  }

  return next;
};

const extractDraftMetadata = (metadata: any): DraftMetadata | null => {
  if (!metadata) return null;
  const processed = Array.isArray(metadata.processed_sections) ? metadata.processed_sections : [];
  if (
    processed.length === 0 &&
    !metadata.full_document &&
    !metadata.divergence_summary &&
    !metadata.committee_review_report
  ) {
    return null;
  }
  return {
    processed_sections: processed,
    has_any_divergence: metadata.has_any_divergence,
    divergence_summary: metadata.divergence_summary,
    full_document: metadata.full_document,
    models: metadata.models,
    committee_config: metadata.committee_config,
    committee_participants: metadata.committee_participants,
    consensus: metadata.consensus,
    audit: metadata.audit,
    committee_review_report: metadata.committee_review_report,
  };
};

const persistDraftMetadata = (chatId: string | null, metadata: any) => {
  if (!chatId || typeof window === 'undefined') return;
  const payload = extractDraftMetadata(metadata);
  if (!payload) return;
  try {
    localStorage.setItem(getDraftStorageKey(chatId), JSON.stringify(payload));
  } catch {
    // ignore storage errors
  }
};

const loadDraftMetadata = (chatId: string | null): DraftMetadata | null => {
  if (!chatId || typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(getDraftStorageKey(chatId));
    if (!raw) return null;
    return JSON.parse(raw) as DraftMetadata;
  } catch {
    return null;
  }
};

const clearDraftMetadata = (chatId: string) => {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(getDraftStorageKey(chatId));
  } catch {
    // ignore storage errors
  }
};

let langGraphEventSource: EventSource | null = null;

const closeLangGraphStream = () => {
  try {
    langGraphEventSource?.close();
  } catch {
    // noop
  }
  langGraphEventSource = null;
};

const attachLangGraphStream = (jobId: string, persistChatId: string | null, set: any, get: any) => {
  if (typeof window === 'undefined') return;

  // Ensure only one active stream
  closeLangGraphStream();

  const eventSource = new EventSource(`${apiBaseUrl}/jobs/${jobId}/stream`);
  langGraphEventSource = eventSource;
  let streamBuffer = '';
  let streamActive = false;
  let streamCanvasShown = false;

  const handleSse = (event: MessageEvent) => {
    if (!event?.data) return;
    let data: any;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }

    const eventType = data?.type;
    const envelopePayload =
      data && typeof data === 'object' && data.data && typeof data.data === 'object'
        ? data.data
        : null;
    const payload = envelopePayload ?? data;
    const outlinePayload = payload?.outline;
    const isOutlineEvent =
      eventType === 'outline_done' || eventType === 'outline_generated' || eventType === 'outline';

    if (eventType === 'token' && payload?.delta) {
      const delta = String(payload.delta);
      if (!delta) return;
      if (payload?.reset || !streamActive) {
        streamActive = true;
        streamBuffer = '';
        try {
          const canvas = useCanvasStore.getState();
          canvas.setContent('');
        } catch {
          // noop
        }
      }
      streamBuffer += delta;
      try {
        const canvas = useCanvasStore.getState();
        canvas.setContent(streamBuffer);
        if (!streamCanvasShown) {
          canvas.showCanvas();
          canvas.setActiveTab('editor');
          streamCanvasShown = true;
        }
      } catch {
        // noop
      }
      return;
    }

    // Hard Research: study_token streams content into the canvas
    if (eventType === 'study_token' && payload?.delta) {
      const delta = String(payload.delta);
      if (!delta) return;
      if (!streamActive) {
        streamActive = true;
        streamBuffer = '';
        try {
          const canvas = useCanvasStore.getState();
          canvas.setContent('');
        } catch {
          // noop
        }
      }
      streamBuffer += delta;
      try {
        const canvas = useCanvasStore.getState();
        canvas.setContent(streamBuffer);
        if (!streamCanvasShown) {
          canvas.showCanvas();
          canvas.setActiveTab('editor');
          streamCanvasShown = true;
        }
      } catch {
        // noop
      }
      // Also store in jobEvents for the viewer
      set((state: any) => ({
        jobEvents: [...state.jobEvents, data],
      }));
      return;
    }

    // Code Artifact: artifact_start creates a new artifact
    if (eventType === 'artifact_start' && payload) {
      try {
        const canvas = useCanvasStore.getState();
        const artifactId = canvas.addArtifact({
          type: payload.artifact_type || 'code',
          language: payload.language || 'typescript',
          title: payload.title || 'Artifact',
          code: '',
          description: payload.description,
          status: 'streaming',
          agent: payload.agent || payload.model,
          model: payload.model,
          isStreaming: true,
          executable: payload.executable,
          dependencies: payload.dependencies,
          messageId: payload.message_id,
        });
        // Store artifact ID for subsequent tokens
        (window as any).__currentArtifactId = artifactId;
        canvas.setActiveTab('code');
      } catch {
        // noop
      }
      return;
    }

    // Code Artifact: artifact_token streams code
    if (eventType === 'artifact_token' && payload?.delta) {
      try {
        const canvas = useCanvasStore.getState();
        const artifactId = payload.artifact_id || (window as any).__currentArtifactId;
        if (artifactId) {
          canvas.streamArtifactToken(artifactId, String(payload.delta));
        }
      } catch {
        // noop
      }
      return;
    }

    // Code Artifact: artifact_done finalizes the artifact
    if (eventType === 'artifact_done' && payload) {
      try {
        const canvas = useCanvasStore.getState();
        const artifactId = payload.artifact_id || (window as any).__currentArtifactId;
        if (artifactId) {
          canvas.finalizeArtifact(artifactId, payload.code);
        }
        delete (window as any).__currentArtifactId;
      } catch {
        // noop
      }
      return;
    }

    // Code Artifact: artifact (single-shot, non-streaming)
    if (eventType === 'artifact' && payload) {
      try {
        const canvas = useCanvasStore.getState();
        canvas.addArtifact({
          type: payload.artifact_type || payload.type || 'code',
          language: payload.language || 'typescript',
          title: payload.title || 'Artifact',
          code: payload.code || '',
          description: payload.description,
          status: 'complete',
          agent: payload.agent || payload.model,
          model: payload.model,
          executable: payload.executable,
          dependencies: payload.dependencies,
          messageId: payload.message_id,
        });
        canvas.setActiveTab('code');
      } catch {
        // noop
      }
      return;
    }

    const shouldStoreEvent = eventType !== 'token' && eventType !== 'meta' && eventType !== 'thinking';
    set((state: any) => ({
      ...(shouldStoreEvent ? { jobEvents: [...state.jobEvents, data] } : {}),
      jobOutline:
        isOutlineEvent && Array.isArray(outlinePayload) ? outlinePayload : state.jobOutline,
      // Update retry progress from SSE
      retryProgress:
        eventType === 'research_retry_progress'
          ? {
            progress: payload?.progress,
            reason: payload?.reason,
            isRetrying: payload?.is_retrying,
            attempts: payload?.attempts,
          }
          : state.retryProgress,
    }));

    if (isOutlineEvent && Array.isArray(outlinePayload)) {
      try {
        useCanvasStore.getState().syncOutlineFromTitles(outlinePayload);
      } catch {
        // noop
      }
    }

    if (eventType === 'hil_required' && envelopePayload) {
      const reviewPayload = {
        checkpoint: envelopePayload.checkpoint,
        ...(envelopePayload.payload || {}),
      };
      set({ reviewData: reviewPayload });
      if ((reviewPayload as any).committee_review_report) {
        try {
          const { setMetadata, metadata } = useCanvasStore.getState();
          const report = (reviewPayload as any).committee_review_report;
          const participants = Array.isArray(report?.agents_participated)
            ? report.agents_participated
            : undefined;
          const updatedMetadata = {
            ...(metadata || {}),
            committee_review_report: report,
            ...(participants ? { committee_participants: participants } : {}),
          };
          setMetadata(updatedMetadata, null);
          persistDraftMetadata(persistChatId, updatedMetadata);
        } catch {
          // noop
        }
      }
    }

    // v5.9: Handle hil_outline_waiting for improved observability
    if (eventType === 'hil_outline_waiting' && envelopePayload) {
      const reviewPayload = {
        checkpoint: 'outline',
        type: 'outline_review',
        outline: envelopePayload.outline || [],
        message: envelopePayload.message || 'Aguardando aprovação do sumário.',
      };
      set({ reviewData: reviewPayload });
    }

    if (eventType === 'human_review_required') {
      const reviewPayload = { checkpoint: data.checkpoint, ...data.review_data };
      set({ reviewData: reviewPayload });
      try {
        const { setMetadata, metadata } = useCanvasStore.getState();
        let updatedMetadata = metadata || {};
        let hasUpdate = false;

        if ((reviewPayload as any).committee_review_report) {
          const report = (reviewPayload as any).committee_review_report;
          const participants = Array.isArray(report?.agents_participated)
            ? report.agents_participated
            : undefined;
          updatedMetadata = {
            ...updatedMetadata,
            committee_review_report: report,
            ...(participants ? { committee_participants: participants } : {}),
          };
          hasUpdate = true;
        }

        const auditReport = (reviewPayload as any).audit_report;
        const auditStatus = (reviewPayload as any).audit_status;
        const auditIssues = (reviewPayload as any).audit_issues;
        if (auditReport || auditStatus || auditIssues) {
          updatedMetadata = mergeAuditMetadata(updatedMetadata, {
            report: auditReport,
            status: auditStatus,
            issues: auditIssues,
          });
          hasUpdate = true;
        }

        if (hasUpdate) {
          setMetadata(updatedMetadata, null);
          persistDraftMetadata(persistChatId, updatedMetadata);
        }
      } catch {
        // noop
      }
    }

    if (eventType === 'audit_done') {
      const report = payload?.report;
      const status = payload?.status || payload?.audit_status;
      const issuesCount = typeof payload?.issues_count === 'number' ? payload.issues_count : null;
      if (report || status || typeof issuesCount === 'number') {
        try {
          const { setMetadata, metadata } = useCanvasStore.getState();
          const updatedMetadata = mergeAuditMetadata(metadata, {
            report,
            status,
            issuesCount,
          });
          setMetadata(updatedMetadata, null);
          persistDraftMetadata(persistChatId, updatedMetadata);
        } catch {
          // noop
        }
      }
    }

    if (eventType === 'quality_report_done') {
      const markdown = typeof payload?.markdown_preview === 'string' ? payload.markdown_preview : '';
      if (markdown.trim()) {
        try {
          const { setMetadata, metadata } = useCanvasStore.getState();
          const updatedMetadata = {
            ...(metadata || {}),
            quality_report_markdown: markdown,
            quality: {
              ...(metadata?.quality || {}),
              quality_report_markdown: markdown,
            },
          };
          setMetadata(updatedMetadata, null);
          persistDraftMetadata(persistChatId, updatedMetadata);
        } catch {
          // noop
        }
      }
    }

    // NEW: Update Canvas Metadata in real-time for 'section' events
    if (data?.type === 'section_processed' || data?.type === 'debate_done') {
      try {
        const { setMetadata, metadata } = useCanvasStore.getState();
        // Merge with existing metadata or create new structure
        const currentSections = metadata?.processed_sections || [];

        // Helper to merge or append section
        const mergeSection = (sec: any) => {
          const sectionTitle = sec.section || sec.section_title || sec.sectionName;
          const idx = currentSections.findIndex((s: any) => s.section_title === sectionTitle);
          const review = sec.review && typeof sec.review === 'object' ? sec.review : undefined;
          const detailedSec = {
            section_title: sectionTitle,
            has_significant_divergence: sec.has_divergence,
            drafts: sec.drafts, // Capture raw drafts!
            divergence_details: sec.divergence_details,
            risk_flags: sec.risk_flags,
            claims_requiring_citation: sec.claims_requiring_citation,
            removed_claims: sec.removed_claims,
            review,
          };

          if (idx >= 0) {
            currentSections[idx] = { ...currentSections[idx], ...detailedSec };
          } else {
            currentSections.push(detailedSec);
          }
        };

        if (data.type === 'section_processed') {
          mergeSection(data);
        }

        const updatedMetadata = {
          ...(metadata || {}),
          processed_sections: [...currentSections],
          has_any_divergence: data.has_divergence || metadata?.has_any_divergence,
          divergence_summary: data.divergence_summary || metadata?.divergence_summary,
          full_document: data.document_preview || metadata?.full_document,
        };
        setMetadata(updatedMetadata, null);
        persistDraftMetadata(persistChatId, updatedMetadata);

        const preview = typeof data.document_preview === 'string' ? data.document_preview : '';
        if (preview.trim() && !streamActive) {
          const { setContent: setCanvasContent, content: currentContent } =
            useCanvasStore.getState();
          if (preview.trim() !== (currentContent || '').trim()) {
            setCanvasContent(preview);
          }
        }
      } catch (e) {
        console.error('Error updating canvas metadata from stream', e);
      }
    }

    // NEW: Handle granular streaming events for real-time editor updates
    if (data?.type === 'granular' || data?.type === 'stream_chunk') {
      try {
        // If the event carries a full preview or a delta, update the canvas
        const preview = data.document_preview || data.markdown || data.content;
        if (typeof preview === 'string' && preview.trim()) {
          const { setContent: setCanvasContent, content: currentContent } = useCanvasStore.getState();
          // Avoid stuttering if content is identical
          if (preview.trim() !== (currentContent || '').trim()) {
            setCanvasContent(preview);
          }
        }

        // Also update step/status if provided
        if (data.node || data.step) {
          // Optional: highlight active node in UI if we had a graph view
        }
      } catch (e) {
        // Ignore streaming errors to prevent crashing
      }
    }

    // Claude Agent SDK Event Handlers
    if (eventType === 'agent_iteration') {
      set((state: any) => ({
        agentIterationCount: (state.agentIterationCount || 0) + 1,
        isAgentMode: true,
      }));
    }

    if (eventType === 'tool_call') {
      set({
        lastToolCall: {
          tool: payload?.tool || payload?.name || 'unknown',
          status: 'pending',
        },
      });
    }

    if (eventType === 'tool_result') {
      set((state: any) => ({
        lastToolCall: state.lastToolCall
          ? {
              ...state.lastToolCall,
              status: payload?.error ? 'error' : 'success',
              result: payload?.result || payload?.output,
            }
          : null,
      }));
    }

    if (eventType === 'tool_approval_required') {
      set({
        pendingToolApproval: {
          tool: payload?.tool || payload?.name || 'unknown',
          input: payload?.input || {},
          riskLevel: payload?.risk_level || 'medium',
        },
      });
    }

    if (eventType === 'code_execution') {
      set({
        lastToolCall: {
          tool: 'code_interpreter',
          status: 'running',
          language: payload?.language || 'python',
          code: payload?.code || '',
        },
      });
    }

    if (eventType === 'code_execution_result') {
      set((state: any) => ({
        lastToolCall: state.lastToolCall
          ? {
              ...state.lastToolCall,
              status: payload?.outcome === 'OUTCOME_OK' ? 'success' : 'error',
              result: payload?.output || '',
            }
          : null,
      }));
    }

    if (eventType === 'context_warning') {
      const usagePercent = typeof payload?.usage_percent === 'number' ? payload.usage_percent : 0;
      set({ contextUsagePercent: usagePercent });
    }

    if (eventType === 'compaction_done') {
      set({
        lastSummaryId: payload?.summary_id || null,
        contextUsagePercent: typeof payload?.new_percent === 'number' ? payload.new_percent : 0,
      });
    }

    if (eventType === 'checkpoint_created') {
      set((state: any) => ({
        checkpoints: [
          ...(state.checkpoints || []),
          {
            id: payload?.id || payload?.checkpoint_id || nanoid(),
            description: payload?.description || 'Checkpoint',
            createdAt: payload?.created_at || new Date().toISOString(),
          },
        ],
      }));
    }

    if (eventType === 'parallel_start') {
      set({
        parallelExecution: {
          active: true,
          toolCount: payload?.tool_count || payload?.count || 0,
          completedCount: 0,
        },
      });
    }

    if (eventType === 'parallel_progress') {
      set((state: any) => ({
        parallelExecution: state.parallelExecution
          ? {
              ...state.parallelExecution,
              completedCount: payload?.completed || (state.parallelExecution.completedCount + 1),
            }
          : null,
      }));
    }

    if (eventType === 'parallel_complete') {
      set({ parallelExecution: null });
    }

    // CogGRAG Event Handlers
    if (eventType === 'cograg_decompose_start') {
      set({
        cogragStatus: 'decomposing',
        cogragTree: [],
      });
    }

    if (eventType === 'cograg_decompose_node') {
      set((state: any) => {
        const node: CogRAGNode = {
          nodeId: payload?.node_id || '',
          question: payload?.question || '',
          level: payload?.level || 0,
          parentId: payload?.parent_id || null,
          state: 'decomposing',
          childrenCount: 0,
          evidenceCount: 0,
          confidence: 0,
        };
        return {
          cogragTree: [...(state.cogragTree || []), node],
        };
      });
    }

    if (eventType === 'cograg_decompose_complete') {
      set({ cogragStatus: 'retrieving' });
    }

    if (eventType === 'cograg_retrieval_node') {
      set((state: any) => {
        const nodeId = payload?.node_id;
        const cogragTree = (state.cogragTree || []).map((n: CogRAGNode) =>
          n.nodeId === nodeId
            ? { ...n, state: 'retrieved', evidenceCount: payload?.evidence_count || 0 }
            : n
        );
        return { cogragTree };
      });
    }

    if (eventType === 'cograg_retrieval_complete') {
      set({ cogragStatus: 'verifying' });
    }

    if (eventType === 'cograg_verify_node') {
      set((state: any) => {
        const nodeId = payload?.node_id;
        const cogragTree = (state.cogragTree || []).map((n: CogRAGNode) =>
          n.nodeId === nodeId
            ? {
                ...n,
                state: payload?.is_consistent ? 'verified' : 'rejected',
                confidence: payload?.confidence || 0,
              }
            : n
        );
        return { cogragTree };
      });
    }

    if (eventType === 'cograg_verify_complete') {
      set({ cogragStatus: 'integrating' });
    }

    if (eventType === 'cograg_integrate_complete') {
      set({ cogragStatus: 'complete' });
    }

    if (data?.type === 'done') {
      const citations = Array.isArray(data.citations) ? data.citations : null;
      const streamedIntoCanvas = streamActive || String(streamBuffer || '').trim().length > 0;
      const aiMessage: Message = {
        id: nanoid(),
        content: streamedIntoCanvas ? 'Documento finalizado no canvas.' : (data.markdown || 'Documento finalizado.'),
        role: 'assistant',
        timestamp: new Date().toISOString(),
        ...(citations ? { metadata: { citations } } : {}),
      };

      set((state: any) => ({
        currentChat: state.currentChat
          ? {
            ...state.currentChat,
            messages: [...(state.currentChat.messages || []), aiMessage],
          }
          : null,
        isAgentRunning: false,
      }));

      // Atualiza canvas automaticamente (modo LangGraph)
      try {
        const { setContent: setCanvasContent, setMetadata, metadata, costInfo } =
          useCanvasStore.getState();
        setCanvasContent(data.markdown || '');
        streamActive = false;
        streamBuffer = '';
        const decisionPayload = data.final_decision
          ? {
            final_decision: data.final_decision,
            final_decision_reasons: data.final_decision_reasons || [],
            final_decision_score: data.final_decision_score,
            final_decision_target: data.final_decision_target,
          }
          : null;
        const updatedMetadata = {
          ...(metadata || {}),
          full_document: data.markdown || metadata?.full_document,
          ...(citations ? { citations } : {}),
          ...(decisionPayload ? { decision: decisionPayload } : {}),
        };
        const pointsTotalRaw = data?.api_counters?.points_total;
        const pointsTotal = Number.isFinite(Number(pointsTotalRaw))
          ? Number(pointsTotalRaw)
          : 0;
        const nextCostInfo = pointsTotal
          ? {
            ...(costInfo || {}),
            points_total: pointsTotal,
            total_cost: pointsTotal * getUsdPerPoint(),
          }
          : costInfo || null;
        setMetadata(updatedMetadata, nextCostInfo);
        persistDraftMetadata(persistChatId, updatedMetadata);
      } catch {
        // noop
      }

      closeLangGraphStream();
    }
  };

  // Backend emits custom SSE event types: event: outline/section/done/...
  const eventNames = [
    'message',
    'status',
    'outline',
    'research',
    'section',
    'debate',
    'granular',
    'audit',
    'fact_check',
    'quality',
    'hil_decision',
    'corrections',
    'review',
    'document_gate',
    'done',
    'error',
    // Claude Agent SDK events
    'agent_iteration',
    'tool_call',
    'tool_result',
    'tool_approval_required',
    'context_warning',
    'compaction_done',
    'checkpoint_created',
    'parallel_start',
    'parallel_progress',
    'parallel_complete',
    // Hard Research events
    'hard_research_start',
    'provider_start',
    'provider_thinking',
    'provider_source',
    'provider_done',
    'provider_error',
    'merge_start',
    'merge_done',
    'study_generation_start',
    'study_outline',
    'study_token',
    'study_done',
    // Hard Research agentic events
    'agent_thinking',
    'agent_tool_call',
    'agent_tool_result',
    'agent_ask_user',
    // CogGRAG events
    'cograg_decompose_start',
    'cograg_decompose_node',
    'cograg_decompose_complete',
    'cograg_retrieval_start',
    'cograg_retrieval_node',
    'cograg_retrieval_complete',
    'cograg_verify_start',
    'cograg_verify_node',
    'cograg_verify_complete',
    'cograg_integrate_start',
    'cograg_integrate_complete',
  ];

  for (const name of eventNames) {
    eventSource.addEventListener(name, handleSse as unknown as EventListener);
  }

  eventSource.onerror = (e) => {
    const hasReviewOpen = !!get()?.reviewData;
    if (!hasReviewOpen) {
      console.error('SSE Error', e);
    }
    closeLangGraphStream();
    set({ isAgentRunning: false });
  };
};

function loadMultiModelView(): 'tabs' | 'columns' {
  if (typeof window === 'undefined') return 'tabs';
  try {
    const v = localStorage.getItem(MULTI_MODEL_VIEW_STORAGE_KEY);
    return v === 'columns' ? 'columns' : 'tabs';
  } catch {
    return 'tabs';
  }
}

function loadMultiModelDeepDebate(): boolean {
  return loadBooleanPreference(MULTI_MODEL_DEEP_DEBATE_STORAGE_KEY, true);
}

function loadBooleanPreference(key: string, fallback: boolean): boolean {
  if (typeof window === 'undefined') return fallback;
  try {
    const v = localStorage.getItem(key);
    if (v === null) return fallback;
    return v === 'true';
  } catch {
    return fallback;
  }
}

function loadStringPreference(key: string, fallback = ''): string {
  if (typeof window === 'undefined') return fallback;
  try {
    const v = localStorage.getItem(key);
    return v === null ? fallback : v;
  } catch {
    return fallback;
  }
}

function loadJsonPreference<T>(key: string, fallback: T): T {
  if (typeof window === 'undefined') return fallback;
  try {
    const raw = (localStorage.getItem(key) || '').trim();
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function loadRagSelectedGroups(): string[] {
  const raw = loadJsonPreference<unknown>(RAG_SELECTED_GROUPS_STORAGE_KEY, []);
  if (!Array.isArray(raw)) return [];
  return raw.map((v) => String(v || '').trim()).filter(Boolean);
}

function persistRagSelectedGroups(groupIds: string[]): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(RAG_SELECTED_GROUPS_STORAGE_KEY, JSON.stringify(groupIds));
  } catch {
    // ignore storage errors
  }
}

function loadRagAllowGroups(): boolean {
  return loadBooleanPreference(RAG_ALLOW_GROUPS_STORAGE_KEY, true);
}

function persistRagAllowGroups(allow: boolean): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(RAG_ALLOW_GROUPS_STORAGE_KEY, String(Boolean(allow)));
  } catch {
    // ignore storage errors
  }
}

function loadRagGlobalJurisdictions(): string[] {
  const raw = loadJsonPreference<unknown>(RAG_GLOBAL_JURISDICTIONS_STORAGE_KEY, []);
  if (!Array.isArray(raw)) return [];
  return raw.map((v) => String(v || '').trim().toUpperCase()).filter(Boolean);
}

function persistRagGlobalJurisdictions(jurisdictions: string[]): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(RAG_GLOBAL_JURISDICTIONS_STORAGE_KEY, JSON.stringify(jurisdictions));
  } catch {
    // ignore storage errors
  }
}

function loadRagGlobalSourceIds(): string[] {
  const raw = loadJsonPreference<unknown>(RAG_GLOBAL_SOURCE_IDS_STORAGE_KEY, []);
  if (!Array.isArray(raw)) return [];
  return raw.map((v) => String(v || '').trim()).filter(Boolean);
}

function persistRagGlobalSourceIds(sourceIds: string[]): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(RAG_GLOBAL_SOURCE_IDS_STORAGE_KEY, JSON.stringify(sourceIds));
  } catch {
    // ignore storage errors
  }
}

function loadSourceSelection(): SourceSelection {
  if (typeof window === 'undefined') return { ...DEFAULT_SOURCE_SELECTION };
  try {
    const raw = localStorage.getItem(SOURCE_SELECTION_STORAGE_KEY);
    if (!raw) return { ...DEFAULT_SOURCE_SELECTION };
    const parsed = JSON.parse(raw) as Partial<SourceSelection>;
    return {
      webSearch: typeof parsed.webSearch === 'boolean' ? parsed.webSearch : DEFAULT_SOURCE_SELECTION.webSearch,
      attachments: parsed.attachments && typeof parsed.attachments === 'object' ? parsed.attachments : {},
      corpusGlobal: {
        legislacao: parsed.corpusGlobal?.legislacao ?? DEFAULT_SOURCE_SELECTION.corpusGlobal.legislacao,
        jurisprudencia: parsed.corpusGlobal?.jurisprudencia ?? DEFAULT_SOURCE_SELECTION.corpusGlobal.jurisprudencia,
        pecasModelo: parsed.corpusGlobal?.pecasModelo ?? DEFAULT_SOURCE_SELECTION.corpusGlobal.pecasModelo,
        doutrina: parsed.corpusGlobal?.doutrina ?? DEFAULT_SOURCE_SELECTION.corpusGlobal.doutrina,
        sei: parsed.corpusGlobal?.sei ?? DEFAULT_SOURCE_SELECTION.corpusGlobal.sei,
      },
      corpusPrivado: parsed.corpusPrivado && typeof parsed.corpusPrivado === 'object' ? parsed.corpusPrivado : {},
      mcpConnectors: parsed.mcpConnectors && typeof parsed.mcpConnectors === 'object' ? parsed.mcpConnectors : {},
    };
  } catch {
    return { ...DEFAULT_SOURCE_SELECTION };
  }
}

function persistSourceSelection(selection: SourceSelection): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(SOURCE_SELECTION_STORAGE_KEY, JSON.stringify(selection));
  } catch {
    // ignore storage errors
  }
}

const parseOutlineTemplate = (value: string): string[] => {
  const lines = String(value || '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
  return Array.from(new Set(lines));
};

function loadOptionalIntPreference(key: string, min: number, max: number): string {
  if (typeof window === 'undefined') return '';
  try {
    const raw = (localStorage.getItem(key) || '').trim();
    if (!raw) return '';
    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) return '';
    const value = Math.floor(parsed);
    if (value < min || value > max) return '';
    return String(value);
  } catch {
    return '';
  }
}

function loadChatPersonality(): 'juridico' | 'geral' {
  if (typeof window === 'undefined') return 'juridico';
  try {
    const v = localStorage.getItem(CHAT_PERSONALITY_KEY);
    return v === 'geral' ? 'geral' : 'juridico';
  } catch {
    return 'juridico';
  }
}

function loadResearchPolicy(): 'auto' | 'force' {
  if (typeof window === 'undefined') return 'auto';
  try {
    const v = localStorage.getItem(RESEARCH_POLICY_STORAGE_KEY);
    return v === 'force' ? 'force' : 'auto';
  } catch {
    return 'auto';
  }
}

function loadDeepResearchProvider(): 'auto' | 'google' | 'perplexity' {
  if (typeof window === 'undefined') return 'auto';
  try {
    const v = (localStorage.getItem(DEEP_RESEARCH_PROVIDER_STORAGE_KEY) || '').trim().toLowerCase();
    if (v === 'google' || v === 'perplexity') return v;
    return 'auto';
  } catch {
    return 'auto';
  }
}

function loadDeepResearchModel(): string {
  if (typeof window === 'undefined') return 'sonar-deep-research';
  try {
    const v = (localStorage.getItem(DEEP_RESEARCH_MODEL_STORAGE_KEY) || '').trim();
    // Perplexity Deep Research backend in Iudex is restricted to Sonar Deep Research.
    if (v === 'sonar-deep-research') return v;
    return 'sonar-deep-research';
  } catch {
    return 'sonar-deep-research';
  }
}

function loadDeepResearchEffort(): 'low' | 'medium' | 'high' {
  if (typeof window === 'undefined') return 'medium';
  try {
    const v = (localStorage.getItem(DEEP_RESEARCH_EFFORT_STORAGE_KEY) || '').trim().toLowerCase();
    if (v === 'low' || v === 'high' || v === 'medium') return v;
    return 'medium';
  } catch {
    return 'medium';
  }
}

function loadDeepResearchSearchFocus(): 'web' | 'academic' | 'sec' | '' {
  if (typeof window === 'undefined') return '';
  try {
    const v = (localStorage.getItem(DEEP_RESEARCH_SEARCH_FOCUS_STORAGE_KEY) || '')
      .trim()
      .toLowerCase();
    if (v === 'web' || v === 'academic' || v === 'sec') return v;
    return '';
  } catch {
    return '';
  }
}

function loadPerplexitySearchMode(): 'web' | 'academic' | 'sec' {
  if (typeof window === 'undefined') return 'web';
  try {
    const v = (localStorage.getItem(PERPLEXITY_SEARCH_MODE_STORAGE_KEY) || '').trim().toLowerCase();
    if (v === 'academic' || v === 'sec' || v === 'web') return v;
    return 'web';
  } catch {
    return 'web';
  }
}

function loadPerplexitySearchType(): 'fast' | 'pro' | 'auto' {
  if (typeof window === 'undefined') return 'fast';
  try {
    const v = (localStorage.getItem(PERPLEXITY_SEARCH_TYPE_STORAGE_KEY) || '').trim().toLowerCase();
    if (v === 'pro' || v === 'auto' || v === 'fast') return v;
    return 'fast';
  } catch {
    return 'fast';
  }
}

function loadPerplexitySearchContextSize(): 'low' | 'medium' | 'high' {
  if (typeof window === 'undefined') return 'low';
  try {
    const v = (localStorage.getItem(PERPLEXITY_SEARCH_CONTEXT_SIZE_STORAGE_KEY) || '')
      .trim()
      .toLowerCase();
    if (v === 'medium' || v === 'high' || v === 'low') return v;
    return 'low';
  } catch {
    return 'low';
  }
}

function loadPerplexityStreamMode(): 'full' | 'concise' {
  if (typeof window === 'undefined') return 'full';
  try {
    const v = (localStorage.getItem(PERPLEXITY_STREAM_MODE_STORAGE_KEY) || '')
      .trim()
      .toLowerCase();
    if (v === 'concise' || v === 'full') return v;
    return 'full';
  } catch {
    return 'full';
  }
}

function loadPerplexitySearchRecencyFilter(): '' | 'day' | 'week' | 'month' | 'year' {
  if (typeof window === 'undefined') return '';
  try {
    const v = (localStorage.getItem(PERPLEXITY_SEARCH_RECENCY_FILTER_STORAGE_KEY) || '')
      .trim()
      .toLowerCase();
    if (v === 'day' || v === 'week' || v === 'month' || v === 'year') return v;
    return '';
  } catch {
    return '';
  }
}

const buildCommitteeMetadata = (state: {
  selectedModel: string;
  agentStrategistModel: string;
  agentDrafterModels: string[];
  agentReviewerModels: string[];
}) => {
  const committee_config = {
    judge_model: state.selectedModel,
    strategist_model: state.agentStrategistModel,
    drafter_models: state.agentDrafterModels || [],
    reviewer_models: state.agentReviewerModels || [],
  };
  const committee_participants = Array.from(
    new Set([
      ...(committee_config.drafter_models || []),
      ...(committee_config.reviewer_models || []),
    ])
  );
  return {
    committee_config,
    committee_participants,
    models: committee_participants,
    judge_model: committee_config.judge_model,
    strategist_model: committee_config.strategist_model,
  };
};

function normalizePageRange(minPages: number, maxPages: number) {
  let min = Number.isFinite(minPages) ? Math.max(0, Math.floor(minPages)) : 0;
  let max = Number.isFinite(maxPages) ? Math.max(0, Math.floor(maxPages)) : 0;

  if (min > 0 && max === 0) max = min;
  if (max > 0 && min === 0) min = 1;
  if (min > 0 && max > 0 && max < min) max = min;

  return { minPages: min, maxPages: max };
}

function inferDocKindFromType(docType: string): string | null {
  const value = (docType || '').toUpperCase();
  if (!value) return null;
  if (
    value.includes('PETICAO') ||
    value.includes('CONTESTACAO') ||
    value.includes('MANIFESTACAO') ||
    value.includes('MANDADO') ||
    value.includes('HABEAS') ||
    value.includes('RECLAMACAO') ||
    value.includes('DIVORCIO')
  ) {
    return 'PLEADING';
  }
  if (
    value.includes('RECURSO') ||
    value.includes('APELACAO') ||
    value.includes('AGRAVO') ||
    value.includes('RESP') ||
    value.includes('RE') ||
    value.includes('EMBARGOS')
  ) {
    return 'APPEAL';
  }
  if (
    value.includes('SENTENCA') ||
    value.includes('ACORDAO') ||
    value.includes('VOTO') ||
    value.includes('INTERLOCUTORIA')
  ) {
    return 'JUDICIAL_DECISION';
  }
  if (value.includes('OFICIO')) {
    return 'OFFICIAL';
  }
  if (value.includes('NOTIFICACAO')) {
    return 'EXTRAJUDICIAL';
  }
  if (value.includes('PARECER') || value.includes('NOTA') || value.includes('MEMORANDO')) {
    return 'LEGAL_NOTE';
  }
  if (value.includes('ESCRITURA') || value.includes('PROCURACAO')) {
    return 'NOTARIAL';
  }
  if (value.includes('CONTRATO')) {
    return 'CONTRACT';
  }
  return null;
}

interface Message {
  id: string;
  content: string;
  role: 'user' | 'assistant';
  timestamp: string;
  thinking?: string;
  isThinking?: boolean;
  metadata?: any;
}

type CanvasContext = {
  text: string;
  action: 'improve' | 'shorten' | null;
};

type DocumentChecklistItem = {
  id?: string;
  label: string;
  critical: boolean;
};

interface Chat {
  id: string;
  title: string;
  mode?: string;
  context?: any;
  messages: Message[];
  created_at: string;
  updated_at: string;
  is_active?: boolean;
}

type BillingQuote = {
  ok: boolean;
  estimated_points: number;
  estimated_usd: number;
  breakdown?: any;
  current_budget?: number | null;
  suggested_budgets?: number[] | null;
  points_available?: number | null;
  error?: string | null;
};

type BillingModalRetry =
  | { kind: 'chat'; content: string; options?: Record<string, any> }
  | { kind: 'job'; prompt: string }
  | { kind: 'generate'; prompt: string; caseId?: string }
  | { kind: 'agent_legacy'; prompt: string; canvasContext?: CanvasContext | null };

type BillingModalState = {
  open: boolean;
  quote: BillingQuote | null;
  retry: BillingModalRetry | null;
};

interface ChatState {
  chats: Chat[];
  currentChat: Chat | null;
  isLoading: boolean;
  isSending: boolean;
  fetchChats: () => Promise<void>;
  setCurrentChat: (chatId: string | null) => Promise<void>;
  createChat: (title?: string) => Promise<Chat>;
  duplicateChat: (chatId: string, title?: string) => Promise<Chat>;
  deleteChat: (chatId: string) => Promise<void>;
  sendMessage: (
    content: string,
    options?: {
      outline?: string[];
      skipOutlineFetch?: boolean;
      skipUserMessage?: boolean;
      canvasWrite?: 'replace' | 'append';
      outlinePipeline?: boolean;
      budgetOverridePoints?: number;
    }
  ) => Promise<void>;
  billingModal: BillingModalState;
  closeBillingModal: () => void;
  retryWithBudgetOverride: (budgetPoints: number) => Promise<void>;
  generateDocument: (data: {
    prompt: string;
    context?: any;
    effort_level?: number;
    document_type?: string;
  }) => Promise<any>;

  // Context Management
  activeContext: any[];
  setContext: (context: any[]) => void;

  // Canvas context for snippet improvements
  pendingCanvasContext: CanvasContext | null;
  setPendingCanvasContext: (context: CanvasContext | null) => void;

  // Agent State
  agentSteps: AgentStep[];
  isAgentRunning: boolean;

  // Claude Agent SDK State
  isAgentMode: boolean;
  agentIterationCount: number;
  contextUsagePercent: number;
  lastSummaryId: string | null;
  pendingToolApproval: {
    tool: string;
    input: Record<string, unknown>;
    riskLevel: 'low' | 'medium' | 'high';
  } | null;
  toolPermissions: Record<string, 'allow' | 'deny' | 'ask'>;
  checkpoints: Array<{
    id: string;
    description: string;
    createdAt: string;
  }>;
  parallelExecution: {
    active: boolean;
    toolCount: number;
    completedCount: number;
  } | null;
  // CogGRAG State
  cogragTree: CogRAGNode[] | null;
  cogragStatus: CogRAGStatus;
  lastToolCall: {
    tool: string;
    status: 'pending' | 'success' | 'error';
    result?: unknown;
  } | null;
  effortLevel: number;
  selectedModel: string;
  gptModel: string;
  claudeModel: string;
  useMultiAgent: boolean;
  reasoningLevel: 'none' | 'minimal' | 'low' | 'medium' | 'high' | 'xhigh';
  verbosity: 'low' | 'medium' | 'high';
  thinkingBudget: string;
  modelOverrides: Record<
    string,
    {
      verbosity?: 'low' | 'medium' | 'high';
      thinkingBudget?: string;
      reasoningLevel?: 'none' | 'minimal' | 'low' | 'medium' | 'high' | 'xhigh';
    }
  >;
  mcpToolCalling: boolean;
  setMcpToolCalling: (enabled: boolean) => void;
  mcpUseAllServers: boolean;
  setMcpUseAllServers: (enabled: boolean) => void;
  mcpServerLabels: string[];
  setMcpServerLabels: (labels: string[]) => void;
  webSearch: boolean;
  webSearchModel: string;
  /** @deprecated UI moved to SourcesBadge - state kept for API compatibility */
  multiQuery: boolean;
  /** @deprecated UI moved to SourcesBadge - state kept for API compatibility */
  breadthFirst: boolean;
  /** @deprecated UI moved to SourcesBadge - state kept for API compatibility */
  searchMode: 'shared' | 'native' | 'hybrid' | 'perplexity';
  perplexitySearchMode: 'web' | 'academic' | 'sec';
  perplexitySearchType: 'fast' | 'pro' | 'auto';
  perplexitySearchContextSize: 'low' | 'medium' | 'high';
  perplexitySearchClassifier: boolean;
  perplexityDisableSearch: boolean;
  perplexityStreamMode: 'full' | 'concise';
  perplexitySearchDomainFilter: string;
  perplexitySearchLanguageFilter: string;
  perplexitySearchRecencyFilter: '' | 'day' | 'week' | 'month' | 'year';
  perplexitySearchAfterDate: string;
  perplexitySearchBeforeDate: string;
  perplexityLastUpdatedAfter: string;
  perplexityLastUpdatedBefore: string;
  perplexitySearchMaxResults: string;
  perplexitySearchMaxTokens: string;
  perplexitySearchMaxTokensPerPage: string;
  perplexitySearchCountry: string;
  perplexitySearchRegion: string;
  perplexitySearchCity: string;
  perplexitySearchLatitude: string;
  perplexitySearchLongitude: string;
  perplexityReturnImages: boolean;
  perplexityReturnVideos: boolean;
  /** @deprecated UI moved to SourcesBadge - state kept for API compatibility */
  researchPolicy: 'auto' | 'force';
  ragTopK: number;
  ragSources: string[];
  /** Optional narrowing: filter Global Corpus by jurisdiction codes (empty = all). */
  ragGlobalJurisdictions: string[];
  /** Optional narrowing: filter Global Corpus by regional source IDs (empty = all). */
  ragGlobalSourceIds: string[];
  minPages: number;
  maxPages: number;
  attachmentMode: 'auto' | 'rag_local' | 'prompt_injection';

  // Agent Specific Models
  agentStrategistModel: string;
  agentDrafterModels: string[];
  agentReviewerModels: string[];
  // Setters defined later to avoid duplicates

  // Multi-Model V2
  chatMode: 'standard' | 'multi-model';
  selectedModels: string[];
  multiModelMessages: Record<string, Message[]>;
  // UI: Visualização do comparador (Tabs) para multi-modelo
  showMultiModelComparator: boolean;
  setShowMultiModelComparator: (enabled: boolean) => void;
  // UI: Consolidado (juiz/merge)
  autoConsolidate: boolean;
  setAutoConsolidate: (enabled: boolean) => void;
  // UI: Deep debate (4 rounds) vs quick consensus (1 round) for committee-like flows
  multiModelDeepDebate: boolean;
  setMultiModelDeepDebate: (enabled: boolean) => void;
  consolidateTurn: (turnId: string) => Promise<void>;
  // UI: Layout do comparador
  multiModelView: 'tabs' | 'columns';
  setMultiModelView: (view: 'tabs' | 'columns') => void;

  denseResearch: boolean;
  deepResearchProvider: 'auto' | 'google' | 'perplexity' | 'openai';
  deepResearchModel: string;
  deepResearchEffort: 'low' | 'medium' | 'high';
  // Hard Research Mode
  deepResearchMode: 'standard' | 'hard';
  hardResearchProviders: Record<string, boolean>;
  deepResearchSearchFocus: 'web' | 'academic' | 'sec' | '';
  deepResearchDomainFilter: string;
  deepResearchSearchAfterDate: string;
  deepResearchSearchBeforeDate: string;
  deepResearchLastUpdatedAfter: string;
  deepResearchLastUpdatedBefore: string;
  deepResearchCountry: string;
  deepResearchLatitude: string;
  deepResearchLongitude: string;
  hilOutlineEnabled: boolean;
  autoApproveHil: boolean;
  hilTargetSections: string[];
  minutaOutlineTemplate: string;
  minutaOutlineTemplatesBySubtype: Record<string, string>;
  auditMode: 'sei_only' | 'research';
  qualityProfile: 'rapido' | 'padrao' | 'rigoroso' | 'auditoria';
  qualityTargetSectionScore: number | null;
  qualityTargetFinalScore: number | null;
  qualityMaxRounds: number | null;
  qualityMaxFinalReviewLoops: number | null;
  qualityStyleRefineMaxRounds: number | null;
  qualityMaxResearchVerifierAttempts: number | null;
  qualityMaxRagRetries: number | null;
  qualityRagRetryExpandScope: boolean | null;
  recursionLimitOverride: number | null;
  strictDocumentGateOverride: boolean | null;
  hilSectionPolicyOverride: 'none' | 'optional' | 'required' | null;
  hilFinalRequiredOverride: boolean | null;
  documentChecklist: DocumentChecklistItem[];
  cragMinBestScoreOverride: number | null;
  cragMinAvgScoreOverride: number | null;
  forceGranularDebate: boolean;
  maxDivergenceHilRounds: number | null;

  tenantId: string;
  // Context Management (v2)
  contextMode: 'auto' | 'rag_local' | 'upload_cache';
  contextFiles: string[]; // List of paths (simulated for local)
  cacheTTL: number;
  documentType: string;
  docKind: string | null;
  docSubtype: string | null;
  thesis: string;
  formattingOptions: {
    includeToc: boolean;
    includeSummaries: boolean;
    includeSummaryTable: boolean;
  };
  citationStyle:
    | 'forense'
    | 'hibrido'
    | 'abnt'
    | 'forense_br'
    | 'bluebook'
    | 'harvard'
    | 'apa'
    | 'chicago'
    | 'oscola'
    | 'ecli'
    | 'vancouver'
    | 'inline'
    | 'numeric'
    | 'alwd';
  useTemplates: boolean;
  templateFilters: {
    tipoPeca: string;
    area: string;
    rito: string;
    apenasClauseBank: boolean;
  };
  templateId: string | null;
  templateDocumentId: string | null;
  templateVariables: Record<string, any>;
  templateName: string | null;
  templateDocumentName: string | null;
  promptExtra: string;
  adaptiveRouting: boolean;
  cragGate: boolean;
  hydeEnabled: boolean;
  graphRagEnabled: boolean;
  argumentGraphEnabled: boolean;
  graphHops: number;
  /** @deprecated UI moved to SourcesBadge with granular checkboxes - state kept for API compatibility */
  ragScope: 'case_only' | 'case_and_global' | 'global_only';
  /** Optional narrowing: subset of user's org teams to search within (empty = all teams user belongs to). */
  ragSelectedGroups: string[];
  /** Explicit allow/deny for organization private corpus. */
  ragAllowPrivate: boolean;
  /** Explicit allow/deny for department-scoped corpus (group scope). */
  ragAllowGroups: boolean;
  setRagGlobalJurisdictions: (jurisdictions: string[]) => void;
  toggleRagGlobalJurisdiction: (jurisdiction: string) => void;
  clearRagGlobalJurisdictions: () => void;
  setRagGlobalSourceIds: (sourceIds: string[]) => void;
  toggleRagGlobalSourceId: (sourceId: string) => void;
  clearRagGlobalSourceIds: () => void;

  // Granular Source Selection
  sourceSelection: SourceSelection;

  // Chat Personality: 'juridico' for legal language, 'geral' for general/free chat
  chatPersonality: 'juridico' | 'geral';
  creativityMode: 'rigoroso' | 'padrao' | 'criativo';
  temperatureOverride: number | null;

  setEffortLevel: (level: number) => void;
  setSelectedModel: (model: string) => void;
  setGptModel: (model: string) => void;
  setClaudeModel: (model: string) => void;
  setAgentStrategistModel: (model: string) => void;
  setAgentDrafterModels: (models: string[]) => void;
  setAgentReviewerModels: (models: string[]) => void;
  setUseMultiAgent: (use: boolean) => void;
  setReasoningLevel: (level: 'none' | 'minimal' | 'low' | 'medium' | 'high' | 'xhigh') => void;
  setVerbosity: (level: 'low' | 'medium' | 'high') => void;
  setThinkingBudget: (value: string) => void;
  setModelOverride: (
    modelId: string,
    patch: {
      verbosity?: 'low' | 'medium' | 'high';
      thinkingBudget?: string;
      reasoningLevel?: 'none' | 'minimal' | 'low' | 'medium' | 'high' | 'xhigh';
    }
  ) => void;
  setWebSearch: (enabled: boolean) => void;
  setWebSearchModel: (model: string) => void;
  setMultiQuery: (enabled: boolean) => void;
  setBreadthFirst: (enabled: boolean) => void;
  setSearchMode: (mode: 'shared' | 'native' | 'hybrid' | 'perplexity') => void;
  setPerplexitySearchMode: (mode: 'web' | 'academic' | 'sec') => void;
  setPerplexitySearchType: (mode: 'fast' | 'pro' | 'auto') => void;
  setPerplexitySearchContextSize: (size: 'low' | 'medium' | 'high') => void;
  setPerplexitySearchClassifier: (enabled: boolean) => void;
  setPerplexityDisableSearch: (enabled: boolean) => void;
  setPerplexityStreamMode: (mode: 'full' | 'concise') => void;
  setPerplexitySearchDomainFilter: (value: string) => void;
  setPerplexitySearchLanguageFilter: (value: string) => void;
  setPerplexitySearchRecencyFilter: (value: '' | 'day' | 'week' | 'month' | 'year') => void;
  setPerplexitySearchAfterDate: (value: string) => void;
  setPerplexitySearchBeforeDate: (value: string) => void;
  setPerplexityLastUpdatedAfter: (value: string) => void;
  setPerplexityLastUpdatedBefore: (value: string) => void;
  setPerplexitySearchMaxResults: (value: string) => void;
  setPerplexitySearchMaxTokens: (value: string) => void;
  setPerplexitySearchMaxTokensPerPage: (value: string) => void;
  setPerplexitySearchCountry: (value: string) => void;
  setPerplexitySearchRegion: (value: string) => void;
  setPerplexitySearchCity: (value: string) => void;
  setPerplexitySearchLatitude: (value: string) => void;
  setPerplexitySearchLongitude: (value: string) => void;
  setPerplexityReturnImages: (enabled: boolean) => void;
  setPerplexityReturnVideos: (enabled: boolean) => void;
  setResearchPolicy: (policy: 'auto' | 'force') => void;
  setRagTopK: (k: number) => void;
  setRagSources: (sources: string[]) => void;
  setPageRange: (range: { minPages?: number; maxPages?: number }) => void;
  resetPageRange: () => void;
  setAttachmentMode: (mode: 'auto' | 'rag_local' | 'prompt_injection') => void;
  setDenseResearch: (enabled: boolean) => void;
  setDeepResearchProvider: (provider: 'auto' | 'google' | 'perplexity' | 'openai') => void;
  setDeepResearchModel: (model: string) => void;
  setDeepResearchEffort: (effort: 'low' | 'medium' | 'high') => void;
  setDeepResearchMode: (mode: 'standard' | 'hard') => void;
  setHardResearchProvider: (provider: string, enabled: boolean) => void;
  toggleHardResearchProvider: (provider: string) => void;
  setAllHardResearchProviders: (enabled: boolean) => void;
  setDeepResearchSearchFocus: (value: 'web' | 'academic' | 'sec' | '') => void;
  setDeepResearchDomainFilter: (value: string) => void;
  setDeepResearchSearchAfterDate: (value: string) => void;
  setDeepResearchSearchBeforeDate: (value: string) => void;
  setDeepResearchLastUpdatedAfter: (value: string) => void;
  setDeepResearchLastUpdatedBefore: (value: string) => void;
  setDeepResearchCountry: (value: string) => void;
  setDeepResearchLatitude: (value: string) => void;
  setDeepResearchLongitude: (value: string) => void;
  setHilOutlineEnabled: (enabled: boolean) => void;
  setAutoApproveHil: (enabled: boolean) => void;
  setHilTargetSections: (sections: string[]) => void;
  setMinutaOutlineTemplate: (value: string) => void;
  setAuditMode: (mode: 'sei_only' | 'research') => void;
  setQualityProfile: (profile: 'rapido' | 'padrao' | 'rigoroso' | 'auditoria') => void;
  setQualityTargetSectionScore: (value: number | null) => void;
  setQualityTargetFinalScore: (value: number | null) => void;
  setQualityMaxRounds: (value: number | null) => void;
  setQualityMaxFinalReviewLoops: (value: number | null) => void;
  setQualityStyleRefineMaxRounds: (value: number | null) => void;
  setQualityMaxResearchVerifierAttempts: (value: number | null) => void;
  setQualityMaxRagRetries: (value: number | null) => void;
  setQualityRagRetryExpandScope: (value: boolean | null) => void;
  setRecursionLimitOverride: (value: number | null) => void;
  setStrictDocumentGateOverride: (value: boolean | null) => void;
  setHilSectionPolicyOverride: (value: 'none' | 'optional' | 'required' | null) => void;
  setHilFinalRequiredOverride: (value: boolean | null) => void;
  setDocumentChecklist: (items: DocumentChecklistItem[]) => void;
  setCragMinBestScoreOverride: (value: number | null) => void;
  setCragMinAvgScoreOverride: (value: number | null) => void;
  setForceGranularDebate: (enabled: boolean) => void;
  setMaxDivergenceHilRounds: (value: number | null) => void;
  setTenantId: (id: string) => void;
  setContextMode: (mode: 'auto' | 'rag_local' | 'upload_cache') => void;
  setContextFiles: (files: string[]) => void;
  setCacheTTL: (ttl: number) => void;
  setDocumentType: (type: string) => void;
  setThesis: (thesis: string) => void;
  setFormattingOptions: (options: Partial<ChatState['formattingOptions']>) => void;
  setCitationStyle: (style: ChatState['citationStyle']) => void;
  setUseTemplates: (use: boolean) => void;
  setTemplateFilters: (filters: Partial<ChatState['templateFilters']>) => void;
  setTemplateId: (id: string | null) => void;
  setTemplateDocumentId: (id: string | null) => void;
  setTemplateVariables: (vars: Record<string, any>) => void;
  setTemplateName: (name: string | null) => void;
  setTemplateDocumentName: (name: string | null) => void;
  setPromptExtra: (prompt: string) => void;
  setAdaptiveRouting: (enabled: boolean) => void;
  setCragGate: (enabled: boolean) => void;
  setHydeEnabled: (enabled: boolean) => void;
  setGraphRagEnabled: (enabled: boolean) => void;
  setArgumentGraphEnabled: (enabled: boolean) => void;
  setGraphHops: (hops: number) => void;
  setRagScope: (scope: 'case_only' | 'case_and_global' | 'global_only') => void;
  setRagSelectedGroups: (groupIds: string[]) => void;
  toggleRagSelectedGroup: (groupId: string) => void;
  clearRagSelectedGroups: () => void;
  setRagAllowPrivate: (allow: boolean) => void;
  setRagAllowGroups: (allow: boolean) => void;

  // Source Selection Actions
  setSourceSelection: (selection: SourceSelection) => void;
  toggleSource: (category: SourceCategory, id?: string) => void;
  selectAllInCategory: (category: SourceCategory) => void;
  deselectAllInCategory: (category: SourceCategory) => void;
  setAttachmentEnabled: (fileId: string, enabled: boolean) => void;
  setCorpusGlobalEnabled: (key: keyof CorpusGlobalSelection, enabled: boolean) => void;
  setCorpusPrivadoEnabled: (projectId: string, enabled: boolean) => void;
  setMcpConnectorEnabled: (label: string, enabled: boolean) => void;
  getActiveSourcesCount: () => number;
  getActiveSourceIcons: () => string[];

  setChatPersonality: (personality: 'juridico' | 'geral') => void;
  setCreativityMode: (mode: 'rigoroso' | 'padrao' | 'criativo') => void;
  setTemperatureOverride: (value: number | null) => void;
  setChatOutlineReviewEnabled: (enabled: boolean) => void;

  // Playbook integration (for /minuta contract review)
  selectedPlaybookId: string | null;
  selectedPlaybookName: string | null;
  selectedPlaybookPrompt: string | null;
  isPlaybookLoading: boolean;
  setSelectedPlaybook: (id: string | null, name: string | null, prompt: string | null) => void;
  clearPlaybook: () => void;

  // Audit State
  audit: boolean;
  setAudit: (enabled: boolean) => void;
  startAgentGeneration: (
    prompt: string,
    canvasContext?: CanvasContext | null,
    options?: { budgetOverridePoints?: number }
  ) => Promise<void>;
  generateDocumentWithResult: (
    prompt: string,
    caseId?: string,
    options?: { budgetOverridePoints?: number }
  ) => Promise<any>;

  // Manual message injection (useful for system messages or optimistic updates)
  addMessage: (message: Message) => void;

  // Job State
  currentJobId: string | null;
  jobEvents: any[];
  jobOutline: string[];
  reviewData: any | null;
  retryProgress: {
    progress: string | null;
    reason: string | null;
    isRetrying: boolean;
    attempts: number;
  } | null;
  // Chat (single-model): revisar/editar outline antes do streaming
  chatOutlineReviewEnabled: boolean;
  pendingChatOutline: {
    content: string;
    outline: string[];
    model: string;
    canvasWrite?: 'replace' | 'append';
    outlinePipeline?: boolean;
  } | null;
  submitReview: (decision: any) => Promise<void>;
  startLangGraphJob: (prompt: string, options?: { budgetOverridePoints?: number }) => Promise<void>;

  // V2 Actions
  setChatMode: (mode: 'standard' | 'multi-model') => void;
  setSelectedModels: (models: string[]) => void;
  toggleModel: (modelId: string) => void;
  startMultiModelStream: (
    content: string,
    options?: { budgetOverridePoints?: number; existingTurnId?: string; skipUserMessage?: boolean }
  ) => Promise<void>;
  createMultiChatThread: (title?: string) => Promise<any>;

  // Claude Agent SDK Actions
  setIsAgentMode: (enabled: boolean) => void;
  compactConversation: () => Promise<void>;
  approveToolCall: (approved: boolean, remember?: 'session' | 'always') => Promise<void>;
  restoreCheckpoint: (checkpointId: string) => Promise<void>;
  setToolPermission: (tool: string, permission: 'allow' | 'deny' | 'ask') => void;
  clearPendingToolApproval: () => void;
}

// Mock initial data (fallback)
const MOCK_CHATS: Chat[] = [
  {
    id: '1',
    title: 'Análise de Contrato Social',
    messages: [
      {
        id: 'm1',
        content: 'Olá! Sou o Iudex. Como posso ajudar com sua demanda jurídica hoje?',
        role: 'assistant',
        timestamp: new Date().toISOString(),
      },
    ],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

const extractReplacementText = (content: string) => {
  const trimmed = (content || '').trim();
  if (!trimmed) return '';

  const codeBlockMatch = trimmed.match(/```(?:[a-zA-Z0-9_-]+)?\n([\s\S]*?)```/);
  if (codeBlockMatch?.[1]) {
    return codeBlockMatch[1].trim();
  }

  const prefixes = [
    /^Aqui est[aá].*?:\s*/i,
    /^Vers[aã]o .*?:\s*/i,
    /^Trecho reescrito.*?:\s*/i,
    /^Reescrita.*?:\s*/i,
    /^Resposta:\s*/i,
  ];

  let result = trimmed;
  for (const prefix of prefixes) {
    if (prefix.test(result)) {
      result = result.replace(prefix, '').trim();
      break;
    }
  }

  return result;
};

const creativityModeToTemperature = (mode: 'rigoroso' | 'padrao' | 'criativo') => {
  if (mode === 'rigoroso') return 0.1;
  if (mode === 'criativo') return 0.6;
  return 0.3;
};

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));

const resolveTemperature = (
  creativityMode: 'rigoroso' | 'padrao' | 'criativo',
  override: number | null | undefined
) => {
  if (typeof override === 'number' && Number.isFinite(override)) return clamp01(override);
  return creativityModeToTemperature(creativityMode);
};

const isPerplexityModelId = (modelId: string) =>
  String(modelId || '')
    .trim()
    .toLowerCase()
    .startsWith('sonar');

const isPerplexityDeepResearchModelId = (modelId: string) =>
  String(modelId || '').trim().toLowerCase() === 'sonar-deep-research';

const parsePositiveInt = (value: string, min?: number, max?: number) => {
  const raw = String(value || '').trim();
  if (!raw) return null;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return null;
  const intValue = Math.floor(parsed);
  if (intValue <= 0) return null;
  if (typeof min === 'number' && intValue < min) return null;
  if (typeof max === 'number' && intValue > max) return max;
  return intValue;
};

const parseThinkingBudget = (value?: string | null, max = 63999) => {
  const raw = String(value ?? '').trim();
  if (!raw) return null;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return null;
  const intValue = Math.floor(parsed);
  if (intValue < 0) return null;
  if (intValue > max) return max;
  return intValue;
};

const normalizeReasoningLevel = (value?: string | null) =>
  String(value ?? '').trim().toLowerCase();

const isThinkingDisabledLevel = (level: string) =>
  !level || ['none', 'off', 'disabled'].includes(level);

const OPTIMISTIC_THINKING_MODELS = [
  'gemini-3-pro',
  'gpt-5.2',
  'claude-4.5-sonnet',
  'deepseek-v3.2-reasoner',
  'gemini-3-flash',
];

const resolveThinkingEnabled = (
  modelId: string,
  reasoningLevel?: string | null,
  thinkingBudget?: number | null
) => {
  const level = normalizeReasoningLevel(reasoningLevel);
  if (isThinkingDisabledLevel(level)) return false;
  const isClaude = String(modelId || '').toLowerCase().startsWith('claude');
  if (isClaude && typeof thinkingBudget === 'number' && thinkingBudget <= 0) return false;
  return true;
};

const shouldStartThinking = (
  modelId: string,
  reasoningLevel?: string | null,
  thinkingEnabled?: boolean
) => {
  if (!thinkingEnabled) return false;
  const level = normalizeReasoningLevel(reasoningLevel);
  const isOptimisticModel = OPTIMISTIC_THINKING_MODELS.some((m) =>
    String(modelId || '').toLowerCase().includes(m)
  );
  return !['low', 'minimal'].includes(level) || isOptimisticModel;
};

const buildModelOverridesPayload = (
  overrides: ChatState['modelOverrides']
): Record<string, { verbosity?: string; thinking_budget?: number; reasoning_level?: string }> | undefined => {
  if (!overrides || typeof overrides !== 'object') return undefined;
  const payload: Record<
    string,
    { verbosity?: string; thinking_budget?: number; reasoning_level?: string }
  > = {};
  for (const [modelId, override] of Object.entries(overrides)) {
    if (!override) continue;
    const entry: { verbosity?: string; thinking_budget?: number; reasoning_level?: string } = {};
    if (override.verbosity) {
      entry.verbosity = override.verbosity;
    }
    if (override.reasoningLevel) {
      entry.reasoning_level = override.reasoningLevel;
    }
    if (override.thinkingBudget !== undefined) {
      const budget = parseThinkingBudget(override.thinkingBudget);
      if (budget !== null) entry.thinking_budget = budget;
    }
    if (Object.keys(entry).length > 0) {
      payload[modelId] = entry;
    }
  }
  return Object.keys(payload).length > 0 ? payload : undefined;
};

const buildPerplexityPayload = (state: ChatState, targetModels?: string[]) => {
  const models =
    targetModels && targetModels.length
      ? targetModels
      : Array.isArray(state.selectedModels)
        ? state.selectedModels
        : [];
  const hasPerplexityModel = models.some((modelId) => isPerplexityModelId(modelId));
  const shouldInclude = hasPerplexityModel || state.webSearch;
  if (!shouldInclude && !state.perplexityDisableSearch && !state.perplexitySearchClassifier) {
    return {};
  }
  const payload: Record<string, any> = {};
  if (state.perplexitySearchMode) payload.perplexity_search_mode = state.perplexitySearchMode;
  if (state.perplexitySearchType) payload.perplexity_search_type = state.perplexitySearchType;
  if (state.perplexitySearchContextSize) {
    payload.perplexity_search_context_size = state.perplexitySearchContextSize;
  }
  if (state.perplexitySearchClassifier) payload.perplexity_search_classifier = true;
  if (state.perplexityDisableSearch) payload.perplexity_disable_search = true;
  if (state.perplexityStreamMode) payload.perplexity_stream_mode = state.perplexityStreamMode;
  if (state.perplexitySearchDomainFilter) {
    payload.perplexity_search_domain_filter = state.perplexitySearchDomainFilter;
  }
  if (state.perplexitySearchLanguageFilter) {
    payload.perplexity_search_language_filter = state.perplexitySearchLanguageFilter;
  }
  if (state.perplexitySearchRecencyFilter) {
    payload.perplexity_search_recency_filter = state.perplexitySearchRecencyFilter;
  }
  if (state.perplexitySearchAfterDate) {
    payload.perplexity_search_after_date = state.perplexitySearchAfterDate;
  }
  if (state.perplexitySearchBeforeDate) {
    payload.perplexity_search_before_date = state.perplexitySearchBeforeDate;
  }
  if (state.perplexityLastUpdatedAfter) {
    payload.perplexity_last_updated_after = state.perplexityLastUpdatedAfter;
  }
  if (state.perplexityLastUpdatedBefore) {
    payload.perplexity_last_updated_before = state.perplexityLastUpdatedBefore;
  }
  const maxResults = parsePositiveInt(state.perplexitySearchMaxResults, 1, 20);
  if (maxResults) payload.perplexity_search_max_results = maxResults;
  const maxTokens = parsePositiveInt(state.perplexitySearchMaxTokens, 1, 1_000_000);
  if (maxTokens) payload.perplexity_search_max_tokens = maxTokens;
  const maxTokensPerPage = parsePositiveInt(
    state.perplexitySearchMaxTokensPerPage,
    1,
    1_000_000
  );
  if (maxTokensPerPage) payload.perplexity_search_max_tokens_per_page = maxTokensPerPage;
  if (state.perplexitySearchCountry) {
    payload.perplexity_search_country = state.perplexitySearchCountry;
  }
  if (state.perplexitySearchRegion) {
    payload.perplexity_search_region = state.perplexitySearchRegion;
  }
  if (state.perplexitySearchCity) {
    payload.perplexity_search_city = state.perplexitySearchCity;
  }
  if (state.perplexitySearchLatitude) {
    payload.perplexity_search_latitude = state.perplexitySearchLatitude;
  }
  if (state.perplexitySearchLongitude) {
    payload.perplexity_search_longitude = state.perplexitySearchLongitude;
  }
  if (state.perplexityReturnImages) payload.perplexity_return_images = true;
  if (state.perplexityReturnVideos) payload.perplexity_return_videos = true;
  return payload;
};

const buildDeepResearchPayload = (state: ChatState) => {
  const payload: Record<string, any> = {};
  if (state.deepResearchProvider) payload.deep_research_provider = state.deepResearchProvider;
  if (state.deepResearchModel) payload.deep_research_model = state.deepResearchModel;
  if (state.deepResearchEffort) payload.deep_research_effort = state.deepResearchEffort;
  payload.deep_research_mode = state.deepResearchMode;
  if (state.deepResearchMode === 'hard') {
    payload.hard_research_providers = Object.entries(state.hardResearchProviders)
      .filter(([_, enabled]) => enabled !== false)
      .map(([provider]) => provider);
  }
  if (state.deepResearchSearchFocus) {
    payload.deep_research_search_focus = state.deepResearchSearchFocus;
  }
  if (state.deepResearchDomainFilter) {
    payload.deep_research_domain_filter = state.deepResearchDomainFilter;
  }
  if (state.deepResearchSearchAfterDate) {
    payload.deep_research_search_after_date = state.deepResearchSearchAfterDate;
  }
  if (state.deepResearchSearchBeforeDate) {
    payload.deep_research_search_before_date = state.deepResearchSearchBeforeDate;
  }
  if (state.deepResearchLastUpdatedAfter) {
    payload.deep_research_last_updated_after = state.deepResearchLastUpdatedAfter;
  }
  if (state.deepResearchLastUpdatedBefore) {
    payload.deep_research_last_updated_before = state.deepResearchLastUpdatedBefore;
  }
  if (state.deepResearchCountry) payload.deep_research_country = state.deepResearchCountry;
  if (state.deepResearchLatitude) payload.deep_research_latitude = state.deepResearchLatitude;
  if (state.deepResearchLongitude) payload.deep_research_longitude = state.deepResearchLongitude;
  return payload;
};

export const useChatStore = create<ChatState>((set, get) => ({
  chats: [],
  currentChat: null,
  isLoading: false,
  isSending: false,
  billingModal: { open: false, quote: null, retry: null },
  activeContext: [],
  pendingCanvasContext: null,
  agentSteps: [],
  isAgentRunning: false,

  // Claude Agent SDK Initial State
  isAgentMode: false,
  agentIterationCount: 0,
  contextUsagePercent: 0,
  lastSummaryId: null,
  pendingToolApproval: null,
  toolPermissions: {},
  checkpoints: [],
  parallelExecution: null,
  // CogGRAG State
  cogragTree: null,
  cogragStatus: 'idle' as CogRAGStatus,
  lastToolCall: null,

  effortLevel: 3,
  // Modelo "Juiz" (orquestrador/judge). IDs canônicos (ver config/models.ts)
  selectedModel: 'gemini-3-flash',
  gptModel: 'gpt-5.2',
  claudeModel: 'claude-4.5-sonnet',
  useMultiAgent: true,
  reasoningLevel: 'medium',
  verbosity: 'medium',
  thinkingBudget: '',
  modelOverrides: {},
  mcpToolCalling: loadBooleanPreference(MCP_TOOL_CALLING_STORAGE_KEY, false),
  mcpUseAllServers: loadBooleanPreference(MCP_USE_ALL_SERVERS_STORAGE_KEY, true),
  mcpServerLabels: loadJsonPreference<string[]>(MCP_SERVER_LABELS_STORAGE_KEY, []),
  webSearch: loadBooleanPreference(WEB_SEARCH_STORAGE_KEY, false),
  webSearchModel: loadWebSearchModel(),
  multiQuery: true,
  breadthFirst: false,
  searchMode: 'shared',
  perplexitySearchMode: loadPerplexitySearchMode(),
  perplexitySearchType: loadPerplexitySearchType(),
  perplexitySearchContextSize: loadPerplexitySearchContextSize(),
  perplexitySearchClassifier: loadBooleanPreference(PERPLEXITY_SEARCH_CLASSIFIER_STORAGE_KEY, false),
  perplexityDisableSearch: loadBooleanPreference(PERPLEXITY_DISABLE_SEARCH_STORAGE_KEY, false),
  perplexityStreamMode: loadPerplexityStreamMode(),
  perplexitySearchDomainFilter: loadStringPreference(PERPLEXITY_SEARCH_DOMAIN_FILTER_STORAGE_KEY),
  perplexitySearchLanguageFilter: loadStringPreference(PERPLEXITY_SEARCH_LANGUAGE_FILTER_STORAGE_KEY),
  perplexitySearchRecencyFilter: loadPerplexitySearchRecencyFilter(),
  perplexitySearchAfterDate: loadStringPreference(PERPLEXITY_SEARCH_AFTER_DATE_STORAGE_KEY),
  perplexitySearchBeforeDate: loadStringPreference(PERPLEXITY_SEARCH_BEFORE_DATE_STORAGE_KEY),
  perplexityLastUpdatedAfter: loadStringPreference(PERPLEXITY_LAST_UPDATED_AFTER_STORAGE_KEY),
  perplexityLastUpdatedBefore: loadStringPreference(PERPLEXITY_LAST_UPDATED_BEFORE_STORAGE_KEY),
  perplexitySearchMaxResults: loadOptionalIntPreference(
    PERPLEXITY_SEARCH_MAX_RESULTS_STORAGE_KEY,
    1,
    20
  ),
  perplexitySearchMaxTokens: loadOptionalIntPreference(
    PERPLEXITY_SEARCH_MAX_TOKENS_STORAGE_KEY,
    1,
    1_000_000
  ),
  perplexitySearchMaxTokensPerPage: loadOptionalIntPreference(
    PERPLEXITY_SEARCH_MAX_TOKENS_PER_PAGE_STORAGE_KEY,
    1,
    1_000_000
  ),
  perplexitySearchCountry: loadStringPreference(PERPLEXITY_SEARCH_COUNTRY_STORAGE_KEY),
  perplexitySearchRegion: loadStringPreference(PERPLEXITY_SEARCH_REGION_STORAGE_KEY),
  perplexitySearchCity: loadStringPreference(PERPLEXITY_SEARCH_CITY_STORAGE_KEY),
  perplexitySearchLatitude: loadStringPreference(PERPLEXITY_SEARCH_LATITUDE_STORAGE_KEY),
  perplexitySearchLongitude: loadStringPreference(PERPLEXITY_SEARCH_LONGITUDE_STORAGE_KEY),
  perplexityReturnImages: loadBooleanPreference(PERPLEXITY_RETURN_IMAGES_STORAGE_KEY, false),
  perplexityReturnVideos: loadBooleanPreference(PERPLEXITY_RETURN_VIDEOS_STORAGE_KEY, false),
  researchPolicy: loadResearchPolicy(),
  ragTopK: 8,
  ragSources: ['lei', 'juris'],
  ragGlobalJurisdictions: loadRagGlobalJurisdictions(),
  ragGlobalSourceIds: loadRagGlobalSourceIds(),
  minPages: 0,
  maxPages: 0,
  attachmentMode: 'auto',

  agentStrategistModel: 'gpt-5.2', // GPT implies reasoning/planning
  agentDrafterModels: ['gpt-5.2', 'claude-4.5-sonnet', 'gemini-3-flash'],
  agentReviewerModels: ['gpt-5.2', 'claude-4.5-sonnet', 'gemini-3-flash'],

  denseResearch: loadBooleanPreference(DENSE_RESEARCH_STORAGE_KEY, false),
  deepResearchProvider: loadDeepResearchProvider(),
  deepResearchModel: loadDeepResearchModel(),
  deepResearchEffort: loadDeepResearchEffort(),
  deepResearchMode: (typeof window !== 'undefined'
    ? localStorage.getItem('iudex_deep_research_mode') as 'standard' | 'hard'
    : null) || 'standard',
  hardResearchProviders: (typeof window !== 'undefined'
    ? (() => {
        try { return JSON.parse(localStorage.getItem('iudex_hard_research_providers') || '{}') }
        catch { return {} }
      })()
    : {}) as Record<string, boolean> || {
      gemini: true,
      perplexity: true,
      openai: true,
      rag_global: true,
      rag_local: true,
    },
  deepResearchSearchFocus: loadDeepResearchSearchFocus(),
  deepResearchDomainFilter: loadStringPreference(DEEP_RESEARCH_DOMAIN_FILTER_STORAGE_KEY),
  deepResearchSearchAfterDate: loadStringPreference(DEEP_RESEARCH_SEARCH_AFTER_DATE_STORAGE_KEY),
  deepResearchSearchBeforeDate: loadStringPreference(DEEP_RESEARCH_SEARCH_BEFORE_DATE_STORAGE_KEY),
  deepResearchLastUpdatedAfter: loadStringPreference(DEEP_RESEARCH_LAST_UPDATED_AFTER_STORAGE_KEY),
  deepResearchLastUpdatedBefore: loadStringPreference(DEEP_RESEARCH_LAST_UPDATED_BEFORE_STORAGE_KEY),
  deepResearchCountry: loadStringPreference(DEEP_RESEARCH_COUNTRY_STORAGE_KEY),
  deepResearchLatitude: loadStringPreference(DEEP_RESEARCH_LATITUDE_STORAGE_KEY),
  deepResearchLongitude: loadStringPreference(DEEP_RESEARCH_LONGITUDE_STORAGE_KEY),
  hilOutlineEnabled: false,
  autoApproveHil: false,
  hilTargetSections: [],
  minutaOutlineTemplate: INITIAL_MINUTA_OUTLINE_TEMPLATE,
  minutaOutlineTemplatesBySubtype: INITIAL_MINUTA_OUTLINE_TEMPLATES_BY_SUBTYPE,
  auditMode: 'sei_only',
  qualityProfile: 'padrao',
  qualityTargetSectionScore: null,
  qualityTargetFinalScore: null,
  qualityMaxRounds: null,
  qualityMaxFinalReviewLoops: null,
  qualityStyleRefineMaxRounds: null,
  qualityMaxResearchVerifierAttempts: null,
  qualityMaxRagRetries: null,
  qualityRagRetryExpandScope: null,
  recursionLimitOverride: null,
  strictDocumentGateOverride: null,
  hilSectionPolicyOverride: null,
  hilFinalRequiredOverride: null,
  documentChecklist: [],
  cragMinBestScoreOverride: null,
  cragMinAvgScoreOverride: null,
  forceGranularDebate: false,
  maxDivergenceHilRounds: null,

  // Multi-Model V2
  chatMode: 'standard' as const, // 'standard' | 'multi-model'
  selectedModels: ['gemini-3-flash'], // Default
  multiModelMessages: {}, // Map threadId -> messages
  showMultiModelComparator: true,
  autoConsolidate: false,
  multiModelDeepDebate: loadMultiModelDeepDebate(),
  multiModelView: loadMultiModelView(),

  tenantId: 'default',
  contextMode: 'auto',
  contextFiles: [],
  cacheTTL: 60,
  documentType: 'PETICAO_INICIAL',
  docKind: 'PLEADING',
  docSubtype: 'PETICAO_INICIAL',
  thesis: '',
  formattingOptions: {
    includeToc: true,
    includeSummaries: false,
    includeSummaryTable: true,
  },
  citationStyle: 'abnt',
  useTemplates: false,
  templateFilters: {
    tipoPeca: '',
    area: '',
    rito: '',
    apenasClauseBank: false,
  },
  templateId: null,
  templateDocumentId: null,
  templateVariables: {},
  templateName: null,
  templateDocumentName: null,
  promptExtra: '',
  adaptiveRouting: true, // Default ON for better experience
  cragGate: true,
  hydeEnabled: true,
  graphRagEnabled: true,
  argumentGraphEnabled: true,
  graphHops: 2,
  ragScope: 'case_and_global', // case_only, case_and_global, global_only
  ragSelectedGroups: loadRagSelectedGroups(),
  ragAllowPrivate: true,
  ragAllowGroups: loadRagAllowGroups(),
  sourceSelection: loadSourceSelection(),
  chatPersonality: loadChatPersonality(), // Default to persisted or legal
  creativityMode: 'padrao',
  temperatureOverride: null,
  audit: true,

  // Playbook integration
  selectedPlaybookId: null,
  selectedPlaybookName: null,
  selectedPlaybookPrompt: null,
  isPlaybookLoading: false,

  currentJobId: null,
  jobEvents: [],
  jobOutline: [],
  reviewData: null,
  retryProgress: null,
  chatOutlineReviewEnabled: true,
  pendingChatOutline: null,

  setContext: (context) => set({ activeContext: context }),
  setPendingCanvasContext: (context) => set({ pendingCanvasContext: context }),

  // Playbook setters
  setSelectedPlaybook: (id, name, prompt) =>
    set({
      selectedPlaybookId: id,
      selectedPlaybookName: name,
      selectedPlaybookPrompt: prompt,
      isPlaybookLoading: false,
    }),
  clearPlaybook: () =>
    set({
      selectedPlaybookId: null,
      selectedPlaybookName: null,
      selectedPlaybookPrompt: null,
      isPlaybookLoading: false,
    }),
  setEffortLevel: (level) => set({ effortLevel: level }),
  setSelectedModel: (model) => {
    const current = get();
    if (isPerplexityDeepResearchModelId(model)) {
      if (!current.denseResearch) current.setDenseResearch(true);
      if (current.deepResearchProvider !== 'perplexity') current.setDeepResearchProvider('perplexity');
      if (current.deepResearchModel !== 'sonar-deep-research') {
        current.setDeepResearchModel('sonar-deep-research');
      }
    }
    set((state) => {
      if (state.chatMode === 'standard' && isPerplexityModelId(model) && !state.webSearch) {
        if (typeof window !== 'undefined') {
          try {
            localStorage.setItem(WEB_SEARCH_STORAGE_KEY, 'true');
          } catch {
            // ignore storage errors
          }
        }
        toast.info('Web Search ativado para modelos Sonar.');
      }
      return {
        selectedModel: model,
        agentStrategistModel: model,
        ...(state.chatMode === 'standard'
          ? { selectedModels: [model], webSearch: state.webSearch || isPerplexityModelId(model) }
          : {}),
      };
    });
  },
  setGptModel: (model) => set({ gptModel: model }),
  setClaudeModel: (model) => set({ claudeModel: model }),
  setAgentStrategistModel: (model) => {
    const current = get();
    if (isPerplexityDeepResearchModelId(model)) {
      if (!current.denseResearch) current.setDenseResearch(true);
      if (current.deepResearchProvider !== 'perplexity') current.setDeepResearchProvider('perplexity');
      if (current.deepResearchModel !== 'sonar-deep-research') {
        current.setDeepResearchModel('sonar-deep-research');
      }
    }
    set((state) => {
      if (state.chatMode === 'standard' && isPerplexityModelId(model) && !state.webSearch) {
        if (typeof window !== 'undefined') {
          try {
            localStorage.setItem(WEB_SEARCH_STORAGE_KEY, 'true');
          } catch {
            // ignore storage errors
          }
        }
        toast.info('Web Search ativado para modelos Sonar.');
      }
      return {
        agentStrategistModel: model,
        selectedModel: model,
        ...(state.chatMode === 'standard'
          ? { selectedModels: [model], webSearch: state.webSearch || isPerplexityModelId(model) }
          : {}),
      };
    });
  },
  setAgentDrafterModels: (models) => set({ agentDrafterModels: models }),
  setAgentReviewerModels: (models) => set({ agentReviewerModels: models }),
  setUseMultiAgent: (use) => set({ useMultiAgent: use }),
  setReasoningLevel: (level) => set({ reasoningLevel: level }),
  setVerbosity: (level) => set({ verbosity: level }),
  setThinkingBudget: (value) => set({ thinkingBudget: value }),
  setModelOverride: (modelId, patch) =>
    set((state) => {
      const nextOverrides = { ...(state.modelOverrides || {}) };
      const current = { ...(nextOverrides[modelId] || {}) };
      if ('verbosity' in patch) {
        if (patch.verbosity) {
          current.verbosity = patch.verbosity;
        } else {
          delete current.verbosity;
        }
      }
      if ('reasoningLevel' in patch) {
        if (patch.reasoningLevel) {
          current.reasoningLevel = patch.reasoningLevel;
        } else {
          delete current.reasoningLevel;
        }
      }
      if ('thinkingBudget' in patch) {
        const value = patch.thinkingBudget;
        if (value !== undefined && value !== '') {
          current.thinkingBudget = value;
        } else {
          delete current.thinkingBudget;
        }
      }
      if (Object.keys(current).length === 0) {
        delete nextOverrides[modelId];
      } else {
        nextOverrides[modelId] = current;
      }
      return { modelOverrides: nextOverrides };
    }),
  setChatPersonality: (personality) => {
    set({ chatPersonality: personality });
    if (typeof window !== 'undefined') {
      localStorage.setItem(CHAT_PERSONALITY_KEY, personality);
    }
  },
  setCreativityMode: (mode) => set({ creativityMode: mode }),
  setTemperatureOverride: (value) =>
    set({
      temperatureOverride:
        typeof value === 'number' && Number.isFinite(value) ? clamp01(value) : null,
    }),
  setChatOutlineReviewEnabled: (enabled) => set({ chatOutlineReviewEnabled: enabled }),
  setMcpToolCalling: (enabled) => {
    set({ mcpToolCalling: enabled });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(MCP_TOOL_CALLING_STORAGE_KEY, String(enabled));
      } catch {
        // ignore storage errors
      }
    }
  },
  setMcpUseAllServers: (enabled) => {
    set({ mcpUseAllServers: enabled });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(MCP_USE_ALL_SERVERS_STORAGE_KEY, String(enabled));
      } catch {
        // ignore storage errors
      }
    }
  },
  setMcpServerLabels: (labels) => {
    const next = Array.from(
      new Set((Array.isArray(labels) ? labels : []).map((x) => String(x || '').trim()).filter(Boolean))
    );
    set({ mcpServerLabels: next });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(MCP_SERVER_LABELS_STORAGE_KEY, JSON.stringify(next));
      } catch {
        // ignore storage errors
      }
    }
  },
  setWebSearch: (enabled) => {
    const state = get();
    const hasSonarSelected = Array.isArray(state.selectedModels)
      ? state.selectedModels.some((modelId) => isPerplexityModelId(modelId))
      : false;

    if (!enabled && hasSonarSelected) {
      toast.info('Modelos Sonar requerem Web Search ativado.');
      enabled = true;
    }

    set({ webSearch: enabled });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(WEB_SEARCH_STORAGE_KEY, String(enabled));
      } catch {
        // ignore storage errors
      }
    }
  },
  setWebSearchModel: (model) => {
    const next = (model || '').trim() || 'auto';
    set({ webSearchModel: next });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(LANGGRAPH_WEB_SEARCH_MODEL_STORAGE_KEY, next);
      } catch {
        // ignore storage errors
      }
    }
  },
  setMultiQuery: (enabled) => set({ multiQuery: enabled }),
  setBreadthFirst: (enabled) => set({ breadthFirst: enabled }),
  setSearchMode: (mode) => set({ searchMode: mode === 'perplexity' ? 'shared' : mode }),
  setPerplexitySearchMode: (mode) => {
    set({ perplexitySearchMode: mode });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_SEARCH_MODE_STORAGE_KEY, mode);
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexitySearchType: (mode) => {
    set({ perplexitySearchType: mode });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_SEARCH_TYPE_STORAGE_KEY, mode);
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexitySearchContextSize: (size) => {
    set({ perplexitySearchContextSize: size });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_SEARCH_CONTEXT_SIZE_STORAGE_KEY, size);
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexitySearchClassifier: (enabled) => {
    set({ perplexitySearchClassifier: enabled });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_SEARCH_CLASSIFIER_STORAGE_KEY, String(enabled));
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexityDisableSearch: (enabled) => {
    set({ perplexityDisableSearch: enabled });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_DISABLE_SEARCH_STORAGE_KEY, String(enabled));
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexityStreamMode: (mode) => {
    set({ perplexityStreamMode: mode });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_STREAM_MODE_STORAGE_KEY, mode);
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexitySearchDomainFilter: (value) => {
    set({ perplexitySearchDomainFilter: value });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_SEARCH_DOMAIN_FILTER_STORAGE_KEY, value);
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexitySearchLanguageFilter: (value) => {
    set({ perplexitySearchLanguageFilter: value });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_SEARCH_LANGUAGE_FILTER_STORAGE_KEY, value);
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexitySearchRecencyFilter: (value) => {
    set({ perplexitySearchRecencyFilter: value });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_SEARCH_RECENCY_FILTER_STORAGE_KEY, value);
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexitySearchAfterDate: (value) => {
    set({ perplexitySearchAfterDate: value });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_SEARCH_AFTER_DATE_STORAGE_KEY, value);
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexitySearchBeforeDate: (value) => {
    set({ perplexitySearchBeforeDate: value });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_SEARCH_BEFORE_DATE_STORAGE_KEY, value);
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexityLastUpdatedAfter: (value) => {
    set({ perplexityLastUpdatedAfter: value });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_LAST_UPDATED_AFTER_STORAGE_KEY, value);
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexityLastUpdatedBefore: (value) => {
    set({ perplexityLastUpdatedBefore: value });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_LAST_UPDATED_BEFORE_STORAGE_KEY, value);
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexitySearchMaxResults: (value) => {
    const normalized = (value || '').replace(/[^\d]/g, '');
    set({ perplexitySearchMaxResults: normalized });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_SEARCH_MAX_RESULTS_STORAGE_KEY, normalized);
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexitySearchMaxTokens: (value) => {
    const normalized = (value || '').replace(/[^\d]/g, '');
    set({ perplexitySearchMaxTokens: normalized });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_SEARCH_MAX_TOKENS_STORAGE_KEY, normalized);
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexitySearchMaxTokensPerPage: (value) => {
    const normalized = (value || '').replace(/[^\d]/g, '');
    set({ perplexitySearchMaxTokensPerPage: normalized });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_SEARCH_MAX_TOKENS_PER_PAGE_STORAGE_KEY, normalized);
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexitySearchCountry: (value) => {
    set({ perplexitySearchCountry: value });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_SEARCH_COUNTRY_STORAGE_KEY, value);
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexitySearchRegion: (value) => {
    set({ perplexitySearchRegion: value });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_SEARCH_REGION_STORAGE_KEY, value);
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexitySearchCity: (value) => {
    set({ perplexitySearchCity: value });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_SEARCH_CITY_STORAGE_KEY, value);
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexitySearchLatitude: (value) => {
    set({ perplexitySearchLatitude: value });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_SEARCH_LATITUDE_STORAGE_KEY, value);
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexitySearchLongitude: (value) => {
    set({ perplexitySearchLongitude: value });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_SEARCH_LONGITUDE_STORAGE_KEY, value);
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexityReturnImages: (enabled) => {
    set({ perplexityReturnImages: enabled });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_RETURN_IMAGES_STORAGE_KEY, String(enabled));
      } catch {
        // ignore storage errors
      }
    }
  },
  setPerplexityReturnVideos: (enabled) => {
    set({ perplexityReturnVideos: enabled });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(PERPLEXITY_RETURN_VIDEOS_STORAGE_KEY, String(enabled));
      } catch {
        // ignore storage errors
      }
    }
  },
  setResearchPolicy: (policy) => {
    set({ researchPolicy: policy });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(RESEARCH_POLICY_STORAGE_KEY, policy);
      } catch {
        // ignore storage errors
      }
    }
  },
  setRagTopK: (k) => set({ ragTopK: k }),
  setRagSources: (sources) => set({ ragSources: sources }),
  setRagGlobalJurisdictions: (jurisdictions) => {
    const normalized = (Array.isArray(jurisdictions) ? jurisdictions : [])
      .map((v) => String(v || '').trim().toUpperCase())
      .filter(Boolean);
    persistRagGlobalJurisdictions(normalized);
    set({ ragGlobalJurisdictions: normalized });
  },
  toggleRagGlobalJurisdiction: (jurisdiction) => {
    const id = String(jurisdiction || '').trim().toUpperCase();
    if (!id) return;
    set((state) => {
      const current = new Set(state.ragGlobalJurisdictions || []);
      if (current.has(id)) current.delete(id);
      else current.add(id);
      const next = Array.from(current);
      persistRagGlobalJurisdictions(next);
      return { ragGlobalJurisdictions: next };
    });
  },
  clearRagGlobalJurisdictions: () => {
    persistRagGlobalJurisdictions([]);
    set({ ragGlobalJurisdictions: [] });
  },
  setRagGlobalSourceIds: (sourceIds) => {
    const normalized = (Array.isArray(sourceIds) ? sourceIds : [])
      .map((v) => String(v || '').trim())
      .filter(Boolean);
    persistRagGlobalSourceIds(normalized);
    set({ ragGlobalSourceIds: normalized });
  },
  toggleRagGlobalSourceId: (sourceId) => {
    const id = String(sourceId || '').trim();
    if (!id) return;
    set((state) => {
      const current = new Set(state.ragGlobalSourceIds || []);
      if (current.has(id)) current.delete(id);
      else current.add(id);
      const next = Array.from(current);
      persistRagGlobalSourceIds(next);
      return { ragGlobalSourceIds: next };
    });
  },
  clearRagGlobalSourceIds: () => {
    persistRagGlobalSourceIds([]);
    set({ ragGlobalSourceIds: [] });
  },
  setPageRange: (range) =>
    set((state) =>
      normalizePageRange(range.minPages ?? state.minPages, range.maxPages ?? state.maxPages)
    ),
  resetPageRange: () => set({ minPages: 0, maxPages: 0 }),
  setAttachmentMode: (mode) => set({ attachmentMode: mode }),
  setDenseResearch: (enabled) => {
    const state = get();
    const hasDeepResearchModel = Array.isArray(state.selectedModels)
      ? state.selectedModels.some((modelId) => isPerplexityDeepResearchModelId(modelId))
      : false;
    if (!enabled && hasDeepResearchModel) {
      toast.info('Sonar Deep Research requer Deep Research ativado.');
      enabled = true;
    }
    set({ denseResearch: enabled });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(DENSE_RESEARCH_STORAGE_KEY, String(enabled));
      } catch {
        // ignore storage errors
      }
    }
  },
  setDeepResearchProvider: (provider) => {
    set((state) => ({
      deepResearchProvider: provider,
      deepResearchModel:
        provider === 'perplexity' ? 'sonar-deep-research' : state.deepResearchModel,
    }));
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(DEEP_RESEARCH_PROVIDER_STORAGE_KEY, provider);
        if (provider === 'perplexity') {
          localStorage.setItem(DEEP_RESEARCH_MODEL_STORAGE_KEY, 'sonar-deep-research');
        }
      } catch {
        // ignore storage errors
      }
    }
  },
  setDeepResearchModel: (model) => {
    const resolved = model === 'sonar-deep-research' ? model : 'sonar-deep-research';
    set({ deepResearchModel: resolved });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(DEEP_RESEARCH_MODEL_STORAGE_KEY, resolved);
      } catch {
        // ignore storage errors
      }
    }
  },
  setDeepResearchEffort: (effort) => {
    set({ deepResearchEffort: effort });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(DEEP_RESEARCH_EFFORT_STORAGE_KEY, effort);
      } catch {
        // ignore storage errors
      }
    }
  },
  setDeepResearchMode: (mode) => {
    set({ deepResearchMode: mode });
    if (typeof window !== 'undefined') {
      localStorage.setItem('iudex_deep_research_mode', mode);
    }
  },
  setHardResearchProvider: (provider, enabled) => {
    const current = get().hardResearchProviders;
    const updated = { ...current, [provider]: enabled };
    set({ hardResearchProviders: updated });
    if (typeof window !== 'undefined') {
      localStorage.setItem('iudex_hard_research_providers', JSON.stringify(updated));
    }
  },
  toggleHardResearchProvider: (provider) => {
    const current = get().hardResearchProviders;
    const enabled = current[provider] !== false; // default true
    get().setHardResearchProvider(provider, !enabled);
  },
  setAllHardResearchProviders: (enabled) => {
    const updated = {
      gemini: enabled,
      perplexity: enabled,
      openai: enabled,
      rag_global: enabled,
      rag_local: enabled,
    };
    set({ hardResearchProviders: updated });
    if (typeof window !== 'undefined') {
      localStorage.setItem('iudex_hard_research_providers', JSON.stringify(updated));
    }
  },
  setDeepResearchSearchFocus: (value) => {
    set({ deepResearchSearchFocus: value });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(DEEP_RESEARCH_SEARCH_FOCUS_STORAGE_KEY, value);
      } catch {
        // ignore storage errors
      }
    }
  },
  setDeepResearchDomainFilter: (value) => {
    set({ deepResearchDomainFilter: value });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(DEEP_RESEARCH_DOMAIN_FILTER_STORAGE_KEY, value);
      } catch {
        // ignore storage errors
      }
    }
  },
  setDeepResearchSearchAfterDate: (value) => {
    set({ deepResearchSearchAfterDate: value });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(DEEP_RESEARCH_SEARCH_AFTER_DATE_STORAGE_KEY, value);
      } catch {
        // ignore storage errors
      }
    }
  },
  setDeepResearchSearchBeforeDate: (value) => {
    set({ deepResearchSearchBeforeDate: value });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(DEEP_RESEARCH_SEARCH_BEFORE_DATE_STORAGE_KEY, value);
      } catch {
        // ignore storage errors
      }
    }
  },
  setDeepResearchLastUpdatedAfter: (value) => {
    set({ deepResearchLastUpdatedAfter: value });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(DEEP_RESEARCH_LAST_UPDATED_AFTER_STORAGE_KEY, value);
      } catch {
        // ignore storage errors
      }
    }
  },
  setDeepResearchLastUpdatedBefore: (value) => {
    set({ deepResearchLastUpdatedBefore: value });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(DEEP_RESEARCH_LAST_UPDATED_BEFORE_STORAGE_KEY, value);
      } catch {
        // ignore storage errors
      }
    }
  },
  setDeepResearchCountry: (value) => {
    set({ deepResearchCountry: value });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(DEEP_RESEARCH_COUNTRY_STORAGE_KEY, value);
      } catch {
        // ignore storage errors
      }
    }
  },
  setDeepResearchLatitude: (value) => {
    set({ deepResearchLatitude: value });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(DEEP_RESEARCH_LATITUDE_STORAGE_KEY, value);
      } catch {
        // ignore storage errors
      }
    }
  },
  setDeepResearchLongitude: (value) => {
    set({ deepResearchLongitude: value });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(DEEP_RESEARCH_LONGITUDE_STORAGE_KEY, value);
      } catch {
        // ignore storage errors
      }
    }
  },
  setHilOutlineEnabled: (enabled) => set({ hilOutlineEnabled: enabled }),
  setAutoApproveHil: (enabled) => set({ autoApproveHil: enabled }),
  setHilTargetSections: (sections) => set({ hilTargetSections: sections }),
  setMinutaOutlineTemplate: (value) => {
    const next = stripBaseMarker(String(value ?? ''));
    const subtype = String(get().docSubtype || get().documentType || '').trim();
    const currentBySubtype = get().minutaOutlineTemplatesBySubtype || {};
    const nextBySubtype = subtype ? { ...currentBySubtype, [subtype]: next } : currentBySubtype;

    set({ minutaOutlineTemplate: next, minutaOutlineTemplatesBySubtype: nextBySubtype });
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(MINUTA_OUTLINE_TEMPLATE_STORAGE_KEY, next);
      } catch {
        // ignore storage errors
      }
      try {
        localStorage.setItem(
          MINUTA_OUTLINE_TEMPLATES_BY_SUBTYPE_STORAGE_KEY,
          JSON.stringify(nextBySubtype)
        );
      } catch {
        // ignore storage errors
      }
    }
  },
  setAuditMode: (mode) => set({ auditMode: mode }),
  setQualityProfile: (profile) => set({ qualityProfile: profile }),
  setQualityTargetSectionScore: (value) => set({ qualityTargetSectionScore: value }),
  setQualityTargetFinalScore: (value) => set({ qualityTargetFinalScore: value }),
  setQualityMaxRounds: (value) => set({ qualityMaxRounds: value }),
  setQualityMaxFinalReviewLoops: (value) => set({ qualityMaxFinalReviewLoops: value }),
  setQualityStyleRefineMaxRounds: (value) => set({ qualityStyleRefineMaxRounds: value }),
  setQualityMaxResearchVerifierAttempts: (value) =>
    set({ qualityMaxResearchVerifierAttempts: value }),
  setQualityMaxRagRetries: (value) => set({ qualityMaxRagRetries: value }),
  setQualityRagRetryExpandScope: (value) => set({ qualityRagRetryExpandScope: value }),
  setRecursionLimitOverride: (value) => set({ recursionLimitOverride: value }),
  setStrictDocumentGateOverride: (value) => set({ strictDocumentGateOverride: value }),
  setHilSectionPolicyOverride: (value) => set({ hilSectionPolicyOverride: value }),
  setHilFinalRequiredOverride: (value) => set({ hilFinalRequiredOverride: value }),
  setDocumentChecklist: (items) => set({ documentChecklist: items }),
  setCragMinBestScoreOverride: (value) => set({ cragMinBestScoreOverride: value }),
  setCragMinAvgScoreOverride: (value) => set({ cragMinAvgScoreOverride: value }),
  setForceGranularDebate: (enabled) => set({ forceGranularDebate: enabled }),
  setMaxDivergenceHilRounds: (value) => set({ maxDivergenceHilRounds: value }),
  setAdaptiveRouting: () => set({ adaptiveRouting: true }),
  setCragGate: () => set({ cragGate: true }),
  setHydeEnabled: () => set({ hydeEnabled: true }),
  setGraphRagEnabled: () => set({ graphRagEnabled: true, argumentGraphEnabled: true }),
  setArgumentGraphEnabled: () => set({ argumentGraphEnabled: true, graphRagEnabled: true }),
  setGraphHops: (hops) => set({ graphHops: hops }),
  setRagScope: (scope) => set({ ragScope: scope }),
  setRagSelectedGroups: (groupIds) => {
    const normalized = (Array.isArray(groupIds) ? groupIds : [])
      .map((v) => String(v || '').trim())
      .filter(Boolean);
    persistRagSelectedGroups(normalized);
    set({ ragSelectedGroups: normalized });
  },
  setRagAllowPrivate: (allow) => {
    set({ ragAllowPrivate: Boolean(allow) });
    if (!allow) {
      // Desligar corpus privado também desliga departamentos
      persistRagAllowGroups(false);
      set({ ragAllowGroups: false, ragSelectedGroups: [] });
    }
  },
  setRagAllowGroups: (allow) => {
    persistRagAllowGroups(Boolean(allow));
    set({ ragAllowGroups: Boolean(allow) });
  },
  toggleRagSelectedGroup: (groupId) => {
    const id = String(groupId || '').trim();
    if (!id) return;
    set((state) => {
      const current = new Set(state.ragSelectedGroups || []);
      if (current.has(id)) current.delete(id);
      else current.add(id);
      const next = Array.from(current);
      persistRagSelectedGroups(next);
      return { ragSelectedGroups: next };
    });
  },
  clearRagSelectedGroups: () => {
    persistRagSelectedGroups([]);
    set({ ragSelectedGroups: [] });
  },

  // Source Selection Actions
  setSourceSelection: (selection) => {
    persistSourceSelection(selection);
    set({ sourceSelection: selection });
  },

  toggleSource: (category, id) => {
    set((state) => {
      const next = { ...state.sourceSelection };
      if (category === 'webSearch') {
        next.webSearch = !next.webSearch;
      } else if (category === 'attachments' && id) {
        next.attachments = { ...next.attachments, [id]: !next.attachments[id] };
      } else if (category === 'corpusGlobal' && id) {
        const key = id as keyof CorpusGlobalSelection;
        next.corpusGlobal = { ...next.corpusGlobal, [key]: !next.corpusGlobal[key] };
      } else if (category === 'corpusPrivado' && id) {
        next.corpusPrivado = { ...next.corpusPrivado, [id]: !next.corpusPrivado[id] };
      } else if (category === 'mcpConnectors' && id) {
        next.mcpConnectors = { ...next.mcpConnectors, [id]: !next.mcpConnectors[id] };
      }
      persistSourceSelection(next);
      return { sourceSelection: next };
    });
  },

  selectAllInCategory: (category) => {
    set((state) => {
      const next = { ...state.sourceSelection };
      if (category === 'webSearch') {
        next.webSearch = true;
      } else if (category === 'attachments') {
        next.attachments = Object.fromEntries(
          Object.keys(next.attachments).map((k) => [k, true])
        );
      } else if (category === 'corpusGlobal') {
        next.corpusGlobal = {
          legislacao: true,
          jurisprudencia: true,
          pecasModelo: true,
          doutrina: true,
          sei: true,
        };
      } else if (category === 'corpusPrivado') {
        next.corpusPrivado = Object.fromEntries(
          Object.keys(next.corpusPrivado).map((k) => [k, true])
        );
      } else if (category === 'mcpConnectors') {
        next.mcpConnectors = Object.fromEntries(
          Object.keys(next.mcpConnectors).map((k) => [k, true])
        );
      }
      persistSourceSelection(next);
      return { sourceSelection: next };
    });
  },

  deselectAllInCategory: (category) => {
    set((state) => {
      const next = { ...state.sourceSelection };
      if (category === 'webSearch') {
        next.webSearch = false;
      } else if (category === 'attachments') {
        next.attachments = Object.fromEntries(
          Object.keys(next.attachments).map((k) => [k, false])
        );
      } else if (category === 'corpusGlobal') {
        next.corpusGlobal = {
          legislacao: false,
          jurisprudencia: false,
          pecasModelo: false,
          doutrina: false,
          sei: false,
        };
      } else if (category === 'corpusPrivado') {
        next.corpusPrivado = Object.fromEntries(
          Object.keys(next.corpusPrivado).map((k) => [k, false])
        );
      } else if (category === 'mcpConnectors') {
        next.mcpConnectors = Object.fromEntries(
          Object.keys(next.mcpConnectors).map((k) => [k, false])
        );
      }
      persistSourceSelection(next);
      return { sourceSelection: next };
    });
  },

  setAttachmentEnabled: (fileId, enabled) => {
    set((state) => {
      const next = {
        ...state.sourceSelection,
        attachments: { ...state.sourceSelection.attachments, [fileId]: enabled },
      };
      persistSourceSelection(next);
      return { sourceSelection: next };
    });
  },

  setCorpusGlobalEnabled: (key, enabled) => {
    set((state) => {
      const next = {
        ...state.sourceSelection,
        corpusGlobal: { ...state.sourceSelection.corpusGlobal, [key]: enabled },
      };
      persistSourceSelection(next);
      return { sourceSelection: next };
    });
  },

  setCorpusPrivadoEnabled: (projectId, enabled) => {
    set((state) => {
      const next = {
        ...state.sourceSelection,
        corpusPrivado: { ...state.sourceSelection.corpusPrivado, [projectId]: enabled },
      };
      persistSourceSelection(next);
      return { sourceSelection: next };
    });
  },

  setMcpConnectorEnabled: (label, enabled) => {
    set((state) => {
      const next = {
        ...state.sourceSelection,
        mcpConnectors: { ...state.sourceSelection.mcpConnectors, [label]: enabled },
      };
      persistSourceSelection(next);
      return { sourceSelection: next };
    });
  },

  getActiveSourcesCount: () => {
    const state = get();
    const sel = state.sourceSelection;
    let count = 0;

    if (sel.webSearch) count++;
    count += Object.values(sel.attachments).filter(Boolean).length;
    count += Object.values(sel.corpusGlobal).filter(Boolean).length;
    count += Object.values(sel.corpusPrivado).filter(Boolean).length;
    count += Object.values(sel.mcpConnectors).filter(Boolean).length;

    return count;
  },

  getActiveSourceIcons: () => {
    const state = get();
    const sel = state.sourceSelection;
    const icons: string[] = [];

    if (sel.webSearch) icons.push(SOURCE_ICONS.webSearch);
    if (Object.values(sel.attachments).some(Boolean)) icons.push(SOURCE_ICONS.attachments);
    if (sel.corpusGlobal.legislacao) icons.push(SOURCE_ICONS.legislacao);
    if (sel.corpusGlobal.jurisprudencia) icons.push(SOURCE_ICONS.jurisprudencia);
    if (sel.corpusGlobal.pecasModelo) icons.push(SOURCE_ICONS.pecasModelo);
    if (sel.corpusGlobal.doutrina) icons.push(SOURCE_ICONS.doutrina);
    if (sel.corpusGlobal.sei) icons.push(SOURCE_ICONS.sei);
    if (Object.values(sel.corpusPrivado).some(Boolean)) icons.push(SOURCE_ICONS.corpusPrivado);
    if (Object.values(sel.mcpConnectors).some(Boolean)) icons.push(SOURCE_ICONS.mcpConnectors);

    return icons;
  },

  // V2 Setters
  setChatMode: (mode) =>
    set((state) => {
      const nextSelected =
        mode === 'standard' && state.selectedModels.length > 0
          ? [state.selectedModels[0]]
          : state.selectedModels;
      return {
        chatMode: mode as any,
        selectedModels: nextSelected,
        ...(mode === 'standard' && nextSelected.length === 1
          ? { selectedModel: nextSelected[0], agentStrategistModel: nextSelected[0] }
          : {}),
      };
    }),
  setSelectedModels: (models) => {
    const input = Array.isArray(models) ? models : [];
    const normalized = input.map((m) => String(m || '').trim()).filter(Boolean);
    if (normalized.some((m) => isPerplexityDeepResearchModelId(m))) {
      const current = get();
      if (!current.denseResearch) current.setDenseResearch(true);
      if (current.deepResearchProvider !== 'perplexity') current.setDeepResearchProvider('perplexity');
      if (current.deepResearchModel !== 'sonar-deep-research') {
        current.setDeepResearchModel('sonar-deep-research');
      }
    }
    set((state) => {
      const filtered = normalized;

      const shouldEnableWebSearch =
        state.chatMode === 'standard' &&
        filtered.length === 1 &&
        isPerplexityModelId(filtered[0]) &&
        !state.webSearch;
      if (shouldEnableWebSearch) {
        if (typeof window !== 'undefined') {
          try {
            localStorage.setItem(WEB_SEARCH_STORAGE_KEY, 'true');
          } catch {
            // ignore storage errors
          }
        }
        toast.info('Web Search ativado para modelos Sonar.');
      }

      return {
        selectedModels: filtered,
        ...(state.chatMode === 'standard' && filtered.length === 1
          ? {
            selectedModel: filtered[0],
            agentStrategistModel: filtered[0],
            ...(shouldEnableWebSearch ? { webSearch: true } : {}),
          }
          : {}),
      };
    });
  },
  setShowMultiModelComparator: (enabled) => set({ showMultiModelComparator: enabled }),
  setAutoConsolidate: (enabled) => set({ autoConsolidate: enabled }),
  setMultiModelDeepDebate: (enabled) => {
    try {
      if (typeof window !== 'undefined') {
        localStorage.setItem(MULTI_MODEL_DEEP_DEBATE_STORAGE_KEY, String(!!enabled));
      }
    } catch {
      // noop
    }
    set({ multiModelDeepDebate: !!enabled });
  },
  setMultiModelView: (view) => {
    try {
      if (typeof window !== 'undefined') {
        localStorage.setItem(MULTI_MODEL_VIEW_STORAGE_KEY, view);
      }
    } catch {
      // noop
    }
    set({ multiModelView: view });
  },
  toggleModel: (modelId) => {
    const current = get();
    if (isPerplexityDeepResearchModelId(modelId)) {
      if (!current.denseResearch) current.setDenseResearch(true);
      if (current.deepResearchProvider !== 'perplexity') current.setDeepResearchProvider('perplexity');
      if (current.deepResearchModel !== 'sonar-deep-research') {
        current.setDeepResearchModel('sonar-deep-research');
      }
    }

    if (isPerplexityModelId(modelId) && !current.webSearch) {
      current.setWebSearch(true);
      toast.info('Web Search ativado para modelos Sonar.');
    }

    set((state) => {
      if (state.chatMode === 'standard') {
        return {
          selectedModels: [modelId],
          selectedModel: modelId,
          agentStrategistModel: modelId,
        };
      }
      const currentSelected = state.selectedModels;
      if (currentSelected.includes(modelId)) {
        return { selectedModels: currentSelected.filter((m) => m !== modelId) };
      }
      return { selectedModels: [...currentSelected, modelId] };
    });
  },

  setTenantId: (id) => set({ tenantId: id }),
  setContextMode: (mode) => set({ contextMode: mode }),
  setContextFiles: (files) => set({ contextFiles: files }),
  setCacheTTL: (ttl) => set({ cacheTTL: ttl }),
  setDocumentType: (type) =>
    set((state) => {
      const nextSubtype = type || null;
      const nextTemplate = resolveMinutaOutlineTemplateForSubtype(
        nextSubtype,
        state.minutaOutlineTemplatesBySubtype || {}
      );
      if (typeof window !== 'undefined') {
        try {
          localStorage.setItem(MINUTA_OUTLINE_TEMPLATE_STORAGE_KEY, nextTemplate);
        } catch {
          // ignore storage errors
        }
      }
      return {
        documentType: type,
        docSubtype: nextSubtype,
        docKind: inferDocKindFromType(type) || null,
        minutaOutlineTemplate: nextTemplate,
      };
    }),
  setThesis: (thesis) => set({ thesis }),
  setFormattingOptions: (options) =>
    set((state) => ({
      formattingOptions: { ...state.formattingOptions, ...options },
    })),
  setCitationStyle: (style) => set({ citationStyle: style }),
  setUseTemplates: (use) => set({ useTemplates: use }),
  setTemplateFilters: (filters) =>
    set((state) => ({
      templateFilters: { ...state.templateFilters, ...filters },
    })),
  setTemplateId: (id) => set({ templateId: id }),
  setTemplateDocumentId: (id) => set({ templateDocumentId: id }),
  setTemplateVariables: (vars) => set({ templateVariables: vars }),
  setTemplateName: (name) => set({ templateName: name }),
  setTemplateDocumentName: (name) => set({ templateDocumentName: name }),
  setPromptExtra: (prompt) => set({ promptExtra: prompt }),
  setAudit: (enabled) => set({ audit: enabled }),

  fetchChats: async () => {
    set({ isLoading: true });
    try {
      const response = await apiClient.getChats();
      // @ts-ignore
      const nextChats = Array.isArray((response as any)?.chats)
        ? (response as any).chats
        : MOCK_CHATS;
      set({ chats: nextChats, isLoading: false });
    } catch (error) {
      console.error('[ChatStore] Error fetching chats:', describeApiError(error), error);
      set({ chats: MOCK_CHATS, isLoading: false });
    }
  },

  setCurrentChat: async (chatId: string | null) => {
    if (!chatId) {
      set({ currentChat: null });
      return;
    }

    const current = get().currentChat;
    if (current?.id === chatId && (current.messages?.length ?? 0) > 0) {
      const { setMetadata } = useCanvasStore.getState();
      const stored = loadDraftMetadata(chatId);
      if (stored) {
        setMetadata(stored, null);
      }
      return;
    }

    set({ isLoading: true });
    try {
      const chat = await apiClient.getChat(chatId);
      // Ensure messages is always an array
      const normalizedChat = {
        ...chat,
        messages: (chat as any)?.messages || [],
      };
      // @ts-ignore
      set({ currentChat: normalizedChat, isLoading: false });
      const { setMetadata } = useCanvasStore.getState();
      const stored = loadDraftMetadata(chatId);
      setMetadata(stored || null, null);
    } catch (error) {
      console.error('Error fetching chat:', error);
      const fallbackChat = get().chats.find((c) => c.id === chatId);
      // Ensure fallback also has messages array
      const normalizedFallback = fallbackChat
        ? { ...fallbackChat, messages: fallbackChat.messages || [] }
        : null;
      set({ currentChat: normalizedFallback, isLoading: false });
      const { setMetadata } = useCanvasStore.getState();
      const stored = loadDraftMetadata(chatId);
      setMetadata(stored || null, null);
    }
  },

  createChat: async (title?: string) => {
    set({ isLoading: true });
    try {
      const newChat = (await apiClient.createChat({ title })) as any;
      // Ensure messages is always an array
      const normalizedChat = {
        ...newChat,
        messages: newChat?.messages || [],
      };
      set((state) => ({
        chats: [normalizedChat, ...state.chats],
        currentChat: normalizedChat,
        isLoading: false,
      }));
      return normalizedChat;
    } catch (error) {
      console.error('[ChatStore] Error creating chat:', describeApiError(error), error);
      set({ isLoading: false });
      throw error;
    }
  },

  duplicateChat: async (chatId: string, title?: string) => {
    set({ isLoading: true });
    try {
      const newChat = (await apiClient.duplicateChat(chatId, title)) as any;
      const normalizedChat = {
        ...newChat,
        messages: newChat?.messages || [],
      };
      set((state) => ({
        chats: [normalizedChat, ...state.chats],
        currentChat: normalizedChat,
        isLoading: false,
      }));
      return normalizedChat;
    } catch (error) {
      console.error('[ChatStore] Error duplicating chat:', describeApiError(error), error);
      set({ isLoading: false });
      throw error;
    }
  },

  createMultiChatThread: async (title?: string) => {
    set({ isLoading: true });
    try {
      const newThread = await apiClient.createMultiChatThread(title);
      // Map to Chat interface
      const chat: Chat = {
        id: newThread.id,
        title: newThread.title,
        messages: [],
        created_at: newThread.created_at,
        updated_at: newThread.updated_at,
        is_active: true,
      };

      set((state) => ({
        chats: [chat, ...state.chats],
        currentChat: chat,
        isLoading: false,
      }));
      return chat;
    } catch (error) {
      console.error('Error creating multi-chat thread:', error);
      set({ isLoading: false });
      throw error;
    }
  },

  deleteChat: async (chatId: string) => {
    try {
      await apiClient.deleteChat(chatId);
      clearDraftMetadata(chatId);
      set((state) => ({
        chats: state.chats.filter((c) => c.id !== chatId),
        currentChat: state.currentChat?.id === chatId ? null : state.currentChat,
      }));
    } catch (error) {
      console.error('Error deleting chat:', error);
    }
  },

  closeBillingModal: () => {
    set({ billingModal: { open: false, quote: null, retry: null } });
  },

  retryWithBudgetOverride: async (budgetPoints: number) => {
    const { billingModal } = get();
    const retry = billingModal?.retry;
    if (!retry) {
      set({ billingModal: { open: false, quote: null, retry: null } });
      return;
    }
    set({ billingModal: { open: false, quote: null, retry: null } });

    if (retry.kind === 'chat') {
      await get().sendMessage(retry.content, {
        ...(retry.options || {}),
        budgetOverridePoints: budgetPoints,
      });
      return;
    }

    if (retry.kind === 'job') {
      await get().startLangGraphJob(retry.prompt, { budgetOverridePoints: budgetPoints });
      return;
    }

    if (retry.kind === 'generate') {
      await get().generateDocumentWithResult(retry.prompt, retry.caseId, { budgetOverridePoints: budgetPoints });
      return;
    }

    if (retry.kind === 'agent_legacy') {
      await get().startAgentGeneration(retry.prompt, retry.canvasContext, { budgetOverridePoints: budgetPoints });
    }
  },

  sendMessage: async (
    content: string,
    options: {
      outline?: string[];
      skipOutlineFetch?: boolean;
      skipUserMessage?: boolean;
      canvasWrite?: 'replace' | 'append';
      outlinePipeline?: boolean;
      budgetOverridePoints?: number;
      existingTurnId?: string;
    } = {}
  ) => {
    const {
      currentChat,
      chatMode,
      chatPersonality,
      selectedModels,
      selectedModel,
      activeContext,
      minPages,
      maxPages,
      documentType,
      thesis,
      ragTopK,
      ragSources,
      attachmentMode,
      contextMode,
      contextFiles,
      cacheTTL,
      graphHops,
      denseResearch,
      useTemplates,
      templateFilters,
      templateId,
      templateDocumentId,
      templateVariables,
      pendingCanvasContext,
      chatOutlineReviewEnabled,
    } = get();
    if (!currentChat) throw new Error('No chat selected');
    if (content.trim().length < 1) {
      toast.error('Digite uma mensagem.');
      return;
    }

    if (chatMode === 'multi-model' && !options.canvasWrite) {
      try {
        await get().startMultiModelStream(content, {
          budgetOverridePoints: options.budgetOverridePoints,
          existingTurnId: options.existingTurnId,
          skipUserMessage: options.skipUserMessage,
        });
      } catch (error) {
        const msg = error instanceof Error ? error.message : String(error || '');
        toast.error('Erro ao enviar mensagem', {
          description: msg ? msg.slice(0, 220) : undefined,
        });
        console.error('[ChatStore] startMultiModelStream error:', error);
        throw error;
      }
      return;
    }

    const shouldSkipUserMessage = Boolean(options.skipUserMessage);
    let userMessageId: string | null = null;
    if (!shouldSkipUserMessage) {
      userMessageId = nanoid();
      const userMessage: Message = {
        id: userMessageId,
        content,
        role: 'user',
        timestamp: new Date().toISOString(),
        metadata: pendingCanvasContext ? { canvas_context: pendingCanvasContext } : undefined,
      };

      set((state) => ({
        currentChat: state.currentChat
          ? {
            ...state.currentChat,
            messages: [...(state.currentChat.messages || []), userMessage],
          }
          : null,
        pendingCanvasContext: null,
      }));
    }

    let assistantMessageId: string | null = null;
    const canvasWriteMode = options.canvasWrite;
    let canvasFinalApplied = false;
    const canvasBase =
      canvasWriteMode === 'append'
        ? String(useCanvasStore.getState().content || '').trim()
        : '';
    let lastCanvasUpdateAt = 0;
    let assistantContentSnapshot = '';
    try {
      const fastModel =
        selectedModels && selectedModels.length > 0 ? selectedModels[0] : selectedModel;
      const hasPageRange = minPages > 0 || maxPages > 0;
      const shouldFetchOutline = hasPageRange || Boolean(options.outlinePipeline);
      let outline: string[] = Array.isArray(options.outline) ? options.outline : [];

      if (!options.skipOutlineFetch && !outline.length && shouldFetchOutline) {
        try {
          const outlineResponse = await apiClient.generateOutline(currentChat.id, {
            prompt: content,
            document_type: documentType,
            doc_kind: get().docKind || undefined,
            doc_subtype: get().docSubtype || undefined,
            thesis,
            model: fastModel,
            min_pages: minPages,
            max_pages: maxPages,
          });
          outline = outlineResponse?.outline || [];
        } catch (error) {
          console.warn('Outline generation failed, proceeding without outline.', error);
        }
      }

      if (!options.skipOutlineFetch && outline.length > 0 && shouldFetchOutline && chatOutlineReviewEnabled) {
        set({
          reviewData: {
            checkpoint: 'outline',
            outline,
            mode: 'chat',
          },
          pendingChatOutline: {
            content,
            outline,
            model: fastModel,
            canvasWrite: options.canvasWrite,
            outlinePipeline: options.outlinePipeline,
          },
        });
        toast.info('Revise o outline antes de enviar a resposta.');
        return;
      }

      const modelOverride = get().modelOverrides?.[fastModel] || {};
      const effectiveVerbosity = modelOverride.verbosity || get().verbosity;
      const effectiveReasoningLevel = modelOverride.reasoningLevel || get().reasoningLevel;
      const rawThinkingBudget =
        Object.prototype.hasOwnProperty.call(modelOverride, 'thinkingBudget')
          ? modelOverride.thinkingBudget
          : get().thinkingBudget;
      const effectiveThinkingBudget = parseThinkingBudget(rawThinkingBudget);
      const thinkingEnabled = resolveThinkingEnabled(
        fastModel,
        effectiveReasoningLevel,
        effectiveThinkingBudget
      );

      assistantMessageId = nanoid();

      // NEW: Optimistic thinking UI
      // If we are using a robust model (reasoningLevel is not low) or specific models, show thinking immediately
      const startThinking = shouldStartThinking(
        fastModel,
        effectiveReasoningLevel,
        thinkingEnabled
      );

      const assistantMessage: Message = {
        id: assistantMessageId,
        content: '',
        role: 'assistant',
        timestamp: new Date().toISOString(),
        thinking: startThinking ? '' : undefined, // Empty string ensures block is rendered but waiting
        isThinking: startThinking, // Trigger loading dots
        metadata: {
          stream_t0: Date.now(),
          thinking_enabled: thinkingEnabled,
        },
      };

      set((state) => ({
        currentChat: state.currentChat
          ? {
            ...state.currentChat,
            messages: [...(state.currentChat.messages || []), assistantMessage],
          }
          : null,
        isSending: true,
      }));

      const normalizeTemplateFilters = (filters: Record<string, any> | null | undefined) => {
        if (!filters) return {};
        const next: Record<string, any> = {};
        if (filters.tipoPeca) next.tipo_peca = filters.tipoPeca;
        if (filters.area) next.area = filters.area;
        if (filters.rito) next.rito = filters.rito;
        if (filters.apenasClauseBank !== undefined) {
          next.apenas_clause_bank = !!filters.apenasClauseBank;
        }
        return next;
      };

      const temperature = resolveTemperature(get().creativityMode, get().temperatureOverride);
      const shouldSendContextFiles = contextMode === 'upload_cache' || contextMode === 'auto';
      const attachmentDocs = (activeContext || [])
        .filter((item: any) => item?.type === 'file' && typeof item.id === 'string')
        .map((item: any) => ({
          id: item.id,
          type: 'doc',
          name: item.name,
        }));
      const perplexityPayload = buildPerplexityPayload(get(), [fastModel]);
      const deepResearchPayload = buildDeepResearchPayload(get());
      const mcpServerLabels =
        get().mcpToolCalling && !get().mcpUseAllServers && (get().mcpServerLabels || []).length > 0
          ? get().mcpServerLabels
          : undefined;
      const playbookPrompt = get().selectedPlaybookPrompt;
      // Resolve 'auto' attachment mode based on model context window and file count
      const resolvedAttachmentMode =
        attachmentMode === 'auto'
          ? resolveAutoAttachmentMode([fastModel], attachmentDocs.length)
          : attachmentMode;
      const payload: Record<string, any> = {
        content,
        attachments: attachmentDocs,
        chat_personality: chatPersonality,
        model: fastModel,
        temperature,
        mcp_tool_calling: get().mcpToolCalling,
        mcp_server_labels: mcpServerLabels,
        reasoning_level: effectiveReasoningLevel,
        verbosity: effectiveVerbosity,
        ...(effectiveThinkingBudget !== null
          ? { thinking_budget: effectiveThinkingBudget }
          : {}),
        web_search: get().webSearch,
        multi_query: get().multiQuery,
        breadth_first: get().breadthFirst,
        search_mode: get().searchMode,
        ...perplexityPayload,
        ...deepResearchPayload,
        research_policy: get().researchPolicy,
        rag_top_k: ragTopK,
        rag_sources: ragSources,
        attachment_mode: resolvedAttachmentMode,
        context_mode: contextMode,
        context_files: shouldSendContextFiles ? contextFiles : undefined,
        cache_ttl: shouldSendContextFiles ? cacheTTL : undefined,
        adaptive_routing: true,
        rag_mode: 'manual',
        crag_gate: true,
        hyde_enabled: true,
        graph_rag_enabled: true,
        argument_graph_enabled: true,
        graph_hops: graphHops,
        rag_scope: get().ragScope,
        rag_selected_groups: (get().ragSelectedGroups || []).length > 0 ? get().ragSelectedGroups : undefined,
        rag_allow_private: get().ragAllowPrivate,
        rag_allow_groups: get().ragAllowGroups,
        rag_jurisdictions:
          (get().ragGlobalJurisdictions || []).length > 0 ? get().ragGlobalJurisdictions : undefined,
        rag_source_ids:
          (get().ragGlobalSourceIds || []).length > 0 ? get().ragGlobalSourceIds : undefined,
        dense_research: denseResearch,
        use_templates: useTemplates,
        template_filters: normalizeTemplateFilters(templateFilters),
        template_id: templateId || undefined,
        template_document_id: templateDocumentId || undefined,
        variables: templateVariables || undefined,
        ...(options.outlinePipeline
          ? {
            outline_pipeline: true,
            document_type: documentType,
            doc_kind: get().docKind || undefined,
            doc_subtype: get().docSubtype || undefined,
            thesis: thesis || undefined,
            min_pages: minPages || undefined,
            max_pages: maxPages || undefined,
          }
          : {}),
        ...(options.budgetOverridePoints ? { budget_override_points: options.budgetOverridePoints } : {}),
        ...(playbookPrompt ? { playbook_prompt: playbookPrompt } : {}),
      };
      if (outline.length > 0) {
        payload.outline = outline;
      }

      let streamRequestId: string | null = null;
      let lastEventId: string | null = null;
      let lastAppliedEventId: number | null = null;
      let retryDelayMs = 2000;
      let streamCompleted = false;

      const maxReconnects = 1;
      let attempt = 0;
      while (true) {
        const resumeAttempt = attempt > 0 && !!streamRequestId && !!lastEventId;
        const requestPayload = resumeAttempt && streamRequestId
          ? { ...payload, stream_request_id: streamRequestId }
          : payload;
        const requestHeaders: HeadersInit = resumeAttempt && lastEventId
          ? { 'Last-Event-ID': lastEventId }
          : {};

        const response = await apiClient.fetchWithAuth(`/chats/${currentChat.id}/messages/stream`, {
          method: 'POST',
          body: JSON.stringify(requestPayload),
          headers: requestHeaders,
        });

        if (!response.ok || !response.body) {
          let detail = '';
          let parsed: any = null;
          try {
            const raw = await response.text();
            if (raw) {
              try {
                parsed = JSON.parse(raw);
                detail = parsed?.detail ? String(parsed.detail) : raw;
              } catch {
                detail = raw;
              }
            }
          } catch {
            // ignore
          }

          if (
            (response.status === 402 || response.status === 409 || response.status === 422) &&
            parsed?.detail &&
            typeof parsed.detail === 'object'
          ) {
            const quote = parsed.detail as BillingQuote;
            set((state) => ({
              currentChat: state.currentChat
                ? {
                  ...state.currentChat,
                  messages: (state.currentChat.messages || []).filter(
                    (m) => m.id !== assistantMessageId && m.id !== userMessageId
                  ),
                }
                : null,
              isSending: false,
              billingModal: {
                open: true,
                quote,
                retry: { kind: 'chat', content, options: { ...options, outline } },
              },
            }));
            return;
          }

          throw new Error(
            `Erro ao iniciar streaming (HTTP ${response.status}): ${detail || response.statusText}`
          );
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

      const applyCanvasSnapshot = (text: string | undefined, isFinal = false) => {
        if (!canvasWriteMode) return;
        const rawText = String(text || '');
        const nextText = isFinal ? rawText.trim() : rawText;
        if (!String(nextText || '').trim()) return;
        if (isFinal && canvasFinalApplied) return;
        const now = Date.now();
        // Adaptive throttle: longer docs get less frequent updates to reduce flickering
        const docLength = String(nextText || '').length;
        const minIntervalMs = canvasWriteMode
          ? (docLength > 20000 ? 200 : docLength > 8000 ? 100 : 40)
          : 120;
        if (!isFinal && now - lastCanvasUpdateAt < minIntervalMs) return;
        lastCanvasUpdateAt = now;
        const canvasStore = useCanvasStore.getState();
        const updated =
          canvasWriteMode === 'append' && canvasBase ? `${canvasBase}\n\n${nextText}` : nextText;
        canvasStore.setContent(updated);
        canvasStore.showCanvas();
        canvasStore.setActiveTab('editor');
        if (isFinal) canvasFinalApplied = true;
      };

      const applyCanvasWrite = (text: string | undefined) => {
        applyCanvasSnapshot(text, true);
      };

      const updateAssistant = (updater: (message: Message) => Message) => {
        set((state) => {
          if (!state.currentChat) return {};
          const updatedMessages = (state.currentChat.messages || []).map((message) =>
            message.id === assistantMessageId ? updater(message) : message
          );
          return {
            currentChat: {
              ...state.currentChat,
              messages: updatedMessages,
            },
          };
        });
      };

      const upsertActivityStep = (
        message: Message,
        step: {
          id: string;
          title: string;
          status?: 'running' | 'done' | 'error';
          detail?: string;
          tags?: string[];
          kind?: 'assess' | 'attachment_review' | 'file_terms' | 'web_search' | 'delegate_subtask' | 'generic';
          attachments?: Array<{ name: string; kind?: string; ext?: string }>;
          terms?: string[];
          sources?: Array<{ title?: string; url: string }>;
        },
        op?: 'add' | 'update' | 'append' | 'done' | 'error' | 'tags'
      ) => {
        const meta: any = { ...(message.metadata || {}) };
        const activity: any = { ...(meta.activity || {}) };
        const steps: any[] = Array.isArray(activity.steps) ? [...activity.steps] : [];
        const idx = steps.findIndex((s) => s?.id === step.id);
        const prev = idx >= 0 ? steps[idx] : null;

        // Handle different operations
        let nextDetail = typeof step.detail === 'string' ? step.detail : prev?.detail ?? '';
        let nextTags = step.tags ?? prev?.tags ?? [];
        const nextKind = step.kind ?? prev?.kind;

        const mergeStrings = (a: any[] | undefined, b: any[] | undefined) => {
          const out: string[] = [];
          const seen = new Set<string>();
          for (const item of [...(a || []), ...(b || [])]) {
            const v = String(item || '').trim();
            if (!v) continue;
            const k = v.toLowerCase();
            if (seen.has(k)) continue;
            seen.add(k);
            out.push(v);
          }
          return out;
        };

        const mergeSources = (a: any[] | undefined, b: any[] | undefined) => {
          const out: Array<{ title?: string; url: string }> = [];
          const seen = new Set<string>();
          for (const item of [...(a || []), ...(b || [])]) {
            const url = String(item?.url || '').trim();
            if (!url) continue;
            const key = url.toLowerCase();
            if (seen.has(key)) continue;
            seen.add(key);
            out.push({ url, title: item?.title ? String(item.title) : undefined });
          }
          return out;
        };

        const mergeAttachments = (a: any[] | undefined, b: any[] | undefined) => {
          const out: Array<{ name: string; kind?: string; ext?: string }> = [];
          const seen = new Set<string>();
          for (const item of [...(a || []), ...(b || [])]) {
            const name = String(item?.name || '').trim();
            if (!name) continue;
            const ext = item?.ext ? String(item.ext).trim() : undefined;
            const key = `${name.toLowerCase()}|${String(ext || '').toLowerCase()}`;
            if (seen.has(key)) continue;
            seen.add(key);
            out.push({ name, kind: item?.kind ? String(item.kind) : undefined, ext });
          }
          return out;
        };

        if (op === 'append' && prev?.detail && step.detail) {
          // Append to existing detail text
          nextDetail = `${prev.detail}${step.detail}`;
        } else if (op === 'tags' && step.tags) {
          // Merge tags without duplicates
          const existingTags = new Set(prev?.tags ?? []);
          step.tags.forEach(t => existingTags.add(t));
          nextTags = Array.from(existingTags);
        }

        const next = {
          id: step.id,
          title: step.title ?? prev?.title ?? step.id,
          status: op === 'done' ? 'done' : op === 'error' ? 'error' : (step.status ?? prev?.status ?? 'running'),
          detail: nextDetail,
          tags: nextTags,
          kind: nextKind,
          attachments: mergeAttachments(prev?.attachments, step.attachments),
          terms: mergeStrings(prev?.terms, step.terms),
          sources: mergeSources(prev?.sources, step.sources),
          t: Date.now(),
        };
        if (idx >= 0) steps[idx] = next;
        else steps.push(next);
        activity.steps = steps;
        meta.activity = activity;
        return { ...(message.metadata || {}), ...meta };
      };

      let hasActivityEvents = false;

      // Handler for new unified activity events from backend
      const handleActivityEvent = (data: any) => {
        const step = data.step;
        const op = data.op as 'add' | 'update' | 'append' | 'done' | 'error' | 'tags' | undefined;
        if (!step || !step.id) return;
        if (!thinkingEnabled && String(step.id).toLowerCase() === 'thinking') return;
        hasActivityEvents = true;

        updateAssistant((message) => ({
          ...message,
          metadata: upsertActivityStep(message, {
            id: step.id,
            title: step.title || step.id,
            status: step.status || 'running',
            detail: step.detail || '',
            tags: step.tags || [],
            kind: step.kind,
            attachments: step.attachments,
            terms: step.terms,
            sources: step.sources,
          }, op),
        }));
      };

      // Handler for granular step.* events from streaming (step.start, step.add_query, step.add_source, step.done)
      const handleStepEvent = (data: any): boolean => {
        if (data.type === 'step.start') {
          hasActivityEvents = true;
          const rawName = String(data.step_name || '').trim();
          const rawId = String(data.step_id || '').trim();
          const nameLower = rawName.toLowerCase();
          const idLower = rawId.toLowerCase();
          const isWeb =
            nameLower.includes('web') ||
            nameLower.includes('internet') ||
            idLower.includes('web_search') ||
            idLower.includes('openai_web_search') ||
            idLower.includes('pplx');
          updateAssistant((message) => ({
            ...message,
            metadata: upsertActivityStep(message, {
              id: isWeb ? 'web_search' : (data.step_id || data.step_name || 'search'),
              title: rawName || 'Pesquisando',
              status: 'running',
              kind: isWeb ? 'web_search' : undefined,
            }, 'add'),
          }));
          return true;
        }
        if (data.type === 'step.add_query') {
          hasActivityEvents = true;
          const rawId = String(data.step_id || '').trim();
          const idLower = rawId.toLowerCase();
          const isWeb = idLower.includes('web_search') || idLower.includes('openai_web_search') || idLower.includes('pplx');
          updateAssistant((message) => ({
            ...message,
            metadata: upsertActivityStep(message, {
              id: isWeb ? 'web_search' : (data.step_id || 'search'),
              title: 'Pesquisa',
              tags: data.query ? [String(data.query).slice(0, 100)] : [],
              kind: isWeb ? 'web_search' : undefined,
            }, 'tags'),
          }));
          return true;
        }
        if (data.type === 'step.add_source') {
          hasActivityEvents = true;
          updateAssistant((message) => {
            const citations = Array.isArray(message.metadata?.citations) ? [...message.metadata.citations] : [];
            const src = data.source;
            const srcUrl =
              (typeof src?.url === 'string' && src.url.trim()) ||
              (typeof src?.source_url === 'string' && src.source_url.trim()) ||
              '';
            const srcDocId =
              String(src?.provenance?.doc_id || src?.doc_id || src?.document_id || '').trim();
            const srcChunk =
              String(src?.provenance?.chunk_uid || src?.chunk_uid || '').trim();
            const srcChunkIndex = src?.provenance?.chunk_index ?? src?.chunk_index;
            const srcPage =
              src?.viewer?.source_page ?? src?.provenance?.page_number ?? src?.page_number ?? src?.source_page;
            const sourceKey = srcDocId
              ? `${srcDocId}|${String(srcChunkIndex ?? '')}|${String(srcPage ?? '')}|${srcChunk}`
              : srcUrl.toLowerCase();
            if (
              sourceKey &&
              !citations.some((c: any) => {
                const cDocId = String(c?.provenance?.doc_id || c?.doc_id || c?.document_id || '').trim();
                const cChunk = String(c?.provenance?.chunk_uid || c?.chunk_uid || '').trim();
                const cChunkIndex = c?.provenance?.chunk_index ?? c?.chunk_index;
                const cPage =
                  c?.viewer?.source_page ?? c?.provenance?.page_number ?? c?.page_number ?? c?.source_page;
                const cUrl =
                  (typeof c?.url === 'string' && c.url.trim()) ||
                  (typeof c?.source_url === 'string' && c.source_url.trim()) ||
                  '';
                const candidateKey = cDocId
                  ? `${cDocId}|${String(cChunkIndex ?? '')}|${String(cPage ?? '')}|${cChunk}`
                  : cUrl.toLowerCase();
                return candidateKey === sourceKey;
              })
            ) {
              citations.push({
                number: String(citations.length + 1),
                title: src?.title || srcUrl || `Fonte ${citations.length + 1}`,
                url: srcUrl || undefined,
                quote:
                  (typeof src?.quote === 'string' && src.quote) ||
                  (typeof src?.highlight_text === 'string' && src.highlight_text) ||
                  undefined,
                ...(src?.provenance && typeof src.provenance === 'object' ? { provenance: src.provenance } : {}),
                ...(src?.viewer && typeof src.viewer === 'object' ? { viewer: src.viewer } : {}),
                ...(src?.doc_id ? { doc_id: src.doc_id } : {}),
                ...(src?.document_id ? { document_id: src.document_id } : {}),
                ...(src?.chunk_uid ? { chunk_uid: src.chunk_uid } : {}),
                ...(src?.chunk_index != null ? { chunk_index: src.chunk_index } : {}),
                ...(src?.source_page != null ? { source_page: src.source_page } : {}),
                ...(src?.source_url ? { source_url: src.source_url } : {}),
              });
            }
            return {
              ...message,
              metadata: { ...(message.metadata || {}), citations },
            };
          });
          const src = data.source;
          const srcUrl =
            (typeof src?.url === 'string' && src.url.trim()) ||
            (typeof src?.source_url === 'string' && src.source_url.trim()) ||
            '';
          if (srcUrl) {
            updateAssistant((message) => ({
              ...message,
              metadata: upsertActivityStep(message, {
                id: 'web_search',
                title: 'Pesquisando na web',
                kind: 'web_search',
                sources: [{ url: srcUrl, title: src?.title ? String(src.title) : undefined }],
              }, 'update'),
            }));
          }
          return true;
        }
        if (data.type === 'step.done') {
          hasActivityEvents = true;
          const rawId = String(data.step_id || '').trim();
          const idLower = rawId.toLowerCase();
          const isWeb = idLower.includes('web_search') || idLower.includes('openai_web_search') || idLower.includes('pplx') || rawId === 'web_search';
          updateAssistant((message) => ({
            ...message,
            metadata: upsertActivityStep(message, {
              id: isWeb ? 'web_search' : (data.step_id || 'search'),
              title: 'Pesquisa',
              kind: isWeb ? 'web_search' : undefined,
            }, 'done'),
          }));
          return true;
        }
        return false;
      };

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        // SSE frames can arrive with LF or CRLF depending on proxy/runtime
        const parts = buffer.split(/\r?\n\r?\n/);
        buffer = parts.pop() || '';

        for (const part of parts) {
          const lines = part.split(/\r?\n/);
          let eventId: string | null = null;
          let retryMs: number | null = null;
          const dataLines: string[] = [];
          for (const line of lines) {
            const trimmedLine = line.trimStart();
            if (!trimmedLine) continue;
            if (trimmedLine.startsWith(':')) continue;
            if (trimmedLine.startsWith('id:')) {
              eventId = trimmedLine.slice(3).trim();
              continue;
            }
            if (trimmedLine.startsWith('retry:')) {
              const value = Number.parseInt(trimmedLine.slice(6).trim(), 10);
              if (!Number.isNaN(value)) retryMs = value;
              continue;
            }
            if (trimmedLine.startsWith('data:')) {
              const payload = trimmedLine.slice(5).trim();
              if (payload) dataLines.push(payload);
            }
          }
          if (retryMs !== null) retryDelayMs = retryMs;
          if (!dataLines.length) continue;
          const payload = dataLines.join('\n');

          let data: any;
          try {
            data = JSON.parse(payload);
          } catch (err) {
            console.error('Erro parse SSE', err);
            continue;
          }

          if (eventId) {
            lastEventId = eventId;
            const numericId = Number.parseInt(eventId, 10);
            if (!Number.isNaN(numericId)) {
              if (lastAppliedEventId !== null && numericId <= lastAppliedEventId) {
                continue;
              }
              lastAppliedEventId = numericId;
            }
          }
          if (data?.request_id && !streamRequestId) {
            streamRequestId = String(data.request_id);
          }

          // Handle unified activity events and granular step.* events
          if (data.type === 'activity') {
            handleActivityEvent(data);
          } else if (data.type?.startsWith('step.') && handleStepEvent(data)) {
            // Handled by handleStepEvent
          } else if (data.type === 'tool_call' && data.step_id) {
            hasActivityEvents = true;
            const toolName = String(data.name || '').trim() || 'tool';
            const toolNameLower = toolName.toLowerCase();
            const delegatedModel =
              String(
                data?.arguments?.model ??
                data?.args?.model ??
                data?.input?.model ??
                '',
              ).trim();
            const isDelegateSubtask = toolNameLower === 'delegate_subtask' || toolNameLower.includes('delegate');
            const stepId = isDelegateSubtask ? 'delegate_subtask' : String(data.step_id || 'mcp_tools');
            const stepTitle = isDelegateSubtask ? 'Delegado para Haiku' : 'MCP tools';
            const tagLabel = isDelegateSubtask
              ? (delegatedModel || 'claude-4.5-haiku')
              : toolName;
            const previewRaw = data.result_preview != null ? String(data.result_preview) : '';
            const preview = previewRaw ? previewRaw.slice(0, 220) : '';
            const line = `\n${toolName}${preview ? `: ${preview}` : ''}`;

            updateAssistant((message) => ({
              ...message,
              metadata: upsertActivityStep(message, {
                id: stepId,
                title: stepTitle,
                tags: [tagLabel],
                kind: isDelegateSubtask ? 'delegate_subtask' : undefined,
              }, 'tags'),
            }));
            updateAssistant((message) => ({
              ...message,
              metadata: upsertActivityStep(message, {
                id: stepId,
                title: stepTitle,
                detail: line,
                kind: isDelegateSubtask ? 'delegate_subtask' : undefined,
              }, 'append'),
            }));
          } else if (data.type === 'search_started') {
            const query = data.query ? `: ${data.query}` : '';
            toast.info(`Buscando na web${query}...`);
            if (!hasActivityEvents) {
              updateAssistant((message) => ({
                ...message,
                metadata: upsertActivityStep(message, {
                  id: 'web_search',
                  title: 'Pesquisando na web',
                  status: 'running',
                  detail: data.query ? `Consulta: ${String(data.query)}` : '',
                  kind: 'web_search',
                }),
              }));
            }
          } else if (data.type === 'search_done') {
            const count = typeof data.count === 'number' ? data.count : 0;
            const cached = data.cached ? ' (cache)' : '';
            toast.info(`Pesquisa web concluída (${count} fontes${cached}).`);
            if (!hasActivityEvents) {
              updateAssistant((message) => ({
                ...message,
                metadata: upsertActivityStep(message, {
                  id: 'web_search',
                  title: 'Pesquisando na web',
                  status: 'done',
                  detail: `Fontes: ${count}${cached}`,
                  kind: 'web_search',
                }),
              }));
            }
          } else if (data.type === 'research_start') {
            toast.info('Pesquisa profunda iniciada...');
            if (!hasActivityEvents) {
              updateAssistant((message) => ({
                ...message,
                metadata: upsertActivityStep(message, {
                  id: 'deep',
                  title: 'Pesquisa profunda',
                  status: 'running',
                }),
              }));
            }
          } else if (data.type === 'research_done') {
            toast.info('Pesquisa profunda concluída.');
            if (!hasActivityEvents) {
              updateAssistant((message) => ({
                ...message,
                metadata: upsertActivityStep(message, {
                  id: 'deep',
                  title: 'Pesquisa profunda',
                  status: 'done',
                }),
              }));
            }
          } else if (data.type === 'research_error') {
            toast.error('Pesquisa profunda falhou', {
              description: String(data.message || data.error || '').slice(0, 220) || undefined,
            });
            if (!hasActivityEvents) {
              updateAssistant((message) => ({
                ...message,
                metadata: upsertActivityStep(message, {
                  id: 'deep',
                  title: 'Pesquisa profunda',
                  status: 'error',
                  detail: String(data.message || data.error || '').slice(0, 220),
                }),
              }));
            }
          } else if (data.type === 'cache_hit') {
            toast.info('Usando cache...');
            updateAssistant((message) => ({
              ...message,
              metadata: upsertActivityStep(message, {
                id: 'cache',
                title: 'Cache',
                status: 'done',
                detail: 'Usando cache',
              }),
            }));
          }

            if (data.type === 'outline' && Array.isArray(data.outline)) {
              try {
                useCanvasStore.getState().syncOutlineFromTitles(data.outline);
              } catch {
                // noop
              }
            } else if (data.type === 'granular' || data.type === 'stream_chunk') {
              const preview = data.document_preview || data.markdown || data.content;
              if (typeof preview === 'string' && preview.trim()) {
                applyCanvasSnapshot(preview);
              }
            }

            if (data.type === 'meta' && data.phase && typeof data.t === 'number') {
              updateAssistant((message) => ({
                ...message,
                metadata: {
                  ...(message.metadata || {}),
                  ...(data.phase === 'start' ? { stream_t0: data.t } : {}),
                  ...(data.phase === 'answer_start' ? { stream_t_answer_start: data.t } : {}),
                },
              }));
            } else if (data.type === 'error') {
              streamCompleted = true;
              const now = Date.now();
              updateAssistant((message) => ({
                ...message,
                content: data.error || 'Erro ao enviar mensagem',
                isThinking: false,
                metadata: (() => {
                  const next: any = { ...(message.metadata || {}) };
                  if (typeof next.stream_t0 !== 'number') next.stream_t0 = now;
                  if (typeof next.stream_t_done !== 'number') next.stream_t_done = now;
                  return next;
                })(),
              }));
              set({ isSending: false });
              toast.error(data.error || 'Erro ao enviar mensagem');
              updateAssistant((message) => ({
                ...message,
                metadata: upsertActivityStep(message, {
                  id: 'error',
                  title: 'Erro',
                  status: 'error',
                  detail: String(data.error || '').slice(0, 220),
                }),
              }));
            } else if (data.type === 'thinking' && data.delta && thinkingEnabled) {
              const now = Date.now();
              updateAssistant((message) => ({
                ...message,
                thinking: (message.thinking || '') + data.delta,
                isThinking: true,
                metadata: (() => {
                  const next = { ...(message.metadata || {}) } as any;
                  if (typeof next.stream_t0 !== 'number') next.stream_t0 = now;
                  const chunks = Array.isArray(next.thinkingChunks) ? [...next.thinkingChunks] : [];
                  const chunkType =
                    data?.thinking_type === 'summary' || data?.summary ? 'summary' : 'llm';
                  const last = chunks[chunks.length - 1];
                  if (last && last.type === chunkType) {
                    last.text = `${last.text || ''}${data.delta}`;
                  } else {
                    chunks.push({ type: chunkType, text: String(data.delta) });
                  }
                  next.thinkingChunks = chunks;
                  return next;
                })(),
              }));
            } else if (data.type === 'deepresearch_step' && data.text && thinkingEnabled) {
              const now = Date.now();
              updateAssistant((message) => ({
                ...message,
                thinking: (message.thinking || '') + data.text,
                isThinking: true,
                metadata: (() => {
                  const next = { ...(message.metadata || {}) } as any;
                  if (typeof next.stream_t0 !== 'number') next.stream_t0 = now;
                  const chunks = Array.isArray(next.thinkingChunks) ? [...next.thinkingChunks] : [];
                  chunks.push({ type: 'research', text: String(data.text) });
                  next.thinkingChunks = chunks;
                  return next;
                })(),
              }));
            } else if (data.type === 'token' && data.delta) {
              const delta = String(data.delta || '');
              assistantContentSnapshot += delta;
              const now = Date.now();
              // v5.9: When canvas write mode is active, don't accumulate tokens in chat message
              // Instead, show a brief status indicator and stream content only to canvas
              updateAssistant((message) => ({
                ...message,
                content: canvasWriteMode ? '📝 Escrevendo no canvas...' : (message.content || '') + delta,
                isThinking: false,
                metadata: (() => {
                  const next = { ...(message.metadata || {}) } as any;
                  if (typeof next.stream_t0 !== 'number') next.stream_t0 = now;
                  if (typeof next.stream_t_answer_start !== 'number')
                    next.stream_t_answer_start = now;
                  return next;
                })(),
              }));
              applyCanvasSnapshot(assistantContentSnapshot);
            } else if (data.type === 'done') {
              streamCompleted = true;
              const now = Date.now();
              let finalText = String(data.full_text || assistantContentSnapshot || '');
              updateAssistant((message) => {
                if (!finalText) finalText = String(message.content || '');
                return {
                  ...message,
                  id: data.message_id || message.id,
                  content: canvasWriteMode ? '✅ Documento gerado no canvas.' : finalText,
                  thinking: thinkingEnabled
                    ? (() => {
                      const streamed = typeof message.thinking === 'string' ? message.thinking : '';
                      if (streamed.trim()) return streamed;
                      return typeof data.thinking === 'string' ? data.thinking : message.thinking;
                    })()
                    : undefined, // Preserve streamed thinking; fallback to summary if none
                  isThinking: false, // Stop thinking animation
                  metadata: (() => {
                    const nextMetadata: any = {
                      ...(message.metadata || {}),
                      ...(canvasWriteMode ? { canvas_write: undefined } : {}),
                      ...(data.model ? { model: data.model } : {}),
                      ...(data.turn_id ? { turn_id: data.turn_id } : {}),
                      ...(data.token_usage ? { token_usage: data.token_usage } : {}),
                      ...(data.citations ? { citations: data.citations } : {}),
                      ...(data.billing ? { billing: data.billing } : {}),
                      ...(typeof data.execution_mode === 'string'
                        ? { execution_mode: data.execution_mode }
                        : {}),
                      ...(typeof data.execution_path === 'string'
                        ? { execution_path: data.execution_path }
                        : {}),
                      ...(typeof data.thinking_enabled === 'boolean'
                        ? { thinking_enabled: data.thinking_enabled }
                        : {}),
                    };
                    if (typeof nextMetadata.stream_t0 !== 'number') nextMetadata.stream_t0 = now;
                    if (typeof nextMetadata.stream_t_answer_start !== 'number')
                      nextMetadata.stream_t_answer_start = now;
                    nextMetadata.stream_t_done = now;
                    return Object.keys(nextMetadata).length ? nextMetadata : message.metadata;
                  })(),
                };
              });
              applyCanvasWrite(finalText);
              // Auto-open canvas when backend detects document-like response
              if (!canvasWriteMode && data.canvas_suggestion && finalText.length > 600) {
                try {
                  const canvasStore = useCanvasStore.getState();
                  canvasStore.setContent(finalText);
                  canvasStore.showCanvas();
                  canvasStore.setActiveTab('editor');
                } catch (_) { /* canvas store may not be available */ }
              }
              set({ isSending: false });
            } else if (data.type === 'error') {
              streamCompleted = true;
              const now = Date.now();
              updateAssistant((message) => ({
                ...message,
                content: data.error || 'Erro ao enviar mensagem',
                isThinking: false,
                metadata: (() => {
                  const next: any = { ...(message.metadata || {}) };
                  if (typeof next.stream_t0 !== 'number') next.stream_t0 = now;
                  if (typeof next.stream_t_done !== 'number') next.stream_t_done = now;
                  return next;
                })(),
              }));
              set({ isSending: false });
              toast.error(data.error || 'Erro ao enviar mensagem');
              updateAssistant((message) => ({
                ...message,
                metadata: upsertActivityStep(message, {
                  id: 'error',
                  title: 'Erro',
                  status: 'error',
                  detail: String(data.error || '').slice(0, 220),
                }),
              }));
            } else if (data.type === 'deepresearch_step' && (data.text || data.delta) && thinkingEnabled) {
              const now = Date.now();
              const delta = String(data.text || data.delta || '');
              updateAssistant((message) => ({
                ...message,
                thinking: (message.thinking || '') + (delta.endsWith('\n') ? delta : `${delta}\n`),
                isThinking: true,
                metadata: (() => {
                  const next = { ...(message.metadata || {}) } as any;
                  if (typeof next.stream_t0 !== 'number') next.stream_t0 = now;
                  return next;
                })(),
              }));
            }
          }
        }

      if (buffer.trim()) {
        const lines = buffer.split(/\r?\n/);
        let eventId: string | null = null;
        let retryMs: number | null = null;
        const dataLines: string[] = [];
        for (const line of lines) {
          const trimmedLine = line.trimStart();
          if (!trimmedLine) continue;
          if (trimmedLine.startsWith(':')) continue;
          if (trimmedLine.startsWith('id:')) {
            eventId = trimmedLine.slice(3).trim();
            continue;
          }
          if (trimmedLine.startsWith('retry:')) {
            const value = Number.parseInt(trimmedLine.slice(6).trim(), 10);
            if (!Number.isNaN(value)) retryMs = value;
            continue;
          }
          if (trimmedLine.startsWith('data:')) {
            const payload = trimmedLine.slice(5).trim();
            if (payload) dataLines.push(payload);
          }
        }
        if (retryMs !== null) retryDelayMs = retryMs;
        if (!dataLines.length) {
          // nothing to flush
        } else {
          const payload = dataLines.join('\n');
          try {
            const data = JSON.parse(payload);
            let skipEvent = false;
            if (eventId) {
              lastEventId = eventId;
              const numericId = Number.parseInt(eventId, 10);
              if (!Number.isNaN(numericId)) {
                if (lastAppliedEventId !== null && numericId <= lastAppliedEventId) {
                  skipEvent = true;
                } else {
                  lastAppliedEventId = numericId;
                }
              }
            }
            if (!skipEvent) {
              if (data?.request_id && !streamRequestId) {
                streamRequestId = String(data.request_id);
              }
              // Handle unified activity events and granular step.* events (buffer flush)
              if (data.type === 'activity') {
                handleActivityEvent(data);
              } else if (data.type?.startsWith('step.') && handleStepEvent(data)) {
                // Handled by handleStepEvent
              } else if (data.type === 'search_started') {
                const query = data.query ? `: ${data.query}` : '';
                toast.info(`Buscando na web${query}...`);
                if (!hasActivityEvents) {
                  updateAssistant((message) => ({
                    ...message,
                    metadata: upsertActivityStep(message, {
                      id: 'web_search',
                      title: 'Pesquisando na web',
                      status: 'running',
                      detail: data.query ? `Consulta: ${String(data.query)}` : '',
                      kind: 'web_search',
                    }),
                  }));
                }
              } else if (data.type === 'search_done') {
                const count = typeof data.count === 'number' ? data.count : 0;
                const cached = data.cached ? ' (cache)' : '';
                toast.info(`Pesquisa web concluída (${count} fontes${cached}).`);
                if (!hasActivityEvents) {
                  updateAssistant((message) => ({
                    ...message,
                    metadata: upsertActivityStep(message, {
                      id: 'web_search',
                      title: 'Pesquisando na web',
                      status: 'done',
                      detail: `Fontes: ${count}${cached}`,
                      kind: 'web_search',
                    }),
                  }));
                }
              } else if (data.type === 'research_start') {
                toast.info('Pesquisa profunda iniciada...');
                if (!hasActivityEvents) {
                  updateAssistant((message) => ({
                    ...message,
                    metadata: upsertActivityStep(message, {
                      id: 'deep',
                      title: 'Pesquisa profunda',
                      status: 'running',
                    }),
                  }));
                }
              } else if (data.type === 'research_done') {
                toast.info('Pesquisa profunda concluída.');
                if (!hasActivityEvents) {
                  updateAssistant((message) => ({
                    ...message,
                    metadata: upsertActivityStep(message, {
                      id: 'deep',
                      title: 'Pesquisa profunda',
                      status: 'done',
                    }),
                  }));
                }
              } else if (data.type === 'research_error') {
                toast.error('Pesquisa profunda falhou', {
                  description: String(data.message || data.error || '').slice(0, 220) || undefined,
                });
                if (!hasActivityEvents) {
                  updateAssistant((message) => ({
                    ...message,
                    metadata: upsertActivityStep(message, {
                      id: 'deep',
                      title: 'Pesquisa profunda',
                      status: 'error',
                      detail: String(data.message || data.error || '').slice(0, 220),
                    }),
                  }));
                }
              } else if (data.type === 'cache_hit') {
                toast.info('Usando cache...');
                updateAssistant((message) => ({
                  ...message,
                  metadata: upsertActivityStep(message, {
                    id: 'cache',
                    title: 'Cache',
                    status: 'done',
                    detail: 'Usando cache',
                  }),
                }));
              }
            }
            if (data.type === 'outline' && Array.isArray(data.outline)) {
              try {
                useCanvasStore.getState().syncOutlineFromTitles(data.outline);
              } catch {
                // noop
              }
            } else if (data.type === 'granular' || data.type === 'stream_chunk') {
              const preview = data.document_preview || data.markdown || data.content;
              if (typeof preview === 'string' && preview.trim()) {
                applyCanvasSnapshot(preview);
              }
            }
            if (data.type === 'token' && data.delta) {
              const delta = String(data.delta || '');
              assistantContentSnapshot += delta;
              const now = Date.now();
              updateAssistant((message) => ({
                ...message,
                content: canvasWriteMode
                  ? (String(message.content || '').trim() ? String(message.content) : 'Escrevendo no canvas...')
                  : (message.content || '') + delta,
                metadata: (() => {
                  const next: any = { ...(message.metadata || {}) };
                  if (typeof next.stream_t0 !== 'number') next.stream_t0 = now;
                  if (typeof next.stream_t_answer_start !== 'number')
                    next.stream_t_answer_start = now;
                  return next;
                })(),
              }));
              applyCanvasSnapshot(assistantContentSnapshot);
              updateAssistant((message) => ({
                ...message,
                metadata: upsertActivityStep(message, {
                  id: 'answer',
                  title: 'Gerando resposta',
                  status: 'running',
                }),
              }));
            } else if (data.type === 'done') {
              streamCompleted = true;
              const now = Date.now();
              let finalText = String(data.full_text || assistantContentSnapshot || '');
              updateAssistant((message) => {
                if (!finalText) finalText = String(message.content || '');
                return {
                  ...message,
                  id: data.message_id || message.id,
                  content: canvasWriteMode ? 'Atualizado no canvas.' : finalText,
                  thinking: thinkingEnabled
                    ? (() => {
                      const streamed = typeof message.thinking === 'string' ? message.thinking : '';
                      if (streamed.trim()) return streamed;
                      return typeof data.thinking === 'string' ? data.thinking : message.thinking;
                    })()
                    : undefined,
                  metadata: (() => {
                    const nextMetadata: any = {
                      ...(message.metadata || {}),
                      ...(canvasWriteMode ? { canvas_write: undefined } : {}),
                      ...(data.model ? { model: data.model } : {}),
                      ...(data.turn_id ? { turn_id: data.turn_id } : {}),
                      ...(data.token_usage ? { token_usage: data.token_usage } : {}),
                      ...(data.citations ? { citations: data.citations } : {}),
                      ...(data.billing ? { billing: data.billing } : {}),
                      ...(typeof data.execution_mode === 'string'
                        ? { execution_mode: data.execution_mode }
                        : {}),
                      ...(typeof data.execution_path === 'string'
                        ? { execution_path: data.execution_path }
                        : {}),
                      ...(typeof data.thinking_enabled === 'boolean'
                        ? { thinking_enabled: data.thinking_enabled }
                        : {}),
                    };
                    if (typeof nextMetadata.stream_t0 !== 'number') nextMetadata.stream_t0 = now;
                    if (typeof nextMetadata.stream_t_answer_start !== 'number')
                      nextMetadata.stream_t_answer_start = now;
                    nextMetadata.stream_t_done = now;
                    return Object.keys(nextMetadata).length ? nextMetadata : message.metadata;
                  })(),
                };
              });
              applyCanvasWrite(finalText);
              // Auto-open canvas when backend detects document-like response
              if (!canvasWriteMode && data.canvas_suggestion && finalText.length > 600) {
                try {
                  const canvasStore = useCanvasStore.getState();
                  canvasStore.setContent(finalText);
                  canvasStore.showCanvas();
                  canvasStore.setActiveTab('editor');
                } catch (_) { /* canvas store may not be available */ }
              }
            } else if (data.type === 'thinking' && data.delta && thinkingEnabled) {
              const now = Date.now();
              updateAssistant((message) => ({
                ...message,
                thinking: (message.thinking || '') + data.delta,
                isThinking: true,
                metadata: (() => {
                  const next = { ...(message.metadata || {}) } as any;
                  if (typeof next.stream_t0 !== 'number') next.stream_t0 = now;
                  const chunks = Array.isArray(next.thinkingChunks) ? [...next.thinkingChunks] : [];
                  const chunkType =
                    data?.thinking_type === 'summary' || data?.summary ? 'summary' : 'llm';
                  const last = chunks[chunks.length - 1];
                  if (last && last.type === chunkType) {
                    last.text = `${last.text || ''}${data.delta}`;
                  } else {
                    chunks.push({ type: chunkType, text: String(data.delta) });
                  }
                  next.thinkingChunks = chunks;
                  return next;
                })(),
              }));
            } else if (data.type === 'deepresearch_step' && (data.text || data.delta) && thinkingEnabled) {
              const now = Date.now();
              const delta = String(data.text || data.delta || '');
              updateAssistant((message) => ({
                ...message,
                thinking: (message.thinking || '') + (delta.endsWith('\n') ? delta : `${delta}\n`),
                isThinking: true,
                metadata: (() => {
                  const next = { ...(message.metadata || {}) } as any;
                  if (typeof next.stream_t0 !== 'number') next.stream_t0 = now;
                  const chunks = Array.isArray(next.thinkingChunks) ? [...next.thinkingChunks] : [];
                  chunks.push({ type: 'research', text: delta });
                  next.thinkingChunks = chunks;
                  return next;
                })(),
              }));
            }
          } catch (err) {
            console.error('Erro parse SSE (final)', err);
          }
        }
      }

        if (streamCompleted || !streamRequestId || !lastEventId || attempt >= maxReconnects) {
          break;
        }
        attempt += 1;
        await new Promise((resolve) => setTimeout(resolve, retryDelayMs));
      }

    } catch (error) {
      console.error('[ChatStore] sendMessage error:', error);
      set((state) => {
        if (!state.currentChat) return {};
        const updatedMessages = assistantMessageId
          ? (state.currentChat.messages || []).map((message) =>
            message.id === assistantMessageId
              ? { ...message, content: 'Erro ao enviar mensagem' }
              : message
          )
          : state.currentChat.messages || [];
        return {
          currentChat: {
            ...state.currentChat,
            messages: updatedMessages,
          },
        };
      });
      set({ isSending: false });
      const msg = error instanceof Error ? error.message : String(error || '');
      toast.error('Erro ao enviar mensagem', {
        description: msg ? msg.slice(0, 220) : undefined,
      });
      throw error;
    }
  },

  startAgentGeneration: async (
    prompt: string,
    canvasContext?: CanvasContext | null,
    options: { budgetOverridePoints?: number } = {}
  ) => {
    const {
      currentChat,
      activeContext,
      effortLevel,
      minPages,
      maxPages,
      attachmentMode,
      chatPersonality,
    } = get();
    if (!currentChat) return;

    set({
      isAgentRunning: true,
      agentSteps: AgentOrchestrator.getInitialSteps(),
      retryProgress: null,
    });

    // Standardize full document generation on LangGraph.
    // Keep the legacy endpoint only for "canvasContext" (diff/suggestion) flows.
    if (!canvasContext) {
      await get().startLangGraphJob(prompt, options);
      return;
    }

    const normalizedRange = normalizePageRange(minPages, maxPages);
    const hasPageRange = normalizedRange.minPages > 0 || normalizedRange.maxPages > 0;
    const contextDocumentIds = (activeContext || [])
      .filter((item: any) => item?.type === 'file' && typeof item.id === 'string')
      .map((item: any) => item.id);
    const hasContextDocs = contextDocumentIds.length > 0;

    // --- Original Legacy Flow (Web Search / Simple) ---
    // Simulate steps visually while waiting for backend
    const stepsInterval = setInterval(() => {
      set((state) => {
        const newSteps = [...state.agentSteps];
        const workingIndex = newSteps.findIndex((s) => s.status === 'working');
        const pendingIndex = newSteps.findIndex((s) => s.status === 'pending');

        if (workingIndex !== -1) {
          newSteps[workingIndex].status = 'completed';
        }
        if (pendingIndex !== -1) {
          newSteps[pendingIndex].status = 'working';
        }
        return { agentSteps: newSteps };
      });
    }, 2000);

    try {
      const targetSectionScore = get().qualityTargetSectionScore;
      const targetFinalScore = get().qualityTargetFinalScore;
      const maxRounds = get().qualityMaxRounds;
      const styleRefineMaxRounds = get().qualityStyleRefineMaxRounds;
      const maxResearchVerifierAttempts = get().qualityMaxResearchVerifierAttempts;
      const maxRagRetries = get().qualityMaxRagRetries;
      const ragRetryExpandScope = get().qualityRagRetryExpandScope;
      const recursionLimitOverride = get().recursionLimitOverride;
      const strictDocumentGateOverride = get().strictDocumentGateOverride;
      const hilSectionPolicyOverride = get().hilSectionPolicyOverride;
      const hilFinalRequiredOverride = get().hilFinalRequiredOverride;
      const cragMinBestScoreOverride = get().cragMinBestScoreOverride;
      const cragMinAvgScoreOverride = get().cragMinAvgScoreOverride;
      const temperature = resolveTemperature(get().creativityMode, get().temperatureOverride);
      const perplexityPayload = buildPerplexityPayload(get());
      const deepResearchPayload = buildDeepResearchPayload(get());
      // Resolve 'auto' attachment mode based on model context window and file count
      const resolvedAttachmentMode =
        attachmentMode === 'auto'
          ? resolveAutoAttachmentMode([get().selectedModel], contextDocumentIds.length)
          : attachmentMode;

      const response = await apiClient.generateDocument(currentChat.id, {
        prompt,
        context: { active_items: activeContext },
        effort_level: effortLevel,
        ...(hasPageRange
          ? { min_pages: normalizedRange.minPages, max_pages: normalizedRange.maxPages }
          : {}),
        ...(hasContextDocs ? { context_documents: contextDocumentIds } : {}),
        attachment_mode: resolvedAttachmentMode,
        chat_personality: chatPersonality,
        model: get().selectedModel,
        model_gpt: get().gptModel,
        model_claude: get().claudeModel,
        strategist_model: get().agentStrategistModel,
        drafter_models: get().agentDrafterModels,
        reviewer_models: get().agentReviewerModels,
        use_multi_agent: get().useMultiAgent,
        reasoning_level: get().reasoningLevel,
        temperature,
        web_search: get().webSearch,
        search_mode: get().searchMode,
        ...perplexityPayload,
        ...deepResearchPayload,
        multi_query: get().multiQuery,
        breadth_first: get().breadthFirst,
        research_policy: get().researchPolicy,
        dense_research: get().denseResearch, // Should be false if we reached here usually, but keeping for safety
        thinking_level: get().reasoningLevel,
        document_type: get().documentType,
        doc_kind: get().docKind || undefined,
        doc_subtype: get().docSubtype || undefined,
        thesis: get().thesis,
        formatting_options: get().formattingOptions,
        citation_style: get().citationStyle,
        rag_top_k: get().ragTopK,
        rag_sources: get().ragSources,
        rag_jurisdictions:
          (get().ragGlobalJurisdictions || []).length > 0 ? get().ragGlobalJurisdictions : undefined,
        rag_source_ids:
          (get().ragGlobalSourceIds || []).length > 0 ? get().ragGlobalSourceIds : undefined,
        hil_outline_enabled: get().hilOutlineEnabled,
        hil_target_sections: get().hilTargetSections,
        auto_approve_hil: get().autoApproveHil,
        audit_mode: get().auditMode,
        quality_profile: get().qualityProfile,
        ...(targetSectionScore != null ? { target_section_score: targetSectionScore } : {}),
        ...(targetFinalScore != null ? { target_final_score: targetFinalScore } : {}),
        ...(maxRounds != null ? { max_rounds: maxRounds } : {}),
        ...(styleRefineMaxRounds != null ? { style_refine_max_rounds: styleRefineMaxRounds } : {}),
        ...(strictDocumentGateOverride != null
          ? { strict_document_gate: strictDocumentGateOverride }
          : {}),
        ...(hilSectionPolicyOverride != null
          ? { hil_section_policy: hilSectionPolicyOverride }
          : {}),
        ...(hilFinalRequiredOverride != null
          ? { hil_final_required: hilFinalRequiredOverride }
          : {}),
        ...(maxResearchVerifierAttempts != null
          ? { max_research_verifier_attempts: maxResearchVerifierAttempts }
          : {}),
        ...(maxRagRetries != null ? { max_rag_retries: maxRagRetries } : {}),
        ...(ragRetryExpandScope != null ? { rag_retry_expand_scope: ragRetryExpandScope } : {}),
        ...(recursionLimitOverride != null ? { recursion_limit: recursionLimitOverride } : {}),
        ...(cragMinBestScoreOverride != null
          ? { crag_min_best_score: cragMinBestScoreOverride }
          : {}),
        ...(cragMinAvgScoreOverride != null ? { crag_min_avg_score: cragMinAvgScoreOverride } : {}),
        document_checklist_hint: get().documentChecklist,
        template_id: get().templateId || undefined,
        template_document_id: get().templateDocumentId || undefined,
        variables: get().templateVariables,
        ...(options.budgetOverridePoints ? { budget_override_points: options.budgetOverridePoints } : {}),
        ...(get().selectedPlaybookPrompt ? { playbook_prompt: get().selectedPlaybookPrompt } : {}),
	        rag_config: {
	          top_k: get().ragTopK,
	          sources: get().ragSources,
            jurisdictions:
              (get().ragGlobalJurisdictions || []).length > 0 ? get().ragGlobalJurisdictions : undefined,
	          tenant_id: get().tenantId,
	          use_templates: get().useTemplates,
	          template_filters: get().templateFilters,
	          template_id: get().templateId || undefined,
	          template_document_id: get().templateDocumentId || undefined,
	          variables: get().templateVariables,
	          prompt_extra: get().promptExtra,
	          adaptive_routing: true,
	          rag_mode: 'manual',
	          crag_gate: true,
	          ...(cragMinBestScoreOverride != null
	            ? { crag_min_best_score: cragMinBestScoreOverride }
	            : {}),
	          ...(cragMinAvgScoreOverride != null
	            ? { crag_min_avg_score: cragMinAvgScoreOverride }
	            : {}),
	          hyde_enabled: true,
	          graph_rag_enabled: true,
          argument_graph_enabled: true,
          graph_hops: get().graphHops,
          rag_scope: get().ragScope,
          rag_selected_groups: (get().ragSelectedGroups || []).length > 0 ? get().ragSelectedGroups : undefined,
          rag_allow_private: get().ragAllowPrivate,
        rag_allow_groups: get().ragAllowGroups,
        },
      } as any);

      clearInterval(stepsInterval);

      // Mark all steps completed
      set((state) => ({
        agentSteps: state.agentSteps.map((s) => ({ ...s, status: 'completed' })),
      }));

      const replacementText = canvasContext ? extractReplacementText(response.content || '') : '';
      const normalizedOriginal = (canvasContext?.text || '').trim();
      const hasReplacement = replacementText && replacementText.trim() !== normalizedOriginal;
      const canvasSuggestion =
        canvasContext && hasReplacement
          ? {
            original: canvasContext.text,
            replacement: replacementText,
            action: canvasContext.action,
          }
          : null;

      const responseMetadata = (response as any)?.metadata ? { ...(response as any).metadata } : {};
      Object.assign(responseMetadata, buildCommitteeMetadata(get()));
      if (canvasSuggestion) {
        responseMetadata.canvas_suggestion = canvasSuggestion;
      }

      // Add final message with document
      const aiMessage: Message = {
        id: nanoid(),
        content: response.content || 'Documento gerado.',
        role: 'assistant',
        timestamp: new Date().toISOString(),
        metadata: Object.keys(responseMetadata).length > 0 ? responseMetadata : undefined,
      };

      set((state) => ({
        currentChat: state.currentChat
          ? {
            ...state.currentChat,
            messages: [...(state.currentChat.messages || []), aiMessage],
          }
          : null,
        isAgentRunning: false,
      }));

      // Atualiza canvas automaticamente (fluxo padrão)
      // Se houver sugestão de trecho, não sobrescreve o documento inteiro.
      if (!canvasSuggestion) {
        try {
          const { setContent: setCanvasContent, setMetadata } = useCanvasStore.getState();
          setCanvasContent(response.content || '');
          const nextMetadata = {
            ...((response as any)?.metadata || {}),
            ...buildCommitteeMetadata(get()),
          };
          setMetadata(nextMetadata, (response as any)?.cost_info || null);
        } catch {
          // noop
        }
      }
    } catch (e) {
      clearInterval(stepsInterval);
      const details = describeApiError(e);
      const status = (e as any)?.response?.status;
      const detailData = (e as any)?.response?.data?.detail;

      // Handle billing errors (402, 409, 422)
      if ((status === 402 || status === 409 || status === 422) && detailData && typeof detailData === 'object') {
        set({
          isAgentRunning: false,
          billingModal: {
            open: true,
            quote: detailData as BillingQuote,
            retry: { kind: 'agent_legacy', prompt, canvasContext },
          },
        });
        return;
      }

      console.error('[ChatStore] StartAgentGeneration Error:', details, e);
      toast.error(`Erro na geração (Comitê): ${details}`);

      set((state) => ({
        isAgentRunning: false,
        agentSteps: state.agentSteps.map((s) =>
          s.status === 'working'
            ? { ...s, status: 'failed' as const, message: 'Erro na geração' }
            : s
        ),
      }));
    }
  },

  startLangGraphJob: async (
    prompt: string,
    options: { budgetOverridePoints?: number } = {}
  ) => {
    const { currentChat } = get();
    if (!currentChat) throw new Error('No chat selected');
    const persistChatId = currentChat.id;

    // Ensure UI is in "running" state (Wizard can call this directly)
    set({ isAgentRunning: true, retryProgress: null });
    try {
      const canvas = useCanvasStore.getState();
      canvas.showCanvas();
      canvas.setActiveTab('process');
    } catch {
      // noop
    }

    try {
      const { setMetadata, metadata } = useCanvasStore.getState();
      const updatedMetadata = {
        ...(metadata || {}),
        ...buildCommitteeMetadata(get()),
      };
      setMetadata(updatedMetadata, null);
      persistDraftMetadata(persistChatId, updatedMetadata);
    } catch {
      // noop
    }

    try {
      const targetSectionScore = get().qualityTargetSectionScore;
      const targetFinalScore = get().qualityTargetFinalScore;
      const maxRounds = get().qualityMaxRounds;
      const styleRefineMaxRounds = get().qualityStyleRefineMaxRounds;
      const maxResearchVerifierAttempts = get().qualityMaxResearchVerifierAttempts;
      const maxRagRetries = get().qualityMaxRagRetries;
      const ragRetryExpandScope = get().qualityRagRetryExpandScope;
      const recursionLimitOverride = get().recursionLimitOverride;
	      const strictDocumentGateOverride = get().strictDocumentGateOverride;
	      const hilSectionPolicyOverride = get().hilSectionPolicyOverride;
	      const hilFinalRequiredOverride = get().hilFinalRequiredOverride;
	      const cragMinBestScoreOverride = get().cragMinBestScoreOverride;
	      const cragMinAvgScoreOverride = get().cragMinAvgScoreOverride;
	      const temperature = resolveTemperature(get().creativityMode, get().temperatureOverride);
	      const perplexityPayload = buildPerplexityPayload(get());
	      const outlineOverride = parseOutlineTemplate(get().minutaOutlineTemplate);

	      const normalizedRange = normalizePageRange(get().minPages, get().maxPages);
	      const hasPageRange = normalizedRange.minPages > 0 || normalizedRange.maxPages > 0;
	      const contextDocumentIds = (get().activeContext || [])
        .filter((item: any) => item?.type === 'file' && typeof item.id === 'string')
        .map((item: any) => item.id);
      const hasContextDocs = contextDocumentIds.length > 0;

      const deepResearchPayload = buildDeepResearchPayload(get());
      // Resolve 'auto' attachment mode based on model context window and file count
      const resolvedAttachmentMode =
        get().attachmentMode === 'auto'
          ? resolveAutoAttachmentMode([get().selectedModel], contextDocumentIds.length)
          : get().attachmentMode;

      const jobRes = await apiClient.startJob({
        prompt,
        web_search: get().webSearch,
        web_search_model: get().webSearchModel === 'auto' ? undefined : get().webSearchModel,
        search_mode: get().searchMode,
        ...perplexityPayload,
        ...deepResearchPayload,
        multi_query: get().multiQuery,
        breadth_first: get().breadthFirst,
        research_policy: get().researchPolicy,
        dense_research: get().denseResearch,
        deep_research_provider: get().deepResearchProvider,
        deep_research_model: get().deepResearchModel,
        effort_level: get().effortLevel,
        ...(hasPageRange
          ? { min_pages: normalizedRange.minPages, max_pages: normalizedRange.maxPages }
          : {}),
        ...(hasContextDocs ? { context_documents: contextDocumentIds } : {}),
        attachment_mode: resolvedAttachmentMode,
        chat_personality: get().chatPersonality,
        reasoning_level: get().reasoningLevel,
        thinking_level: get().reasoningLevel,
        temperature,
        document_type: get().documentType,
        doc_kind: get().docKind || undefined,
        doc_subtype: get().docSubtype || undefined,
        thesis: get().thesis,
        use_multi_agent: get().useMultiAgent,
        formatting_options: get().formattingOptions,
        citation_style: get().citationStyle,
        hil_target_sections: get().hilTargetSections,
        hil_outline_enabled: get().hilOutlineEnabled,
        auto_approve_hil: get().autoApproveHil,
        audit_mode: get().auditMode,
        quality_profile: get().qualityProfile,
        ...(targetSectionScore != null ? { target_section_score: targetSectionScore } : {}),
        ...(targetFinalScore != null ? { target_final_score: targetFinalScore } : {}),
        ...(maxRounds != null ? { max_rounds: maxRounds } : {}),
        ...(get().qualityMaxFinalReviewLoops != null
          ? { max_final_review_loops: get().qualityMaxFinalReviewLoops }
          : {}),
        ...(styleRefineMaxRounds != null ? { style_refine_max_rounds: styleRefineMaxRounds } : {}),
        ...(get().maxDivergenceHilRounds != null
          ? { max_divergence_hil_rounds: get().maxDivergenceHilRounds }
          : {}),
        ...(get().forceGranularDebate ? { force_granular_debate: true } : {}),
        ...(strictDocumentGateOverride != null
          ? { strict_document_gate: strictDocumentGateOverride }
          : {}),
        ...(hilSectionPolicyOverride != null
          ? { hil_section_policy: hilSectionPolicyOverride }
          : {}),
        ...(hilFinalRequiredOverride != null
          ? { hil_final_required: hilFinalRequiredOverride }
          : {}),
        ...(maxResearchVerifierAttempts != null
          ? { max_research_verifier_attempts: maxResearchVerifierAttempts }
          : {}),
	        ...(maxRagRetries != null ? { max_rag_retries: maxRagRetries } : {}),
	        ...(ragRetryExpandScope != null ? { rag_retry_expand_scope: ragRetryExpandScope } : {}),
	        ...(recursionLimitOverride != null ? { recursion_limit: recursionLimitOverride } : {}),
	        document_checklist_hint: get().documentChecklist,
	        ...(outlineOverride.length > 0 ? { outline_override: outlineOverride } : {}),
	        judge_model: get().selectedModel,
	        gpt_model: get().gptModel,
	        claude_model: get().claudeModel,
	        strategist_model: get().agentStrategistModel,
	        drafter_models: get().agentDrafterModels,
	        reviewer_models: get().agentReviewerModels,
	        adaptive_routing: true,
	        rag_mode: 'manual',
	        crag_gate: true,
	        ...(cragMinBestScoreOverride != null
	          ? { crag_min_best_score: cragMinBestScoreOverride }
	          : {}),
	        ...(cragMinAvgScoreOverride != null ? { crag_min_avg_score: cragMinAvgScoreOverride } : {}),
	        hyde_enabled: true,
        graph_rag_enabled: true,
        argument_graph_enabled: true,
        graph_hops: get().graphHops,
        rag_scope: get().ragScope,
        rag_selected_groups: (get().ragSelectedGroups || []).length > 0 ? get().ragSelectedGroups : undefined,
        rag_allow_private: get().ragAllowPrivate,
        rag_allow_groups: get().ragAllowGroups,
        rag_jurisdictions:
          (get().ragGlobalJurisdictions || []).length > 0 ? get().ragGlobalJurisdictions : undefined,
        rag_source_ids:
          (get().ragGlobalSourceIds || []).length > 0 ? get().ragGlobalSourceIds : undefined,
        stream_tokens: true,
        stream_token_chunk_chars: 40,
	        ...(options.budgetOverridePoints ? { budget_override_points: options.budgetOverridePoints } : {}),
	        ...(get().selectedPlaybookPrompt ? { playbook_prompt: get().selectedPlaybookPrompt } : {}),
      } as any);

      const jobId = jobRes.job_id;
      set({ currentJobId: jobId, jobEvents: [], jobOutline: [], reviewData: null });

      attachLangGraphStream(jobId, persistChatId, set, get);
    } catch (e) {
      console.error('Error starting job', e);
      const status = (e as any)?.response?.status;
      const detail = (e as any)?.response?.data?.detail;
      if ((status === 402 || status === 409 || status === 422) && detail && typeof detail === 'object') {
        set({
          isAgentRunning: false,
          billingModal: {
            open: true,
            quote: detail as BillingQuote,
            retry: { kind: 'job', prompt },
          },
        });
        return;
      }
      set({ isAgentRunning: false });
      toast.error('Erro ao iniciar geração (LangGraph)');
      return;
    }
  },

  generateDocumentWithResult: async (
    prompt: string,
    caseId?: string,
    options: { budgetOverridePoints?: number } = {}
  ) => {
    const {
      currentChat,
      activeContext,
      effortLevel,
      minPages,
      maxPages,
      attachmentMode,
      chatPersonality,
    } = get();
    if (!currentChat) throw new Error('Crie uma conversa primeiro');

    set({
      isAgentRunning: true,
      agentSteps: AgentOrchestrator.getInitialSteps(),
      retryProgress: null,
    });

    const normalizedRange = normalizePageRange(minPages, maxPages);
    const hasPageRange = normalizedRange.minPages > 0 || normalizedRange.maxPages > 0;
    const contextDocumentIds = (activeContext || [])
      .filter((item: any) => item?.type === 'file' && typeof item.id === 'string')
      .map((item: any) => item.id);
    const hasContextDocs = contextDocumentIds.length > 0;

    try {
      const targetSectionScore = get().qualityTargetSectionScore;
      const targetFinalScore = get().qualityTargetFinalScore;
      const maxRounds = get().qualityMaxRounds;
      const styleRefineMaxRounds = get().qualityStyleRefineMaxRounds;
      const maxResearchVerifierAttempts = get().qualityMaxResearchVerifierAttempts;
      const maxRagRetries = get().qualityMaxRagRetries;
      const ragRetryExpandScope = get().qualityRagRetryExpandScope;
      const recursionLimitOverride = get().recursionLimitOverride;
	      const strictDocumentGateOverride = get().strictDocumentGateOverride;
	      const hilSectionPolicyOverride = get().hilSectionPolicyOverride;
	      const hilFinalRequiredOverride = get().hilFinalRequiredOverride;
	      const cragMinBestScoreOverride = get().cragMinBestScoreOverride;
	      const cragMinAvgScoreOverride = get().cragMinAvgScoreOverride;
	      const temperature = resolveTemperature(get().creativityMode, get().temperatureOverride);
	      const perplexityPayload = buildPerplexityPayload(get());
	      const outlineOverride = parseOutlineTemplate(get().minutaOutlineTemplate);

	      const deepResearchPayload = buildDeepResearchPayload(get());
      // Resolve 'auto' attachment mode based on model context window and file count
      const resolvedAttachmentMode =
        attachmentMode === 'auto'
          ? resolveAutoAttachmentMode([get().selectedModel], contextDocumentIds.length)
          : attachmentMode;

      const response = await apiClient.generateDocument(currentChat.id, {
        prompt,
        case_id: caseId,
        context: { active_items: activeContext },
        effort_level: effortLevel,
        ...(hasPageRange
          ? { min_pages: normalizedRange.minPages, max_pages: normalizedRange.maxPages }
          : {}),
        ...(hasContextDocs ? { context_documents: contextDocumentIds } : {}),
        attachment_mode: resolvedAttachmentMode,
        chat_personality: chatPersonality,
        model: get().selectedModel,

        // Agent Mode
        use_multi_agent: get().useMultiAgent,
        model_gpt: get().gptModel,
        model_claude: get().claudeModel,
        strategist_model: get().agentStrategistModel,
        drafter_models: get().agentDrafterModels,
        reviewer_models: get().agentReviewerModels,
        reasoning_level: get().reasoningLevel,
        temperature,

        // Flags
        web_search: get().webSearch,
        search_mode: get().searchMode,
        ...perplexityPayload,
        ...deepResearchPayload,
        multi_query: get().multiQuery,
        breadth_first: get().breadthFirst,
        research_policy: get().researchPolicy,
        dense_research: get().denseResearch,
        thinking_level: get().reasoningLevel,
        audit: get().audit,

        // Document Meta
        document_type: get().documentType,
        thesis: get().thesis,
        formatting_options: get().formattingOptions,
        citation_style: get().citationStyle,
        hil_outline_enabled: get().hilOutlineEnabled,
        hil_target_sections: get().hilTargetSections,
        auto_approve_hil: get().autoApproveHil,
        audit_mode: get().auditMode,
        quality_profile: get().qualityProfile,
        ...(targetSectionScore != null ? { target_section_score: targetSectionScore } : {}),
        ...(targetFinalScore != null ? { target_final_score: targetFinalScore } : {}),
        ...(maxRounds != null ? { max_rounds: maxRounds } : {}),
        ...(styleRefineMaxRounds != null ? { style_refine_max_rounds: styleRefineMaxRounds } : {}),
        ...(strictDocumentGateOverride != null
          ? { strict_document_gate: strictDocumentGateOverride }
          : {}),
        ...(hilSectionPolicyOverride != null
          ? { hil_section_policy: hilSectionPolicyOverride }
          : {}),
        ...(hilFinalRequiredOverride != null
          ? { hil_final_required: hilFinalRequiredOverride }
          : {}),
        ...(maxResearchVerifierAttempts != null
          ? { max_research_verifier_attempts: maxResearchVerifierAttempts }
          : {}),
	        ...(maxRagRetries != null ? { max_rag_retries: maxRagRetries } : {}),
	        ...(ragRetryExpandScope != null ? { rag_retry_expand_scope: ragRetryExpandScope } : {}),
	        ...(recursionLimitOverride != null ? { recursion_limit: recursionLimitOverride } : {}),
	        document_checklist_hint: get().documentChecklist,
	        ...(outlineOverride.length > 0 ? { outline_override: outlineOverride } : {}),

	        // RAG Config (Flattened for Backend Adapter)
	        rag_top_k: get().ragTopK,
	        rag_sources: get().ragSources,
          rag_jurisdictions:
            (get().ragGlobalJurisdictions || []).length > 0 ? get().ragGlobalJurisdictions : undefined,
          rag_source_ids:
            (get().ragGlobalSourceIds || []).length > 0 ? get().ragGlobalSourceIds : undefined,
        tenant_id: get().tenantId,
        use_templates: get().useTemplates,
        template_filters: get().templateFilters,
        prompt_extra: get().promptExtra,
        template_id: get().templateId || undefined,
        template_document_id: get().templateDocumentId || undefined,
	        variables: get().templateVariables,
	        adaptive_routing: true,
	        crag_gate: true,
	        ...(cragMinBestScoreOverride != null
	          ? { crag_min_best_score: cragMinBestScoreOverride }
	          : {}),
	        ...(cragMinAvgScoreOverride != null ? { crag_min_avg_score: cragMinAvgScoreOverride } : {}),
	        hyde_enabled: true,
        graph_rag_enabled: true,
        argument_graph_enabled: true,
        graph_hops: get().graphHops,
        rag_scope: get().ragScope,
        rag_selected_groups: (get().ragSelectedGroups || []).length > 0 ? get().ragSelectedGroups : undefined,
        rag_allow_private: get().ragAllowPrivate,
        rag_allow_groups: get().ragAllowGroups,

        // Context Caching (v3.4)
        // Only send if mode is upload_cache or auto.
        context_files: ['upload_cache', 'auto'].includes(get().contextMode)
          ? get().contextFiles
          : undefined,
        cache_ttl: ['upload_cache', 'auto'].includes(get().contextMode)
          ? get().cacheTTL
          : undefined,
        ...(options.budgetOverridePoints ? { budget_override_points: options.budgetOverridePoints } : {}),
      });

      // Add assistant message to chat local history
      const aiMessage: Message = {
        id: nanoid(),
        content: response.content || 'Documento gerado.',
        role: 'assistant',
        timestamp: new Date().toISOString(),
        metadata: buildCommitteeMetadata(get()),
      };

      set((state) => ({
        currentChat: state.currentChat
          ? {
            ...state.currentChat,
            messages: [...(state.currentChat.messages || []), aiMessage],
          }
          : null,
        isAgentRunning: false,
        agentSteps: state.agentSteps.map((s) => ({ ...s, status: 'completed' })),
      }));

      // Atualiza canvas automaticamente (helper usado por /minuta antigo)
      try {
        const { setContent: setCanvasContent, setMetadata } = useCanvasStore.getState();
        setCanvasContent(response.content || '');
        const nextMetadata = {
          ...((response as any)?.metadata || {}),
          ...buildCommitteeMetadata(get()),
        };
        setMetadata(nextMetadata, (response as any)?.cost_info || null);
      } catch {
        // noop
      }

      return response;
    } catch (error) {
      const status = (error as any)?.response?.status;
      const detail = (error as any)?.response?.data?.detail;
      if ((status === 402 || status === 409 || status === 422) && detail && typeof detail === 'object') {
        set({
          isAgentRunning: false,
          billingModal: {
            open: true,
            quote: detail as BillingQuote,
            retry: { kind: 'generate', prompt, caseId },
          },
        });
        return;
      }
      set({ isAgentRunning: false });
      throw error;
    }
  },

  generateDocument: async (data) => {
    // Legacy method, redirect to sendMessage
    return get().sendMessage(data.prompt);
  },

  submitReview: async (decision) => {
    const { currentJobId, pendingChatOutline, reviewData } = get();
    const isChatOutline = reviewData?.mode === 'chat';

    if (pendingChatOutline && decision?.checkpoint === 'outline' && isChatOutline) {
      set({ reviewData: null, pendingChatOutline: null });

      if (!decision?.approved) {
        toast.info('Outline rejeitado. Mensagem cancelada.');
        return;
      }

      const editsText = typeof decision?.edits === 'string' ? decision.edits : '';
      const approvedOutline = editsText
        ? editsText
          .split('\n')
          .map((line: string) => line.trim())
          .filter(Boolean)
        : pendingChatOutline.outline;

      await get().sendMessage(pendingChatOutline.content, {
        outline: approvedOutline,
        skipOutlineFetch: true,
        skipUserMessage: true,
        canvasWrite: pendingChatOutline.canvasWrite,
        outlinePipeline: pendingChatOutline.outlinePipeline,
      });
      return;
    }

    if (!currentJobId) return;

    // Optimistic close
    set({ reviewData: null });

    if (Array.isArray((decision as any)?.hil_target_sections)) {
      set({ hilTargetSections: (decision as any).hil_target_sections });
    }

    await apiClient.resumeJob(currentJobId, decision);
    set({ isAgentRunning: true, retryProgress: null });
    attachLangGraphStream(currentJobId, get().currentChat?.id ?? null, set, get);
  },

  addMessage: (message: Message) =>
    set((state) => ({
      currentChat: state.currentChat
        ? { ...state.currentChat, messages: [...(state.currentChat.messages || []), message] }
        : null,
    })),

  // ===========================================================================
  // MULTI-MODEL STREAMING (V2)
  // ===========================================================================

  consolidateTurn: async (turnId: string) => {
    const { currentChat } = get();
    if (!currentChat) return;
    if (!turnId) return;

    // Evita duplicar
    const already = currentChat.messages.some(
      (m) =>
        m.role === 'assistant' &&
        m.metadata?.turn_id === turnId &&
        (m.metadata?.is_consolidated ||
          String(m.metadata?.model || '').toLowerCase() === 'consolidado')
    );
    if (already) {
      toast.info('Consolidado já foi gerado para este turno.');
      return;
    }

    const userMsg = currentChat.messages.find(
      (m) => m.role === 'user' && m.metadata?.turn_id === turnId
    );
    const userText = userMsg?.content || '';

    const candidates = currentChat.messages
      .filter(
        (m) =>
          m.role === 'assistant' &&
          m.metadata?.turn_id === turnId &&
          m.metadata?.model &&
          !m.metadata?.is_consolidated
      )
      .map((m) => ({ model: String(m.metadata.model), text: String(m.content || '').trim() }))
      .filter((c) => c.text.length > 0);

    if (candidates.length < 2) {
      toast.info('Preciso de pelo menos 2 respostas para consolidar.');
      return;
    }

    const mode: 'merge' | 'debate' = get().multiModelDeepDebate ? 'debate' : 'merge';
    toast.info(
      mode === 'debate'
        ? 'Gerando Consolidado (Debate Profundo, consome tokens adicionais)...'
        : 'Gerando Consolidado (consome tokens adicionais)...'
    );
    const res = await apiClient.consolidateMultiChatTurn(currentChat.id, {
      message: userText,
      candidates,
      mode,
    });

    const consolidatedMsg: Message = {
      id: nanoid(),
      role: 'assistant',
      content: res.content || '',
      timestamp: new Date().toISOString(),
      metadata: {
        model: mode === 'debate' ? 'Consolidado (Debate)' : 'Consolidado',
        turn_id: turnId,
        is_consolidated: true,
      },
    };

    set((state) => ({
      currentChat: state.currentChat
        ? {
          ...state.currentChat,
          messages: [...(state.currentChat.messages || []), consolidatedMsg],
        }
        : null,
    }));
    toast.success('Consolidado gerado.');
  },

  startMultiModelStream: async (
    content: string,
    options: { budgetOverridePoints?: number; existingTurnId?: string; skipUserMessage?: boolean } = {}
  ) => {
    const {
      currentChat,
      selectedModels,
      gptModel,
      claudeModel,
      chatPersonality,
      activeContext,
      attachmentMode,
    } = get();
    if (!currentChat) throw new Error('No chat');
    const temperature = resolveTemperature(get().creativityMode, get().temperatureOverride);

    // --- Model Shortcut Parsing ---
    // Detects @model prefix and overrides selectedModels for this turn only.
    const MODEL_SHORTCUTS: Record<string, string> = {
      '@gpt': gptModel || 'gpt-5.2',
      '@claude': claudeModel || 'claude-4.5-sonnet',
      '@gemini': 'gemini-3-flash',
      '@gemini-pro': 'gemini-3-pro',
      '@mini': 'gpt-5-mini',
      '@flash': 'gemini-3-flash',
      '@haiku': 'claude-4.5-haiku',
      '@sonar': 'sonar',
      '@sonar-pro': 'sonar-pro',
      '@sonar-deep': 'sonar-deep-research',
      '@sonar-reason': 'sonar-reasoning-pro',
    };

    let actualContent = content.trim();
    let targetModels = [...selectedModels];
    let overrideWebSearch: boolean | null = null;
    let overrideDenseResearch: boolean | null = null;
    let overrideDeepResearchPayload: Record<string, any> | null = null;

    for (const [shortcut, modelId] of Object.entries(MODEL_SHORTCUTS)) {
      if (!actualContent.toLowerCase().startsWith(shortcut)) continue;

      actualContent = actualContent.slice(shortcut.length).trim();

      if (isPerplexityDeepResearchModelId(modelId)) {
        overrideDenseResearch = true;
        overrideWebSearch = true;
        overrideDeepResearchPayload = {
          deep_research_provider: 'perplexity',
          deep_research_model: 'sonar-deep-research',
        };
        targetModels = ['sonar-pro'];
        toast.info(
          'Deep Research (Perplexity) ativado apenas neste envio. Respondendo com Sonar Pro.'
        );
      } else {
        if (isPerplexityModelId(modelId) && !get().webSearch) {
          get().setWebSearch(true);
          toast.info('Web Search ativado para modelos Sonar.');
        }
        targetModels = [modelId];
        toast.info(`Roteando para ${modelId}`);
      }
      break;
    }

    // Identificador único do "turno" para agrupar respostas multi-modelo na UI
    const turnId = options.existingTurnId || nanoid();

    if (!options.skipUserMessage) {
      // 1. Add User Message (show original content with shortcut for transparency)
      const userMsg: Message = {
        id: nanoid(),
        content, // Keep original for display
        role: 'user',
        timestamp: new Date().toISOString(),
        metadata: { turn_id: turnId },
      };

      set((state) => ({
        currentChat: state.currentChat
          ? {
            ...state.currentChat,
            messages: [...(state.currentChat.messages || []), userMsg],
          }
          : null,
        isSending: true,
      }));
    } else {
      set({ isSending: true });
    }

    const attachmentDocs = (activeContext || [])
      .filter((item: any) => item?.type === 'file' && typeof item.id === 'string')
      .map((item: any) => ({
        id: item.id,
        type: 'doc',
        name: item.name,
      }));
    const perplexityPayload = buildPerplexityPayload(get(), targetModels);
    const deepResearchPayload = {
      ...buildDeepResearchPayload(get()),
      ...(overrideDeepResearchPayload || {}),
    };
    const effectiveWebSearch = overrideWebSearch ?? get().webSearch;
    const effectiveDenseResearch = overrideDenseResearch ?? get().denseResearch;
    const mcpServerLabels =
      get().mcpToolCalling && !get().mcpUseAllServers && (get().mcpServerLabels || []).length > 0
        ? get().mcpServerLabels
        : undefined;
    const perModelOverrides = buildModelOverridesPayload(get().modelOverrides);
    const defaultThinkingBudget = parseThinkingBudget(get().thinkingBudget);
    const thinkingEnabledByModel: Record<string, boolean> = {};
    const startThinkingByModel: Record<string, boolean> = {};
    targetModels.forEach((modelId) => {
      const override = get().modelOverrides?.[modelId] || {};
      const effectiveReasoningLevel = override.reasoningLevel || get().reasoningLevel;
      const rawBudget = Object.prototype.hasOwnProperty.call(override, 'thinkingBudget')
        ? override.thinkingBudget
        : get().thinkingBudget;
      const effectiveBudget = parseThinkingBudget(rawBudget);
      const enabled = resolveThinkingEnabled(modelId, effectiveReasoningLevel, effectiveBudget);
      thinkingEnabledByModel[modelId] = enabled;
      startThinkingByModel[modelId] = shouldStartThinking(
        modelId,
        effectiveReasoningLevel,
        enabled
      );
    });

    // Resolve 'auto' attachment mode based on model context window and file count
    const resolvedAttachmentMode =
      attachmentMode === 'auto'
        ? resolveAutoAttachmentMode(targetModels, attachmentDocs.length)
        : attachmentMode;

    try {
      const streamPayload = {
        message: actualContent,
        models: targetModels,
        attachments: attachmentDocs,
        attachment_mode: resolvedAttachmentMode,
        chat_personality: chatPersonality,
        reasoning_level: get().reasoningLevel,
        verbosity: get().verbosity,
        ...(defaultThinkingBudget !== null ? { thinking_budget: defaultThinkingBudget } : {}),
        temperature,
        mcp_tool_calling: get().mcpToolCalling,
        mcp_server_labels: mcpServerLabels,
        web_search: effectiveWebSearch,
        multi_query: get().multiQuery,
        breadth_first: get().breadthFirst,
        search_mode: get().searchMode,
        ...perplexityPayload,
        ...deepResearchPayload,
        dense_research: effectiveDenseResearch,
        research_policy: get().researchPolicy,
        ...(perModelOverrides ? { per_model_overrides: perModelOverrides } : {}),
        ...(options.budgetOverridePoints
          ? { budget_override_points: options.budgetOverridePoints }
          : {}),
      };

      let streamRequestId: string | null = null;
      let lastEventId: string | null = null;
      let lastAppliedEventId: number | null = null;
      let retryDelayMs = 2000;
      let streamCompleted = false;
      const doneByModel = new Set<string>();

      // Captura do texto completo por modelo para gerar "Consolidado" ao final (opcional)
      const fullTextByModel: Record<string, string> = {};
      targetModels.forEach((m) => {
        fullTextByModel[m] = '';
      });

      // Prepare placeholders for assistant responses
      // Map modelId -> messageId
      const modelMessageIds: Record<string, string> = {};
      targetModels.forEach((m) => {
        modelMessageIds[m] = nanoid();
      });

      // Init empty messages for each model
      set((state) => {
        if (!state.currentChat) return {};

        const newMessages = targetModels.map((m) => ({
          id: modelMessageIds[m],
          role: 'assistant' as const,
          content: '',
          timestamp: new Date().toISOString(),
          thinking: startThinkingByModel[m] ? '' : undefined,
          isThinking: startThinkingByModel[m],
          metadata: {
            model: m,
            turn_id: turnId,
            stream_t0: Date.now(),
            thinking_enabled: thinkingEnabledByModel[m],
          },
        }));

        return {
          currentChat: {
            ...state.currentChat,
            messages: [...(state.currentChat.messages || []), ...newMessages],
          },
        };
      });

      const updateModelMessage = (modelId: string, updater: (message: any) => any) => {
        const msgId = modelMessageIds[modelId];
        if (!msgId) return;
        set((state) => {
          if (!state.currentChat) return {};
          const msgs = state.currentChat.messages.map((m) => {
            if (m.id === msgId) return updater(m);
            return m;
          });
          return { currentChat: { ...state.currentChat, messages: msgs } };
        });
      };

      const upsertModelActivityStep = (
        metadata: any,
        step: {
          id: string;
          title: string;
          status?: 'running' | 'done' | 'error';
          detail?: string;
          tags?: string[];
          kind?: 'assess' | 'attachment_review' | 'file_terms' | 'web_search' | 'delegate_subtask' | 'generic';
          attachments?: Array<{ name: string; kind?: string; ext?: string }>;
          terms?: string[];
          sources?: Array<{ title?: string; url: string }>;
        },
        op?: 'add' | 'update' | 'append' | 'done' | 'error' | 'tags'
      ) => {
        const meta: any = { ...(metadata || {}) };
        const activity: any = { ...(meta.activity || {}) };
        const steps: any[] = Array.isArray(activity.steps) ? [...activity.steps] : [];
        const idx = steps.findIndex((s) => s?.id === step.id);
        const prev = idx >= 0 ? steps[idx] : null;

        let nextDetail = typeof step.detail === 'string' ? step.detail : prev?.detail ?? '';
        let nextTags = step.tags ?? prev?.tags ?? [];
        const nextKind = step.kind ?? prev?.kind;

        const mergeStrings = (a: any[] | undefined, b: any[] | undefined) => {
          const out: string[] = [];
          const seen = new Set<string>();
          for (const item of [...(a || []), ...(b || [])]) {
            const v = String(item || '').trim();
            if (!v) continue;
            const k = v.toLowerCase();
            if (seen.has(k)) continue;
            seen.add(k);
            out.push(v);
          }
          return out;
        };

        const mergeSources = (a: any[] | undefined, b: any[] | undefined) => {
          const out: Array<{ title?: string; url: string }> = [];
          const seen = new Set<string>();
          for (const item of [...(a || []), ...(b || [])]) {
            const url = String(item?.url || '').trim();
            if (!url) continue;
            const key = url.toLowerCase();
            if (seen.has(key)) continue;
            seen.add(key);
            out.push({ url, title: item?.title ? String(item.title) : undefined });
          }
          return out;
        };

        const mergeAttachments = (a: any[] | undefined, b: any[] | undefined) => {
          const out: Array<{ name: string; kind?: string; ext?: string }> = [];
          const seen = new Set<string>();
          for (const item of [...(a || []), ...(b || [])]) {
            const name = String(item?.name || '').trim();
            if (!name) continue;
            const ext = item?.ext ? String(item.ext).trim() : undefined;
            const key = `${name.toLowerCase()}|${String(ext || '').toLowerCase()}`;
            if (seen.has(key)) continue;
            seen.add(key);
            out.push({ name, kind: item?.kind ? String(item.kind) : undefined, ext });
          }
          return out;
        };

        if (op === 'append' && prev?.detail && step.detail) {
          nextDetail = `${prev.detail}${step.detail}`;
        } else if (op === 'tags' && step.tags) {
          const existing = new Set(prev?.tags ?? []);
          step.tags.forEach((t) => existing.add(t));
          nextTags = Array.from(existing);
        }

        const next = {
          id: step.id,
          title: step.title ?? prev?.title ?? step.id,
          status:
            op === 'done'
              ? 'done'
              : op === 'error'
                ? 'error'
                : (step.status ?? prev?.status ?? 'running'),
          detail: nextDetail,
          tags: nextTags,
          kind: nextKind,
          attachments: mergeAttachments(prev?.attachments, step.attachments),
          terms: mergeStrings(prev?.terms, step.terms),
          sources: mergeSources(prev?.sources, step.sources),
        };

        if (idx >= 0) steps[idx] = next;
        else steps.push(next);
        activity.steps = steps;
        meta.activity = activity;
        return meta;
      };

      const maxReconnects = 1;
      let attempt = 0;
      while (true) {
        // 2. Fetch SSE Stream (use targetModels which may be overridden, and actualContent which has shortcut stripped)
        const resumeAttempt = attempt > 0 && !!streamRequestId && !!lastEventId;
        const requestPayload = resumeAttempt && streamRequestId
          ? { ...streamPayload, stream_request_id: streamRequestId }
          : streamPayload;
        const requestHeaders: HeadersInit = resumeAttempt && lastEventId
          ? { 'Last-Event-ID': lastEventId }
          : {};

        const response = await apiClient.fetchWithAuth(
          `/multi-chat/threads/${currentChat.id}/messages`,
          {
            method: 'POST',
            body: JSON.stringify(requestPayload),
            headers: requestHeaders,
          }
        );

        if (!response.ok || !response.body) {
          let detail = '';
          let parsed: any = null;
          try {
            const raw = await response.text();
            if (raw) {
              try {
                parsed = JSON.parse(raw);
                detail = parsed?.detail ? String(parsed.detail) : raw;
              } catch {
                detail = raw;
              }
            }
          } catch {
            // ignore
          }
          const quote = parsed?.detail;
          if (
            (response.status === 402 || response.status === 409 || response.status === 422) &&
            quote &&
            typeof quote === 'object'
          ) {
            set({
              isSending: false,
              billingModal: {
                open: true,
                quote: quote as BillingQuote,
                retry: {
                  kind: 'chat',
                  content,
                  options: { skipUserMessage: true, existingTurnId: turnId },
                },
              },
            });
            return;
          }
          throw new Error(
            `Erro no stream multi-modelo (HTTP ${response.status}): ${detail || response.statusText}`
          );
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        // 3. Read Loop
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          // SSE frames can arrive with LF or CRLF depending on proxy/runtime
          const frames = buffer.split(/\r?\n\r?\n/);
          buffer = frames.pop() || '';

          for (const frame of frames) {
            const frameLines = frame.split(/\r?\n/);
            let eventId: string | null = null;
            let retryMs: number | null = null;
            const dataLines: string[] = [];
            for (const frameLine of frameLines) {
              const trimmedLine = frameLine.trimStart();
              if (!trimmedLine) continue;
              if (trimmedLine.startsWith(':')) continue;
              if (trimmedLine.startsWith('id:')) {
                eventId = trimmedLine.slice(3).trim();
                continue;
              }
              if (trimmedLine.startsWith('retry:')) {
                const value = Number.parseInt(trimmedLine.slice(6).trim(), 10);
                if (!Number.isNaN(value)) retryMs = value;
                continue;
              }
              if (trimmedLine.startsWith('data:')) {
                const payload = trimmedLine.slice(5).trim();
                if (payload) dataLines.push(payload);
              }
            }
            if (retryMs !== null) retryDelayMs = retryMs;
            if (!dataLines.length) continue;
            const payload = dataLines.join('\n');

            try {
              const data = JSON.parse(payload);
              if (eventId) {
                lastEventId = eventId;
                const numericId = Number.parseInt(eventId, 10);
                if (!Number.isNaN(numericId)) {
                  if (lastAppliedEventId !== null && numericId <= lastAppliedEventId) {
                    continue;
                  }
                  lastAppliedEventId = numericId;
                }
              }
              if (data?.request_id && !streamRequestId) {
                streamRequestId = String(data.request_id);
              }

              if (data.type === 'search_started') {
                const query = data.query ? `: ${data.query}` : '';
                toast.info(`Buscando na web${query}...`);
                continue;
              }
              if (data.type === 'search_done') {
                const count = typeof data.count === 'number' ? data.count : 0;
                const cached = data.cached ? ' (cache)' : '';
                toast.info(`Pesquisa web concluída (${count} fontes${cached}).`);
                continue;
              }

              if (data.type === 'meta' && data.model && data.phase && typeof data.t === 'number') {
                updateModelMessage(data.model, (m) => ({
                  ...m,
                  metadata: {
                    ...(m.metadata || {}),
                    ...(data.phase === 'start' ? { stream_t0: data.t } : {}),
                    ...(data.phase === 'answer_start' ? { stream_t_answer_start: data.t } : {}),
                  },
                }));
                continue;
              }

              if (data.type === 'activity' && data.model && data.step) {
                const step = data.step || {};
                updateModelMessage(data.model, (m) => ({
                  ...m,
                  metadata: upsertModelActivityStep(
                    m.metadata,
                    {
                      id: step.id,
                      title: step.title || step.id,
                      status: step.status || 'running',
                      detail: step.detail || '',
                      tags: step.tags || [],
                      kind: step.kind,
                      attachments: step.attachments,
                      terms: step.terms,
                      sources: step.sources,
                    },
                    data.op
                  ),
                }));
                continue;
              }

              if (data.type === 'step.start' && data.model) {
                const rawName = String(data.step_name || '').trim();
                const rawId = String(data.step_id || '').trim();
                const nameLower = rawName.toLowerCase();
                const idLower = rawId.toLowerCase();
                const isWeb =
                  nameLower.includes('web') ||
                  nameLower.includes('internet') ||
                  idLower.includes('web_search') ||
                  idLower.includes('openai_web_search') ||
                  idLower.includes('pplx');
                updateModelMessage(data.model, (m) => ({
                  ...m,
                  metadata: upsertModelActivityStep(m.metadata, {
                    id: isWeb ? 'web_search' : (data.step_id || data.step_name || 'step'),
                    title: rawName || 'Processando',
                    status: 'running',
                    kind: isWeb ? 'web_search' : undefined,
                  }, 'add'),
                }));
                continue;
              }
              if (data.type === 'step.done' && data.model) {
                const rawId = String(data.step_id || '').trim();
                const idLower = rawId.toLowerCase();
                const isWeb =
                  idLower.includes('web_search') ||
                  idLower.includes('openai_web_search') ||
                  idLower.includes('pplx') ||
                  rawId === 'web_search';
                updateModelMessage(data.model, (m) => ({
                  ...m,
                  metadata: upsertModelActivityStep(m.metadata, {
                    id: isWeb ? 'web_search' : (data.step_id || 'step'),
                    title: data.step_name || 'Processando',
                    status: 'done',
                    kind: isWeb ? 'web_search' : undefined,
                  }, 'done'),
                }));
                continue;
              }
              if (data.type === 'step.add_query' && data.model) {
                const rawId = String(data.step_id || '').trim();
                const idLower = rawId.toLowerCase();
                const isWeb =
                  idLower.includes('web_search') ||
                  idLower.includes('openai_web_search') ||
                  idLower.includes('pplx') ||
                  rawId === 'web_search';
                updateModelMessage(data.model, (m) => ({
                  ...m,
                  metadata: upsertModelActivityStep(
                    m.metadata,
                    {
                      id: isWeb ? 'web_search' : (data.step_id || 'step'),
                      title: 'Pesquisa',
                      tags: data.query ? [String(data.query).slice(0, 100)] : [],
                      kind: isWeb ? 'web_search' : undefined,
                    },
                    'tags'
                  ),
                }));
                continue;
              }
              if (data.type === 'step.add_source' && data.model) {
                const src = data.source;
                const srcUrl =
                  (typeof src?.url === 'string' && src.url.trim()) ||
                  (typeof src?.source_url === 'string' && src.source_url.trim()) ||
                  '';
                if (srcUrl) {
                  updateModelMessage(data.model, (m) => {
                    const citations = Array.isArray(m.metadata?.citations) ? [...m.metadata.citations] : [];
                    const srcDocId =
                      String(src?.provenance?.doc_id || src?.doc_id || src?.document_id || '').trim();
                    const srcChunk =
                      String(src?.provenance?.chunk_uid || src?.chunk_uid || '').trim();
                    const srcChunkIndex = src?.provenance?.chunk_index ?? src?.chunk_index;
                    const srcPage =
                      src?.viewer?.source_page ?? src?.provenance?.page_number ?? src?.page_number ?? src?.source_page;
                    const sourceKey = srcDocId
                      ? `${srcDocId}|${String(srcChunkIndex ?? '')}|${String(srcPage ?? '')}|${srcChunk}`
                      : srcUrl.toLowerCase();
                    if (!citations.some((c: any) => {
                      const cDocId = String(c?.provenance?.doc_id || c?.doc_id || c?.document_id || '').trim();
                      const cChunk = String(c?.provenance?.chunk_uid || c?.chunk_uid || '').trim();
                      const cChunkIndex = c?.provenance?.chunk_index ?? c?.chunk_index;
                      const cPage =
                        c?.viewer?.source_page ?? c?.provenance?.page_number ?? c?.page_number ?? c?.source_page;
                      const cUrl =
                        (typeof c?.url === 'string' && c.url.trim()) ||
                        (typeof c?.source_url === 'string' && c.source_url.trim()) ||
                        '';
                      const candidateKey = cDocId
                        ? `${cDocId}|${String(cChunkIndex ?? '')}|${String(cPage ?? '')}|${cChunk}`
                        : cUrl.toLowerCase();
                      return candidateKey === sourceKey;
                    })) {
                      citations.push({
                        number: String(citations.length + 1),
                        title: src?.title || srcUrl || `Fonte ${citations.length + 1}`,
                        url: srcUrl || undefined,
                        quote:
                          (typeof src?.quote === 'string' && src.quote) ||
                          (typeof src?.highlight_text === 'string' && src.highlight_text) ||
                          undefined,
                        ...(src?.provenance && typeof src.provenance === 'object' ? { provenance: src.provenance } : {}),
                        ...(src?.viewer && typeof src.viewer === 'object' ? { viewer: src.viewer } : {}),
                        ...(src?.doc_id ? { doc_id: src.doc_id } : {}),
                        ...(src?.document_id ? { document_id: src.document_id } : {}),
                        ...(src?.chunk_uid ? { chunk_uid: src.chunk_uid } : {}),
                        ...(src?.chunk_index != null ? { chunk_index: src.chunk_index } : {}),
                        ...(src?.source_page != null ? { source_page: src.source_page } : {}),
                        ...(src?.source_url ? { source_url: src.source_url } : {}),
                      });
                    }
                    return {
                      ...m,
                      metadata: { ...(m.metadata || {}), citations },
                    };
                  });
                  updateModelMessage(data.model, (m) => ({
                    ...m,
                    metadata: upsertModelActivityStep(
                      m.metadata,
                      {
                        id: 'web_search',
                        title: 'Pesquisando na web',
                        kind: 'web_search',
                        sources: [{ url: srcUrl, title: src?.title ? String(src.title) : undefined }],
                      },
                      'update'
                    ),
                  }));
                }
                continue;
              }
              if (data.type === 'tool_call' && data.model && data.step_id) {
                const toolName = String(data.name || '').trim() || 'tool';
                const toolNameLower = toolName.toLowerCase();
                const delegatedModel =
                  String(
                    data?.arguments?.model ??
                    data?.args?.model ??
                    data?.input?.model ??
                    '',
                  ).trim();
                const isDelegateSubtask =
                  toolNameLower === 'delegate_subtask' || toolNameLower.includes('delegate');
                const stepId = isDelegateSubtask ? 'delegate_subtask' : String(data.step_id || 'mcp_tools');
                const stepTitle = isDelegateSubtask ? 'Delegado para Haiku' : 'MCP tools';
                const tagLabel = isDelegateSubtask
                  ? (delegatedModel || 'claude-4.5-haiku')
                  : toolName;
                const previewRaw = data.result_preview != null ? String(data.result_preview) : '';
                const preview = previewRaw ? previewRaw.slice(0, 220) : '';
                const line = `\n${toolName}${preview ? `: ${preview}` : ''}`;

                updateModelMessage(data.model, (m) => ({
                  ...m,
                  metadata: upsertModelActivityStep(
                    m.metadata,
                    {
                      id: stepId,
                      title: stepTitle,
                      tags: [tagLabel],
                      kind: isDelegateSubtask ? 'delegate_subtask' : undefined,
                    },
                    'tags'
                  ),
                }));
                updateModelMessage(data.model, (m) => ({
                  ...m,
                  metadata: upsertModelActivityStep(
                    m.metadata,
                    {
                      id: stepId,
                      title: stepTitle,
                      detail: line,
                      kind: isDelegateSubtask ? 'delegate_subtask' : undefined,
                    },
                    'append'
                  ),
                }));
                continue;
              }

              if (data.type === 'thinking' && data.model && data.delta && thinkingEnabledByModel[data.model]) {
                updateModelMessage(data.model, (m) => ({
                  ...m,
                  thinking: (m.thinking || '') + data.delta,
                  isThinking: true,
                  metadata: (() => {
                    const next: any = { ...(m.metadata || {}) };
                    const chunks = Array.isArray(next.thinkingChunks) ? [...next.thinkingChunks] : [];
                    const chunkType =
                      data?.thinking_type === 'summary' || data?.summary ? 'summary' : 'llm';
                    const last = chunks[chunks.length - 1];
                    if (last && last.type === chunkType) {
                      last.text = `${last.text || ''}${data.delta}`;
                    } else {
                      chunks.push({ type: chunkType, text: String(data.delta) });
                    }
                    next.thinkingChunks = chunks;
                    return next;
                  })(),
                }));
                continue;
              }

              if (data.type === 'token' && data.model && data.delta) {
                const now = Date.now();
                fullTextByModel[data.model] = (fullTextByModel[data.model] || '') + data.delta;
                updateModelMessage(data.model, (m) => ({
                  ...m,
                  content: (m.content || '') + data.delta,
                  // Once text starts, stop the "thinking" dots unless more thinking arrives.
                  isThinking: false,
                  metadata: (() => {
                    const next: any = { ...(m.metadata || {}) };
                    if (typeof next.stream_t0 !== 'number') next.stream_t0 = now;
                    if (typeof next.stream_t_answer_start !== 'number')
                      next.stream_t_answer_start = now;
                    return next;
                  })(),
                }));
                continue;
              }

              if (data.type === 'usage' && data.model && data.usage) {
                updateModelMessage(data.model, (m) => ({
                  ...m,
                  metadata: { ...(m.metadata || {}), token_usage: data.usage },
                }));
                continue;
              }

              if (data.type === 'done' && data.model && data.full_text) {
                const now = Date.now();
                fullTextByModel[data.model] = data.full_text;
                doneByModel.add(data.model);
                if (doneByModel.size >= targetModels.length) {
                  streamCompleted = true;
                }
                updateModelMessage(data.model, (m) => ({
                  ...m,
                  content: data.full_text,
                  thinking: thinkingEnabledByModel[data.model]
                    ? (() => {
                      const streamed = typeof m.thinking === 'string' ? m.thinking : '';
                      if (streamed.trim()) return streamed;
                      return typeof data.thinking === 'string' ? data.thinking : m.thinking;
                    })()
                    : undefined,
                  isThinking: false,
                  metadata: (() => {
                    const next: any = { ...(m.metadata || {}) };
                    if (typeof next.stream_t0 !== 'number') next.stream_t0 = now;
                    if (typeof next.stream_t_answer_start !== 'number')
                      next.stream_t_answer_start = now;
                    next.stream_t_done = now;
                    if (data.citations) next.citations = data.citations;
                    if (typeof data.execution_mode === 'string') {
                      next.execution_mode = data.execution_mode;
                    }
                    if (typeof data.execution_path === 'string') {
                      next.execution_path = data.execution_path;
                    }
                    if (typeof data.thinking_enabled === 'boolean') {
                      next.thinking_enabled = data.thinking_enabled;
                    }
                    return next;
                  })(),
                }));
                continue;
              }

              if (data.type === 'error') {
                toast.error(`Erro no modelo ${data.model}: ${data.error}`);
                if (data.model) {
                  doneByModel.add(data.model);
                  if (doneByModel.size >= targetModels.length) {
                    streamCompleted = true;
                  }
                  const now = Date.now();
                  updateModelMessage(data.model, (m) => ({
                    ...m,
                    isThinking: false,
                    metadata: (() => {
                      const next: any = { ...(m.metadata || {}) };
                      if (typeof next.stream_t0 !== 'number') next.stream_t0 = now;
                      if (typeof next.stream_t_done !== 'number') next.stream_t_done = now;
                      return next;
                    })(),
                  }));
                }
                continue;
              }
            } catch (e) {
              console.error('JSON parse error', e);
            }
          }
        }
        if (buffer.trim()) {
          const frameLines = buffer.split(/\r?\n/);
          let eventId: string | null = null;
          let retryMs: number | null = null;
          const dataLines: string[] = [];
          for (const frameLine of frameLines) {
            const trimmedLine = frameLine.trimStart();
            if (!trimmedLine) continue;
            if (trimmedLine.startsWith(':')) continue;
            if (trimmedLine.startsWith('id:')) {
              eventId = trimmedLine.slice(3).trim();
              continue;
            }
            if (trimmedLine.startsWith('retry:')) {
              const value = Number.parseInt(trimmedLine.slice(6).trim(), 10);
              if (!Number.isNaN(value)) retryMs = value;
              continue;
            }
            if (trimmedLine.startsWith('data:')) {
              const payload = trimmedLine.slice(5).trim();
              if (payload) dataLines.push(payload);
            }
          }
          if (retryMs !== null) retryDelayMs = retryMs;
          if (dataLines.length) {
            try {
              const data = JSON.parse(dataLines.join('\n'));
              if (eventId) {
                lastEventId = eventId;
                const numericId = Number.parseInt(eventId, 10);
                if (!Number.isNaN(numericId)) {
                  if (lastAppliedEventId !== null && numericId <= lastAppliedEventId) {
                    // skip duplicate
                  } else {
                    lastAppliedEventId = numericId;
                  }
                }
              }
              if (data?.request_id && !streamRequestId) {
                streamRequestId = String(data.request_id);
              }
            } catch (err) {
              console.error('JSON parse error (final)', err);
            }
          }
        }

        if (streamCompleted) break;
        if (!streamRequestId || !lastEventId || attempt >= maxReconnects) break;
        attempt += 1;
        await new Promise((resolve) => setTimeout(resolve, retryDelayMs));
      }

      // Gerar resposta consolidada (juiz) — somente se comparador estiver ligado e houver 2+ respostas
      try {
        const { showMultiModelComparator, autoConsolidate } = get();
        const candidates = targetModels
          .map((m) => ({ model: m, text: (fullTextByModel[m] || '').trim() }))
          .filter((c) => c.text.length > 0);

        if (showMultiModelComparator && autoConsolidate && candidates.length >= 2) {
          const mode: 'merge' | 'debate' = get().multiModelDeepDebate ? 'debate' : 'merge';
          const res = await apiClient.consolidateMultiChatTurn(currentChat.id, {
            message: content,
            candidates,
            mode,
          });
          const consolidatedMsg: Message = {
            id: nanoid(),
            role: 'assistant',
            content: res.content || '',
            timestamp: new Date().toISOString(),
            metadata: {
              model: mode === 'debate' ? 'Consolidado (Debate)' : 'Consolidado',
              turn_id: turnId,
              is_consolidated: true,
            },
          };

          set((state) => ({
            currentChat: state.currentChat
              ? {
                ...state.currentChat,
                messages: [...(state.currentChat.messages || []), consolidatedMsg],
              }
              : null,
          }));
        }
      } catch (e) {
        console.error('Consolidation error', e);
      }
    } catch (error) {
      console.error('Multi-model stream error', error);
      toast.error('Erro no stream multi-modelo');
    } finally {
      set({ isSending: false });
    }
  },

  // Claude Agent SDK Actions Implementation
  setIsAgentMode: (enabled: boolean) => {
    set({ isAgentMode: enabled });
    if (!enabled) {
      // Reset agent-specific state when leaving agent mode
      set({
        agentIterationCount: 0,
        pendingToolApproval: null,
        parallelExecution: null,
        lastToolCall: null,
        cogragTree: null,
        cogragStatus: 'idle' as CogRAGStatus,
      });
    }
  },

  compactConversation: async () => {
    const { currentChat, currentJobId } = get();
    if (!currentChat?.id) {
      toast.error('Nenhuma conversa ativa para compactar.');
      return;
    }

    try {
      const response = await apiClient.fetchWithAuth(
        `/chats/${currentChat.id}/compact`,
        {
          method: 'POST',
          body: JSON.stringify({
            job_id: currentJobId,
          }),
        }
      );

      if (!response.ok) {
        throw new Error('Failed to compact conversation');
      }

      const data = await response.json();
      set({
        lastSummaryId: data.summary_id || null,
        contextUsagePercent: data.new_percent || 0,
      });

      toast.success('Conversa compactada com sucesso.');
    } catch (error) {
      console.error('Error compacting conversation:', error);
      toast.error('Erro ao compactar conversa.');
    }
  },

  approveToolCall: async (approved: boolean, remember?: 'session' | 'always') => {
    const { currentChat, currentJobId, pendingToolApproval, toolPermissions } = get();
    if (!currentChat?.id || !pendingToolApproval) {
      toast.error('Nenhuma aprovação pendente.');
      return;
    }

    try {
      const response = await apiClient.fetchWithAuth(
        `/chats/${currentChat.id}/tool-approval`,
        {
          method: 'POST',
          body: JSON.stringify({
            job_id: currentJobId,
            tool: pendingToolApproval.tool,
            approved,
            remember,
          }),
        }
      );

      if (!response.ok) {
        throw new Error('Failed to send tool approval');
      }

      // Update tool permissions if user chose to remember
      if (remember) {
        const newPermission = approved ? 'allow' : 'deny';
        set({
          toolPermissions: {
            ...toolPermissions,
            [pendingToolApproval.tool]: newPermission,
          },
        });
      }

      // Clear pending approval
      set({ pendingToolApproval: null });

      toast.success(approved ? 'Ferramenta aprovada.' : 'Ferramenta negada.');
    } catch (error) {
      console.error('Error approving tool call:', error);
      toast.error('Erro ao enviar aprovação.');
    }
  },

  restoreCheckpoint: async (checkpointId: string) => {
    const { currentChat, currentJobId } = get();
    if (!currentChat?.id) {
      toast.error('Nenhuma conversa ativa.');
      return;
    }

    try {
      const response = await apiClient.fetchWithAuth(
        `/chats/${currentChat.id}/restore-checkpoint`,
        {
          method: 'POST',
          body: JSON.stringify({
            job_id: currentJobId,
            checkpoint_id: checkpointId,
          }),
        }
      );

      if (!response.ok) {
        throw new Error('Failed to restore checkpoint');
      }

      const data = await response.json();

      // Update checkpoints list - remove checkpoints after the restored one
      set((state) => {
        const idx = state.checkpoints.findIndex((cp) => cp.id === checkpointId);
        return {
          checkpoints: idx >= 0 ? state.checkpoints.slice(0, idx + 1) : state.checkpoints,
          contextUsagePercent: data.context_percent || state.contextUsagePercent,
        };
      });

      toast.success('Checkpoint restaurado.');
    } catch (error) {
      console.error('Error restoring checkpoint:', error);
      toast.error('Erro ao restaurar checkpoint.');
    }
  },

  setToolPermission: (tool: string, permission: 'allow' | 'deny' | 'ask') => {
    set((state) => ({
      toolPermissions: {
        ...state.toolPermissions,
        [tool]: permission,
      },
    }));
  },

  clearPendingToolApproval: () => {
    set({ pendingToolApproval: null });
  },
}));
