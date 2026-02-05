'use client';

/**
 * React Query hooks for Corpus API
 *
 * Provides cached data fetching for the RAG knowledge base (Corpus).
 * Features:
 * - Automatic caching with stale-while-revalidate
 * - Optimistic updates for mutations
 * - Scoped queries (global, private, local)
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import apiClient from '@/lib/api-client';

// =============================================================================
// TYPES  (aligned with backend schemas in app/schemas/corpus.py)
// =============================================================================

export type CorpusScope = 'global' | 'private' | 'group' | 'local';
export type CorpusDocumentStatus = 'ingested' | 'pending' | 'processing' | 'failed';

/**
 * Maps to backend CorpusStats schema.
 */
export interface CorpusStats {
  total_documents: number;
  by_scope: Record<string, number>;
  by_collection: Record<string, number>;
  pending_ingestion: number;
  failed_ingestion: number;
  last_indexed_at: string | null;
  storage_size_mb: number | null;
}

/**
 * Maps to backend CorpusCollectionInfo schema.
 */
export interface CorpusCollectionInfo {
  name: string;
  display_name: string;
  description: string;
  document_count: number;
  chunk_count: number;
  scope: string;
  vector_count: number | null;
  status: string;
}

/**
 * Maps to backend CorpusDocument schema.
 */
export interface CorpusDocument {
  id: string;
  name: string;
  collection: string | null;
  scope: string | null;
  status: string;
  ingested_at: string | null;
  expires_at: string | null;
  chunk_count: number | null;
  file_type: string | null;
  size_bytes: number | null;
  jurisdiction?: string | null;
  source_id?: string | null;
}

export interface CorpusDocumentFilters {
  scope?: CorpusScope;
  group_id?: string;
  status?: CorpusDocumentStatus;
  collection?: string;
  search?: string;
  page?: number;
  per_page?: number;
}

/**
 * Maps to backend CorpusDocumentList schema.
 */
export interface CorpusDocumentsResponse {
  items: CorpusDocument[];
  total: number;
  page: number;
  per_page: number;
}

/**
 * Maps to backend CorpusIngestResponse schema.
 */
export interface CorpusIngestResponse {
  queued: number;
  skipped: number;
  errors: Array<Record<string, string>>;
}

/**
 * Payload for the ingest mutation (maps to CorpusIngestRequest on the backend).
 */
export interface IngestDocumentPayload {
  document_ids: string[];
  collection: string;
  scope: CorpusScope;
  jurisdiction?: string;
  source_id?: string;
  group_ids?: string[];
}

/**
 * Maps to backend CorpusPromoteResponse schema.
 */
export interface CorpusPromoteResponse {
  document_id: string;
  old_scope: string;
  new_scope: string;
  success: boolean;
  message: string;
}

/**
 * Maps to backend CorpusExtendTTLResponse schema.
 */
export interface CorpusExtendTTLResponse {
  document_id: string;
  new_expires_at: string | null;
  success: boolean;
  message: string;
}

// =============================================================================
// QUERY KEYS
// =============================================================================

// =============================================================================
// CORPUS PROJECT TYPES
// =============================================================================

export type ProjectScope = 'personal' | 'organization';

export interface CorpusProject {
  id: string;
  name: string;
  description: string | null;
  owner_id: string;
  organization_id: string | null;
  is_knowledge_base: boolean;
  scope: string;
  collection_name: string;
  max_documents: number;
  retention_days: number | null;
  document_count: number;
  chunk_count: number;
  storage_size_bytes: number;
  last_indexed_at: string | null;
  metadata: Record<string, any> | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CorpusProjectListResponse {
  items: CorpusProject[];
  total: number;
  page: number;
  per_page: number;
}

export interface CorpusProjectFilters {
  scope?: ProjectScope;
  is_knowledge_base?: boolean;
  search?: string;
  page?: number;
  per_page?: number;
}

export interface CreateCorpusProjectPayload {
  name: string;
  description?: string;
  is_knowledge_base?: boolean;
  scope?: string;
  max_documents?: number;
  retention_days?: number | null;
}

export interface UpdateCorpusProjectPayload {
  name?: string;
  description?: string;
  is_knowledge_base?: boolean;
  max_documents?: number;
  retention_days?: number | null;
}

// =============================================================================
// QUERY KEYS
// =============================================================================

// =============================================================================
// ADMIN TYPES (aligned with backend admin schemas)
// =============================================================================

export interface CorpusAdminUserStats {
  user_id: string;
  user_name: string;
  user_email: string;
  doc_count: number;
  storage_bytes: number;
  last_activity: string | null;
  collections_used: string[];
}

export interface CorpusAdminUserList {
  items: CorpusAdminUserStats[];
  total: number;
  skip: number;
  limit: number;
}

export interface CorpusAdminOverview {
  total_documents: number;
  total_storage_bytes: number;
  active_users: number;
  pending_ingestion: number;
  processing_ingestion: number;
  failed_ingestion: number;
  by_collection: Record<string, number>;
  by_scope: Record<string, number>;
  top_contributors: CorpusAdminUserStats[];
  recent_activity: Array<Record<string, any>>;
}

export interface CorpusAdminActivity {
  document_id: string;
  document_name: string;
  user_id: string;
  user_name: string;
  action: string;
  timestamp: string | null;
  details: Record<string, any> | null;
}

export interface CorpusAdminActivityList {
  items: CorpusAdminActivity[];
  total: number;
  skip: number;
  limit: number;
}

export interface CorpusTransferResponse {
  document_id: string;
  old_owner_id: string;
  new_owner_id: string;
  success: boolean;
  message: string;
}

// =============================================================================
// FOLDER TYPES
// =============================================================================

export interface FolderNode {
  name: string;
  path: string;
  document_count: number;
  children: FolderNode[];
}

export interface FolderTreeResponse {
  project_id: string;
  folders: FolderNode[];
  total_folders: number;
}

export interface ProjectDocumentResponse {
  id: string;
  project_id: string;
  document_id: string;
  document_name: string | null;
  folder_path: string | null;
  status: string;
  ingested_at: string | null;
  error_message: string | null;
  created_at: string;
}

export const corpusKeys = {
  all: ['corpus'] as const,
  stats: () => [...corpusKeys.all, 'stats'] as const,
  collections: () => [...corpusKeys.all, 'collections'] as const,
  documents: (filters: CorpusDocumentFilters) => [...corpusKeys.all, 'documents', filters] as const,
  document: (id: string) => [...corpusKeys.all, 'document', id] as const,
  projects: (filters?: CorpusProjectFilters) => [...corpusKeys.all, 'projects', filters] as const,
  project: (id: string) => [...corpusKeys.all, 'project', id] as const,
  projectFolders: (projectId: string) => [...corpusKeys.all, 'project', projectId, 'folders'] as const,
  projectDocuments: (projectId: string, params?: Record<string, any>) => [...corpusKeys.all, 'project', projectId, 'documents', params] as const,
  adminOverview: () => [...corpusKeys.all, 'admin', 'overview'] as const,
  adminUsers: (params?: { skip?: number; limit?: number }) => [...corpusKeys.all, 'admin', 'users', params] as const,
  adminUserDocuments: (userId: string, params?: Record<string, any>) => [...corpusKeys.all, 'admin', 'users', userId, 'documents', params] as const,
  adminActivity: (params?: Record<string, any>) => [...corpusKeys.all, 'admin', 'activity', params] as const,
};

// =============================================================================
// HOOKS
// =============================================================================

/**
 * Fetch corpus statistics (global overview)
 * Backend endpoint: GET /api/corpus/stats
 */
export function useCorpusStats() {
  return useQuery({
    queryKey: corpusKeys.stats(),
    queryFn: async (): Promise<CorpusStats> => {
      return await apiClient.getCorpusStats();
    },
    staleTime: 1000 * 60 * 2, // 2 minutos
    gcTime: 1000 * 60 * 10, // 10 minutos
  });
}

/**
 * Fetch corpus collections
 * Backend endpoint: GET /api/corpus/collections
 */
export function useCorpusCollections() {
  return useQuery({
    queryKey: corpusKeys.collections(),
    queryFn: async (): Promise<CorpusCollectionInfo[]> => {
      return await apiClient.getCorpusCollections();
    },
    staleTime: 1000 * 60 * 5, // 5 minutos
    gcTime: 1000 * 60 * 15, // 15 minutos
  });
}

/**
 * Fetch corpus documents with filters and pagination
 * Backend endpoint: GET /api/corpus/documents?scope=X&collection=X&status=X&page=X&per_page=X
 */
export function useCorpusDocuments(filters: CorpusDocumentFilters = {}) {
  return useQuery({
    queryKey: corpusKeys.documents(filters),
    queryFn: async (): Promise<CorpusDocumentsResponse> => {
      return await apiClient.getCorpusDocuments({
        scope: filters.scope,
        group_id: filters.group_id,
        collection: filters.collection,
        status: filters.status,
        search: filters.search,
        page: filters.page,
        per_page: filters.per_page,
      });
    },
    staleTime: 1000 * 60 * 1, // 1 minuto
    gcTime: 1000 * 60 * 5, // 5 minutos
  });
}

/**
 * Ingest documents into the corpus
 * Backend endpoint: POST /api/corpus/ingest  body: {document_ids, collection, scope}
 */
export function useIngestDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: IngestDocumentPayload): Promise<CorpusIngestResponse> => {
      return await apiClient.ingestCorpusDocuments({
        document_ids: payload.document_ids,
        collection: payload.collection,
        scope: payload.scope,
        jurisdiction: payload.jurisdiction,
        source_id: payload.source_id,
        group_ids: payload.group_ids,
      });
    },
    onSuccess: () => {
      toast.success('Documentos enviados para ingestão');
      queryClient.invalidateQueries({ queryKey: corpusKeys.all });
    },
    onError: () => {
      toast.error('Erro ao ingerir documentos');
    },
  });
}

/**
 * Delete a document from the corpus
 * Backend endpoint: DELETE /api/corpus/documents/{id}
 */
export function useDeleteCorpusDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (documentId: string): Promise<void> => {
      await apiClient.deleteCorpusDocument(documentId);
    },
    onSuccess: () => {
      toast.success('Documento removido');
      queryClient.invalidateQueries({ queryKey: corpusKeys.all });
    },
    onError: () => {
      toast.error('Erro ao remover documento');
    },
  });
}

/**
 * Promote a local document to private scope
 * Backend endpoint: POST /api/corpus/documents/{id}/promote
 */
export function usePromoteDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (documentId: string): Promise<CorpusPromoteResponse> => {
      return await apiClient.promoteCorpusDocument(documentId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: corpusKeys.all });
    },
  });
}

/**
 * Extend TTL of a local document
 * Backend endpoint: POST /api/corpus/documents/{id}/extend-ttl  body: {days}
 */
export function useExtendDocumentTTL() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ documentId, days }: { documentId: string; days: number }): Promise<CorpusExtendTTLResponse> => {
      return await apiClient.extendCorpusDocumentTTL(documentId, days);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: corpusKeys.all });
    },
  });
}

// =============================================================================
// CORPUS PROJECT HOOKS
// =============================================================================

/**
 * Fetch corpus projects with filters and pagination
 * Backend endpoint: GET /api/corpus/projects
 */
export function useCorpusProjects(filters: CorpusProjectFilters = {}) {
  return useQuery({
    queryKey: corpusKeys.projects(filters),
    queryFn: async (): Promise<CorpusProjectListResponse> => {
      return await apiClient.getCorpusProjects({
        scope: filters.scope,
        is_knowledge_base: filters.is_knowledge_base,
        search: filters.search,
        page: filters.page,
        per_page: filters.per_page,
      });
    },
    staleTime: 1000 * 60 * 1,
    gcTime: 1000 * 60 * 5,
  });
}

/**
 * Fetch a single corpus project
 * Backend endpoint: GET /api/corpus/projects/{id}
 */
export function useCorpusProject(projectId: string) {
  return useQuery({
    queryKey: corpusKeys.project(projectId),
    queryFn: async (): Promise<CorpusProject> => {
      return await apiClient.getCorpusProject(projectId);
    },
    enabled: !!projectId,
    staleTime: 1000 * 60 * 1,
    gcTime: 1000 * 60 * 5,
  });
}

/**
 * Create a new corpus project
 * Backend endpoint: POST /api/corpus/projects
 */
export function useCreateCorpusProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: CreateCorpusProjectPayload): Promise<CorpusProject> => {
      return await apiClient.createCorpusProject(payload);
    },
    onSuccess: () => {
      toast.success('Projeto criado com sucesso');
      queryClient.invalidateQueries({ queryKey: corpusKeys.all });
    },
    onError: () => {
      toast.error('Erro ao criar projeto');
    },
  });
}

/**
 * Update a corpus project
 * Backend endpoint: PUT /api/corpus/projects/{id}
 */
export function useUpdateCorpusProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      projectId,
      data,
    }: {
      projectId: string;
      data: UpdateCorpusProjectPayload;
    }): Promise<CorpusProject> => {
      return await apiClient.updateCorpusProject(projectId, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: corpusKeys.all });
    },
  });
}

/**
 * Delete a corpus project
 * Backend endpoint: DELETE /api/corpus/projects/{id}
 */
export function useDeleteCorpusProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (projectId: string): Promise<void> => {
      await apiClient.deleteCorpusProject(projectId);
    },
    onSuccess: () => {
      toast.success('Projeto excluído');
      queryClient.invalidateQueries({ queryKey: corpusKeys.all });
    },
    onError: () => {
      toast.error('Erro ao excluir projeto');
    },
  });
}

/**
 * Add documents to a corpus project
 * Backend endpoint: POST /api/corpus/projects/{id}/documents
 */
export function useAddDocumentsToProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      projectId,
      documentIds,
    }: {
      projectId: string;
      documentIds: string[];
    }): Promise<{ added: number; skipped: number; errors: Array<Record<string, string>> }> => {
      return await apiClient.addDocumentsToCorpusProject(projectId, documentIds);
    },
    onSuccess: () => {
      toast.success('Documentos adicionados ao projeto');
      queryClient.invalidateQueries({ queryKey: corpusKeys.all });
    },
    onError: () => {
      toast.error('Erro ao adicionar documentos');
    },
  });
}

/**
 * Remove document from a corpus project
 * Backend endpoint: DELETE /api/corpus/projects/{id}/documents/{doc_id}
 */
export function useRemoveDocumentFromProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      projectId,
      documentId,
    }: {
      projectId: string;
      documentId: string;
    }): Promise<void> => {
      await apiClient.removeDocumentFromCorpusProject(projectId, documentId);
    },
    onSuccess: () => {
      toast.success('Documento removido do projeto');
      queryClient.invalidateQueries({ queryKey: corpusKeys.all });
    },
    onError: () => {
      toast.error('Erro ao remover documento');
    },
  });
}

// =============================================================================
// ADMIN HOOKS
// =============================================================================

/**
 * Visao geral administrativa do Corpus
 * Backend endpoint: GET /api/corpus/admin/overview
 */
export function useCorpusAdminOverview() {
  return useQuery({
    queryKey: corpusKeys.adminOverview(),
    queryFn: async (): Promise<CorpusAdminOverview> => {
      return await apiClient.getCorpusAdminOverview();
    },
    staleTime: 1000 * 60 * 2,
    gcTime: 1000 * 60 * 10,
  });
}

/**
 * Lista usuarios da org com stats do Corpus
 * Backend endpoint: GET /api/corpus/admin/users
 */
export function useCorpusAdminUsers(params?: { skip?: number; limit?: number }) {
  return useQuery({
    queryKey: corpusKeys.adminUsers(params),
    queryFn: async (): Promise<CorpusAdminUserList> => {
      return await apiClient.getCorpusAdminUsers(params);
    },
    staleTime: 1000 * 60 * 2,
    gcTime: 1000 * 60 * 10,
  });
}

/**
 * Lista documentos de um usuario especifico (visao admin)
 * Backend endpoint: GET /api/corpus/admin/users/{userId}/documents
 */
export function useCorpusAdminUserDocuments(
  userId: string,
  params?: { scope?: string; collection?: string; status?: string; skip?: number; limit?: number }
) {
  return useQuery({
    queryKey: corpusKeys.adminUserDocuments(userId, params),
    queryFn: async (): Promise<CorpusDocumentsResponse> => {
      return await apiClient.getCorpusAdminUserDocuments(userId, params);
    },
    enabled: !!userId,
    staleTime: 1000 * 60 * 1,
    gcTime: 1000 * 60 * 5,
  });
}

/**
 * Log de atividades do Corpus
 * Backend endpoint: GET /api/corpus/admin/activity
 */
export function useCorpusAdminActivity(params?: {
  skip?: number;
  limit?: number;
  user_id?: string;
  action?: string;
}) {
  return useQuery({
    queryKey: corpusKeys.adminActivity(params),
    queryFn: async (): Promise<CorpusAdminActivityList> => {
      return await apiClient.getCorpusAdminActivity(params);
    },
    staleTime: 1000 * 60 * 1,
    gcTime: 1000 * 60 * 5,
  });
}

/**
 * Transferir propriedade de documento
 * Backend endpoint: POST /api/corpus/admin/transfer/{documentId}
 */
export function useTransferDocumentOwnership() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      documentId,
      newOwnerId,
    }: {
      documentId: string;
      newOwnerId: string;
    }): Promise<CorpusTransferResponse> => {
      return await apiClient.transferCorpusDocument(documentId, newOwnerId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: corpusKeys.all });
    },
  });
}

// =============================================================================
// FOLDER HOOKS
// =============================================================================

/**
 * Fetch folder tree for a project
 * Backend endpoint: GET /api/corpus/projects/{id}/folders
 */
export function useProjectFolders(projectId: string) {
  return useQuery({
    queryKey: corpusKeys.projectFolders(projectId),
    queryFn: async (): Promise<FolderTreeResponse> => {
      return await apiClient.getCorpusProjectFolders(projectId);
    },
    enabled: !!projectId,
    staleTime: 1000 * 30,
    gcTime: 1000 * 60 * 5,
  });
}

/**
 * List documents in a project with folder filter
 * Backend endpoint: GET /api/corpus/projects/{id}/documents?folder=...
 */
export function useProjectDocuments(
  projectId: string,
  params?: { folder?: string; status?: string; sort?: string; page?: number; per_page?: number }
) {
  return useQuery({
    queryKey: corpusKeys.projectDocuments(projectId, params),
    queryFn: async (): Promise<ProjectDocumentResponse[]> => {
      return await apiClient.getCorpusProjectDocuments(projectId, params);
    },
    enabled: !!projectId,
    staleTime: 1000 * 30,
    gcTime: 1000 * 60 * 5,
  });
}

/**
 * Create a folder in a project
 * Backend endpoint: POST /api/corpus/projects/{id}/folders
 */
export function useCreateProjectFolder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      projectId,
      folderPath,
    }: {
      projectId: string;
      folderPath: string;
    }): Promise<any> => {
      return await apiClient.createCorpusProjectFolder(projectId, folderPath);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: corpusKeys.all });
    },
  });
}

// =============================================================================
// DUPLICATE DETECTION TYPES & HOOK
// =============================================================================

export interface DuplicatePair {
  document_id_1: string;
  document_name_1: string;
  document_id_2: string;
  document_name_2: string;
  similarity: number;
  match_type: string;
}

export interface DuplicatesResponse {
  project_id: string;
  duplicates: DuplicatePair[];
  total_checked: number;
  threshold: number;
}

/**
 * Check for duplicate documents in a corpus project
 * Backend endpoint: GET /api/corpus/projects/{id}/duplicates
 */
export function useCheckDuplicates() {
  return useMutation({
    mutationFn: async ({
      projectId,
      threshold,
    }: {
      projectId: string;
      threshold?: number;
    }): Promise<DuplicatesResponse> => {
      const params = threshold ? `?threshold=${threshold}` : '';
      return await apiClient.request(`/corpus/projects/${projectId}/duplicates${params}`);
    },
  });
}

/**
 * Move a document between folders
 * Backend endpoint: PATCH /api/corpus/projects/{id}/documents/{docId}/move
 */
export function useMoveProjectDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      projectId,
      documentId,
      folderPath,
    }: {
      projectId: string;
      documentId: string;
      folderPath: string | null;
    }): Promise<any> => {
      return await apiClient.moveCorpusProjectDocument(projectId, documentId, folderPath);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: corpusKeys.all });
    },
  });
}
