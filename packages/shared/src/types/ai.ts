/**
 * Tipos relacionados ao sistema de IA
 */

export enum AIModel {
  CLAUDE_SONNET_4_5 = 'CLAUDE_SONNET_4_5',
  GEMINI_2_5_PRO = 'GEMINI_2_5_PRO',
  GPT_5 = 'GPT_5',
}

export enum AIProvider {
  ANTHROPIC = 'ANTHROPIC',
  GOOGLE = 'GOOGLE',
  OPENAI = 'OPENAI',
}

export enum AgentRole {
  GENERATOR = 'GENERATOR', // Gera o documento inicial
  LEGAL_REVIEWER = 'LEGAL_REVIEWER', // Revisa precisão jurídica
  TEXT_REVIEWER = 'TEXT_REVIEWER', // Revisa qualidade textual
  ORCHESTRATOR = 'ORCHESTRATOR', // Coordena os agentes
}

export interface AIAgent {
  id: string;
  name: string;
  role: AgentRole;
  model: AIModel;
  provider: AIProvider;
  systemPrompt: string;
  temperature: number;
  maxTokens: number;
  isActive: boolean;
}

export interface AIMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
  name?: string;
  metadata?: Record<string, any>;
}

export interface AIGenerationRequest {
  messages: AIMessage[];
  model: AIModel;
  temperature?: number;
  maxTokens?: number;
  stream?: boolean;
  tools?: AITool[];
}

export interface AIGenerationResponse {
  id: string;
  content: string;
  model: AIModel;
  usage: TokenUsage;
  finishReason: 'stop' | 'length' | 'content_filter' | 'tool_calls';
  toolCalls?: AIToolCall[];
  metadata?: Record<string, any>;
}

export interface TokenUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  estimatedCost: number;
}

export interface AITool {
  name: string;
  description: string;
  parameters: Record<string, any>;
}

export interface AIToolCall {
  id: string;
  name: string;
  arguments: Record<string, any>;
}

export interface MultiAgentContext {
  documentIds: string[];
  modelIds: string[];
  jurisprudenceIds: string[];
  legislationIds: string[];
  webSearches: string[];
  libraryItems: string[];
  customInstructions?: string;
  verbosity: 'concise' | 'balanced' | 'detailed';
  effort: 1 | 2 | 3 | 4 | 5;
  useProfile?: string;
}

export interface AgentReview {
  agentId: string;
  agentRole: AgentRole;
  originalContent: string;
  suggestedChanges: string;
  comments: string[];
  score: number;
  timestamp: Date;
}

export interface MultiAgentResult {
  finalContent: string;
  reviews: AgentReview[];
  consensus: boolean;
  conflicts: string[];
  totalTokens: TokenUsage;
  processingTime: number;
}

