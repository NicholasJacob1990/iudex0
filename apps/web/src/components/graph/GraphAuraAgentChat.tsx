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

type GraphAskOperation = 'path' | 'neighbors' | 'cooccurrence' | 'search' | 'count';

type GraphChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  operation?: GraphAskOperation;
  entities?: Array<{ id: string; name: string }>;
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

function parseIntent(raw: string, selectedNodeId: string | null): GraphAskIntent | { error: string } {
  const input = String(raw || '').trim();
  if (!input) return { error: 'Digite uma pergunta para consultar o grafo.' };

  const lower = input.toLowerCase();
  const commandMatch = input.match(/^\/?([a-zA-Z_-]+)\s*(.*)$/);
  const command = String(commandMatch?.[1] || '').toLowerCase();
  const rest = String(commandMatch?.[2] || '').trim();

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
    return { operation: 'path', params: { source_id: sourceId, target_id: targetId, max_hops: 4, limit: 5 } };
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

interface GraphAuraAgentChatProps {
  selectedNodeId?: string | null;
  onNavigateToNode?: (nodeId: string) => void;
}

export function GraphAuraAgentChat({
  selectedNodeId = null,
  onNavigateToNode,
}: GraphAuraAgentChatProps) {
  const [isOpen, setIsOpen] = useState(true);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<GraphChatMessage[]>([
    {
      id: makeId('assistant'),
      role: 'assistant',
      content:
        'Aura Agent pronto. Use linguagem natural (busca) ou comandos: /search, /neighbors, /path, /cooccur, /count.',
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

  const handleSend = async () => {
    const content = input.trim();
    if (!content || loading) return;

    setMessages((prev) => [
      ...prev,
      { id: makeId('user'), role: 'user', content },
    ]);
    setInput('');

    const intent = parseIntent(content, selectedNodeId || null);
    if ('error' in intent) {
      pushAssistant(intent.error);
      return;
    }

    setLoading(true);
    try {
      const response = await callGraphAsk({
        operation: intent.operation,
        params: intent.params,
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
      pushAssistant(formatted, intent.operation, entities);
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
            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => setIsOpen(false)}>
              <X className="h-4 w-4" />
            </Button>
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
            <Input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleInputKeyDown}
              placeholder="Pergunte ao grafo (ex: /neighbors lei_8666)"
              disabled={loading}
            />
            <div className="flex items-center justify-between gap-2">
              <p className="text-[10px] text-muted-foreground truncate">
                /search termo | /neighbors id | /path id1 id2 | /cooccur id1 id2 | /count [tipo]
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
