import { create } from 'zustand';
import {
  createChat,
  getChatMessages,
  type Chat,
  type Message,
} from '@/api/client';
import { streamMessage } from '@/api/sse-client';

interface SendMessageOptions {
  model?: string;
  playbook_id?: string;
  web_search?: boolean;
  rag_enabled?: boolean;
}

interface ChatState {
  currentChat: Chat | null;
  messages: Message[];
  isStreaming: boolean;
  streamingContent: string;
  streamingThinking: string;
  error: string | null;
  extraContext: string | null;

  initChat: (documentContext?: string) => Promise<void>;
  sendMessage: (content: string, options?: SendMessageOptions) => Promise<void>;
  loadMessages: (chatId: string) => Promise<void>;
  clearChat: () => void;
  abortStream: () => void;
  setDocumentContext: (context: string) => void;
}

export const useChatStore = create<ChatState>()((set, get) => {
  let abortController: AbortController | null = null;

  return {
    currentChat: null,
    messages: [],
    isStreaming: false,
    streamingContent: '',
    streamingThinking: '',
    error: null,
    extraContext: null,

    initChat: async (documentContext?: string) => {
      try {
        const title = documentContext
          ? `Word: ${documentContext.slice(0, 50)}...`
          : 'Word Add-in Chat';
        const chat = await createChat(title);
        set({ currentChat: chat, messages: [], error: null });
      } catch (err: unknown) {
        set({
          error: err instanceof Error ? err.message : 'Erro ao criar chat',
        });
      }
    },

    sendMessage: async (content: string, options?: SendMessageOptions) => {
      const { currentChat, extraContext } = get();
      if (!currentChat) {
        set({ error: 'Nenhum chat ativo' });
        return;
      }

      // Prepend extra context if available (from corpus)
      let finalContent = content;
      if (extraContext) {
        finalContent = `${extraContext}\n\n---\n\n${content}`;
        set({ extraContext: null });
      }

      // Add user message optimistically
      const userMessage: Message = {
        id: `temp-${Date.now()}`,
        chat_id: currentChat.id,
        role: 'user',
        content: finalContent,
        created_at: new Date().toISOString(),
      };

      // Abort any previous stream
      abortController?.abort();
      abortController = new AbortController();
      const currentController = abortController;

      set((state) => ({
        messages: [...state.messages, userMessage],
        isStreaming: true,
        streamingContent: '',
        streamingThinking: '',
        error: null,
      }));

      let fullContent = '';
      let fullThinking = '';

      try {
        await streamMessage({
          chatId: currentChat.id,
          content: finalContent,
          model: options?.model,
          playbook_id: options?.playbook_id,
          web_search: options?.web_search,
          rag_enabled: options?.rag_enabled,
          signal: currentController.signal,
          onThinking: (text) => {
            fullThinking += text;
            set({ streamingThinking: fullThinking });
          },
          onContent: (text) => {
            fullContent += text;
            set({ streamingContent: fullContent });
          },
          onDone: () => {
            const assistantMessage: Message = {
              id: `msg-${Date.now()}`,
              chat_id: currentChat.id,
              role: 'assistant',
              content: fullContent,
              thinking: fullThinking || undefined,
              created_at: new Date().toISOString(),
            };
            set((state) => ({
              messages: [...state.messages, assistantMessage],
              isStreaming: false,
              streamingContent: '',
              streamingThinking: '',
            }));
          },
          onError: (error) => {
            set({ isStreaming: false, error });
          },
        });
      } catch (err: unknown) {
        if ((err as Error).name !== 'AbortError') {
          set({
            isStreaming: false,
            error: err instanceof Error ? err.message : 'Erro no stream',
          });
        }
      }
    },

    loadMessages: async (chatId: string) => {
      try {
        const messages = await getChatMessages(chatId);
        set({ messages });
      } catch (err: unknown) {
        set({
          error:
            err instanceof Error ? err.message : 'Erro ao carregar mensagens',
        });
      }
    },

    clearChat: () => {
      abortController?.abort();
      abortController = null;
      set({
        currentChat: null,
        messages: [],
        streamingContent: '',
        streamingThinking: '',
        error: null,
        extraContext: null,
      });
    },

    abortStream: () => {
      abortController?.abort();
      abortController = null;
      set({ isStreaming: false });
    },

    setDocumentContext: (context: string) => {
      set({ extraContext: context });
    },
  };
});
