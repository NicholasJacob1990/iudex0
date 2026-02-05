import { create } from 'zustand';
import {
  getPlaybooksForAddin,
  runPlaybook,
  applyRedlines as apiApplyRedlines,
  rejectRedlines as apiRejectRedlines,
  persistRedlineApplied,
  persistRedlineRejected,
  getRedlineStates,
  type PlaybookListItem,
  type RedlineData,
  type ClauseData,
  type PlaybookRunStats,
  type RunPlaybookResponse,
  type ClauseAnalysis,
  type InlineAnalyzeResponse,
  type RedlineStateData,
  analyzeInlineContent,
} from '@/api/client';
import { useDocumentStore } from './document-store';
import type { RedlineOperation } from '@/office/redline-engine';
import { getDocumentHash, checkDocumentModified } from '@/office/document-bridge';

// ── Gap 5: Sincronização entre abas ─────────────────────────────

const SYNC_KEY = 'iudex_redline_sync';
const TAB_ID_KEY = 'iudex_tab_id';
const POLLING_INTERVAL = 30000; // 30 segundos

/** Gera ou recupera um ID único para esta aba */
function getTabId(): string {
  let tabId = sessionStorage.getItem(TAB_ID_KEY);
  if (!tabId) {
    tabId = crypto.randomUUID();
    sessionStorage.setItem(TAB_ID_KEY, tabId);
  }
  return tabId;
}

interface SyncData {
  playbookRunId: string;
  redlineId: string;
  status: 'applied' | 'rejected';
  timestamp: number;
  tabId: string;
}

/** Broadcast de mudança de estado para outras abas via localStorage */
function broadcastStateChange(playbookRunId: string, redlineId: string, status: 'applied' | 'rejected'): void {
  const syncData: SyncData = {
    playbookRunId,
    redlineId,
    status,
    timestamp: Date.now(),
    tabId: getTabId(),
  };
  try {
    localStorage.setItem(SYNC_KEY, JSON.stringify(syncData));
  } catch {
    // localStorage pode não estar disponível em alguns contextos
  }
}

// ── Gap 6: Tracking de modificações ─────────────────────────────

interface RedlineApplication {
  redlineId: string;
  documentHashBefore: string;
  documentHashAfter: string;
  appliedAt: number;
}

type AnalysisState =
  | 'idle'
  | 'loading-playbooks'
  | 'analyzing'
  | 'results';

type FilterClassification =
  | 'all'
  | 'compliant'
  | 'needs_review'
  | 'non_compliant'
  | 'not_found'
  // Legacy classifications
  | 'conforme'
  | 'nao_conforme'
  | 'ausente'
  | 'parcial';

type FilterSeverity = 'all' | 'critical' | 'high' | 'medium' | 'low' | 'warning' | 'info';
type ReviewTab = 'all' | 'reviewed' | 'pending';

interface PlaybookStore {
  // State
  state: AnalysisState;
  playbooks: PlaybookListItem[];
  selectedPlaybook: PlaybookListItem | null;
  clauses: ClauseData[];
  redlines: RedlineData[];
  summary: string;
  stats: PlaybookRunStats;
  ooxmlPackage: string | null;
  error: string | null;

  // Filters
  filterClassification: FilterClassification;
  filterSeverity: FilterSeverity;
  reviewTab: ReviewTab;
  highlightedClauseId: string | null;

  // Applied/Rejected tracking
  appliedRedlines: Set<string>;
  rejectedRedlines: Set<string>;
  reviewedRedlines: Set<string>;

  // Gap 5: Sync state
  playbookRunId: string | null;

  // Gap 6: Document modification tracking
  documentHashBeforeAnalysis: string | null;
  documentHashAfterRedlines: string | null;
  documentModified: boolean;
  redlineApplications: RedlineApplication[];

  // Actions
  loadPlaybooks: () => Promise<void>;
  runPlaybookAnalysis: (playbook: PlaybookListItem) => Promise<void>;
  /** Legacy analyze — still supported for backwards compat */
  analyze: (playbook: PlaybookListItem) => Promise<void>;
  reset: () => void;
  setFilterClassification: (f: FilterClassification) => void;
  setFilterSeverity: (f: FilterSeverity) => void;
  setReviewTab: (tab: ReviewTab) => void;
  setHighlightedClause: (id: string | null) => void;
  markRedlineApplied: (redlineId: string) => Promise<void>;
  markRedlineRejected: (redlineId: string) => void;
  markRedlineReviewed: (redlineId: string) => void;

  // Gap 5: Sync actions
  syncRedlineState: (playbookRunId: string, redlineId: string, status: 'applied' | 'rejected') => void;
  initSyncListener: () => () => void;

  // Gap 6: Document modification actions
  checkDocumentModification: () => Promise<boolean>;
  updateDocumentHash: () => Promise<void>;
  clearModificationWarning: () => void;

  // Gap 4: State persistence actions
  loadSavedRedlineStates: (playbookRunId: string) => Promise<void>;
  persistAppliedState: (redlineId: string) => Promise<void>;
  persistRejectedState: (redlineId: string) => Promise<void>;

  // Computed
  filteredClauses: () => ClauseData[];
  pendingRedlines: () => RedlineData[];
  reviewProgress: () => { reviewed: number; total: number; percentage: number };
  toRedlineOperations: (clauseIds?: string[]) => RedlineOperation[];
  getRedlineForClause: (ruleId: string) => RedlineData | undefined;
}

const EMPTY_STATS: PlaybookRunStats = {
  total_rules: 0,
  compliant: 0,
  needs_review: 0,
  non_compliant: 0,
  not_found: 0,
  risk_score: 0,
  total_redlines: 0,
};

export const usePlaybookStore = create<PlaybookStore>((set, get) => ({
  state: 'idle',
  playbooks: [],
  selectedPlaybook: null,
  clauses: [],
  redlines: [],
  summary: '',
  stats: { ...EMPTY_STATS },
  ooxmlPackage: null,
  error: null,
  filterClassification: 'all',
  filterSeverity: 'all',
  reviewTab: 'all',
  highlightedClauseId: null,
  appliedRedlines: new Set(),
  rejectedRedlines: new Set(),
  reviewedRedlines: new Set(),

  // Gap 5: Sync state
  playbookRunId: null,

  // Gap 6: Document modification tracking
  documentHashBeforeAnalysis: null,
  documentHashAfterRedlines: null,
  documentModified: false,
  redlineApplications: [],

  loadPlaybooks: async () => {
    set({ state: 'loading-playbooks', error: null });
    try {
      const playbooks = await getPlaybooksForAddin();
      set({ playbooks, state: 'idle' });
    } catch {
      set({ error: 'Erro ao carregar playbooks', state: 'idle' });
    }
  },

  runPlaybookAnalysis: async (playbook: PlaybookListItem) => {
    set({
      selectedPlaybook: playbook,
      state: 'analyzing',
      error: null,
      clauses: [],
      redlines: [],
      summary: '',
      stats: { ...EMPTY_STATS },
      ooxmlPackage: null,
      appliedRedlines: new Set(),
      rejectedRedlines: new Set(),
      reviewedRedlines: new Set(),
      playbookRunId: null,
      documentHashBeforeAnalysis: null,
      documentHashAfterRedlines: null,
      documentModified: false,
      redlineApplications: [],
    });

    // Refresh document text
    await useDocumentStore.getState().loadFullText();
    const text = useDocumentStore.getState().fullText;

    if (!text.trim()) {
      set({ error: 'Documento vazio', state: 'idle' });
      return;
    }

    // Gap 6: Capturar hash do documento antes da análise
    let documentHash: string | null = null;
    try {
      documentHash = await getDocumentHash();
    } catch {
      // Hash não é crítico, continuar sem ele
    }

    try {
      const result: RunPlaybookResponse = await runPlaybook({
        playbook_id: playbook.id,
        document_content: text,
        document_format: 'text',
        include_ooxml: true,
      });

      if (!result.success) {
        set({
          error: result.error || 'Erro na analise',
          state: 'idle',
        });
        return;
      }

      // Usar o playbook_run_id do backend, ou gerar um local como fallback
      const playbookRunId = result.playbook_run_id || crypto.randomUUID();

      set({
        clauses: result.clauses,
        redlines: result.redlines,
        summary: result.summary,
        stats: result.stats,
        ooxmlPackage: result.ooxml_package || null,
        state: 'results',
        playbookRunId,
        documentHashBeforeAnalysis: documentHash,
        documentHashAfterRedlines: documentHash, // Inicialmente igual
      });

      // Gap 4: Tentar carregar estados salvos (se houver)
      if (playbookRunId) {
        get().loadSavedRedlineStates(playbookRunId);
      }
    } catch (err: unknown) {
      set({
        error: err instanceof Error ? err.message : 'Erro na analise',
        state: 'idle',
      });
    }
  },

  // Legacy analyze method — delegates to runPlaybookAnalysis
  analyze: async (playbook: PlaybookListItem) => {
    await get().runPlaybookAnalysis(playbook);
  },

  reset: () =>
    set({
      state: 'idle',
      selectedPlaybook: null,
      clauses: [],
      redlines: [],
      summary: '',
      stats: { ...EMPTY_STATS },
      ooxmlPackage: null,
      error: null,
      filterClassification: 'all',
      filterSeverity: 'all',
      reviewTab: 'all',
      highlightedClauseId: null,
      appliedRedlines: new Set(),
      rejectedRedlines: new Set(),
      reviewedRedlines: new Set(),
      playbookRunId: null,
      documentHashBeforeAnalysis: null,
      documentHashAfterRedlines: null,
      documentModified: false,
      redlineApplications: [],
    }),

  setFilterClassification: (f) => set({ filterClassification: f }),
  setFilterSeverity: (f) => set({ filterSeverity: f }),
  setReviewTab: (tab) => set({ reviewTab: tab }),
  setHighlightedClause: (id) => set({ highlightedClauseId: id }),

  markRedlineApplied: async (redlineId) => {
    const { playbookRunId, documentHashAfterRedlines, redlineApplications } = get();

    // Capturar hash antes da aplicação
    const hashBefore = documentHashAfterRedlines || '';

    const next = new Set(get().appliedRedlines);
    next.add(redlineId);
    const reviewed = new Set(get().reviewedRedlines);
    reviewed.add(redlineId);
    set({ appliedRedlines: next, reviewedRedlines: reviewed });

    // Gap 6: Capturar hash após aplicação e registrar
    try {
      const hashAfter = await getDocumentHash();
      const application: RedlineApplication = {
        redlineId,
        documentHashBefore: hashBefore,
        documentHashAfter: hashAfter,
        appliedAt: Date.now(),
      };
      set({
        documentHashAfterRedlines: hashAfter,
        redlineApplications: [...redlineApplications, application],
      });
    } catch {
      // Hash não é crítico
    }

    // Gap 5: Broadcast para outras abas
    if (playbookRunId) {
      broadcastStateChange(playbookRunId, redlineId, 'applied');
    }

    // Gap 4: Persistir estado no backend (fire and forget)
    get().persistAppliedState(redlineId);
  },

  markRedlineRejected: (redlineId) => {
    const { playbookRunId } = get();

    const next = new Set(get().rejectedRedlines);
    next.add(redlineId);
    const reviewed = new Set(get().reviewedRedlines);
    reviewed.add(redlineId);
    set({ rejectedRedlines: next, reviewedRedlines: reviewed });

    // Gap 5: Broadcast para outras abas
    if (playbookRunId) {
      broadcastStateChange(playbookRunId, redlineId, 'rejected');
    }

    // Gap 4: Persistir estado no backend (fire and forget)
    get().persistRejectedState(redlineId);
  },

  markRedlineReviewed: (redlineId) => {
    const reviewed = new Set(get().reviewedRedlines);
    reviewed.add(redlineId);
    set({ reviewedRedlines: reviewed });
  },

  filteredClauses: () => {
    const { clauses, filterClassification, filterSeverity, reviewTab, reviewedRedlines } = get();
    return clauses.filter((c) => {
      // Classification filter
      if (filterClassification !== 'all' && c.classification !== filterClassification)
        return false;
      // Severity filter
      if (filterSeverity !== 'all' && c.severity !== filterSeverity) return false;
      // Review tab filter
      if (reviewTab === 'reviewed' && c.redline_id && !reviewedRedlines.has(c.redline_id))
        return false;
      if (reviewTab === 'pending' && c.redline_id && reviewedRedlines.has(c.redline_id))
        return false;
      return true;
    });
  },

  pendingRedlines: () => {
    const { redlines, appliedRedlines, rejectedRedlines } = get();
    return redlines.filter(
      (r) => !appliedRedlines.has(r.redline_id) && !rejectedRedlines.has(r.redline_id)
    );
  },

  reviewProgress: () => {
    const { redlines, reviewedRedlines } = get();
    const total = redlines.length;
    const reviewed = [...reviewedRedlines].filter((id) =>
      redlines.some((r) => r.redline_id === id)
    ).length;
    return {
      reviewed,
      total,
      percentage: total > 0 ? Math.round((reviewed / total) * 100) : 0,
    };
  },

  toRedlineOperations: (clauseIds?: string[]) => {
    const { clauses, redlines } = get();
    const target = clauseIds
      ? clauses.filter((c) => c.redline_id && clauseIds.includes(c.redline_id))
      : clauses.filter(
          (c) =>
            c.classification !== 'compliant' &&
            c.classification !== 'conforme' &&
            c.suggested_redline
        );

    return target.map((c) => {
      const redline = redlines.find((r) => r.redline_id === c.redline_id);
      return {
        id: c.redline_id || c.rule_id,
        action: 'replace' as const,
        originalText: c.original_text || '',
        suggestedText: c.suggested_redline,
        comment: c.explanation,
        severity: (c.severity === 'critical' || c.severity === 'high'
          ? 'critical'
          : c.severity === 'medium' || c.severity === 'warning'
            ? 'warning'
            : 'info') as 'critical' | 'warning' | 'info',
        ruleName: c.rule_name,
        ooxml: redline?.ooxml,
      };
    });
  },

  getRedlineForClause: (ruleId: string) => {
    return get().redlines.find((r) => r.rule_id === ruleId);
  },

  // ── Gap 5: Sincronização entre abas ─────────────────────────────

  syncRedlineState: (playbookRunId, redlineId, status) => {
    const { playbookRunId: currentRunId } = get();

    // Só sincronizar se for o mesmo playbook run
    if (currentRunId !== playbookRunId) return;

    if (status === 'applied') {
      const next = new Set(get().appliedRedlines);
      next.add(redlineId);
      const reviewed = new Set(get().reviewedRedlines);
      reviewed.add(redlineId);
      set({ appliedRedlines: next, reviewedRedlines: reviewed });
    } else if (status === 'rejected') {
      const next = new Set(get().rejectedRedlines);
      next.add(redlineId);
      const reviewed = new Set(get().reviewedRedlines);
      reviewed.add(redlineId);
      set({ rejectedRedlines: next, reviewedRedlines: reviewed });
    }
  },

  initSyncListener: () => {
    const tabId = getTabId();
    let pollingInterval: ReturnType<typeof setInterval> | null = null;

    // Listener para storage events (mudanças de outras abas)
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key !== SYNC_KEY || !e.newValue) return;

      try {
        const data: SyncData = JSON.parse(e.newValue);
        // Ignorar eventos da própria aba
        if (data.tabId === tabId) return;

        get().syncRedlineState(data.playbookRunId, data.redlineId, data.status);
      } catch {
        // JSON inválido, ignorar
      }
    };

    window.addEventListener('storage', handleStorageChange);

    // Polling fallback para casos onde storage event não funciona
    pollingInterval = setInterval(() => {
      const { playbookRunId, documentHashAfterRedlines } = get();
      if (!playbookRunId || !documentHashAfterRedlines) return;

      // Verificar se documento foi modificado externamente
      get().checkDocumentModification();
    }, POLLING_INTERVAL);

    // Retornar função de cleanup
    return () => {
      window.removeEventListener('storage', handleStorageChange);
      if (pollingInterval) {
        clearInterval(pollingInterval);
      }
    };
  },

  // ── Gap 6: Tracking de modificações no documento ────────────────

  checkDocumentModification: async () => {
    const { documentHashAfterRedlines } = get();

    if (!documentHashAfterRedlines) {
      return false;
    }

    try {
      const modified = await checkDocumentModified(documentHashAfterRedlines);
      if (modified !== get().documentModified) {
        set({ documentModified: modified });
      }
      return modified;
    } catch {
      return false;
    }
  },

  updateDocumentHash: async () => {
    try {
      const hash = await getDocumentHash();
      set({
        documentHashAfterRedlines: hash,
        documentModified: false,
      });
    } catch {
      // Hash não é crítico
    }
  },

  clearModificationWarning: () => {
    set({ documentModified: false });
  },

  // ── Gap 4: Persistencia de Estado de Redlines ─────────────────

  loadSavedRedlineStates: async (playbookRunId: string) => {
    try {
      const response = await getRedlineStates(playbookRunId);
      if (!response.success || !response.states.length) {
        return;
      }

      const appliedRedlines = new Set<string>();
      const rejectedRedlines = new Set<string>();
      const reviewedRedlines = new Set<string>();

      for (const state of response.states) {
        if (state.status === 'applied') {
          appliedRedlines.add(state.redline_id);
          reviewedRedlines.add(state.redline_id);
        } else if (state.status === 'rejected') {
          rejectedRedlines.add(state.redline_id);
          reviewedRedlines.add(state.redline_id);
        }
      }

      set({
        appliedRedlines,
        rejectedRedlines,
        reviewedRedlines,
      });

      console.log(
        `[PlaybookStore] Restaurados ${response.states.length} estados de redlines`,
        response.stats
      );
    } catch (error) {
      console.warn('[PlaybookStore] Erro ao carregar estados salvos:', error);
      // Nao e critico, continuar sem estados salvos
    }
  },

  persistAppliedState: async (redlineId: string) => {
    const { playbookRunId } = get();
    if (!playbookRunId) return;

    try {
      await persistRedlineApplied(playbookRunId, redlineId);
    } catch (error) {
      console.warn('[PlaybookStore] Erro ao persistir estado applied:', error);
      // Nao e critico, o estado local ja foi atualizado
    }
  },

  persistRejectedState: async (redlineId: string) => {
    const { playbookRunId } = get();
    if (!playbookRunId) return;

    try {
      await persistRedlineRejected(playbookRunId, redlineId);
    } catch (error) {
      console.warn('[PlaybookStore] Erro ao persistir estado rejected:', error);
      // Nao e critico, o estado local ja foi atualizado
    }
  },
}));
