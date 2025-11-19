/**
 * Tipos relacionados à jurisprudência
 */

export enum TribunalLevel {
  FEDERAL = 'FEDERAL',
  ESTADUAL = 'ESTADUAL',
  SUPERIOR = 'SUPERIOR',
  ESPECIAL = 'ESPECIAL',
}

export enum TribunalType {
  STF = 'STF',
  STJ = 'STJ',
  TST = 'TST',
  TSE = 'TSE',
  STM = 'STM',
  TRF = 'TRF',
  TRT = 'TRT',
  TRE = 'TRE',
  TJ = 'TJ',
  CARF = 'CARF',
}

export interface Tribunal {
  id: string;
  code: TribunalType;
  name: string;
  level: TribunalLevel;
  state?: string;
  region?: number;
}

export interface Jurisprudence {
  id: string;
  tribunal: TribunalType;
  type: 'ACORDAO' | 'SUMULA' | 'INFORMATIVO';
  number: string;
  date: Date;
  ementa: string;
  fullText?: string;
  relator?: string;
  orgaoJulgador?: string;
  tags: string[];
  relevance?: number;
  isGeneralRepercussion?: boolean;
  url?: string;
  metadata: JurisprudenceMetadata;
  createdAt: Date;
}

export interface JurisprudenceMetadata {
  processNumber?: string;
  classe?: string;
  assunto?: string[];
  decisao?: string;
  publicacao?: string;
  legislacaoCitada?: string[];
  jurisprudenciaCitada?: string[];
}

export interface JurisprudenceSearchRequest {
  query: string;
  tribunals: TribunalType[];
  types?: Array<'ACORDAO' | 'SUMULA' | 'INFORMATIVO'>;
  dateFrom?: Date;
  dateTo?: Date;
  states?: string[];
  regions?: number[];
  maxResults?: number;
  includeGeneralRepercussion?: boolean;
}

export interface JurisprudenceSearchResult {
  items: Jurisprudence[];
  total: number;
  query: string;
  processingTime: number;
}

export interface Sumula {
  id: string;
  tribunal: TribunalType;
  number: number;
  type: 'SUMULA' | 'SUMULA_VINCULANTE';
  text: string;
  observacao?: string;
  aprovacao: Date;
  publicacao?: Date;
  url?: string;
}

