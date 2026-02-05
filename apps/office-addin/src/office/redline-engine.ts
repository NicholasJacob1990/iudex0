/**
 * Motor de redlines para aplicar tracked changes no documento Word.
 *
 * Estratégias disponíveis:
 * 1. Comentários com sugestão (sempre funciona, WordApi 1.1+)
 * 2. Substituição direta com destaque (WordApi 1.3+)
 * 3. OOXML com tracked changes (avançado, Word desktop)
 */

import {
  addCommentAtText,
  replaceText,
} from './document-bridge';

// ── Platform Detection (Gap 9) ─────────────────────────────────

/**
 * Detecta se o add-in esta rodando no Word Online.
 * Word Online tem limitacoes com OOXML tracked changes.
 */
export function isWordOnline(): boolean {
  try {
    return Office.context.platform === Office.PlatformType.OfficeOnline;
  } catch {
    // Se nao conseguir detectar, assume desktop (mais capaz)
    return false;
  }
}

/**
 * Detecta a plataforma atual do Office.
 */
export function getOfficePlatform(): 'online' | 'windows' | 'mac' | 'ios' | 'android' | 'unknown' {
  try {
    switch (Office.context.platform) {
      case Office.PlatformType.OfficeOnline:
        return 'online';
      case Office.PlatformType.PC:
        return 'windows';
      case Office.PlatformType.Mac:
        return 'mac';
      case Office.PlatformType.iOS:
        return 'ios';
      case Office.PlatformType.Android:
        return 'android';
      default:
        return 'unknown';
    }
  } catch {
    return 'unknown';
  }
}

/**
 * Verifica se a plataforma suporta OOXML tracked changes completos.
 * Apenas Windows e Mac desktop tem suporte confiavel.
 */
export function supportsFullOOXML(): boolean {
  const platform = getOfficePlatform();
  return platform === 'windows' || platform === 'mac';
}

// ── Types ──────────────────────────────────────────────────────

export type RedlineAction = 'insert' | 'delete' | 'replace' | 'comment';

export interface RedlineOperation {
  id: string;
  action: RedlineAction;
  /** Texto original encontrado no documento */
  originalText: string;
  /** Texto sugerido (para replace/insert) */
  suggestedText?: string;
  /** Comentário explicativo */
  comment?: string;
  /** Severidade da cláusula */
  severity: 'critical' | 'warning' | 'info';
  /** Nome da regra do playbook */
  ruleName: string;
  /** OOXML pré-gerado pelo servidor (Fase 2) — quando presente, usado em vez de gerar client-side */
  ooxml?: string;
}

export interface RedlineResult {
  operationId: string;
  success: boolean;
  error?: string;
  /** Metodo usado para aplicar o redline */
  method?: 'ooxml' | 'fallback' | 'comment' | 'highlight' | 'replace';
}

export interface BatchRedlineResult {
  total: number;
  applied: number;
  failed: number;
  results: RedlineResult[];
}

// ── Aplicar redline individual ─────────────────────────────────

/**
 * Aplica um redline como comentário no documento.
 * Busca o texto original e adiciona comentário com a sugestão.
 */
export async function applyRedlineAsComment(
  op: RedlineOperation
): Promise<RedlineResult> {
  try {
    const commentBody = buildCommentText(op);
    const searchText = op.originalText.slice(0, 200);
    const found = await addCommentAtText(searchText, commentBody);

    return {
      operationId: op.id,
      success: found,
      error: found ? undefined : 'Texto não encontrado no documento',
    };
  } catch (err) {
    return {
      operationId: op.id,
      success: false,
      error: err instanceof Error ? err.message : 'Erro ao aplicar comentário',
    };
  }
}

/**
 * Aplica um redline substituindo o texto diretamente.
 * Busca o texto original e substitui pelo sugerido.
 */
export async function applyRedlineAsReplace(
  op: RedlineOperation
): Promise<RedlineResult> {
  if (!op.suggestedText) {
    return {
      operationId: op.id,
      success: false,
      error: 'Sem texto sugerido para substituição',
    };
  }

  try {
    const count = await replaceText(op.originalText, op.suggestedText);
    return {
      operationId: op.id,
      success: count > 0,
      error: count === 0 ? 'Texto não encontrado no documento' : undefined,
    };
  } catch (err) {
    return {
      operationId: op.id,
      success: false,
      error: err instanceof Error ? err.message : 'Erro ao substituir texto',
    };
  }
}

/**
 * Aplica redline com destaque visual (highlight + comentário).
 * Busca o trecho, aplica highlight amarelo e adiciona comentário.
 */
export async function applyRedlineWithHighlight(
  op: RedlineOperation
): Promise<RedlineResult> {
  try {
    const result = await Word.run(async (context) => {
      const searchText = op.originalText.slice(0, 255);
      const results = context.document.body.search(searchText, {
        matchCase: false,
        matchWholeWord: false,
      });
      results.load('items');
      await context.sync();

      if (results.items.length === 0) {
        return false;
      }

      const range = results.items[0];

      // Highlight com cor baseada na severidade
      const highlightColor = getHighlightColor(op.severity);
      range.font.highlightColor = highlightColor;

      // Adicionar comentário com sugestão
      const commentBody = buildCommentText(op);
      range.insertComment(commentBody);

      await context.sync();
      return true;
    });

    return {
      operationId: op.id,
      success: result,
      error: result ? undefined : 'Texto não encontrado no documento',
    };
  } catch (err) {
    return {
      operationId: op.id,
      success: false,
      error: err instanceof Error ? err.message : 'Erro ao aplicar redline',
    };
  }
}

/**
 * Aplica redline usando OOXML para criar tracked changes reais.
 * Funciona melhor em Word desktop (Windows/Mac).
 *
 * Gap 9: Detecta Word Online automaticamente e usa fallback.
 */
export async function applyRedlineAsTrackedChange(
  op: RedlineOperation
): Promise<RedlineResult> {
  if (!op.suggestedText || op.action === 'comment') {
    return applyRedlineAsComment(op);
  }

  // Gap 9: Word Online nao suporta OOXML tracked changes de forma confiavel
  // Usar fallback automatico com comentarios + highlight
  if (isWordOnline()) {
    return applyRedlineAsFallback(op);
  }

  try {
    const result = await Word.run(async (context) => {
      const searchText = op.originalText.slice(0, 255);
      const results = context.document.body.search(searchText, {
        matchCase: false,
        matchWholeWord: false,
      });
      results.load('items');
      await context.sync();

      if (results.items.length === 0) {
        return { found: false, method: 'ooxml' as const };
      }

      const range = results.items[0];

      // Fase 2: preferir OOXML pré-gerado pelo servidor quando disponível
      const ooxml = op.ooxml || buildTrackedChangeOoxml(
        op.originalText,
        op.suggestedText || '',
        op.action
      );

      try {
        range.insertOoxml(ooxml, Word.InsertLocation.replace);
        await context.sync();
        return { found: true, method: 'ooxml' as const };
      } catch {
        // Fallback: OOXML tracked changes não suportado nesta plataforma
        // Usar highlight + comentário
        range.font.highlightColor = getHighlightColor(op.severity);
        range.insertComment(buildCommentText(op));
        await context.sync();
        return { found: true, method: 'fallback' as const };
      }
    });

    return {
      operationId: op.id,
      success: result.found,
      method: result.method,
      error: result.found ? undefined : 'Texto não encontrado no documento',
    };
  } catch (err) {
    return {
      operationId: op.id,
      success: false,
      error: err instanceof Error ? err.message : 'Erro ao aplicar tracked change',
    };
  }
}

/**
 * Gap 9: Fallback para Word Online e plataformas sem suporte a OOXML.
 *
 * Aplica redline usando comentarios + highlight em vez de tracked changes.
 * Esta estrategia funciona em todas as plataformas.
 */
export async function applyRedlineAsFallback(
  op: RedlineOperation
): Promise<RedlineResult> {
  try {
    const result = await Word.run(async (context) => {
      const searchText = op.originalText.slice(0, 255);
      const results = context.document.body.search(searchText, {
        matchCase: false,
        matchWholeWord: false,
      });
      results.load('items');
      await context.sync();

      if (results.items.length === 0) {
        return false;
      }

      const range = results.items[0];

      // 1. Highlight com cor baseada na classificacao/severidade
      const highlightColor = getHighlightColorForFallback(op);
      range.font.highlightColor = highlightColor;

      // 2. Comentario detalhado com sugestao de redline
      const commentBody = buildFallbackComment(op);
      range.insertComment(commentBody);

      await context.sync();
      return true;
    });

    return {
      operationId: op.id,
      success: result,
      method: 'fallback',
      error: result ? undefined : 'Texto não encontrado no documento',
    };
  } catch (err) {
    return {
      operationId: op.id,
      success: false,
      method: 'fallback',
      error: err instanceof Error ? err.message : 'Erro ao aplicar fallback',
    };
  }
}

/**
 * Determina cor de highlight para fallback baseado em severidade e classificacao.
 */
function getHighlightColorForFallback(op: RedlineOperation): string {
  // Priorizar severidade
  if (op.severity === 'critical') return 'Red';
  if (op.severity === 'warning') return 'Yellow';
  return 'Turquoise';
}

/**
 * Constroi comentario detalhado para modo fallback do Word Online.
 */
function buildFallbackComment(op: RedlineOperation): string {
  const parts: string[] = ['[Iudex]'];

  if (op.ruleName) {
    parts.push(`Regra: ${op.ruleName}`);
  }

  parts.push('\n\n--- SUGESTAO DE ALTERACAO ---');

  if (op.suggestedText) {
    parts.push(`\nSubstituir por:\n"${op.suggestedText}"`);
  }

  if (op.comment) {
    parts.push(`\n\nMotivo: ${op.comment}`);
  }

  parts.push('\n\n(Word Online: aplique manualmente esta sugestao)');

  return parts.join(' ');
}

// ── Navegação ──────────────────────────────────────────────────

/**
 * Navega até um trecho de texto no documento e o seleciona.
 */
export async function navigateToText(searchText: string): Promise<boolean> {
  return Word.run(async (context) => {
    const text = searchText.slice(0, 255);
    const results = context.document.body.search(text, {
      matchCase: false,
      matchWholeWord: false,
    });
    results.load('items');
    await context.sync();

    if (results.items.length === 0) return false;

    results.items[0].select();
    await context.sync();
    return true;
  });
}

/**
 * Destaca visualmente múltiplos trechos no documento
 * para indicar cláusulas encontradas pela análise.
 */
export async function highlightClauses(
  clauses: Array<{
    text: string;
    severity: 'critical' | 'warning' | 'info';
    classification: string;
  }>
): Promise<number> {
  return Word.run(async (context) => {
    let highlighted = 0;

    for (const clause of clauses) {
      if (!clause.text || clause.classification === 'conforme' || clause.classification === 'compliant') continue;

      const searchText = clause.text.slice(0, 255);
      const results = context.document.body.search(searchText, {
        matchCase: false,
        matchWholeWord: false,
      });
      results.load('items');
      await context.sync();

      if (results.items.length > 0) {
        results.items[0].font.highlightColor = getHighlightColor(clause.severity);
        highlighted++;
      }
    }

    await context.sync();
    return highlighted;
  });
}

/**
 * Remove todos os highlights do documento.
 */
export async function clearHighlights(): Promise<void> {
  return Word.run(async (context) => {
    const body = context.document.body;
    body.font.highlightColor = 'None';
    await context.sync();
  });
}

// ── Batch operations ───────────────────────────────────────────

/**
 * Aplica múltiplos redlines em batch.
 * Usa a estratégia especificada para cada operação.
 */
export async function applyBatchRedlines(
  operations: RedlineOperation[],
  strategy: 'comment' | 'highlight' | 'replace' | 'tracked-change' = 'highlight'
): Promise<BatchRedlineResult> {
  const results: RedlineResult[] = [];

  const applyFn =
    strategy === 'comment'
      ? applyRedlineAsComment
      : strategy === 'replace'
        ? applyRedlineAsReplace
        : strategy === 'tracked-change'
          ? applyRedlineAsTrackedChange
          : applyRedlineWithHighlight;

  // Aplicar sequencialmente para evitar conflitos no Office.js
  for (const op of operations) {
    const result = await applyFn(op);
    results.push(result);
  }

  const applied = results.filter((r) => r.success).length;

  return {
    total: operations.length,
    applied,
    failed: operations.length - applied,
    results,
  };
}

// ── Helpers ────────────────────────────────────────────────────

function getHighlightColor(severity: 'critical' | 'warning' | 'info'): string {
  switch (severity) {
    case 'critical':
      return 'Red';
    case 'warning':
      return 'Yellow';
    case 'info':
      return 'Turquoise';
  }
}

function buildCommentText(op: RedlineOperation): string {
  const parts: string[] = [];

  if (op.ruleName) {
    parts.push(`[${op.ruleName}]`);
  }

  if (op.comment) {
    parts.push(op.comment);
  }

  if (op.suggestedText && op.action !== 'comment') {
    parts.push(`\nSugestao de redline: ${op.suggestedText}`);
  }

  return parts.join(' ');
}

/**
 * Gera OOXML com tracked changes (w:ins/w:del).
 *
 * Nota: OOXML tracked changes requer um pacote completo.
 * Esta é uma versão simplificada que funciona em Word desktop.
 */
function buildTrackedChangeOoxml(
  originalText: string,
  newText: string,
  action: RedlineAction
): string {
  const author = 'Vorbium AI';
  const date = new Date().toISOString();
  const rsidR = '00A77427';

  const escapeXml = (text: string) =>
    text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');

  const safeOriginal = escapeXml(originalText);
  const safeNew = escapeXml(newText);

  if (action === 'delete') {
    return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage">
  <pkg:part pkg:name="/_rels/.rels" pkg:contentType="application/vnd.openxmlformats-package.relationships+xml">
    <pkg:xmlData>
      <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
        <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
      </Relationships>
    </pkg:xmlData>
  </pkg:part>
  <pkg:part pkg:name="/word/document.xml" pkg:contentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml">
    <pkg:xmlData>
      <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
        <w:body>
          <w:p w:rsidR="${rsidR}">
            <w:del w:id="1" w:author="${author}" w:date="${date}">
              <w:r><w:delText xml:space="preserve">${safeOriginal}</w:delText></w:r>
            </w:del>
          </w:p>
        </w:body>
      </w:document>
    </pkg:xmlData>
  </pkg:part>
</pkg:package>`;
  }

  if (action === 'insert') {
    return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage">
  <pkg:part pkg:name="/_rels/.rels" pkg:contentType="application/vnd.openxmlformats-package.relationships+xml">
    <pkg:xmlData>
      <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
        <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
      </Relationships>
    </pkg:xmlData>
  </pkg:part>
  <pkg:part pkg:name="/word/document.xml" pkg:contentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml">
    <pkg:xmlData>
      <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
        <w:body>
          <w:p w:rsidR="${rsidR}">
            <w:ins w:id="1" w:author="${author}" w:date="${date}">
              <w:r><w:t xml:space="preserve">${safeNew}</w:t></w:r>
            </w:ins>
          </w:p>
        </w:body>
      </w:document>
    </pkg:xmlData>
  </pkg:part>
</pkg:package>`;
  }

  // Replace: del + ins
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage">
  <pkg:part pkg:name="/_rels/.rels" pkg:contentType="application/vnd.openxmlformats-package.relationships+xml">
    <pkg:xmlData>
      <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
        <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
      </Relationships>
    </pkg:xmlData>
  </pkg:part>
  <pkg:part pkg:name="/word/document.xml" pkg:contentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml">
    <pkg:xmlData>
      <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
        <w:body>
          <w:p w:rsidR="${rsidR}">
            <w:del w:id="1" w:author="${author}" w:date="${date}">
              <w:r><w:delText xml:space="preserve">${safeOriginal}</w:delText></w:r>
            </w:del>
            <w:ins w:id="2" w:author="${author}" w:date="${date}">
              <w:r><w:t xml:space="preserve">${safeNew}</w:t></w:r>
            </w:ins>
          </w:p>
        </w:body>
      </w:document>
    </pkg:xmlData>
  </pkg:part>
</pkg:package>`;
}
