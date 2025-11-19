'use client';

import { useEffect, useRef } from 'react';
import { useChatStore } from '@/stores';
import { ChatMessage } from './chat-message';
import { ChatInput } from './chat-input';
import { Loader2 } from 'lucide-react';

interface ChatInterfaceProps {
  chatId: string;
}

export function ChatInterface({ chatId }: ChatInterfaceProps) {
  const { currentChat, setCurrentChat, sendMessage, isSending, isLoading } = useChatStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setCurrentChat(chatId);
  }, [chatId, setCurrentChat]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [currentChat?.messages]);

  const handleSendMessage = async (content: string) => {
    try {
      await sendMessage(content);
    } catch (error) {
      console.error('Error sending message:', error);
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
    <div className="flex h-full flex-col">
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {currentChat.messages.length === 0 ? (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            Nenhuma mensagem ainda. Comece a conversar!
          </div>
        ) : (
          <>
            {currentChat.messages.map((message) => (
              <ChatMessage key={message.id} message={message} />
            ))}
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
      <div className="border-t bg-card p-4">
        <ChatInput onSend={handleSendMessage} disabled={isSending} />
      </div>
    </div>
  );
}

