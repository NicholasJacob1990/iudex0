'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient, { apiBaseUrl } from '@/lib/api-client';
import { toast } from 'sonner';

// ============================================================================
// Types (frontend — kept as-is for component compatibility)
// ============================================================================

export type PlaybookArea =
  | 'trabalhista'
  | 'civil'
  | 'tributario'
  | 'empresarial'
  | 'ti'
  | 'ma'
  | 'imobiliario'
  | 'ambiental'
  | 'consumidor'
  | 'outro';

export type PlaybookStatus = 'rascunho' | 'ativo' | 'arquivado';

export type RuleSeverity = 'baixa' | 'media' | 'alta' | 'critica';

export type RejectAction = 'redline' | 'flag' | 'block' | 'suggest';

export type AnalysisResultStatus = 'compliant' | 'review' | 'non_compliant' | 'not_found';

export interface PlaybookRule {
  id: string;
  playbook_id: string;
  name: string;
  clause_type: string;
  severity: RuleSeverity;
  preferred_position: string;
  fallback_positions: string[];
  rejected_positions: string[];
  reject_action: RejectAction;
  guidance_notes: string;
  is_active: boolean;
  order: number;
  created_at: string;
  updated_at: string;
}

export interface PlaybookShareInfo {
  id: string;
  playbook_id: string;
  shared_with_user_id: string | null;
  shared_with_org_id: string | null;
  shared_with_email: string | null;
  permission: 'view' | 'edit' | 'admin';
  created_at: string;
}

export type PartyPerspective = 'contratante' | 'contratado' | 'neutro';

export const PARTY_PERSPECTIVE_LABELS: Record<PartyPerspective, string> = {
  contratante: 'Contratante',
  contratado: 'Contratado',
  neutro: 'Neutro',
};

export interface Playbook {
  id: string;
  name: string;
  description: string;
  area: PlaybookArea;
  scope: string;
  party_perspective: PartyPerspective;
  status: PlaybookStatus;
  is_template: boolean;
  is_shared: boolean;
  shared_with: string[];
  shares: PlaybookShareInfo[];
  rule_count: number;
  rules?: PlaybookRule[];
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface ClauseReviewInfo {
  reviewed_by: string;
  reviewed_at: string;
  status: 'approved' | 'rejected' | 'modified';
  notes: string;
}

export interface PlaybookAnalysisResult {
  rule_id: string;
  rule_name: string;
  clause_type: string;
  status: AnalysisResultStatus;
  original_text: string;
  explanation: string;
  suggested_redline: string;
  comment?: string;
  severity: RuleSeverity;
}

export interface PlaybookVersionEntry {
  id: string;
  playbook_id: string;
  version_number: number;
  changed_by: string;
  changed_by_email?: string;
  changes_summary: string;
  previous_rules: any[];
  created_at: string;
}

export interface PlaybookAnalysis {
  id: string;
  playbook_id: string;
  document_id: string;
  document_name: string;
  risk_score: number;
  results: PlaybookAnalysisResult[];
  reviewed_clauses?: Record<string, ClauseReviewInfo> | null;
  summary?: string;
  total_rules?: number;
  created_at: string;
  updated_at?: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
}

export interface PlaybookFilters {
  area?: PlaybookArea;
  status?: PlaybookStatus;
  scope?: string;
  search?: string;
}

// ============================================================================
// Area labels
// ============================================================================

export const AREA_LABELS: Record<PlaybookArea, string> = {
  trabalhista: 'Trabalhista',
  civil: 'Civil',
  tributario: 'Tributario',
  empresarial: 'Empresarial',
  ti: 'Tecnologia da Informacao',
  ma: 'Fusoes e Aquisicoes',
  imobiliario: 'Imobiliario',
  ambiental: 'Ambiental',
  consumidor: 'Consumidor',
  outro: 'Outro',
};

export const SEVERITY_LABELS: Record<RuleSeverity, string> = {
  baixa: 'Baixa',
  media: 'Media',
  alta: 'Alta',
  critica: 'Critica',
};

export const SEVERITY_COLORS: Record<RuleSeverity, string> = {
  baixa: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  media: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  alta: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  critica: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
};

export const STATUS_COLORS: Record<AnalysisResultStatus, string> = {
  compliant: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  review: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  non_compliant: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  not_found: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400',
};

export const STATUS_LABELS: Record<AnalysisResultStatus, string> = {
  compliant: 'Conforme',
  review: 'Revisar',
  non_compliant: 'Nao conforme',
  not_found: 'Nao encontrado',
};

export const REJECT_ACTION_LABELS: Record<RejectAction, string> = {
  redline: 'Redline',
  flag: 'Sinalizar',
  block: 'Bloquear',
  suggest: 'Sugerir alteracao',
};

// ============================================================================
// Backend ↔ Frontend mapping helpers
// ============================================================================

// Backend severity uses English; frontend uses Portuguese
const SEVERITY_BACKEND_TO_FRONTEND: Record<string, RuleSeverity> = {
  low: 'baixa',
  medium: 'media',
  high: 'alta',
  critical: 'critica',
};

const SEVERITY_FRONTEND_TO_BACKEND: Record<RuleSeverity, string> = {
  baixa: 'low',
  media: 'medium',
  alta: 'high',
  critica: 'critical',
};

// Backend uses "needs_review"; frontend uses "review"
const CLASSIFICATION_TO_STATUS: Record<string, AnalysisResultStatus> = {
  compliant: 'compliant',
  needs_review: 'review',
  non_compliant: 'non_compliant',
  not_found: 'not_found',
};

/**
 * Maps a backend PlaybookRuleResponse to the frontend PlaybookRule shape.
 * Backend fields: rule_name, action_on_reject, severity (English)
 * Frontend fields: name, reject_action, severity (Portuguese)
 */
function mapRuleFromBackend(raw: any): PlaybookRule {
  return {
    id: raw.id,
    playbook_id: raw.playbook_id,
    name: raw.rule_name ?? raw.name ?? '',
    clause_type: raw.clause_type,
    severity: SEVERITY_BACKEND_TO_FRONTEND[raw.severity] ?? (raw.severity as RuleSeverity),
    preferred_position: raw.preferred_position,
    fallback_positions: raw.fallback_positions ?? [],
    rejected_positions: raw.rejected_positions ?? [],
    reject_action: (raw.action_on_reject ?? raw.reject_action ?? 'flag') as RejectAction,
    guidance_notes: raw.guidance_notes ?? raw.description ?? '',
    is_active: raw.is_active ?? true,
    order: raw.order ?? 0,
    created_at: raw.created_at,
    updated_at: raw.updated_at,
  };
}

/**
 * Maps a backend PlaybookResponse to the frontend Playbook shape.
 * Backend fields: user_id, is_active (bool), rules_count, rules_items
 * Frontend fields: created_by, status (string enum), rule_count, rules
 */
function mapPlaybookFromBackend(raw: any): Playbook {
  // Derive frontend "status" from backend is_active
  let status: PlaybookStatus = 'ativo';
  if (raw.status) {
    status = raw.status as PlaybookStatus;
  } else if (raw.is_active === false) {
    status = 'arquivado';
  }

  const rules = raw.rules_items
    ? (raw.rules_items as any[]).map(mapRuleFromBackend)
    : raw.rules
      ? (raw.rules as any[]).map(mapRuleFromBackend)
      : undefined;

  const shares: PlaybookShareInfo[] = (raw.shares ?? []).map((s: any) => ({
    id: s.id,
    playbook_id: s.playbook_id,
    shared_with_user_id: s.shared_with_user_id ?? null,
    shared_with_org_id: s.shared_with_org_id ?? null,
    shared_with_email: s.shared_with_email ?? null,
    permission: s.permission ?? 'view',
    created_at: s.created_at,
  }));

  return {
    id: raw.id,
    name: raw.name,
    description: raw.description ?? '',
    area: (raw.area ?? 'outro') as PlaybookArea,
    scope: raw.scope ?? 'personal',
    party_perspective: (raw.party_perspective ?? 'neutro') as PartyPerspective,
    status,
    is_template: raw.is_template ?? false,
    is_shared: shares.length > 0,
    shared_with: shares.map((s) => s.shared_with_user_id ?? s.shared_with_org_id).filter(Boolean) as string[],
    shares,
    rule_count: raw.rules_count ?? raw.rule_count ?? 0,
    rules,
    created_by: raw.user_id ?? raw.created_by ?? '',
    created_at: raw.created_at,
    updated_at: raw.updated_at,
  };
}

/**
 * Maps frontend rule data to the backend PlaybookRuleCreate shape.
 */
function mapRuleToBackend(data: Omit<PlaybookRule, 'id' | 'created_at' | 'updated_at'>) {
  return {
    rule_name: data.name,
    clause_type: data.clause_type,
    severity: SEVERITY_FRONTEND_TO_BACKEND[data.severity] ?? data.severity,
    preferred_position: data.preferred_position,
    fallback_positions: data.fallback_positions,
    rejected_positions: data.rejected_positions,
    action_on_reject: data.reject_action,
    guidance_notes: data.guidance_notes,
    is_active: data.is_active,
    order: data.order,
  };
}

/**
 * Maps a backend ClauseAnalysisResult to frontend PlaybookAnalysisResult.
 */
function mapClauseResultFromBackend(raw: any): PlaybookAnalysisResult {
  return {
    rule_id: raw.rule_id,
    rule_name: raw.rule_name,
    clause_type: raw.clause_type,
    status: CLASSIFICATION_TO_STATUS[raw.classification] ?? (raw.status as AnalysisResultStatus) ?? 'not_found',
    original_text: raw.original_text ?? '',
    explanation: raw.explanation ?? '',
    suggested_redline: raw.suggested_redline ?? '',
    comment: raw.comment ?? undefined,
    severity: SEVERITY_BACKEND_TO_FRONTEND[raw.severity] ?? (raw.severity as RuleSeverity),
  };
}

// ============================================================================
// Hooks
// ============================================================================

export function usePlaybooks(filters?: PlaybookFilters) {
  return useQuery({
    queryKey: ['playbooks', filters],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters?.scope) params.set('scope', filters.scope);
      if (filters?.area) params.set('area', filters.area);
      if (filters?.search) params.set('search', filters.search);
      // Note: backend has is_template filter but not "status" directly.
      // We pass scope and area and handle status filtering client-side if needed.
      const qs = params.toString();
      const response = await apiClient.request(`/playbooks${qs ? `?${qs}` : ''}`);
      // Backend returns PlaybookListResponse { items, total, skip, limit }
      const items: any[] = response.items ?? response;
      let result = items.map(mapPlaybookFromBackend);

      // Client-side status filter (backend uses is_active bool, not a status enum)
      if (filters?.status) {
        result = result.filter((p) => p.status === filters.status);
      }

      return result;
    },
  });
}

export function usePlaybook(id: string | undefined) {
  return useQuery({
    queryKey: ['playbook', id],
    queryFn: async () => {
      // Backend returns PlaybookWithRulesResponse (includes rules_items and shares)
      const response = await apiClient.request(`/playbooks/${id}`);
      return mapPlaybookFromBackend(response);
    },
    enabled: !!id,
  });
}

export function useCreatePlaybook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: {
      name: string;
      description?: string;
      area: PlaybookArea;
      scope?: string;
      party_perspective?: PartyPerspective;
      from_template_id?: string;
      document_ids?: string[];
    }) => {
      // If from_template_id, use the duplicate endpoint instead
      if (data.from_template_id) {
        const response = await apiClient.request(
          `/playbooks/${data.from_template_id}/duplicate`,
          {
            method: 'POST',
            body: {
              name: data.name,
              scope: data.scope ?? 'personal',
            },
          }
        );
        return mapPlaybookFromBackend(response);
      }

      // Backend PlaybookCreate shape
      const body: Record<string, any> = {
        name: data.name,
        description: data.description,
        area: data.area,
        scope: data.scope ?? 'personal',
        party_perspective: data.party_perspective ?? 'neutro',
      };

      const response = await apiClient.request('/playbooks', {
        method: 'POST',
        body,
      });
      return mapPlaybookFromBackend(response);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      toast.success('Playbook criado com sucesso');
    },
    onError: () => {
      toast.error('Erro ao criar playbook');
    },
  });
}

export function useUpdatePlaybook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<Playbook> & { id: string }) => {
      // Map frontend fields to backend PlaybookUpdate
      const body: Record<string, any> = {};
      if (data.name !== undefined) body.name = data.name;
      if (data.description !== undefined) body.description = data.description;
      if (data.area !== undefined) body.area = data.area;
      if (data.scope !== undefined) body.scope = data.scope;
      if (data.is_template !== undefined) body.is_template = data.is_template;
      if (data.party_perspective !== undefined) body.party_perspective = data.party_perspective;
      // Map status to is_active
      if (data.status !== undefined) {
        body.is_active = data.status !== 'arquivado';
      }

      const response = await apiClient.request(`/playbooks/${id}`, {
        method: 'PUT',
        body,
      });
      return mapPlaybookFromBackend(response);
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      queryClient.invalidateQueries({ queryKey: ['playbook', data.id] });
      toast.success('Playbook atualizado');
    },
    onError: () => {
      toast.error('Erro ao atualizar playbook');
    },
  });
}

export function useDeletePlaybook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await apiClient.request(`/playbooks/${id}`, { method: 'DELETE' });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      toast.success('Playbook removido');
    },
    onError: () => {
      toast.error('Erro ao remover playbook');
    },
  });
}

export function usePlaybookRules(playbookId: string | undefined) {
  return useQuery({
    queryKey: ['playbook-rules', playbookId],
    queryFn: async () => {
      // The backend doesn't have a standalone /rules list endpoint;
      // rules come embedded in GET /playbooks/{id} (as rules_items).
      // We reuse the playbook detail endpoint.
      const response = await apiClient.request(`/playbooks/${playbookId}`);
      const rawRules: any[] = response.rules_items ?? response.rules ?? [];
      return rawRules.map(mapRuleFromBackend);
    },
    enabled: !!playbookId,
  });
}

export function useCreateRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: Omit<PlaybookRule, 'id' | 'created_at' | 'updated_at'>) => {
      const body = mapRuleToBackend(data);
      const response = await apiClient.request(
        `/playbooks/${data.playbook_id}/rules`,
        { method: 'POST', body }
      );
      return mapRuleFromBackend(response);
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['playbook-rules', data.playbook_id] });
      queryClient.invalidateQueries({ queryKey: ['playbook', data.playbook_id] });
      toast.success('Regra adicionada');
    },
    onError: () => {
      toast.error('Erro ao criar regra');
    },
  });
}

export function useUpdateRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...data }: Partial<PlaybookRule> & { id: string; playbook_id: string }) => {
      // Map frontend fields to backend PlaybookRuleUpdate
      const body: Record<string, any> = {};
      if (data.name !== undefined) body.rule_name = data.name;
      if (data.clause_type !== undefined) body.clause_type = data.clause_type;
      if (data.severity !== undefined) body.severity = SEVERITY_FRONTEND_TO_BACKEND[data.severity] ?? data.severity;
      if (data.preferred_position !== undefined) body.preferred_position = data.preferred_position;
      if (data.fallback_positions !== undefined) body.fallback_positions = data.fallback_positions;
      if (data.rejected_positions !== undefined) body.rejected_positions = data.rejected_positions;
      if (data.reject_action !== undefined) body.action_on_reject = data.reject_action;
      if (data.guidance_notes !== undefined) body.guidance_notes = data.guidance_notes;
      if (data.order !== undefined) body.order = data.order;
      if (data.is_active !== undefined) body.is_active = data.is_active;

      const response = await apiClient.request(
        `/playbooks/${data.playbook_id}/rules/${id}`,
        { method: 'PUT', body }
      );
      return mapRuleFromBackend(response);
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['playbook-rules', data.playbook_id] });
      queryClient.invalidateQueries({ queryKey: ['playbook', data.playbook_id] });
      toast.success('Regra atualizada');
    },
    onError: () => {
      toast.error('Erro ao atualizar regra');
    },
  });
}

export function useDeleteRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ ruleId, playbookId }: { ruleId: string; playbookId: string }) => {
      await apiClient.request(
        `/playbooks/${playbookId}/rules/${ruleId}`,
        { method: 'DELETE' }
      );
      return { ruleId, playbookId };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['playbook-rules', data.playbookId] });
      queryClient.invalidateQueries({ queryKey: ['playbook', data.playbookId] });
      toast.success('Regra removida');
    },
    onError: () => {
      toast.error('Erro ao remover regra');
    },
  });
}

export function useRunPlaybookAnalysis() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      playbookId,
      documentId,
    }: {
      playbookId: string;
      documentId: string;
    }) => {
      // POST /playbooks/{id}/analyze/{document_id}
      // Returns PlaybookAnalysisResponse { success, data: PlaybookAnalysisResult }
      const response = await apiClient.request(
        `/playbooks/${playbookId}/analyze/${documentId}`,
        { method: 'POST' }
      );

      const data = response.data ?? response;

      // Map backend PlaybookAnalysisSavedResponse to frontend PlaybookAnalysis
      const analysis: PlaybookAnalysis = {
        id: data.id ?? `analysis-${Date.now()}`,
        playbook_id: data.playbook_id,
        document_id: data.document_id,
        document_name: data.document_name ?? data.playbook_name ?? '',
        risk_score: data.risk_score ?? 0,
        results: (data.clauses ?? []).map(mapClauseResultFromBackend),
        reviewed_clauses: data.reviewed_clauses ?? null,
        summary: data.summary ?? '',
        total_rules: data.total_rules ?? 0,
        created_at: data.created_at ?? data.analyzed_at ?? new Date().toISOString(),
        updated_at: data.updated_at ?? '',
        status: 'completed',
      };
      return analysis;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['playbook-analyses', data.playbook_id] });
      toast.success('Analise concluida');
    },
    onError: () => {
      toast.error('Erro ao executar analise');
    },
  });
}

/**
 * Maps a backend PlaybookAnalysisSavedResponse to the frontend PlaybookAnalysis shape.
 */
function mapAnalysisFromBackend(raw: any): PlaybookAnalysis {
  return {
    id: raw.id,
    playbook_id: raw.playbook_id,
    document_id: raw.document_id,
    document_name: raw.document_name ?? raw.playbook_name ?? '',
    risk_score: raw.risk_score ?? 0,
    results: (raw.clauses ?? []).map(mapClauseResultFromBackend),
    reviewed_clauses: raw.reviewed_clauses ?? null,
    summary: raw.summary ?? '',
    total_rules: raw.total_rules ?? 0,
    created_at: raw.created_at ?? '',
    updated_at: raw.updated_at ?? '',
    status: 'completed',
  };
}

export function usePlaybookAnalyses(playbookId: string | undefined) {
  return useQuery({
    queryKey: ['playbook-analyses', playbookId],
    queryFn: async () => {
      const response = await apiClient.request(`/playbooks/${playbookId}/analyses`);
      const items: any[] = response.items ?? [];
      return items.map(mapAnalysisFromBackend);
    },
    enabled: !!playbookId,
  });
}

export function usePlaybookAnalysis(playbookId: string | undefined, analysisId: string | undefined) {
  return useQuery({
    queryKey: ['playbook-analysis', playbookId, analysisId],
    queryFn: async () => {
      const response = await apiClient.request(`/playbooks/${playbookId}/analyses/${analysisId}`);
      const data = response.data ?? response;
      return mapAnalysisFromBackend(data);
    },
    enabled: !!playbookId && !!analysisId,
  });
}

export function useReviewClauses() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      playbookId,
      analysisId,
      reviews,
    }: {
      playbookId: string;
      analysisId: string;
      reviews: Record<string, { status: string; notes?: string }>;
    }) => {
      const response = await apiClient.request(
        `/playbooks/${playbookId}/analyses/${analysisId}/review`,
        {
          method: 'PATCH',
          body: { reviews },
        }
      );
      const data = response.data ?? response;
      return mapAnalysisFromBackend(data);
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['playbook-analyses', data.playbook_id] });
      queryClient.invalidateQueries({ queryKey: ['playbook-analysis', data.playbook_id, data.id] });
      toast.success('Revisao salva com sucesso');
    },
    onError: () => {
      toast.error('Erro ao salvar revisao');
    },
  });
}

export function useGeneratePlaybook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      documentIds,
      area,
      name,
      description,
    }: {
      documentIds: string[];
      area: PlaybookArea;
      name?: string;
      description?: string;
    }) => {
      // POST /playbooks/generate
      // Body: PlaybookGenerateRequest { document_ids, name, area, description }
      // Returns PlaybookGenerateResponse { success, playbook_id, name, rules_count, message }
      const response = await apiClient.request('/playbooks/generate', {
        method: 'POST',
        body: {
          document_ids: documentIds,
          name: name ?? 'Playbook gerado por IA',
          area,
          description,
        },
      });
      return response as {
        success: boolean;
        playbook_id: string;
        name: string;
        rules_count: number;
        message: string;
      };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      toast.success('Playbook gerado com sucesso');
    },
    onError: () => {
      toast.error('Erro ao gerar playbook a partir dos contratos');
    },
  });
}

export function useImportPlaybook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      documentId,
      name,
      area,
      description,
    }: {
      documentId: string;
      name: string;
      area: PlaybookArea;
      description?: string;
    }) => {
      // POST /playbooks/import
      // Body: PlaybookImportRequest { document_id, name, area, description }
      // Returns PlaybookImportResponse { success, playbook_id, name, rules_count, message }
      const response = await apiClient.request('/playbooks/import', {
        method: 'POST',
        body: {
          document_id: documentId,
          name,
          area,
          description,
        },
      });
      return response as {
        success: boolean;
        playbook_id: string;
        name: string;
        rules_count: number;
        message: string;
      };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      toast.success(data.message || 'Playbook importado com sucesso');
    },
    onError: () => {
      toast.error('Erro ao importar playbook do documento');
    },
  });
}

export function useExtractWinningLanguage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      documentIds,
      name,
      area,
      description,
    }: {
      documentIds: string[];
      name: string;
      area: PlaybookArea;
      description?: string;
    }) => {
      // POST /playbooks/extract-from-contracts
      // Body: WinningLanguageExtractRequest { document_ids, name, area, description }
      // Returns WinningLanguageExtractResponse
      const response = await apiClient.request('/playbooks/extract-from-contracts', {
        method: 'POST',
        body: {
          document_ids: documentIds,
          name,
          area,
          description,
        },
      });
      return response as {
        success: boolean;
        playbook_id: string;
        name: string;
        rules_count: number;
        documents_processed: number;
        message: string;
      };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      toast.success(data.message || 'Winning language extraida com sucesso');
    },
    onError: () => {
      toast.error('Erro ao extrair winning language dos contratos');
    },
  });
}

// ============================================================================
// Import from uploaded document (direct file upload with preview)
// ============================================================================

export interface ExtractedRule {
  clause_type: string;
  rule_name: string;
  description: string | null;
  preferred_position: string;
  fallback_positions: string[];
  rejected_positions: string[];
  action_on_reject: string;
  severity: string;
  guidance_notes: string | null;
  order: number;
}

/**
 * Uploads a file (PDF/DOCX) and extracts playbook rules via AI for preview.
 * POST /playbooks/import-document (multipart/form-data)
 */
export function useExtractRulesFromUpload() {
  return useMutation({
    mutationFn: async ({
      file,
      area,
    }: {
      file: File;
      area: PlaybookArea;
    }) => {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('area', area);

      // Use axios directly for FormData (Content-Type must be multipart/form-data)
      const response = await apiClient.request('/playbooks/import-document', {
        method: 'POST',
        body: formData,
      });

      return response as {
        success: boolean;
        rules: ExtractedRule[];
        rules_count: number;
        message: string;
      };
    },
    onError: () => {
      toast.error('Erro ao extrair regras do documento');
    },
  });
}

/**
 * Confirms and creates a playbook from previously extracted rules.
 * POST /playbooks/import-document/confirm
 */
export function useConfirmImportFromUpload() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      name,
      area,
      description,
      rules,
    }: {
      name: string;
      area: PlaybookArea;
      description?: string;
      rules: ExtractedRule[];
    }) => {
      const response = await apiClient.request('/playbooks/import-document/confirm', {
        method: 'POST',
        body: {
          name,
          area,
          description,
          rules,
        },
      });

      return response as {
        success: boolean;
        playbook_id: string;
        name: string;
        rules_count: number;
        message: string;
      };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      toast.success(data.message || 'Playbook criado com sucesso');
    },
    onError: () => {
      toast.error('Erro ao criar playbook');
    },
  });
}

// ============================================================================
// Share hooks
// ============================================================================

export function useSharePlaybook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      playbookId,
      userEmail,
      permission,
      organizationWide,
    }: {
      playbookId: string;
      userEmail?: string;
      permission: 'view' | 'edit';
      organizationWide?: boolean;
    }) => {
      const body: Record<string, any> = {
        permission,
      };
      if (userEmail) body.user_email = userEmail;
      if (organizationWide) body.organization_wide = true;

      const response = await apiClient.request(
        `/playbooks/${playbookId}/share`,
        { method: 'POST', body }
      );
      return response as PlaybookShareInfo;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['playbook', variables.playbookId] });
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      toast.success('Playbook compartilhado');
    },
    onError: (error: any) => {
      const detail = error?.detail || error?.message || 'Erro ao compartilhar playbook';
      toast.error(detail);
    },
  });
}

export function useUpdateShare() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      playbookId,
      shareId,
      permission,
    }: {
      playbookId: string;
      shareId: string;
      permission: 'view' | 'edit';
    }) => {
      // The backend share endpoint updates permission if share already exists.
      // We re-post to the share endpoint — it will detect existing and update.
      // But we need the user_id or email. Instead, delete and re-create is complex.
      // Simpler: DELETE old share, POST new share.
      // Actually, let's read existing share info from cache and re-share.

      // Get current playbook data from cache
      const cachedPlaybook = queryClient.getQueryData<Playbook>(['playbook', playbookId]);
      const existingShare = cachedPlaybook?.shares?.find((s) => s.id === shareId);

      if (!existingShare) {
        throw new Error('Compartilhamento não encontrado');
      }

      // Delete old share
      await apiClient.request(
        `/playbooks/${playbookId}/share/${shareId}`,
        { method: 'DELETE' }
      );

      // Re-create with new permission
      const body: Record<string, any> = { permission };
      if (existingShare.shared_with_user_id) {
        body.shared_with_user_id = existingShare.shared_with_user_id;
      }
      if (existingShare.shared_with_org_id) {
        body.shared_with_org_id = existingShare.shared_with_org_id;
      }

      const response = await apiClient.request(
        `/playbooks/${playbookId}/share`,
        { method: 'POST', body }
      );
      return response as PlaybookShareInfo;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['playbook', variables.playbookId] });
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      toast.success('Permissão atualizada');
    },
    onError: () => {
      toast.error('Erro ao atualizar permissão');
    },
  });
}

export function useRemoveShare() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      playbookId,
      shareId,
    }: {
      playbookId: string;
      shareId: string;
    }) => {
      await apiClient.request(
        `/playbooks/${playbookId}/share/${shareId}`,
        { method: 'DELETE' }
      );
      return { playbookId, shareId };
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['playbook', variables.playbookId] });
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      toast.success('Compartilhamento removido');
    },
    onError: () => {
      toast.error('Erro ao remover compartilhamento');
    },
  });
}

export function getPlaybookExportUrl(playbookId: string, format: 'json' | 'pdf' | 'docx'): string {
  return `${apiBaseUrl}/playbooks/${playbookId}/export?format=${format}`;
}

// ============================================================================
// Playbook Prompt for /minuta integration
// ============================================================================

/**
 * Fetches the playbook prompt for agent injection in /minuta.
 * Calls GET /playbooks/{id}/prompt and returns the formatted prompt string.
 */
export function usePlaybookPrompt(playbookId: string | null | undefined) {
  return useQuery({
    queryKey: ['playbook-prompt', playbookId],
    queryFn: async () => {
      if (!playbookId) return null;

      const response = await apiClient.request(`/playbooks/${playbookId}/prompt`, {
        method: 'GET',
      });
      const data = response as { success: boolean; playbook_id: string; prompt: string };
      if (data?.success && data?.prompt) {
        return data.prompt;
      }
      return null;
    },
    enabled: !!playbookId,
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
  });
}

/**
 * Returns the list of active (non-draft) playbooks for the selector dropdown.
 */
export function useActivePlaybooks() {
  return usePlaybooks({ status: 'ativo' });
}

// ============================================================================
// Version History hooks
// ============================================================================

export function usePlaybookVersions(playbookId: string | undefined) {
  return useQuery({
    queryKey: ['playbook-versions', playbookId],
    queryFn: async () => {
      const response = await apiClient.request(`/playbooks/${playbookId}/versions`);
      const items: any[] = response.items ?? [];
      return items.map((item: any): PlaybookVersionEntry => ({
        id: item.id,
        playbook_id: item.playbook_id,
        version_number: item.version_number,
        changed_by: item.changed_by ?? item.user_id ?? '',
        changed_by_email: item.changed_by_email ?? item.user_email ?? undefined,
        changes_summary: item.changes_summary ?? item.summary ?? '',
        previous_rules: item.previous_rules ?? [],
        created_at: item.created_at,
      }));
    },
    enabled: !!playbookId,
  });
}
