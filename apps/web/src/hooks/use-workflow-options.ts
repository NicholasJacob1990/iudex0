'use client';

import { useState, useEffect, useCallback } from 'react';
import { MODEL_REGISTRY } from '@/config/models';

export interface ToolOption {
  value: string;
  label: string;
  description: string;
  category: string;
  source: 'gateway' | 'builtin';
}

export interface ModelOption {
  value: string;
  label: string;
  provider: string;
}

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: 'Anthropic',
  openai: 'OpenAI',
  google: 'Google',
  xai: 'xAI',
  perplexity: 'Perplexity',
  openrouter: 'Meta / OpenRouter',
};

const ALL_PROVIDERS = ['anthropic', 'openai', 'google', 'xai', 'perplexity', 'openrouter'] as const;

// Build model options once from the registry
const MODEL_OPTIONS: ModelOption[] = Object.values(MODEL_REGISTRY)
  .filter((m) => m.id !== 'internal-rag')
  .map((m) => ({ value: m.id, label: m.label, provider: m.provider }));

const MODEL_OPTIONS_BY_PROVIDER = ALL_PROVIDERS.map((provider) => ({
  provider,
  label: PROVIDER_LABELS[provider] || provider,
  models: MODEL_OPTIONS.filter((m) => m.provider === provider),
})).filter((g) => g.models.length > 0);

// Builtin SDK tools that may not come from the gateway endpoint
const BUILTIN_SDK_TOOLS: ToolOption[] = [
  { value: 'web_search', label: 'Web Search', description: 'Pesquisa na web com Perplexity/Serper/DuckDuckGo', category: 'SEARCH', source: 'builtin' },
  { value: 'search_jurisprudencia', label: 'Pesquisa Jurisprudência', description: 'Busca jurisprudência em STF, STJ, TRFs e TJs', category: 'LEGAL', source: 'builtin' },
  { value: 'search_legislacao', label: 'Pesquisa Legislação', description: 'Busca leis, decretos e normas vigentes', category: 'LEGAL', source: 'builtin' },
  { value: 'search_rag', label: 'RAG Search', description: 'Busca em bases de conhecimento indexadas (Qdrant + OpenSearch)', category: 'RAG', source: 'builtin' },
  { value: 'verify_citation', label: 'Verificar Citação', description: 'Valida referência jurídica contra fontes oficiais', category: 'LEGAL', source: 'builtin' },
  { value: 'search_jusbrasil', label: 'JusBrasil Search', description: 'Busca no JusBrasil por jurisprudência e notícias jurídicas', category: 'LEGAL', source: 'builtin' },
  { value: 'validate_cpc_compliance', label: 'Validação CPC', description: 'Valida conformidade processual com o CPC', category: 'LEGAL', source: 'builtin' },
  { value: 'ask_graph', label: 'Grafo Jurídico (ask_graph)', description: 'Consulta tipada ao grafo (inclui GDS: PageRank, community detection, centralidade, etc.)', category: 'GRAPH', source: 'builtin' },
  { value: 'scan_graph_risk', label: 'Graph Risk Scan', description: 'Varredura de risco/fraude no grafo (/graph/risk/scan)', category: 'GRAPH', source: 'builtin' },
  { value: 'audit_graph_edge', label: 'Graph Risk Audit Edge', description: 'Auditoria de aresta/sinal no grafo', category: 'GRAPH', source: 'builtin' },
  { value: 'audit_graph_chain', label: 'Graph Risk Audit Chain', description: 'Auditoria de cadeia de sinais no grafo', category: 'GRAPH', source: 'builtin' },
  { value: 'delegate_subtask', label: 'Delegar Subtarefa', description: 'Delega tarefa a sub-agente especializado', category: 'AGENT', source: 'builtin' },
  { value: 'run_workflow', label: 'Executar Workflow', description: 'Executa um sub-workflow dentro do agente', category: 'AGENT', source: 'builtin' },
  { value: 'consultar_processo_datajud', label: 'DataJud (CNJ)', description: 'Consulta processo no DataJud/CNJ', category: 'DATAJUD', source: 'builtin' },
  { value: 'buscar_publicacoes_djen', label: 'DJEN (Diário)', description: 'Busca publicações no Diário de Justiça Eletrônico', category: 'DATAJUD', source: 'builtin' },
  { value: 'consultar_processo_pje', label: 'PJe', description: 'Consulta processo no PJe', category: 'TRIBUNAIS', source: 'builtin' },
  { value: 'consultar_processo_eproc', label: 'e-Proc', description: 'Consulta processo no e-Proc (TRF4)', category: 'TRIBUNAIS', source: 'builtin' },
  { value: 'legal_research', label: 'Pesquisa Legal (RAG)', description: 'Pesquisa completa com RAG + web + jurisprudência', category: 'LEGAL', source: 'builtin' },
  { value: 'edit_document', label: 'Editar Documento', description: 'Edita seções de documento jurídico', category: 'DOCUMENT', source: 'builtin' },
  { value: 'read_document', label: 'Ler Documento', description: 'Lê conteúdo de documento enviado', category: 'DOCUMENT', source: 'builtin' },
];

// Cache tools globally so we only fetch once
let toolsCache: ToolOption[] | null = null;
let gatewayToolsCache: ToolOption[] | null = null;
let toolsFetchPromise: Promise<ToolOption[]> | null = null;

function mergeWithBuiltins(apiTools: ToolOption[]): ToolOption[] {
  const seen = new Set(apiTools.map((t) => t.value));
  const merged = [...apiTools];
  for (const builtin of BUILTIN_SDK_TOOLS) {
    if (!seen.has(builtin.value)) {
      merged.push(builtin);
    }
  }
  return merged;
}

async function fetchTools(): Promise<ToolOption[]> {
  if (toolsCache) return toolsCache;
  if (toolsFetchPromise) return toolsFetchPromise;

  toolsFetchPromise = (async () => {
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const token = typeof window !== 'undefined' ? localStorage.getItem('token') || '' : '';
      const resp = await fetch(`${baseUrl}/mcp/gateway/tools`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) return mergeWithBuiltins([]);
      const data = await resp.json();
      const apiTools: ToolOption[] = (data.tools || []).map((t: any) => ({
        value: t.name,
        label: t.name,
        description: t.description || '',
        category: t.category || 'other',
        source: 'gateway',
      }));
      gatewayToolsCache = apiTools;
      const tools = mergeWithBuiltins(apiTools);
      toolsCache = tools;
      return tools;
    } catch {
      return mergeWithBuiltins([]);
    } finally {
      toolsFetchPromise = null;
    }
  })();

  return toolsFetchPromise;
}

// Group tools by category
function groupToolsByCategory(tools: ToolOption[]): Array<{ category: string; tools: ToolOption[] }> {
  const grouped = new Map<string, ToolOption[]>();
  for (const tool of tools) {
    const cat = tool.category || 'other';
    if (!grouped.has(cat)) grouped.set(cat, []);
    grouped.get(cat)!.push(tool);
  }
  return Array.from(grouped.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([category, tools]) => ({ category, tools }));
}

export function useWorkflowOptions() {
  const [tools, setTools] = useState<ToolOption[]>(toolsCache || []);
  const [isLoading, setIsLoading] = useState(!toolsCache);
  const [gatewayTools, setGatewayTools] = useState<ToolOption[]>(gatewayToolsCache || []);

  useEffect(() => {
    if (toolsCache) {
      setTools(toolsCache);
      setGatewayTools(gatewayToolsCache || []);
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    fetchTools().then((result) => {
      if (!cancelled) {
        setTools(result);
        setGatewayTools(gatewayToolsCache || []);
        setIsLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, []);

  const refreshTools = useCallback(async () => {
    toolsCache = null;
    gatewayToolsCache = null;
    setIsLoading(true);
    const result = await fetchTools();
    setTools(result);
    setGatewayTools(gatewayToolsCache || []);
    setIsLoading(false);
  }, []);

  return {
    tools,
    toolsByCategory: groupToolsByCategory(tools),
    gatewayTools,
    gatewayToolsByCategory: groupToolsByCategory(gatewayTools),
    models: MODEL_OPTIONS,
    modelsByProvider: MODEL_OPTIONS_BY_PROVIDER,
    providerLabels: PROVIDER_LABELS,
    allProviders: ALL_PROVIDERS,
    isLoading,
    refreshTools,
  };
}
