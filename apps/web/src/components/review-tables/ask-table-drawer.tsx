'use client';

import * as React from 'react';
import { useState, useCallback, useRef, useEffect } from 'react';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import {
  MessageCircle,
  Send,
  Loader2,
  FileText,
  BarChart3,
  Table,
  List,
  Sparkles,
  Trash2,
  ExternalLink,
  Copy,
  Check,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import apiClient from '@/lib/api-client';
import { useReviewTableStore } from '@/stores/review-table-store';
import type { TableChatMessage, AskTableResponse } from '@/types/review-table';
import { nanoid } from 'nanoid';

interface AskTableDrawerProps {
  tableId: string;
  open: boolean;
  onClose: () => void;
}

const SUGGESTED_QUESTIONS = [
  'Qual o valor total de todos os contratos?',
  'Quais documentos tem clausula de rescisao?',
  'Resuma as principais informacoes da tabela',
  'Quais documentos estao com baixa confianca?',
  'Compare os valores entre os documentos',
];

const getStructuredDataIcon = (type: string) => {
  switch (type) {
    case 'table':
      return <Table className="h-4 w-4" />;
    case 'chart':
      return <BarChart3 className="h-4 w-4" />;
    case 'list':
      return <List className="h-4 w-4" />;
    default:
      return <FileText className="h-4 w-4" />;
  }
};

function ChatMessage({
  message,
  onDocumentClick,
}: {
  message: TableChatMessage;
  onDocumentClick?: (docId: string) => void;
}) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === 'user';

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [message.content]);

  return (
    <div
      className={cn(
        'flex gap-3 px-4 py-3',
        isUser ? 'bg-muted/50' : 'bg-background'
      )}
    >
      <div
        className={cn(
          'h-8 w-8 rounded-full flex items-center justify-center shrink-0',
          isUser
            ? 'bg-primary text-primary-foreground'
            : 'bg-gradient-to-br from-purple-500 to-blue-500 text-white'
        )}
      >
        {isUser ? (
          <span className="text-xs font-medium">Eu</span>
        ) : (
          <Sparkles className="h-4 w-4" />
        )}
      </div>

      <div className="flex-1 space-y-2 min-w-0">
        <p className="text-sm whitespace-pre-wrap break-words">{message.content}</p>

        {/* Structured data */}
        {message.structured_data && (
          <div className="mt-3 p-3 bg-muted rounded-lg">
            <div className="flex items-center gap-2 mb-2 text-xs text-muted-foreground">
              {getStructuredDataIcon(message.structured_data.type)}
              <span className="capitalize">{message.structured_data.type}</span>
            </div>

            {message.structured_data.type === 'table' &&
              Array.isArray(message.structured_data.data) && (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b">
                        {Object.keys(
                          (message.structured_data.data as Record<string, unknown>[])[0] || {}
                        ).map((key) => (
                          <th
                            key={key}
                            className="px-2 py-1 text-left font-medium"
                          >
                            {key}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(message.structured_data.data as Record<string, unknown>[]).map(
                        (row, i) => (
                          <tr key={i} className="border-b last:border-0">
                            {Object.values(row).map((val, j) => (
                              <td key={j} className="px-2 py-1">
                                {String(val)}
                              </td>
                            ))}
                          </tr>
                        )
                      )}
                    </tbody>
                  </table>
                </div>
              )}

            {message.structured_data.type === 'list' &&
              Array.isArray(message.structured_data.data) && (
                <ul className="list-disc list-inside space-y-1 text-sm">
                  {(message.structured_data.data as string[]).map((item, i) => (
                    <li key={i}>{String(item)}</li>
                  ))}
                </ul>
              )}

            {/* Document references */}
            {message.structured_data.document_refs &&
              message.structured_data.document_refs.length > 0 && (
                <div className="mt-2 pt-2 border-t">
                  <p className="text-xs text-muted-foreground mb-1">
                    Documentos relacionados:
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {message.structured_data.document_refs.map((ref) => (
                      <Badge
                        key={ref.document_id}
                        variant="secondary"
                        className="cursor-pointer hover:bg-secondary/80 text-xs"
                        onClick={() => onDocumentClick?.(ref.document_id)}
                      >
                        <FileText className="h-3 w-3 mr-1" />
                        {ref.document_name}
                        {ref.page && (
                          <span className="ml-1 opacity-60">p.{ref.page}</span>
                        )}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
          </div>
        )}

        {/* Copy button for assistant messages */}
        {!isUser && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-xs text-muted-foreground"
            onClick={handleCopy}
          >
            {copied ? (
              <>
                <Check className="h-3 w-3 mr-1" />
                Copiado
              </>
            ) : (
              <>
                <Copy className="h-3 w-3 mr-1" />
                Copiar
              </>
            )}
          </Button>
        )}
      </div>
    </div>
  );
}

export function AskTableDrawer({ tableId, open, onClose }: AskTableDrawerProps) {
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const { chatMessages, addChatMessage, setChatMessages, clearChatMessages, columns } =
    useReviewTableStore();

  // Load chat history callback
  const loadChatHistory = useCallback(async () => {
    try {
      const history = await apiClient.getTableChatHistory(tableId);
      setChatMessages(history);
    } catch (error) {
      console.error('Error loading chat history:', error);
    }
  }, [tableId, setChatMessages]);

  // Load chat history when opened
  useEffect(() => {
    if (open) {
      loadChatHistory();
      inputRef.current?.focus();
    }
  }, [open, tableId, loadChatHistory]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [chatMessages]);

  const handleSend = useCallback(async () => {
    if (!input.trim() || isLoading) return;

    const question = input.trim();
    setInput('');

    // Add user message immediately
    const userMessage: TableChatMessage = {
      id: nanoid(),
      table_id: tableId,
      role: 'user',
      content: question,
      created_at: new Date().toISOString(),
    };
    addChatMessage(userMessage);

    setIsLoading(true);
    try {
      const response: AskTableResponse = await apiClient.askTable(
        tableId,
        question,
        true
      );

      // Add assistant message
      const assistantMessage: TableChatMessage = {
        id: nanoid(),
        table_id: tableId,
        role: 'assistant',
        content: response.answer,
        structured_data: response.structured_data,
        created_at: new Date().toISOString(),
      };
      addChatMessage(assistantMessage);
    } catch (error) {
      console.error('Error asking table:', error);
      const errorMessage: TableChatMessage = {
        id: nanoid(),
        table_id: tableId,
        role: 'assistant',
        content:
          'Desculpe, ocorreu um erro ao processar sua pergunta. Por favor, tente novamente.',
        created_at: new Date().toISOString(),
      };
      addChatMessage(errorMessage);
    } finally {
      setIsLoading(false);
    }
  }, [input, isLoading, tableId, addChatMessage]);

  const handleClearHistory = useCallback(async () => {
    try {
      await apiClient.clearTableChatHistory(tableId);
      clearChatMessages();
    } catch (error) {
      console.error('Error clearing chat history:', error);
    }
  }, [tableId, clearChatMessages]);

  const handleSuggestedQuestion = useCallback((question: string) => {
    setInput(question);
    inputRef.current?.focus();
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  // Generate context-aware suggestions based on columns
  const dynamicSuggestions = React.useMemo(() => {
    if (columns.length === 0) return SUGGESTED_QUESTIONS;

    const columnNames = columns.slice(0, 3).map((c) => c.name);
    const customSuggestions = [
      `Quais documentos tem ${columnNames[0]} definido?`,
      `Compare ${columnNames[0]} entre todos os documentos`,
      ...SUGGESTED_QUESTIONS.slice(0, 3),
    ];

    return customSuggestions.slice(0, 5);
  }, [columns]);

  return (
    <Sheet open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-lg p-0 flex flex-col">
        <SheetHeader className="px-6 py-4 border-b">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 rounded-full bg-gradient-to-br from-purple-500 to-blue-500 flex items-center justify-center">
                <MessageCircle className="h-4 w-4 text-white" />
              </div>
              <div>
                <SheetTitle className="text-base">Perguntar a Tabela</SheetTitle>
                <SheetDescription className="text-xs">
                  Faca perguntas sobre os dados extraidos
                </SheetDescription>
              </div>
            </div>
            {chatMessages.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleClearHistory}
                className="text-muted-foreground"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
          </div>
        </SheetHeader>

        {/* Chat messages */}
        <ScrollArea ref={scrollRef} className="flex-1">
          {chatMessages.length === 0 ? (
            <div className="p-6 space-y-4">
              <div className="text-center text-muted-foreground">
                <Sparkles className="h-12 w-12 mx-auto mb-4 text-primary/40" />
                <p className="font-medium">Como posso ajudar?</p>
                <p className="text-sm mt-1">
                  Faca perguntas sobre os dados da tabela ou solicite analises.
                </p>
              </div>

              <Separator />

              <div className="space-y-2">
                <p className="text-xs text-muted-foreground font-medium">
                  Sugestoes:
                </p>
                {dynamicSuggestions.map((question) => (
                  <Button
                    key={question}
                    variant="outline"
                    size="sm"
                    className="w-full justify-start text-left h-auto py-2 px-3"
                    onClick={() => handleSuggestedQuestion(question)}
                  >
                    <MessageCircle className="h-3 w-3 mr-2 shrink-0" />
                    <span className="text-xs">{question}</span>
                  </Button>
                ))}
              </div>
            </div>
          ) : (
            <div className="divide-y">
              {chatMessages.map((message) => (
                <ChatMessage key={message.id} message={message} />
              ))}
              {isLoading && (
                <div className="flex gap-3 px-4 py-3 bg-background">
                  <div className="h-8 w-8 rounded-full bg-gradient-to-br from-purple-500 to-blue-500 flex items-center justify-center shrink-0">
                    <Sparkles className="h-4 w-4 text-white" />
                  </div>
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span className="text-sm">Pensando...</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </ScrollArea>

        {/* Input area */}
        <div className="border-t p-4">
          <div className="flex gap-2">
            <Input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Faca uma pergunta sobre a tabela..."
              disabled={isLoading}
              className="flex-1"
            />
            <Button
              size="icon"
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
            >
              {isLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground mt-2 text-center">
            A IA pode cometer erros. Sempre verifique os dados.
          </p>
        </div>
      </SheetContent>
    </Sheet>
  );
}
