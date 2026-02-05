import { create } from 'zustand';
import apiClient from '@/lib/api-client';
import type {
  ReviewTable,
  ReviewTableDocument,
  DynamicColumn,
  CellExtraction,
  ExtractionJob,
  TableChatMessage,
  VerificationStats,
  FilterValue,
  ReviewTableState,
} from '@/types/review-table';

interface ReviewTableActions {
  // Table operations
  loadTable: (tableId: string) => Promise<void>;
  setTable: (table: ReviewTable | null) => void;
  clearTable: () => void;

  // Column operations
  addColumn: (column: DynamicColumn) => void;
  updateColumn: (column: DynamicColumn) => void;
  removeColumn: (columnId: string) => void;
  reorderColumns: (columnIds: string[]) => void;
  toggleColumnVisibility: (columnId: string) => void;
  setAllColumnsVisible: (visible: boolean) => void;

  // Cell operations
  updateCell: (cell: CellExtraction) => void;
  updateCells: (cells: CellExtraction[]) => void;
  getCellKey: (docId: string, colId: string) => string;
  getCell: (docId: string, colId: string) => CellExtraction | undefined;

  // Document operations
  addDocuments: (documents: ReviewTableDocument[]) => void;
  removeDocument: (documentId: string) => void;

  // Sorting and filtering
  setSortColumn: (columnId: string | null) => void;
  toggleSortDirection: () => void;
  setFilter: (columnId: string, filter: FilterValue | null) => void;
  clearFilters: () => void;
  setShowVerifiedOnly: (show: boolean) => void;
  setShowLowConfidenceOnly: (show: boolean) => void;

  // Job operations
  setActiveJob: (job: ExtractionJob | null) => void;
  updateJobProgress: (processed: number, errors?: number) => void;

  // Chat operations
  addChatMessage: (message: TableChatMessage) => void;
  setChatMessages: (messages: TableChatMessage[]) => void;
  clearChatMessages: () => void;
  setIsChatOpen: (open: boolean) => void;

  // Column builder
  setIsColumnBuilderOpen: (open: boolean) => void;

  // Verification stats
  setVerificationStats: (stats: VerificationStats | null) => void;

  // Loading states
  setIsLoading: (loading: boolean) => void;
  setIsLoadingCells: (loading: boolean) => void;

  // Computed getters
  getFilteredDocuments: () => ReviewTableDocument[];
  getSortedDocuments: () => ReviewTableDocument[];
  getVisibleColumns: () => DynamicColumn[];
}

type ReviewTableStore = ReviewTableState & ReviewTableActions;

const initialState: ReviewTableState = {
  table: null,
  columns: [],
  documents: [],
  cells: new Map(),
  visibleColumns: new Set(),
  columnOrder: [],
  sortColumn: null,
  sortDirection: 'asc',
  filters: new Map(),
  showVerifiedOnly: false,
  showLowConfidenceOnly: false,
  isLoading: false,
  isLoadingCells: false,
  activeJob: null,
  chatMessages: [],
  isChatOpen: false,
  isColumnBuilderOpen: false,
  verificationStats: null,
};

export const useReviewTableStore = create<ReviewTableStore>((set, get) => ({
  ...initialState,

  // Table operations
  loadTable: async (tableId: string) => {
    set({ isLoading: true });
    try {
      // Load table data - documents are part of the table response
      const table = await apiClient.getReviewTable(tableId);

      // Load columns and stats in parallel
      const [columns, stats] = await Promise.all([
        apiClient.listDynamicColumns(tableId).catch(() => []),
        apiClient.getVerificationStats(tableId).catch(() => null),
      ]);

      // Extract documents from table response (document_ids) or results
      const documents: ReviewTableDocument[] = (table.document_ids || []).map((id: string, index: number) => ({
        id,
        name: table.results?.[index]?.document_name || `Documento ${index + 1}`,
        file_type: 'pdf',
        file_size: 0,
        status: 'completed' as const,
        created_at: table.created_at,
      }));

      const columnOrder = columns.map((c: DynamicColumn) => c.id);
      const visibleColumns = new Set(
        columns.filter((c: DynamicColumn) => c.is_visible !== false).map((c: DynamicColumn) => c.id)
      );

      set({
        table,
        columns,
        documents,
        columnOrder,
        visibleColumns,
        verificationStats: stats,
        isLoading: false,
      });

      // Load cells in background if we have columns
      if (columns.length > 0) {
        set({ isLoadingCells: true });
        try {
          const cellsResponse = await apiClient.getReviewTableCells(tableId);
          // Handle both array and paginated response formats
          const cellsArray: CellExtraction[] = Array.isArray(cellsResponse)
            ? cellsResponse
            : (cellsResponse as { items?: CellExtraction[] })?.items || [];
          const cellMap = new Map<string, CellExtraction>();
          cellsArray.forEach((cell) => {
            const key = `${cell.document_id}:${cell.column_id}`;
            cellMap.set(key, cell);
          });
          set({ cells: cellMap, isLoadingCells: false });
        } catch (error) {
          console.error('Error loading cells:', error);
          set({ isLoadingCells: false });
        }
      }
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  setTable: (table) => set({ table }),

  clearTable: () => set(initialState),

  // Column operations
  addColumn: (column) =>
    set((state) => ({
      columns: [...state.columns, column],
      columnOrder: [...state.columnOrder, column.id],
      visibleColumns: new Set([...state.visibleColumns, column.id]),
    })),

  updateColumn: (column) =>
    set((state) => ({
      columns: state.columns.map((c) => (c.id === column.id ? column : c)),
    })),

  removeColumn: (columnId) =>
    set((state) => {
      const newVisibleColumns = new Set(state.visibleColumns);
      newVisibleColumns.delete(columnId);

      // Also remove cells for this column
      const newCells = new Map(state.cells);
      for (const key of newCells.keys()) {
        if (key.endsWith(`:${columnId}`)) {
          newCells.delete(key);
        }
      }

      return {
        columns: state.columns.filter((c) => c.id !== columnId),
        columnOrder: state.columnOrder.filter((id) => id !== columnId),
        visibleColumns: newVisibleColumns,
        cells: newCells,
      };
    }),

  reorderColumns: (columnIds) => set({ columnOrder: columnIds }),

  toggleColumnVisibility: (columnId) =>
    set((state) => {
      const newVisibleColumns = new Set(state.visibleColumns);
      if (newVisibleColumns.has(columnId)) {
        newVisibleColumns.delete(columnId);
      } else {
        newVisibleColumns.add(columnId);
      }
      return { visibleColumns: newVisibleColumns };
    }),

  setAllColumnsVisible: (visible) =>
    set((state) => ({
      visibleColumns: visible
        ? new Set(state.columns.map((c) => c.id))
        : new Set(),
    })),

  // Cell operations
  updateCell: (cell) =>
    set((state) => {
      const key = `${cell.document_id}:${cell.column_id}`;
      const newCells = new Map(state.cells);
      newCells.set(key, cell);
      return { cells: newCells };
    }),

  updateCells: (cells) =>
    set((state) => {
      const newCells = new Map(state.cells);
      cells.forEach((cell) => {
        const key = `${cell.document_id}:${cell.column_id}`;
        newCells.set(key, cell);
      });
      return { cells: newCells };
    }),

  getCellKey: (docId, colId) => `${docId}:${colId}`,

  getCell: (docId, colId) => {
    const key = `${docId}:${colId}`;
    return get().cells.get(key);
  },

  // Document operations
  addDocuments: (documents) =>
    set((state) => ({
      documents: [...state.documents, ...documents],
    })),

  removeDocument: (documentId) =>
    set((state) => {
      // Also remove cells for this document
      const newCells = new Map(state.cells);
      for (const key of newCells.keys()) {
        if (key.startsWith(`${documentId}:`)) {
          newCells.delete(key);
        }
      }

      return {
        documents: state.documents.filter((d) => d.id !== documentId),
        cells: newCells,
      };
    }),

  // Sorting and filtering
  setSortColumn: (columnId) =>
    set((state) => ({
      sortColumn: columnId,
      sortDirection: state.sortColumn === columnId ? state.sortDirection : 'asc',
    })),

  toggleSortDirection: () =>
    set((state) => ({
      sortDirection: state.sortDirection === 'asc' ? 'desc' : 'asc',
    })),

  setFilter: (columnId, filter) =>
    set((state) => {
      const newFilters = new Map(state.filters);
      if (filter) {
        newFilters.set(columnId, filter);
      } else {
        newFilters.delete(columnId);
      }
      return { filters: newFilters };
    }),

  clearFilters: () => set({ filters: new Map() }),

  setShowVerifiedOnly: (show) => set({ showVerifiedOnly: show }),

  setShowLowConfidenceOnly: (show) => set({ showLowConfidenceOnly: show }),

  // Job operations
  setActiveJob: (job) => set({ activeJob: job }),

  updateJobProgress: (processed, errors) =>
    set((state) => {
      if (!state.activeJob) return state;
      return {
        activeJob: {
          ...state.activeJob,
          processed_documents: processed,
          error_count: errors ?? state.activeJob.error_count,
        },
      };
    }),

  // Chat operations
  addChatMessage: (message) =>
    set((state) => ({
      chatMessages: [...state.chatMessages, message],
    })),

  setChatMessages: (messages) => set({ chatMessages: messages }),

  clearChatMessages: () => set({ chatMessages: [] }),

  setIsChatOpen: (open) => set({ isChatOpen: open }),

  // Column builder
  setIsColumnBuilderOpen: (open) => set({ isColumnBuilderOpen: open }),

  // Verification stats
  setVerificationStats: (stats) => set({ verificationStats: stats }),

  // Loading states
  setIsLoading: (loading) => set({ isLoading: loading }),

  setIsLoadingCells: (loading) => set({ isLoadingCells: loading }),

  // Computed getters
  getFilteredDocuments: () => {
    const state = get();
    let docs = [...state.documents];

    // Apply filters based on cell values
    if (state.filters.size > 0) {
      docs = docs.filter((doc) => {
        for (const [columnId, filter] of state.filters) {
          const cell = state.cells.get(`${doc.id}:${columnId}`);
          if (!cell) continue;

          const value = cell.value;
          const filterValue = filter.value;

          switch (filter.operator) {
            case 'equals':
              if (value !== filterValue) return false;
              break;
            case 'not_equals':
              if (value === filterValue) return false;
              break;
            case 'contains':
              if (
                typeof value !== 'string' ||
                typeof filterValue !== 'string' ||
                !value.toLowerCase().includes(filterValue.toLowerCase())
              )
                return false;
              break;
            case 'not_contains':
              if (
                typeof value === 'string' &&
                typeof filterValue === 'string' &&
                value.toLowerCase().includes(filterValue.toLowerCase())
              )
                return false;
              break;
            case 'is_empty':
              if (value !== null && value !== '' && value !== undefined) return false;
              break;
            case 'is_not_empty':
              if (value === null || value === '' || value === undefined) return false;
              break;
            case 'greater_than':
              if (typeof value !== 'number' || typeof filterValue !== 'number' || value <= filterValue)
                return false;
              break;
            case 'less_than':
              if (typeof value !== 'number' || typeof filterValue !== 'number' || value >= filterValue)
                return false;
              break;
          }
        }
        return true;
      });
    }

    // Filter by verification status
    if (state.showVerifiedOnly) {
      docs = docs.filter((doc) => {
        for (const column of state.columns) {
          const cell = state.cells.get(`${doc.id}:${column.id}`);
          if (cell && !cell.is_verified) return false;
        }
        return true;
      });
    }

    // Filter by low confidence
    if (state.showLowConfidenceOnly) {
      docs = docs.filter((doc) => {
        for (const column of state.columns) {
          const cell = state.cells.get(`${doc.id}:${column.id}`);
          if (cell && cell.confidence < 0.5) return true;
        }
        return false;
      });
    }

    return docs;
  },

  getSortedDocuments: () => {
    const state = get();
    const docs = get().getFilteredDocuments();

    if (!state.sortColumn) {
      return docs;
    }

    return [...docs].sort((a, b) => {
      const cellA = state.cells.get(`${a.id}:${state.sortColumn}`);
      const cellB = state.cells.get(`${b.id}:${state.sortColumn}`);

      const valueA = cellA?.value ?? '';
      const valueB = cellB?.value ?? '';

      let comparison = 0;
      if (typeof valueA === 'number' && typeof valueB === 'number') {
        comparison = valueA - valueB;
      } else {
        comparison = String(valueA).localeCompare(String(valueB));
      }

      return state.sortDirection === 'asc' ? comparison : -comparison;
    });
  },

  getVisibleColumns: () => {
    const state = get();
    return state.columnOrder
      .filter((id) => state.visibleColumns.has(id))
      .map((id) => state.columns.find((c) => c.id === id))
      .filter((c): c is DynamicColumn => c !== undefined);
  },
}));
