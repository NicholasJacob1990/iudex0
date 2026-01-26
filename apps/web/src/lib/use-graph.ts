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
