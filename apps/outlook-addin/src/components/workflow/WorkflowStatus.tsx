/**
 * Componente de status de execucao de workflow.
 *
 * Exibe o progresso e resultado de um workflow em execucao.
 * Faz polling do status ate completar.
 */

import { useEffect, useState, useRef } from 'react';
import {
  Badge,
  Spinner,
  Text,
} from '@fluentui/react-components';
import {
  CheckmarkCircleRegular,
  DismissCircleRegular,
  ClockRegular,
} from '@fluentui/react-icons';
import { getWorkflowStatus, type WorkflowRun } from '@/api/client';

interface WorkflowStatusProps {
  run: WorkflowRun;
}

const STATUS_CONFIG: Record<
  WorkflowRun['status'],
  {
    color: 'informative' | 'warning' | 'success' | 'danger';
    label: string;
    icon: React.ReactNode;
  }
> = {
  pending: {
    color: 'informative',
    label: 'Pendente',
    icon: <ClockRegular />,
  },
  running: {
    color: 'warning',
    label: 'Executando',
    icon: <Spinner size="tiny" />,
  },
  completed: {
    color: 'success',
    label: 'Concluido',
    icon: <CheckmarkCircleRegular />,
  },
  failed: {
    color: 'danger',
    label: 'Falhou',
    icon: <DismissCircleRegular />,
  },
};

export function WorkflowStatus({ run: initialRun }: WorkflowStatusProps) {
  const [run, setRun] = useState<WorkflowRun>(initialRun);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Polling de status enquanto nao estiver completo
  useEffect(() => {
    if (run.status === 'completed' || run.status === 'failed') {
      return;
    }

    intervalRef.current = setInterval(async () => {
      try {
        const updated = await getWorkflowStatus(run.id);
        setRun(updated);

        if (updated.status === 'completed' || updated.status === 'failed') {
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        }
      } catch (err) {
        console.error('[WorkflowStatus] Polling error:', err);
      }
    }, 3000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [run.id, run.status]);

  const config = STATUS_CONFIG[run.status];

  return (
    <div className="space-y-3">
      {/* Status badge */}
      <div className="office-card">
        <div className="flex items-center gap-2">
          {config.icon}
          <Text size={300} weight="semibold">
            {run.workflow_name}
          </Text>
          <Badge appearance="filled" color={config.color} size="small">
            {config.label}
          </Badge>
        </div>

        <Text size={100} className="mt-1 block text-text-tertiary">
          Iniciado em:{' '}
          {new Date(run.created_at).toLocaleString('pt-BR')}
        </Text>

        {run.updated_at !== run.created_at && (
          <Text size={100} className="block text-text-tertiary">
            Atualizado em:{' '}
            {new Date(run.updated_at).toLocaleString('pt-BR')}
          </Text>
        )}
      </div>

      {/* Resultado */}
      {run.status === 'completed' && run.result && (
        <div className="office-card">
          <Text size={300} weight="semibold" className="mb-2 block">
            Resultado
          </Text>
          <pre className="max-h-[300px] overflow-auto rounded bg-surface-tertiary p-2 text-office-xs">
            {JSON.stringify(run.result, null, 2)}
          </pre>
        </div>
      )}

      {/* Erro */}
      {run.status === 'failed' && (
        <div className="rounded bg-red-50 p-3">
          <Text size={200} className="text-status-error">
            O workflow falhou. Tente novamente ou contate o suporte.
          </Text>
        </div>
      )}

      {/* Loading */}
      {(run.status === 'pending' || run.status === 'running') && (
        <div className="flex items-center justify-center py-4">
          <Spinner size="small" label="Aguardando conclusao..." />
        </div>
      )}
    </div>
  );
}
