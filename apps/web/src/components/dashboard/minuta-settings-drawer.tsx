'use client';

import { useMemo, useState } from 'react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from '@/components/ui/accordion';
import { RichTooltip } from '@/components/ui/rich-tooltip';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { Users, Scale, Sparkles } from 'lucide-react';
import { toast } from 'sonner';

// ---------------------------------------------------------------------------
// Constants & helpers
// ---------------------------------------------------------------------------

const MAX_ROLE_MODELS = 3;

type HilSectionPolicy = 'none' | 'optional' | 'required';

const QUALITY_PROFILE_SPECS = [
  {
    id: 'rapido',
    label: 'Rápido',
    description: '1 rodada • meta seção: inativa, final ≥ 9.0 • HIL só no final.',
    targetSectionScore: 8.5,
    targetFinalScore: 9.0,
    maxRounds: 1,
    hilSectionPolicy: 'none' as HilSectionPolicy,
    hilFinalRequired: true,
  },
  {
    id: 'padrao',
    label: 'Padrão',
    description: '2 rodadas • meta seção ≥ 9.0, final ≥ 9.4 • HIL por seção opcional + final.',
    targetSectionScore: 9.0,
    targetFinalScore: 9.4,
    maxRounds: 2,
    hilSectionPolicy: 'optional' as HilSectionPolicy,
    hilFinalRequired: true,
  },
  {
    id: 'rigoroso',
    label: 'Rigoroso',
    description: '4 rodadas • meta seção ≥ 9.4, final ≥ 9.8 • HIL por seção obrigatório + final obrigatório.',
    targetSectionScore: 9.4,
    targetFinalScore: 9.8,
    maxRounds: 4,
    hilSectionPolicy: 'required' as HilSectionPolicy,
    hilFinalRequired: true,
  },
  {
    id: 'auditoria',
    label: 'Auditoria',
    description: '6 rodadas • meta seção ≥ 9.6, final ≥ 10.0 • HIL por seção obrigatório + final obrigatório.',
    targetSectionScore: 9.6,
    targetFinalScore: 10.0,
    maxRounds: 6,
    hilSectionPolicy: 'required' as HilSectionPolicy,
    hilFinalRequired: true,
  },
] as const;

type QualityProfileSpec = (typeof QUALITY_PROFILE_SPECS)[number];

const formatScoreLabel = (value: number) => value.toFixed(1);
const formatRoundsLabel = (value: number) => `${value} rodada${value === 1 ? '' : 's'}`;
const formatHilPolicyLabel = (policy: HilSectionPolicy, finalRequired: boolean) => {
  if (policy === 'none') return finalRequired ? 'HIL só no final.' : 'Sem HIL.';
  if (policy === 'optional')
    return finalRequired ? 'HIL por seção opcional + final.' : 'HIL por seção opcional.';
  return finalRequired ? 'HIL por seção obrigatório + final.' : 'HIL por seção obrigatório.';
};

const parseOptionalNumber = (value: string) => {
  const n = Number(String(value).replace(',', '.'));
  return Number.isFinite(n) ? n : null;
};
const clampScore = (v: number | null) => (v === null ? null : Math.max(0, Math.min(10, v)));
const clampRounds = (v: number | null) => (v === null ? null : Math.max(1, Math.min(6, Math.floor(v))));
const clampStyleRounds = (v: number | null) => (v === null ? null : Math.max(0, Math.min(6, Math.floor(v))));
const clampRetry = (v: number | null) => (v === null ? null : Math.max(0, Math.min(5, Math.floor(v))));
const clampCragScore = (v: number | null) => (v === null ? null : Math.max(0, Math.min(1, v)));
const clampTemperature = (v: number | null) => (v === null ? null : Math.max(0, Math.min(1, v)));
const clampDivergenceHilRounds = (v: number | null) => (v === null ? null : Math.max(1, Math.min(5, Math.floor(v))));
const clampRecursionLimit = (v: number | null) => (v === null ? null : Math.max(20, Math.min(500, Math.floor(v))));

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface MinutaSettingsDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;

  // Mode
  mode: 'individual' | 'multi-agent';
  chatMode: string;
  onSetChatMode: (mode: 'standard' | 'multi-model') => void;
  chatPersonality: string;
  setChatPersonality: (p: any) => void;
  queryMode?: 'auto' | 'edit' | 'answer';
  setQueryMode?: (mode: 'auto' | 'edit' | 'answer') => void;

  // Document
  documentType: string;
  setDocumentType: (type: string) => void;
  minPages: number;
  maxPages: number;
  setPageRange: (range: { minPages?: number; maxPages?: number }) => void;
  resetPageRange: () => void;
  formattingOptions: any;
  setFormattingOptions: (opts: any) => void;

  // Quality
  reasoningLevel: 'low' | 'medium' | 'high';
  setReasoningLevel: (level: 'low' | 'medium' | 'high') => void;
  effortLevel: number;
  setEffortLevel: (level: any) => void;
  creativityMode: string;
  setCreativityMode: (mode: any) => void;
  temperatureOverride: number | null;
  setTemperatureOverride: (t: number | null) => void;
  qualityProfile: string;
  setQualityProfile: (id: any) => void;
  qualityTargetSectionScore: number | null;
  setQualityTargetSectionScore: (v: number | null) => void;
  qualityTargetFinalScore: number | null;
  setQualityTargetFinalScore: (v: number | null) => void;
  qualityMaxRounds: number | null;
  setQualityMaxRounds: (v: number | null) => void;

  // Research
  researchPolicy: string;
  setResearchPolicy: (p: any) => void;
  webSearch: boolean;
  setWebSearch: (v: boolean) => void;
  denseResearch: boolean;
  setDenseResearch: (v: boolean) => void;
  searchMode: string;
  setSearchMode: (m: any) => void;
  multiQuery: boolean;
  setMultiQuery: (v: boolean) => void;
  breadthFirst: boolean;
  setBreadthFirst: (v: boolean) => void;
  deepResearchProvider: string;
  setDeepResearchProvider: (p: any) => void;
  deepResearchModel: string;
  setDeepResearchModel: (m: string) => void;
  webSearchModel: string;
  setWebSearchModel: (m: string) => void;
  auditMode: string;
  setAuditMode: (m: any) => void;

  // Models
  selectedModel: string;
  setSelectedModel: (m: string) => void;
  agentStrategistModel: string;
  agentDrafterModels: string[];
  setAgentDrafterModels: (m: string[]) => void;
  agentReviewerModels: string[];
  setAgentReviewerModels: (m: string[]) => void;
  selectedModels: string[];
  setSelectedModels: (m: string[]) => void;
  setShowMultiModelComparator: (v: boolean) => void;
  baseModelOptions: Array<{ id: string; label: string; provider: string; capabilities: string[] }>;
  agentModelOptions: Array<{ id: string; label: string; provider: string; capabilities: string[] }>;

  // Control (HIL)
  hilOutlineEnabled: boolean;
  setHilOutlineEnabled: (v: boolean) => void;
  autoApproveHil: boolean;
  setAutoApproveHil: (v: boolean) => void;
  chatOutlineReviewEnabled: boolean;
  setChatOutlineReviewEnabled: (v: boolean) => void;
  hilSectionPolicyOverride: string | null;
  setHilSectionPolicyOverride: (v: any) => void;
  hilFinalRequiredOverride: boolean | null;
  setHilFinalRequiredOverride: (v: boolean | null) => void;

  // Advanced
  qualityMaxFinalReviewLoops: number | null;
  setQualityMaxFinalReviewLoops: (v: number | null) => void;
  qualityStyleRefineMaxRounds: number | null;
  setQualityStyleRefineMaxRounds: (v: number | null) => void;
  qualityMaxResearchVerifierAttempts: number | null;
  setQualityMaxResearchVerifierAttempts: (v: number | null) => void;
  qualityMaxRagRetries: number | null;
  setQualityMaxRagRetries: (v: number | null) => void;
  qualityRagRetryExpandScope: boolean | null;
  setQualityRagRetryExpandScope: (v: boolean | null) => void;
  recursionLimitOverride: number | null;
  setRecursionLimitOverride: (v: number | null) => void;
  strictDocumentGateOverride: boolean | null;
  setStrictDocumentGateOverride: (v: boolean | null) => void;
  forceGranularDebate: boolean;
  setForceGranularDebate: (v: boolean) => void;
  maxDivergenceHilRounds: number | null;
  setMaxDivergenceHilRounds: (v: number | null) => void;
  cragMinBestScoreOverride: number | null;
  setCragMinBestScoreOverride: (v: number | null) => void;
  cragMinAvgScoreOverride: number | null;
  setCragMinAvgScoreOverride: (v: number | null) => void;

  // Checklist
  documentChecklist: Array<{ label: string; critical: boolean }>;
  setDocumentChecklist: (items: Array<{ label: string; critical: boolean }>) => void;
}

// ---------------------------------------------------------------------------
// Reusable pill button
// ---------------------------------------------------------------------------

function Pill({
  active,
  onClick,
  disabled,
  variant = 'indigo',
  children,
  className: extraClassName,
}: {
  active: boolean;
  onClick: () => void;
  disabled?: boolean;
  variant?: 'indigo' | 'rose';
  children: React.ReactNode;
  className?: string;
}) {
  const selected =
    variant === 'rose'
      ? 'border-rose-300 bg-rose-500/15 text-rose-700'
      : 'border-indigo-300 bg-indigo-500/15 text-indigo-700';
  const unselected = 'border-slate-200 text-slate-500 hover:text-slate-700 hover:bg-slate-50';

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
        active ? selected : unselected,
        disabled && 'opacity-50 cursor-not-allowed',
        extraClassName,
      )}
    >
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Reusable section label
// ---------------------------------------------------------------------------

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] font-semibold uppercase text-indigo-700/70">{children}</div>
  );
}

function SubLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] font-semibold uppercase text-slate-500">{children}</div>
  );
}

// ---------------------------------------------------------------------------
// Number input helper
// ---------------------------------------------------------------------------

function NumInput({
  value,
  onChange,
  placeholder,
  min,
  max,
  step,
  disabled,
}: {
  value: number | null;
  onChange: (v: number | null) => void;
  placeholder?: string;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
}) {
  return (
    <input
      type="number"
      min={min}
      max={max}
      step={step}
      disabled={disabled}
      className="w-full text-xs h-8 rounded-lg border border-indigo-200/60 bg-white px-2.5 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition disabled:opacity-50"
      placeholder={placeholder}
      value={value ?? ''}
      onChange={(e) => onChange(parseOptionalNumber(e.target.value))}
    />
  );
}

// ---------------------------------------------------------------------------
// Checkbox helper
// ---------------------------------------------------------------------------

function Check({
  checked,
  onChange,
  disabled,
  children,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className={cn('flex items-center gap-2 text-xs cursor-pointer', disabled && 'opacity-60 cursor-not-allowed')}>
      <input
        type="checkbox"
        className="rounded border-indigo-300 text-indigo-600 focus:ring-indigo-500/20 h-3.5 w-3.5"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="text-slate-600">{children}</span>
    </label>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function MinutaSettingsDrawer(props: MinutaSettingsDrawerProps) {
  const {
    open,
    onOpenChange,
    mode,
    chatMode,
    onSetChatMode,
    chatPersonality,
    setChatPersonality,
    queryMode,
    setQueryMode,
    documentType,
    setDocumentType,
    minPages,
    maxPages,
    setPageRange,
    resetPageRange,
    formattingOptions,
    setFormattingOptions,
    reasoningLevel,
    setReasoningLevel,
    effortLevel,
    setEffortLevel,
    creativityMode,
    setCreativityMode,
    temperatureOverride,
    setTemperatureOverride,
    qualityProfile,
    setQualityProfile,
    qualityTargetSectionScore,
    setQualityTargetSectionScore,
    qualityTargetFinalScore,
    setQualityTargetFinalScore,
    qualityMaxRounds,
    setQualityMaxRounds,
    researchPolicy,
    setResearchPolicy,
    webSearch,
    setWebSearch,
    denseResearch,
    setDenseResearch,
    searchMode,
    setSearchMode,
    multiQuery,
    setMultiQuery,
    breadthFirst,
    setBreadthFirst,
    deepResearchProvider,
    setDeepResearchProvider,
    deepResearchModel,
    setDeepResearchModel,
    webSearchModel,
    setWebSearchModel,
    auditMode,
    setAuditMode,
    selectedModel,
    setSelectedModel,
    agentStrategistModel,
    agentDrafterModels,
    setAgentDrafterModels,
    agentReviewerModels,
    setAgentReviewerModels,
    selectedModels,
    setSelectedModels,
    setShowMultiModelComparator,
    baseModelOptions,
    agentModelOptions,
    hilOutlineEnabled,
    setHilOutlineEnabled,
    autoApproveHil,
    setAutoApproveHil,
    chatOutlineReviewEnabled,
    setChatOutlineReviewEnabled,
    hilSectionPolicyOverride,
    setHilSectionPolicyOverride,
    hilFinalRequiredOverride,
    setHilFinalRequiredOverride,
    qualityMaxFinalReviewLoops,
    setQualityMaxFinalReviewLoops,
    qualityStyleRefineMaxRounds,
    setQualityStyleRefineMaxRounds,
    qualityMaxResearchVerifierAttempts,
    setQualityMaxResearchVerifierAttempts,
    qualityMaxRagRetries,
    setQualityMaxRagRetries,
    qualityRagRetryExpandScope,
    setQualityRagRetryExpandScope,
    recursionLimitOverride,
    setRecursionLimitOverride,
    strictDocumentGateOverride,
    setStrictDocumentGateOverride,
    forceGranularDebate,
    setForceGranularDebate,
    maxDivergenceHilRounds,
    setMaxDivergenceHilRounds,
    cragMinBestScoreOverride,
    setCragMinBestScoreOverride,
    cragMinAvgScoreOverride,
    setCragMinAvgScoreOverride,
    documentChecklist,
    setDocumentChecklist,
  } = props;

  // Local state for checklist textareas
  const [criticalChecklistText, setCriticalChecklistText] = useState(() =>
    documentChecklist
      .filter((i) => i.critical)
      .map((i) => i.label)
      .join('\n'),
  );
  const [nonCriticalChecklistText, setNonCriticalChecklistText] = useState(() =>
    documentChecklist
      .filter((i) => !i.critical)
      .map((i) => i.label)
      .join('\n'),
  );

  // Derived values
  const selectedProfileSpec =
    QUALITY_PROFILE_SPECS.find((p) => p.id === qualityProfile) ?? QUALITY_PROFILE_SPECS[1];

  const effectiveHilSectionPolicy =
    (hilSectionPolicyOverride as HilSectionPolicy | null) ?? selectedProfileSpec.hilSectionPolicy;

  const hilSectionPolicyMode =
    hilSectionPolicyOverride === null ? 'auto' : hilSectionPolicyOverride;

  const hilFinalRequiredMode =
    hilFinalRequiredOverride === null ? 'auto' : hilFinalRequiredOverride ? 'on' : 'off';

  const expandScopeMode =
    qualityRagRetryExpandScope === null ? 'auto' : qualityRagRetryExpandScope ? 'on' : 'off';

  const canExpandScope = auditMode !== 'sei_only';

  const hasQualityOverrides =
    qualityTargetSectionScore != null ||
    qualityTargetFinalScore != null ||
    qualityMaxRounds != null ||
    qualityMaxFinalReviewLoops != null ||
    hilSectionPolicyOverride != null ||
    hilFinalRequiredOverride != null ||
    maxDivergenceHilRounds != null ||
    forceGranularDebate;

  const qualityProfileMeta = hasQualityOverrides
    ? 'Valores ajustados pelos overrides abaixo.'
    : undefined;

  const buildProfileDescription = (profile: QualityProfileSpec) => {
    if (!hasQualityOverrides) return profile.description;
    const tss = qualityTargetSectionScore ?? profile.targetSectionScore;
    const tfs = qualityTargetFinalScore ?? profile.targetFinalScore;
    const mr = qualityMaxRounds ?? profile.maxRounds;
    const hp = (hilSectionPolicyOverride as HilSectionPolicy | null) ?? profile.hilSectionPolicy;
    const hfr = hilFinalRequiredOverride ?? profile.hilFinalRequired;
    const extras: string[] = [];
    if (qualityMaxFinalReviewLoops != null) extras.push(`refino final: ${Math.floor(qualityMaxFinalReviewLoops)}`);
    if (maxDivergenceHilRounds != null) extras.push(`divergência HIL: ${Math.floor(maxDivergenceHilRounds)}`);
    if (forceGranularDebate) extras.push('granular: on');
    const sectionLabel =
      hp === 'none' ? 'meta seção: inativa' : `meta seção ≥ ${formatScoreLabel(tss)}`;
    const base = `${formatRoundsLabel(mr)} • ${sectionLabel}, final ≥ ${formatScoreLabel(tfs)} • ${formatHilPolicyLabel(hp, hfr)}`;
    return extras.length > 0 ? `${base} • ${extras.join(' • ')}` : base;
  };

  const sectionScoreMeta =
    effectiveHilSectionPolicy === 'none' ? 'Sem efeito no perfil atual.' : undefined;

  const getModelLabel = (modelId: string) => {
    const found =
      agentModelOptions.find((m) => m.id === modelId) ||
      baseModelOptions.find((m) => m.id === modelId);
    return found?.label || modelId;
  };

  const committeeModelIds = useMemo(
    () => Array.from(new Set([...(agentDrafterModels || []), ...(agentReviewerModels || [])])),
    [agentDrafterModels, agentReviewerModels],
  );

  const webSearchModelOptions = useMemo(
    () =>
      agentModelOptions.filter(
        (m) =>
          ['openai', 'anthropic', 'google', 'perplexity'].includes(m.provider) &&
          !m.capabilities.includes('deep_research'),
      ),
    [agentModelOptions],
  );

  const gateMode =
    strictDocumentGateOverride === null ? 'auto' : strictDocumentGateOverride ? 'on' : 'off';

  const toggleAgentModel = (
    current: string[],
    modelId: string,
    setter: (models: string[]) => void,
    roleLabel: string,
  ) => {
    if (current.includes(modelId)) {
      if (current.length === 1) return;
      setter(current.filter((m) => m !== modelId));
      return;
    }
    if (current.length >= MAX_ROLE_MODELS) {
      toast.info(`Limite de ${MAX_ROLE_MODELS} modelos para ${roleLabel}.`);
      return;
    }
    setter([...current, modelId]);
  };

  const updateDocumentChecklist = (criticalText: string, nonCriticalText: string) => {
    const critical = criticalText
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)
      .map((label) => ({ label, critical: true }));
    const nonCritical = nonCriticalText
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)
      .map((label) => ({ label, critical: false }));
    setDocumentChecklist([...critical, ...nonCritical]);
  };

  // Summary helpers for accordion triggers
  const modeSummary = `${chatMode === 'multi-model' ? 'Comparar' : 'Normal'} • ${chatPersonality === 'juridico' ? 'Jurídico' : 'Livre'}`;

  const docTypeLabelMap: Record<string, string> = {
    PETICAO_INICIAL: 'Petição Inicial',
    CONTESTACAO: 'Contestação',
    RECURSO: 'Recurso',
    PARECER: 'Parecer',
    MANDADO_SEGURANCA: 'Mandado de Segurança',
    HABEAS_CORPUS: 'Habeas Corpus',
    RECLAMACAO_TRABALHISTA: 'Recl. Trabalhista',
    DIVORCIO: 'Divórcio',
    CONTRATO: 'Contrato',
    NOTA_TECNICA: 'Nota Técnica',
    SENTENCA: 'Sentença',
  };
  const docSummary = `${docTypeLabelMap[documentType] || documentType}${minPages > 0 || maxPages > 0 ? ` • ${minPages}-${maxPages}p` : ''}`;

  const reasoningLabel = reasoningLevel === 'low' ? 'Rápido' : reasoningLevel === 'high' ? 'Profundo' : 'Médio';
  const qualitySummary = `${reasoningLabel} • Rigor ${effortLevel} • ${creativityMode === 'rigoroso' ? 'Rigoroso' : creativityMode === 'criativo' ? 'Criativo' : 'Padrão'}`;

  const researchSummary = `${researchPolicy === 'auto' ? 'Auto' : 'Manual'}${webSearch ? ' • Web' : ''}${denseResearch ? ' • Deep' : ''}`;

  const modelSummary =
    mode === 'multi-agent'
      ? `Comitê: ${committeeModelIds.length} modelos`
      : getModelLabel(selectedModel);

  const controlSummary =
    mode === 'multi-agent'
      ? `Outline: ${hilOutlineEnabled ? 'Sim' : 'Não'}${autoApproveHil ? ' • Auto-aprovar' : ''}`
      : `Outline: ${chatOutlineReviewEnabled ? 'Sim' : 'Não'}`;

  // =========================================================================
  // RENDER
  // =========================================================================

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="sm:max-w-md overflow-y-auto p-0"
        data-testid="settings-panel"
      >
        <SheetHeader className="px-6 pt-6 pb-2">
          <SheetTitle className="text-base">Configurações</SheetTitle>
          <SheetDescription className="text-xs text-slate-500">
            Ajuste os parâmetros de geração da minuta.
          </SheetDescription>
        </SheetHeader>

        <div className="px-6 pb-6">
          <Accordion type="multiple" defaultValue={['modo', 'documento', 'qualidade']} className="w-full">
            {/* ============================================================= */}
            {/* 1. MODO & PERSONALIDADE */}
            {/* ============================================================= */}
            <AccordionItem value="modo">
              <AccordionTrigger className="text-xs font-semibold hover:no-underline">
                <div className="flex flex-col items-start gap-0.5">
                  <span>Modo &amp; Personalidade</span>
                  <span className="text-[10px] font-normal text-slate-400">{modeSummary}</span>
                </div>
              </AccordionTrigger>
              <AccordionContent className="space-y-3">
                {/* Chat mode */}
                <div className="space-y-1.5">
                  <SectionLabel>Modo do chat</SectionLabel>
                  <div className="flex items-center gap-1">
                    <Pill active={chatMode !== 'multi-model'} onClick={() => onSetChatMode('standard')}>
                      Normal
                    </Pill>
                    <Pill active={chatMode === 'multi-model'} onClick={() => onSetChatMode('multi-model')}>
                      Comparar
                    </Pill>
                  </div>
                </div>

                {/* Personality */}
                <div className="space-y-1.5">
                  <SectionLabel>Personalidade</SectionLabel>
                  <div className="flex items-center gap-1">
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span>
                            <Pill
                              active={chatPersonality === 'juridico'}
                              onClick={() => setChatPersonality('juridico')}
                            >
                              <span className="flex items-center gap-1">
                                <Scale className="h-3 w-3" />
                                Jurídico
                              </span>
                            </Pill>
                          </span>
                        </TooltipTrigger>
                        <TooltipContent><p>Linguagem técnica e formal.</p></TooltipContent>
                      </Tooltip>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span>
                            <Pill
                              active={chatPersonality === 'geral'}
                              onClick={() => setChatPersonality('geral')}
                            >
                              <span className="flex items-center gap-1">
                                <Sparkles className="h-3 w-3" />
                                Livre
                              </span>
                            </Pill>
                          </span>
                        </TooltipTrigger>
                        <TooltipContent><p>Assistente geral, sem formalidades jurídicas.</p></TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </div>
                </div>

                {/* Query mode (optional, Ask page only) */}
                {setQueryMode && (
                  <div className="space-y-1.5">
                    <SectionLabel>Comportamento de resposta</SectionLabel>
                    <div className="flex items-center gap-1">
                      <Pill active={queryMode === 'auto'} onClick={() => setQueryMode('auto')}>
                        Automático
                      </Pill>
                      <Pill active={queryMode === 'edit'} onClick={() => setQueryMode('edit')}>
                        Editar
                      </Pill>
                      <Pill active={queryMode === 'answer'} onClick={() => setQueryMode('answer')}>
                        Responder
                      </Pill>
                    </div>
                  </div>
                )}
              </AccordionContent>
            </AccordionItem>

            {/* ============================================================= */}
            {/* 2. DOCUMENTO */}
            {/* ============================================================= */}
            <AccordionItem value="documento">
              <AccordionTrigger className="text-xs font-semibold hover:no-underline">
                <div className="flex flex-col items-start gap-0.5">
                  <span>Documento</span>
                  <span className="text-[10px] font-normal text-slate-400">{docSummary}</span>
                </div>
              </AccordionTrigger>
              <AccordionContent className="space-y-4">
                {/* Document type */}
                <div className="space-y-1.5">
                  <RichTooltip
                    title="Tipo de Documento"
                    description="Define a estrutura e o vocabulário da peça."
                    badge="Minuta"
                  >
                    <SectionLabel>Tipo de Documento</SectionLabel>
                  </RichTooltip>
                  <select
                    className="w-full text-xs h-8 rounded-lg border border-indigo-200/60 bg-white px-2.5 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition"
                    value={documentType}
                    onChange={(e) => setDocumentType(e.target.value)}
                    data-testid="document-type-select"
                  >
                    <option value="PETICAO_INICIAL">Petição Inicial</option>
                    <option value="CONTESTACAO">Contestação</option>
                    <option value="RECURSO">Recurso / Apelação</option>
                    <option value="PARECER">Parecer Jurídico</option>
                    <option value="MANDADO_SEGURANCA">Mandado de Segurança</option>
                    <option value="HABEAS_CORPUS">Habeas Corpus</option>
                    <option value="RECLAMACAO_TRABALHISTA">Reclamação Trabalhista</option>
                    <option value="DIVORCIO">Divórcio Consensual</option>
                    <option value="CONTRATO">Contrato</option>
                    <option value="NOTA_TECNICA">Nota Técnica</option>
                    <option value="SENTENCA">Sentença</option>
                  </select>
                </div>

                {/* Page range */}
                <div className="space-y-1.5">
                  <RichTooltip
                    title="Intervalo de páginas"
                    description="Limita o tamanho da minuta e habilita revisão de outline quando definido."
                    badge="Tamanho"
                  >
                    <SectionLabel>Intervalo de páginas</SectionLabel>
                  </RichTooltip>
                  <div className="flex items-center justify-between text-[10px] text-slate-500">
                    <span>{minPages > 0 || maxPages > 0 ? `${minPages}-${maxPages} págs` : 'Auto'}</span>
                    {(minPages > 0 || maxPages > 0) && (
                      <button
                        type="button"
                        onClick={() => resetPageRange()}
                        className="text-indigo-600 hover:text-indigo-700"
                      >
                        limpar
                      </button>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <input
                      type="number"
                      min={0}
                      className="w-full text-xs h-8 rounded-lg border border-indigo-200/60 bg-white px-2.5 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition"
                      placeholder="Mín."
                      value={minPages === 0 ? '' : minPages}
                      onChange={(e) => {
                        const next = parseInt(e.target.value, 10);
                        setPageRange({ minPages: Number.isNaN(next) ? 0 : next });
                      }}
                    />
                    <input
                      type="number"
                      min={0}
                      className="w-full text-xs h-8 rounded-lg border border-indigo-200/60 bg-white px-2.5 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition"
                      placeholder="Máx."
                      value={maxPages === 0 ? '' : maxPages}
                      onChange={(e) => {
                        const next = parseInt(e.target.value, 10);
                        setPageRange({ maxPages: Number.isNaN(next) ? 0 : next });
                      }}
                    />
                  </div>
                  <div className="flex items-center gap-1">
                    {([
                      { label: 'Curta', min: 5, max: 8 },
                      { label: 'Média', min: 10, max: 15 },
                      { label: 'Longa', min: 20, max: 30 },
                    ] as const).map((preset) => (
                      <button
                        key={preset.label}
                        type="button"
                        className={cn(
                          'h-7 flex-1 rounded-md text-[10px] font-semibold transition-all',
                          minPages === preset.min && maxPages === preset.max
                            ? 'bg-indigo-600 text-white'
                            : 'bg-white text-indigo-400 border border-indigo-200/60 hover:bg-indigo-50',
                        )}
                        onClick={() => setPageRange({ minPages: preset.min, maxPages: preset.max })}
                      >
                        {preset.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Formatting */}
                <div className="space-y-1.5">
                  <RichTooltip
                    title="Formatação"
                    description="Elementos extras de estrutura e navegação no documento."
                    badge="Saída"
                  >
                    <SectionLabel>Formatação</SectionLabel>
                  </RichTooltip>
                  <div className="flex flex-col gap-1">
                    <Check
                      checked={!!formattingOptions?.includeToc}
                      onChange={(v) => setFormattingOptions({ includeToc: v })}
                    >
                      Incluir sumário
                    </Check>
                    <Check
                      checked={!!formattingOptions?.includeSummaries}
                      onChange={(v) => setFormattingOptions({ includeSummaries: v })}
                    >
                      Resumos por seção
                    </Check>
                    <Check
                      checked={!!formattingOptions?.includeSummaryTable}
                      onChange={(v) => setFormattingOptions({ includeSummaryTable: v })}
                    >
                      Tabela síntese
                    </Check>
                  </div>
                </div>
              </AccordionContent>
            </AccordionItem>

            {/* ============================================================= */}
            {/* 3. QUALIDADE */}
            {/* ============================================================= */}
            <AccordionItem value="qualidade">
              <AccordionTrigger className="text-xs font-semibold hover:no-underline">
                <div className="flex flex-col items-start gap-0.5">
                  <span>Qualidade</span>
                  <span className="text-[10px] font-normal text-slate-400">{qualitySummary}</span>
                </div>
              </AccordionTrigger>
              <AccordionContent className="space-y-4">
                {/* Quality profile */}
                {mode === 'multi-agent' && (
                  <div className="space-y-2">
                    <RichTooltip
                      title="Perfil de qualidade"
                      description="Define valores base de rodadas, metas de nota e política de HIL."
                      badge="Minuta"
                    >
                      <SectionLabel>Perfil de qualidade</SectionLabel>
                    </RichTooltip>
                    <div className="flex flex-wrap gap-1">
                      {QUALITY_PROFILE_SPECS.map((p) => (
                        <RichTooltip
                          key={p.id}
                          title={p.label}
                          description={buildProfileDescription(p)}
                          badge="Perfil"
                          meta={qualityProfileMeta}
                        >
                          <span>
                            <Pill
                              active={qualityProfile === p.id}
                              onClick={() => setQualityProfile(p.id)}
                            >
                              {p.label}
                            </Pill>
                          </span>
                        </RichTooltip>
                      ))}
                    </div>

                    {/* Score / rounds overrides */}
                    <div
                      className={cn(
                        'grid gap-2 pt-1',
                        effectiveHilSectionPolicy === 'none' ? 'grid-cols-2' : 'grid-cols-3',
                      )}
                    >
                      {effectiveHilSectionPolicy !== 'none' && (
                        <div className="space-y-1">
                          <RichTooltip
                            title="Nota da seção"
                            description="Meta mínima para cada seção antes de aceitar a saída."
                            badge="Override"
                            meta={sectionScoreMeta}
                          >
                            <SubLabel>Nota seção</SubLabel>
                          </RichTooltip>
                          <NumInput
                            value={qualityTargetSectionScore}
                            onChange={(v) => setQualityTargetSectionScore(clampScore(v))}
                            placeholder="Ex.: 9.2"
                            min={0}
                            max={10}
                            step={0.1}
                          />
                        </div>
                      )}
                      <div className="space-y-1">
                        <RichTooltip
                          title="Nota final"
                          description="Sobrescreve o perfil quando definido."
                          badge="Override"
                        >
                          <SubLabel>Nota final</SubLabel>
                        </RichTooltip>
                        <NumInput
                          value={qualityTargetFinalScore}
                          onChange={(v) => setQualityTargetFinalScore(clampScore(v))}
                          placeholder="Ex.: 9.8"
                          min={0}
                          max={10}
                          step={0.1}
                        />
                      </div>
                      <div className="space-y-1">
                        <RichTooltip
                          title="Rodadas do comitê"
                          description="Sobrescreve o perfil (máx. 6)."
                          badge="Override"
                        >
                          <SubLabel>Rodadas</SubLabel>
                        </RichTooltip>
                        <NumInput
                          value={qualityMaxRounds}
                          onChange={(v) => setQualityMaxRounds(clampRounds(v))}
                          placeholder="Ex.: 3"
                          min={1}
                          max={6}
                          step={1}
                        />
                      </div>
                    </div>
                  </div>
                )}

                {/* Reasoning level */}
                <div className="space-y-1.5">
                  <RichTooltip
                    title="Nível de Raciocínio (Thinking)"
                    description="Controla a profundidade do raciocínio do modelo. Pode ser sobrescrito no chat."
                    badge="Thinking"
                  >
                    <SectionLabel>Nível de Raciocínio</SectionLabel>
                  </RichTooltip>
                  <div className="flex items-center gap-0.5">
                    {([
                      { id: 'low', label: 'Rápido' },
                      { id: 'medium', label: 'Médio' },
                      { id: 'high', label: 'Profundo' },
                    ] as const).map((opt) => (
                      <button
                        key={opt.id}
                        type="button"
                        onClick={() => setReasoningLevel(opt.id)}
                        className={cn(
                          'h-8 flex-1 rounded-md text-xs font-bold transition-all',
                          reasoningLevel === opt.id
                            ? 'bg-violet-600 text-white'
                            : 'bg-white text-violet-300 border border-violet-200/60 hover:bg-violet-50',
                        )}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Effort level */}
                <div className="space-y-1.5">
                  <RichTooltip
                    title="Nível de Rigor"
                    description="Controla profundidade e tempo de geração."
                    badge="Qualidade"
                  >
                    <SectionLabel>Nível de Rigor</SectionLabel>
                  </RichTooltip>
                  <div className="flex items-center gap-0.5">
                    {[1, 2, 3, 4, 5].map((level) => (
                      <button
                        key={level}
                        onClick={() => setEffortLevel(level)}
                        className={cn(
                          'h-8 flex-1 rounded-md text-xs font-bold transition-all',
                          effortLevel >= level
                            ? 'bg-indigo-600 text-white'
                            : 'bg-white text-indigo-300 border border-indigo-200/60 hover:bg-indigo-50',
                        )}
                      >
                        {level}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Creativity */}
                <div className="space-y-1.5">
                  <RichTooltip
                    title="Criatividade (Temperatura)"
                    description="Equilibra rigor e fluidez."
                    badge="Estilo"
                  >
                    <SectionLabel>Criatividade</SectionLabel>
                  </RichTooltip>
                  <div className="flex items-center gap-0.5">
                    {([
                      { id: 'rigoroso', label: 'Rigoroso' },
                      { id: 'padrao', label: 'Padrão' },
                      { id: 'criativo', label: 'Criativo' },
                    ] as const).map((opt) => (
                      <button
                        key={opt.id}
                        type="button"
                        onClick={() => {
                          setCreativityMode(opt.id);
                          setTemperatureOverride(null);
                        }}
                        className={cn(
                          'h-8 flex-1 rounded-md text-xs font-bold transition-all',
                          creativityMode === opt.id
                            ? 'bg-rose-500 text-white'
                            : 'bg-white text-rose-300 border border-rose-200/60 hover:bg-rose-50',
                        )}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
              </AccordionContent>
            </AccordionItem>

            {/* ============================================================= */}
            {/* 4. PESQUISA */}
            {/* ============================================================= */}
            <AccordionItem value="pesquisa">
              <AccordionTrigger className="text-xs font-semibold hover:no-underline">
                <div className="flex flex-col items-start gap-0.5">
                  <span>Pesquisa</span>
                  <span className="text-[10px] font-normal text-slate-400">{researchSummary}</span>
                </div>
              </AccordionTrigger>
              <AccordionContent className="space-y-4">
                {/* Research policy */}
                <div className="space-y-1.5">
                  <SectionLabel>Decisão de pesquisa</SectionLabel>
                  <div className="flex items-center gap-1">
                    <RichTooltip
                      title="Auto"
                      description="Permite que a IA ative Web/Deep quando necessário."
                      badge="Modo"
                    >
                      <span>
                        <Pill active={researchPolicy === 'auto'} onClick={() => setResearchPolicy('auto')}>
                          Auto
                        </Pill>
                      </span>
                    </RichTooltip>
                    <RichTooltip
                      title="Manual"
                      description="Respeita apenas os toggles de Web/Deep."
                      badge="Modo"
                    >
                      <span>
                        <Pill active={researchPolicy === 'force'} onClick={() => setResearchPolicy('force')}>
                          Manual
                        </Pill>
                      </span>
                    </RichTooltip>
                  </div>
                </div>

                {/* Toggles */}
                <div className="space-y-1">
                  <Check checked={webSearch} onChange={setWebSearch}>
                    Web Search
                  </Check>
                  <Check checked={denseResearch} onChange={setDenseResearch}>
                    Deep Research
                  </Check>
                </div>

                {/* Deep research provider */}
                <div className={cn('space-y-1.5', !denseResearch && 'opacity-60')}>
                  <SubLabel>Backend do Deep Research</SubLabel>
                  <div className="flex flex-wrap gap-1">
                    {([
                      { id: 'auto', label: 'Auto' },
                      { id: 'google', label: 'Google' },
                      { id: 'perplexity', label: 'Perplexity' },
                    ] as const).map((opt) => (
                      <Pill
                        key={opt.id}
                        active={deepResearchProvider === opt.id}
                        onClick={() => setDeepResearchProvider(opt.id)}
                        disabled={!denseResearch}
                        variant={opt.id === 'perplexity' && deepResearchProvider === 'perplexity' ? 'rose' : 'indigo'}
                      >
                        {opt.label}
                      </Pill>
                    ))}
                  </div>
                  {deepResearchProvider === 'perplexity' && denseResearch && (
                    <div className="space-y-1">
                      <SubLabel>Modelo (Perplexity)</SubLabel>
                      <Pill
                        active={deepResearchModel === 'sonar-deep-research'}
                        onClick={() => setDeepResearchModel('sonar-deep-research')}
                        variant="rose"
                      >
                        Sonar Deep Research
                      </Pill>
                      <p className="text-[10px] text-rose-700/80">
                        Dica: para atuar como agente, prefira <span className="font-semibold">Google</span>.
                      </p>
                    </div>
                  )}
                </div>

                {/* Search mode */}
                <div className={cn('space-y-1.5', !webSearch && 'opacity-60')}>
                  <SubLabel>Modo de busca</SubLabel>
                  <div className="flex flex-wrap gap-1">
                    {([
                      { id: 'shared', label: 'Compartilhada' },
                      { id: 'native', label: 'Nativa' },
                      { id: 'hybrid', label: 'Híbrida' },
                    ] as const).map((opt) => (
                      <Pill
                        key={opt.id}
                        active={searchMode === opt.id}
                        onClick={() => setSearchMode(opt.id)}
                        disabled={!webSearch}
                      >
                        {opt.label}
                      </Pill>
                    ))}
                  </div>

                  {/* Web search model */}
                  <div className="mt-2 space-y-1">
                    <SubLabel>Modelo de pesquisa (LangGraph)</SubLabel>
                    <select
                      className="w-full text-[10px] h-8 rounded border border-slate-200 bg-white px-2"
                      value={webSearchModel}
                      disabled={!webSearch || searchMode !== 'native'}
                      onChange={(e) => setWebSearchModel(e.target.value)}
                    >
                      <option value="auto">Auto (usar Juiz)</option>
                      {webSearchModelOptions.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.label}
                        </option>
                      ))}
                    </select>
                    {webSearch && searchMode !== 'native' && (
                      <p className="text-[10px] text-slate-500">
                        Disponível apenas em <span className="font-semibold">Nativa por modelo</span>.
                      </p>
                    )}
                  </div>

                  {/* Extra toggles */}
                  <div className="mt-2 space-y-1">
                    <Check checked={multiQuery} onChange={setMultiQuery} disabled={!webSearch}>
                      Multi-query
                    </Check>
                    <Check checked={breadthFirst} onChange={setBreadthFirst} disabled={!webSearch}>
                      Breadth-first
                    </Check>
                  </div>
                </div>

                {/* Audit mode */}
                <div className="space-y-1.5">
                  <RichTooltip
                    title="Modo de auditoria"
                    description="Controla se a verificação se limita a Base local ou inclui fontes externas."
                    badge="Compliance"
                  >
                    <SectionLabel>Modo de auditoria</SectionLabel>
                  </RichTooltip>
                  <div className="flex flex-wrap gap-1">
                    <Pill active={auditMode === 'sei_only'} onClick={() => setAuditMode('sei_only')}>
                      Somente Base local
                    </Pill>
                    <Pill active={auditMode === 'research'} onClick={() => setAuditMode('research')}>
                      Base local + fontes externas
                    </Pill>
                  </div>
                </div>
              </AccordionContent>
            </AccordionItem>

            {/* ============================================================= */}
            {/* 5. MODELOS */}
            {/* ============================================================= */}
            <AccordionItem value="modelos">
              <AccordionTrigger className="text-xs font-semibold hover:no-underline">
                <div className="flex flex-col items-start gap-0.5">
                  <span>Modelos</span>
                  <span className="text-[10px] font-normal text-slate-400">{modelSummary}</span>
                </div>
              </AccordionTrigger>
              <AccordionContent className="space-y-4">
                {mode === 'individual' ? (
                  <div className="space-y-1.5">
                    <RichTooltip
                      title="Modelo base (Chat)"
                      description="Define qual modelo responde no modo Chat de um único modelo."
                      badge="Chat"
                    >
                      <SectionLabel>Modelo base (Chat)</SectionLabel>
                    </RichTooltip>
                    <select
                      className="w-full text-xs h-8 rounded-lg border border-indigo-200/60 bg-white px-2.5 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition"
                      value={selectedModel}
                      onChange={(e) => setSelectedModel(e.target.value)}
                    >
                      {baseModelOptions.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.label}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <SectionLabel>
                      <span className="flex items-center gap-2">
                        <Users className="h-3 w-3" /> Modelos do Comitê de Agentes
                      </span>
                    </SectionLabel>

                    {/* Summary badges */}
                    <div className="flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
                      <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5">
                        Juiz: {getModelLabel(selectedModel)}
                      </span>
                      <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5">
                        Estrategista: {getModelLabel(agentStrategistModel)}
                      </span>
                      <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5">
                        Comitê: {committeeModelIds.length} modelo{committeeModelIds.length === 1 ? '' : 's'}
                      </span>
                    </div>

                    {/* Strategist */}
                    <div className="space-y-1">
                      <SubLabel>Estrategista (Planejamento)</SubLabel>
                      <select
                        className="w-full text-[10px] h-7 rounded border border-indigo-200 bg-white"
                        value={selectedModel}
                        onChange={(e) => setSelectedModel(e.target.value)}
                      >
                        {agentModelOptions.map((model) => (
                          <option key={model.id} value={model.id}>
                            {model.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Drafter */}
                    <div className="space-y-1">
                      <SubLabel>Redator (multi-seleção, máx 3)</SubLabel>
                      <div className="space-y-1 rounded border border-indigo-200 bg-white p-2">
                        {agentModelOptions.map((model) => (
                          <label
                            key={model.id}
                            className={cn(
                              'flex items-center gap-2 text-[10px] text-slate-600',
                              !agentDrafterModels.includes(model.id) &&
                                agentDrafterModels.length >= MAX_ROLE_MODELS
                                ? 'opacity-60 cursor-not-allowed'
                                : 'cursor-pointer',
                            )}
                          >
                            <input
                              type="checkbox"
                              className="rounded border-indigo-300 text-indigo-600 focus:ring-indigo-500/20 h-3 w-3"
                              checked={agentDrafterModels.includes(model.id)}
                              disabled={
                                !agentDrafterModels.includes(model.id) &&
                                agentDrafterModels.length >= MAX_ROLE_MODELS
                              }
                              onChange={() =>
                                toggleAgentModel(agentDrafterModels, model.id, setAgentDrafterModels, 'redator')
                              }
                            />
                            <span>{model.label}</span>
                          </label>
                        ))}
                      </div>
                    </div>

                    {/* Reviewer */}
                    <div className="space-y-1">
                      <SubLabel>Revisor (multi-seleção, máx 3)</SubLabel>
                      <div className="space-y-1 rounded border border-indigo-200 bg-white p-2">
                        {agentModelOptions.map((model) => (
                          <label
                            key={model.id}
                            className={cn(
                              'flex items-center gap-2 text-[10px] text-slate-600',
                              !agentReviewerModels.includes(model.id) &&
                                agentReviewerModels.length >= MAX_ROLE_MODELS
                                ? 'opacity-60 cursor-not-allowed'
                                : 'cursor-pointer',
                            )}
                          >
                            <input
                              type="checkbox"
                              className="rounded border-indigo-300 text-indigo-600 focus:ring-indigo-500/20 h-3 w-3"
                              checked={agentReviewerModels.includes(model.id)}
                              disabled={
                                !agentReviewerModels.includes(model.id) &&
                                agentReviewerModels.length >= MAX_ROLE_MODELS
                              }
                              onChange={() =>
                                toggleAgentModel(agentReviewerModels, model.id, setAgentReviewerModels, 'revisor')
                              }
                            />
                            <span>{model.label}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </AccordionContent>
            </AccordionItem>

            {/* ============================================================= */}
            {/* 6. CONTROLE (HIL) */}
            {/* ============================================================= */}
            <AccordionItem value="controle">
              <AccordionTrigger className="text-xs font-semibold hover:no-underline">
                <div className="flex flex-col items-start gap-0.5">
                  <span>Controle (HIL)</span>
                  <span className="text-[10px] font-normal text-slate-400">{controlSummary}</span>
                </div>
              </AccordionTrigger>
              <AccordionContent className="space-y-4">
                {mode === 'individual' ? (
                  <div className="space-y-2">
                    {(() => {
                      const hasPageRange = minPages > 0 || maxPages > 0;
                      const canShow = hasPageRange && chatMode !== 'multi-model';
                      if (!canShow) {
                        return (
                          <p className="text-[10px] text-slate-500">
                            {chatMode === 'multi-model'
                              ? 'Revisão de outline é disponível apenas no Chat normal (1 modelo).'
                              : 'Defina um intervalo de páginas para habilitar revisão de outline.'}
                          </p>
                        );
                      }
                      return (
                        <>
                          <Check
                            checked={chatOutlineReviewEnabled}
                            onChange={setChatOutlineReviewEnabled}
                          >
                            Revisar outline (pré-resposta)
                          </Check>
                          <p className="text-[10px] text-slate-500">
                            Abre um modal para revisar/editar a estrutura antes do streaming.
                          </p>
                        </>
                      );
                    })()}
                  </div>
                ) : (
                  <div className="space-y-3">
                    {/* Outline approval */}
                    <div className="space-y-1">
                      <Check
                        checked={hilOutlineEnabled}
                        onChange={setHilOutlineEnabled}
                        disabled={autoApproveHil}
                      >
                        Aprovar outline (HIL)
                      </Check>
                      <p className="text-[10px] text-slate-500">
                        Pausa para aprovar/editar a outline antes da redação.
                      </p>
                    </div>

                    {/* Auto approve */}
                    <div className="space-y-1">
                      <Check checked={autoApproveHil} onChange={setAutoApproveHil}>
                        Forçar nunca interromper (auto-aprovar)
                      </Check>
                      <p className="text-[10px] text-slate-500">
                        Se ativado, overrides de HIL não interrompem o fluxo.
                      </p>
                    </div>

                    {/* HIL section policy */}
                    <div className="space-y-1">
                      <SubLabel>HIL por seção</SubLabel>
                      <div className="flex flex-wrap gap-1">
                        {([
                          { id: 'auto', label: 'Perfil' },
                          { id: 'none', label: 'Desligado' },
                          { id: 'optional', label: 'Opcional' },
                          { id: 'required', label: 'Obrigatório' },
                        ] as const).map((opt) => (
                          <Pill
                            key={opt.id}
                            active={hilSectionPolicyMode === opt.id}
                            onClick={() => {
                              if (opt.id === 'auto') setHilSectionPolicyOverride(null);
                              else setHilSectionPolicyOverride(opt.id);
                            }}
                          >
                            {opt.label}
                          </Pill>
                        ))}
                      </div>
                    </div>

                    {/* HIL final */}
                    <div className="space-y-1">
                      <SubLabel>HIL final</SubLabel>
                      <div className="flex flex-wrap gap-1">
                        {([
                          { id: 'auto', label: 'Perfil' },
                          { id: 'on', label: 'Exigir' },
                          { id: 'off', label: 'Não exigir' },
                        ] as const).map((opt) => (
                          <Pill
                            key={opt.id}
                            active={hilFinalRequiredMode === opt.id}
                            onClick={() => {
                              if (opt.id === 'auto') setHilFinalRequiredOverride(null);
                              if (opt.id === 'on') setHilFinalRequiredOverride(true);
                              if (opt.id === 'off') setHilFinalRequiredOverride(false);
                            }}
                          >
                            {opt.label}
                          </Pill>
                        ))}
                      </div>
                    </div>

                    {/* Gate documental */}
                    <div className="space-y-1">
                      <RichTooltip
                        title="Gate documental"
                        description="Define se a minuta bloqueia quando falta documento essencial."
                        badge="Minuta"
                      >
                        <SubLabel>Gate documental</SubLabel>
                      </RichTooltip>
                      <div className="flex flex-wrap gap-1">
                        {([
                          { id: 'auto', label: 'Perfil' },
                          { id: 'on', label: 'Bloquear' },
                          { id: 'off', label: 'Ressalva' },
                        ] as const).map((opt) => (
                          <Pill
                            key={opt.id}
                            active={gateMode === opt.id}
                            onClick={() => {
                              if (opt.id === 'auto') setStrictDocumentGateOverride(null);
                              if (opt.id === 'on') setStrictDocumentGateOverride(true);
                              if (opt.id === 'off') setStrictDocumentGateOverride(false);
                            }}
                          >
                            {opt.label}
                          </Pill>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </AccordionContent>
            </AccordionItem>

            {/* ============================================================= */}
            {/* 7. AVANÇADO */}
            {/* ============================================================= */}
            <AccordionItem value="avancado">
              <AccordionTrigger className="text-xs font-semibold hover:no-underline">
                <div className="flex flex-col items-start gap-0.5">
                  <span>Avançado</span>
                  <span className="text-[10px] font-normal text-slate-400">Ajustes finos opcionais</span>
                </div>
              </AccordionTrigger>
              <AccordionContent className="space-y-3">
                <p className="text-[10px] text-slate-500">
                  Use apenas se precisar de mais insistência na pesquisa ou de ajustes finos de estilo.
                </p>

                <div className="grid grid-cols-2 gap-3">
                  {/* Refino final */}
                  <div className="space-y-1">
                    <RichTooltip
                      title="Refinamentos finais"
                      description="Passagens finais de polimento antes do gate final."
                      badge="Final"
                    >
                      <SubLabel>Refino final</SubLabel>
                    </RichTooltip>
                    <NumInput
                      value={qualityMaxFinalReviewLoops}
                      onChange={(v) => setQualityMaxFinalReviewLoops(clampStyleRounds(v))}
                      placeholder="Auto (perfil)"
                      min={0}
                      max={6}
                      step={1}
                    />
                  </div>

                  {/* Divergência HIL */}
                  <div className="space-y-1">
                    <RichTooltip
                      title="Divergência (HIL)"
                      description="Limita iterações na resolução de divergências via HIL."
                      badge="HIL"
                    >
                      <SubLabel>Divergência HIL</SubLabel>
                    </RichTooltip>
                    <NumInput
                      value={maxDivergenceHilRounds}
                      onChange={(v) => setMaxDivergenceHilRounds(clampDivergenceHilRounds(v))}
                      placeholder="Auto (2)"
                      min={1}
                      max={5}
                      step={1}
                    />
                  </div>

                  {/* Temperatura */}
                  <div className="space-y-1">
                    <RichTooltip
                      title="Temperatura (custom)"
                      description="Sobrescreve o preset de criatividade por um valor contínuo 0.0-1.0."
                      badge="Estilo"
                    >
                      <SubLabel>Temperatura</SubLabel>
                    </RichTooltip>
                    <NumInput
                      value={temperatureOverride}
                      onChange={(v) => setTemperatureOverride(clampTemperature(v))}
                      placeholder="Auto (preset)"
                      min={0}
                      max={1}
                      step={0.05}
                    />
                  </div>

                  {/* Debate granular */}
                  <div className="space-y-1">
                    <RichTooltip
                      title="Debate granular"
                      description="Força o subgrafo granular em todas as seções."
                      badge="Rigor"
                    >
                      <div className="h-8 flex items-center">
                        <Check checked={forceGranularDebate} onChange={setForceGranularDebate}>
                          Forçar granular
                        </Check>
                      </div>
                    </RichTooltip>
                  </div>

                  {/* Refino de estilo */}
                  <div className="space-y-1">
                    <RichTooltip
                      title="Refino de estilo"
                      description="Ajustes de tom quando a nota de estilo fica baixa."
                      badge="Estilo"
                    >
                      <SubLabel>Refino de estilo</SubLabel>
                    </RichTooltip>
                    <NumInput
                      value={qualityStyleRefineMaxRounds}
                      onChange={(v) => setQualityStyleRefineMaxRounds(clampStyleRounds(v))}
                      placeholder="Auto (perfil)"
                      min={0}
                      max={6}
                      step={1}
                    />
                  </div>

                  {/* Tentativas de pesquisa */}
                  <div className="space-y-1">
                    <RichTooltip
                      title="Tentativas de pesquisa"
                      description="Se faltarem citações/jurisprudência, quantas vezes tenta pesquisar de novo."
                      badge="Pesquisa"
                    >
                      <SubLabel>Tentativas pesquisa</SubLabel>
                    </RichTooltip>
                    <NumInput
                      value={qualityMaxResearchVerifierAttempts}
                      onChange={(v) => setQualityMaxResearchVerifierAttempts(clampRetry(v))}
                      placeholder="Auto (perfil)"
                      min={0}
                      max={5}
                      step={1}
                    />
                  </div>

                  {/* Retentativas RAG */}
                  <div className="space-y-1">
                    <RichTooltip
                      title="Retentativas no RAG"
                      description="Repete busca com parâmetros mais agressivos quando qualidade das fontes está baixa."
                      badge="RAG"
                    >
                      <SubLabel>Retentativas RAG</SubLabel>
                    </RichTooltip>
                    <NumInput
                      value={qualityMaxRagRetries}
                      onChange={(v) => setQualityMaxRagRetries(clampRetry(v))}
                      placeholder="Auto (perfil)"
                      min={0}
                      max={5}
                      step={1}
                    />
                  </div>

                  {/* Expandir fontes */}
                  <div className="space-y-1">
                    <RichTooltip
                      title="Expandir fontes"
                      description="Permite buscar em lei/jurisprudência se falta prova local."
                      badge="Política"
                    >
                      <SubLabel>Expandir fontes</SubLabel>
                    </RichTooltip>
                    <div className="flex flex-wrap gap-1">
                      {([
                        { id: 'auto', label: 'Perfil' },
                        { id: 'on', label: 'Permitir' },
                        { id: 'off', label: 'Bloquear' },
                      ] as const).map((opt) => (
                        <Pill
                          key={opt.id}
                          active={expandScopeMode === opt.id}
                          disabled={!canExpandScope}
                          onClick={() => {
                            if (opt.id === 'auto') setQualityRagRetryExpandScope(null);
                            if (opt.id === 'on') setQualityRagRetryExpandScope(true);
                            if (opt.id === 'off') setQualityRagRetryExpandScope(false);
                          }}
                        >
                          {opt.label}
                        </Pill>
                      ))}
                    </div>
                    {!canExpandScope && (
                      <p className="text-[10px] text-slate-500">
                        Bloqueado porque auditoria est&aacute; em &quot;Somente Base local&quot;.
                      </p>
                    )}
                  </div>

                  {/* CRAG melhor fonte */}
                  <div className="space-y-1">
                    <RichTooltip
                      title="CRAG: melhor fonte"
                      description="Mínimo de qualidade da melhor evidência."
                      badge="CRAG"
                    >
                      <SubLabel>CRAG (melhor fonte)</SubLabel>
                    </RichTooltip>
                    <NumInput
                      value={cragMinBestScoreOverride}
                      onChange={(v) => setCragMinBestScoreOverride(clampCragScore(v))}
                      placeholder="Auto (perfil)"
                      min={0}
                      max={1}
                      step={0.05}
                    />
                  </div>

                  {/* CRAG média top 3 */}
                  <div className="space-y-1">
                    <RichTooltip
                      title="CRAG: média top 3"
                      description="Mínimo de qualidade média das 3 melhores fontes."
                      badge="CRAG"
                    >
                      <SubLabel>CRAG (média top 3)</SubLabel>
                    </RichTooltip>
                    <NumInput
                      value={cragMinAvgScoreOverride}
                      onChange={(v) => setCragMinAvgScoreOverride(clampCragScore(v))}
                      placeholder="Auto (perfil)"
                      min={0}
                      max={1}
                      step={0.05}
                    />
                  </div>

                  {/* Recursion limit */}
                  <div className="space-y-1">
                    <RichTooltip
                      title="Limite de recursão"
                      description="Máximo de passos/loops que o agente pode executar."
                      badge="Avançado"
                    >
                      <SubLabel>Limite de recursão</SubLabel>
                    </RichTooltip>
                    <NumInput
                      value={recursionLimitOverride}
                      onChange={(v) => setRecursionLimitOverride(clampRecursionLimit(v))}
                      placeholder="Auto (perfil)"
                      min={20}
                      max={500}
                      step={10}
                    />
                  </div>
                </div>
              </AccordionContent>
            </AccordionItem>

            {/* ============================================================= */}
            {/* 8. CHECKLIST */}
            {/* ============================================================= */}
            <AccordionItem value="checklist">
              <AccordionTrigger className="text-xs font-semibold hover:no-underline">
                <div className="flex flex-col items-start gap-0.5">
                  <span>Checklist</span>
                  <span className="text-[10px] font-normal text-slate-400">
                    {documentChecklist.length > 0
                      ? `${documentChecklist.filter((i) => i.critical).length} críticos, ${documentChecklist.filter((i) => !i.critical).length} opcionais`
                      : 'Nenhum item'}
                  </span>
                </div>
              </AccordionTrigger>
              <AccordionContent className="space-y-3">
                <RichTooltip
                  title="Checklist complementar"
                  description="Itens extras para checagem automática, além da Base local. Um item por linha."
                  badge="Validação"
                >
                  <SectionLabel>Checklist complementar</SectionLabel>
                </RichTooltip>

                <div className="space-y-3">
                  {/* Critical items */}
                  <div className="space-y-1">
                    <div className="text-[10px] font-semibold uppercase text-rose-600/70">Críticos</div>
                    <textarea
                      rows={3}
                      className="w-full text-xs rounded-lg border border-indigo-200/60 bg-white px-2.5 py-2"
                      placeholder={'Ex.: Ata de licitação\nTED assinado\nHomologação'}
                      value={criticalChecklistText}
                      onChange={(e) => {
                        const next = e.target.value;
                        setCriticalChecklistText(next);
                        updateDocumentChecklist(next, nonCriticalChecklistText);
                      }}
                    />
                  </div>

                  {/* Non-critical items */}
                  <div className="space-y-1">
                    <SubLabel>Não críticos</SubLabel>
                    <textarea
                      rows={3}
                      className="w-full text-xs rounded-lg border border-indigo-200/60 bg-white px-2.5 py-2"
                      placeholder={'Ex.: Número de apoio\nMemorando complementar'}
                      value={nonCriticalChecklistText}
                      onChange={(e) => {
                        const next = e.target.value;
                        setNonCriticalChecklistText(next);
                        updateDocumentChecklist(criticalChecklistText, next);
                      }}
                    />
                  </div>
                </div>

                <p className="text-[10px] text-slate-500">
                  Itens adicionais para checagem automática (um por linha). Não substitui a base local.
                </p>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </div>
      </SheetContent>
    </Sheet>
  );
}
