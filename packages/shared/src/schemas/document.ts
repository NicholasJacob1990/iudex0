/**
 * Zod Schema for Document API Responses
 * 
 * Transforms snake_case API responses to camelCase TypeScript interfaces.
 * Also converts date strings to Date objects.
 */

import { z } from 'zod';
import type { Document, DocumentMetadata, DocumentType, DocumentStatus, DocumentCategory } from '../types/document';

// Schema for API response (snake_case)
const ApiDocumentMetadataSchema = z.object({
    pages: z.number().optional(),
    language: z.string().optional(),
    author: z.string().optional(),
    created_date: z.string().optional(),
    modified_date: z.string().optional(),
    file_hash: z.string().optional(),
    ocr_applied: z.boolean().optional(),
    process_number: z.string().optional(),
    court: z.string().optional(),
    parties: z.object({
        plaintiff: z.array(z.string()).optional(),
        defendant: z.array(z.string()).optional(),
    }).optional(),
    cnj_metadata: z.object({
        process_number: z.string(),
        tribunal: z.string(),
        classe: z.string(),
        assunto: z.string(),
        vara: z.string(),
        comarca: z.string(),
        distribuicao: z.string(),
        valor_causa: z.number().optional(),
    }).optional(),
    custom_fields: z.record(z.any()).optional(),
}).passthrough();

const ApiDocumentSchema = z.object({
    id: z.string(),
    user_id: z.string(),
    name: z.string(),
    original_name: z.string().optional(),
    type: z.string(),
    category: z.string().optional().nullable(),
    status: z.string(),
    size: z.number(),
    url: z.string(),
    thumbnail_url: z.string().optional().nullable(),
    content: z.string().optional(),
    extracted_text: z.string().optional(),
    metadata: ApiDocumentMetadataSchema.optional().default({}),
    tags: z.array(z.string()).default([]),
    folder_id: z.string().optional().nullable(),
    is_shared: z.boolean().default(false),
    is_archived: z.boolean().default(false),
    created_at: z.string(),
    updated_at: z.string(),
}).passthrough();

/**
 * Transforms API document response to frontend Document type
 */
export const DocumentSchema = ApiDocumentSchema.transform((data): Document => ({
    id: data.id,
    userId: data.user_id,
    name: data.name,
    originalName: data.original_name ?? data.name,
    type: data.type as DocumentType,
    category: data.category as DocumentCategory | undefined,
    status: data.status as DocumentStatus,
    size: data.size,
    url: data.url,
    thumbnailUrl: data.thumbnail_url ?? undefined,
    content: data.content,
    extractedText: data.extracted_text,
    metadata: transformMetadata(data.metadata),
    tags: data.tags,
    folderId: data.folder_id ?? undefined,
    isShared: data.is_shared,
    isArchived: data.is_archived,
    createdAt: new Date(data.created_at),
    updatedAt: new Date(data.updated_at),
}));

function transformMetadata(meta: z.infer<typeof ApiDocumentMetadataSchema>): DocumentMetadata {
    return {
        pages: meta.pages,
        language: meta.language,
        author: meta.author,
        createdDate: meta.created_date,
        modifiedDate: meta.modified_date,
        fileHash: meta.file_hash,
        ocrApplied: meta.ocr_applied,
        processNumber: meta.process_number,
        court: meta.court,
        parties: meta.parties,
        cnjMetadata: meta.cnj_metadata ? {
            processNumber: meta.cnj_metadata.process_number,
            tribunal: meta.cnj_metadata.tribunal,
            classe: meta.cnj_metadata.classe,
            assunto: meta.cnj_metadata.assunto,
            vara: meta.cnj_metadata.vara,
            comarca: meta.cnj_metadata.comarca,
            distribuicao: meta.cnj_metadata.distribuicao,
            valorCausa: meta.cnj_metadata.valor_causa,
        } : undefined,
        customFields: meta.custom_fields,
    };
}

/**
 * Schema for array of documents
 */
export const DocumentArraySchema = z.array(ApiDocumentSchema).transform(
    (docs) => docs.map((doc) => DocumentSchema.parse(doc))
);

// Type exports for convenience
export type ApiDocumentInput = z.input<typeof DocumentSchema>;
export type DocumentOutput = z.output<typeof DocumentSchema>;
