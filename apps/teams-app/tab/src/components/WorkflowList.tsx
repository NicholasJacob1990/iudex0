import {
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
  Badge,
  Text,
} from '@fluentui/react-components';
import type { Workflow } from '@/api/client';

interface WorkflowListProps {
  workflows: Workflow[];
}

const statusConfig: Record<
  Workflow['status'],
  { label: string; color: 'success' | 'warning' | 'danger' | 'informative' }
> = {
  completed: { label: 'Concluido', color: 'success' },
  running: { label: 'Em andamento', color: 'warning' },
  pending: { label: 'Pendente', color: 'informative' },
  failed: { label: 'Falhou', color: 'danger' },
};

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function WorkflowList({ workflows }: WorkflowListProps) {
  if (workflows.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8">
        <Text className="text-text-secondary">
          Nenhum workflow encontrado.
        </Text>
        <Text size={200} className="text-text-tertiary">
          Seus workflows iniciados aparecerão aqui.
        </Text>
      </div>
    );
  }

  return (
    <Table aria-label="Workflows recentes">
      <TableHeader>
        <TableRow>
          <TableHeaderCell>Nome</TableHeaderCell>
          <TableHeaderCell>Tipo</TableHeaderCell>
          <TableHeaderCell>Status</TableHeaderCell>
          <TableHeaderCell>Data</TableHeaderCell>
        </TableRow>
      </TableHeader>
      <TableBody>
        {workflows.map((workflow) => {
          const status = statusConfig[workflow.status];
          return (
            <TableRow key={workflow.id}>
              <TableCell>
                <Text weight="semibold">{workflow.name}</Text>
              </TableCell>
              <TableCell>
                <Text size={200}>{workflow.type}</Text>
              </TableCell>
              <TableCell>
                <Badge appearance="filled" color={status.color} size="small">
                  {status.label}
                </Badge>
              </TableCell>
              <TableCell>
                <Text size={200} className="text-text-secondary">
                  {formatDate(workflow.created_at)}
                </Text>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
