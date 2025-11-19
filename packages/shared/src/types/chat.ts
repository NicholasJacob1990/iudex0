/**
 * Tipos relacionados ao chat e minutas
 */

export enum ChatMode {
  CHAT = 'CHAT', // Modo conversa
  MINUTA = 'MINUTA', // Modo geração de minuta
}

export interface Chat {
  id: string;
  userId: string;
  title: string;
  mode: ChatMode;
  context: ChatContext;
  messages: ChatMessage[];
  generatedDocument?: GeneratedDocument;
  isActive: boolean;
  createdAt: Date;
  updatedAt: Date;
}

export interface ChatContext {
  documentIds: string[];
  modelIds: string[];
  jurisprudenceIds: string[];
  legislationIds: string[];
  webSearchEnabled: boolean;
  librarianId?: string;
  profile?: string;
}

export interface ChatMessage {
  id: string;
  chatId: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  attachments?: MessageAttachment[];
  thinking?: string; // Pensamento do modelo (modo esforço 5)
  metadata?: {
    model?: string;
    tokens?: number;
    cost?: number;
    processingTime?: number;
  };
  createdAt: Date;
}

export interface MessageAttachment {
  type: 'document' | 'image' | 'audio';
  id: string;
  name: string;
  url: string;
}

export interface GeneratedDocument {
  id: string;
  chatId: string;
  title: string;
  content: string;
  format: 'html' | 'markdown';
  template?: string;
  revisions: DocumentRevision[];
  exportedVersions: ExportedVersion[];
  createdAt: Date;
  updatedAt: Date;
}

export interface DocumentRevision {
  id: string;
  content: string;
  prompt: string;
  agentReviews?: any[];
  createdAt: Date;
}

export interface ExportedVersion {
  id: string;
  format: 'docx' | 'pdf' | 'odt';
  url: string;
  template?: string;
  createdAt: Date;
}

export interface ChatInstruction {
  text: string;
  mode: ChatMode;
  verbosity: 'concise' | 'balanced' | 'detailed';
  effort: 1 | 2 | 3 | 4 | 5;
  profile?: string;
  useWebSearch: boolean;
}

