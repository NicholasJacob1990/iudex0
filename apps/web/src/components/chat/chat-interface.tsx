'use client';

import React, { useEffect, useRef, useCallback, useMemo, useState, lazy, Suspense } from 'react';
import { useChatStore, useCanvasStore, useAuthStore } from '@/stores';
import { ChatMessage } from './chat-message';
import { MultiModelResponse } from './multi-model-response';
import { ChatInput } from './chat-input';
import { DeepResearchViewer } from './deep-research-viewer';
import { HardResearchViewer } from './hard-research-viewer';
import { CogRAGTreeViewer } from './cograg-tree-viewer';
import { ToolApprovalModal } from './tool-approval-modal';
import { ContextIndicatorCompact } from './context-indicator';
import { CheckpointTimeline } from './checkpoint-timeline';
const LazyDiffConfirmDialog = lazy(() =>
  import('@/components/dashboard/diff-confirm-dialog').then(m => ({ default: m.DiffConfirmDialog }))
);
import { Loader2, Download, FileText, FileType, RotateCcw, Scissors, X, Copy, PanelRight, Search, BookOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { MessageBudgetModal } from '@/components/billing/message-budget-modal';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';

interface ChatInterfaceProps {
  chatId: string;
  hideInput?: boolean;
  placeholder?: string;
  autoCanvasOnDocumentRequest?: boolean;
  showCanvasButton?: boolean;
  renderBudgetModal?: boolean;
  messageAreaStyle?: React.CSSProperties;
  assistantBubbleStyle?: React.CSSProperties;
  inputAreaStyle?: React.CSSProperties;
}

export function ChatInterface({
  chatId,
  hideInput,
  placeholder,
  autoCanvasOnDocumentRequest = false,
  showCanvasButton = false,
  renderBudgetModal = true,
  messageAreaStyle,
  assistantBubbleStyle,
  inputAreaStyle,
}: ChatInterfaceProps) {
  const {
    currentChat, setCurrentChat, sendMessage, startAgentGeneration, isSending, isLoading,
    currentJobId, jobEvents,
    showMultiModelComparator, chatMode, selectedModel, selectedModels, denseResearch, deepResearchMode, useMultiAgent,
    multiModelDeepDebate, setMultiModelDeepDebate,
    billingModal, closeBillingModal, retryWithBudgetOverride,
    pendingToolApproval, approveToolCall, contextUsagePercent, compactConversation,
    checkpoints, restoreCheckpoint,
    cogragTree, cogragStatus,
  } = useChatStore();
  const {
    selectedText,
    selectionRange,
    selectionContext,
    clearSelectedText,
    applyTextReplacement,
    content: documentContent,
    showCanvas,
    setActiveTab,
  } = useCanvasStore();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const prevMessageCountRef = useRef<number>(0);
  const isNearBottomRef = useRef<boolean>(true);
  const [isCompacting, setIsCompacting] = useState(false);
  const [editPreviewOpen, setEditPreviewOpen] = useState(false);
  const [editPreview, setEditPreview] = useState<{
    original: string;
    edited: string;
    agents: string[];
    range: { from: number; to: number } | null;
  } | null>(null);
  const showDeepResearch = denseResearch && !!currentJobId;

  const latestTokenPercent = useMemo(() => {
    const msgs = (currentChat?.messages || []) as any[];
    for (let i = msgs.length - 1; i >= 0; i -= 1) {
      const m = msgs[i];
      const percent = m?.metadata?.token_usage?.limits?.percent_used;
      if (typeof percent === 'number' && Number.isFinite(percent)) {
        return percent;
      }
    }
    return null;
  }, [currentChat?.messages]);

  const latestTokenPercentLabel = useMemo(() => {
    if (latestTokenPercent === null) return null;
    return `${latestTokenPercent.toFixed(1)}%`;
  }, [latestTokenPercent]);

  const useDeepDebate = multiModelDeepDebate;

  const parseCanvasCommand = (raw: string) => {
    const trimmed = raw.trim();
    const match = trimmed.match(/^\/(?:canvas|doc|documento|minuta)(?:\s+(append|replace))?\b\s*(.*)$/i);
    if (!match) return null;
    const action = (match[1] || 'edit').toLowerCase() as 'edit' | 'append' | 'replace';
    return { action, payload: (match[2] || '').trim() };
  };

  const normalizeCanvasPrompt = (raw: string) => {
    const cleaned = raw
      .replace(/\bno\s+canvas\b/gi, '')
      .replace(/\bno\s+quadro\b/gi, '')
      .replace(/\bno\s+editor\b/gi, '')
      .replace(/\bno\s+documento\b/gi, '')
      .replace(/\bna\s+minuta\b/gi, '')
      .replace(/\bna\s+pe[cç]a\b/gi, '')
      .replace(/\bna\s+peti[cç]ao\b/gi, '')
      .replace(/\bna\s+inicial\b/gi, '')
      .replace(/\bna\s+contesta[cç][aã]o\b/gi, '')
      .replace(/\s{2,}/g, ' ')
      .trim();
    const target = cleaned || raw.trim();
    return [
      'Escreva o conteúdo final do documento solicitado.',
      'Evite mencionar canvas, interface ou limitações de UI.',
      `Solicitação: ${target}`,
    ].join('\n');
  };

  const openCanvas = () => {
    showCanvas();
    setActiveTab('editor');
  };

  const isCommandOrContextMessage = (raw: string) => {
    const trimmed = raw.trim();
    if (!trimmed) return false;
    if (/^[@/]/.test(trimmed)) return true;
    return /^(contexto|fatos|dados|informacoes|informações|anexos|documentos)\s*:/i.test(trimmed);
  };

  const isDocumentRequest = (raw: string) => {
    if (!autoCanvasOnDocumentRequest) return false;
    if (isCommandOrContextMessage(raw)) return false;
    const lower = raw.toLowerCase();
    return /\b(minuta|documento|pe[cç]a|peti[cç][aã]o|inicial|contesta[cç][aã]o|recurso|agravo|apela[cç][aã]o|mandado\s+de\s+seguran[cç]a|habeas|contrato|parecer|relat[oó]rio|manifest[aã]o|embargos|memorial|defesa|impugna[cç][aã]o|r[eé]plica|contrarraz[oõ]es|despacho|senten[cç]a|ac[oó]rd[aã]o|voto|ementa|not[ií]cia|procura[cç][aã]o|den[uú]ncia|queixa|libelo|ar[tg]ui[cç][aã]o)\b/.test(lower);
  };

  // Sync tenantId with user's organization
  const { user } = useAuthStore();
  const setTenantId = useChatStore((s) => s.setTenantId);
  useEffect(() => {
    const tid = user?.organization_id || user?.id || 'default';
    setTenantId(tid);
  }, [user?.organization_id, user?.id, setTenantId]);

  useEffect(() => {
    setCurrentChat(chatId);
  }, [chatId, setCurrentChat]);

  // Check if user is near the bottom of the scroll
  const checkIfNearBottom = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return true;
    const threshold = 100; // pixels from bottom
    return container.scrollHeight - container.scrollTop - container.clientHeight < threshold;
  }, []);

  // Throttled scroll handler using RAF
  const scrollRafRef = useRef<number | null>(null);
  const handleScroll = useCallback(() => {
    if (scrollRafRef.current !== null) return;
    scrollRafRef.current = requestAnimationFrame(() => {
      isNearBottomRef.current = checkIfNearBottom();
      scrollRafRef.current = null;
    });
  }, [checkIfNearBottom]);
  useEffect(() => {
    return () => {
      if (scrollRafRef.current !== null) cancelAnimationFrame(scrollRafRef.current);
    };
  }, []);

  // Only auto-scroll when new messages arrive AND user is near bottom
  useEffect(() => {
    const messageCount = currentChat?.messages?.length ?? 0;
    const prevCount = prevMessageCountRef.current;

    // Only scroll if new messages arrived (not on initial load when going from 0 to messages)
    if (messageCount > prevCount && prevCount > 0 && isNearBottomRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }

    prevMessageCountRef.current = messageCount;
  }, [currentChat?.messages]);

  const startDocumentEdit = async ({
    message,
    selection,
    selectionRange,
    selectionContext,
    isFullDocument = false,
  }: {
    message: string;
    selection?: string | null;
    selectionRange?: { from: number; to: number } | null;
    selectionContext?: { before: string; after: string } | null;
    isFullDocument?: boolean;
  }) => {
    if (!currentChat || !documentContent) return;

    // Determine mode: Single model -> Fast Mode; Multi-model -> Committee
    const isFastMode = chatMode !== 'multi-model';
    // Priority: selectedModels[0] (UI selection) > selectedModel (Judge default)
    const fastModel = (selectedModels && selectedModels.length > 0) ? selectedModels[0] : selectedModel;
    const models = isFastMode ? [fastModel] : undefined;
    const scopeLabel = isFullDocument ? 'documento' : 'trecho selecionado';

    // Add fake user message immediately for feedback
    useChatStore.getState().addMessage({
      id: `temp-${Date.now()}`,
      role: 'user',
      content: isFullDocument
        ? `[EDITANDO DOCUMENTO] ${message}`
        : `[EDITANDO] "${selection?.slice(0, 30) ?? ''}..." : ${message}`,
      timestamp: new Date().toISOString()
    });

    // Add optimistic system message
    const editModeLabel = isFastMode
      ? "Modo Chat"
      : (useDeepDebate ? "Minuta (Debate Profundo)" : "Minuta (Rápido)");

    useChatStore.getState().addMessage({
      id: `sys-${Date.now()}`,
      role: 'assistant',
      content: `Iniciando edição do ${scopeLabel} em **${editModeLabel}**...`,
      timestamp: new Date().toISOString()
    });

    toast.info(isFastMode ? `Editando ${scopeLabel}...` : `Minuta avaliando (${useDeepDebate ? '4 Rodadas' : 'Rápido'})...`);

    // Capture selection data at the start to avoid race conditions if user clicks away
    const capturedRange = selectionRange || null;
    const capturedContext = selectionContext || null;

    await apiClient.editDocumentWithCommittee(
      currentChat.id,
      {
        message,
        document: documentContent,
        selection: selection || undefined,
        selection_context_before: capturedContext?.before,
        selection_context_after: capturedContext?.after,
        models: models,
        use_debate: !isFastMode && useDeepDebate // User controlled toggle
      },
      (agent, text) => {
        // Optional: Show streaming thoughts in toast or temporary message
        console.log(`[${agent}]`, text);
      },
      (original, edited, agents) => {
        if (!original || !edited) {
          toast.error("Resposta inválida da edição.");
          return;
        }
        setEditPreview({
          original,
          edited,
          agents,
          range: capturedRange,
        });
        setEditPreviewOpen(true);
      },
      (error) => {
        toast.error(`Erro na edição: ${error}`);
      }
    );
  };

  const ensureChatSelected = async () => {
    // Guard against race condition: user can send before setCurrentChat finishes
    if (!chatId) return false;
    if (currentChat?.id !== chatId) {
      try {
        await setCurrentChat(chatId);
      } catch (e) {
        console.error('Error selecting chat before send:', e);
      }
    }
    return useChatStore.getState().currentChat?.id === chatId;
  };

  const handleSendMessage = async (content: string) => {
    try {
      const ready = await ensureChatSelected();
      if (!ready) {
        toast.error('Não foi possível carregar a conversa. Tente recarregar a página.');
        return;
      }

      const canvasCommand = parseCanvasCommand(content);
      if (canvasCommand !== null) {
        openCanvas();
        if (!canvasCommand.payload) {
          toast.error("Descreva a alteração após o comando.");
          return;
        }
        const hasDocument = !!documentContent?.trim();
        const canUsePipeline = chatMode === 'standard' && !denseResearch && !useMultiAgent;
        const shouldGenerate = canvasCommand.action === 'replace' || !hasDocument;
        if (canUsePipeline && shouldGenerate) {
          if (selectedText) {
            clearSelectedText();
          }
          const prompt = normalizeCanvasPrompt(canvasCommand.payload);
          useChatStore.getState().addMessage({
            id: `user-${Date.now()}`,
            role: 'user',
            content,
            timestamp: new Date().toISOString(),
          });
          await sendMessage(prompt, {
            skipUserMessage: true,
            canvasWrite: 'replace',
            outlinePipeline: true,
          });
          return;
        }
        if (!hasDocument) {
          toast.error("Canvas vazio. Gere ou cole um documento antes.");
          return;
        }
        const message =
          canvasCommand.action === 'append'
            ? `Adicione ao final do documento, mantendo o restante intacto: ${canvasCommand.payload}`
            : canvasCommand.action === 'replace'
              ? `Substitua o documento inteiro por uma nova versão que atenda: ${canvasCommand.payload}`
              : canvasCommand.payload;
        if (selectedText) {
          clearSelectedText();
        }
        await startDocumentEdit({
          message,
          selection: documentContent,
          selectionRange: null,
          selectionContext: null,
          isFullDocument: true,
        });
        return;
      }

      const lower = content.toLowerCase().trim();
      const openCanvasOnly = /^(abrir|abra|mostrar|exibir|ver)\s+(o\s+|a\s+)?(canvas|editor|minuta|documento|pe[cç]a|peti[cç]ao|inicial|contesta[cç][aã]o)\b/.test(lower);
      if (openCanvasOnly || lower === 'canvas') {
        openCanvas();
        toast.info('Canvas aberto.');
        return;
      }

      if (isDocumentRequest(content)) {
        openCanvas();
        if (selectedText) {
          clearSelectedText();
        }
        useChatStore.getState().addMessage({
          id: `user-${Date.now()}`,
          role: 'user',
          content,
          timestamp: new Date().toISOString(),
        });
        if (chatMode === 'standard' && !denseResearch && !useMultiAgent) {
          await sendMessage(content, {
            skipUserMessage: true,
            canvasWrite: 'replace',
            outlinePipeline: true,
          });
        } else {
          await startAgentGeneration(content);
        }
        return;
      }

      const targetExplicit = /\b(canvas|editor|minuta|documento|pe[cç]a|peti[cç]ao)\b/.test(lower);
      const targetContextual = /\bno\s+documento\b/.test(lower)
        || /\bna\s+minuta\b/.test(lower)
        || /\bno\s+editor\b/.test(lower)
        || /\bno\s+canvas\b/.test(lower)
        || /\bna\s+pe[cç]a\b/.test(lower)
        || /\bna\s+peti[cç]ao\b/.test(lower)
        || /\bna\s+inicial\b/.test(lower)
        || /\bna\s+contesta[cç][aã]o\b/.test(lower);
      const wantsCanvas = targetExplicit || targetContextual;
      const wantsWrite = /(escrev|gerar|gera|gere|redigir|redija|criar|crie|elaborar|elabore|montar|monte|produzir|produza|rascunhar|rascunhe|esbocar|esboce|preparar|prepare|fazer|fa[cç]a)/.test(lower);
      const wantsAppend = /(adicion|acresc|append|incluir|anexar|complementar)/.test(lower);
      if (wantsCanvas && wantsWrite) {
        openCanvas();
        const prompt = normalizeCanvasPrompt(content);
        const userMessageId = `user-${Date.now()}`;
        useChatStore.getState().addMessage({
          id: userMessageId,
          role: 'user',
          content,
          timestamp: new Date().toISOString(),
        });
        await sendMessage(prompt, {
          skipUserMessage: true,
          canvasWrite: wantsAppend ? 'append' : 'replace',
        });
        return;
      }

      // INTERCEPT FOR DOCUMENT EDITING
      if (selectedText && documentContent) {
        await startDocumentEdit({
          message: content,
          selection: selectedText,
          selectionRange,
          selectionContext,
          isFullDocument: false,
        });
        return;
      }

      const { startMultiModelStream } = useChatStore.getState();

      if (chatMode === 'multi-model') {
        await startMultiModelStream(content);
      } else {
        await sendMessage(content);
      }
    } catch (error) {
      console.error('Error sending message:', error);
      const msg = error instanceof Error ? error.message : String(error || '');
      toast.error('Erro ao enviar mensagem', {
        description: msg ? msg.slice(0, 220) : undefined,
      });
    }
  };

  const handleExport = async (format: 'txt' | 'md' | 'docx') => {
    if (!currentChat?.messages?.length) {
      toast.error("Nada para exportar");
      return;
    }

    const messages = currentChat.messages;

    // Formatter
    const formatContent = () => {
      return messages.map(m => {
        const role = m.role === 'user' ? '👤 Você' : '🤖 Iudex';
        const time = new Date(m.timestamp).toLocaleString();
        return `[${time}] ${role}:\n${m.content}\n\n${'-'.repeat(40)}\n`;
      }).join('\n');
    };

    const content = formatContent();
    const filename = `chat-${currentChat.id.slice(0, 8)}-${format}`;

    try {
      if (format === 'docx') {
        toast.info("Gerando DOCX...");
        const blob = await apiClient.exportLegalDocx(content, `${filename}.docx`, 'GENERICO');
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${filename}.docx`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        toast.success("Download concluído!");
      } else {
        const type = format === 'md' ? 'text/markdown' : 'text/plain';
        const ext = format === 'md' ? 'md' : 'txt';
        const blob = new Blob([content], { type });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${filename}.${ext}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        toast.success("Download concluído!");
      }
    } catch (e) {
      console.error(e);
      toast.error("Erro ao exportar");
    }
  };

  const lastAssistantMessage = useMemo(() => {
    const msgs = currentChat?.messages || [];
    for (let i = msgs.length - 1; i >= 0; i -= 1) {
      if (msgs[i]?.role === 'assistant' && String(msgs[i]?.content || '').trim()) {
        return msgs[i];
      }
    }
    return null;
  }, [currentChat?.messages]);

  const lastAssistantSnippet = useMemo(() => {
    const text = String(lastAssistantMessage?.content || '').trim();
    if (!text) return '';
    const max = 600;
    return text.length > max ? `${text.slice(0, max)}…` : text;
  }, [lastAssistantMessage]);

  const getUserMessageForAssistant = (assistantMessage: any) => {
    if (!assistantMessage || !currentChat?.messages?.length) return null;
    const messages = currentChat.messages;
    const turnId = assistantMessage?.metadata?.turn_id;
    if (turnId) {
      const byTurn = messages.find(
        (m: any) => m.role === 'user' && m.metadata?.turn_id === turnId
      );
      if (byTurn) return byTurn;
    }
    const index = messages.findIndex((m: any) => m.id === assistantMessage.id);
    if (index <= 0) return null;
    for (let i = index - 1; i >= 0; i -= 1) {
      if (messages[i]?.role === 'user') return messages[i];
    }
    return null;
  };

  const handleCopyMessage = useCallback(async (message: any) => {
    if (!message) return;
    const text = String(message.content || '').trim();
    if (!text) {
      toast.error('Nenhuma resposta da IA para copiar.');
      return;
    }

    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
      }
      toast.success('Resposta copiada.');
    } catch (error) {
      console.error('Failed to copy response:', error);
      toast.error('Não foi possível copiar.');
    }
  }, []);

  const handleFeedback = useCallback(async (message: any, type: 'up' | 'down') => {
    // TODO: Send feedback to backend
    console.log('Feedback:', type, message.id);
    toast.success(type === 'up' ? 'Obrigado pelo feedback positivo!' : 'Feedback registrado. Vamos melhorar!');
  }, []);

  const handleShareMessage = useCallback(async (message: any) => {
    const text = String(message.content || '').trim();
    if (!text) return;

    try {
      if (navigator.share) {
        await navigator.share({
          title: 'Resposta do Iudex',
          text: text.slice(0, 500) + (text.length > 500 ? '...' : ''),
        });
      } else {
        await navigator.clipboard.writeText(text);
        toast.success('Link copiado para compartilhar.');
      }
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        toast.error('Não foi possível compartilhar.');
      }
    }
  }, []);

  const handleRegenerateFromMessage = useCallback(async (assistantMessage: any) => {
    if (!assistantMessage || isSending) return;
    const userMessage = getUserMessageForAssistant(assistantMessage);
    const content = String(userMessage?.content || '').trim();
    if (!content) {
      toast.error('Não encontrei a mensagem anterior para regerar.');
      return;
    }
    await sendMessage(content);
  }, [isSending, sendMessage, getUserMessageForAssistant]);

  const handleCompact = useCallback(async () => {
    setIsCompacting(true);
    try {
      await compactConversation();
    } finally {
      setIsCompacting(false);
    }
  }, [compactConversation]);

  const handleApproveToolCall = useCallback(
    (remember?: 'session' | 'always') => {
      approveToolCall(true, remember);
    },
    [approveToolCall]
  );

  const handleDenyToolCall = useCallback(
    (remember?: 'session' | 'always') => {
      approveToolCall(false, remember);
    },
    [approveToolCall]
  );

  if (isLoading && !currentChat) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!currentChat) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        Selecione ou crie uma conversa
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col font-google-sans-text" data-testid="chat-interface">
      {renderBudgetModal ? (
        <MessageBudgetModal
          open={billingModal.open}
          quote={billingModal.quote}
          onClose={closeBillingModal}
          onSelectBudget={retryWithBudgetOverride}
        />
      ) : null}
      {/* Messages Area */}
      <div
        ref={messagesContainerRef}
        onScroll={handleScroll}
        role="log"
        aria-live="polite"
        aria-label="Mensagens do chat"
        className="relative flex-1 min-h-0 overflow-y-auto bg-muted/50 py-4 px-2 md:px-4 dark:bg-background/70"
        style={messageAreaStyle}
      >
        {/* Export Actions - Absolute Top Right */}
        {currentChat && currentChat.messages?.length > 0 && (
          <div className="absolute top-2 right-4 z-10 flex items-center gap-2 transition-opacity">
            {showCanvasButton && (
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8 border-border bg-background/80 shadow-sm backdrop-blur"
                title="Abrir canvas"
                onClick={openCanvas}
              >
                <PanelRight className="h-4 w-4 text-muted-foreground" />
              </Button>
            )}
            {(contextUsagePercent > 0 || latestTokenPercentLabel) && (
              <ContextIndicatorCompact
                usagePercent={contextUsagePercent > 0 ? contextUsagePercent : (latestTokenPercent ?? 0)}
                tokensUsed={Math.round(((contextUsagePercent > 0 ? contextUsagePercent : (latestTokenPercent ?? 0)) / 100) * 200000)}
                tokenLimit={200000}
              />
            )}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="icon" className="h-8 w-8 border-border bg-background/80 shadow-sm backdrop-blur">
                  <Download className="h-4 w-4 text-muted-foreground" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => handleExport('docx')}>
                  <FileType className="mr-2 h-4 w-4" /> Word (.docx)
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => handleExport('md')}>
                  <FileText className="mr-2 h-4 w-4" /> Markdown (.md)
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => handleExport('txt')}>
                  <FileText className="mr-2 h-4 w-4" /> Texto (.txt)
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        )}

        <div className="mx-auto w-full max-w-none min-h-full flex flex-col">
          {showDeepResearch && deepResearchMode === 'hard' && (
            <div className="mb-4">
              <HardResearchViewer
                jobId={currentJobId || ''}
                isVisible
                events={jobEvents}
              />
            </div>
          )}
          {showDeepResearch && deepResearchMode !== 'hard' && (
            <div className="mb-4">
              <DeepResearchViewer
                jobId={currentJobId || ''}
                isVisible={showDeepResearch}
                events={jobEvents}
              />
            </div>
          )}

          {/* CogGRAG Tree Viewer */}
          {cogragTree && cogragTree.length > 0 && (
            <div className="mb-4">
              <CogRAGTreeViewer
                nodes={cogragTree}
                status={cogragStatus}
                isVisible
              />
            </div>
          )}

          {(currentChat.messages?.length ?? 0) === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-8 px-4">
              {/* Logo + Title */}
              <div className="flex flex-col items-center gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-600 text-white font-bold text-xl shadow-lg">
                  I
                </div>
                <h2 className="text-xl font-semibold text-foreground">
                  Como posso ajudar?
                </h2>
                <p className="text-sm text-muted-foreground">
                  Assistente jurídico com IA
                </p>
              </div>

              {/* Suggestion Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-lg">
                {[
                  { icon: FileText, label: 'Analise este contrato', desc: 'Upload e análise de documentos' },
                  { icon: Search, label: 'Pesquise jurisprudência sobre...', desc: 'Busca em tribunais e legislação' },
                  { icon: FileText, label: 'Redija uma petição inicial', desc: 'Geração de peças processuais' },
                  { icon: BookOpen, label: 'Explique o artigo 5º da CF', desc: 'Consulta e explicação de leis' },
                ].map((item) => (
                  <button
                    key={item.label}
                    type="button"
                    onClick={() => handleSendMessage(item.label)}
                    className="flex items-start gap-3 rounded-xl border border-border bg-card p-4 text-left transition-all hover:border-emerald-300 hover:shadow-md hover:bg-emerald-50/50 dark:hover:bg-emerald-900/20 group"
                  >
                    <item.icon className="h-5 w-5 mt-0.5 text-muted-foreground group-hover:text-emerald-600 transition-colors shrink-0" />
                    <div>
                      <span className="text-sm font-medium text-foreground group-hover:text-emerald-700 dark:group-hover:text-emerald-400">
                        {item.label}
                      </span>
                      <p className="text-xs text-muted-foreground mt-0.5">{item.desc}</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex flex-1 flex-col space-y-6">
              {(() => {
                const items = [];
                const msgs = currentChat.messages;
                let i = 0;

                while (i < msgs.length) {
                  const current = msgs[i] as any;

                  // Check for multi-model group: assistant messages that share the same turn_id
                  // (Robusto: evita agrupar mensagens de turns diferentes por acidente)
                  const turnId = current?.metadata?.turn_id;
                  if (showMultiModelComparator && current.role === 'assistant' && current.metadata?.model && turnId) {
                    const group = [current];
                    let j = i + 1;
                    while (
                      j < msgs.length &&
                      (msgs[j] as any).role === 'assistant' &&
                      (msgs[j] as any).metadata?.model &&
                      (msgs[j] as any).metadata?.turn_id === turnId
                    ) {
                      group.push(msgs[j]);
                      j++;
                    }

                    // Só mostra comparador se houver 2+ modelos no mesmo turno
                    const uniqueModels = new Set(group.map((m: any) => m?.metadata?.model).filter(Boolean));
                    if (uniqueModels.size > 1) {
                      items.push(
                        <MultiModelResponse
                          key={`turn-${turnId}`}
                          messages={group}
                          onCopy={handleCopyMessage}
                          onRegenerate={handleRegenerateFromMessage}
                          disableRegenerate={isSending}
                          assistantBubbleStyle={assistantBubbleStyle}
                        />
                      );
                      i = j;
                      continue;
                    }
                  }

                  items.push(
                    <ChatMessage
                      key={current.id}
                      message={current}
                      onCopy={handleCopyMessage}
                      onRegenerate={handleRegenerateFromMessage}
                      onFeedback={handleFeedback}
                      onShare={handleShareMessage}
                      disableRegenerate={isSending}
                      assistantBubbleStyle={assistantBubbleStyle}
                    />
                  );
                  i++;
                }
                return items;
              })()}
              {/* Follow-up input (Perplexity style) */}
              {!isSending && (currentChat.messages?.length ?? 0) > 0 && (() => {
                const lastMsg = currentChat.messages[currentChat.messages.length - 1];
                return lastMsg?.role === 'assistant';
              })() && (
                <div className="max-w-[min(92%,76ch)] mt-4">
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      const input = (e.currentTarget.elements.namedItem('followup') as HTMLInputElement);
                      const val = input?.value?.trim();
                      if (val) {
                        handleSendMessage(val);
                        input.value = '';
                      }
                    }}
                    className="flex items-center gap-2 rounded-xl border border-border bg-muted/50 px-4 py-2.5 transition-all focus-within:border-emerald-300 focus-within:bg-card focus-within:shadow-sm"
                  >
                    <input
                      name="followup"
                      type="text"
                      placeholder="Pergunte um seguimento..."
                      className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none"
                      autoComplete="off"
                    />
                    <button
                      type="submit"
                      className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500 text-white hover:bg-emerald-600 transition-colors shrink-0"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
                    </button>
                  </form>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}

          {isSending && (
            <div className="flex items-center space-x-2 text-muted-foreground" role="status" aria-label="Enviando mensagem">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              <span className="sr-only">Processando resposta...</span>
            </div>
          )}
        </div>
      </div>

      {/* Tool Approval Modal */}
      {pendingToolApproval && (
        <ToolApprovalModal
          isOpen={!!pendingToolApproval}
          onClose={() => useChatStore.getState().clearPendingToolApproval()}
          tool={{
            name: pendingToolApproval.tool,
            input: pendingToolApproval.input as Record<string, any>,
            riskLevel: pendingToolApproval.riskLevel,
          }}
          onApprove={handleApproveToolCall}
          onDeny={handleDenyToolCall}
        />
      )}

      {/* Checkpoint Timeline */}
      {checkpoints.length > 0 && (
        <div className="border-t border-border bg-card">
          <CheckpointTimeline
            checkpoints={checkpoints}
            onRestore={restoreCheckpoint}
          />
        </div>
      )}

      {/* Input Area */}
      {
        !hideInput && (
          <div className="border-t border-border bg-card p-3 md:p-4 transition-colors duration-500" style={inputAreaStyle}>
            {/* Job Quality Panels - Moved to Canvas Quality Tab */}
            {useChatStore.getState().useMultiAgent && (
              <>
                {/* Panels removed from here */}
              </>
            )}

            {/* Selection Indicator */}
            {selectedText && (
              <div className="mb-2 flex items-center justify-between rounded-md border border-primary/20 bg-primary/5 px-3 py-2 text-xs text-primary">
                <div className="flex items-center gap-2 overflow-hidden">
                  <Scissors className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate max-w-[300px] italic">
                    {"\""}
                    {selectedText}
                    {"\""}
                  </span>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 rounded-full hover:bg-destructive/20 hover:text-destructive text-muted-foreground"
                  onClick={clearSelectedText}
                >
                  <X className="h-3 w-3" />
                </Button>
              </div>
            )}

            {/* Debate Toggle (Only visible if not in Fast Mode) */}
            {chatMode !== 'multi-model' ? null : (
              <div className="flex items-center gap-2 mb-2 px-1">
                {/* @ts-ignore */}
                <Switch
                  checked={useDeepDebate}
                  onCheckedChange={setMultiModelDeepDebate}
                  id="deep-debate-toggle"
                  className="scale-75"
                />
                <label htmlFor="deep-debate-toggle" className="text-xs text-muted-foreground cursor-pointer select-none flex items-center gap-1">
                  {useDeepDebate ? "Debate Profundo (4 Rodadas)" : "Consenso Rápido (1 Rodada)"}
                  {useDeepDebate && <span className="text-[10px] text-amber-500 font-medium">(~45s)</span>}
                </label>
              </div>
            )}


            <ChatInput
              onSend={handleSendMessage}
              disabled={isSending}
              placeholder={
                selectedText
                  ? "Digite como quer editar o texto selecionado..."
                  : (placeholder || "Digite sua mensagem...")
              }
            />
          </div>
        )
      }

      {editPreviewOpen && (
        <Suspense fallback={null}>
          <LazyDiffConfirmDialog
            open={editPreviewOpen}
            onOpenChange={(open) => {
              setEditPreviewOpen(open);
              if (!open) {
                setEditPreview(null);
              }
            }}
            title="Confirmar edição"
            description="Revise a alteração sugerida antes de aplicar no documento."
            original={editPreview?.original || ''}
            replacement={editPreview?.edited || ''}
            onAccept={() => {
              if (!editPreview) return;
              const result = applyTextReplacement(editPreview.original, editPreview.edited, 'Edição', editPreview.range);
              if (result.success && result.reason === 'pending') {
                toast.info("Aplicando edição no documento...");
              } else if (result.success) {
                toast.success("Edição aplicada com sucesso!");
              } else {
                toast.error(`Falha ao aplicar edição: ${result.reason}`);
              }

              useChatStore.getState().addMessage({
                id: `sys-${Date.now()}`,
                role: 'assistant',
                content: `Edição concluída por ${editPreview.agents.join(', ')}.`,
                timestamp: new Date().toISOString()
              });
              clearSelectedText();
              setEditPreviewOpen(false);
              setEditPreview(null);
            }}
            onReject={() => {
              toast.info("Edição descartada.");
              clearSelectedText();
              setEditPreviewOpen(false);
              setEditPreview(null);
            }}
          />
        </Suspense>
      )}
    </div >
  );
}
