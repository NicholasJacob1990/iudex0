'use client';

import { useEffect, useRef, useCallback } from 'react';
import { useChatStore } from '@/stores';
import { ChatMessage } from './chat-message';
import { MultiModelResponse } from './multi-model-response';
import { ChatInput } from './chat-input';
import { DeepResearchViewer } from './deep-research-viewer';
import { JobQualityPanel } from './job-quality-panel';
import { JobQualityPipelinePanel } from './job-quality-pipeline-panel';
import { HumanReviewModal } from './human-review-modal';
import { Loader2, Download, FileText, FileType, MoreVertical } from 'lucide-react';
import { Button } from '@/components/ui/button';
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
}

export function ChatInterface({ chatId, hideInput }: ChatInterfaceProps) {
  const {
    currentChat, setCurrentChat, sendMessage, isSending, isLoading,
    currentJobId, jobEvents, reviewData, submitReview,
    showMultiModelComparator
  } = useChatStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const prevMessageCountRef = useRef<number>(0);
  const isNearBottomRef = useRef<boolean>(true);

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

  const handleSendMessage = async (content: string) => {
    try {
      const { chatMode, startMultiModelStream } = useChatStore.getState();

      if (chatMode === 'multi-model') {
        await startMultiModelStream(content);
      } else {
        await sendMessage(content);
      }
    } catch (error) {
      console.error('Error sending message:', error);
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

  if (isLoading) {
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
    <div className="flex flex-1 min-h-0 flex-col">
      {/* Messages Area */}
      <div
        ref={messagesContainerRef}
        onScroll={() => { isNearBottomRef.current = checkIfNearBottom(); }}
        className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4 relative"
      >
        {/* Export Actions - Absolute Top Right */}
        {currentChat && currentChat.messages?.length > 0 && (
          <div className="absolute top-2 right-4 z-10 transition-opacity">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="icon" className="h-8 w-8 bg-background/50 backdrop-blur shadow-sm">
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

        {(currentChat.messages?.length ?? 0) === 0 ? (
          <div className="flex h-full items-center justify-center text-muted-foreground">
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
                    items.push(<MultiModelResponse key={`turn-${turnId}`} messages={group} />);
                    i = j;
                    continue;
                  }
                }

                items.push(<ChatMessage key={current.id} message={current} />);
                i++;
              }
              return items;
            })()}
            <div ref={messagesEndRef} />
          </>
        )}

        {isSending && (
          <div className="flex items-center space-x-2 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="text-sm">IA está pensando...</span>
          </div>
        )}
      </div>

      {/* Input Area */}
      {
        !hideInput && (
          <div className="border-t bg-card p-4">
            <DeepResearchViewer
              jobId={currentJobId || ''}
              isVisible={!!currentJobId}
              events={jobEvents}
            />
            <JobQualityPanel isVisible={!!currentJobId} events={jobEvents} />
            <JobQualityPipelinePanel isVisible={!!currentJobId} events={jobEvents} />
            <ChatInput onSend={handleSendMessage} disabled={isSending} />
          </div>
        )
      }

      <HumanReviewModal
        isOpen={!!reviewData}
        data={reviewData}
        onSubmit={submitReview}
      />
    </div >
  );
}
