/**
 * Barra de acoes sugeridas e workflows recomendados.
 *
 * Renderiza botoes para acoes sugeridas pela IA e links para workflows.
 */

import { Button, Text } from '@fluentui/react-components';
import {
  LightbulbRegular,
  FlowRegular,
} from '@fluentui/react-icons';

interface ActionBarProps {
  acoes: string[];
  workflows: string[];
}

export function ActionBar({ acoes, workflows }: ActionBarProps) {
  if (acoes.length === 0 && workflows.length === 0) return null;

  return (
    <div className="space-y-3">
      {/* Acoes sugeridas */}
      {acoes.length > 0 && (
        <div className="office-card">
          <div className="mb-2 flex items-center gap-2">
            <LightbulbRegular className="text-brand" />
            <Text size={300} weight="semibold">
              Acoes Sugeridas
            </Text>
          </div>

          <div className="space-y-1.5">
            {acoes.map((acao, index) => (
              <div
                key={index}
                className="flex items-start gap-2 rounded bg-surface-secondary p-2"
              >
                <span className="mt-0.5 shrink-0 text-office-xs text-brand">
                  {index + 1}.
                </span>
                <Text size={200} className="text-text-secondary">
                  {acao}
                </Text>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Workflows recomendados */}
      {workflows.length > 0 && (
        <div className="office-card">
          <div className="mb-2 flex items-center gap-2">
            <FlowRegular className="text-brand" />
            <Text size={300} weight="semibold">
              Workflows Recomendados
            </Text>
          </div>

          <div className="flex flex-wrap gap-2">
            {workflows.map((workflow, index) => (
              <Button
                key={index}
                appearance="outline"
                size="small"
              >
                {workflow}
              </Button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
