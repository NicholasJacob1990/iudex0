import { useCallback } from 'react';
import { useDocumentStore } from '@/stores/document-store';
import {
  insertTextAtCursor,
  appendText,
  replaceText,
  addCommentAtSelection,
  addCommentAtText,
} from '@/office/document-bridge';

/**
 * Hook para interagir com o documento Word.
 * Combina o estado do documento (store) com ações de escrita (bridge).
 */
export function useOfficeDocument() {
  const {
    fullText,
    selectedText,
    metadata,
    isLoading,
    error,
    loadFullText,
    loadSelection,
    loadMetadata,
    refresh,
  } = useDocumentStore();

  const insert = useCallback(async (text: string) => {
    await insertTextAtCursor(text);
    await useDocumentStore.getState().loadFullText();
  }, []);

  const append = useCallback(async (text: string) => {
    await appendText(text);
    await useDocumentStore.getState().loadFullText();
  }, []);

  const replace = useCallback(async (search: string, replacement: string) => {
    const count = await replaceText(search, replacement);
    await useDocumentStore.getState().loadFullText();
    return count;
  }, []);

  const commentSelection = useCallback(async (comment: string) => {
    await addCommentAtSelection(comment);
  }, []);

  const commentText = useCallback(async (search: string, comment: string) => {
    return addCommentAtText(search, comment);
  }, []);

  return {
    // State
    fullText,
    selectedText,
    metadata,
    isLoading,
    error,
    // Read actions
    loadFullText,
    loadSelection,
    loadMetadata,
    refresh,
    // Write actions
    insert,
    append,
    replace,
    commentSelection,
    commentText,
  };
}
