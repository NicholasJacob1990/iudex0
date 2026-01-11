'use client';

import { useEffect, useState } from 'react';
import { useChatStore, useCanvasStore } from '@/stores';
import { Button } from '@/components/ui/button';
import { ChatInterface, ChatInput } from '@/components/chat';
import {
  Sparkles,
  FileText,
  ChevronDown,
  ChevronUp,
  FileSearch,
  BookOpen,
  Users,
  User,
  CheckCircle2,
  Circle,
  Loader2,
  Settings2,
  Zap,
  Scale,
} from 'lucide-react';
import { toast } from 'sonner';
import { CanvasContainer, OutlineApprovalModal } from '@/components/dashboard';
import { useContextStore, type ContextItem } from '@/stores/context-store';
import { cn } from '@/lib/utils';
import { listModels } from '@/config/models';
import { type OutlineApprovalSection } from '@/components/dashboard/outline-approval-modal';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
// Resizable panels via CSS resize

type GenerationMode = 'individual' | 'multi-agent';

export default function MinutaPage() {
  const {
    currentChat,
    createChat,
    sendMessage,
    startAgentGeneration,
    isLoading,
    isSending,
    setContext,
    setUseMultiAgent,
    isAgentRunning,
    agentSteps,
    effortLevel,
    setEffortLevel,
    minPages,
    maxPages,
    setPageRange,
    resetPageRange,
    reviewData,
    submitReview,
    chatMode,
    setChatMode,
    selectedModels,
    setSelectedModels,
    setShowMultiModelComparator,
    webSearch,
    denseResearch,
    reasoningLevel,
    setReasoningLevel,
    agentStrategistModel,
    setAgentStrategistModel,
    agentDrafterModels,
    setAgentDrafterModels,
    agentReviewerModels,
    setAgentReviewerModels,
    chatPersonality,
    setChatPersonality,
  } = useChatStore();

  const { state: canvasState, showCanvas, setActiveTab } = useCanvasStore();
  const { items: contextItems } = useContextStore();

  const [showFontes, setShowFontes] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [mode, setMode] = useState<GenerationMode>('multi-agent');

  const MAX_ROLE_MODELS = 3;
  const DEFAULT_COMPARE_MODELS = ['gpt-5.2', 'claude-4.5-sonnet', 'gemini-3-flash'];
  const agentModelOptions = listModels({ forAgents: true });

  const toggleAgentModel = (
    current: string[],
    modelId: string,
    setter: (models: string[]) => void,
    roleLabel: string
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

  // Sync mode with store
  useEffect(() => {
    setUseMultiAgent(mode === 'multi-agent');
  }, [mode, setUseMultiAgent]);

  // Sync context items to ChatStore
  useEffect(() => {
    setContext(contextItems);
  }, [contextItems, setContext]);

  // Ensure canvas is visible on initial mount only (not overriding user close action)
  useEffect(() => {
    showCanvas();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-create chat on mount if none exists
  useEffect(() => {
    if (!currentChat && !isLoading) {
      createChat('Nova Minuta').catch(() => {
        // Silent fail - user can create manually
      });
    }
  }, [currentChat, isLoading, createChat]);

  const handleStartNewMinuta = async () => {
    try {
      await createChat('Nova Minuta');
      toast.success('Nova conversa criada!');
    } catch (error) {
      // handled
    }
  };

  const handleGenerate = async () => {
    try {
      let chat = currentChat;
      if (!chat) {
        chat = await createChat('Nova Minuta');
      }
      await startAgentGeneration('Gerar minuta baseada nos documentos selecionados.');
    } catch (e) {
      // handled by store/toast
    }
  };

  const handleSetChatMode = (next: 'standard' | 'multi-model') => {
    if (next === 'multi-model') {
      const nextModels =
        selectedModels.length >= 2
          ? selectedModels
          : selectedModels.length === 1
            ? [selectedModels[0], DEFAULT_COMPARE_MODELS.find((m) => m !== selectedModels[0]) || 'gpt-5.2']
            : DEFAULT_COMPARE_MODELS.slice(0, 3);

      setSelectedModels(nextModels);
      setShowMultiModelComparator(true);
      setChatMode('multi-model');
      return;
    }

    if (selectedModels.length > 1) setSelectedModels([selectedModels[0]]);
    setChatMode('standard');
  };

  // Agent step labels
  const getAgentLabel = (agent: string) => {
    switch (agent) {
      case 'strategist': return 'Estrategista';
      case 'researcher': return 'Pesquisador';
      case 'drafter': return 'Redator';
      case 'reviewer': return 'Revisor';
      case 'judge': return 'Juiz';
      default: return agent;
    }
  };

  // HIL Handlers
  const handleOutlineApprove = async (sections: OutlineApprovalSection[]) => {
    try {
      await submitReview({ approved: true, outline: sections });
      toast.success('Estrutura aprovada! Agentes iniciando redação...');
    } catch (e) {
      toast.error('Erro ao enviar aprovação.');
    }
  };

  const handleOutlineReject = async () => {
    try {
      await submitReview({ approved: false, comment: "Usuário cancelou no modal." });
      toast.info('Geração cancelada.');
    } catch (e) {
      toast.error('Erro ao rejeitar.');
    }
  };

  // Check if HIL modal should be shown
  const showOutlineModal = reviewData?.checkpoint === 'outline' || reviewData?.type === 'outline_review';
  const outlinePayload = reviewData?.review_data?.outline || reviewData?.outline || [];

  // Convert generic list to typed sections if needed
  const initialSections: OutlineApprovalSection[] = Array.isArray(outlinePayload)
    ? outlinePayload.map((s: string | any, i: number) =>
      typeof s === 'string' ? { id: `sect-${i}`, title: s } : s
    )
    : [];

  const handleOpenQuality = () => {
    showCanvas();
    setActiveTab('audit');
  };

  return (
    <div className="flex h-full flex-1 min-h-0 flex-col gap-3">
      {/* Compact Toolbar */}
      <div className="flex flex-none flex-wrap items-center justify-between gap-2 rounded-xl bg-white/90 border border-slate-200/60 px-4 py-2.5 shadow-sm">
        {/* Left: Mode controls */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Generation Mode Toggle */}
          <div className="flex items-center rounded-lg border border-slate-200 bg-slate-50 p-0.5">
            <button
              onClick={() => setMode('individual')}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all",
                mode === 'individual'
                  ? "bg-white text-slate-900 shadow-sm"
                  : "text-slate-500 hover:text-slate-700"
              )}
            >
              <Zap className="h-3.5 w-3.5" />
              Rápido
            </button>
            <button
              onClick={() => setMode('multi-agent')}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all",
                mode === 'multi-agent'
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-500 hover:text-slate-700"
              )}
            >
              <Users className="h-3.5 w-3.5" />
              Comitê
            </button>
          </div>

          <div className="h-5 w-px bg-slate-200 hidden sm:block" />

          {/* Chat Mode Toggle */}
          <div className="flex items-center rounded-lg border border-slate-200 bg-slate-50 p-0.5">
            <button
              onClick={() => handleSetChatMode('standard')}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all",
                chatMode !== 'multi-model'
                  ? "bg-white text-slate-900 shadow-sm"
                  : "text-slate-500 hover:text-slate-700"
              )}
            >
              <User className="h-3.5 w-3.5" />
              Normal
            </button>
            <button
              onClick={() => handleSetChatMode('multi-model')}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all",
                chatMode === 'multi-model'
                  ? "bg-amber-500 text-white shadow-sm"
                  : "text-slate-500 hover:text-slate-700"
              )}
            >
              <Scale className="h-3.5 w-3.5" />
              Comparar
            </button>
          </div>

          <div className="h-5 w-px bg-slate-200 hidden sm:block" />

          {/* Chat Personality Toggle */}
          <div className="flex items-center rounded-lg border border-slate-200 bg-slate-50 p-0.5">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => setChatPersonality('juridico')}
                    className={cn(
                      "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all",
                      chatPersonality === 'juridico'
                        ? "bg-emerald-600 text-white shadow-sm"
                        : "text-slate-500 hover:text-slate-700"
                    )}
                  >
                    <Scale className="h-3.5 w-3.5" />
                    Jurídico
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>Linguagem técnica e formal.</p>
                </TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => setChatPersonality('geral')}
                    className={cn(
                      "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all",
                      chatPersonality === 'geral'
                        ? "bg-sky-500 text-white shadow-sm"
                        : "text-slate-500 hover:text-slate-700"
                    )}
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    Livre
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>Assistente geral, sem formalidades jurídicas.</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-8 rounded-lg text-xs"
            onClick={handleOpenQuality}
          >
            <Scale className="mr-1.5 h-3.5 w-3.5" />
            Auditoria
          </Button>

          <Button
            variant="ghost"
            size="icon"
            className={cn("h-8 w-8 rounded-lg", showSettings && "bg-slate-100")}
            onClick={() => setShowSettings(!showSettings)}
          >
            <Settings2 className="h-4 w-4" />
          </Button>

          <Button
            variant="outline"
            size="sm"
            className="h-8 rounded-lg text-xs"
            onClick={handleStartNewMinuta}
          >
            <FileText className="mr-1.5 h-3.5 w-3.5" />
            Nova
          </Button>

          <Button
            size="sm"
            className="h-8 rounded-lg bg-indigo-600 text-xs hover:bg-indigo-700"
            onClick={handleGenerate}
            disabled={isSending || isLoading}
          >
            <Sparkles className="mr-1.5 h-3.5 w-3.5" />
            Gerar
          </Button>
        </div>
      </div>

      {/* Expanded Settings Panel */}
      {showSettings && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 rounded-xl border border-indigo-200/60 bg-indigo-50/30 px-4 py-3 animate-in slide-in-from-top-1 duration-200">
          {/* Document Type */}
          <div className="space-y-1.5">
            <label className="text-[10px] font-semibold uppercase text-indigo-700/70">Tipo de Documento</label>
            <select
              className="w-full text-xs h-8 rounded-lg border border-indigo-200/60 bg-white px-2.5 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition"
              value={useChatStore.getState().documentType || 'PETICAO_INICIAL'}
              onChange={(e) => useChatStore.getState().setDocumentType(e.target.value)}
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

          {/* Effort Level */}
          <div className="space-y-1.5">
            <label className="text-[10px] font-semibold uppercase text-indigo-700/70">Nível de Rigor</label>
            <div className="flex items-center gap-0.5">
              {[1, 2, 3, 4, 5].map((level) => (
                <button
                  key={level}
                  onClick={() => setEffortLevel(level)}
                  className={cn(
                    "h-8 flex-1 rounded-md text-xs font-bold transition-all",
                    effortLevel >= level
                      ? "bg-indigo-600 text-white"
                      : "bg-white text-indigo-300 border border-indigo-200/60 hover:bg-indigo-50"
                  )}
                >
                  {level}
                </button>
              ))}
            </div>
          </div>

          {/* Page Range */}
          <div className="space-y-1.5">
            <label className="text-[10px] font-semibold uppercase text-indigo-700/70">Intervalo de páginas</label>
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
              <button
                type="button"
                className={cn(
                  "h-7 flex-1 rounded-md text-[10px] font-semibold transition-all",
                  minPages === 5 && maxPages === 8
                    ? "bg-indigo-600 text-white"
                    : "bg-white text-indigo-400 border border-indigo-200/60 hover:bg-indigo-50"
                )}
                onClick={() => setPageRange({ minPages: 5, maxPages: 8 })}
              >
                Curta
              </button>
              <button
                type="button"
                className={cn(
                  "h-7 flex-1 rounded-md text-[10px] font-semibold transition-all",
                  minPages === 10 && maxPages === 15
                    ? "bg-indigo-600 text-white"
                    : "bg-white text-indigo-400 border border-indigo-200/60 hover:bg-indigo-50"
                )}
                onClick={() => setPageRange({ minPages: 10, maxPages: 15 })}
              >
                Média
              </button>
              <button
                type="button"
                className={cn(
                  "h-7 flex-1 rounded-md text-[10px] font-semibold transition-all",
                  minPages === 20 && maxPages === 30
                    ? "bg-indigo-600 text-white"
                    : "bg-white text-indigo-400 border border-indigo-200/60 hover:bg-indigo-50"
                )}
                onClick={() => setPageRange({ minPages: 20, maxPages: 30 })}
              >
                Longa
              </button>
            </div>
          </div>

          {/* Reasoning Level */}
          <div className="space-y-1.5">
            <label className="text-[10px] font-semibold uppercase text-indigo-700/70">Nível de Raciocínio</label>
            <div className="flex items-center gap-0.5">
              {(['low', 'medium', 'high'] as const).map((level) => (
                <button
                  key={level}
                  onClick={() => setReasoningLevel(level)}
                  className={cn(
                    "h-8 flex-1 rounded-md text-xs font-bold transition-all",
                    reasoningLevel === level
                      ? "bg-purple-600 text-white"
                      : "bg-white text-purple-300 border border-purple-200/60 hover:bg-purple-50"
                  )}
                >
                  {level === 'low' ? 'Rápido' : level === 'medium' ? 'Médio' : 'Profundo'}
                </button>
              ))}
            </div>
          </div>

          {/* Committee Models (Only if Multi-Agent) */}
          {mode === 'multi-agent' && (
            <div className="col-span-full space-y-2 pt-2 border-t border-indigo-200/40 mt-1">
              <label className="text-[10px] font-semibold uppercase text-indigo-700/70 flex items-center gap-2">
                <Users className="h-3 w-3" /> Modelos do Comitê de Agentes
              </label>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {/* Strategist */}
                <div className="space-y-1">
                  <span className="text-[10px] text-slate-500 font-medium">Estrategista (Planejamento)</span>
                  <select
                    className="w-full text-[10px] h-7 rounded border border-indigo-200 bg-white"
                    value={agentStrategistModel}
                    onChange={(e) => setAgentStrategistModel(e.target.value)}
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
                  <span className="text-[10px] text-slate-500 font-medium">Redator (multi-seleção, máx 3)</span>
                  <div className="space-y-1 rounded border border-indigo-200 bg-white p-2">
                    {agentModelOptions.map((model) => (
                      <label
                        key={model.id}
                        className={cn(
                          "flex items-center gap-2 text-[10px] text-slate-600",
                          !agentDrafterModels.includes(model.id) && agentDrafterModels.length >= MAX_ROLE_MODELS
                            ? "opacity-60 cursor-not-allowed"
                            : "cursor-pointer"
                        )}
                      >
                        <input
                          type="checkbox"
                          className="rounded border-indigo-300 text-indigo-600 focus:ring-indigo-500/20 h-3 w-3"
                          checked={agentDrafterModels.includes(model.id)}
                          disabled={!agentDrafterModels.includes(model.id) && agentDrafterModels.length >= MAX_ROLE_MODELS}
                          onChange={() => toggleAgentModel(agentDrafterModels, model.id, setAgentDrafterModels, "redator")}
                        />
                        <span>{model.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
                {/* Reviewer */}
                <div className="space-y-1">
                  <span className="text-[10px] text-slate-500 font-medium">Revisor (multi-seleção, máx 3)</span>
                  <div className="space-y-1 rounded border border-indigo-200 bg-white p-2">
                    {agentModelOptions.map((model) => (
                      <label
                        key={model.id}
                        className={cn(
                          "flex items-center gap-2 text-[10px] text-slate-600",
                          !agentReviewerModels.includes(model.id) && agentReviewerModels.length >= MAX_ROLE_MODELS
                            ? "opacity-60 cursor-not-allowed"
                            : "cursor-pointer"
                        )}
                      >
                        <input
                          type="checkbox"
                          className="rounded border-indigo-300 text-indigo-600 focus:ring-indigo-500/20 h-3 w-3"
                          checked={agentReviewerModels.includes(model.id)}
                          disabled={!agentReviewerModels.includes(model.id) && agentReviewerModels.length >= MAX_ROLE_MODELS}
                          onChange={() => toggleAgentModel(agentReviewerModels, model.id, setAgentReviewerModels, "revisor")}
                        />
                        <span>{model.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Research Options */}
          <div className="space-y-1.5">
            <label className="text-[10px] font-semibold uppercase text-indigo-700/70">Pesquisa</label>
            <div className="flex flex-col gap-1">
              <label className="flex items-center gap-2 text-xs cursor-pointer">
                <input
                  type="checkbox"
                  className="rounded border-indigo-300 text-indigo-600 focus:ring-indigo-500/20 h-3.5 w-3.5"
                  checked={webSearch}
                  onChange={(e) => useChatStore.getState().setWebSearch(e.target.checked)}
                />
                <span className="text-slate-600">Web Search</span>
              </label>
              <label className="flex items-center gap-2 text-xs cursor-pointer">
                <input
                  type="checkbox"
                  className="rounded border-indigo-300 text-indigo-600 focus:ring-indigo-500/20 h-3.5 w-3.5"
                  checked={denseResearch}
                  onChange={(e) => useChatStore.getState().setDenseResearch(e.target.checked)}
                />
                <span className="text-slate-600">Deep Research</span>
              </label>
            </div>
          </div>

          {/* Control Options */}
          <div className="space-y-1.5">
            <label className="text-[10px] font-semibold uppercase text-indigo-700/70">Controle</label>
            <label className="flex items-center gap-2 text-xs cursor-pointer opacity-60">
              <input
                type="checkbox"
                className="rounded border-indigo-300 text-indigo-600 focus:ring-indigo-500/20 h-3.5 w-3.5"
                checked={true}
                readOnly
              />
              <span className="text-slate-600">Aprovar Outline (HIL)</span>
            </label>
          </div>
        </div>
      )}

      {/* Main Content Area - Resizable Layout */}
      <div className="flex-1 h-full flex flex-row gap-0 min-h-0 overflow-hidden">
        {/* Left Panel: Chat - Resizable via CSS, hidden when canvas is expanded */}
        <div
          className={cn(
            "flex min-h-0 h-full flex-col rounded-l-xl border border-slate-200/60 bg-white shadow-sm overflow-hidden resize-x transition-all duration-300",
            canvasState === 'expanded' && "hidden"
          )}
          style={{ width: canvasState === 'expanded' ? '0%' : '45%', minWidth: canvasState === 'expanded' ? '0px' : '300px', maxWidth: '70%' }}
        >
          {/* Mode Status Bar */}
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-slate-100 bg-slate-50/50">
            <div className={cn(
              "flex h-2 w-2 rounded-full",
              mode === 'multi-agent' ? "bg-indigo-500 animate-pulse" : "bg-emerald-500"
            )} />
            <span className={cn(
              "text-xs font-medium",
              mode === 'multi-agent' ? "text-indigo-600" : "text-emerald-600"
            )}>
              {mode === 'multi-agent' ? 'Comitê de Agentes' : 'Modo Direto'}
            </span>
          </div>

          {/* Agent Progress (Multi-Agent only) */}
          {mode === 'multi-agent' && isAgentRunning && agentSteps.length > 0 && (
            <div className="border-b border-indigo-100 bg-indigo-50/50 p-3">
              <h3 className="mb-2 text-[10px] font-semibold text-indigo-600 uppercase tracking-wider flex items-center justify-between">
                <span>Processo Multi-Agente</span>
                {agentSteps.some(s => s.status === 'working') && <Loader2 className="h-3 w-3 animate-spin" />}
              </h3>
              <div className="space-y-1.5 max-h-[120px] overflow-y-auto">
                {agentSteps.map((step) => (
                  <div key={step.id} className="flex items-center gap-2">
                    <div className={cn(
                      "flex h-4 w-4 items-center justify-center rounded-full flex-shrink-0",
                      step.status === 'completed' && "bg-emerald-100 text-emerald-600",
                      step.status === 'working' && "bg-indigo-100 text-indigo-600",
                      step.status === 'pending' && "bg-slate-100 text-slate-400",
                    )}>
                      {step.status === 'completed' && <CheckCircle2 className="h-3 w-3" />}
                      {step.status === 'working' && <Loader2 className="h-3 w-3 animate-spin" />}
                      {step.status === 'pending' && <Circle className="h-3 w-3" />}
                    </div>
                    <span className={cn(
                      "text-xs truncate",
                      step.status === 'working' ? "text-indigo-700 font-medium" : "text-slate-600"
                    )}>
                      {getAgentLabel(step.agent)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Chat Content */}
          <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
            {currentChat ? (
              <ChatInterface chatId={currentChat.id} hideInput={false} />
            ) : (
              <>
                {/* Empty state message */}
                <div className="flex-1 flex flex-col items-center justify-center gap-4 p-6 text-center">
                  <div className={cn(
                    "rounded-2xl p-5",
                    mode === 'multi-agent' ? "bg-indigo-100" : "bg-slate-100"
                  )}>
                    {mode === 'multi-agent'
                      ? <Users className="h-10 w-10 text-indigo-400" />
                      : <Sparkles className="h-10 w-10 text-slate-400" />
                    }
                  </div>
                  <div>
                    <p className="text-base font-semibold text-slate-900 mb-1">Pronto para começar</p>
                    <p className="text-sm text-slate-500 max-w-[280px]">
                      {mode === 'multi-agent'
                        ? 'O comitê de agentes irá colaborar para gerar seu documento jurídico.'
                        : 'O modelo irá gerar seu documento diretamente.'}
                    </p>
                  </div>
                </div>
                {/* Chat Input always visible */}
                <div className="border-t bg-card p-3">
                  <ChatInput
                    onSend={async (content) => {
                      try {
                        const newChat = await createChat('Nova Minuta');
                        if (newChat) {
                          await sendMessage(content);
                        }
                      } catch (e) {
                        toast.error('Erro ao enviar mensagem');
                      }
                    }}
                    disabled={isSending}
                  />
                </div>
              </>
            )}
          </div>

          {/* Fontes Panel (Collapsible) */}
          <div className="border-t border-slate-100">
            <button
              onClick={() => setShowFontes(!showFontes)}
              className="w-full flex items-center justify-between px-4 py-2.5 text-xs font-medium text-slate-500 hover:bg-slate-50 transition-colors"
            >
              <div className="flex items-center gap-2">
                <FileSearch className="h-4 w-4" />
                <span>Fontes RAG</span>
                <span className="text-[10px] bg-slate-100 px-2 py-0.5 rounded-full text-slate-600">
                  {contextItems.length}
                </span>
              </div>
              {showFontes ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
            </button>

            {showFontes && (
              <div className="max-h-[150px] overflow-y-auto p-3 bg-slate-50/50 space-y-1.5">
                {contextItems.length > 0 ? (
                  contextItems.map((item: ContextItem, idx: number) => (
                    <div key={idx} className="flex items-center gap-2 text-sm p-2.5 rounded-lg bg-white border border-slate-100">
                      <BookOpen className="h-4 w-4 text-indigo-500 flex-shrink-0" />
                      <span className="truncate text-slate-600">{item.name || `Documento ${idx + 1}`}</span>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-slate-400 text-center py-3">
                    Nenhum documento no contexto.
                  </p>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right Panel: Canvas */}
        {canvasState !== 'hidden' && (
          <div className={cn(
            "min-h-0 h-full rounded-r-xl border border-l-0 border-slate-200/60 bg-white shadow-sm overflow-hidden transition-all duration-300",
            canvasState === 'expanded' ? "flex-1 rounded-xl border-l" : "flex-1"
          )}>
            <CanvasContainer />
          </div>
        )}
      </div>

      {/* HIL Modals */}
      <OutlineApprovalModal
        isOpen={showOutlineModal}
        onClose={handleOutlineReject}
        onApprove={handleOutlineApprove}
        onReject={handleOutlineReject}
        initialSections={initialSections}
        documentType={useChatStore.getState().documentType || 'Documento'}
      />
    </div>
  );
}
