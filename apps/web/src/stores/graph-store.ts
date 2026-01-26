import { create } from 'zustand';

// =============================================================================
// TYPES
// =============================================================================

export interface GraphNode {
    id: string;
    label: string;
    type: string;
    group: 'legislacao' | 'jurisprudencia' | 'doutrina' | 'outros';
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
    // Specific types within groups
    entityTypes: string[];
    // Search
    searchQuery: string;
    // Display options
    maxNodes: number;
    showRelationships: boolean;
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
    setZoomLevel: (zoom: number) => void;
    toggleGroup: (group: 'legislacao' | 'jurisprudencia' | 'doutrina') => void;
    resetFilters: () => void;
    clearSelection: () => void;
}

// =============================================================================
// DEFAULT VALUES
// =============================================================================

const defaultFilters: GraphFilters = {
    showLegislacao: true,
    showJurisprudencia: true,
    showDoutrina: true,
    entityTypes: ['lei', 'artigo', 'sumula', 'jurisprudencia', 'tema', 'tribunal'],
    searchQuery: '',
    maxNodes: 100,
    showRelationships: true,
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
        }

        return { filters };
    }),

    resetFilters: () => set({ filters: defaultFilters }),

    clearSelection: () => set({
        selectedNode: null,
        selectedEntity: null,
        remissoes: null
    }),
}));

// =============================================================================
// SELECTORS
// =============================================================================

export const selectFilteredNodes = (state: GraphState) => {
    if (!state.graphData) return [];

    const { showLegislacao, showJurisprudencia, showDoutrina, searchQuery } = state.filters;

    return state.graphData.nodes.filter(node => {
        // Filter by group
        if (node.group === 'legislacao' && !showLegislacao) return false;
        if (node.group === 'jurisprudencia' && !showJurisprudencia) return false;
        if (node.group === 'doutrina' && !showDoutrina) return false;

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
};

export const getNodeColor = (node: GraphNode): string => {
    return TYPE_COLORS[node.type] || GROUP_COLORS[node.group] || GROUP_COLORS.outros;
};
