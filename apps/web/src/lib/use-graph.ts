/**
 * React Query hooks for Graph API
 *
 * Provides cached data fetching for the knowledge graph visualization.
 * Features:
 * - Automatic caching with stale-while-revalidate
 * - Optimistic updates for navigation
 * - Prefetching for neighbors
 * - Lazy loading support
 */

import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import apiClient from '@/lib/api-client';
import type {
    GraphNode,
    GraphLink,
    GraphData,
    EntityDetail,
    Remissao,
    GraphStats,
    GraphFilters,
} from '@/stores/graph-store';

// =============================================================================
// QUERY KEYS
// =============================================================================

export const graphKeys = {
    all: ['graph'] as const,
    data: (params: GraphDataParams) => [...graphKeys.all, 'data', params] as const,
    entity: (id: string) => [...graphKeys.all, 'entity', id] as const,
    remissoes: (id: string) => [...graphKeys.all, 'remissoes', id] as const,
    semanticNeighbors: (id: string, limit?: number) =>
        [...graphKeys.all, 'semantic-neighbors', id, limit] as const,
    stats: () => [...graphKeys.all, 'stats'] as const,
    path: (sourceId: string, targetId: string, maxLength?: number) =>
        [...graphKeys.all, 'path', sourceId, targetId, maxLength] as const,
    search: (query: string, types?: string, group?: string) =>
        [...graphKeys.all, 'search', query, types, group] as const,
    lexicalSearch: (
        terms: string[],
        devices: string[],
        authors: string[],
        matchMode: 'all' | 'any',
        types: string[],
        limit?: number
    ) => [...graphKeys.all, 'lexical-search', terms, devices, authors, matchMode, types, limit] as const,
    relationTypes: () => [...graphKeys.all, 'relation-types'] as const,
};

// =============================================================================
// TYPES
// =============================================================================

export interface GraphDataParams {
    types?: string;
    groups?: string;
    maxNodes?: number;
    includeRelationships?: boolean;
    entityIds?: string;
    documentIds?: string;
    caseIds?: string;
}

export interface PathNode {
    labels: string[];
    entity_id?: string;
    chunk_uid?: string;
    doc_hash?: string;
    name?: string;
    entity_type?: string;
    normalized?: string;
    chunk_index?: number;
    text_preview?: string;
}

export interface PathEdge {
    type: string;
    from_id: string;
    to_id: string;
    properties: Record<string, unknown>;
}

export interface PathResult {
    path: string[];
    path_ids: string[];
    relationships: string[];
    length: number;
    nodes?: PathNode[];
    edges?: PathEdge[];
}

export interface FindPathResponse {
    found: boolean;
    source?: string;
    target?: string;
    paths?: PathResult[];
    message?: string;
}

export interface SemanticNeighbor {
    id: string;
    name: string;
    type: string;
    group: string;
    normalized?: string;
    strength: number;
    relation: {
        type: string;
        label: string;
        description: string;
    };
    sample_contexts: string[];
    source_docs: string[];
}

export interface SemanticNeighborsResponse {
    entity_id: string;
    total: number;
    neighbors: SemanticNeighbor[];
}

// =============================================================================
// HOOKS
// =============================================================================

/**
 * Fetch graph data for visualization
 */
export function useGraphData(params: GraphDataParams, enabled = true) {
    return useQuery({
        queryKey: graphKeys.data(params),
        queryFn: async (): Promise<GraphData> => {
            const data = await apiClient.getGraphData({
                types: params.types,
                groups: params.groups,
                max_nodes: params.maxNodes,
                include_relationships: params.includeRelationships,
                entity_ids: params.entityIds,
                document_ids: params.documentIds,
                case_ids: params.caseIds,
            });
            return data;
        },
        enabled,
        staleTime: 1000 * 60 * 2, // 2 minutes
        gcTime: 1000 * 60 * 10, // 10 minutes
    });
}

/**
 * Fetch entity details with neighbors and chunks
 */
export function useGraphEntity(entityId: string | null, enabled = true) {
    const queryClient = useQueryClient();

    return useQuery({
        queryKey: graphKeys.entity(entityId ?? ''),
        queryFn: async (): Promise<EntityDetail> => {
            if (!entityId) throw new Error('Entity ID is required');
            const data = await apiClient.getGraphEntity(entityId);
            return data;
        },
        enabled: enabled && !!entityId,
        staleTime: 1000 * 60 * 5, // 5 minutes
        gcTime: 1000 * 60 * 15, // 15 minutes
    });
}

/**
 * Fetch remissoes (cross-references) for an entity
 */
export function useGraphRemissoes(entityId: string | null, enabled = true) {
    return useQuery({
        queryKey: graphKeys.remissoes(entityId ?? ''),
        queryFn: async () => {
            if (!entityId) throw new Error('Entity ID is required');
            const data = await apiClient.getGraphRemissoes(entityId);
            // Transform to Remissao array
            return [
                ...data.legislacao.map((r) => ({ ...r, group: 'legislacao' as const })),
                ...data.jurisprudencia.map((r) => ({ ...r, group: 'jurisprudencia' as const })),
            ];
        },
        enabled: enabled && !!entityId,
        staleTime: 1000 * 60 * 5,
        gcTime: 1000 * 60 * 15,
    });
}

/**
 * Fetch semantic neighbors for an entity (lazy loading)
 */
export function useSemanticNeighbors(
    entityId: string | null,
    limit = 30,
    enabled = true
) {
    return useQuery({
        queryKey: graphKeys.semanticNeighbors(entityId ?? '', limit),
        queryFn: async (): Promise<SemanticNeighborsResponse> => {
            if (!entityId) throw new Error('Entity ID is required');
            return await apiClient.getGraphSemanticNeighbors(entityId, limit);
        },
        enabled: enabled && !!entityId,
        staleTime: 1000 * 60 * 3, // 3 minutes
        gcTime: 1000 * 60 * 10,
    });
}

/**
 * Fetch graph statistics
 */
export function useGraphStats(enabled = true) {
    return useQuery({
        queryKey: graphKeys.stats(),
        queryFn: async (): Promise<GraphStats> => {
            return await apiClient.getGraphStats();
        },
        enabled,
        staleTime: 1000 * 60 * 5, // 5 minutes
        gcTime: 1000 * 60 * 30,
    });
}

/**
 * Find path between two entities
 */
export function useGraphPath(
    sourceId: string | null,
    targetId: string | null,
    maxLength = 4,
    enabled = true
) {
    return useQuery({
        queryKey: graphKeys.path(sourceId ?? '', targetId ?? '', maxLength),
        queryFn: async (): Promise<FindPathResponse> => {
            if (!sourceId || !targetId) throw new Error('Source and target IDs are required');
            return await apiClient.getGraphPath(sourceId, targetId, maxLength);
        },
        enabled: enabled && !!sourceId && !!targetId,
        staleTime: 1000 * 60 * 10, // 10 minutes (paths don't change often)
        gcTime: 1000 * 60 * 30,
    });
}

/**
 * Search entities in the graph
 */
export function useSearchEntities(
    query: string,
    types?: string,
    group?: string,
    limit = 50,
    enabled = true
) {
    return useQuery({
        queryKey: graphKeys.search(query, types, group),
        queryFn: async () => {
            return await apiClient.searchGraphEntities({
                query: query || undefined,
                types,
                group,
                limit,
            });
        },
        enabled: enabled && query.length >= 2, // Only search with 2+ chars
        staleTime: 1000 * 60 * 2,
        gcTime: 1000 * 60 * 10,
    });
}

/**
 * Server-side lexical search for entities (Neo4j)
 *
 * Used to seed graph export with entities that match the lexical filters.
 */
export function useGraphLexicalSearch(
    params: {
        terms: string[];
        devices: string[];
        authors: string[];
        matchMode: 'all' | 'any';
        types: string[];
        limit?: number;
    },
    enabled = true
) {
    return useQuery({
        queryKey: graphKeys.lexicalSearch(
            params.terms,
            params.devices,
            params.authors,
            params.matchMode,
            params.types,
            params.limit
        ),
        queryFn: async () => {
            return await apiClient.graphLexicalSearch({
                terms: params.terms,
                devices: params.devices,
                authors: params.authors,
                matchMode: params.matchMode,
                types: params.types,
                limit: params.limit,
            });
        },
        enabled,
        staleTime: 1000 * 30,
        gcTime: 1000 * 60 * 5,
    });
}

/**
 * Content search (OpenSearch BM25) -> entity_ids
 */
export function useGraphContentSearch(
    params: {
        query: string;
        types: string[];
        groups: string[];
        maxChunks?: number;
        maxEntities?: number;
        includeGlobal?: boolean;
        documentIds?: string[];
        caseIds?: string[];
    },
    enabled = true
) {
    return useQuery({
        queryKey: [...graphKeys.all, 'content-search', params] as const,
        queryFn: async () => {
            return await apiClient.graphContentSearch({
                query: params.query,
                types: params.types,
                groups: params.groups,
                maxChunks: params.maxChunks,
                maxEntities: params.maxEntities,
                includeGlobal: params.includeGlobal,
                documentIds: params.documentIds,
                caseIds: params.caseIds,
            });
        },
        enabled: enabled && params.query.trim().length >= 2,
        staleTime: 1000 * 30,
        gcTime: 1000 * 60 * 5,
    });
}

/**
 * Fetch available relation types
 */
export function useRelationTypes(enabled = true) {
    return useQuery({
        queryKey: graphKeys.relationTypes(),
        queryFn: async () => {
            return await apiClient.getGraphRelationTypes();
        },
        enabled,
        staleTime: 1000 * 60 * 60, // 1 hour (static data)
        gcTime: 1000 * 60 * 60 * 24, // 24 hours
    });
}

// =============================================================================
// PREFETCHING UTILITIES
// =============================================================================

/**
 * Prefetch entity data for hover preview
 */
export function usePrefetchEntity() {
    const queryClient = useQueryClient();

    return (entityId: string) => {
        queryClient.prefetchQuery({
            queryKey: graphKeys.entity(entityId),
            queryFn: () => apiClient.getGraphEntity(entityId),
            staleTime: 1000 * 60 * 5,
        });
    };
}

/**
 * Prefetch neighbors for expansion
 */
export function usePrefetchNeighbors() {
    const queryClient = useQueryClient();

    return (entityId: string) => {
        queryClient.prefetchQuery({
            queryKey: graphKeys.semanticNeighbors(entityId, 30),
            queryFn: () => apiClient.getGraphSemanticNeighbors(entityId, 30),
            staleTime: 1000 * 60 * 3,
        });
    };
}

// =============================================================================
// COMBINED HOOK FOR ENTITY SELECTION
// =============================================================================

/**
 * Combined hook for entity detail + remissoes (used when clicking a node)
 */
export function useEntityDetails(entityId: string | null) {
    const entityQuery = useGraphEntity(entityId);
    const remissoesQuery = useGraphRemissoes(entityId);
    const neighborsQuery = useSemanticNeighbors(entityId, 30, false); // Lazy - enable manually

    return {
        entity: entityQuery.data,
        remissoes: remissoesQuery.data,
        neighbors: neighborsQuery.data?.neighbors,
        isLoading: entityQuery.isLoading || remissoesQuery.isLoading,
        isLoadingNeighbors: neighborsQuery.isLoading,
        error: entityQuery.error || remissoesQuery.error,
        refetch: () => {
            entityQuery.refetch();
            remissoesQuery.refetch();
        },
        loadNeighbors: () => neighborsQuery.refetch(),
    };
}

// =============================================================================
// LEXICAL SEARCH IN GRAPH
// =============================================================================

export interface LexicalSearchParams {
    terms?: string[];
    devices?: string[];
    authors?: string[];
    matchMode?: 'any' | 'all';
    types?: string[];
    limit?: number;
}

/**
 * Lexical search for entities in the graph
 * Searches entities by terms, legal devices, and authors/tribunals
 */
export function useLexicalSearch(params: LexicalSearchParams, enabled = true) {
    const hasTerms = (params.terms?.length || 0) > 0 ||
                     (params.devices?.length || 0) > 0 ||
                     (params.authors?.length || 0) > 0;

    return useQuery({
        queryKey: ['graph', 'lexical-search', params],
        queryFn: async () => {
            return await apiClient.graphLexicalSearch(params);
        },
        enabled: enabled && hasTerms,
        staleTime: 1000 * 60 * 2, // 2 minutes
        gcTime: 1000 * 60 * 10,
    });
}

// =============================================================================
// ADD ENTITIES FROM RAG LOCAL
// =============================================================================

export interface AddFromRAGParams {
    documentIds?: string[];
    caseIds?: string[];
    extractSemantic?: boolean;
}

export interface AddFromRAGResult {
    documents_processed: number;
    chunks_processed: number;
    entities_extracted: number;
    entities_added: number;
    entities_existing: number;
    relationships_created: number;
    entities: Array<{
        entity_id: string;
        entity_type: string;
        name: string;
        normalized: string;
    }>;
}

/**
 * Mutation to add entities from RAG local documents to the graph
 */
export function useAddFromRAG() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (params: AddFromRAGParams): Promise<AddFromRAGResult> => {
            return await apiClient.graphAddFromRAG(params);
        },
        onSuccess: () => {
            // Invalidate graph data queries to refresh the visualization
            queryClient.invalidateQueries({ queryKey: graphKeys.all });
        },
    });
}
