import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { useChatStore } from '@/stores';
import { useAuthStore } from '@/stores/auth-store';
import { useContextStore } from '@/stores/context-store';
import { listModels } from '@/config/models';
import { type OutlineApprovalSection } from '@/components/dashboard/outline-approval-modal';
import { toast } from 'sonner';

import { useLayoutResize } from './use-layout-resize';
import { useChatCitations } from './use-chat-citations';
import { useChatActions } from './use-chat-actions';

export type GenerationMode = 'individual' | 'multi-agent';
export type QueryMode = 'auto' | 'edit' | 'answer';

export function useAskPageState(basePath: string) {
  // ---------------------------------------------------------------------------
  // Composed hooks
  // ---------------------------------------------------------------------------
  const layout = useLayoutResize();
  const citationsHook = useChatCitations();
  const actions = useChatActions(basePath);

  // ---------------------------------------------------------------------------
  // Stores (remaining fields not covered by composed hooks)
  // ---------------------------------------------------------------------------
  const {
    currentChat,
    isLoading,
    isSending,
    setContext,
    useMultiAgent,
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
    retryProgress,
    selectedModel,
    setSelectedModel,
    searchMode,
    setSearchMode,
    multiQuery,
    setMultiQuery,
    breadthFirst,
    setBreadthFirst,
    hilOutlineEnabled,
    setHilOutlineEnabled,
    autoApproveHil,
    setAutoApproveHil,
    chatOutlineReviewEnabled,
    setChatOutlineReviewEnabled,
    auditMode,
    setAuditMode,
    qualityProfile,
    setQualityProfile,
    qualityTargetSectionScore,
    setQualityTargetSectionScore,
    qualityTargetFinalScore,
    setQualityTargetFinalScore,
    qualityMaxRounds,
    setQualityMaxRounds,
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
    hilSectionPolicyOverride,
    setHilSectionPolicyOverride,
    hilFinalRequiredOverride,
    setHilFinalRequiredOverride,
    documentChecklist,
    setDocumentChecklist,
    cragMinBestScoreOverride,
    setCragMinBestScoreOverride,
    cragMinAvgScoreOverride,
    setCragMinAvgScoreOverride,
    forceGranularDebate,
    setForceGranularDebate,
    maxDivergenceHilRounds,
    setMaxDivergenceHilRounds,
    formattingOptions,
    setFormattingOptions,
    citationStyle,
    setCitationStyle,
    graphHops,
    setGraphHops,
    webSearch,
    webSearchModel,
    setWebSearchModel,
    denseResearch,
    deepResearchProvider,
    setDeepResearchProvider,
    deepResearchModel,
    setDeepResearchModel,
    reasoningLevel,
    setReasoningLevel,
    researchPolicy,
    setResearchPolicy,
    agentStrategistModel,
    setAgentStrategistModel,
    agentDrafterModels,
    setAgentDrafterModels,
    agentReviewerModels,
    setAgentReviewerModels,
    chatPersonality,
    setChatPersonality,
    creativityMode,
    setCreativityMode,
    temperatureOverride,
    setTemperatureOverride,
  } = useChatStore();

  const { items: contextItems, removeItem } = useContextStore();
  const { isAuthenticated } = useAuthStore();

  // ---------------------------------------------------------------------------
  // Local state
  // ---------------------------------------------------------------------------
  const mode: GenerationMode = useMultiAgent ? 'multi-agent' : 'individual';
  const setMode = useCallback(
    (nextMode: GenerationMode) => {
      setUseMultiAgent(nextMode === 'multi-agent');
    },
    [setUseMultiAgent],
  );
  const [queryMode, setQueryMode] = useState<QueryMode>('auto');
  const [showSettings, setShowSettings] = useState(false);
  const [showToolbar, setShowToolbar] = useState(true);
  const [showFontes, setShowFontes] = useState(false);
  const [showSourcesPanel, setShowSourcesPanel] = useState(false);

  // ---------------------------------------------------------------------------
  // Refs
  // ---------------------------------------------------------------------------
  const autoCreateAttemptedRef = useRef(false);

  // ---------------------------------------------------------------------------
  // Router
  // ---------------------------------------------------------------------------
  const params = useParams<{ chatId?: string | string[] }>();

  const routeChatId = (() => {
    const raw = params?.chatId as unknown;
    if (typeof raw === 'string') return raw;
    if (Array.isArray(raw) && typeof raw[0] === 'string') return raw[0];
    return null;
  })();

  const activeChatId = routeChatId || currentChat?.id || null;

  // ---------------------------------------------------------------------------
  // Model options
  // ---------------------------------------------------------------------------
  const agentModelOptions = listModels({ forAgents: true });
  const baseModelOptions = listModels({ forJuridico: true });

  // ---------------------------------------------------------------------------
  // Derived values
  // ---------------------------------------------------------------------------
  const isChatEmpty = !currentChat?.messages || currentChat.messages.length === 0;

  // ---------------------------------------------------------------------------
  // Effects
  // ---------------------------------------------------------------------------

  // Sync agent strategist model when multi-agent
  useEffect(() => {
    if (mode !== 'multi-agent') return;
    if (agentStrategistModel === selectedModel) return;
    setAgentStrategistModel(selectedModel);
  }, [mode, agentStrategistModel, selectedModel, setAgentStrategistModel]);

  // Sync context items to ChatStore
  useEffect(() => {
    setContext(contextItems);
  }, [contextItems, setContext]);

  // Auto-create chat on mount if none exists
  useEffect(() => {
    if (!isAuthenticated || autoCreateAttemptedRef.current) return;
    if (currentChat) return;

    autoCreateAttemptedRef.current = true;
    actions.createChat().catch(() => {
      toast.error('Erro ao criar conversa');
    });
  }, [isAuthenticated, currentChat, actions]);

  // ---------------------------------------------------------------------------
  // handleMessageSent (depends on queryMode — stays here)
  // ---------------------------------------------------------------------------
  const handleMessageSent = useCallback(
    (content: string) => {
      const draftKeywords = [
        'redija', 'escreva', 'elabore', 'minuta', 'peticao', 'parecer',
        'draft', 'write', 'memo', 'memorando', 'contrato', 'acordo',
      ];

      const shouldOpenCanvas = draftKeywords.some((keyword) =>
        content.toLowerCase().includes(keyword),
      );

      if (shouldOpenCanvas && queryMode === 'auto') {
        layout.showCanvas();
        layout.setCanvasState('normal');
      }
    },
    [queryMode, layout],
  );

  // handleSend wraps handleMessageSent + store.sendMessage
  const handleSend = useCallback(
    async (content: string) => {
      handleMessageSent(content);

      if (!currentChat) {
        try {
          await actions.createChat();
        } catch {
          toast.error('Erro ao criar conversa');
          return;
        }
      }

      actions.sendMessage(content);
    },
    [handleMessageSent, actions, currentChat],
  );

  // ---------------------------------------------------------------------------
  // Contextual suggestions
  // ---------------------------------------------------------------------------
  const contextualSuggestions = useMemo(() => {
    if (contextItems.length === 0) return [];
    const firstItem = contextItems[0];
    return [
      `Analise ${firstItem.name}`,
      `Resuma os pontos principais`,
      `Compare com a legislacao vigente`,
    ];
  }, [contextItems]);

  // ---------------------------------------------------------------------------
  // HIL logic
  // ---------------------------------------------------------------------------
  const isChatOutlineReview =
    reviewData?.checkpoint === 'outline' && (reviewData as any)?.mode === 'chat';
  const showOutlineModal =
    (reviewData?.checkpoint === 'outline' || reviewData?.type === 'outline_review') &&
    !isChatOutlineReview;
  const outlinePayload = reviewData?.review_data?.outline || reviewData?.outline || [];

  const initialSections: OutlineApprovalSection[] = Array.isArray(outlinePayload)
    ? outlinePayload.map((s: string | any, i: number) =>
        typeof s === 'string' ? { id: `sect-${i}`, title: s } : s,
      )
    : [];

  const handleOutlineApprove = async (sections: OutlineApprovalSection[]) => {
    try {
      await submitReview({ approved: true, outline: sections });
      toast.success('Estrutura aprovada! Agentes iniciando redacao...');
    } catch {
      toast.error('Erro ao enviar aprovacao.');
    }
  };

  const handleOutlineReject = async () => {
    try {
      await submitReview({ approved: false, comment: 'Usuario cancelou no modal.' });
      toast.info('Geracao cancelada.');
    } catch {
      toast.error('Erro ao rejeitar.');
    }
  };

  // ---------------------------------------------------------------------------
  // Agent label helper
  // ---------------------------------------------------------------------------
  const getAgentLabel = (agent: string) => {
    switch (agent) {
      case 'strategist':
        return 'Estrategista';
      case 'researcher':
        return 'Pesquisador';
      case 'drafter':
        return 'Redator';
      case 'reviewer':
        return 'Revisor';
      case 'judge':
        return 'Juiz';
      default:
        return agent;
    }
  };

  // ---------------------------------------------------------------------------
  // Return (same interface as before)
  // ---------------------------------------------------------------------------
  return {
    // Chat store
    currentChat: actions.currentChat,
    createChat: actions.createChat,
    setCurrentChat: actions.setCurrentChat,
    sendMessage: actions.sendMessage,
    startAgentGeneration: actions.startAgentGeneration,
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
    retryProgress,
    selectedModel,
    setSelectedModel,
    searchMode,
    setSearchMode,
    multiQuery,
    setMultiQuery,
    breadthFirst,
    setBreadthFirst,
    hilOutlineEnabled,
    setHilOutlineEnabled,
    autoApproveHil,
    setAutoApproveHil,
    chatOutlineReviewEnabled,
    setChatOutlineReviewEnabled,
    auditMode,
    setAuditMode,
    qualityProfile,
    setQualityProfile,
    qualityTargetSectionScore,
    setQualityTargetSectionScore,
    qualityTargetFinalScore,
    setQualityTargetFinalScore,
    qualityMaxRounds,
    setQualityMaxRounds,
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
    hilSectionPolicyOverride,
    setHilSectionPolicyOverride,
    hilFinalRequiredOverride,
    setHilFinalRequiredOverride,
    documentChecklist,
    setDocumentChecklist,
    cragMinBestScoreOverride,
    setCragMinBestScoreOverride,
    cragMinAvgScoreOverride,
    setCragMinAvgScoreOverride,
    forceGranularDebate,
    setForceGranularDebate,
    maxDivergenceHilRounds,
    setMaxDivergenceHilRounds,
    formattingOptions,
    setFormattingOptions,
    citationStyle,
    setCitationStyle,
    graphHops,
    setGraphHops,
    chatMode: actions.chatMode,
    setChatMode: actions.setChatMode,
    selectedModels: actions.selectedModels,
    setSelectedModels: actions.setSelectedModels,
    setShowMultiModelComparator: actions.setShowMultiModelComparator,
    webSearch,
    webSearchModel,
    setWebSearchModel,
    denseResearch,
    deepResearchProvider,
    setDeepResearchProvider,
    deepResearchModel,
    setDeepResearchModel,
    reasoningLevel,
    setReasoningLevel,
    researchPolicy,
    setResearchPolicy,
    agentStrategistModel,
    setAgentStrategistModel,
    agentDrafterModels,
    setAgentDrafterModels,
    agentReviewerModels,
    setAgentReviewerModels,
    chatPersonality,
    setChatPersonality,
    creativityMode,
    setCreativityMode,
    temperatureOverride,
    setTemperatureOverride,

    // Canvas store (from layout hook)
    canvasState: layout.canvasState,
    showCanvas: layout.showCanvas,
    hideCanvas: layout.hideCanvas,
    setCanvasState: layout.setCanvasState,
    setActiveTab: layout.setActiveTab,

    // Context store
    contextItems,
    removeItem,

    // Auth store
    isAuthenticated,

    // Local state
    mode,
    setMode,
    queryMode,
    setQueryMode,
    showSettings,
    setShowSettings,
    showToolbar,
    setShowToolbar,
    showFontes,
    setShowFontes,
    showSourcesPanel,
    setShowSourcesPanel,
    chatPanelWidth: layout.chatPanelWidth,
    setChatPanelWidth: layout.setChatPanelWidth,
    isResizing: layout.isResizing,
    isFullscreen: layout.isFullscreen,
    pendingFullscreenTarget: layout.pendingFullscreenTarget,

    // Refs
    pageRootRef: layout.pageRootRef,
    splitContainerRef: layout.splitContainerRef,
    chatPanelRef: layout.chatPanelRef,
    canvasPanelRef: layout.canvasPanelRef,
    autoCreateAttemptedRef,

    // Router
    router: actions.router,
    params,
    routeChatId,
    activeChatId,

    // Model options
    DEFAULT_COMPARE_MODELS: actions.DEFAULT_COMPARE_MODELS,
    agentModelOptions,
    baseModelOptions,

    // Derived values (from layout hook)
    layoutMode: layout.layoutMode,
    chatActive: layout.chatActive,
    canvasActive: layout.canvasActive,
    isChatEmpty,

    // Fullscreen API (from layout hook)
    fullscreenApi: layout.fullscreenApi,
    enterFullscreen: layout.enterFullscreen,
    exitFullscreen: layout.exitFullscreen,

    // Handlers
    handleSetChatMode: actions.handleSetChatMode,
    handleStartNewChat: actions.handleStartNewChat,
    handleGenerate: actions.handleGenerate,
    handleOpenQuality: actions.handleOpenQuality,
    handleOpenCitationEvidence: citationsHook.handleOpenCitationEvidence,
    handleToggleFullscreen: layout.handleToggleFullscreen,
    toggleChatMode: layout.toggleChatMode,
    toggleCanvasMode: layout.toggleCanvasMode,
    handleDividerPointerDown: layout.handleDividerPointerDown,
    updateChatWidthFromPointer: layout.updateChatWidthFromPointer,
    handleMessageSent,
    handleSend,
    handleShareChat: actions.handleShareChat,
    handleExportChat: actions.handleExportChat,

    // Data extraction (from citations hook)
    citations: citationsHook.citations,
    streamingStatus: citationsHook.streamingStatus,
    stepsCount: citationsHook.stepsCount,
    routedPages: citationsHook.routedPages,
    routedDocumentRoute: citationsHook.routedDocumentRoute,

    // Contextual suggestions
    contextualSuggestions,

    // HIL logic
    isChatOutlineReview,
    showOutlineModal,
    outlinePayload,
    initialSections,
    handleOutlineApprove,
    handleOutlineReject,

    // Agent label helper
    getAgentLabel,
  };
}
