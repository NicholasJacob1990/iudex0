/**
 * Bridge entre o Office Add-in e o documento Word via Office.js API.
 *
 * Todas as interações com o documento passam por este módulo.
 */

export interface DocumentMetadata {
  title: string;
  author: string;
  lastModified: string;
  wordCount: number;
}

export interface DocumentSelection {
  text: string;
  isEmpty: boolean;
}

/** Extrai o texto completo do documento. */
export async function getDocumentText(): Promise<string> {
  return Word.run(async (context) => {
    const body = context.document.body;
    body.load('text');
    await context.sync();
    return body.text;
  });
}

/** Extrai o texto selecionado pelo usuário. */
export async function getSelectedText(): Promise<DocumentSelection> {
  return Word.run(async (context) => {
    const selection = context.document.getSelection();
    selection.load('text');
    await context.sync();
    return {
      text: selection.text,
      isEmpty: !selection.text.trim(),
    };
  });
}

/** Insere texto na posição do cursor. */
export async function insertTextAtCursor(text: string): Promise<void> {
  return Word.run(async (context) => {
    const selection = context.document.getSelection();
    selection.insertText(text, Word.InsertLocation.replace);
    await context.sync();
  });
}

/** Insere texto ao final do documento. */
export async function appendText(text: string): Promise<void> {
  return Word.run(async (context) => {
    const body = context.document.body;
    body.insertText(text, Word.InsertLocation.end);
    await context.sync();
  });
}

/** Substitui todas as ocorrências de um texto. */
export async function replaceText(
  search: string,
  replacement: string
): Promise<number> {
  return Word.run(async (context) => {
    const results = context.document.body.search(search, {
      matchCase: false,
      matchWholeWord: false,
    });
    results.load('items');
    await context.sync();

    for (const item of results.items) {
      item.insertText(replacement, Word.InsertLocation.replace);
    }
    await context.sync();
    return results.items.length;
  });
}

/** Adiciona um comentário na seleção atual. */
export async function addCommentAtSelection(text: string): Promise<void> {
  return Word.run(async (context) => {
    const selection = context.document.getSelection();
    selection.insertComment(text);
    await context.sync();
  });
}

/** Busca um trecho de texto e adiciona um comentário nele. */
export async function addCommentAtText(
  searchText: string,
  comment: string
): Promise<boolean> {
  return Word.run(async (context) => {
    const results = context.document.body.search(searchText, {
      matchCase: false,
      matchWholeWord: false,
    });
    results.load('items');
    await context.sync();

    if (results.items.length > 0) {
      results.items[0].insertComment(comment);
      await context.sync();
      return true;
    }
    return false;
  });
}

/** Obtém metadata do documento. */
export async function getDocumentMetadata(): Promise<DocumentMetadata> {
  return Word.run(async (context) => {
    const properties = context.document.properties;
    const body = context.document.body;
    properties.load(['title', 'author', 'lastSaveTime']);
    body.load('text');
    await context.sync();

    const wordCount = body.text
      .split(/\s+/)
      .filter((w) => w.length > 0).length;

    return {
      title: properties.title || 'Documento sem título',
      author: properties.author || 'Desconhecido',
      lastModified: properties.lastSaveTime?.toISOString() || '',
      wordCount,
    };
  });
}

/** Obtém o conteúdo OOXML do documento (para redlines avançados). */
export async function getDocumentOoxml(): Promise<string> {
  return Word.run(async (context) => {
    const body = context.document.body;
    const ooxml = body.getOoxml();
    await context.sync();
    return ooxml.value;
  });
}

/** Insere OOXML no documento (para redlines com tracked changes). */
export async function insertOoxml(ooxml: string): Promise<void> {
  return Word.run(async (context) => {
    const selection = context.document.getSelection();
    selection.insertOoxml(ooxml, Word.InsertLocation.replace);
    await context.sync();
  });
}

/** Obtém todas as tabelas do documento. */
export async function getTableCount(): Promise<number> {
  return Word.run(async (context) => {
    const tables = context.document.body.tables;
    tables.load('items');
    await context.sync();
    return tables.items.length;
  });
}

/** Obtém parágrafos do documento para processamento incremental. */
export async function getParagraphs(): Promise<string[]> {
  return Word.run(async (context) => {
    const paragraphs = context.document.body.paragraphs;
    paragraphs.load('text');
    await context.sync();
    return paragraphs.items.map((p) => p.text);
  });
}

// ── Gap 6: Document Hash para tracking de modificações ──────────

/**
 * Calcula um hash SHA-256 do texto do documento.
 * Usado para detectar se o documento foi modificado após aplicação de redlines.
 */
export async function getDocumentHash(): Promise<string> {
  return Word.run(async (context) => {
    const body = context.document.body;
    body.load('text');
    await context.sync();

    const text = body.text;
    const encoder = new TextEncoder();
    const data = encoder.encode(text);
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
  });
}

/**
 * Compara o hash atual do documento com um hash esperado.
 * Retorna true se o documento foi modificado.
 */
export async function checkDocumentModified(expectedHash: string): Promise<boolean> {
  const currentHash = await getDocumentHash();
  return currentHash !== expectedHash;
}
