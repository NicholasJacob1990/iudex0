'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Bot, Loader2, MessageSquare, Send, X } from 'lucide-react';
import { apiBaseUrl } from '@/lib/api-client';
import { cn } from '@/lib/utils';

type GraphAskOperation =
  | 'path'
  | 'neighbors'
  | 'cooccurrence'
  | 'search'
  | 'count'
  | 'legal_diagnostics'
  | 'link_entities'
  | 'recompute_co_menciona';

type GraphChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  operation?: GraphAskOperation;
  entities?: Array<{ id: string; name: string }>;
  pendingLink?: {
    source: { id: string; name: string };
    target: { id: string; name: string };
    relation_type: string;
    properties?: Record<string, any>;
    preflight_token?: string;
    raw?: string;
  };
};

type GraphAskIntent = {
  operation: GraphAskOperation;
  params: Record<string, any>;
};

const ENTITY_TYPES = new Set([
  'lei',
  'artigo',
  'sumula',
  'jurisprudencia',
  'tema',
  'tribunal',
  'tese',
  'conceito',
  'principio',
  'instituto',
]);

function makeId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

// UI clamp: keep production-safe defaults (server may allow 6 for admins via API).
const clampGraphHops = (value: number) => Math.max(1, Math.min(5, Math.floor(Number(value) || 3)));

async function callCreateChat(payload: { title?: string; mode?: 'CHAT' | 'MINUTA'; context?: Record<string, any> }) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const response = await fetch(`${apiBaseUrl}/chats/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      title: payload.title || 'Graph Chat',
      mode: payload.mode || 'CHAT',
      context: payload.context || {},
    }),
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const data = await response.json();
      message = String(data?.detail || data?.error || message);
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  return (await response.json()) as { id: string; title: string; mode: string; context: Record<string, any> };
}

async function callChatStream(params: {
  chatId: string;
  content: string;
  graphHops: number;
  onToken: (delta: string) => void;
  onDone: (fullText?: string) => void;
  onError: (message: string) => void;
}) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const response = await fetch(`${apiBaseUrl}/chats/${params.chatId}/messages/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      content: params.content,
      chat_personality: 'juridico',
      // Force agent model so the backend enables native tool-calling (ask_graph + unified tools).
      model: 'claude-agent',
      reasoning_level: 'medium',
      web_search: false,
      graph_rag_enabled: true,
      graph_hops: clampGraphHops(params.graphHops),
      // Extra safety: don't let the LLM write in LLM-mode; writes stay deterministic (/link or "conecte").
      thesis:
        'MODO GRAFO (UI): Use tools do grafo (ask_graph) e escolha a operacao pelo pedido do usuario. ' +
        'Mapa rapido: vizinhos/relacionados=>neighbors/related_entities; caminho/cadeia=>path (ou audit_graph_chain se pedir auditoria/evidencias); ' +
        'comunidades/cluster=>leiden; centralidade/ponte=>betweenness_centrality ou bridges/articulation_points; similaridade=>node_similarity (lista) ou adamic_adar (par). ' +
        'CUSTO: prefira operacoes basicas antes de GDS; max 1 GDS pesado por turno. ' +
        'ESCRITA BLOQUEADA neste modo: nao use link_entities nem recompute_co_menciona. Para escrita, o usuario deve usar /link fora deste modo.',
    }),
  });

  if (!response.ok || !response.body) {
    let message = `HTTP ${response.status}`;
    try {
      const data = await response.json();
      message = String(data?.detail || data?.error || message);
    } catch {
      // ignore
    }
    params.onError(message);
    return;
  }

  const decoder = new TextDecoder('utf-8');
  const reader = response.body.getReader();
  let buf = '';

  const flushEvent = (rawEvent: string) => {
    const lines = rawEvent.split('\n');
    const dataLines = lines
      .map((l) => l.trimEnd())
      .filter((l) => l.startsWith('data:'))
      .map((l) => l.replace(/^data:\s?/, ''));
    if (!dataLines.length) return;
    const dataStr = dataLines.join('\n').trim();
    if (!dataStr) return;
    let obj: any = null;
    try {
      obj = JSON.parse(dataStr);
    } catch {
      return;
    }
    const t = String(obj?.type || '');
    if (t === 'token') {
      const delta = String(obj?.delta || '');
      if (delta) params.onToken(delta);
    } else if (t === 'done') {
      const fullText = typeof obj?.full_text === 'string' ? obj.full_text : undefined;
      params.onDone(fullText);
    } else if (t === 'error') {
      params.onError(String(obj?.error || 'erro desconhecido'));
    }
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      // SSE events are separated by blank line.
      while (true) {
        const idx = buf.indexOf('\n\n');
        if (idx < 0) break;
        const rawEvent = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const trimmed = rawEvent.trim();
        if (!trimmed || trimmed.startsWith(':')) continue; // keepalive/comment
        flushEvent(rawEvent);
      }
    }
    // Flush any remaining buffered event.
    const tail = buf.trim();
    if (tail && !tail.startsWith(':')) flushEvent(tail);
    params.onDone(undefined);
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'erro desconhecido';
    params.onError(msg);
  }
}

function looksLikeEntityId(value: string) {
  const v = String(value || '').trim();
  if (!v) return false;
  if (v.length > 120) return false;
  if (/\s/.test(v)) return false;
  // Entity IDs in Iudex are typically snake-ish with at least one underscore.
  return v.includes('_') || v.startsWith('proc_');
}

function stripOuterQuotes(value: string) {
  const v = String(value || '').trim();
  if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
    return v.slice(1, -1).trim();
  }
  return v;
}

function _extractQuotedPhrases(input: string) {
  const out: string[] = [];
  const re = /"([^"]+)"/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(input)) !== null) {
    const v = String(m[1] || '').trim();
    if (v) out.push(v);
  }
  return out;
}

function looksLikeEntityRef(value: string) {
  const v = String(value || '').trim();
  if (!v) return false;
  if (looksLikeEntityId(v)) return true;
  const lower = v.toLowerCase();
  if (/\d/.test(v) && /\b(art\.?|sumul[ae]|lei|tema|processo|re|resp|are|adi|adpf|hc|ms|rcl)\b/.test(lower)) {
    return true;
  }
  if (/\b(stf|stj|tst|trf|tj)\b/.test(lower) && /\d/.test(v)) return true;
  if (/^art\.?\s*\d+/.test(lower)) return true;
  if (/^s[uú]mula/.test(lower)) return true;
  if (/^lei\s*(n[ºo]\s*)?\d/.test(lower)) return true;
  if (/^tema\s*\d+/.test(lower)) return true;
  return false;
}

function normalizeRelationFromVerb(verb: string, rightRef: string): string {
  const v = String(verb || '').toLowerCase();
  if (v.includes('interpreta') || v.includes('interpretad')) return 'INTERPRETA';
  if (v.includes('remete')) return 'REMETE_A';
  if (v.includes('pertence')) return 'PERTENCE_A';
  if (v.includes('fundament')) return 'FUNDAMENTA';
  if (v.includes('cita')) return 'CITA';
  if (v.includes('fixa tese')) return 'FIXA_TESE';
  if (v.includes('julga tema')) return 'JULGA_TEMA';
  if (v.includes('proferida por') || v.includes('proferido por')) return 'PROFERIDA_POR';
  if (v.includes('revoga')) return 'REVOGA';
  if (v.includes('altera')) return 'ALTERA';
  if (v.includes('regulament')) return 'REGULAMENTA';
  if (v.includes('especializa')) return 'ESPECIALIZA';
  if (v.includes('substitui')) return 'SUBSTITUI';
  if (v.includes('cancela')) return 'CANCELA';
  if (v.includes('complementa')) return 'COMPLEMENTA';
  if (v.includes('excepcion')) return 'EXCEPCIONA';
  if (v.includes('disting')) return 'DISTINGUE';
  if (v.includes('supera')) return 'SUPERA';
  if (v.includes('confirma')) return 'CONFIRMA';
  if (v.includes('aplica')) {
    const r = String(rightRef || '').toLowerCase();
    if (/\bs[uú]mula\b/.test(r)) return 'APLICA_SUMULA';
    return 'APLICA';
  }
  return 'RELATED_TO';
}

function _extractEvidenceSnippet(raw: string): string | null {
  const text = String(raw || '');
  if (!text) return null;

  // Accept: evidence:"..." | trecho:"..." | ev:"..."
  const m = text.match(/\b(evidence|trecho|ev)\s*:\s*\"([^\"]{3,400})\"/i);
  if (m) return String(m[2] || '').trim();

  // Accept: evidence "...", ev "..."
  const m2 = text.match(/\b(evidence|trecho|ev)\b\s+\"([^\"]{3,400})\"/i);
  if (m2) return String(m2[2] || '').trim();

  return null;
}

function inferDimension(relationType: string): string | null {
  const rel = String(relationType || '').trim().toUpperCase();
  if (!rel) return null;
  if (rel === 'REMETE_A') return 'remissiva';
  if (['CITA', 'CONFIRMA', 'SUPERA', 'DISTINGUE', 'CANCELA', 'SUBSTITUI', 'REVOGA', 'ALTERA', 'COMPLEMENTA', 'EXCEPCIONA', 'REGULAMENTA', 'ESPECIALIZA', 'CO_MENCIONA'].includes(rel)) {
    return 'horizontal';
  }
  if (['PERTENCE_A', 'INTERPRETA', 'APLICA', 'APLICA_SUMULA', 'FIXA_TESE', 'JULGA_TEMA', 'FUNDAMENTA', 'PROFERIDA_POR', 'SUBDISPOSITIVO_DE'].includes(rel)) {
    return 'hierarquica';
  }
  if (['PARTICIPA_DE', 'REPRESENTA', 'PARTE_DE', 'IDENTIFICADO_POR', 'OCORRE_EM'].includes(rel)) {
    return 'fatica';
  }
  return null;
}

function parseNaturalLinkIntent(input: string): { source: string; target: string; relation_type: string; evidence?: string | null } | null {
  const raw = String(input || '').trim();
  if (!raw) return null;

  const lower = raw.toLowerCase();

  // Avoid accidental writes for explicit questions.
  const looksLikeQuestion =
    raw.includes('?') ||
    /\b(qual|quais|como|por que|porque|mostre|exiba|encontre|buscar|busca)\b/.test(lower);

  const hasWriteVerb =
    /\b(conecte|conectar|crie|criar|adicione|adicionar|gere|gerar|linke|ligue|relacione)\b/.test(lower) ||
    /\b(interpreta|interpreta[ds]?|aplica|remete|pertence|fundamenta|cita|revoga|altera|regulamenta|especializa|substitui|cancela|complementa|excepciona)\b/.test(
      lower
    ) ||
    /\b(fixa\s+tese|julga\s+tema|proferid[ao]\s+por)\b/.test(lower);
  const hasWriteNoun = /\b(aresta|relacao|relação|link|conexao|conexão)\b/.test(lower);
  const viaMatch = raw.match(/\bvia\s+([A-Za-z][A-Za-z0-9_]{0,40})\b/i);
  const explicitRelationType = String(viaMatch?.[1] || '').trim().toUpperCase();
  let relationType = explicitRelationType || 'RELATED_TO';
  const evidence = _extractEvidenceSnippet(raw);

  // Gate: only interpret as write intent if it's imperative-ish and not phrased as a query.
  if (!hasWriteVerb) return null;
  if (looksLikeQuestion && !/\b(crie|criar|adicione|adicionar)\b/.test(lower)) return null;

  const quoted = _extractQuotedPhrases(raw);
  if (quoted.length >= 2) {
    if (!explicitRelationType) {
      // Try infer from verbs when relation is not explicit.
      relationType = normalizeRelationFromVerb(lower, quoted[1]);
    }
    return { source: quoted[0], target: quoted[1], relation_type: relationType, evidence };
  }

  // Remove trailing "via REL" to parse entities.
  const withoutVia = viaMatch ? raw.replace(/\bvia\s+[A-Za-z][A-Za-z0-9_]{0,40}\b/i, '').trim() : raw;

  // Try "entre X e Y" first
  const entreMatch = withoutVia.match(/\bentre\s+(.+?)\s+e\s+(.+)$/i);
  if (entreMatch) {
    const source = stripOuterQuotes(String(entreMatch[1] || '').trim());
    const target = stripOuterQuotes(String(entreMatch[2] || '').trim());
    if (source && target) {
      if (!explicitRelationType) relationType = normalizeRelationFromVerb(lower, target);
      if (!hasWriteNoun && relationType === 'RELATED_TO') return null;
      if (!looksLikeEntityRef(source) || !looksLikeEntityRef(target)) return null;
      return { source, target, relation_type: relationType, evidence };
    }
  }

  // Try "X com Y"
  const comMatch = withoutVia.match(/(.+?)\s+\bcom\b\s+(.+)$/i);
  if (comMatch) {
    const source = stripOuterQuotes(String(comMatch[1] || '').trim());
    const target = stripOuterQuotes(String(comMatch[2] || '').trim());
    if (source && target) {
      if (!explicitRelationType) relationType = normalizeRelationFromVerb(lower, target);
      if (!hasWriteNoun && relationType === 'RELATED_TO') return null;
      if (!looksLikeEntityRef(source) || !looksLikeEntityRef(target)) return null;
      return { source, target, relation_type: relationType, evidence };
    }
  }

  // Try arrow form: "X -> Y"
  const arrow = withoutVia.split('->');
  if (arrow.length >= 2) {
    const source = stripOuterQuotes(String(arrow[0] || '').trim());
    const target = stripOuterQuotes(String(arrow.slice(1).join('->') || '').trim());
    if (source && target) {
      if (!explicitRelationType) relationType = normalizeRelationFromVerb(lower, target);
      if (!hasWriteNoun && relationType === 'RELATED_TO') return null;
      if (!looksLikeEntityRef(source) || !looksLikeEntityRef(target)) return null;
      return { source, target, relation_type: relationType, evidence };
    }
  }

  // Verb-based patterns: "X interpreta Y", "X remete a Y", "Y é interpretado por X"
  const verbPatterns: Array<{ re: RegExp; flip?: boolean; verb: string }> = [
    { re: /^(.+?)\s+(fixa\s+tese)\s+(.+)$/i, verb: 'fixa tese' },
    { re: /^(.+?)\s+(julga\s+tema)\s+(.+)$/i, verb: 'julga tema' },
    { re: /^(.+?)\s+(proferid[ao]\s+por)\s+(.+)$/i, verb: 'proferida por', flip: true }, // "X proferida por Y" => Y -> PROFERIDA_POR -> X
    { re: /^(.+?)\s+(interpreta)\s+(.+)$/i, verb: 'interpreta' },
    { re: /^(.+?)\s+(aplica)\s+(.+)$/i, verb: 'aplica' },
    { re: /^(.+?)\s+(fundamenta)\s+(.+)$/i, verb: 'fundamenta' },
    { re: /^(.+?)\s+(cita)\s+(.+)$/i, verb: 'cita' },
    { re: /^(.+?)\s+(remete\s+a)\s+(.+)$/i, verb: 'remete a' },
    { re: /^(.+?)\s+(pertence\s+a)\s+(.+)$/i, verb: 'pertence a' },
    { re: /^(.+?)\s+(revoga)\s+(.+)$/i, verb: 'revoga' },
    { re: /^(.+?)\s+(altera)\s+(.+)$/i, verb: 'altera' },
    { re: /^(.+?)\s+(regulamenta)\s+(.+)$/i, verb: 'regulamenta' },
    { re: /^(.+?)\s+(especializa)\s+(.+)$/i, verb: 'especializa' },
    { re: /^(.+?)\s+(substitui)\s+(.+)$/i, verb: 'substitui' },
    { re: /^(.+?)\s+(cancela)\s+(.+)$/i, verb: 'cancela' },
    { re: /^(.+?)\s+(complementa)\s+(.+)$/i, verb: 'complementa' },
    { re: /^(.+?)\s+(excepciona)\s+(.+)$/i, verb: 'excepciona' },
    // Passive-ish: "Y é interpretado por X"
    { re: /^(.+?)\s+e\s+interpretad[ao]\s+por\s+(.+)$/i, verb: 'interpretado por', flip: true },
  ];

  for (const p of verbPatterns) {
    const m = withoutVia.match(p.re);
    if (!m) continue;
    const a = stripOuterQuotes(String(m[1] || '').trim());
    const b = stripOuterQuotes(String(m[3] || m[2] || '').trim());
    if (!a || !b) continue;
    const rel = explicitRelationType || normalizeRelationFromVerb(p.verb, b);
    // If we cannot infer a relation and user did not explicitly ask to "create/link", avoid accidental writes.
    if (!hasWriteNoun && rel === 'RELATED_TO' && !/\b(conecte|crie|adicione|linke|relacione)\b/.test(lower)) {
      continue;
    }
    if (!looksLikeEntityRef(a) || !looksLikeEntityRef(b)) continue;
    if (p.flip) {
      return { source: b, target: a, relation_type: rel, evidence };
    }
    return { source: a, target: b, relation_type: rel, evidence };
  }

  return null;
}

function parseIntent(
  raw: string,
  selectedNodeId: string | null,
  defaultMaxHops: number
): GraphAskIntent | { error: string } {
  const input = String(raw || '').trim();
  if (!input) return { error: 'Digite uma pergunta para consultar o grafo.' };

  const lower = input.toLowerCase();

  // Natural language write intent (no slash command):
  // "Conecte X com Y via REL" / "Crie aresta entre X e Y via REL" etc.
  const nlLink = parseNaturalLinkIntent(input);
  if (nlLink) {
    const dim = inferDimension(nlLink.relation_type);
    return {
      operation: 'link_entities',
      params: {
        source: nlLink.source,
        target: nlLink.target,
        relation_type: nlLink.relation_type,
        ...(nlLink.evidence ? { evidence: nlLink.evidence } : {}),
        ...(dim ? { dimension: dim } : {}),
      },
    };
  }

  const commandMatch = input.match(/^\/?([a-zA-Z_-]+)\s*(.*)$/);
  const command = String(commandMatch?.[1] || '').toLowerCase();
  const rest = String(commandMatch?.[2] || '').trim();

  if (['diagnostics', 'diag', 'legal_diagnostics', 'relatorio', 'report'].includes(command)) {
    return { operation: 'legal_diagnostics', params: {} };
  }

  if (['comenciona', 'co_menciona', 'comentions', 'comencoes', 'cooc_build'].includes(command)) {
    // Usage:
    //   /comenciona
    //   /comenciona 2 20000
    //   /comenciona min=2 max=20000
    let min = 2;
    let maxPairs = 20000;

    const minMatch = rest.match(/\\bmin\\s*=\\s*(\\d+)\\b/i);
    const maxMatch = rest.match(/\\bmax\\s*=\\s*(\\d+)\\b/i);
    if (minMatch) min = Number(minMatch[1] || 2);
    if (maxMatch) maxPairs = Number(maxMatch[1] || 20000);

    const nums = rest
      .split(/\\s+/)
      .map((t) => Number(t))
      .filter((n) => Number.isFinite(n));
    if (nums.length >= 1 && !minMatch) min = nums[0] as number;
    if (nums.length >= 2 && !maxMatch) maxPairs = nums[1] as number;

    return {
      operation: 'recompute_co_menciona',
      params: { min_cooccurrences: min, max_pairs: maxPairs },
    };
  }

  if (['path', 'caminho'].includes(command)) {
    const arrowParts = rest.split('->').map((s) => s.trim()).filter(Boolean);
    let sourceId = '';
    let targetId = '';
    if (arrowParts.length >= 2) {
      sourceId = arrowParts[0];
      targetId = arrowParts[1];
    } else {
      const parts = rest.split(/\s+/).filter(Boolean);
      sourceId = parts[0] || selectedNodeId || '';
      targetId = parts[1] || '';
    }
    if (!sourceId || !targetId) {
      return { error: 'Use: `/path origem destino` (ou `/path origem->destino`).' };
    }
    return {
      operation: 'path',
      params: {
        source_id: sourceId,
        target_id: targetId,
        max_hops: clampGraphHops(defaultMaxHops),
        limit: 5,
      },
    };
  }

  if (['neighbors', 'neighbor', 'vizinhos', 'vizinhos'].includes(command)) {
    const entityId = rest.split(/\s+/).filter(Boolean)[0] || selectedNodeId || '';
    if (!entityId) {
      return { error: 'Use: `/neighbors entity_id` (ou selecione um nó antes).' };
    }
    return { operation: 'neighbors', params: { entity_id: entityId, limit: 20 } };
  }

  if (['cooccur', 'cooccurrence', 'coocorrencia', 'co-ocorrencia'].includes(command)) {
    const parts = rest.split(/\s+/).filter(Boolean);
    if (parts.length < 2) {
      return { error: 'Use: `/cooccur entity_id_1 entity_id_2`.' };
    }
    return { operation: 'cooccurrence', params: { entity1_id: parts[0], entity2_id: parts[1] } };
  }

  if (['count', 'contar'].includes(command)) {
    const parts = rest.split(/\s+/).filter(Boolean);
    const first = String(parts[0] || '').toLowerCase();
    if (!first) return { operation: 'count', params: {} };
    if (ENTITY_TYPES.has(first)) {
      return {
        operation: 'count',
        params: {
          entity_type: first,
          query: parts.slice(1).join(' ') || null,
        },
      };
    }
    return { operation: 'count', params: { query: rest } };
  }

  if (['search', 'buscar', 'busca'].includes(command)) {
    if (!rest) return { error: 'Use: `/search termo`.' };
    return { operation: 'search', params: { query: rest, limit: 30 } };
  }

  if (['link', 'conectar', 'connect', 'aresta', 'edge'].includes(command)) {
    if (!rest) {
      return {
        error:
          'Use: `/link origem destino via RELACAO` ou `/link origem -> destino via RELACAO`. ' +
          'Origem/destino podem ser entity_id (ex: art_5_cf) ou texto (ex: "Art. 5 CF").',
      };
    }

    // Parse "... -> ..." form first (allows spaces). Relation is best specified using "via".
    const arrow = rest.split('->');
    let left = '';
    let right = '';
    if (arrow.length >= 2) {
      left = arrow[0].trim();
      right = arrow.slice(1).join('->').trim();
    } else {
      const parts = rest.split(/\s+/).filter(Boolean);
      left = parts[0] || '';
      right = parts[1] || '';
      const tail = parts.slice(2).join(' ');
      if (tail) right = `${right} ${tail}`.trim();
    }

    if (!left || !right) {
      return { error: 'Use: `/link origem destino via RELACAO` (ou com `->`).' };
    }

    const viaMatch = right.match(/\bvia\s+([A-Za-z][A-Za-z0-9_]{0,40})\s*$/i);
    const relationType = String(viaMatch?.[1] || 'RELATED_TO').toUpperCase();
    if (viaMatch) {
      right = right.slice(0, viaMatch.index).trim();
    }

    // Optional: evidence snippet (quoted)
    let evidence: string | null = null;
    const evMatch = right.match(/\b(ev|evidence|trecho)\b\s*:?[\s]*\"([^\"]{3,400})\"\s*$/i);
    if (evMatch) {
      evidence = String(evMatch[2] || '').trim();
      right = right.slice(0, evMatch.index).trim();
    }

    left = stripOuterQuotes(left);
    right = stripOuterQuotes(right);

    const dim = inferDimension(relationType);
    return {
      operation: 'link_entities',
      // NOTE: this intent may carry refs (query or entity_id). We resolve before calling the API.
      params: {
        source: left,
        target: right,
        relation_type: relationType,
        ...(evidence ? { evidence } : {}),
        ...(dim ? { dimension: dim } : {}),
      },
    };
  }

  if (/\b(vizinh|relacionad|conex)\w*/.test(lower) && selectedNodeId) {
    return { operation: 'neighbors', params: { entity_id: selectedNodeId, limit: 20 } };
  }

  return { operation: 'search', params: { query: input, limit: 30 } };
}

function extractEntities(operation: string, results: Array<Record<string, any>>) {
  if (!Array.isArray(results) || results.length === 0) return [] as Array<{ id: string; name: string }>;

  if (operation === 'path') {
    const first = results[0];
    const ids = Array.isArray(first?.path_ids) ? first.path_ids : [];
    const labels = Array.isArray(first?.path) ? first.path : [];
    return ids
      .map((id: string, idx: number) => ({ id, name: String(labels[idx] || id) }))
      .filter((item: { id: string; name: string }) => !!item.id);
  }

  if (operation === 'link_entities') {
    const first = results[0] || {};
    const src = String(first?.source_id || '').trim();
    const tgt = String(first?.target_id || '').trim();
    const rel = String(first?.relation_type || '').trim();
    const out: Array<{ id: string; name: string }> = [];
    if (src) out.push({ id: src, name: src });
    if (tgt) out.push({ id: tgt, name: tgt });
    if (rel) out.push({ id: rel, name: rel });
    return out;
  }

  return results
    .map((row) => {
      const id = String(row?.entity_id || row?.id || '').trim();
      if (!id) return null;
      const name = String(row?.name || row?.normalized || id);
      return { id, name };
    })
    .filter(Boolean) as Array<{ id: string; name: string }>;
}

function formatResponse(
  operation: string,
  results: Array<Record<string, any>>,
  executionTimeMs: number,
  success: boolean,
  error?: string | null
) {
  if (!success) {
    return `Nao foi possivel consultar o grafo: ${error || 'erro desconhecido'}.`;
  }

  if (!Array.isArray(results) || results.length === 0) {
    return `Nenhum resultado encontrado para \`${operation}\`.`;
  }

  if (operation === 'path') {
    const first = results[0];
    const pathNames = Array.isArray(first?.path) ? first.path : [];
    const rels = Array.isArray(first?.relationships) ? first.relationships : [];
    const hops = Number(first?.hops ?? rels.length ?? 0);
    const chain = pathNames.length ? pathNames.join(' -> ') : 'Caminho encontrado';
    return `Caminho encontrado (${hops} hops):\n${chain}\nRelacoes: ${rels.join(', ') || '-' }\nTempo: ${executionTimeMs}ms`;
  }

  if (operation === 'neighbors') {
    const lines = results.slice(0, 8).map((r, i) => {
      const name = String(r?.name || r?.entity_id || 'entidade');
      const co = Number(r?.co_occurrences || 0);
      return `${i + 1}. ${name} (co-ocorrencias: ${co})`;
    });
    return `Principais vizinhos:\n${lines.join('\n')}\nTempo: ${executionTimeMs}ms`;
  }

  if (operation === 'cooccurrence') {
    const first = results[0];
    const e1 = String(first?.entity1_name || '-');
    const e2 = String(first?.entity2_name || '-');
    const count = Number(first?.co_occurrence_count || 0);
    const docs = Array.isArray(first?.documents) ? first.documents.slice(0, 3) : [];
    const docsText = docs.length ? `\nDocs: ${docs.join(', ')}` : '';
    return `Co-ocorrencia entre ${e1} e ${e2}: ${count}.${docsText}\nTempo: ${executionTimeMs}ms`;
  }

  if (operation === 'count') {
    const first = results[0];
    const entities = Number(first?.entity_count || 0);
    const refs = Number(first?.total_document_references || 0);
    return `Contagem:\n- Entidades: ${entities}\n- Referencias em documentos: ${refs}\nTempo: ${executionTimeMs}ms`;
  }

  if (operation === 'legal_diagnostics') {
    const first = results[0] || {};
    const components = (first?.components && typeof first.components === 'object') ? first.components : {};
    const remTotal = Number(first?.remissoes_art_art_total || 0);
    const remCross = Number(first?.remissoes_cross_law_total || 0);
    const top = Array.isArray(first?.remissoes_top) ? first.remissoes_top : [];
    const topLines = top.slice(0, 8).map((r: any, i: number) => {
      const origem = String(r?.origem || '-');
      const destino = String(r?.destino || '-');
      const c = Number(r?.c || 0);
      const ev = String(r?.evidence || '').trim();
      const evPart = ev ? ` | ev: "${ev}"` : '';
      return `${i + 1}. ${origem} -> ${destino} (c=${c})${evPart}`;
    });

    const chains3 = Number(first?.cadeias_3_hops_total || 0);
    const chainCounts = (first?.chain_counts_4_5_hops && typeof first.chain_counts_4_5_hops === 'object')
      ? first.chain_counts_4_5_hops
      : {};

    const chainLines = Object.entries(chainCounts).slice(0, 8).map(([k, v]) => `- ${k}: ${Number(v || 0)}`);
    const parts: string[] = [];
    parts.push('Diagnostico do grafo (legal_diagnostics):');
    parts.push(`- Nos: Artigo=${Number((components as any)?.Artigo || 0)}, Lei=${Number((components as any)?.Lei || 0)}, Sumula=${Number((components as any)?.Sumula || 0)}, Decisao=${Number((components as any)?.Decisao || 0)}, Tese=${Number((components as any)?.Tese || 0)}`);
    parts.push(`- REMETE_A Art->Art: ${remTotal} (cross-law: ${remCross})`);
    parts.push(`- Cadeias 3 hops (Art->Art->Art): ${chains3}`);
    if (topLines.length) {
      parts.push('\nTop remissoes:');
      parts.push(topLines.join('\n'));
    }
    if (chainLines.length) {
      parts.push('\nCadeias 4-5 hops (contagens):');
      parts.push(chainLines.join('\n'));
    }
    parts.push(`\nTempo: ${executionTimeMs}ms`);
    return parts.join('\n');
  }

  if (operation === 'link_entities') {
    const first = results[0] || {};
    const src = String(first?.source_id || '-');
    const tgt = String(first?.target_id || '-');
    const rel = String(first?.relation_type || 'RELATED_TO');
    return `Aresta criada/atualizada:\n- ${src} -[${rel}]-> ${tgt}\nTempo: ${executionTimeMs}ms`;
  }

  if (operation === 'recompute_co_menciona') {
    const first = results[0] || {};
    const edges = Number(first?.edges || 0);
    const minCo = Number(first?.min_cooccurrences || 0);
    const maxPairs = Number(first?.max_pairs || 0);
    const includeGlobal = Boolean(first?.include_global);
    return (
      `CO_MENCIONA (candidate) recomputado:\n` +
      `- edges: ${edges}\n` +
      `- min_cooccurrences: ${minCo}\n` +
      `- max_pairs: ${maxPairs}\n` +
      `- include_global: ${includeGlobal}\n` +
      `Tempo: ${executionTimeMs}ms`
    );
  }

  const lines = results.slice(0, 10).map((r, i) => {
    const name = String(r?.name || r?.entity_id || r?.normalized || 'entidade');
    const type = String(r?.type || r?.entity_type || 'n/a');
    const mentions = Number(r?.mention_count || 0);
    return `${i + 1}. ${name} [${type}] (mencoes: ${mentions})`;
  });
  return `Resultados de busca:\n${lines.join('\n')}\nTempo: ${executionTimeMs}ms`;
}

async function callGraphAsk(payload: {
  operation: GraphAskOperation;
  params: Record<string, any>;
  include_global?: boolean;
}) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const response = await fetch(`${apiBaseUrl}/graph/ask`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const data = await response.json();
      message = String(data?.detail || data?.error || message);
    } catch {
      // ignore parse errors
    }
    throw new Error(message);
  }

  return (await response.json()) as {
    success: boolean;
    operation: string;
    results: Array<Record<string, any>>;
    result_count: number;
    execution_time_ms: number;
    error?: string | null;
  };
}

async function callGraphText2Cypher(payload: { question: string; include_global?: boolean }) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const includeGlobal = payload.include_global !== false;
  const response = await fetch(
    `${apiBaseUrl}/graph/ask/text2cypher?include_global=${includeGlobal ? 'true' : 'false'}`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ question: payload.question }),
    }
  );

  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const data = await response.json();
      message = String(data?.detail || data?.error || message);
    } catch {
      // ignore parse errors
    }
    throw new Error(message);
  }

  return (await response.json()) as {
    success: boolean;
    operation: string;
    results: Array<Record<string, any>>;
    result_count: number;
    execution_time_ms: number;
    error?: string | null;
    cypher_template?: string | null;
    metadata?: Record<string, any> | null;
  };
}

interface GraphAuraAgentChatProps {
  selectedNodeId?: string | null;
  onNavigateToNode?: (nodeId: string) => void;
  defaultMaxHops?: number;
  onMaxHopsChange?: (hops: number) => void;
}

export function GraphAuraAgentChat({
  selectedNodeId = null,
  onNavigateToNode,
  defaultMaxHops = 3,
  onMaxHopsChange,
}: GraphAuraAgentChatProps) {
  const [isOpen, setIsOpen] = useState(true);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [pendingWriteId, setPendingWriteId] = useState<string | null>(null);
  const [maxHops, setMaxHops] = useState(() => clampGraphHops(defaultMaxHops));
  const [llmMode, setLlmMode] = useState<boolean>(() => {
    try {
      return localStorage.getItem('iudex_graph_llm_mode') === '1';
    } catch {
      return false;
    }
  });
  const [llmChatId, setLlmChatId] = useState<string | null>(() => {
    try {
      return localStorage.getItem('iudex_graph_llm_chat_id') || null;
    } catch {
      return null;
    }
  });
  const [messages, setMessages] = useState<GraphChatMessage[]>([
    {
      id: makeId('assistant'),
        role: 'assistant',
        content:
        'Aura Agent pronto. Use linguagem natural (busca) ou comandos: /search, /neighbors, /path, /cooccur, /count, /link, /comenciona, /t2c, /risk.\n' +
        'Dica (arestas): "Sumula 473 STF interpreta Art. 5 CF" ou "Art. 135 CTN remete a Art. 50 CC".\n' +
        'Modo LLM (opcional): ligue o toggle para respostas em linguagem natural com GraphRAG.',
    },
  ]);
  const messagesBottomRef = useRef<HTMLDivElement>(null);

  const selectedNodeBadge = useMemo(
    () => (selectedNodeId ? `Nó selecionado: ${selectedNodeId}` : 'Nenhum nó selecionado'),
    [selectedNodeId]
  );

  useEffect(() => {
    messagesBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(() => {
    setMaxHops(clampGraphHops(defaultMaxHops));
  }, [defaultMaxHops]);

  const pushAssistant = (content: string, operation?: GraphAskOperation, entities?: Array<{ id: string; name: string }>) => {
    setMessages((prev) => [
      ...prev,
      {
        id: makeId('assistant'),
        role: 'assistant',
        content,
        operation,
        entities,
      },
    ]);
  };

  const pushAssistantPendingLink = (payload: {
    content: string;
    pendingLink: NonNullable<GraphChatMessage['pendingLink']>;
  }) => {
    setMessages((prev) => [
      ...prev,
      {
        id: makeId('assistant'),
        role: 'assistant',
        content: payload.content,
        operation: 'link_entities',
        pendingLink: payload.pendingLink,
      },
    ]);
  };

  const ensureLlmChatId = async () => {
    if (llmChatId) return llmChatId;
    const created = await callCreateChat({
      title: 'Graph LLM',
      mode: 'CHAT',
      context: { graph_rag_enabled: true, source: 'graph_page' },
    });
    const id = String(created?.id || '').trim();
    if (id) {
      setLlmChatId(id);
      try {
        localStorage.setItem('iudex_graph_llm_chat_id', id);
      } catch {
        // ignore
      }
    }
    return id;
  };

  const updateAssistantMessage = (messageId: string, patch: Partial<GraphChatMessage>) => {
    setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, ...patch } : m)));
  };

  const appendAssistantDelta = (messageId: string, delta: string) => {
    if (!delta) return;
    setMessages((prev) =>
      prev.map((m) => (m.id === messageId ? { ...m, content: `${m.content || ''}${delta}` } : m))
    );
  };

  const confirmPendingLink = async (messageId: string) => {
    const msg = messages.find((m) => m.id === messageId);
    const pending = msg?.pendingLink;
    if (!pending) return;

    setPendingWriteId(messageId);
    try {
      const props = { ...(pending.properties || {}) };
      const response = await callGraphAsk({
        operation: 'link_entities',
        params: {
          source_id: pending.source.id,
          target_id: pending.target.id,
          relation_type: pending.relation_type,
          confirm: true,
          ...(pending.preflight_token ? { preflight_token: pending.preflight_token } : {}),
          ...(Object.keys(props).length ? { properties: props } : {}),
        },
        include_global: true,
      });
      const entities = extractEntities(response.operation, response.results);
      const formatted = formatResponse(
        response.operation,
        response.results,
        response.execution_time_ms,
        response.success,
        response.error
      );
      updateAssistantMessage(messageId, {
        content: formatted,
        operation: 'link_entities',
        entities,
        pendingLink: undefined,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erro desconhecido';
      updateAssistantMessage(messageId, {
        content: `Falha ao escrever no grafo: ${message}`,
        pendingLink: undefined,
      });
    } finally {
      setPendingWriteId(null);
    }
  };

  const cancelPendingLink = (messageId: string) => {
    updateAssistantMessage(messageId, {
      content: 'Operacao cancelada. Nenhuma aresta foi escrita.',
      pendingLink: undefined,
    });
  };

  const handleSend = async () => {
    const content = input.trim();
    if (!content || loading) return;

    setMessages((prev) => [
      ...prev,
      { id: makeId('user'), role: 'user', content },
    ]);
    setInput('');

    // /t2c is a separate endpoint (graph/ask/text2cypher) and is not part of GraphAskOperation.
    const t2cMatch = content.match(/^\/?(t2c|text2cypher)\s+(.+)$/i);
    const t2cQuestion = String(t2cMatch?.[2] || '').trim();

    // Shortcut: open the dedicated Risk & Audit page.
    if (/^\/?risk\b/i.test(content)) {
      pushAssistant('Abrindo /graph/risk ...');
      try {
        window.location.href = '/graph/risk';
      } catch {
        // ignore
      }
      return;
    }

    const intent = t2cQuestion ? null : parseIntent(content, selectedNodeId || null, maxHops);
    if (intent && 'error' in intent) {
      pushAssistant(intent.error);
      return;
    }

    setLoading(true);
    try {
      if (t2cQuestion) {
        const response = await callGraphText2Cypher({ question: t2cQuestion, include_global: true });
        const entities = extractEntities(response.operation, response.results);
        const formatted = formatResponse(
          response.operation,
          response.results,
          response.execution_time_ms,
          response.success,
          response.error
        );
        // Render as a normal assistant message. Operation label is informational.
        pushAssistant(formatted, 'search', entities);
        return;
      }

      // Special handling for /link: resolve refs via search before calling link_entities.
      if (intent && intent.operation === 'link_entities') {
        const sourceRef = String(intent.params?.source || intent.params?.source_id || '').trim();
        const targetRef = String(intent.params?.target || intent.params?.target_id || '').trim();
        const relationType = String(intent.params?.relation_type || 'RELATED_TO').trim().toUpperCase();
        const evidence = String(intent.params?.evidence || '').trim();
        const dimension = String(intent.params?.dimension || '').trim();

        const resolveOne = async (ref: string) => {
          if (!ref) return null;
          if (looksLikeEntityId(ref)) return { id: ref, name: ref };
          const sr = await callGraphAsk({ operation: 'search', params: { query: ref, limit: 5 }, include_global: true });
          if (!sr.success || !Array.isArray(sr.results) || sr.results.length === 0) {
            pushAssistant(`Nao encontrei entidade para: "${ref}". Tente /search "${ref}" e use o entity_id retornado.`);
            return null;
          }
          if (sr.results.length > 1) {
            const lines = sr.results.slice(0, 5).map((r, i) => {
              const id = String(r?.entity_id || '-');
              const name = String(r?.name || r?.normalized || id);
              const t = String(r?.type || r?.entity_type || '');
              const suffix = t ? ` [${t}]` : '';
              return `${i + 1}. ${id}${suffix} - ${name}`;
            });
            pushAssistant(
              `Ambiguo para "${ref}". Escolha um entity_id e rode:\n` +
                `  /link <source_id> <target_id> via ${relationType}\n\n` +
                `Candidatos:\n${lines.join('\n')}`
            );
            return null;
          }
          const only = sr.results[0] || {};
          const id = String(only?.entity_id || '').trim();
          const name = String(only?.name || only?.normalized || id);
          if (!id) return null;
          return { id, name };
        };

        const src = await resolveOne(sourceRef);
        if (!src) return;
        const tgt = await resolveOne(targetRef);
        if (!tgt) return;

        const props: Record<string, any> = {};
        if (dimension) props.dimension = dimension;
        if (evidence) props.evidence = evidence.slice(0, 200);

        // Ask server for a cryptographically binding preflight_token (no write yet).
        let preflightToken = '';
        try {
          const pre = await callGraphAsk({
            operation: 'link_entities',
            params: {
              source_id: src.id,
              target_id: tgt.id,
              relation_type: relationType,
              ...(Object.keys(props).length ? { properties: props } : {}),
              // confirm omitted/false => preflight
            },
            include_global: true,
          });
          preflightToken = String(pre?.results?.[0]?.preflight_token || '').trim();
        } catch {
          // If preflight fails, we still show the preview but confirmation will likely fail.
          preflightToken = '';
        }

        const lines: string[] = [];
        lines.push('Confirmar escrita no grafo?');
        lines.push('');
        lines.push(`- source: ${src.id} (${src.name})`);
        lines.push(`- rel: ${relationType}${dimension ? ` [dim=${dimension}]` : ''}`);
        lines.push(`- target: ${tgt.id} (${tgt.name})`);
        if (evidence) lines.push(`- evidence: "${evidence.slice(0, 160)}"`);
        lines.push('');
        lines.push('Clique em Confirmar para gravar (ou Cancelar).');

        pushAssistantPendingLink({
          content: lines.join('\n'),
          pendingLink: {
            source: src,
            target: tgt,
            relation_type: relationType,
            properties: Object.keys(props).length ? props : undefined,
            preflight_token: preflightToken || undefined,
            raw: content,
          },
        });
        return;
      }

      // LLM mode: for non-command messages, use chat streaming (GraphRAG) instead of fixed typed calls.
      if (llmMode && !content.startsWith('/')) {
        const chatId = await ensureLlmChatId();
        if (!chatId) {
          pushAssistant('Falha ao iniciar chat LLM (chat_id vazio).');
          return;
        }

        const assistantId = makeId('assistant');
        setMessages((prev) => [...prev, { id: assistantId, role: 'assistant', content: '' }]);

        await callChatStream({
          chatId,
          content,
          graphHops: maxHops,
          onToken: (delta) => appendAssistantDelta(assistantId, delta),
          onDone: (fullText) => {
            if (typeof fullText === 'string' && fullText.trim()) {
              updateAssistantMessage(assistantId, { content: fullText });
            }
          },
          onError: (message) => {
            const lower = String(message || '').toLowerCase();
            const looksLikeAgentGated =
              lower.includes('rollout') ||
              lower.includes('canário') ||
              lower.includes('canario') ||
              lower.includes('kill switch') ||
              lower.includes('fora da amostra') ||
              lower.includes('agentic') ||
              lower.includes('modelo') && lower.includes('não suportado') ||
              lower.includes('nao suportado');
            if (looksLikeAgentGated) {
              updateAssistantMessage(assistantId, {
                content:
                  'Modo LLM (ferramentas do grafo) indisponivel neste ambiente/tenant. ' +
                  'Use os comandos: /search, /neighbors, /path, /cooccur, /count (e /risk).',
              });
              return;
            }
            updateAssistantMessage(assistantId, { content: `Falha no modo LLM: ${message}` });
          },
        });
        return;
      }

      const response = await callGraphAsk({ operation: intent!.operation, params: intent!.params, include_global: true });
      const entities = extractEntities(response.operation, response.results);
      const formatted = formatResponse(
        response.operation,
        response.results,
        response.execution_time_ms,
        response.success,
        response.error
      );
      pushAssistant(formatted, intent!.operation, entities);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Erro desconhecido';
      pushAssistant(`Falha ao consultar o Neo4j Aura Agent: ${message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleInputKeyDown: React.KeyboardEventHandler<HTMLInputElement> = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  };

  if (!isOpen) {
    return (
      <div className="fixed bottom-5 right-5 z-50">
        <Button className="rounded-full shadow-lg" onClick={() => setIsOpen(true)}>
          <MessageSquare className="mr-2 h-4 w-4" />
          Aura Agent
        </Button>
      </div>
    );
  }

  return (
    <div className="fixed bottom-5 right-5 z-50 w-[380px] max-w-[92vw]">
      <Card className="shadow-2xl border-slate-200">
        <CardHeader className="pb-2 border-b">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm flex items-center gap-2">
              <Bot className="h-4 w-4 text-blue-600" />
              Neo4j Aura Agent
            </CardTitle>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant={llmMode ? 'default' : 'outline'}
                className={cn('h-7 px-2 text-[11px]', llmMode ? 'bg-blue-600 hover:bg-blue-700' : '')}
                onClick={() => {
                  const next = !llmMode;
                  setLlmMode(next);
                  try {
                    localStorage.setItem('iudex_graph_llm_mode', next ? '1' : '0');
                  } catch {
                    // ignore
                  }
                }}
                title="Liga/desliga respostas por LLM (GraphRAG)"
              >
                {llmMode ? 'LLM: ON' : 'LLM: OFF'}
              </Button>
              <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => setIsOpen(false)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <Badge variant="outline" className="w-fit text-[10px] font-normal">
            {selectedNodeBadge}
          </Badge>
        </CardHeader>
        <CardContent className="p-0">
          <ScrollArea className="h-[360px] px-3 py-3">
            <div className="space-y-3">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={cn(
                    'rounded-lg px-3 py-2 text-xs whitespace-pre-wrap',
                    message.role === 'user'
                      ? 'ml-10 bg-slate-900 text-white'
                      : 'mr-10 bg-slate-100 text-slate-800'
                  )}
                >
                  <div className="font-semibold mb-1">
                    {message.role === 'user' ? 'Você' : 'Aura'}
                  </div>
                  <div>{message.content}</div>
                  {message.role === 'assistant' && message.pendingLink && (
                    <div className="mt-2 flex items-center gap-2">
                      <Button
                        type="button"
                        size="sm"
                        className="h-7 px-2 text-[11px] bg-blue-600 hover:bg-blue-700"
                        onClick={() => void confirmPendingLink(message.id)}
                        disabled={!!pendingWriteId && pendingWriteId !== message.id}
                        title="Confirma e grava a aresta via link_entities"
                      >
                        {pendingWriteId === message.id ? (
                          <>
                            <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
                            Gravando...
                          </>
                        ) : (
                          'Confirmar'
                        )}
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="h-7 px-2 text-[11px]"
                        onClick={() => cancelPendingLink(message.id)}
                        disabled={pendingWriteId === message.id}
                      >
                        Cancelar
                      </Button>
                    </div>
                  )}
                  {message.entities && message.entities.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {message.entities.slice(0, 8).map((entity) => (
                        <Button
                          key={`${message.id}-${entity.id}`}
                          type="button"
                          size="sm"
                          variant="outline"
                          className="h-6 px-2 text-[10px]"
                          onClick={() => onNavigateToNode?.(entity.id)}
                        >
                          {entity.name}
                        </Button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {loading && (
                <div className="mr-10 rounded-lg bg-slate-100 text-slate-700 px-3 py-2 text-xs flex items-center gap-2">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Consultando o grafo...
                </div>
              )}
              <div ref={messagesBottomRef} />
            </div>
          </ScrollArea>

          <div className="border-t p-3 space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-muted-foreground">Hops</span>
              <select
                className="h-7 rounded border border-slate-200 bg-white px-1.5 text-xs"
                value={maxHops}
                onChange={(event) => {
                  const next = clampGraphHops(Number(event.target.value));
                  setMaxHops(next);
                  onMaxHopsChange?.(next);
                }}
                disabled={loading}
              >
                {[1, 2, 3, 4, 5].map((hop) => (
                  <option key={hop} value={hop}>
                    {hop}
                  </option>
                ))}
              </select>
              <span className="text-[10px] text-muted-foreground">/path usa este valor</span>
            </div>
            <Input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleInputKeyDown}
              placeholder="Pergunte ao grafo (ex: /neighbors lei_8666)"
              disabled={loading}
            />
            <div className="flex items-center justify-between gap-2">
              <p className="text-[10px] text-muted-foreground truncate">
                /search termo | /neighbors id | /path id1 id2 | /cooccur id1 id2 | /count [tipo] | /comenciona | /risk
              </p>
              <Button size="sm" onClick={() => void handleSend()} disabled={!input.trim() || loading}>
                <Send className="h-3.5 w-3.5 mr-1.5" />
                Enviar
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
