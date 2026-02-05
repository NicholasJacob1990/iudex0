import { useState } from 'react';
import { TranslationForm } from './TranslationForm';
import { AnonymizationForm } from './AnonymizationForm';

type WorkflowId = 'translate' | 'anonymize' | null;

interface WorkflowOption {
  id: WorkflowId;
  label: string;
  description: string;
  icon: string;
}

const WORKFLOWS: WorkflowOption[] = [
  {
    id: 'translate',
    label: 'Traducao',
    description: 'Traduzir texto mantendo terminologia juridica',
    icon: '🌐',
  },
  {
    id: 'anonymize',
    label: 'Anonimizacao (LGPD)',
    description: 'Identificar e substituir dados pessoais',
    icon: '🔒',
  },
];

export function WorkflowPanel() {
  const [activeWorkflow, setActiveWorkflow] = useState<WorkflowId>(null);

  if (!activeWorkflow) {
    return (
      <div className="h-full overflow-y-auto p-office-md">
        <h2 className="mb-2 text-office-lg font-semibold">Ferramentas</h2>
        <p className="mb-4 text-office-xs text-text-secondary">
          Workflows automatizados para documentos juridicos.
        </p>

        <div className="space-y-2">
          {WORKFLOWS.map((wf) => (
            <button
              key={wf.id}
              onClick={() => setActiveWorkflow(wf.id)}
              className="office-card flex w-full cursor-pointer items-start gap-3 text-left hover:border-brand"
            >
              <span className="text-xl">{wf.icon}</span>
              <div>
                <p className="text-office-base font-medium">{wf.label}</p>
                <p className="mt-0.5 text-office-xs text-text-secondary">
                  {wf.description}
                </p>
              </div>
            </button>
          ))}
        </div>
      </div>
    );
  }

  const current = WORKFLOWS.find((w) => w.id === activeWorkflow);

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-gray-200 p-office-md">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span>{current?.icon}</span>
            <h2 className="text-office-base font-semibold">{current?.label}</h2>
          </div>
          <button
            onClick={() => setActiveWorkflow(null)}
            className="text-office-xs text-brand hover:underline"
          >
            Voltar
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-office-md">
        {activeWorkflow === 'translate' && <TranslationForm />}
        {activeWorkflow === 'anonymize' && <AnonymizationForm />}
      </div>
    </div>
  );
}
