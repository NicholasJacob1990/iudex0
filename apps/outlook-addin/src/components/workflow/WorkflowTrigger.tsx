/**
 * Painel para disparar workflows a partir do contexto do e-mail.
 *
 * Permite ao usuario selecionar e executar workflows sobre o e-mail atual.
 */

import { useState, useCallback } from 'react';
import {
  Button,
  Text,
  Spinner,
} from '@fluentui/react-components';
import { FlowRegular, PlayRegular } from '@fluentui/react-icons';
import { useEmailStore } from '@/stores/email-store';
import { triggerWorkflow, type WorkflowRun } from '@/api/client';
import { WorkflowStatus } from './WorkflowStatus';

interface WorkflowOption {
  id: string;
  label: string;
  description: string;
}

const AVAILABLE_WORKFLOWS: WorkflowOption[] = [
  {
    id: 'extract-deadlines',
    label: 'Extrair Prazos',
    description: 'Identifica e extrai todos os prazos mencionados no e-mail.',
  },
  {
    id: 'draft-reply',
    label: 'Minutar Resposta',
    description: 'Gera um rascunho de resposta juridica ao e-mail.',
  },
  {
    id: 'create-calendar-events',
    label: 'Criar Eventos',
    description: 'Cria eventos no calendario a partir dos prazos extraidos.',
  },
  {
    id: 'classify-archive',
    label: 'Classificar e Arquivar',
    description: 'Classifica o e-mail e sugere pasta de arquivamento.',
  },
];

export function WorkflowTrigger() {
  const currentEmail = useEmailStore((s) => s.currentEmail);
  const [activeRun, setActiveRun] = useState<WorkflowRun | null>(null);
  const [isTriggering, setIsTriggering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleTrigger = useCallback(
    async (workflowId: string) => {
      if (!currentEmail) return;

      setIsTriggering(true);
      setError(null);

      try {
        const run = await triggerWorkflow({
          workflow_id: workflowId,
          email_data: {
            subject: currentEmail.subject,
            body: currentEmail.body,
            sender: currentEmail.senderEmail || currentEmail.sender,
            recipients: currentEmail.recipients,
            date: currentEmail.date,
            attachments: currentEmail.attachments?.map((a) => ({
              name: a.name,
              contentType: a.contentType,
            })),
          },
        });
        setActiveRun(run);
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : 'Erro ao iniciar workflow';
        setError(message);
      } finally {
        setIsTriggering(false);
      }
    },
    [currentEmail]
  );

  const handleBack = useCallback(() => {
    setActiveRun(null);
    setError(null);
  }, []);

  // Estado: nenhum e-mail selecionado
  if (!currentEmail) {
    return (
      <div className="flex h-full items-center justify-center p-office-md text-center">
        <Text size={200} className="text-text-tertiary">
          Selecione um e-mail para executar workflows.
        </Text>
      </div>
    );
  }

  // Mostra status do workflow em execucao
  if (activeRun) {
    return (
      <div className="flex h-full flex-col">
        <div className="border-b border-gray-200 p-office-md">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FlowRegular className="text-brand" />
              <Text size={300} weight="semibold">
                {activeRun.workflow_name}
              </Text>
            </div>
            <button
              onClick={handleBack}
              className="text-office-xs text-brand hover:underline"
            >
              Voltar
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-office-md">
          <WorkflowStatus run={activeRun} />
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-office-md">
      <div className="mb-2 flex items-center gap-2">
        <FlowRegular className="text-brand" />
        <Text size={400} weight="semibold">
          Workflows
        </Text>
      </div>

      <Text size={200} className="mb-4 block text-text-secondary">
        Execute workflows automatizados sobre o e-mail atual.
      </Text>

      {/* Erro */}
      {error && (
        <div className="mb-3 rounded bg-red-50 p-2">
          <Text size={200} className="text-status-error">
            {error}
          </Text>
        </div>
      )}

      {/* Lista de workflows */}
      <div className="space-y-2">
        {AVAILABLE_WORKFLOWS.map((wf) => (
          <div
            key={wf.id}
            className="office-card flex items-start gap-3"
          >
            <div className="min-w-0 flex-1">
              <Text size={300} weight="semibold" className="block">
                {wf.label}
              </Text>
              <Text size={200} className="mt-0.5 block text-text-secondary">
                {wf.description}
              </Text>
            </div>
            <Button
              appearance="primary"
              size="small"
              icon={isTriggering ? <Spinner size="tiny" /> : <PlayRegular />}
              onClick={() => handleTrigger(wf.id)}
              disabled={isTriggering}
            >
              Executar
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}
