import { create } from 'zustand';
import { AISimulationService } from '@/services/ai-simulation';
import { AgentOrchestrator, AgentStep } from '@/services/agents/agent-orchestrator';
import { nanoid } from 'nanoid';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';

interface Message {
  id: string;
  content: string;
  role: 'user' | 'assistant';
  timestamp: string;
}

interface Chat {
  id: string;
  title: string;
  messages: Message[];
  created_at: string;
  updated_at: string;
}

interface ChatState {
  chats: Chat[];
  currentChat: Chat | null;
  isLoading: boolean;
  isSending: boolean;
  fetchChats: () => Promise<void>;
  setCurrentChat: (chatId: string | null) => Promise<void>;
  createChat: (title?: string) => Promise<Chat>;
  deleteChat: (chatId: string) => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  generateDocument: (data: {
    prompt: string;
    context?: any;
    effort_level?: number;
    document_type?: string;
  }) => Promise<any>;

  // Context Management
  activeContext: any[];
  setContext: (context: any[]) => void;

  // Agent State
  agentSteps: AgentStep[];
  isAgentRunning: boolean;
  startAgentGeneration: (prompt: string) => Promise<void>;
}

// Mock initial data (fallback)
const MOCK_CHATS: Chat[] = [
  {
    id: '1',
    title: 'Análise de Contrato Social',
    messages: [
      {
        id: 'm1',
        content: 'Olá! Sou o Iudex. Como posso ajudar com sua demanda jurídica hoje?',
        role: 'assistant',
        timestamp: new Date().toISOString(),
      }
    ],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }
];

export const useChatStore = create<ChatState>((set, get) => ({
  chats: [],
  currentChat: null,
  isLoading: false,
  isSending: false,
  activeContext: [],
  agentSteps: [],
  isAgentRunning: false,

  setContext: (context) => set({ activeContext: context }),

  fetchChats: async () => {
    set({ isLoading: true });
    try {
      const response = await apiClient.getChats();
      // @ts-ignore
      set({ chats: response.chats || MOCK_CHATS, isLoading: false });
    } catch (error) {
      console.error('Error fetching chats:', error);
      set({ chats: MOCK_CHATS, isLoading: false });
    }
  },

  setCurrentChat: async (chatId: string | null) => {
    if (!chatId) {
      set({ currentChat: null });
      return;
    }

    set({ isLoading: true });
    try {
      const chat = await apiClient.getChat(chatId);
      // @ts-ignore
      set({ currentChat: chat, isLoading: false });
    } catch (error) {
      console.error('Error fetching chat:', error);
      const fallbackChat = get().chats.find(c => c.id === chatId);
      set({ currentChat: fallbackChat || null, isLoading: false });
    }
  },

  createChat: async (title?: string) => {
    set({ isLoading: true });
    try {
      const newChat = await apiClient.createChat({ title });
      set((state) => ({
        chats: [newChat, ...state.chats],
        currentChat: newChat,
        isLoading: false,
      }));
      return newChat;
    } catch (error) {
      console.error('Error creating chat:', error);
      set({ isLoading: false });
      throw error;
    }
  },

  deleteChat: async (chatId: string) => {
    try {
      await apiClient.deleteChat(chatId);
      set((state) => ({
        chats: state.chats.filter((c) => c.id !== chatId),
        currentChat: state.currentChat?.id === chatId ? null : state.currentChat,
      }));
    } catch (error) {
      console.error('Error deleting chat:', error);
    }
  },

  sendMessage: async (content: string) => {
    const { currentChat } = get();
    if (!currentChat) throw new Error('No chat selected');

    const userMessage: Message = {
      id: nanoid(),
      content,
      role: 'user',
      timestamp: new Date().toISOString(),
    };

    // Optimistic update
    set((state) => ({
      currentChat: state.currentChat
        ? {
          ...state.currentChat,
          messages: [...state.currentChat.messages, userMessage],
        }
        : null,
      isSending: true,
    }));

    try {
      // Trigger Agent Workflow (Real Backend Call)
      await get().startAgentGeneration(content);

      set({ isSending: false });
    } catch (error) {
      set({ isSending: false });
      toast.error("Erro ao enviar mensagem");
      throw error;
    }
  },

  startAgentGeneration: async (prompt: string) => {
    const { currentChat, activeContext } = get();
    if (!currentChat) return;

    set({ isAgentRunning: true, agentSteps: AgentOrchestrator.getInitialSteps() });

    // Simulate steps visually while waiting for backend
    // In a real streaming implementation, these would update via socket/SSE
    const stepsInterval = setInterval(() => {
      set(state => {
         const newSteps = [...state.agentSteps];
         const workingIndex = newSteps.findIndex(s => s.status === 'working');
         const pendingIndex = newSteps.findIndex(s => s.status === 'pending');
         
         if (workingIndex !== -1) {
            newSteps[workingIndex].status = 'completed';
         }
         if (pendingIndex !== -1) {
            newSteps[pendingIndex].status = 'working';
         }
         return { agentSteps: newSteps };
      });
    }, 2000); // Rotate simulated steps every 2s

    try {
      const response = await apiClient.generateDocument(currentChat.id, {
        prompt,
        context: { active_items: activeContext },
        effort_level: 3 // Default to standard effort
      });
      
      clearInterval(stepsInterval);
      
      // Mark all steps completed
      set(state => ({
        agentSteps: state.agentSteps.map(s => ({ ...s, status: 'completed' }))
      }));

      // Add final message with document
      const aiMessage: Message = {
        id: nanoid(),
        content: response.content || response.message?.content || "Documento gerado.",
        role: 'assistant',
        timestamp: new Date().toISOString(),
      };

      set((state) => ({
        currentChat: state.currentChat
          ? {
            ...state.currentChat,
            messages: [...state.currentChat.messages, aiMessage],
          }
          : null,
        isAgentRunning: false,
      }));

    } catch (e) {
      clearInterval(stepsInterval);
      console.error(e);
      set(state => ({
        isAgentRunning: false,
        agentSteps: state.agentSteps.map(s => 
            s.status === 'working' ? { ...s, status: 'failed' as const, message: 'Erro na geração' } : s
        )
      }));
    }
  },

  generateDocument: async (data) => {
    // Legacy method, redirect to sendMessage
    return get().sendMessage(data.prompt);
  },
}));
