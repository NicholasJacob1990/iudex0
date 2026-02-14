'use client';

import React, { useMemo } from 'react';
import { useAskPageState } from '@/hooks/use-ask-page-state';
import { ChatInterface, ChatInput } from '@/components/chat';
import { CanvasContainer, OutlineApprovalModal, MinutaSettingsDrawer } from '@/components/dashboard';
import { AskSourcesPanel, AskStreamingStatus } from '@/components/ask';
import { Button } from '@/components/ui/button';
import { RichTooltip } from '@/components/ui/rich-tooltip';
import { tintToColor, mixHex, LIGHT_STOPS, DARK_STOPS } from '@/components/layout/top-nav';
import { getChatTintStyles } from '@/lib/chat-tint-styles';
import { useTheme } from 'next-themes';
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
  Sparkles,
  Users,
  User,
  Zap,
  Scale,
  Settings2,
  CheckCircle2,
  Circle,
  Loader2,
  ChevronDown,
  ChevronUp,
  MoreHorizontal,
} from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import { useChatStore, useUIStore } from '@/stores';

// Sugestões estáticas para quando não há mensagens (modo individual)
const INITIAL_SUGGESTIONS = [
  { icon: FileText, label: 'Analise este contrato', desc: 'Upload e análise de documentos' },
  { icon: Search, label: 'Pesquise jurisprudência sobre...', desc: 'Busca em tribunais e legislação' },
  { icon: FileText, label: 'Redija uma petição inicial', desc: 'Geração de peças processuais' },
  { icon: BookOpen, label: 'Explique o artigo 5º da CF', desc: 'Consulta e explicação de leis' },
];

export default function AskPage() {
  const s = useAskPageState('/ask');
  const { chatBgTintLight, chatBgTintDark, tintMode } = useUIStore();
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';
  const activeTint = isDark ? chatBgTintDark : chatBgTintLight;

  const chatBg = useMemo(
    () => tintToColor(activeTint, isDark ? DARK_STOPS : LIGHT_STOPS),
    [activeTint, isDark],
  );
  const toolbarStyle = useMemo(
    () => ({
      backgroundColor: mixHex(chatBg, isDark ? '#0f1115' : '#ffffff', 0.88),
      borderColor: mixHex(chatBg, isDark ? '#334155' : '#cbd5e1', 0.35),
    }),
    [chatBg, isDark],
  );
  const toolbarGroupStyle = useMemo(
    () => ({
      backgroundColor: mixHex(chatBg, isDark ? '#111827' : '#ffffff', 0.72),
      borderColor: mixHex(chatBg, isDark ? '#475569' : '#d1d5db', 0.25),
    }),
    [chatBg, isDark],
  );
  const { messageAreaStyle, assistantBubbleStyle, inputAreaStyle, canvasStyle } = useMemo(
    () => getChatTintStyles({ tintMode, isDark, chatBg }),
    [chatBg, isDark, tintMode],
  );

  return (
    <div
      ref={s.pageRootRef}
      className="flex h-[calc(100vh-64px)] transition-colors duration-500 ease-out"
      style={{ backgroundColor: chatBg }}
    >
      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* ── Toolbar ── */}
        {s.showToolbar ? (
        <header
          className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 border-b backdrop-blur supports-[backdrop-filter]:bg-transparent/60 transition-colors duration-500"
          style={toolbarStyle}
        >
          {/* Left: Mode controls + streaming status */}
          <div className="flex flex-wrap items-center gap-3">
            {/* Generation Mode Toggle: Rápido / Comitê */}
            <div className="flex items-center rounded-lg border p-0.5 transition-colors duration-500" style={toolbarGroupStyle}>
              <RichTooltip
                title="Modo Chat (Rápido)"
                description="Conversa livre e rápida. Ideal para tirar dúvidas pontuais ou pedir resumos."
                badge="1 modelo"
                icon={<Zap className="h-3.5 w-3.5" />}
              >
                <button
                  type="button"
                  onClick={() => {
                    s.setMode('individual');
                    s.hideCanvas();
                  }}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all",
                    s.mode === 'individual'
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  <Zap className="h-3.5 w-3.5" />
                  Rápido
                </button>
              </RichTooltip>
              <RichTooltip
                title="Modo Minuta (Comitê)"
                description="Geração de documentos complexos com múltiplos agentes verificando a consistência jurídica."
                badge="Multi‑agente"
                icon={<Users className="h-3.5 w-3.5" />}
              >
                <button
                  type="button"
                  onClick={() => {
                    s.setMode('multi-agent');
                    s.showCanvas();
                  }}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all",
                    s.mode === 'multi-agent'
                      ? "bg-indigo-600 text-white shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  <Users className="h-3.5 w-3.5" />
                  Comitê
                </button>
              </RichTooltip>
            </div>

            <div className="h-5 w-px bg-border hidden sm:block" />

            {/* Chat Mode Toggle: Normal / Comparar */}
            <div className="flex items-center rounded-lg border p-0.5 transition-colors duration-500" style={toolbarGroupStyle}>
              <RichTooltip
                title="Chat Normal"
                description="Conversa com um único modelo. Ideal para iterações rápidas."
                badge="1 resposta"
                icon={<User className="h-3.5 w-3.5" />}
              >
                <button
                  type="button"
                  onClick={() => s.handleSetChatMode('standard')}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all",
                    s.chatMode !== 'multi-model'
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  <User className="h-3.5 w-3.5" />
                  Normal
                </button>
              </RichTooltip>
              <RichTooltip
                title="Comparar modelos"
                description="Respostas paralelas para avaliar argumentos e escolher a melhor abordagem."
                badge="2–3 respostas"
                icon={<Scale className="h-3.5 w-3.5" />}
              >
                <button
                  type="button"
                  onClick={() => s.handleSetChatMode('multi-model')}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all",
                    s.chatMode === 'multi-model'
                      ? "bg-amber-500 text-white shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  <Scale className="h-3.5 w-3.5" />
                  Comparar
                </button>
              </RichTooltip>
            </div>

            {/* Streaming Status */}
            <AskStreamingStatus
              status={s.streamingStatus}
              stepsCount={s.stepsCount}
              isStreaming={s.isSending}
              minPages={s.minPages}
              maxPages={s.maxPages}
              estimatedPages={s.routedPages}
              documentRoute={s.routedDocumentRoute}
            />
          </div>

          {/* Right: Actions */}
          <div className="flex items-center gap-2">
            {/* Auditoria */}
            <Button
              variant="outline"
              size="sm"
              className="h-8 rounded-lg text-xs"
              onClick={s.handleOpenQuality}
            >
              <Scale className="mr-1.5 h-3.5 w-3.5" />
              Auditoria
            </Button>

            {/* Layout Toggle: Chat / Split / Canvas */}
            <div className="flex items-center rounded-md border p-0.5 transition-colors duration-500" style={toolbarGroupStyle}>
              <button
                type="button"
                onClick={s.toggleChatMode}
                className={cn(
                  "rounded px-2 py-1 text-xs font-medium transition-all",
                  s.layoutMode === 'chat'
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
                  s.showCanvas();
                  s.setCanvasState('normal');
                }}
                className={cn(
                  "rounded px-2 py-1 text-xs font-medium transition-all",
                  s.layoutMode === 'split'
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                )}
                title="Dividido"
              >
                <Columns2 className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={s.toggleCanvasMode}
                className={cn(
                  "rounded px-2 py-1 text-xs font-medium transition-all",
                  s.layoutMode === 'canvas'
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                )}
                title="Apenas Canvas"
              >
                <LayoutTemplate className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* Fullscreen */}
            {s.fullscreenApi.supported && (
              <Button
                variant="ghost"
                size="icon"
                onClick={s.handleToggleFullscreen}
                className="h-8 w-8"
                title={s.isFullscreen ? 'Sair da tela cheia' : 'Tela cheia'}
              >
                {s.isFullscreen ? (
                  <Minimize2 className="h-4 w-4" />
                ) : (
                  <Maximize2 className="h-4 w-4" />
                )}
              </Button>
            )}

            {/* Settings gear */}
            <Button
              variant="ghost"
              size="icon"
              className={cn("h-8 w-8", s.showSettings && "bg-accent")}
              onClick={() => s.setShowSettings(!s.showSettings)}
            >
              <Settings2 className="h-4 w-4" />
            </Button>

            {/* Novo chat */}
            <Button
              variant="outline"
              size="sm"
              className="h-8 rounded-lg text-xs"
              onClick={s.handleStartNewChat}
            >
              <FileText className="mr-1.5 h-3.5 w-3.5" />
              Novo chat
            </Button>

            {/* Gerar (multi-agent) */}
            {s.mode === 'multi-agent' && (
              <Button
                size="sm"
                className="h-8 rounded-lg bg-indigo-600 text-xs hover:bg-indigo-700"
                onClick={s.handleGenerate}
                disabled={s.isSending || s.isLoading}
              >
                <Sparkles className="mr-1.5 h-3.5 w-3.5" />
                Gerar
              </Button>
            )}

            {/* Compartilhar & Exportar (agrupados) */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8">
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={s.handleShareChat}>
                  <Share2 className="mr-2 h-4 w-4" />
                  Compartilhar
                </DropdownMenuItem>
                <DropdownMenuItem onClick={s.handleExportChat}>
                  <Download className="mr-2 h-4 w-4" />
                  Exportar
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Sources panel toggle */}
            <Button
              variant="ghost"
              size="icon"
              onClick={() => s.setShowSourcesPanel(!s.showSourcesPanel)}
              className={cn(s.showSourcesPanel && 'bg-accent')}
            >
              {s.showSourcesPanel ? (
                <PanelRightClose className="h-4 w-4" />
              ) : (
                <PanelRight className="h-4 w-4" />
              )}
            </Button>

            {/* Hide toolbar toggle */}
            <button
              type="button"
              onClick={() => s.setShowToolbar(false)}
              className="ml-1 p-1 rounded text-muted-foreground/40 hover:text-muted-foreground transition-colors"
              title="Esconder barra"
            >
              <ChevronUp className="h-3.5 w-3.5" />
            </button>
          </div>
        </header>
        ) : (
          /* Collapsed toolbar: thin bar with expand button */
          <div
            className="flex items-center justify-center border-b transition-colors duration-500"
            style={toolbarStyle}
          >
            <button
              type="button"
              onClick={() => s.setShowToolbar(true)}
              className="w-full py-0.5 flex items-center justify-center text-muted-foreground/30 hover:text-muted-foreground/60 transition-colors"
              title="Mostrar barra de ferramentas"
            >
              <ChevronDown className="h-3 w-3" />
            </button>
          </div>
        )}

        {/* ── Split View: Thread + Canvas ── */}
        <div
          ref={s.splitContainerRef}
          className="flex-1 flex flex-row gap-0 min-h-0 overflow-hidden"
        >
          {/* Chat Panel (resizable) */}
          <div
            ref={s.chatPanelRef}
            className={cn(
              "relative flex flex-col min-w-0 transition-[width,opacity,transform] duration-300 ease-in-out will-change-[width]",
              s.layoutMode === 'split' ? 'border-r border-border' : '',
              s.canvasState === 'expanded' ? 'hidden w-0 opacity-0' : '',
              s.isFullscreen && s.pendingFullscreenTarget === 'chat' ? 'fixed inset-0 z-50 w-full h-full' : ''
            )}
            style={{
              width: s.canvasState === 'normal' ? `${s.chatPanelWidth}%` : '100%',
            }}
          >
            {/* Agent Steps Progress (multi-agent only) */}
            {s.mode === 'multi-agent' && s.isAgentRunning && s.agentSteps.length > 0 && (
              <div className="border-b border-indigo-100 bg-indigo-50/50 dark:bg-indigo-950/20 p-3">
                <h3 className="mb-2 text-[10px] font-semibold text-indigo-600 uppercase tracking-wider flex items-center justify-between">
                  <span>Processo Multi-Agente</span>
                  {s.agentSteps.some((step: any) => step.status === 'working') && (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  )}
                </h3>
                <div className="space-y-1.5 max-h-[120px] overflow-y-auto">
                  {s.agentSteps.map((step: any) => (
                    <div key={step.id} className="flex items-center gap-2">
                      <div className={cn(
                        "flex h-4 w-4 items-center justify-center rounded-full flex-shrink-0",
                        step.status === 'completed' && "bg-emerald-100 text-emerald-600",
                        step.status === 'working' && "bg-indigo-100 text-indigo-600",
                        step.status === 'pending' && "bg-muted text-muted-foreground",
                      )}>
                        {step.status === 'completed' && <CheckCircle2 className="h-3 w-3" />}
                        {step.status === 'working' && <Loader2 className="h-3 w-3 animate-spin" />}
                        {step.status === 'pending' && <Circle className="h-3 w-3" />}
                      </div>
                      <span className={cn(
                        "text-xs truncate",
                        step.status === 'working' ? "text-indigo-700 font-medium" : "text-muted-foreground"
                      )}>
                        {s.getAgentLabel(step.agent)}
                      </span>
                    </div>
                  ))}
                </div>
                {/* Retry Progress */}
                {s.retryProgress?.isRetrying && (
                  <div className="mt-2 pt-2 border-t border-indigo-200/50">
                    <div className="flex items-center gap-2 text-xs">
                      <div className="flex h-4 w-4 items-center justify-center rounded-full bg-amber-100 text-amber-600 flex-shrink-0">
                        <Loader2 className="h-3 w-3 animate-spin" />
                      </div>
                      <span className="text-amber-700 font-medium">
                        Tentando novamente ({s.retryProgress?.progress || '...'})
                      </span>
                    </div>
                    {s.retryProgress?.reason && (
                      <p className="text-[10px] text-amber-600/80 mt-1 ml-6">
                        Razão: {s.retryProgress?.reason === 'missing_citations_for_jurisprudence'
                          ? 'Faltam citações de jurisprudência'
                          : s.retryProgress?.reason}
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Chat Content - conditional by mode */}
            <div className="flex-1 overflow-y-auto min-h-0">
              {s.currentChat && (s.mode === 'multi-agent' || !s.isChatEmpty) ? (
                <ChatInterface
                  chatId={s.currentChat.id}
                  hideInput={s.mode === 'individual'}
                  autoCanvasOnDocumentRequest={s.mode === 'multi-agent'}
                  showCanvasButton={s.mode === 'multi-agent'}
                  messageAreaStyle={messageAreaStyle}
                  assistantBubbleStyle={assistantBubbleStyle}
                  inputAreaStyle={inputAreaStyle}
                />
              ) : s.mode === 'multi-agent' ? (
                /* Multi-agent empty state */
                <div className="flex-1 flex flex-col items-center justify-center gap-4 p-6 text-center h-full">
                  <div className="rounded-2xl p-5 bg-indigo-100 dark:bg-indigo-950/30">
                    <Users className="h-10 w-10 text-indigo-400" />
                  </div>
                  <div>
                    <p className="text-base font-semibold text-foreground mb-1">Pronto para começar</p>
                    <p className="text-sm text-muted-foreground max-w-[280px]">
                      O comitê de agentes irá colaborar para gerar seu documento jurídico.
                    </p>
                  </div>
                </div>
              ) : (
                /* Individual empty state (Ask-style suggestions) */
                <div className="flex flex-col items-center justify-center h-full p-8">
                  <div className="text-center mb-8">
                    <h2 className="text-2xl font-semibold text-foreground mb-2">
                      Como posso ajudar?
                    </h2>
                    <p className="text-muted-foreground">
                      Faça uma pergunta jurídica ou escolha uma sugestão abaixo
                    </p>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-lg">
                    {INITIAL_SUGGESTIONS.map((item) => (
                      <button
                        key={item.label}
                        type="button"
                        onClick={() => s.handleSend(item.label)}
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

                  {s.contextualSuggestions.length > 0 && (
                    <div className="mt-6 w-full max-w-lg">
                      <p className="text-xs text-muted-foreground mb-2">
                        Baseado nas fontes selecionadas:
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {s.contextualSuggestions.map((suggestion) => (
                          <button
                            key={suggestion}
                            type="button"
                            onClick={() => s.handleSend(suggestion)}
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

            {/* Input Area (individual mode: standalone input; multi-agent: built-in in ChatInterface) */}
            {s.mode === 'individual' && (
              <div className="border-t px-4 py-1.5 shrink-0 transition-colors duration-500" style={inputAreaStyle}>
                <div className="max-w-5xl mx-auto">
                  <ChatInput
                    onSend={s.handleSend}
                    placeholder="Faça sua pergunta jurídica... (Digite '/' para prompts, '@' para contexto)"
                  />
                </div>
              </div>
            )}
          </div>

          {/* Resizable Divider */}
          {s.canvasState === 'normal' && (
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label="Redimensionar painel"
              tabIndex={0}
              className={cn(
                "relative w-3 cursor-col-resize bg-transparent touch-none",
                "before:absolute before:left-1/2 before:top-0 before:h-full before:w-px before:-translate-x-1/2 before:bg-border",
                "hover:before:w-0.5 hover:before:bg-primary/50",
                s.isResizing && "bg-muted before:bg-primary"
              )}
              onPointerDown={s.handleDividerPointerDown}
              onKeyDown={(e) => {
                const step = e.shiftKey ? 5 : 1;
                if (e.key === 'ArrowLeft') {
                  e.preventDefault();
                  s.setChatPanelWidth((w: number) => Math.max(20, w - step));
                } else if (e.key === 'ArrowRight') {
                  e.preventDefault();
                  s.setChatPanelWidth((w: number) => Math.min(70, w + step));
                }
              }}
            >
              <div className="absolute inset-0" />
            </div>
          )}

          {/* Canvas Area */}
          {s.canvasState !== 'hidden' && (
            <div
              ref={s.canvasPanelRef}
              className="min-h-0 h-full flex-1 bg-background overflow-hidden transition-[flex-grow,width,opacity,transform,background-color] duration-300 ease-in-out"
              style={canvasStyle}
            >
              <CanvasContainer mode={s.mode === 'multi-agent' ? 'full' : 'chat'} />
            </div>
          )}
        </div>
      </div>

      {/* Sources Panel (lateral) */}
      {s.showSourcesPanel && (
        <div className="w-80 shrink-0 border-l">
          <AskSourcesPanel
            citations={s.citations}
            onClose={() => s.setShowSourcesPanel(false)}
            contextItems={s.contextItems}
            onRemoveItem={s.removeItem}
            onOpenEvidence={s.handleOpenCitationEvidence}
          />
        </div>
      )}

      {/* HIL Modal */}
      <OutlineApprovalModal
        isOpen={s.showOutlineModal}
        onClose={s.handleOutlineReject}
        onApprove={s.handleOutlineApprove}
        onReject={s.handleOutlineReject}
        initialSections={s.initialSections}
        documentType={useChatStore.getState().documentType || 'Documento'}
      />

      {/* Settings Drawer (lateral direita) */}
      <MinutaSettingsDrawer
        open={s.showSettings}
        onOpenChange={s.setShowSettings}
        mode={s.mode}
        chatMode={s.chatMode}
        onSetChatMode={s.handleSetChatMode}
        chatPersonality={s.chatPersonality}
        setChatPersonality={s.setChatPersonality}
        queryMode={s.queryMode}
        setQueryMode={s.setQueryMode}
        documentType={useChatStore.getState().documentType || 'PETICAO_INICIAL'}
        setDocumentType={(t: string) => useChatStore.getState().setDocumentType(t)}
        minPages={s.minPages}
        maxPages={s.maxPages}
        setPageRange={s.setPageRange}
        resetPageRange={s.resetPageRange}
        formattingOptions={s.formattingOptions}
        setFormattingOptions={s.setFormattingOptions}
        citationStyle={s.citationStyle}
        setCitationStyle={s.setCitationStyle}
        graphHops={s.graphHops}
        setGraphHops={s.setGraphHops}
        reasoningLevel={(['low', 'medium', 'high'].includes(s.reasoningLevel) ? s.reasoningLevel : 'medium') as 'low' | 'medium' | 'high'}
        setReasoningLevel={s.setReasoningLevel}
        effortLevel={s.effortLevel}
        setEffortLevel={s.setEffortLevel}
        creativityMode={s.creativityMode}
        setCreativityMode={s.setCreativityMode}
        temperatureOverride={s.temperatureOverride}
        setTemperatureOverride={s.setTemperatureOverride}
        qualityProfile={s.qualityProfile}
        setQualityProfile={s.setQualityProfile}
        qualityTargetSectionScore={s.qualityTargetSectionScore}
        setQualityTargetSectionScore={s.setQualityTargetSectionScore}
        qualityTargetFinalScore={s.qualityTargetFinalScore}
        setQualityTargetFinalScore={s.setQualityTargetFinalScore}
        qualityMaxRounds={s.qualityMaxRounds}
        setQualityMaxRounds={s.setQualityMaxRounds}
        researchPolicy={s.researchPolicy}
        setResearchPolicy={s.setResearchPolicy}
        webSearch={s.webSearch}
        setWebSearch={(v: boolean) => useChatStore.getState().setWebSearch(v)}
        denseResearch={s.denseResearch}
        setDenseResearch={(v: boolean) => useChatStore.getState().setDenseResearch(v)}
        searchMode={s.searchMode}
        setSearchMode={s.setSearchMode}
        multiQuery={s.multiQuery}
        setMultiQuery={s.setMultiQuery}
        breadthFirst={s.breadthFirst}
        setBreadthFirst={s.setBreadthFirst}
        deepResearchProvider={s.deepResearchProvider}
        setDeepResearchProvider={s.setDeepResearchProvider}
        deepResearchModel={s.deepResearchModel}
        setDeepResearchModel={s.setDeepResearchModel}
        webSearchModel={s.webSearchModel}
        setWebSearchModel={s.setWebSearchModel}
        auditMode={s.auditMode}
        setAuditMode={s.setAuditMode}
        selectedModel={s.selectedModel}
        setSelectedModel={s.setSelectedModel}
        agentStrategistModel={s.agentStrategistModel}
        agentDrafterModels={s.agentDrafterModels}
        setAgentDrafterModels={s.setAgentDrafterModels}
        agentReviewerModels={s.agentReviewerModels}
        setAgentReviewerModels={s.setAgentReviewerModels}
        selectedModels={s.selectedModels}
        setSelectedModels={s.setSelectedModels}
        setShowMultiModelComparator={s.setShowMultiModelComparator}
        baseModelOptions={s.baseModelOptions}
        agentModelOptions={s.agentModelOptions}
        hilOutlineEnabled={s.hilOutlineEnabled}
        setHilOutlineEnabled={s.setHilOutlineEnabled}
        autoApproveHil={s.autoApproveHil}
        setAutoApproveHil={s.setAutoApproveHil}
        chatOutlineReviewEnabled={s.chatOutlineReviewEnabled}
        setChatOutlineReviewEnabled={s.setChatOutlineReviewEnabled}
        hilSectionPolicyOverride={s.hilSectionPolicyOverride}
        setHilSectionPolicyOverride={s.setHilSectionPolicyOverride}
        hilFinalRequiredOverride={s.hilFinalRequiredOverride}
        setHilFinalRequiredOverride={s.setHilFinalRequiredOverride}
        qualityMaxFinalReviewLoops={s.qualityMaxFinalReviewLoops}
        setQualityMaxFinalReviewLoops={s.setQualityMaxFinalReviewLoops}
        qualityStyleRefineMaxRounds={s.qualityStyleRefineMaxRounds}
        setQualityStyleRefineMaxRounds={s.setQualityStyleRefineMaxRounds}
        qualityMaxResearchVerifierAttempts={s.qualityMaxResearchVerifierAttempts}
        setQualityMaxResearchVerifierAttempts={s.setQualityMaxResearchVerifierAttempts}
        qualityMaxRagRetries={s.qualityMaxRagRetries}
        setQualityMaxRagRetries={s.setQualityMaxRagRetries}
        qualityRagRetryExpandScope={s.qualityRagRetryExpandScope}
        setQualityRagRetryExpandScope={s.setQualityRagRetryExpandScope}
        recursionLimitOverride={s.recursionLimitOverride}
        setRecursionLimitOverride={s.setRecursionLimitOverride}
        strictDocumentGateOverride={s.strictDocumentGateOverride}
        setStrictDocumentGateOverride={s.setStrictDocumentGateOverride}
        forceGranularDebate={s.forceGranularDebate}
        setForceGranularDebate={s.setForceGranularDebate}
        maxDivergenceHilRounds={s.maxDivergenceHilRounds}
        setMaxDivergenceHilRounds={s.setMaxDivergenceHilRounds}
        cragMinBestScoreOverride={s.cragMinBestScoreOverride}
        setCragMinBestScoreOverride={s.setCragMinBestScoreOverride}
        cragMinAvgScoreOverride={s.cragMinAvgScoreOverride}
        setCragMinAvgScoreOverride={s.setCragMinAvgScoreOverride}
        documentChecklist={s.documentChecklist}
        setDocumentChecklist={s.setDocumentChecklist}
      />
    </div>
  );
}
