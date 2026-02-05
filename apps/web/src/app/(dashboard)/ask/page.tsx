'use client';

import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
// useRouter available if needed for navigation
import { useChatStore, useCanvasStore } from '@/stores';
import { useAuthStore } from '@/stores/auth-store';
import { useContextStore } from '@/stores/context-store';
import { ChatInterface, ChatInput } from '@/components/chat';
import { SourcesBadge } from '@/components/chat/sources-badge';
import { CanvasContainer } from '@/components/dashboard';
import { AskSourcesPanel, AskStreamingStatus, AskModeToggle } from '@/components/ask';
import { Button } from '@/components/ui/button';
import {
  PanelRight,
  PanelRightClose,
  Share2,
  Download,
  FileText,
  Search,
  BookOpen,
  Maximize2,
  Minimize2,
  PanelLeft,
  Columns2,
  LayoutTemplate,
} from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
// apiClient available for future file upload feature

type QueryMode = 'auto' | 'edit' | 'answer';

// Sugestões estáticas para quando não há mensagens
const INITIAL_SUGGESTIONS = [
  { icon: FileText, label: 'Analise este contrato', desc: 'Upload e análise de documentos' },
  { icon: Search, label: 'Pesquise jurisprudência sobre...', desc: 'Busca em tribunais e legislação' },
  { icon: FileText, label: 'Redija uma petição inicial', desc: 'Geração de peças processuais' },
  { icon: BookOpen, label: 'Explique o artigo 5º da CF', desc: 'Consulta e explicação de leis' },
];

export default function AskPage() {
  const { isAuthenticated } = useAuthStore();
  const autoCreateAttemptedRef = useRef(false);

  // Refs for resizable panels
  const pageRootRef = useRef<HTMLDivElement>(null);
  const splitContainerRef = useRef<HTMLDivElement>(null);
  const chatPanelRef = useRef<HTMLDivElement>(null);
  const canvasPanelRef = useRef<HTMLDivElement>(null);

  // Chat store
  const {
    currentChat,
    createChat,
    sendMessage,
    isSending,
    setContext,
  } = useChatStore();

  // Canvas store
  const {
    state: canvasState,
    showCanvas,
    hideCanvas,
    setState: setCanvasState,
  } = useCanvasStore();

  // Context store
  const { items: contextItems, removeItem } = useContextStore();

  // Local state
  const [queryMode, setQueryMode] = useState<QueryMode>('auto');
  const [showSourcesPanel, setShowSourcesPanel] = useState(true);

  // Resizable panel state
  const [chatPanelWidth, setChatPanelWidth] = useState(50);
  const [isResizing, setIsResizing] = useState(false);
  const dragRectRef = useRef<DOMRect | null>(null);
  const rafRef = useRef<number | null>(null);

  // Fullscreen state
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [pendingFullscreenTarget, setPendingFullscreenTarget] = useState<'chat' | 'canvas' | 'split' | null>(null);

  // Derived layout mode
  const layoutMode: 'chat' | 'split' | 'canvas' =
    canvasState === 'hidden' ? 'chat' : canvasState === 'expanded' ? 'canvas' : 'split';

  // Sync context items to ChatStore
  useEffect(() => {
    setContext(contextItems);
  }, [contextItems, setContext]);

  // Auto-create chat on mount
  useEffect(() => {
    if (!isAuthenticated || autoCreateAttemptedRef.current) return;
    if (currentChat) return;

    autoCreateAttemptedRef.current = true;
    createChat().catch(() => {
      toast.error('Erro ao criar conversa');
    });
  }, [isAuthenticated, currentChat, createChat]);

  // Track browser fullscreen state
  useEffect(() => {
    if (typeof document === 'undefined') return;
    const onChange = () => setIsFullscreen(!!document.fullscreenElement);
    onChange();
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);

  // Handle resize cursor state
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

  // Clamp width on window resize
  useEffect(() => {
    const container = splitContainerRef.current;
    if (!container) return;

    const handleResize = () => {
      const rect = container.getBoundingClientRect();
      if (!rect.width) return;
      const minPx = 300;
      const maxPx = Math.max(minPx, rect.width * 0.7); // Ensure max >= min
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

  // Fullscreen API
  const fullscreenApi = useMemo(() => {
    if (typeof document === 'undefined') return { supported: false as const };
    const supported = typeof document.documentElement?.requestFullscreen === 'function';
    return { supported };
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

  // Handle pending fullscreen target
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

  // Resize handlers - using cached rect and RAF for performance
  const updateChatWidthFromPointer = useCallback((clientX: number) => {
    const rect = dragRectRef.current;
    if (!rect || !rect.width) return;

    const minPx = 300;
    const maxPx = Math.max(minPx, rect.width * 0.7); // Ensure max >= min
    const rawPx = clientX - rect.left;
    const clampedPx = Math.min(Math.max(rawPx, minPx), maxPx);
    setChatPanelWidth((clampedPx / rect.width) * 100);
  }, []);

  const handleDividerPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (canvasState !== 'normal') return;
    event.preventDefault();

    // Cache rect at drag start for performance
    const container = splitContainerRef.current;
    if (container) {
      dragRectRef.current = container.getBoundingClientRect();
    }

    setIsResizing(true);
  };

  // Global listeners for resize (more robust than element listeners)
  useEffect(() => {
    if (!isResizing) return;

    const handlePointerMove = (event: PointerEvent) => {
      // Use RAF for throttling
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

  // Layout toggle functions
  const toggleChatMode = () => {
    if (layoutMode === 'chat') {
      showCanvas();
      setCanvasState('normal');
      return;
    }
    hideCanvas();
  };

  const toggleCanvasMode = () => {
    if (layoutMode === 'canvas') {
      showCanvas();
      setCanvasState('normal');
      return;
    }
    showCanvas();
    setCanvasState('expanded');
  };

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

  // Extract last assistant message data
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
      status = `Concluído em ${completedSteps} etapa${completedSteps > 1 ? 's' : ''}`;
    }

    return {
      citations: formattedCitations,
      streamingStatus: status,
      stepsCount: steps.length,
    };
  }, [currentChat?.messages, isSending]);

  // Handle canvas auto-open based on content type (keywords)
  const handleMessageSent = useCallback((content: string) => {
    const draftKeywords = [
      'redija', 'escreva', 'elabore', 'minuta', 'petição', 'parecer',
      'draft', 'write', 'memo', 'memorando', 'contrato', 'acordo'
    ];

    const shouldOpenCanvas = draftKeywords.some(
      keyword => content.toLowerCase().includes(keyword)
    );

    if (shouldOpenCanvas && queryMode === 'auto') {
      showCanvas();
      setCanvasState('normal');
    }
  }, [queryMode, showCanvas, setCanvasState]);

  // Handle sending a message
  const handleSend = useCallback(async (content: string) => {
    handleMessageSent(content);

    // Create chat if it doesn't exist
    if (!currentChat) {
      try {
        await createChat();
      } catch {
        toast.error('Erro ao criar conversa');
        return;
      }
    }

    sendMessage(content);
  }, [handleMessageSent, sendMessage, currentChat, createChat]);

  // Generate contextual suggestions based on selected sources
  const contextualSuggestions = useMemo(() => {
    if (contextItems.length === 0) return [];

    const firstItem = contextItems[0];
    return [
      `Analise ${firstItem.name}`,
      `Resuma os pontos principais`,
      `Compare com a legislação vigente`,
    ];
  }, [contextItems]);

  // Check if chat is empty
  const isChatEmpty = !currentChat?.messages || currentChat.messages.length === 0;

  return (
    <div ref={pageRootRef} className="flex h-[calc(100vh-64px)] bg-background">
      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="flex items-center justify-between px-4 py-2 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-semibold">Ask</h1>
            {currentChat && (
              <span className="text-sm text-muted-foreground">
                {currentChat.title || 'Nova conversa'}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <AskStreamingStatus
              status={streamingStatus}
              stepsCount={stepsCount}
              isStreaming={isSending}
            />

            {/* Layout Toggle */}
            <div className="flex items-center rounded-md border border-border bg-muted/50 p-0.5">
              <button
                type="button"
                onClick={toggleChatMode}
                className={cn(
                  "rounded px-2 py-1 text-xs font-medium transition-all",
                  layoutMode === 'chat'
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                )}
                title="Apenas Chat"
              >
                <PanelLeft className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={() => {
                  showCanvas();
                  setCanvasState('normal');
                }}
                className={cn(
                  "rounded px-2 py-1 text-xs font-medium transition-all",
                  layoutMode === 'split'
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                )}
                title="Dividido"
              >
                <Columns2 className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={toggleCanvasMode}
                className={cn(
                  "rounded px-2 py-1 text-xs font-medium transition-all",
                  layoutMode === 'canvas'
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                )}
                title="Apenas Canvas"
              >
                <LayoutTemplate className="h-3.5 w-3.5" />
              </button>
            </div>

            {fullscreenApi.supported && (
              <Button
                variant="ghost"
                size="icon"
                onClick={handleToggleFullscreen}
                className="h-8 w-8"
                title={isFullscreen ? 'Sair da tela cheia' : 'Tela cheia'}
              >
                {isFullscreen ? (
                  <Minimize2 className="h-4 w-4" />
                ) : (
                  <Maximize2 className="h-4 w-4" />
                )}
              </Button>
            )}

            <Button variant="ghost" size="sm" className="gap-2">
              <Share2 className="h-4 w-4" />
              Share
            </Button>

            <Button variant="ghost" size="sm" className="gap-2">
              <Download className="h-4 w-4" />
              Export
            </Button>

            <Button
              variant="ghost"
              size="icon"
              onClick={() => setShowSourcesPanel(!showSourcesPanel)}
              className={cn(showSourcesPanel && 'bg-accent')}
            >
              {showSourcesPanel ? (
                <PanelRightClose className="h-4 w-4" />
              ) : (
                <PanelRight className="h-4 w-4" />
              )}
            </Button>
          </div>
        </header>

        {/* Split View: Thread + Canvas */}
        <div
          ref={splitContainerRef}
          className="flex-1 flex flex-row gap-0 min-h-0 overflow-hidden"
        >
          {/* Thread Area - Resizable */}
          <div
            ref={chatPanelRef}
            className={cn(
              "relative flex flex-col min-w-0 bg-background transition-[width,opacity,transform] duration-300 ease-in-out will-change-[width]",
              layoutMode === 'split' ? 'border-r border-border' : '',
              canvasState === 'expanded' ? 'hidden w-0 opacity-0' : '',
              isFullscreen && pendingFullscreenTarget === 'chat' ? 'fixed inset-0 z-50 w-full h-full' : ''
            )}
            style={{
              width: canvasState === 'normal' ? `${chatPanelWidth}%` : '100%',
            }}
          >
            {/* Chat Messages or Empty State */}
            <div className="flex-1 overflow-y-auto min-h-0">
              {currentChat && !isChatEmpty ? (
                <ChatInterface chatId={currentChat.id} hideInput />
              ) : (
                /* Empty State with Suggestions */
                <div className="flex flex-col items-center justify-center h-full p-8">
                  <div className="text-center mb-8">
                    <h2 className="text-2xl font-semibold text-foreground mb-2">
                      Como posso ajudar?
                    </h2>
                    <p className="text-muted-foreground">
                      Faça uma pergunta jurídica ou escolha uma sugestão abaixo
                    </p>
                  </div>

                  {/* Initial Suggestions Grid */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-lg">
                    {INITIAL_SUGGESTIONS.map((item) => (
                      <button
                        key={item.label}
                        type="button"
                        onClick={() => handleSend(item.label)}
                        className="group flex items-start gap-3 rounded-xl border border-border p-4 text-left hover:border-emerald-300 hover:bg-emerald-50/50 dark:hover:bg-emerald-950/20 transition-all"
                      >
                        <item.icon className="h-5 w-5 text-muted-foreground group-hover:text-emerald-600 transition-colors mt-0.5" />
                        <div>
                          <span className="text-sm font-medium text-foreground">{item.label}</span>
                          <p className="text-xs text-muted-foreground mt-0.5">{item.desc}</p>
                        </div>
                      </button>
                    ))}
                  </div>

                  {/* Contextual Suggestions (when sources are selected) */}
                  {contextualSuggestions.length > 0 && (
                    <div className="mt-6 w-full max-w-lg">
                      <p className="text-xs text-muted-foreground mb-2">
                        Baseado nas fontes selecionadas:
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {contextualSuggestions.map((suggestion) => (
                          <button
                            key={suggestion}
                            onClick={() => handleSend(suggestion)}
                            className="px-3 py-1.5 text-sm rounded-full border border-border hover:border-emerald-300 hover:bg-emerald-50/50 dark:hover:bg-emerald-950/20 transition-all"
                          >
                            {suggestion}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Input Area */}
            <div className="border-t p-4 pb-6 shrink-0">
              <div className="max-w-3xl mx-auto space-y-3">
                {/* Main Input */}
                <ChatInput onSend={handleSend} />

                {/* Sources & Mode Toggle */}
                <div className="flex items-center justify-between mt-2">
                  <div className="flex items-center gap-2">
                    <SourcesBadge />
                    {contextItems.length > 0 && (
                      <span className="text-xs text-muted-foreground">
                        {contextItems.length} fonte(s) selecionada(s)
                      </span>
                    )}
                  </div>

                  <AskModeToggle
                    mode={queryMode}
                    onChange={setQueryMode}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Resizable Divider */}
          {canvasState === 'normal' && (
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label="Redimensionar painel"
              tabIndex={0}
              className={cn(
                "relative w-3 cursor-col-resize bg-transparent touch-none",
                "before:absolute before:left-1/2 before:top-0 before:h-full before:w-px before:-translate-x-1/2 before:bg-border",
                "hover:before:w-0.5 hover:before:bg-primary/50",
                isResizing && "bg-muted before:bg-primary"
              )}
              onPointerDown={handleDividerPointerDown}
              onKeyDown={(e) => {
                // Keyboard accessibility for resize
                const step = e.shiftKey ? 5 : 1;
                if (e.key === 'ArrowLeft') {
                  e.preventDefault();
                  setChatPanelWidth((w) => Math.max(20, w - step));
                } else if (e.key === 'ArrowRight') {
                  e.preventDefault();
                  setChatPanelWidth((w) => Math.min(70, w + step));
                }
              }}
            >
              <div className="absolute inset-0" />
            </div>
          )}

          {/* Canvas Area */}
          {canvasState !== 'hidden' && (
            <div
              ref={canvasPanelRef}
              className="min-h-0 h-full flex-1 bg-background overflow-hidden transition-[flex-grow,width,opacity,transform] duration-300 ease-in-out"
            >
              <CanvasContainer />
            </div>
          )}
        </div>
      </div>

      {/* Sources Panel */}
      {showSourcesPanel && (
        <div className="w-80 shrink-0 border-l">
          <AskSourcesPanel
            citations={citations}
            onClose={() => setShowSourcesPanel(false)}
            contextItems={contextItems}
            onRemoveItem={removeItem}
          />
        </div>
      )}
    </div>
  );
}
