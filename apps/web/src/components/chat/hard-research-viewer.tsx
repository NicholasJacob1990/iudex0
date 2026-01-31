'use client';

import { useEffect, useRef, useState, useMemo } from 'react';
import { Card } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  Brain,
  Database,
  CheckCircle2,
  Loader2,
  XCircle,
  ChevronDown,
  ChevronRight,
  Globe,
  Search,
  BookOpen,
  FolderOpen,
  FileText,
  Sparkles,
  Zap,
  MessageCircle,
  Wrench,
  RotateCw,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface ProviderStatus {
  name: string;
  label: string;
  icon: React.ReactNode;
  description: string;
  status: 'idle' | 'searching' | 'done' | 'error';
  query?: string;
  resultsCount: number;
  elapsedMs: number;
  sources: Array<{ title: string; url: string }>;
  thinkingSteps: string[];
  error?: string;
}

interface StudyProgress {
  status: 'idle' | 'generating' | 'done';
  currentSection?: string;
  sections: string[];
  totalChars: number;
  sourcesCount: number;
}

interface MergeStatus {
  status: 'idle' | 'merging' | 'done';
  totalSources: number;
  deduplicated: number;
}

interface AgentToolCall {
  tool: string;
  input_summary?: string;
  timestamp: number;
}

interface AgentStatus {
  iteration: number;
  maxIterations: number;
  thinkingSteps: string[];
  toolCalls: AgentToolCall[];
  lastToolResult?: string;
  askingUser?: { question: string; options?: string[] };
}

interface HardResearchViewerProps {
  jobId: string;
  isVisible: boolean;
  events: any[];
}

const PROVIDER_CONFIGS: Record<string, { label: string; icon: React.ReactNode; description: string }> = {
  gemini: { label: 'Gemini Deep Research', icon: <Sparkles className="h-3.5 w-3.5" />, description: 'Google' },
  perplexity: { label: 'Perplexity Sonar', icon: <Search className="h-3.5 w-3.5" />, description: 'Web + Academic' },
  openai: { label: 'ChatGPT Deep Research', icon: <Brain className="h-3.5 w-3.5" />, description: 'OpenAI' },
  rag_global: { label: 'RAG Global', icon: <BookOpen className="h-3.5 w-3.5" />, description: 'Legislacao, Juris' },
  rag_local: { label: 'RAG Local', icon: <FolderOpen className="h-3.5 w-3.5" />, description: 'Docs do Caso' },
};

const TOOL_LABELS: Record<string, string> = {
  search_gemini: 'Pesquisar Gemini',
  search_perplexity: 'Pesquisar Perplexity',
  search_openai: 'Pesquisar ChatGPT',
  search_rag_global: 'Pesquisar RAG Global',
  search_rag_local: 'Pesquisar RAG Local',
  analyze_results: 'Analisar Resultados',
  ask_user: 'Perguntar ao Usuario',
  generate_study_section: 'Gerar Secao do Estudo',
  verify_citations: 'Verificar Citacoes',
};

function getStatusIcon(status: string) {
  switch (status) {
    case 'searching': return <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-400" />;
    case 'done': return <CheckCircle2 className="h-3.5 w-3.5 text-green-400" />;
    case 'error': return <XCircle className="h-3.5 w-3.5 text-red-400" />;
    default: return <div className="h-3.5 w-3.5 rounded-full border border-slate-600" />;
  }
}

function formatElapsed(ms: number): string {
  if (ms <= 0) return '';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function HardResearchViewer({ jobId, isVisible, events }: HardResearchViewerProps) {
  const [providers, setProviders] = useState<Record<string, ProviderStatus>>({});
  const [merge, setMerge] = useState<MergeStatus>({ status: 'idle', totalSources: 0, deduplicated: 0 });
  const [study, setStudy] = useState<StudyProgress>({ status: 'idle', sections: [], totalChars: 0, sourcesCount: 0 });
  const [agent, setAgent] = useState<AgentStatus>({
    iteration: 0,
    maxIterations: 15,
    thinkingSteps: [],
    toolCalls: [],
  });
  const [isExpanded, setIsExpanded] = useState(true);
  const [expandedProvider, setExpandedProvider] = useState<string | null>(null);
  const [showAgentDetails, setShowAgentDetails] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Process events
  useEffect(() => {
    if (!isVisible || !events?.length) return;

    const newProviders: Record<string, ProviderStatus> = {};
    let newMerge: MergeStatus = { status: 'idle', totalSources: 0, deduplicated: 0 };
    let newStudy: StudyProgress = { status: 'idle', sections: [], totalChars: 0, sourcesCount: 0 };
    let newAgent: AgentStatus = {
      iteration: 0,
      maxIterations: 15,
      thinkingSteps: [],
      toolCalls: [],
    };

    for (const e of events) {
      if (!e?.type) continue;

      switch (e.type) {
        case 'hard_research_start': {
          const providerList = e.providers || [];
          for (const p of providerList) {
            const config = PROVIDER_CONFIGS[p] || { label: p, icon: <Globe className="h-3.5 w-3.5" />, description: '' };
            newProviders[p] = {
              name: p,
              label: config.label,
              icon: config.icon,
              description: config.description,
              status: 'idle',
              resultsCount: 0,
              elapsedMs: 0,
              sources: [],
              thinkingSteps: [],
            };
          }
          if (e.max_iterations) newAgent.maxIterations = e.max_iterations;
          break;
        }
        case 'provider_start': {
          const p = e.provider;
          if (p && newProviders[p]) {
            newProviders[p].status = 'searching';
            if (e.query) newProviders[p].query = e.query;
          }
          break;
        }
        case 'provider_thinking': {
          const p = e.provider;
          if (p && newProviders[p] && e.text) {
            newProviders[p].thinkingSteps.push(e.text);
          }
          break;
        }
        case 'provider_source': {
          const p = e.provider;
          if (p && newProviders[p] && e.source) {
            newProviders[p].sources.push(e.source);
          }
          break;
        }
        case 'provider_done': {
          const p = e.provider;
          if (p && newProviders[p]) {
            newProviders[p].status = 'done';
            newProviders[p].resultsCount = e.results_count || newProviders[p].sources.length;
            newProviders[p].elapsedMs = e.elapsed_ms || 0;
          }
          break;
        }
        case 'provider_error': {
          const p = e.provider;
          if (p && newProviders[p]) {
            newProviders[p].status = 'error';
            newProviders[p].error = e.error || 'Erro desconhecido';
          }
          break;
        }
        case 'merge_start':
          newMerge = { status: 'merging', totalSources: 0, deduplicated: 0 };
          break;
        case 'merge_done':
          newMerge = { status: 'done', totalSources: e.total_sources || 0, deduplicated: e.deduplicated || 0 };
          break;
        case 'study_generation_start':
          newStudy = { ...newStudy, status: 'generating' };
          break;
        case 'study_outline':
          newStudy = { ...newStudy, sections: e.sections || [] };
          break;
        case 'study_token':
          if (e.section) newStudy.currentSection = e.section;
          break;
        case 'study_done':
          newStudy = {
            ...newStudy,
            status: 'done',
            totalChars: e.total_chars || 0,
            sourcesCount: e.sources_count || 0,
          };
          break;
        // Agent-specific events
        case 'agent_iteration':
          newAgent.iteration = e.iteration || (newAgent.iteration + 1);
          if (e.max_iterations) newAgent.maxIterations = e.max_iterations;
          break;
        case 'agent_thinking': {
          const text = e.text || e.thinking || '';
          if (text) newAgent.thinkingSteps.push(text);
          break;
        }
        case 'agent_tool_call':
          newAgent.toolCalls.push({
            tool: e.tool || 'unknown',
            input_summary: e.input_summary || e.query || '',
            timestamp: Date.now(),
          });
          break;
        case 'agent_tool_result':
          newAgent.lastToolResult = e.summary || e.result || '';
          break;
        case 'agent_ask_user':
          newAgent.askingUser = {
            question: e.question || '',
            options: e.options,
          };
          break;
      }
    }

    setProviders(newProviders);
    setMerge(newMerge);
    setStudy(newStudy);
    setAgent(newAgent);
  }, [events, isVisible]);

  // Auto-scroll
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [providers, merge, study, agent]);

  const providerList = useMemo(() => Object.values(providers), [providers]);
  const doneCount = providerList.filter(p => p.status === 'done').length;
  const totalCount = providerList.length;
  const isAgentActive = agent.iteration > 0 && study.status !== 'done';
  const isActive = isAgentActive || (totalCount > 0 && (doneCount < totalCount || merge.status !== 'done' || study.status !== 'done'));
  const overallDone = study.status === 'done';

  if (!isVisible || (totalCount === 0 && agent.iteration === 0)) return null;

  return (
    <Card className="my-4 border-red-500/20 bg-red-500/5 overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between p-3 cursor-pointer hover:bg-white/5 transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          {isActive && !overallDone && <Loader2 className="h-4 w-4 text-red-400 animate-spin" />}
          {overallDone && <CheckCircle2 className="h-4 w-4 text-green-400" />}

          <span className="text-sm font-medium text-red-200">
            Deep Research Hard
          </span>

          {agent.iteration > 0 && (
            <Badge variant="outline" className="ml-1 border-red-500/30 text-[10px] text-red-300">
              Iteracao {agent.iteration}/{agent.maxIterations}
            </Badge>
          )}

          {totalCount > 0 && (
            <Badge variant="outline" className="border-blue-500/30 text-[10px] text-blue-300">
              {doneCount}/{totalCount} fontes
            </Badge>
          )}

          {merge.status === 'done' && (
            <Badge variant="outline" className="border-amber-500/30 text-[10px] text-amber-300">
              {merge.deduplicated} resultados
            </Badge>
          )}

          {agent.askingUser && (
            <Badge variant="outline" className="border-yellow-500/30 text-[10px] text-yellow-300 animate-pulse">
              Aguardando resposta
            </Badge>
          )}
        </div>

        {isExpanded ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
      </div>

      {isExpanded && (
        <div className="border-t border-red-500/10 bg-black/20">
          <ScrollArea className="max-h-[400px] w-full" ref={scrollRef}>
            <div className="p-3 space-y-1">

              {/* Agent activity log */}
              {agent.iteration > 0 && (
                <div className="mb-2">
                  <div
                    className="flex items-center gap-2 py-1.5 px-2 rounded text-sm cursor-pointer hover:bg-white/5 transition-colors"
                    onClick={() => setShowAgentDetails(!showAgentDetails)}
                  >
                    <RotateCw className={cn("h-3.5 w-3.5 text-red-400", isAgentActive && "animate-spin")} />
                    <span className="text-xs font-medium text-red-200">Agente Claude</span>
                    <span className="text-[10px] text-muted-foreground">
                      {agent.toolCalls.length} acoes executadas
                    </span>
                    {showAgentDetails
                      ? <ChevronDown className="h-3 w-3 text-muted-foreground ml-auto" />
                      : <ChevronRight className="h-3 w-3 text-muted-foreground ml-auto" />
                    }
                  </div>

                  {showAgentDetails && (
                    <div className="ml-6 mb-2 space-y-1 border-l border-red-500/20 pl-3">
                      {/* Recent thinking */}
                      {agent.thinkingSteps.length > 0 && (
                        <div className="space-y-0.5">
                          {agent.thinkingSteps.slice(-3).map((step, i) => (
                            <p key={i} className="text-[10px] text-slate-500 italic line-clamp-2">
                              {step}
                            </p>
                          ))}
                        </div>
                      )}

                      {/* Tool call history */}
                      {agent.toolCalls.slice(-8).map((tc, i) => (
                        <div key={i} className="flex items-center gap-2 py-0.5">
                          <Wrench className="h-2.5 w-2.5 text-slate-500" />
                          <span className="text-[10px] text-slate-400">
                            {TOOL_LABELS[tc.tool] || tc.tool}
                          </span>
                          {tc.input_summary && (
                            <span className="text-[10px] text-slate-600 truncate max-w-[200px]">
                              {tc.input_summary}
                            </span>
                          )}
                        </div>
                      ))}
                      {agent.toolCalls.length > 8 && (
                        <p className="text-[10px] text-slate-600">
                          +{agent.toolCalls.length - 8} acoes anteriores...
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Provider rows */}
              {providerList.map((provider) => (
                <div key={provider.name}>
                  <div
                    className={cn(
                      'flex items-center gap-3 py-1.5 px-2 rounded text-sm cursor-pointer hover:bg-white/5 transition-colors',
                      expandedProvider === provider.name && 'bg-white/5'
                    )}
                    onClick={() => setExpandedProvider(expandedProvider === provider.name ? null : provider.name)}
                  >
                    {getStatusIcon(provider.status)}
                    <span className="text-muted-foreground">{provider.icon}</span>
                    <div className="flex-1 min-w-0">
                      <span className="text-xs font-medium text-slate-200">{provider.label}</span>
                      <span className="text-[10px] text-muted-foreground ml-1.5">({provider.description})</span>
                    </div>
                    {provider.status === 'done' && (
                      <span className="text-[10px] text-green-400/70 tabular-nums">
                        {provider.resultsCount} resultados
                      </span>
                    )}
                    {provider.status === 'error' && (
                      <span className="text-[10px] text-red-400/70">erro</span>
                    )}
                    {provider.status === 'searching' && (
                      <span className="text-[10px] text-blue-400/70 animate-pulse">Pesquisando...</span>
                    )}
                    {provider.elapsedMs > 0 && (
                      <span className="text-[10px] text-muted-foreground tabular-nums ml-1">
                        {formatElapsed(provider.elapsedMs)}
                      </span>
                    )}
                  </div>

                  {expandedProvider === provider.name && (
                    <div className="ml-8 mb-2 space-y-1 border-l border-slate-700 pl-3">
                      {provider.query && (
                        <p className="text-[10px] text-slate-400 font-mono">
                          Query: {provider.query}
                        </p>
                      )}
                      {provider.sources.slice(0, 5).map((src, i) => (
                        <p key={i} className="text-[10px] text-slate-500 truncate">
                          {src.title}
                        </p>
                      ))}
                      {provider.sources.length > 5 && (
                        <p className="text-[10px] text-slate-600">
                          +{provider.sources.length - 5} mais...
                        </p>
                      )}
                      {provider.error && (
                        <p className="text-[10px] text-red-400">{provider.error}</p>
                      )}
                    </div>
                  )}
                </div>
              ))}

              {/* Merge status */}
              {merge.status !== 'idle' && (
                <div className="flex items-center gap-3 py-1.5 px-2 text-sm">
                  {merge.status === 'merging' && <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-400" />}
                  {merge.status === 'done' && <Zap className="h-3.5 w-3.5 text-amber-400" />}
                  <span className="text-xs text-amber-200">Consolidando resultados</span>
                  {merge.status === 'done' && (
                    <span className="text-[10px] text-amber-400/70 ml-auto">
                      {merge.totalSources} fontes → {merge.deduplicated} apos dedup
                    </span>
                  )}
                </div>
              )}

              {/* Agent asking user */}
              {agent.askingUser && (
                <div className="py-2 px-2 bg-yellow-500/10 border border-yellow-500/20 rounded space-y-1.5">
                  <div className="flex items-center gap-2">
                    <MessageCircle className="h-3.5 w-3.5 text-yellow-400" />
                    <span className="text-xs font-medium text-yellow-200">Agente pergunta:</span>
                  </div>
                  <p className="text-xs text-yellow-100/80 ml-5">{agent.askingUser.question}</p>
                  {agent.askingUser.options && agent.askingUser.options.length > 0 && (
                    <div className="ml-5 space-y-0.5">
                      {agent.askingUser.options.map((opt, i) => (
                        <p key={i} className="text-[10px] text-yellow-300/60">
                          {i + 1}. {opt}
                        </p>
                      ))}
                    </div>
                  )}
                  <p className="text-[10px] text-yellow-400/50 ml-5 italic">
                    Responda no chat para continuar a pesquisa
                  </p>
                </div>
              )}

              {/* Study generation */}
              {study.status !== 'idle' && (
                <div className="py-1.5 px-2 space-y-1.5">
                  <div className="flex items-center gap-3 text-sm">
                    {study.status === 'generating' && <Loader2 className="h-3.5 w-3.5 animate-spin text-purple-400" />}
                    {study.status === 'done' && <FileText className="h-3.5 w-3.5 text-purple-400" />}
                    <span className="text-xs text-purple-200">Gerando estudo</span>
                    {study.currentSection && study.status === 'generating' && (
                      <span className="text-[10px] text-purple-400/70 ml-auto animate-pulse">
                        {study.currentSection}
                      </span>
                    )}
                    {study.status === 'done' && (
                      <span className="text-[10px] text-purple-400/70 ml-auto">
                        {study.sourcesCount} citacoes
                      </span>
                    )}
                  </div>
                  {study.sections.length > 0 && study.status === 'generating' && (
                    <Progress
                      value={study.currentSection
                        ? ((study.sections.indexOf(study.currentSection) + 1) / study.sections.length) * 100
                        : 0
                      }
                      className="h-1"
                    />
                  )}
                </div>
              )}
            </div>
          </ScrollArea>
        </div>
      )}
    </Card>
  );
}
