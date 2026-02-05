import { useEffect, useRef, useCallback } from 'react';
import { useChatStore } from '@/stores/chat-store';
import { useDocumentStore } from '@/stores/document-store';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';

export function ChatPanel() {
  const {
    currentChat,
    messages,
    isStreaming,
    streamingContent,
    streamingThinking,
    error,
    initChat,
    sendMessage,
  } = useChatStore();
  const fullText = useDocumentStore((s) => s.fullText);
  const scrollRef = useRef<HTMLDivElement>(null);
  const initedRef = useRef(false);

  // Initialize chat once on mount
  useEffect(() => {
    if (!currentChat && !initedRef.current) {
      initedRef.current = true;
      initChat(fullText?.slice(0, 200));
    }
  }, [currentChat, initChat, fullText]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streamingContent]);

  const handleSend = useCallback(
    async (content: string) => {
      const isFirstMessage = useChatStore.getState().messages.length === 0;
      let messageContent = content;

      if (isFirstMessage && fullText) {
        const docSnippet =
          fullText.length > 10000
            ? fullText.slice(0, 10000) + '\n\n[... documento truncado ...]'
            : fullText;
        messageContent = `[Contexto do documento Word aberto]\n\n${docSnippet}\n\n---\n\n${content}`;
      }

      await sendMessage(messageContent);
    },
    [fullText, sendMessage]
  );

  return (
    <div className="flex h-full flex-col">
      {/* Messages area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-office-md">
        {messages.length === 0 && !isStreaming && (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <p className="text-office-base font-medium text-text-primary">
              Pergunte sobre o documento
            </p>
            <p className="mt-1 text-office-sm text-text-tertiary">
              O Vorbium tem acesso ao conteudo do Word aberto.
            </p>
            <div className="mt-4 space-y-2">
              {[
                'Resuma este documento',
                'Quais as clausulas principais?',
                'Identifique riscos juridicos',
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => handleSend(suggestion)}
                  className="block w-full rounded-lg border border-gray-200 px-3 py-2 text-left text-office-sm text-text-secondary hover:border-brand hover:bg-blue-50"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}

        {/* Streaming message */}
        {isStreaming && (
          <ChatMessage
            message={{
              id: 'streaming',
              chat_id: '',
              role: 'assistant',
              content: streamingContent,
              thinking: streamingThinking,
              created_at: new Date().toISOString(),
            }}
            isStreaming
          />
        )}

        {error && (
          <div className="mt-2 rounded-lg bg-red-50 p-3 text-office-sm text-status-error">
            {error}
          </div>
        )}
      </div>

      {/* Input */}
      <ChatInput onSend={handleSend} disabled={isStreaming} />
    </div>
  );
}
