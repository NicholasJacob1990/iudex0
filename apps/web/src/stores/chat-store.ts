import { create } from 'zustand';
import { AISimulationService } from '@/services/ai-simulation';
import { AgentOrchestrator, AgentStep } from '@/services/agents/agent-orchestrator';
import { nanoid } from 'nanoid';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';
import { useCanvasStore } from '@/stores/canvas-store';

const MULTI_MODEL_VIEW_STORAGE_KEY = 'iudex_multi_model_view';
const CHAT_PERSONALITY_KEY = 'iudex_chat_personality';
const CHAT_DRAFTS_KEY_PREFIX = 'iudex_chat_drafts_';

type DraftMetadata = {
  processed_sections?: any[];
  has_any_divergence?: boolean;
  divergence_summary?: string;
  full_document?: string;
  models?: string[];
  consensus?: boolean;
  audit?: any;
};

const getDraftStorageKey = (chatId: string) => `${CHAT_DRAFTS_KEY_PREFIX}${chatId}`;

const extractDraftMetadata = (metadata: any): DraftMetadata | null => {
  if (!metadata) return null;
  const processed = Array.isArray(metadata.processed_sections)
    ? metadata.processed_sections
    : [];
  if (processed.length === 0 && !metadata.full_document && !metadata.divergence_summary) {
    return null;
  }
  return {
    processed_sections: processed,
    has_any_divergence: metadata.has_any_divergence,
    divergence_summary: metadata.divergence_summary,
    full_document: metadata.full_document,
    models: metadata.models,
    consensus: metadata.consensus,
    audit: metadata.audit,
  };
};

const persistDraftMetadata = (chatId: string | null, metadata: any) => {
  if (!chatId || typeof window === 'undefined') return;
  const payload = extractDraftMetadata(metadata);
  if (!payload) return;
  try {
    localStorage.setItem(getDraftStorageKey(chatId), JSON.stringify(payload));
  } catch {
    // ignore storage errors
  }
};

const loadDraftMetadata = (chatId: string | null): DraftMetadata | null => {
  if (!chatId || typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(getDraftStorageKey(chatId));
    if (!raw) return null;
    return JSON.parse(raw) as DraftMetadata;
  } catch {
    return null;
  }
};

const clearDraftMetadata = (chatId: string) => {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(getDraftStorageKey(chatId));
  } catch {
    // ignore storage errors
  }
};

function loadMultiModelView(): 'tabs' | 'columns' {
  if (typeof window === 'undefined') return 'tabs';
  try {
    const v = localStorage.getItem(MULTI_MODEL_VIEW_STORAGE_KEY);
    return v === 'columns' ? 'columns' : 'tabs';
  } catch {
    return 'tabs';
  }
}

function loadChatPersonality(): 'juridico' | 'geral' {
  if (typeof window === 'undefined') return 'juridico';
  try {
    const v = localStorage.getItem(CHAT_PERSONALITY_KEY);
    return v === 'geral' ? 'geral' : 'juridico';
  } catch {
    return 'juridico';
  }
}

function normalizePageRange(minPages: number, maxPages: number) {
  let min = Number.isFinite(minPages) ? Math.max(0, Math.floor(minPages)) : 0;
  let max = Number.isFinite(maxPages) ? Math.max(0, Math.floor(maxPages)) : 0;

  if (min > 0 && max === 0) max = min;
  if (max > 0 && min === 0) min = 1;
  if (min > 0 && max > 0 && max < min) max = min;

  return { minPages: min, maxPages: max };
}

interface Message {
  id: string;
  content: string;
  role: 'user' | 'assistant';
  timestamp: string;
  metadata?: any;
}

type CanvasContext = {
  text: string;
  action: 'improve' | 'shorten' | null;
};

interface Chat {
  id: string;
  title: string;
  messages: Message[];
  created_at: string;
  updated_at: string;
  is_active?: boolean;
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

  // Canvas context for snippet improvements
  pendingCanvasContext: CanvasContext | null;
  setPendingCanvasContext: (context: CanvasContext | null) => void;

  // Agent State
  agentSteps: AgentStep[];
  isAgentRunning: boolean;
  effortLevel: number;
  selectedModel: string;
  gptModel: string;
  claudeModel: string;
  useMultiAgent: boolean;
  reasoningLevel: 'low' | 'medium' | 'high';
  webSearch: boolean;
  ragTopK: number;
  ragSources: string[];
  minPages: number;
  maxPages: number;
  attachmentMode: 'rag_local' | 'prompt_injection';

  // Agent Specific Models
  agentStrategistModel: string;
  agentDrafterModels: string[];
  agentReviewerModels: string[];
  setAgentStrategistModel: (model: string) => void;
  setAgentDrafterModels: (models: string[]) => void;
  setAgentReviewerModels: (models: string[]) => void;

  // Multi-Model V2
  chatMode: 'standard' | 'multi-model';
  selectedModels: string[];
  multiModelMessages: Record<string, Message[]>;
  // UI: Visualização do comparador (Tabs) para multi-modelo
  showMultiModelComparator: boolean;
  setShowMultiModelComparator: (enabled: boolean) => void;
  // UI: Consolidado (juiz/merge)
  autoConsolidate: boolean;
  setAutoConsolidate: (enabled: boolean) => void;
  consolidateTurn: (turnId: string) => Promise<void>;
  // UI: Layout do comparador
  multiModelView: 'tabs' | 'columns';
  setMultiModelView: (view: 'tabs' | 'columns') => void;

  denseResearch: boolean;
  hilTargetSections: string[];

  tenantId: string;
  // Context Management (v2)
  contextMode: 'rag_local' | 'upload_cache';
  contextFiles: string[]; // List of paths (simulated for local)
  cacheTTL: number;
  documentType: string;
  thesis: string;
  formattingOptions: {
    includeToc: boolean;
    includeSummaries: boolean;
    includeSummaryTable: boolean;
  };
  citationStyle: 'forense' | 'abnt' | 'hibrido';
  useTemplates: boolean;
  templateFilters: {
    tipoPeca: string;
    area: string;
    rito: string;
    apenasClauseBank: boolean;
  };
  templateId: string | null;
  templateVariables: Record<string, any>;
  templateName: string | null;
  promptExtra: string;
  adaptiveRouting: boolean;
  cragGate: boolean;
  hydeEnabled: boolean;
  graphRagEnabled: boolean;
  graphHops: number;

  // Chat Personality: 'juridico' for legal language, 'geral' for general/free chat
  chatPersonality: 'juridico' | 'geral';

  setEffortLevel: (level: number) => void;
  setSelectedModel: (model: string) => void;
  setGptModel: (model: string) => void;
  setClaudeModel: (model: string) => void;
  setAgentStrategistModel: (model: string) => void;
  setAgentDrafterModels: (models: string[]) => void;
  setAgentReviewerModels: (models: string[]) => void;
  setUseMultiAgent: (use: boolean) => void;
  setReasoningLevel: (level: 'low' | 'medium' | 'high') => void;
  setWebSearch: (enabled: boolean) => void;
  setRagTopK: (k: number) => void;
  setRagSources: (sources: string[]) => void;
  setPageRange: (range: { minPages?: number; maxPages?: number }) => void;
  resetPageRange: () => void;
  setAttachmentMode: (mode: 'rag_local' | 'prompt_injection') => void;
  setDenseResearch: (enabled: boolean) => void;
  setHilTargetSections: (sections: string[]) => void;
  setTenantId: (id: string) => void;
  setContextMode: (mode: 'rag_local' | 'upload_cache') => void;
  setContextFiles: (files: string[]) => void;
  setCacheTTL: (ttl: number) => void;
  setDocumentType: (type: string) => void;
  setThesis: (thesis: string) => void;
  setFormattingOptions: (options: Partial<ChatState['formattingOptions']>) => void;
  setCitationStyle: (style: ChatState['citationStyle']) => void;
  setUseTemplates: (use: boolean) => void;
  setTemplateFilters: (filters: Partial<ChatState['templateFilters']>) => void;
  setTemplateId: (id: string | null) => void;
  setTemplateVariables: (vars: Record<string, any>) => void;
  setTemplateName: (name: string | null) => void;
  setPromptExtra: (prompt: string) => void;
  setAdaptiveRouting: (enabled: boolean) => void;
  setCragGate: (enabled: boolean) => void;
  setHydeEnabled: (enabled: boolean) => void;
  setGraphRagEnabled: (enabled: boolean) => void;
  setGraphHops: (hops: number) => void;
  setChatPersonality: (personality: 'juridico' | 'geral') => void;
  // Audit State
  audit: boolean;
  setAudit: (enabled: boolean) => void;
  startAgentGeneration: (prompt: string, canvasContext?: CanvasContext | null) => Promise<void>;
  generateDocumentWithResult: (prompt: string, caseId?: string) => Promise<any>;

  // Job State
  currentJobId: string | null;
  jobEvents: any[];
  jobOutline: string[];
  reviewData: any | null;
  submitReview: (decision: any) => Promise<void>;
  startLangGraphJob: (prompt: string) => Promise<void>;

  // V2 Actions
  setChatMode: (mode: 'standard' | 'multi-model') => void;
  setSelectedModels: (models: string[]) => void;
  toggleModel: (modelId: string) => void;
  startMultiModelStream: (content: string) => Promise<void>;
  createMultiChatThread: (title?: string) => Promise<any>;
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

const extractReplacementText = (content: string) => {
  const trimmed = (content || '').trim();
  if (!trimmed) return '';

  const codeBlockMatch = trimmed.match(/```(?:[a-zA-Z0-9_-]+)?\n([\s\S]*?)```/);
  if (codeBlockMatch?.[1]) {
    return codeBlockMatch[1].trim();
  }

  const prefixes = [
    /^Aqui est[aá].*?:\s*/i,
    /^Vers[aã]o .*?:\s*/i,
    /^Trecho reescrito.*?:\s*/i,
    /^Reescrita.*?:\s*/i,
    /^Resposta:\s*/i,
  ];

  let result = trimmed;
  for (const prefix of prefixes) {
    if (prefix.test(result)) {
      result = result.replace(prefix, '').trim();
      break;
    }
  }

  return result;
};

export const useChatStore = create<ChatState>((set, get) => ({
  chats: [],
  currentChat: null,
  isLoading: false,
  isSending: false,
  activeContext: [],
  pendingCanvasContext: null,
  agentSteps: [],
  isAgentRunning: false,
  effortLevel: 3,
  // Modelo "Juiz" (orquestrador/judge). IDs canônicos (ver config/models.ts)
  selectedModel: 'gemini-3-pro',
  gptModel: 'gpt-5.2',
  claudeModel: 'claude-4.5-sonnet',
  useMultiAgent: true,
  reasoningLevel: 'medium',
  webSearch: false,
  ragTopK: 8,
  ragSources: ['lei', 'juris'],
  minPages: 0,
  maxPages: 0,
  attachmentMode: 'rag_local',

  agentStrategistModel: 'gpt-5.2', // GPT implies reasoning/planning
  agentDrafterModels: ['gpt-5.2', 'claude-4.5-sonnet', 'gemini-3-pro'],
  agentReviewerModels: ['gpt-5.2', 'claude-4.5-sonnet', 'gemini-3-pro'],

  denseResearch: false,
  hilTargetSections: [],

  // Multi-Model V2
  chatMode: 'standard' as const, // 'standard' | 'multi-model'
  selectedModels: ['gemini-3-flash'], // Default
  multiModelMessages: {}, // Map threadId -> messages
  showMultiModelComparator: true,
  autoConsolidate: false,
  multiModelView: loadMultiModelView(),

  tenantId: 'default',
  contextMode: 'rag_local',
  contextFiles: [],
  cacheTTL: 60,
  documentType: 'PETICAO_INICIAL',
  thesis: '',
  formattingOptions: {
    includeToc: true,
    includeSummaries: false,
    includeSummaryTable: true,
  },
  citationStyle: 'forense',
  useTemplates: false,
  templateFilters: {
    tipoPeca: '',
    area: '',
    rito: '',
    apenasClauseBank: false,
  },
  templateId: null,
  templateVariables: {},
  templateName: null,
  promptExtra: '',
  adaptiveRouting: true, // Default ON for better experience
  cragGate: true,       // Default ON
  hydeEnabled: false,    // Optional boost
  graphRagEnabled: false, // Optional boost
  graphHops: 2,
  chatPersonality: loadChatPersonality(), // Default to persisted or legal
  audit: true,

  currentJobId: null,
  jobEvents: [],
  jobOutline: [],
  reviewData: null,

  setContext: (context) => set({ activeContext: context }),
  setPendingCanvasContext: (context) => set({ pendingCanvasContext: context }),
  setEffortLevel: (level) => set({ effortLevel: level }),
  setSelectedModel: (model) => set({ selectedModel: model }),
  setGptModel: (model) => set({ gptModel: model }),
  setClaudeModel: (model) => set({ claudeModel: model }),
  setAgentStrategistModel: (model) => set({ agentStrategistModel: model }),
  setAgentDrafterModels: (models) => set({ agentDrafterModels: models }),
  setAgentReviewerModels: (models) => set({ agentReviewerModels: models }),
  setUseMultiAgent: (use) => set({ useMultiAgent: use }),
  setReasoningLevel: (level) => set({ reasoningLevel: level }),
  setChatPersonality: (personality) => {
    set({ chatPersonality: personality });
    if (typeof window !== 'undefined') {
      localStorage.setItem(CHAT_PERSONALITY_KEY, personality);
    }
  },
  setWebSearch: (enabled) => set({ webSearch: enabled }),
  setRagTopK: (k) => set({ ragTopK: k }),
  setRagSources: (sources) => set({ ragSources: sources }),
  setPageRange: (range) =>
    set((state) => normalizePageRange(
      range.minPages ?? state.minPages,
      range.maxPages ?? state.maxPages
    )),
  resetPageRange: () => set({ minPages: 0, maxPages: 0 }),
  setAttachmentMode: (mode) => set({ attachmentMode: mode }),
  setDenseResearch: (enabled) => set({ denseResearch: enabled }),
  setHilTargetSections: (sections) => set({ hilTargetSections: sections }),
  setAdaptiveRouting: (enabled) => set({ adaptiveRouting: enabled }),
  setCragGate: (enabled) => set({ cragGate: enabled }),
  setHydeEnabled: (enabled) => set({ hydeEnabled: enabled }),
  setGraphRagEnabled: (enabled) => set({ graphRagEnabled: enabled }),
  setGraphHops: (hops) => set({ graphHops: hops }),


  // V2 Setters
  setChatMode: (mode) => set({ chatMode: mode as any }),
  setSelectedModels: (models) => set({ selectedModels: models }),
  setShowMultiModelComparator: (enabled) => set({ showMultiModelComparator: enabled }),
  setAutoConsolidate: (enabled) => set({ autoConsolidate: enabled }),
  setMultiModelView: (view) => {
    try {
      if (typeof window !== 'undefined') {
        localStorage.setItem(MULTI_MODEL_VIEW_STORAGE_KEY, view);
      }
    } catch {
      // noop
    }
    set({ multiModelView: view });
  },
  toggleModel: (modelId) => set((state) => {
    const current = state.selectedModels;
    if (current.includes(modelId)) {
      return { selectedModels: current.filter(m => m !== modelId) };
    }
    return { selectedModels: [...current, modelId] };
  }),

  setTenantId: (id) => set({ tenantId: id }),
  setContextMode: (mode) => set({ contextMode: mode }),
  setContextFiles: (files) => set({ contextFiles: files }),
  setCacheTTL: (ttl) => set({ cacheTTL: ttl }),
  setDocumentType: (type) => set({ documentType: type }),
  setThesis: (thesis) => set({ thesis }),
  setFormattingOptions: (options) => set((state) => ({
    formattingOptions: { ...state.formattingOptions, ...options }
  })),
  setCitationStyle: (style) => set({ citationStyle: style }),
  setUseTemplates: (use) => set({ useTemplates: use }),
  setTemplateFilters: (filters) => set((state) => ({
    templateFilters: { ...state.templateFilters, ...filters }
  })),
  setTemplateId: (id) => set({ templateId: id }),
  setTemplateVariables: (vars) => set({ templateVariables: vars }),
  setTemplateName: (name) => set({ templateName: name }),
  setPromptExtra: (prompt) => set({ promptExtra: prompt }),
  setAudit: (enabled) => set({ audit: enabled }),

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

    const current = get().currentChat;
    if (current?.id === chatId && (current.messages?.length ?? 0) > 0) {
      const { setMetadata } = useCanvasStore.getState();
      const stored = loadDraftMetadata(chatId);
      if (stored) {
        setMetadata(stored, null);
      }
      return;
    }

    set({ isLoading: true });
    try {
      const chat = await apiClient.getChat(chatId);
      // Ensure messages is always an array
      const normalizedChat = {
        ...chat,
        messages: (chat as any)?.messages || []
      };
      // @ts-ignore
      set({ currentChat: normalizedChat, isLoading: false });
      const { setMetadata } = useCanvasStore.getState();
      const stored = loadDraftMetadata(chatId);
      setMetadata(stored || null, null);
    } catch (error) {
      console.error('Error fetching chat:', error);
      const fallbackChat = get().chats.find(c => c.id === chatId);
      // Ensure fallback also has messages array
      const normalizedFallback = fallbackChat ? { ...fallbackChat, messages: fallbackChat.messages || [] } : null;
      set({ currentChat: normalizedFallback, isLoading: false });
      const { setMetadata } = useCanvasStore.getState();
      const stored = loadDraftMetadata(chatId);
      setMetadata(stored || null, null);
    }
  },

  createChat: async (title?: string) => {
    set({ isLoading: true });
    try {
      const newChat = await apiClient.createChat({ title }) as any;
      // Ensure messages is always an array
      const normalizedChat = {
        ...newChat,
        messages: newChat?.messages || []
      };
      set((state) => ({
        chats: [normalizedChat, ...state.chats],
        currentChat: normalizedChat,
        isLoading: false,
      }));
      return normalizedChat;
    } catch (error) {
      console.error('Error creating chat:', error);
      set({ isLoading: false });
      throw error;
    }
  },

  createMultiChatThread: async (title?: string) => {
    set({ isLoading: true });
    try {
      const newThread = await apiClient.createMultiChatThread(title);
      // Map to Chat interface
      const chat: Chat = {
        id: newThread.id,
        title: newThread.title,
        messages: [],
        created_at: newThread.created_at,
        updated_at: newThread.updated_at,
        is_active: true
      };

      set((state) => ({
        chats: [chat, ...state.chats],
        currentChat: chat,
        isLoading: false,
      }));
      return chat;
    } catch (error) {
      console.error('Error creating multi-chat thread:', error);
      set({ isLoading: false });
      throw error;
    }
  },

  deleteChat: async (chatId: string) => {
    try {
      await apiClient.deleteChat(chatId);
      clearDraftMetadata(chatId);
      set((state) => ({
        chats: state.chats.filter((c) => c.id !== chatId),
        currentChat: state.currentChat?.id === chatId ? null : state.currentChat,
      }));
    } catch (error) {
      console.error('Error deleting chat:', error);
    }
  },

  sendMessage: async (content: string) => {
    const { currentChat, chatMode, chatPersonality } = get();
    if (!currentChat) throw new Error('No chat selected');
    if (content.trim().length < 1) {
      toast.error('Digite uma mensagem.');
      return;
    }

    if (chatMode === 'multi-model') {
      try {
        await get().startMultiModelStream(content);
      } catch (error) {
        toast.error("Erro ao enviar mensagem");
        throw error;
      }
      return;
    }

    const canvasContext = get().pendingCanvasContext;

    const userMessage: Message = {
      id: nanoid(),
      content,
      role: 'user',
      timestamp: new Date().toISOString(),
      metadata: canvasContext ? { canvas_context: canvasContext } : undefined,
    };

    // Optimistic update
    set((state) => ({
      currentChat: state.currentChat
        ? {
          ...state.currentChat,
          messages: [...(state.currentChat.messages || []), userMessage],
        }
        : null,
      isSending: true,
      pendingCanvasContext: null,
    }));

    try {
      const response = await apiClient.sendMessage(currentChat.id, content, undefined, chatPersonality);
      const aiMessage: Message = {
        id: response.id || nanoid(),
        content: response.content || '',
        role: 'assistant',
        timestamp: response.created_at || new Date().toISOString(),
        metadata: response.metadata || undefined,
      };

      set((state) => ({
        currentChat: state.currentChat
          ? {
            ...state.currentChat,
            messages: [...(state.currentChat.messages || []), aiMessage],
          }
          : null,
        isSending: false,
      }));
    } catch (error) {
      set({ isSending: false });
      toast.error("Erro ao enviar mensagem");
      throw error;
    }
  },

  startAgentGeneration: async (prompt: string, canvasContext?: CanvasContext | null) => {
    const { currentChat, activeContext, effortLevel, minPages, maxPages, attachmentMode, chatPersonality } = get();
    if (!currentChat) return;

    set({ isAgentRunning: true, agentSteps: AgentOrchestrator.getInitialSteps() });

    const normalizedRange = normalizePageRange(minPages, maxPages);
    const hasPageRange = normalizedRange.minPages > 0 || normalizedRange.maxPages > 0;
    const contextDocumentIds = (activeContext || [])
      .filter((item: any) => item?.type === 'file' && typeof item.id === 'string')
      .map((item: any) => item.id);
    const hasContextDocs = contextDocumentIds.length > 0;

    // --- HYBRID FORK: If Deep Research is ON, use LangGraph Job API instead ---
    if (get().denseResearch) {
      await get().startLangGraphJob(prompt);
      return; // Exit normal flow, we are in LangGraph mode
    }

    // --- Original Legacy Flow (Web Search / Simple) ---
    // Simulate steps visually while waiting for backend
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
    }, 2000);

    try {
      const response = await apiClient.generateDocument(currentChat.id, {
        prompt,
        context: { active_items: activeContext },
        effort_level: effortLevel,
        ...(hasPageRange ? { min_pages: normalizedRange.minPages, max_pages: normalizedRange.maxPages } : {}),
        ...(hasContextDocs ? { context_documents: contextDocumentIds } : {}),
        attachment_mode: attachmentMode,
        chat_personality: chatPersonality,
        model: get().selectedModel,
        model_gpt: get().gptModel,
        model_claude: get().claudeModel,
        strategist_model: get().agentStrategistModel,
        drafter_models: get().agentDrafterModels,
        reviewer_models: get().agentReviewerModels,
        use_multi_agent: get().useMultiAgent,
        reasoning_level: get().reasoningLevel,
        web_search: get().webSearch,
        dense_research: get().denseResearch, // Should be false if we reached here usually, but keeping for safety
        thinking_level: get().reasoningLevel,
        document_type: get().documentType,
        thesis: get().thesis,
        formatting_options: get().formattingOptions,
        template_id: get().templateId || undefined,
        variables: get().templateVariables,
        rag_config: {
          top_k: get().ragTopK,
          sources: get().ragSources,
          tenant_id: get().tenantId,
          use_templates: get().useTemplates,
          template_filters: get().templateFilters,
          template_id: get().templateId || undefined,
          variables: get().templateVariables,
          prompt_extra: get().promptExtra,
          adaptive_routing: get().adaptiveRouting,
          crag_gate: get().cragGate,
          hyde_enabled: get().hydeEnabled,
          graph_rag_enabled: get().graphRagEnabled,
          graph_hops: get().graphHops
        }
      } as any);

      clearInterval(stepsInterval);

      // Mark all steps completed
      set(state => ({
        agentSteps: state.agentSteps.map(s => ({ ...s, status: 'completed' }))
      }));

      const replacementText = canvasContext ? extractReplacementText(response.content || '') : '';
      const normalizedOriginal = (canvasContext?.text || '').trim();
      const hasReplacement = replacementText && replacementText.trim() !== normalizedOriginal;
      const canvasSuggestion = canvasContext && hasReplacement
        ? {
          original: canvasContext.text,
          replacement: replacementText,
          action: canvasContext.action,
        }
        : null;

      const responseMetadata = (response as any)?.metadata ? { ...(response as any).metadata } : {};
      if (canvasSuggestion) {
        responseMetadata.canvas_suggestion = canvasSuggestion;
      }

      // Add final message with document
      const aiMessage: Message = {
        id: nanoid(),
        content: response.content || "Documento gerado.",
        role: 'assistant',
        timestamp: new Date().toISOString(),
        metadata: Object.keys(responseMetadata).length > 0 ? responseMetadata : undefined,
      };

      set((state) => ({
        currentChat: state.currentChat
          ? {
            ...state.currentChat,
            messages: [...(state.currentChat.messages || []), aiMessage],
          }
          : null,
        isAgentRunning: false,
      }));

      // Atualiza canvas automaticamente (fluxo padrão)
      // Se houver sugestão de trecho, não sobrescreve o documento inteiro.
      if (!canvasSuggestion) {
        try {
          const { setContent: setCanvasContent, setMetadata } = useCanvasStore.getState();
          setCanvasContent(response.content || '');
          setMetadata((response as any)?.metadata || null, (response as any)?.cost_info || null);
        } catch {
          // noop
        }
      }

    } catch (e) {
      clearInterval(stepsInterval);
      console.error("StartAgentGeneration Error:", e);
      // @ts-ignore
      if (typeof window !== 'undefined') alert(`Erro na geração: ${e.message || JSON.stringify(e)}`);

      set(state => ({
        isAgentRunning: false,
        agentSteps: state.agentSteps.map(s =>
          s.status === 'working' ? { ...s, status: 'failed' as const, message: 'Erro na geração' } : s
        )
      }));
    }
  },

  startLangGraphJob: async (prompt: string) => {
    const { currentChat } = get();
    if (!currentChat) throw new Error('No chat selected');
    const persistChatId = currentChat.id;

    // Ensure UI is in "running" state (Wizard can call this directly)
    set({ isAgentRunning: true });

    try {
      const normalizedRange = normalizePageRange(get().minPages, get().maxPages);
      const hasPageRange = normalizedRange.minPages > 0 || normalizedRange.maxPages > 0;
      const contextDocumentIds = (get().activeContext || [])
        .filter((item: any) => item?.type === 'file' && typeof item.id === 'string')
        .map((item: any) => item.id);
      const hasContextDocs = contextDocumentIds.length > 0;

      const jobRes = await apiClient.startJob({
        prompt,
        web_search: get().webSearch,
        dense_research: true,
        effort_level: get().effortLevel,
        ...(hasPageRange ? { min_pages: normalizedRange.minPages, max_pages: normalizedRange.maxPages } : {}),
        ...(hasContextDocs ? { context_documents: contextDocumentIds } : {}),
        attachment_mode: get().attachmentMode,
        chat_personality: get().chatPersonality,
        reasoning_level: get().reasoningLevel,
        document_type: get().documentType,
        thesis: get().thesis,
        use_multi_agent: get().useMultiAgent,
        formatting_options: get().formattingOptions,
        citation_style: get().citationStyle,
        hil_target_sections: get().hilTargetSections,
        hil_outline_enabled: true,
        judge_model: get().selectedModel,
        gpt_model: get().gptModel,
        claude_model: get().claudeModel,
        strategist_model: get().agentStrategistModel,
        drafter_models: get().agentDrafterModels,
        reviewer_models: get().agentReviewerModels,
        adaptive_routing: get().adaptiveRouting,
        crag_gate: get().cragGate,
        hyde_enabled: get().hydeEnabled,
        graph_rag_enabled: get().graphRagEnabled,
        graph_hops: get().graphHops,
      });

      const jobId = jobRes.job_id;
      set({ currentJobId: jobId, jobEvents: [], jobOutline: [], reviewData: null });

      // Start SSE Stream
      const eventSource = new EventSource(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api'}/jobs/${jobId}/stream`);

      const handleSse = (event: MessageEvent) => {
        if (!event?.data) return;
        let data: any;
        try {
          data = JSON.parse(event.data);
        } catch {
          return;
        }

        set((state) => ({
          jobEvents: [...state.jobEvents, data],
          jobOutline: data?.type === 'outline_done' ? (data.outline || []) : state.jobOutline,
        }));

        if (data?.type === 'human_review_required') {
          set({ reviewData: { checkpoint: data.checkpoint, ...data.review_data } });
        }

        // NEW: Update Canvas Metadata in real-time for 'section' events
        if (data?.type === 'section_processed' || data?.type === 'debate_done') {
          try {
            const { setMetadata, metadata } = useCanvasStore.getState();
            // Merge with existing metadata or create new structure
            const currentSections = metadata?.processed_sections || [];

            // Helper to merge or append section
            const mergeSection = (sec: any) => {
              const sectionTitle = sec.section || sec.section_title || sec.sectionName;
              const idx = currentSections.findIndex((s: any) => s.section_title === sectionTitle);
              const detailedSec = {
                section_title: sectionTitle,
                has_significant_divergence: sec.has_divergence,
                drafts: sec.drafts, // Capture raw drafts!
                divergence_details: sec.divergence_details,
                risk_flags: sec.risk_flags,
                claims_requiring_citation: sec.claims_requiring_citation,
                removed_claims: sec.removed_claims
              };

              if (idx >= 0) {
                currentSections[idx] = { ...currentSections[idx], ...detailedSec };
              } else {
                currentSections.push(detailedSec);
              }
            };

            if (data.type === 'section_processed') {
              mergeSection(data);
            }

            const updatedMetadata = {
              ...(metadata || {}),
              processed_sections: [...currentSections],
              has_any_divergence: data.has_divergence || metadata?.has_any_divergence,
              divergence_summary: data.divergence_summary || metadata?.divergence_summary,
              full_document: data.document_preview || metadata?.full_document
            };
            setMetadata(updatedMetadata, null);
            persistDraftMetadata(persistChatId, updatedMetadata);
          } catch (e) {
            console.error("Error updating canvas metadata from stream", e);
          }
        }

        if (data?.type === 'done') {
          const aiMessage: Message = {
            id: nanoid(),
            content: data.markdown || "Documento finalizado.",
            role: 'assistant',
            timestamp: new Date().toISOString(),
          };

          set((state) => ({
            currentChat: state.currentChat
              ? {
                ...state.currentChat,
                messages: [...(state.currentChat.messages || []), aiMessage],
              }
              : null,
            isAgentRunning: false,
          }));

          // Atualiza canvas automaticamente (modo LangGraph)
          try {
            const { setContent: setCanvasContent, setMetadata, metadata } = useCanvasStore.getState();
            setCanvasContent(data.markdown || '');
            const updatedMetadata = {
              ...(metadata || {}),
              full_document: data.markdown || metadata?.full_document
            };
            setMetadata(updatedMetadata, null);
            persistDraftMetadata(persistChatId, updatedMetadata);
          } catch {
            // noop
          }

          try {
            eventSource.close();
          } catch {
            // noop
          }
        }
      };

      // Backend emits custom SSE event types: event: outline/section/done/...
      const eventNames = [
        'message',
        'status',
        'outline',
        'research',
        'section',
        'debate',
        'granular',
        'audit',
        'quality',
        'hil_decision',
        'corrections',
        'review',
        'done',
        'error',
      ];

      for (const name of eventNames) {
        eventSource.addEventListener(name, handleSse as unknown as EventListener);
      }

      eventSource.onerror = (e) => {
        console.error("SSE Error", e);
        try {
          eventSource.close();
        } catch {
          // noop
        }
        set({ isAgentRunning: false });
      };
    } catch (e) {
      console.error("Error starting job", e);
      set({ isAgentRunning: false });
      toast.error("Erro ao iniciar geração (LangGraph)");
      return;
    }
  },

  generateDocumentWithResult: async (prompt: string, caseId?: string) => {
    const { currentChat, activeContext, effortLevel, minPages, maxPages, attachmentMode, chatPersonality } = get();
    if (!currentChat) throw new Error('Crie uma conversa primeiro');

    set({ isAgentRunning: true, agentSteps: AgentOrchestrator.getInitialSteps() });

    const normalizedRange = normalizePageRange(minPages, maxPages);
    const hasPageRange = normalizedRange.minPages > 0 || normalizedRange.maxPages > 0;
    const contextDocumentIds = (activeContext || [])
      .filter((item: any) => item?.type === 'file' && typeof item.id === 'string')
      .map((item: any) => item.id);
    const hasContextDocs = contextDocumentIds.length > 0;

    try {
      const response = await apiClient.generateDocument(currentChat.id, {
        prompt,
        case_id: caseId,
        context: { active_items: activeContext },
        effort_level: effortLevel,
        ...(hasPageRange ? { min_pages: normalizedRange.minPages, max_pages: normalizedRange.maxPages } : {}),
        ...(hasContextDocs ? { context_documents: contextDocumentIds } : {}),
        attachment_mode: attachmentMode,
        chat_personality: chatPersonality,
        model: get().selectedModel,

        // Agent Mode
        use_multi_agent: get().useMultiAgent,
        model_gpt: get().gptModel,
        model_claude: get().claudeModel,
        strategist_model: get().agentStrategistModel,
        drafter_models: get().agentDrafterModels,
        reviewer_models: get().agentReviewerModels,
        reasoning_level: get().reasoningLevel,

        // Flags
        web_search: get().webSearch,
        dense_research: get().denseResearch,
        thinking_level: get().reasoningLevel,
        audit: get().audit,

        // Document Meta
        document_type: get().documentType,
        thesis: get().thesis,
        formatting_options: get().formattingOptions,

        // RAG Config (Flattened for Backend Adapter)
        rag_top_k: get().ragTopK,
        rag_sources: get().ragSources,
        tenant_id: get().tenantId,
        use_templates: get().useTemplates,
        template_filters: get().templateFilters,
        prompt_extra: get().promptExtra,
        template_id: get().templateId || undefined,
        variables: get().templateVariables,
        adaptive_routing: get().adaptiveRouting,
        crag_gate: get().cragGate,
        hyde_enabled: get().hydeEnabled,
        graph_rag_enabled: get().graphRagEnabled,
        graph_hops: get().graphHops,

        // Context Caching (v3.4)
        // Only send if mode is upload_cache, or generic handling
        // We'll add these fields to ApiClient request type too
        context_files: get().contextMode === 'upload_cache' ? get().contextFiles : undefined,
        cache_ttl: get().contextMode === 'upload_cache' ? get().cacheTTL : undefined
      });

      // Add assistant message to chat local history
      const aiMessage: Message = {
        id: nanoid(),
        content: response.content || "Documento gerado.",
        role: 'assistant',
        timestamp: new Date().toISOString(),
      };

      set((state) => ({
        currentChat: state.currentChat
          ? {
            ...state.currentChat,
            messages: [...(state.currentChat.messages || []), aiMessage],
          }
          : null,
        isAgentRunning: false,
        agentSteps: state.agentSteps.map(s => ({ ...s, status: 'completed' }))
      }));

      // Atualiza canvas automaticamente (helper usado por /minuta antigo)
      try {
        const { setContent: setCanvasContent, setMetadata } = useCanvasStore.getState();
        setCanvasContent(response.content || '');
        setMetadata((response as any)?.metadata || null, (response as any)?.cost_info || null);
      } catch {
        // noop
      }

      return response;
    } catch (error) {
      set({ isAgentRunning: false });
      throw error;
    }
  },

  generateDocument: async (data) => {
    // Legacy method, redirect to sendMessage
    return get().sendMessage(data.prompt);
  },

  submitReview: async (decision) => {
    const { currentJobId } = get();
    if (!currentJobId) return;

    // Optimistic close
    set({ reviewData: null });

    if (Array.isArray((decision as any)?.hil_target_sections)) {
      set({ hilTargetSections: (decision as any).hil_target_sections });
    }

    await apiClient.resumeJob(currentJobId, decision);
  },

  // ===========================================================================
  // MULTI-MODEL STREAMING (V2)
  // ===========================================================================

  consolidateTurn: async (turnId: string) => {
    const { currentChat } = get();
    if (!currentChat) return;
    if (!turnId) return;

    // Evita duplicar
    const already = currentChat.messages.some(
      (m) => m.role === 'assistant' && m.metadata?.turn_id === turnId && (m.metadata?.is_consolidated || String(m.metadata?.model || '').toLowerCase() === 'consolidado')
    );
    if (already) {
      toast.info('Consolidado já foi gerado para este turno.');
      return;
    }

    const userMsg = currentChat.messages.find((m) => m.role === 'user' && m.metadata?.turn_id === turnId);
    const userText = userMsg?.content || '';

    const candidates = currentChat.messages
      .filter((m) => m.role === 'assistant' && m.metadata?.turn_id === turnId && m.metadata?.model && !m.metadata?.is_consolidated)
      .map((m) => ({ model: String(m.metadata.model), text: String(m.content || '').trim() }))
      .filter((c) => c.text.length > 0);

    if (candidates.length < 2) {
      toast.info('Preciso de pelo menos 2 respostas para consolidar.');
      return;
    }

    toast.info('Gerando Consolidado (consome tokens adicionais)...');
    const res = await apiClient.consolidateMultiChatTurn(currentChat.id, { message: userText, candidates });

    const consolidatedMsg: Message = {
      id: nanoid(),
      role: 'assistant',
      content: res.content || '',
      timestamp: new Date().toISOString(),
      metadata: { model: 'Consolidado', turn_id: turnId, is_consolidated: true },
    };

    set((state) => ({
      currentChat: state.currentChat
        ? { ...state.currentChat, messages: [...(state.currentChat.messages || []), consolidatedMsg] }
        : null,
    }));
    toast.success('Consolidado gerado.');
  },

  startMultiModelStream: async (content: string) => {
    const { currentChat, selectedModels, gptModel, claudeModel, chatPersonality } = get();
    if (!currentChat) throw new Error("No chat");

    // --- Model Shortcut Parsing ---
    // Detects @model prefix and overrides selectedModels for this turn only.
    const MODEL_SHORTCUTS: Record<string, string> = {
      '@gpt': gptModel || 'gpt-5.2',
      '@claude': claudeModel || 'claude-4.5-sonnet',
      '@gemini': 'gemini-3-flash',
      '@gemini-pro': 'gemini-3-pro',
      '@mini': 'gpt-5-mini',
      '@flash': 'gemini-3-flash',
      '@haiku': 'claude-4.5-haiku',
    };

    let actualContent = content.trim();
    let targetModels = [...selectedModels];

    for (const [shortcut, modelId] of Object.entries(MODEL_SHORTCUTS)) {
      if (actualContent.toLowerCase().startsWith(shortcut)) {
        // Remove the shortcut from content
        actualContent = actualContent.slice(shortcut.length).trim();
        // Override models for this turn
        targetModels = [modelId];
        toast.info(`Roteando para ${modelId}`);
        break;
      }
    }

    // Identificador único do "turno" para agrupar respostas multi-modelo na UI
    const turnId = nanoid();

    // 1. Add User Message (show original content with shortcut for transparency)
    const userMsg: Message = {
      id: nanoid(),
      content, // Keep original for display
      role: 'user',
      timestamp: new Date().toISOString(),
      metadata: { turn_id: turnId }
    };

    set(state => ({
      currentChat: state.currentChat ? {
        ...state.currentChat,
        messages: [...(state.currentChat.messages || []), userMsg]
      } : null,
      isSending: true
    }));

    try {
      // 2. Fetch SSE Stream (use targetModels which may be overridden, and actualContent which has shortcut stripped)
      const response = await apiClient.fetchWithAuth(`/multi-chat/threads/${currentChat.id}/messages`, {
        method: 'POST',
        body: JSON.stringify({
          message: actualContent,
          models: targetModels,
          chat_personality: chatPersonality
        })
      });

      if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      // Captura do texto completo por modelo para gerar "Consolidado" ao final (opcional)
      const fullTextByModel: Record<string, string> = {};
      selectedModels.forEach((m) => {
        fullTextByModel[m] = '';
      });

      // Prepare placeholders for assistant responses
      // Map modelId -> messageId
      const modelMessageIds: Record<string, string> = {};
      selectedModels.forEach(m => {
        modelMessageIds[m] = nanoid();
      });

      // Init empty messages for each model
      set(state => {
        if (!state.currentChat) return {};

        const newMessages = selectedModels.map(m => ({
          id: modelMessageIds[m],
          role: 'assistant' as const,
          content: '',
          timestamp: new Date().toISOString(),
          metadata: { model: m, turn_id: turnId }
        }));

        return {
          currentChat: {
            ...state.currentChat,
            messages: [...(state.currentChat.messages || []), ...newMessages]
          }
        };
      });

      // 3. Read Loop
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const jsonStr = line.slice(6);
            if (jsonStr === '[DONE]') continue;

            try {
              const data = JSON.parse(jsonStr);
              // { type: "token", model: "gpt-4o", delta: "..." }

              if (data.type === 'token' && data.model && data.delta) {
                const msgId = modelMessageIds[data.model];
                if (msgId) {
                  fullTextByModel[data.model] = (fullTextByModel[data.model] || '') + data.delta;
                  // Append delta to specific message
                  set(state => {
                    if (!state.currentChat) return {};
                    const msgs = state.currentChat.messages.map(m => {
                      if (m.id === msgId) {
                        return { ...m, content: m.content + data.delta };
                      }
                      return m;
                    });
                    return { currentChat: { ...state.currentChat, messages: msgs } };
                  });
                }
              }

              if (data.type === 'usage' && data.model && data.usage) {
                const msgId = modelMessageIds[data.model];
                if (msgId) {
                  set(state => {
                    if (!state.currentChat) return {};
                    const msgs = state.currentChat.messages.map(m => {
                      if (m.id === msgId) {
                        return {
                          ...m,
                          metadata: { ...m.metadata, token_usage: data.usage }
                        };
                      }
                      return m;
                    });
                    return { currentChat: { ...state.currentChat, messages: msgs } };
                  });
                }
              }

              if (data.type === 'error') {
                toast.error(`Erro no modelo ${data.model}: ${data.error}`);
              }

            } catch (e) {
              console.error("JSON parse error", e);
            }
          }
        }
      }

      // Gerar resposta consolidada (juiz) — somente se comparador estiver ligado e houver 2+ respostas
      try {
        const { showMultiModelComparator, autoConsolidate } = get();
        const candidates = selectedModels
          .map((m) => ({ model: m, text: (fullTextByModel[m] || '').trim() }))
          .filter((c) => c.text.length > 0);

        if (showMultiModelComparator && autoConsolidate && candidates.length >= 2) {
          const res = await apiClient.consolidateMultiChatTurn(currentChat.id, { message: content, candidates });
          const consolidatedMsg: Message = {
            id: nanoid(),
            role: 'assistant',
            content: res.content || '',
            timestamp: new Date().toISOString(),
            metadata: { model: 'Consolidado', turn_id: turnId, is_consolidated: true }
          };

          set(state => ({
            currentChat: state.currentChat ? {
              ...state.currentChat,
              messages: [...(state.currentChat.messages || []), consolidatedMsg]
            } : null
          }));
        }
      } catch (e) {
        console.error("Consolidation error", e);
      }

    } catch (error) {
      console.error("Multi-model stream error", error);
      toast.error("Erro no stream multi-modelo");
    } finally {
      set({ isSending: false });
    }
  }
}));
