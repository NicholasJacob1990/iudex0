'use client';

import { useEffect, useRef, useCallback, useMemo, useState } from 'react';
import { useChatStore, useCanvasStore } from '@/stores';
import { ChatMessage } from './chat-message';
import { MultiModelResponse } from './multi-model-response';
import { ChatInput } from './chat-input';
import { DeepResearchViewer } from './deep-research-viewer';
import { JobQualityPanel } from './job-quality-panel';
import { JobQualityPipelinePanel } from './job-quality-pipeline-panel';
import { HumanReviewModal } from './human-review-modal';
import { DiffConfirmDialog } from '@/components/dashboard/diff-confirm-dialog';
import { Loader2, Download, FileText, FileType, RotateCcw, Scissors, X, Copy } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
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
}

export function ChatInterface({ chatId, hideInput, placeholder }: ChatInterfaceProps) {
  const {
    currentChat, setCurrentChat, sendMessage, isSending, isLoading,
    currentJobId, jobEvents, reviewData, submitReview,
    showMultiModelComparator, chatMode, selectedModel, selectedModels, denseResearch
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
  const [editPreviewOpen, setEditPreviewOpen] = useState(false);
  const [editPreview, setEditPreview] = useState<{
    original: string;
    edited: string;
    agents: string[];
    range: { from: number; to: number } | null;
  } | null>(null);
  const showDeepResearch = denseResearch && !!currentJobId;

  /* 
   * NEW: Deep Debate Toggle for Committee Mode 
   */
  const [useDeepDebate, setUseDeepDebate] = useState(true);

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
        if (!documentContent?.trim()) {
          toast.error("Canvas vazio. Gere ou cole um documento antes.");
          return;
        }
        if (!canvasCommand.payload) {
          toast.error("Descreva a alteração após o comando.");
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
      const wantsWrite = /(escrev|gerar|redigir|criar|elaborar|montar|produzir|rascunhar|esbocar|preparar|fazer)/.test(lower);
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

  const handleCopyMessage = async (message: any) => {
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
  };

  const handleRegenerateFromMessage = async (assistantMessage: any) => {
    if (!assistantMessage || isSending) return;
    const userMessage = getUserMessageForAssistant(assistantMessage);
    const content = String(userMessage?.content || '').trim();
    if (!content) {
      toast.error('Não encontrei a mensagem anterior para regerar.');
      return;
    }
    await sendMessage(content);
  };

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
    <div className="flex flex-1 min-h-0 flex-col font-google-sans-text" data-testid="chat-interface">
      {/* Messages Area */}
      <div
        ref={messagesContainerRef}
        onScroll={() => { isNearBottomRef.current = checkIfNearBottom(); }}
        className="flex-1 min-h-0 overflow-y-auto p-6 space-y-5 relative bg-[#f7f7f8]"
      >
        {/* Export Actions - Absolute Top Right */}
        {currentChat && currentChat.messages?.length > 0 && (
          <div className="absolute top-2 right-4 z-10 transition-opacity">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="icon" className="h-8 w-8 bg-white/80 backdrop-blur border-slate-200 shadow-sm">
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

        {showDeepResearch && (
          <DeepResearchViewer
            jobId={currentJobId || ''}
            isVisible={showDeepResearch}
            events={jobEvents}
          />
        )}

        {(currentChat.messages?.length ?? 0) === 0 ? (
          <div className="flex h-full items-center justify-center text-slate-500">
            Nenhuma mensagem ainda. Comece a conversar!
          </div>
        ) : (
          <>
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
                    disableRegenerate={isSending}
                  />
                );
                i++;
              }
              return items;
            })()}
            <div ref={messagesEndRef} />
          </>
        )}

        {isSending && (
          <div className="flex items-center space-x-2 text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="text-sm">IA está pensando...</span>
          </div>
        )}
      </div>

      {/* Input Area */}
      {
        !hideInput && (
          <div className="border-t border-slate-200 bg-white p-4">
            <JobQualityPanel isVisible={!!currentJobId} events={jobEvents} />
            <JobQualityPipelinePanel isVisible={!!currentJobId} events={jobEvents} />

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
                  onCheckedChange={setUseDeepDebate}
                  id="deep-debate-toggle"
                  className="scale-75"
                />
                <label htmlFor="deep-debate-toggle" className="text-xs text-muted-foreground cursor-pointer select-none flex items-center gap-1">
                  {useDeepDebate ? "Debate Profundo (4 Rodadas)" : "Consenso Rápido (1 Rodada)"}
                  {useDeepDebate && <span className="text-[10px] text-amber-500 font-medium">(~45s)</span>}
                </label>
              </div>
            )}

            {lastAssistantMessage && !selectedText && (
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-[11px] text-slate-500">
                <span className="max-w-[65%] truncate">
                  Última resposta: {lastAssistantSnippet || '—'}
                </span>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    className="h-7 gap-1 text-[11px]"
                    onClick={() => handleCopyMessage(lastAssistantMessage)}
                  >
                    <Copy className="h-3.5 w-3.5" />
                    Copiar
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    className="h-7 gap-1 text-[11px]"
                    onClick={() => handleRegenerateFromMessage(lastAssistantMessage)}
                    disabled={isSending}
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    Regerar resposta
                  </Button>
                </div>
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

      <HumanReviewModal
        isOpen={!!reviewData}
        data={reviewData}
        onSubmit={submitReview}
      />
      <DiffConfirmDialog
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
            toast.success("Edição aplicada com sucesso! 🎉");
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
    </div >
  );
}
