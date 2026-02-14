import { create } from 'zustand';

// =============================================================================
// TYPES
// =============================================================================

export interface GraphNode {
    id: string;
    label: string;
    type: string;
    group: 'legislacao' | 'jurisprudencia' | 'doutrina' | 'fatos' | 'outros';
    metadata?: Record<string, unknown>;
    size?: number;
    // For force-graph
    x?: number;
    y?: number;
    fx?: number | null;
    fy?: number | null;
}

export interface GraphLink {
    source: string | GraphNode;
    target: string | GraphNode;
    type: string;
    label?: string;  // Human-readable label
    description?: string;  // Explanation of the relationship
    weight?: number;
    semantic?: boolean;  // Is this a semantic/inferred relation?
}

// Semantic relation types
export const RELATION_LABELS: Record<string, { label: string; description: string }> = {
    co_occurrence: {
        label: 'Aparece junto com',
        description: 'Entidades mencionadas no mesmo trecho de documento',
    },
    related: {
        label: 'Relacionado semanticamente',
        description: 'Conexão semântica inferida pelo contexto',
    },
    mentions: {
        label: 'Menciona',
        description: 'Documento ou trecho que referencia a entidade',
    },
    cita: {
        label: 'Cita',
        description: 'Citação explícita de dispositivo legal',
    },
    fundamenta: {
        label: 'Fundamenta',
        description: 'Serve como fundamento jurídico',
    },
    interpreta: {
        label: 'Interpreta',
        description: 'Oferece interpretação do dispositivo',
    },
    aplica: {
        label: 'Aplica',
        description: 'Aplicação prática do dispositivo',
    },
    complementa: {
        label: 'Complementa',
        description: 'Complementa ou detalha outro dispositivo',
    },
    fact_refers_to: {
        label: 'Relacionado ao fato',
        description: 'Fato extraído do documento que referencia/conecta a entidade',
    },
};

export interface GraphData {
    nodes: GraphNode[];
    links: GraphLink[];
}

export interface EntityDetail {
    id: string;
    name: string;
    type: string;
    normalized: string;
    metadata: Record<string, unknown>;
    neighbors: Array<{
        id: string;
        name: string;
        type: string;
        relationship: string;
        weight: number;
    }>;
    chunks: Array<{
        chunk_uid: string;
        text: string;
        doc_title: string;
        source_type: string;
    }>;
}

export interface Remissao {
    id: string;
    name: string;
    type: string;
    group: string;
    co_occurrences: number;
    sample_text?: string;
    // Transparency-first hybrid
    verified?: boolean;
    relationship_type?: string; // REMETE_A | CO_MENCIONA | co_occurrence | ...
    layer?: string; // verified | candidate
    dimension?: string; // hierarquica | horizontal | remissiva
    evidence?: string;
}

export interface GraphStats {
    total_entities: number;
    total_chunks: number;
    total_documents: number;
    entities_by_type: Record<string, number>;
    relationships_count: number;
}

// =============================================================================
// FILTERS
// =============================================================================

export interface GraphFilters {
    // Entity type checkboxes
    showLegislacao: boolean;
    showJurisprudencia: boolean;
    showDoutrina: boolean;
    showFatos: boolean;
    // Specific types within groups
    entityTypes: string[];
    // Search
    searchQuery: string;
    // Display options
    maxNodes: number;
    showRelationships: boolean;
    includeGlobal: boolean;

    // Material selection (documents, cases, library)
    selectedDocuments: string[];
    selectedCases: string[];
    filterByMaterials: boolean;

    // Lexical search (tags)
    lexicalTerms: string[];
    lexicalAuthors: string[];
    lexicalDevices: string[];
    lexicalMatchMode: 'all' | 'any';
    lexicalSearchMode: 'entities' | 'content';
}

// =============================================================================
// STORE STATE
// =============================================================================

interface GraphState {
    // Data
    graphData: GraphData | null;
    selectedNode: GraphNode | null;
    selectedEntity: EntityDetail | null;
    remissoes: Remissao[] | null;
    stats: GraphStats | null;

    // UI State
    isLoading: boolean;
    isLoadingDetail: boolean;
    error: string | null;

    // Filters
    filters: GraphFilters;

    // Zoom/Pan
    zoomLevel: number;

    // Actions
    setGraphData: (data: GraphData | null) => void;
    setSelectedNode: (node: GraphNode | null) => void;
    setSelectedEntity: (entity: EntityDetail | null) => void;
    setRemissoes: (remissoes: Remissao[] | null) => void;
    setStats: (stats: GraphStats | null) => void;
    setLoading: (loading: boolean) => void;
    setLoadingDetail: (loading: boolean) => void;
    setError: (error: string | null) => void;
    setFilters: (filters: Partial<GraphFilters>) => void;
    setIncludeGlobal: (includeGlobal: boolean) => void;
    setZoomLevel: (zoom: number) => void;
    toggleGroup: (group: 'legislacao' | 'jurisprudencia' | 'doutrina' | 'fatos') => void;
    resetFilters: () => void;
    clearSelection: () => void;

    // Material selection actions
    setSelectedDocuments: (docs: string[]) => void;
    setSelectedCases: (cases: string[]) => void;
    toggleFilterByMaterials: () => void;
    addDocument: (docId: string) => void;
    removeDocument: (docId: string) => void;
    addCase: (caseId: string) => void;
    removeCase: (caseId: string) => void;

    // Lexical search actions
    setLexicalTerms: (terms: string[]) => void;
    setLexicalAuthors: (authors: string[]) => void;
    setLexicalDevices: (devices: string[]) => void;
    setLexicalMatchMode: (mode: 'all' | 'any') => void;
    addLexicalTerm: (term: string) => void;
    removeLexicalTerm: (term: string) => void;
    addLexicalAuthor: (author: string) => void;
    removeLexicalAuthor: (author: string) => void;
    addLexicalDevice: (device: string) => void;
    removeLexicalDevice: (device: string) => void;
    clearLexicalFilters: () => void;
    setLexicalSearchMode: (mode: 'entities' | 'content') => void;
}

// =============================================================================
// DEFAULT VALUES
// =============================================================================

const defaultFilters: GraphFilters = {
    showLegislacao: true,
    showJurisprudencia: true,
    showDoutrina: true,
    showFatos: false,
    entityTypes: ['lei', 'artigo', 'sumula', 'jurisprudencia', 'tema', 'tribunal'],
    searchQuery: '',
    maxNodes: 100,
    showRelationships: true,
    includeGlobal: true,
    // Material selection
    selectedDocuments: [],
    selectedCases: [],
    filterByMaterials: false,
    // Lexical search
    lexicalTerms: [],
    lexicalAuthors: [],
    lexicalDevices: [],
    lexicalMatchMode: 'any',
    lexicalSearchMode: 'entities',
};

// =============================================================================
// STORE
// =============================================================================

export const useGraphStore = create<GraphState>((set, get) => ({
    // Initial state
    graphData: null,
    selectedNode: null,
    selectedEntity: null,
    remissoes: null,
    stats: null,
    isLoading: false,
    isLoadingDetail: false,
    error: null,
    filters: defaultFilters,
    zoomLevel: 1,

    // Actions
    setGraphData: (data) => set({ graphData: data }),

    setSelectedNode: (node) => set({ selectedNode: node }),

    setSelectedEntity: (entity) => set({ selectedEntity: entity }),

    setRemissoes: (remissoes) => set({ remissoes }),

    setStats: (stats) => set({ stats }),

    setLoading: (loading) => set({ isLoading: loading }),

    setLoadingDetail: (loading) => set({ isLoadingDetail: loading }),

    setError: (error) => set({ error }),

    setFilters: (newFilters) => set((state) => ({
        filters: { ...state.filters, ...newFilters }
    })),

    setIncludeGlobal: (includeGlobal) => set((state) => ({
        filters: { ...state.filters, includeGlobal }
    })),

    setZoomLevel: (zoom) => set({ zoomLevel: zoom }),

    toggleGroup: (group) => set((state) => {
        const filters = { ...state.filters };

        switch (group) {
            case 'legislacao':
                filters.showLegislacao = !filters.showLegislacao;
                if (filters.showLegislacao) {
                    filters.entityTypes = [...new Set([...filters.entityTypes, 'lei', 'artigo'])];
                } else {
                    filters.entityTypes = filters.entityTypes.filter(t => !['lei', 'artigo'].includes(t));
                }
                break;
            case 'jurisprudencia':
                filters.showJurisprudencia = !filters.showJurisprudencia;
                if (filters.showJurisprudencia) {
                    filters.entityTypes = [...new Set([...filters.entityTypes, 'sumula', 'jurisprudencia', 'tema', 'tribunal'])];
                } else {
                    filters.entityTypes = filters.entityTypes.filter(t => !['sumula', 'jurisprudencia', 'tema', 'tribunal'].includes(t));
                }
                break;
            case 'doutrina':
                filters.showDoutrina = !filters.showDoutrina;
                if (filters.showDoutrina) {
                    filters.entityTypes = [...new Set([...filters.entityTypes, 'tese', 'conceito'])];
                } else {
                    filters.entityTypes = filters.entityTypes.filter(t => !['tese', 'conceito'].includes(t));
                }
                break;
            case 'fatos':
                filters.showFatos = !filters.showFatos;
                break;
        }

        return { filters };
    }),

    resetFilters: () => set({ filters: defaultFilters }),

    clearSelection: () => set({
        selectedNode: null,
        selectedEntity: null,
        remissoes: null
    }),

    // Material selection actions
    setSelectedDocuments: (docs) => set((state) => ({
        filters: { ...state.filters, selectedDocuments: docs }
    })),

    setSelectedCases: (cases) => set((state) => ({
        filters: { ...state.filters, selectedCases: cases }
    })),

    toggleFilterByMaterials: () => set((state) => ({
        filters: { ...state.filters, filterByMaterials: !state.filters.filterByMaterials }
    })),

    addDocument: (docId) => set((state) => ({
        filters: {
            ...state.filters,
            selectedDocuments: state.filters.selectedDocuments.includes(docId)
                ? state.filters.selectedDocuments
                : [...state.filters.selectedDocuments, docId]
        }
    })),

    removeDocument: (docId) => set((state) => ({
        filters: {
            ...state.filters,
            selectedDocuments: state.filters.selectedDocuments.filter(id => id !== docId)
        }
    })),

    addCase: (caseId) => set((state) => ({
        filters: {
            ...state.filters,
            selectedCases: state.filters.selectedCases.includes(caseId)
                ? state.filters.selectedCases
                : [...state.filters.selectedCases, caseId]
        }
    })),

    removeCase: (caseId) => set((state) => ({
        filters: {
            ...state.filters,
            selectedCases: state.filters.selectedCases.filter(id => id !== caseId)
        }
    })),

    // Lexical search actions
    setLexicalTerms: (terms) => set((state) => ({
        filters: { ...state.filters, lexicalTerms: terms }
    })),

    setLexicalAuthors: (authors) => set((state) => ({
        filters: { ...state.filters, lexicalAuthors: authors }
    })),

    setLexicalDevices: (devices) => set((state) => ({
        filters: { ...state.filters, lexicalDevices: devices }
    })),

    setLexicalMatchMode: (mode) => set((state) => ({
        filters: { ...state.filters, lexicalMatchMode: mode }
    })),

    addLexicalTerm: (term) => set((state) => ({
        filters: {
            ...state.filters,
            lexicalTerms: state.filters.lexicalTerms.includes(term)
                ? state.filters.lexicalTerms
                : [...state.filters.lexicalTerms, term]
        }
    })),

    removeLexicalTerm: (term) => set((state) => ({
        filters: {
            ...state.filters,
            lexicalTerms: state.filters.lexicalTerms.filter(t => t !== term)
        }
    })),

    addLexicalAuthor: (author) => set((state) => ({
        filters: {
            ...state.filters,
            lexicalAuthors: state.filters.lexicalAuthors.includes(author)
                ? state.filters.lexicalAuthors
                : [...state.filters.lexicalAuthors, author]
        }
    })),

    removeLexicalAuthor: (author) => set((state) => ({
        filters: {
            ...state.filters,
            lexicalAuthors: state.filters.lexicalAuthors.filter(a => a !== author)
        }
    })),

    addLexicalDevice: (device) => set((state) => ({
        filters: {
            ...state.filters,
            lexicalDevices: state.filters.lexicalDevices.includes(device)
                ? state.filters.lexicalDevices
                : [...state.filters.lexicalDevices, device]
        }
    })),

    removeLexicalDevice: (device) => set((state) => ({
        filters: {
            ...state.filters,
            lexicalDevices: state.filters.lexicalDevices.filter(d => d !== device)
        }
    })),

    clearLexicalFilters: () => set((state) => ({
        filters: {
            ...state.filters,
            lexicalTerms: [],
            lexicalAuthors: [],
            lexicalDevices: []
        }
    })),

    setLexicalSearchMode: (mode) => set((state) => ({
        filters: { ...state.filters, lexicalSearchMode: mode }
    })),
}));

// =============================================================================
// SELECTORS
// =============================================================================

export const selectFilteredNodes = (state: GraphState) => {
    if (!state.graphData) return [];

    const {
        showLegislacao,
        showJurisprudencia,
        showDoutrina,
        showFatos,
        searchQuery
    } = state.filters;

    return state.graphData.nodes.filter(node => {
        // Filter by group
        if (node.group === 'legislacao' && !showLegislacao) return false;
        if (node.group === 'jurisprudencia' && !showJurisprudencia) return false;
        if (node.group === 'doutrina' && !showDoutrina) return false;
        if (node.group === 'fatos' && !showFatos) return false;

        // Filter by search
        if (searchQuery && !node.label.toLowerCase().includes(searchQuery.toLowerCase())) {
            return false;
        }

        return true;
    });
};

export const selectFilteredLinks = (state: GraphState) => {
    if (!state.graphData || !state.filters.showRelationships) return [];

    const filteredNodeIds = new Set(selectFilteredNodes(state).map(n => n.id));

    return state.graphData.links.filter(link => {
        const sourceId = typeof link.source === 'string' ? link.source : link.source.id;
        const targetId = typeof link.target === 'string' ? link.target : link.target.id;

        return filteredNodeIds.has(sourceId) && filteredNodeIds.has(targetId);
    });
};

// =============================================================================
// COLOR SCHEME
// =============================================================================

export const GROUP_COLORS = {
    legislacao: '#3b82f6',      // blue-500
    jurisprudencia: '#10b981',  // emerald-500
    doutrina: '#8b5cf6',        // violet-500
    fatos: '#f97316',           // orange-500
    outros: '#6b7280',          // gray-500
} as const;

export const TYPE_COLORS: Record<string, string> = {
    lei: '#2563eb',             // blue-600
    artigo: '#60a5fa',          // blue-400
    sumula: '#059669',          // emerald-600
    jurisprudencia: '#34d399',  // emerald-400
    tema: '#047857',            // emerald-700
    tribunal: '#6ee7b7',        // emerald-300
    tese: '#7c3aed',            // violet-600
    conceito: '#a78bfa',        // violet-400
    processo: '#9ca3af',        // gray-400
    parte: '#d1d5db',           // gray-300
    oab: '#e5e7eb',             // gray-200
    fato: '#f97316',            // orange-500
};

export const getNodeColor = (node: GraphNode): string => {
    return TYPE_COLORS[node.type] || GROUP_COLORS[node.group] || GROUP_COLORS.outros;
};
