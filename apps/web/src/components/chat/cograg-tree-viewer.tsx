'use client';

import { useMemo } from 'react';
import { Card } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import {
  Brain,
  CheckCircle2,
  Loader2,
  XCircle,
  ChevronDown,
  ChevronRight,
  Search,
  FileCheck,
  GitBranch,
  AlertCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useState } from 'react';

type CogRAGNodeState = 'pending' | 'decomposing' | 'retrieving' | 'retrieved' | 'verifying' | 'verified' | 'rejected' | 'complete' | 'error';
type CogRAGStatus = 'idle' | 'decomposing' | 'retrieving' | 'verifying' | 'integrating' | 'complete';

interface CogRAGNode {
  nodeId: string;
  question: string;
  level: number;
  parentId: string | null;
  state: CogRAGNodeState;
  childrenCount: number;
  evidenceCount: number;
  confidence: number;
}

interface CogRAGTreeViewerProps {
  nodes: CogRAGNode[] | null;
  status: CogRAGStatus;
  isVisible: boolean;
}

function getNodeStateIcon(state: CogRAGNodeState) {
  switch (state) {
    case 'decomposing':
      return <Loader2 className="h-3 w-3 animate-spin text-blue-400" />;
    case 'retrieving':
      return <Loader2 className="h-3 w-3 animate-spin text-amber-400" />;
    case 'retrieved':
      return <Search className="h-3 w-3 text-amber-400" />;
    case 'verifying':
      return <Loader2 className="h-3 w-3 animate-spin text-purple-400" />;
    case 'verified':
      return <CheckCircle2 className="h-3 w-3 text-green-400" />;
    case 'rejected':
      return <XCircle className="h-3 w-3 text-red-400" />;
    case 'complete':
      return <CheckCircle2 className="h-3 w-3 text-green-400" />;
    case 'error':
      return <AlertCircle className="h-3 w-3 text-red-400" />;
    default:
      return <div className="h-3 w-3 rounded-full border border-slate-600" />;
  }
}

function getStatusIcon(status: CogRAGStatus) {
  switch (status) {
    case 'decomposing':
      return <GitBranch className="h-4 w-4 text-blue-400 animate-pulse" />;
    case 'retrieving':
      return <Search className="h-4 w-4 text-amber-400 animate-pulse" />;
    case 'verifying':
      return <FileCheck className="h-4 w-4 text-purple-400 animate-pulse" />;
    case 'integrating':
      return <Brain className="h-4 w-4 text-cyan-400 animate-pulse" />;
    case 'complete':
      return <CheckCircle2 className="h-4 w-4 text-green-400" />;
    default:
      return <Brain className="h-4 w-4 text-slate-400" />;
  }
}

function getStatusLabel(status: CogRAGStatus): string {
  switch (status) {
    case 'decomposing':
      return 'Decompondo pergunta...';
    case 'retrieving':
      return 'Buscando evidencias...';
    case 'verifying':
      return 'Verificando respostas...';
    case 'integrating':
      return 'Integrando resposta final...';
    case 'complete':
      return 'Analise cognitiva completa';
    default:
      return 'Iniciando...';
  }
}

export function CogRAGTreeViewer({ nodes, status, isVisible }: CogRAGTreeViewerProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());

  // Build tree structure
  const treeData = useMemo(() => {
    if (!nodes || nodes.length === 0) return null;

    // Group nodes by level
    const byLevel: Record<number, CogRAGNode[]> = {};
    for (const node of nodes) {
      if (!byLevel[node.level]) byLevel[node.level] = [];
      byLevel[node.level].push(node);
    }

    // Find root (level 0)
    const root = byLevel[0]?.[0] || null;
    const maxLevel = Math.max(...Object.keys(byLevel).map(Number));
    const leafCount = (byLevel[maxLevel] || []).length;

    return {
      root,
      byLevel,
      maxLevel,
      leafCount,
      totalNodes: nodes.length,
    };
  }, [nodes]);

  const toggleNode = (nodeId: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  };

  const isActive = status !== 'idle' && status !== 'complete';

  if (!isVisible || (!nodes?.length && status === 'idle')) return null;

  return (
    <Card className="my-4 border-cyan-500/20 bg-cyan-500/5 overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between p-3 cursor-pointer hover:bg-white/5 transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          {getStatusIcon(status)}

          <span className="text-sm font-medium text-cyan-200">
            CogGRAG
          </span>

          <Badge variant="outline" className="border-cyan-500/30 text-[10px] text-cyan-300">
            {getStatusLabel(status)}
          </Badge>

          {treeData && (
            <>
              <Badge variant="outline" className="border-blue-500/30 text-[10px] text-blue-300">
                {treeData.totalNodes} nodes
              </Badge>
              <Badge variant="outline" className="border-amber-500/30 text-[10px] text-amber-300">
                {treeData.leafCount} sub-perguntas
              </Badge>
            </>
          )}
        </div>

        {isExpanded ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        )}
      </div>

      {isExpanded && (
        <div className="border-t border-cyan-500/10 bg-black/20">
          <ScrollArea className="max-h-[350px] w-full">
            <div className="p-3 space-y-1">
              {/* Root question */}
              {treeData?.root && (
                <div className="mb-2">
                  <div className="flex items-center gap-2 py-1.5 px-2 rounded bg-cyan-500/10">
                    {getNodeStateIcon(treeData.root.state)}
                    <span className="text-xs font-medium text-cyan-100">
                      {treeData.root.question}
                    </span>
                  </div>
                </div>
              )}

              {/* Sub-questions by level */}
              {treeData && Object.keys(treeData.byLevel).sort((a, b) => Number(a) - Number(b)).map((levelStr) => {
                const level = Number(levelStr);
                if (level === 0) return null; // Skip root, already shown

                const levelNodes = treeData.byLevel[level];

                return (
                  <div key={level} className="space-y-0.5">
                    <div className="text-[10px] text-slate-500 px-2 py-0.5">
                      Nivel {level} ({levelNodes.length} {levelNodes.length === 1 ? 'sub-pergunta' : 'sub-perguntas'})
                    </div>
                    {levelNodes.map((node) => (
                      <div
                        key={node.nodeId}
                        className={cn(
                          'flex items-center gap-2 py-1 px-2 rounded text-sm cursor-pointer hover:bg-white/5 transition-colors',
                          expandedNodes.has(node.nodeId) && 'bg-white/5'
                        )}
                        style={{ marginLeft: `${(level - 1) * 12}px` }}
                        onClick={() => toggleNode(node.nodeId)}
                      >
                        {getNodeStateIcon(node.state)}
                        <div className="flex-1 min-w-0">
                          <span className="text-xs text-slate-200 line-clamp-1">
                            {node.question}
                          </span>
                        </div>
                        {node.evidenceCount > 0 && (
                          <span className="text-[10px] text-amber-400/70 tabular-nums">
                            {node.evidenceCount} docs
                          </span>
                        )}
                        {node.confidence > 0 && (
                          <span
                            className={cn(
                              'text-[10px] tabular-nums',
                              node.confidence >= 0.7 ? 'text-green-400/70' :
                              node.confidence >= 0.4 ? 'text-amber-400/70' :
                              'text-red-400/70'
                            )}
                          >
                            {(node.confidence * 100).toFixed(0)}%
                          </span>
                        )}
                        {node.state === 'rejected' && (
                          <Badge variant="outline" className="border-red-500/30 text-[9px] text-red-300">
                            rejeitada
                          </Badge>
                        )}
                      </div>
                    ))}
                  </div>
                );
              })}

              {/* Loading state when no nodes yet */}
              {(!nodes || nodes.length === 0) && status !== 'idle' && (
                <div className="flex items-center justify-center py-4 gap-2">
                  <Loader2 className="h-4 w-4 animate-spin text-cyan-400" />
                  <span className="text-xs text-slate-400">Analisando pergunta...</span>
                </div>
              )}

              {/* Summary when complete */}
              {status === 'complete' && treeData && (
                <div className="mt-2 pt-2 border-t border-cyan-500/10">
                  <div className="flex items-center gap-2 text-[10px] text-slate-400">
                    <CheckCircle2 className="h-3 w-3 text-green-400" />
                    <span>
                      Analise completa: {treeData.leafCount} sub-perguntas processadas em {treeData.maxLevel} niveis
                    </span>
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>
        </div>
      )}
    </Card>
  );
}
