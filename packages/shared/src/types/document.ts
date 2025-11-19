/**
 * Tipos relacionados a documentos
 */

export enum DocumentType {
  PDF = 'PDF',
  DOCX = 'DOCX',
  DOC = 'DOC',
  ODT = 'ODT',
  TXT = 'TXT',
  RTF = 'RTF',
  HTML = 'HTML',
  IMAGE = 'IMAGE',
  AUDIO = 'AUDIO',
  VIDEO = 'VIDEO',
  ZIP = 'ZIP',
}

export enum DocumentStatus {
  UPLOADING = 'UPLOADING',
  PROCESSING = 'PROCESSING',
  READY = 'READY',
  ERROR = 'ERROR',
}

export enum DocumentCategory {
  PROCESSO = 'PROCESSO',
  PETICAO = 'PETICAO',
  SENTENCA = 'SENTENCA',
  ACORDAO = 'ACORDAO',
  CONTRATO = 'CONTRATO',
  PARECER = 'PARECER',
  LEI = 'LEI',
  OUTRO = 'OUTRO',
}

export interface Document {
  id: string;
  userId: string;
  name: string;
  originalName: string;
  type: DocumentType;
  category?: DocumentCategory;
  status: DocumentStatus;
  size: number;
  url: string;
  thumbnailUrl?: string;
  content?: string;
  extractedText?: string;
  metadata: DocumentMetadata;
  tags: string[];
  folderId?: string;
  isShared: boolean;
  isArchived: boolean;
  createdAt: Date;
  updatedAt: Date;
}

export interface DocumentMetadata {
  pages?: number;
  language?: string;
  author?: string;
  createdDate?: string;
  modifiedDate?: string;
  fileHash?: string;
  ocrApplied?: boolean;
  processNumber?: string;
  court?: string;
  parties?: {
    plaintiff?: string[];
    defendant?: string[];
  };
  cnjMetadata?: CNJMetadata;
  customFields?: Record<string, any>;
}

export interface CNJMetadata {
  processNumber: string;
  tribunal: string;
  classe: string;
  assunto: string;
  vara: string;
  comarca: string;
  distribuicao: string;
  valorCausa?: number;
}

export interface DocumentUploadRequest {
  file: File | Buffer;
  name: string;
  category?: DocumentCategory;
  folderId?: string;
  tags?: string[];
  applyOCR?: boolean;
  extractMetadata?: boolean;
}

export interface DocumentChunk {
  id: string;
  documentId: string;
  content: string;
  embedding?: number[];
  position: number;
  metadata: {
    page?: number;
    section?: string;
  };
}

export interface DocumentSummary {
  id: string;
  documentId: string;
  type: 'quick' | 'detailed' | 'audio' | 'podcast';
  content: string;
  audioUrl?: string;
  duration?: number;
  createdAt: Date;
}

export interface DocumentAction {
  id: string;
  name: string;
  description: string;
  prompt: string;
  icon?: string;
}

