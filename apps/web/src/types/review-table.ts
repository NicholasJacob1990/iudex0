/**
 * Types for Review Tables feature
 * Supports dynamic columns, cell extraction, and verification
 */

// ============= Dynamic Columns =============

export type ExtractionType =
  | 'text'
  | 'number'
  | 'date'
  | 'boolean'
  | 'currency'
  | 'list'
  | 'entity';

export interface DynamicColumn {
  id: string;
  table_id: string;
  name: string;
  prompt: string;
  extraction_type: ExtractionType;
  order_index: number;
  is_visible: boolean;
  created_at: string;
  updated_at: string;
  metadata?: Record<string, unknown>;
}

export interface CreateColumnRequest {
  prompt: string;
  name?: string;
  extraction_type?: ExtractionType;
}

// ============= Cell Extraction =============

export type CellStatus = 'pending' | 'processing' | 'completed' | 'error';

export interface CellExtraction {
  id: string;
  table_id: string;
  document_id: string;
  column_id: string;
  value: string | number | boolean | null;
  raw_value?: string;
  confidence: number;
  status: CellStatus;
  is_verified: boolean;
  verified_by?: string;
  verified_at?: string;
  correction?: string;
  source_snippet?: string;
  source_page?: number;
  error_message?: string;
  created_at: string;
  updated_at: string;
  metadata?: Record<string, unknown>;
}

export interface VerifyCellRequest {
  verified: boolean;
  correction?: string;
}

export interface BulkVerifyRequest {
  cell_ids: string[];
  verified: boolean;
}

// ============= Review Table =============

export interface ReviewTable {
  id: string;
  name: string;
  description?: string;
  user_id: string;
  document_ids: string[];
  created_at: string;
  updated_at: string;
  metadata?: Record<string, unknown>;
}

export interface ReviewTableDocument {
  id: string;
  name: string;
  file_type: string;
  file_size: number;
  status: 'pending' | 'processing' | 'completed' | 'error';
  created_at: string;
}

// ============= Extraction Jobs =============

export type JobStatus =
  | 'pending'
  | 'running'
  | 'paused'
  | 'completed'
  | 'error'
  | 'cancelled';

export interface ExtractionJob {
  id: string;
  table_id: string;
  status: JobStatus;
  column_ids?: string[];
  total_documents: number;
  processed_documents: number;
  error_count: number;
  errors?: Array<{
    document_id: string;
    column_id: string;
    error: string;
  }>;
  started_at?: string;
  completed_at?: string;
  created_at: string;
  updated_at: string;
}

// ============= Ask Table =============

export interface TableChatMessage {
  id: string;
  table_id: string;
  role: 'user' | 'assistant';
  content: string;
  structured_data?: {
    type: 'table' | 'chart' | 'list' | 'summary';
    data: unknown;
    document_refs?: Array<{
      document_id: string;
      document_name: string;
      page?: number;
    }>;
  };
  created_at: string;
}

export interface AskTableRequest {
  question: string;
  include_sources?: boolean;
}

export interface AskTableResponse {
  answer: string;
  structured_data?: TableChatMessage['structured_data'];
  sources?: Array<{
    document_id: string;
    document_name: string;
    snippet: string;
    page?: number;
  }>;
}

// ============= Verification Stats =============

export interface VerificationStats {
  total_cells: number;
  verified_cells: number;
  pending_cells: number;
  low_confidence_cells: number;
  verification_percentage: number;
}

// ============= Filter Types =============

export type FilterOperator =
  | 'equals'
  | 'not_equals'
  | 'contains'
  | 'not_contains'
  | 'starts_with'
  | 'ends_with'
  | 'greater_than'
  | 'less_than'
  | 'between'
  | 'is_empty'
  | 'is_not_empty';

export interface FilterValue {
  operator: FilterOperator;
  value: string | number | boolean | null;
  value2?: string | number | null; // For 'between' operator
}

// ============= Table State =============

export interface ReviewTableState {
  table: ReviewTable | null;
  columns: DynamicColumn[];
  documents: ReviewTableDocument[];
  cells: Map<string, CellExtraction>; // key: `${docId}:${colId}`

  // UI State
  visibleColumns: Set<string>;
  columnOrder: string[];
  sortColumn: string | null;
  sortDirection: 'asc' | 'desc';
  filters: Map<string, FilterValue>;
  showVerifiedOnly: boolean;
  showLowConfidenceOnly: boolean;

  // Loading states
  isLoading: boolean;
  isLoadingCells: boolean;

  // Active job
  activeJob: ExtractionJob | null;

  // Chat
  chatMessages: TableChatMessage[];
  isChatOpen: boolean;

  // Column builder
  isColumnBuilderOpen: boolean;

  // Verification stats
  verificationStats: VerificationStats | null;
}
