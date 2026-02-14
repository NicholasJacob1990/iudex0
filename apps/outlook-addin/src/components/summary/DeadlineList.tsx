/**
 * Lista de prazos extraidos do e-mail.
 *
 * Renderiza cada prazo com data, descricao e badge de urgencia (alta/media/baixa).
 */

import { Badge, Text } from '@fluentui/react-components';
import {
  CalendarRegular,
  WarningRegular,
} from '@fluentui/react-icons';
import type { DeadlineResult } from '@/api/client';

interface DeadlineListProps {
  deadlines: DeadlineResult[];
}

const URGENCY_CONFIG: Record<
  DeadlineResult['urgencia'],
  { color: 'danger' | 'warning' | 'success'; label: string }
> = {
  alta: { color: 'danger', label: 'Alta' },
  media: { color: 'warning', label: 'Media' },
  baixa: { color: 'success', label: 'Baixa' },
};

export function DeadlineList({ deadlines }: DeadlineListProps) {
  if (deadlines.length === 0) return null;

  return (
    <div className="office-card">
      <div className="mb-2 flex items-center gap-2">
        <CalendarRegular className="text-brand" />
        <Text size={300} weight="semibold">
          Prazos Identificados
        </Text>
        <Badge appearance="filled" color="informative" size="small">
          {deadlines.length}
        </Badge>
      </div>

      <div className="space-y-2">
        {deadlines.map((deadline, index) => {
          const config = URGENCY_CONFIG[deadline.urgencia];
          const formattedDate = formatDate(deadline.data);

          return (
            <div
              key={index}
              className="flex items-start gap-2 rounded border border-gray-100 bg-surface-secondary p-2"
            >
              {deadline.urgencia === 'alta' && (
                <WarningRegular className="mt-0.5 shrink-0 text-urgency-alta" />
              )}

              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <Text size={200} weight="semibold" className="text-text-primary">
                    {formattedDate}
                  </Text>
                  <Badge
                    appearance="outline"
                    color={config.color}
                    size="small"
                  >
                    {config.label}
                  </Badge>
                </div>

                <Text size={200} className="mt-0.5 block text-text-secondary">
                  {deadline.descricao}
                </Text>

                {deadline.fonte && (
                  <Text size={100} className="mt-0.5 block text-text-tertiary">
                    Fonte: {deadline.fonte}
                  </Text>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function formatDate(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    return date.toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  } catch {
    return dateStr;
  }
}
