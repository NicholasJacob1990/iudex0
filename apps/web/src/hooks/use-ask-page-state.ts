import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useChatStore, useCanvasStore } from '@/stores';
import { useAuthStore } from '@/stores/auth-store';
import { useContextStore } from '@/stores/context-store';
import { listModels } from '@/config/models';
import { type OutlineApprovalSection } from '@/components/dashboard/outline-approval-modal';
import { toast } from 'sonner';

export type GenerationMode = 'individual' | 'multi-agent';
export type QueryMode = 'auto' | 'edit' | 'answer';

export function useAskPageState(basePath: string) {
  // ---------------------------------------------------------------------------
  // Stores
  // ---------------------------------------------------------------------------
  const {
    currentChat,
    createChat,
    setCurrentChat,
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
    chatMode,
    setChatMode,
    selectedModels,
    setSelectedModels,
    setShowMultiModelComparator,
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

  const {
    state: canvasState,
    showCanvas,
    hideCanvas,
    setState: setCanvasState,
    setActiveTab,
  } = useCanvasStore();

  const { items: contextItems, removeItem } = useContextStore();

  const { isAuthenticated } = useAuthStore();

  // ---------------------------------------------------------------------------
  // Local state
  // ---------------------------------------------------------------------------
  const [mode, setMode] = useState<GenerationMode>('individual');
  const [queryMode, setQueryMode] = useState<QueryMode>('auto');
  const [showSettings, setShowSettings] = useState(false);
  const [showFontes, setShowFontes] = useState(false);
  const [showSourcesPanel, setShowSourcesPanel] = useState(true);
  const [chatPanelWidth, setChatPanelWidth] = useState(50);
  const [isResizing, setIsResizing] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [pendingFullscreenTarget, setPendingFullscreenTarget] = useState<
    'chat' | 'canvas' | 'split' | null
  >(null);

  // ---------------------------------------------------------------------------
  // Refs
  // ---------------------------------------------------------------------------
  const pageRootRef = useRef<HTMLDivElement>(null);
  const splitContainerRef = useRef<HTMLDivElement>(null);
  const chatPanelRef = useRef<HTMLDivElement>(null);
  const canvasPanelRef = useRef<HTMLDivElement>(null);
  const autoCreateAttemptedRef = useRef(false);
  const dragRectRef = useRef<DOMRect | null>(null);
  const rafRef = useRef<number | null>(null);

  // ---------------------------------------------------------------------------
  // Router
  // ---------------------------------------------------------------------------
  const router = useRouter();
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
  const DEFAULT_COMPARE_MODELS = ['gpt-5.2', 'claude-4.5-sonnet', 'gemini-3-flash'];
  const agentModelOptions = listModels({ forAgents: true });
  const baseModelOptions = listModels({ forJuridico: true });

  // ---------------------------------------------------------------------------
  // Derived values
  // ---------------------------------------------------------------------------
  const layoutMode: 'chat' | 'split' | 'canvas' =
    canvasState === 'hidden' ? 'chat' : canvasState === 'expanded' ? 'canvas' : 'split';
  const chatActive = layoutMode !== 'canvas';
  const canvasActive = layoutMode !== 'chat';
  const isChatEmpty = !currentChat?.messages || currentChat.messages.length === 0;

  // ---------------------------------------------------------------------------
  // Effects
  // ---------------------------------------------------------------------------

  // 1. Sync mode -> store
  useEffect(() => {
    setUseMultiAgent(mode === 'multi-agent');
  }, [mode, setUseMultiAgent]);

  // 2. Sync agent strategist model when multi-agent
  useEffect(() => {
    if (mode !== 'multi-agent') return;
    if (agentStrategistModel === selectedModel) return;
    setAgentStrategistModel(selectedModel);
  }, [mode, agentStrategistModel, selectedModel, setAgentStrategistModel]);

  // 3. Sync context items to ChatStore
  useEffect(() => {
    setContext(contextItems);
  }, [contextItems, setContext]);

  // 4. Track browser fullscreen state
  useEffect(() => {
    if (typeof document === 'undefined') return;
    const onChange = () => setIsFullscreen(!!document.fullscreenElement);
    onChange();
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);

  // 5. Handle resize cursor
  useEffect(() => {
    if (!isResizing) return;
    const { style } = document.body;
    const prevCursor = style.cursor;
    const prevUserSelect = style.userSelect;
    style.cursor = 'col-resize';
    style.userSelect = 'none';
    return () => {
      style.cursor = prevCursor;
      style.userSelect = prevUserSelect;
    };
  }, [isResizing]);

  // 6. Clamp width on window resize (min 300px, max 70%)
  useEffect(() => {
    const container = splitContainerRef.current;
    if (!container) return;

    const handleResize = () => {
      const rect = container.getBoundingClientRect();
      if (!rect.width) return;
      const minPx = 300;
      const maxPx = Math.max(minPx, rect.width * 0.7);
      const currentPx = (chatPanelWidth / 100) * rect.width;
      if (currentPx < minPx) {
        setChatPanelWidth((minPx / rect.width) * 100);
      } else if (currentPx > maxPx) {
        setChatPanelWidth((maxPx / rect.width) * 100);
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [chatPanelWidth]);

  // 7. Global pointer listeners for resize (RAF throttled)
  const updateChatWidthFromPointer = useCallback((clientX: number) => {
    const rect = dragRectRef.current;
    if (!rect || !rect.width) return;

    const minPx = 300;
    const maxPx = Math.max(minPx, rect.width * 0.7);
    const rawPx = clientX - rect.left;
    const clampedPx = Math.min(Math.max(rawPx, minPx), maxPx);
    setChatPanelWidth((clampedPx / rect.width) * 100);
  }, []);

  useEffect(() => {
    if (!isResizing) return;

    const handlePointerMove = (event: PointerEvent) => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        updateChatWidthFromPointer(event.clientX);
      });
    };

    const handlePointerUp = () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      dragRectRef.current = null;
      setIsResizing(false);
    };

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    window.addEventListener('pointercancel', handlePointerUp);
    window.addEventListener('blur', handlePointerUp);

    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
      window.removeEventListener('pointercancel', handlePointerUp);
      window.removeEventListener('blur', handlePointerUp);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [isResizing, updateChatWidthFromPointer]);

  // 8. Handle pending fullscreen target
  useEffect(() => {
    if (!pendingFullscreenTarget) return;
    if (typeof document === 'undefined') return;

    void (async () => {
      let targetEl: HTMLElement | null = null;
      if (pendingFullscreenTarget === 'chat') {
        targetEl = chatPanelRef.current;
      } else if (pendingFullscreenTarget === 'canvas') {
        targetEl = canvasPanelRef.current;
      } else {
        targetEl = pageRootRef.current;
      }
      await enterFullscreen(targetEl);
      setPendingFullscreenTarget(null);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingFullscreenTarget, layoutMode]);

  // 9. Auto-create chat on mount if none exists
  useEffect(() => {
    if (!isAuthenticated || autoCreateAttemptedRef.current) return;
    if (currentChat) return;

    autoCreateAttemptedRef.current = true;
    createChat().catch(() => {
      toast.error('Erro ao criar conversa');
    });
  }, [isAuthenticated, currentChat, createChat]);

  // ---------------------------------------------------------------------------
  // Fullscreen API
  // ---------------------------------------------------------------------------
  const fullscreenApi = useMemo(() => {
    if (typeof document === 'undefined') return { supported: false as const };
    return {
      supported: typeof document.documentElement?.requestFullscreen === 'function',
    };
  }, []);

  const enterFullscreen = async (target?: HTMLElement | null) => {
    if (!fullscreenApi.supported) return;
    try {
      const el = target || pageRootRef.current || document.documentElement;
      // @ts-ignore
      await el.requestFullscreen?.();
    } catch {
      // ignore
    }
  };

  const exitFullscreen = async () => {
    if (typeof document === 'undefined') return;
    if (!document.fullscreenElement) return;
    try {
      await document.exitFullscreen();
    } catch {
      // ignore
    }
  };

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  // 1. handleSetChatMode
  const handleSetChatMode = (next: 'standard' | 'multi-model') => {
    if (next === 'multi-model') {
      const nextModels =
        selectedModels.length >= 2
          ? selectedModels
          : selectedModels.length === 1
            ? [
                selectedModels[0],
                DEFAULT_COMPARE_MODELS.find((m) => m !== selectedModels[0]) || 'gpt-5.2',
              ]
            : DEFAULT_COMPARE_MODELS.slice(0, 3);

      setSelectedModels(nextModels);
      setShowMultiModelComparator(true);
      setChatMode('multi-model');
      return;
    }

    if (selectedModels.length > 1) setSelectedModels([selectedModels[0]]);
    setChatMode('standard');
  };

  // 2. handleStartNewChat
  const handleStartNewChat = async () => {
    try {
      const newChat = await createChat();
      toast.success('Nova conversa criada!');
      if (newChat?.id) {
        router.push(`${basePath}/${newChat.id}`);
      }
    } catch {
      toast.error('Erro ao criar conversa');
    }
  };

  // 3. handleGenerate
  const handleGenerate = async () => {
    try {
      let chat = currentChat;
      if (!chat && activeChatId) {
        await setCurrentChat(activeChatId);
        chat = useChatStore.getState().currentChat;
      }
      if (!chat) {
        chat = await createChat();
      }
      await startAgentGeneration('Gerar minuta baseada nos documentos selecionados.');
    } catch {
      // handled by store/toast
    }
  };

  // 4. handleOpenQuality
  const handleOpenQuality = () => {
    showCanvas();
    setActiveTab('audit');
  };

  // 5. handleToggleFullscreen
  const handleToggleFullscreen = () => {
    if (!fullscreenApi.supported) return;
    if (isFullscreen) {
      void exitFullscreen();
      return;
    }
    if (layoutMode === 'chat') {
      setPendingFullscreenTarget('chat');
      return;
    }
    if (layoutMode === 'canvas') {
      setPendingFullscreenTarget('canvas');
      return;
    }
    setPendingFullscreenTarget('split');
  };

  // 6. toggleChatMode
  const toggleChatMode = () => {
    if (layoutMode === 'chat') {
      showCanvas();
      setCanvasState('normal');
      return;
    }
    hideCanvas();
  };

  // 7. toggleCanvasMode
  const toggleCanvasMode = () => {
    if (layoutMode === 'canvas') {
      showCanvas();
      setCanvasState('normal');
      return;
    }
    showCanvas();
    setCanvasState('expanded');
  };

  // 8. handleDividerPointerDown
  const handleDividerPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (canvasState !== 'normal') return;
    event.preventDefault();

    const container = splitContainerRef.current;
    if (container) {
      dragRectRef.current = container.getBoundingClientRect();
    }

    setIsResizing(true);
  };

  // 9. updateChatWidthFromPointer is already defined above as useCallback

  // 10. handleMessageSent
  const handleMessageSent = useCallback(
    (content: string) => {
      const draftKeywords = [
        'redija',
        'escreva',
        'elabore',
        'minuta',
        'peticao',
        'parecer',
        'draft',
        'write',
        'memo',
        'memorando',
        'contrato',
        'acordo',
      ];

      const shouldOpenCanvas = draftKeywords.some((keyword) =>
        content.toLowerCase().includes(keyword),
      );

      if (shouldOpenCanvas && queryMode === 'auto') {
        showCanvas();
        setCanvasState('normal');
      }
    },
    [queryMode, showCanvas, setCanvasState],
  );

  // 11. handleSend
  const handleSend = useCallback(
    async (content: string) => {
      handleMessageSent(content);

      if (!currentChat) {
        try {
          await createChat();
        } catch {
          toast.error('Erro ao criar conversa');
          return;
        }
      }

      sendMessage(content);
    },
    [handleMessageSent, sendMessage, currentChat, createChat],
  );

  // ---------------------------------------------------------------------------
  // Data extraction (useMemo)
  // ---------------------------------------------------------------------------
  const { citations, streamingStatus, stepsCount } = useMemo(() => {
    const msgs = currentChat?.messages || [];

    // Find last assistant message
    let lastMsg = null;
    for (let i = msgs.length - 1; i >= 0; i -= 1) {
      if (msgs[i]?.role === 'assistant') {
        lastMsg = msgs[i];
        break;
      }
    }

    // Extract activity steps
    const steps = lastMsg?.metadata?.activity?.steps || [];

    // Extract citations and convert to AskSourcesPanel format
    const rawCitations = lastMsg?.metadata?.citations || [];
    const formattedCitations = rawCitations.map((cit: any, idx: number) => {
      let source = 'Fonte';
      try {
        if (cit.url) {
          source = new URL(cit.url).hostname;
        }
      } catch {
        source = cit.source || 'Fonte';
      }

      return {
        id: cit.number || String(idx + 1),
        title: cit.title || cit.url || `Fonte ${idx + 1}`,
        source,
        snippet: cit.quote || cit.excerpt,
        signal: cit.signal || 'neutral',
        url: cit.url,
      };
    });

    // Determine streaming status from steps
    const runningStep = steps.find((s: any) => s?.status === 'running');
    const completedSteps = steps.filter((s: any) => s?.status === 'done').length;

    let status = '';
    if (runningStep) {
      status = runningStep.title || 'Processando...';
    } else if (completedSteps > 0 && !isSending) {
      status = `Concluido em ${completedSteps} etapa${completedSteps > 1 ? 's' : ''}`;
    }

    return {
      citations: formattedCitations,
      streamingStatus: status,
      stepsCount: steps.length,
    };
  }, [currentChat?.messages, isSending]);

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
  // Return
  // ---------------------------------------------------------------------------
  return {
    // Chat store
    currentChat,
    createChat,
    setCurrentChat,
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
    chatMode,
    setChatMode,
    selectedModels,
    setSelectedModels,
    setShowMultiModelComparator,
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

    // Canvas store
    canvasState,
    showCanvas,
    hideCanvas,
    setCanvasState,
    setActiveTab,

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
    showFontes,
    setShowFontes,
    showSourcesPanel,
    setShowSourcesPanel,
    chatPanelWidth,
    setChatPanelWidth,
    isResizing,
    setIsResizing,
    isFullscreen,
    setIsFullscreen,
    pendingFullscreenTarget,
    setPendingFullscreenTarget,

    // Refs
    pageRootRef,
    splitContainerRef,
    chatPanelRef,
    canvasPanelRef,
    autoCreateAttemptedRef,
    dragRectRef,
    rafRef,

    // Router
    router,
    params,
    routeChatId,
    activeChatId,

    // Model options
    DEFAULT_COMPARE_MODELS,
    agentModelOptions,
    baseModelOptions,

    // Derived values
    layoutMode,
    chatActive,
    canvasActive,
    isChatEmpty,

    // Fullscreen API
    fullscreenApi,
    enterFullscreen,
    exitFullscreen,

    // Handlers
    handleSetChatMode,
    handleStartNewChat,
    handleGenerate,
    handleOpenQuality,
    handleToggleFullscreen,
    toggleChatMode,
    toggleCanvasMode,
    handleDividerPointerDown,
    updateChatWidthFromPointer,
    handleMessageSent,
    handleSend,

    // Data extraction
    citations,
    streamingStatus,
    stepsCount,

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
