'use client';

import { useCallback, useEffect, useState } from 'react';
import { Loader2, CheckCircle2, XCircle, X, Bot, ChevronDown, ChevronUp, ArrowRight } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { toast } from 'sonner';
import apiClient from '@/lib/api-client';

interface AgentTask {
  task_id: string;
  user_id: string;
  prompt: string;
  status: 'queued' | 'running' | 'completed' | 'error' | 'cancelled';
  result: string | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  model: string;
  metadata: Record<string, any>;
}

const STATUS_CONFIG = {
  queued: { icon: Loader2, color: 'text-yellow-500', bg: 'bg-yellow-500/10', label: 'Na fila', spin: true },
  running: { icon: Loader2, color: 'text-blue-500', bg: 'bg-blue-500/10', label: 'Executando', spin: true },
  completed: { icon: CheckCircle2, color: 'text-green-500', bg: 'bg-green-500/10', label: 'Concluído', spin: false },
  error: { icon: XCircle, color: 'text-red-500', bg: 'bg-red-500/10', label: 'Erro', spin: false },
  cancelled: { icon: X, color: 'text-gray-400', bg: 'bg-gray-400/10', label: 'Cancelado', spin: false },
} as const;

function formatTimeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'agora';
  if (mins < 60) return `${mins}min`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function truncate(str: string, max: number): string {
  if (str.length <= max) return str;
  return str.slice(0, max - 1) + '\u2026';
}

export function BackgroundTasks() {
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [expanded, setExpanded] = useState(true);
  const [expandedTask, setExpandedTask] = useState<string | null>(null);

  const fetchTasks = useCallback(async () => {
    try {
      const data = await apiClient.listAgentTasks();
      setTasks(data);
    } catch {
      // Silently fail — component is optional
    }
  }, []);

  useEffect(() => {
    fetchTasks();
    const interval = setInterval(fetchTasks, 3000);
    return () => clearInterval(interval);
  }, [fetchTasks]);

  const handleCancel = async (taskId: string) => {
    try {
      await apiClient.cancelAgentTask(taskId);
      toast.success('Agente cancelado');
      fetchTasks();
    } catch {
      toast.error('Falha ao cancelar agente');
    }
  };

  const handleExportToWorkflow = async (taskId: string) => {
    try {
      const result = await apiClient.exportToWorkflow({ agent_task_id: taskId });
      toast.success('Exportado para workflow', {
        description: `Sessão: ${result.session_id.slice(0, 8)}...`,
      });
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Falha ao exportar');
    }
  };

  const activeTasks = tasks.filter(t => t.status === 'queued' || t.status === 'running');
  const recentTasks = tasks.filter(t => t.status !== 'queued' && t.status !== 'running');

  if (tasks.length === 0) return null;

  return (
    <div className="border-t border-border/50">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
      >
        <span className="flex items-center gap-1.5">
          <Bot className="h-3.5 w-3.5" />
          Agentes Background
          {activeTasks.length > 0 && (
            <span className="ml-1 rounded-full bg-blue-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-blue-500">
              {activeTasks.length}
            </span>
          )}
        </span>
        {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronUp className="h-3.5 w-3.5" />}
      </button>

      {/* Task List */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <div className="max-h-48 space-y-1 overflow-y-auto px-2 pb-2">
              {tasks.map((task) => {
                const config = STATUS_CONFIG[task.status];
                const Icon = config.icon;
                const isExpanded = expandedTask === task.task_id;

                return (
                  <div
                    key={task.task_id}
                    className={`rounded-md ${config.bg} p-2 text-xs`}
                  >
                    <div className="flex items-start gap-2">
                      <Icon
                        className={`mt-0.5 h-3.5 w-3.5 flex-shrink-0 ${config.color} ${config.spin ? 'animate-spin' : ''}`}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between">
                          <button
                            onClick={() => setExpandedTask(isExpanded ? null : task.task_id)}
                            className="truncate font-medium text-foreground hover:underline text-left"
                          >
                            {truncate(task.prompt, 40)}
                          </button>
                          <span className="ml-2 flex-shrink-0 text-[10px] text-muted-foreground">
                            {formatTimeAgo(task.created_at)}
                          </span>
                        </div>

                        <div className="mt-0.5 flex items-center gap-2">
                          <span className={`text-[10px] ${config.color}`}>
                            {config.label}
                          </span>
                          {(task.status === 'queued' || task.status === 'running') && (
                            <button
                              onClick={() => handleCancel(task.task_id)}
                              className="text-[10px] text-red-400 hover:text-red-300 underline"
                            >
                              cancelar
                            </button>
                          )}
                          {task.status === 'completed' && task.result && (
                            <button
                              onClick={() => handleExportToWorkflow(task.task_id)}
                              className="inline-flex items-center gap-0.5 text-[10px] text-indigo-400 hover:text-indigo-300 underline"
                            >
                              workflow <ArrowRight className="h-2.5 w-2.5" />
                            </button>
                          )}
                        </div>

                        {/* Expanded result */}
                        <AnimatePresence>
                          {isExpanded && (task.result || task.error) && (
                            <motion.div
                              initial={{ height: 0, opacity: 0 }}
                              animate={{ height: 'auto', opacity: 1 }}
                              exit={{ height: 0, opacity: 0 }}
                              className="mt-1.5 overflow-hidden"
                            >
                              {task.error ? (
                                <p className="text-[11px] text-red-400 whitespace-pre-wrap">
                                  {task.error}
                                </p>
                              ) : task.result ? (
                                <p className="text-[11px] text-muted-foreground whitespace-pre-wrap max-h-32 overflow-y-auto">
                                  {truncate(task.result, 500)}
                                </p>
                              ) : null}
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
