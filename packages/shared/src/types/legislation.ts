/**
 * Tipos relacionados à legislação
 */

export enum LegislationType {
  CONSTITUICAO = 'CONSTITUICAO',
  LEI_COMPLEMENTAR = 'LEI_COMPLEMENTAR',
  LEI_ORDINARIA = 'LEI_ORDINARIA',
  DECRETO_LEI = 'DECRETO_LEI',
  DECRETO = 'DECRETO',
  MEDIDA_PROVISORIA = 'MEDIDA_PROVISORIA',
  RESOLUCAO = 'RESOLUCAO',
  PORTARIA = 'PORTARIA',
  INSTRUCAO_NORMATIVA = 'INSTRUCAO_NORMATIVA',
}

export enum LegislationLevel {
  FEDERAL = 'FEDERAL',
  ESTADUAL = 'ESTADUAL',
  MUNICIPAL = 'MUNICIPAL',
}

export interface Legislation {
  id: string;
  type: LegislationType;
  level: LegislationLevel;
  number: string;
  year: number;
  date: Date;
  ementa: string;
  fullText?: string;
  url?: string;
  state?: string;
  city?: string;
  tags: string[];
  chapters: LegislationChapter[];
  metadata: LegislationMetadata;
  createdAt: Date;
  updatedAt: Date;
}

export interface LegislationChapter {
  id: string;
  title: string;
  number?: string;
  articles: LegislationArticle[];
}

export interface LegislationArticle {
  id: string;
  number: string;
  content: string;
  paragraphs: LegislationParagraph[];
  incisos: LegislationInciso[];
  isRevoked: boolean;
  observations?: string;
}

export interface LegislationParagraph {
  id: string;
  number: string;
  content: string;
  incisos?: LegislationInciso[];
}

export interface LegislationInciso {
  id: string;
  number: string;
  content: string;
  alineas?: LegislationAlinea[];
}

export interface LegislationAlinea {
  id: string;
  letter: string;
  content: string;
}

export interface LegislationMetadata {
  publicacao?: string;
  vigencia?: Date;
  autoria?: string;
  status: 'VIGENTE' | 'REVOGADA' | 'SUSPENSA';
  alteracoes?: string[];
  regulamentacoes?: string[];
}

export interface LegislationSearchRequest {
  query: string;
  types?: LegislationType[];
  levels?: LegislationLevel[];
  yearFrom?: number;
  yearTo?: number;
  state?: string;
  city?: string;
  maxResults?: number;
}

export interface LegislationSearchResult {
  items: Legislation[];
  total: number;
  query: string;
}

export interface SelectedLegislation {
  legislationId: string;
  selectedArticles: string[]; // IDs dos artigos selecionados
  fullLegislation: boolean; // Se toda a legislação está selecionada
}

