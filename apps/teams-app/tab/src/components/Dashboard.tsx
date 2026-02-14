import { useEffect } from 'react';
import {
  Card,
  CardHeader,
  Title2,
  Text,
  Badge,
  Button,
  Spinner,
  Divider,
} from '@fluentui/react-components';
import {
  ArrowSyncRegular,
  SearchRegular,
  DocumentFlowchartRegular,
  AlertRegular,
} from '@fluentui/react-icons';
import { useDashboardStore } from '@/stores/dashboard-store';
import { useAuthStore } from '@/stores/auth-store';
import { WorkflowList } from './WorkflowList';
import { CorpusSearch } from './CorpusSearch';

export function Dashboard() {
  const user = useAuthStore((s) => s.user);
  const {
    workflows,
    workflowsLoading,
    notifications,
    notificationsLoading,
    refreshAll,
  } = useDashboardStore();

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  const unreadCount = notifications.filter((n) => !n.read).length;

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
        <div>
          <Title2>Dashboard</Title2>
          {user && (
            <Text size={200} className="text-text-secondary">
              Bem-vindo, {user.name}
            </Text>
          )}
        </div>
        <Button
          appearance="subtle"
          icon={<ArrowSyncRegular />}
          onClick={() => refreshAll()}
        >
          Atualizar
        </Button>
      </div>

      <div className="flex-1 space-y-6 p-6">
        {/* Quick Actions */}
        <div className="grid grid-cols-3 gap-4">
          <Card className="cursor-pointer hover:shadow-md">
            <CardHeader
              image={<SearchRegular className="text-brand text-xl" />}
              header={<Text weight="semibold">Pesquisar</Text>}
              description={<Text size={200}>Buscar no corpus</Text>}
            />
          </Card>

          <Card className="cursor-pointer hover:shadow-md">
            <CardHeader
              image={<DocumentFlowchartRegular className="text-brand text-xl" />}
              header={<Text weight="semibold">Workflows</Text>}
              description={<Text size={200}>Ver atividades</Text>}
            />
          </Card>

          <Card className="cursor-pointer hover:shadow-md">
            <CardHeader
              image={<AlertRegular className="text-brand text-xl" />}
              header={
                <div className="flex items-center gap-2">
                  <Text weight="semibold">Alertas</Text>
                  {unreadCount > 0 && (
                    <Badge appearance="filled" color="danger" size="small">
                      {unreadCount}
                    </Badge>
                  )}
                </div>
              }
              description={<Text size={200}>Notificacoes</Text>}
            />
          </Card>
        </div>

        <Divider />

        {/* Corpus Search */}
        <section>
          <Title2 className="mb-4">Pesquisa Rapida</Title2>
          <CorpusSearch />
        </section>

        <Divider />

        {/* Recent Workflows */}
        <section>
          <Title2 className="mb-4">Workflows Recentes</Title2>
          {workflowsLoading ? (
            <div className="flex justify-center py-8">
              <Spinner size="medium" />
            </div>
          ) : (
            <WorkflowList workflows={workflows} />
          )}
        </section>

        {/* Notifications */}
        {notificationsLoading ? null : notifications.length > 0 && (
          <section>
            <Divider />
            <Title2 className="mb-4 mt-6">Notificacoes Recentes</Title2>
            <div className="space-y-2">
              {notifications.slice(0, 5).map((notification) => (
                <Card key={notification.id} size="small">
                  <CardHeader
                    header={
                      <div className="flex items-center gap-2">
                        <Text weight={notification.read ? 'regular' : 'semibold'}>
                          {notification.title}
                        </Text>
                        {!notification.read && (
                          <Badge appearance="filled" color="brand" size="tiny">
                            Novo
                          </Badge>
                        )}
                      </div>
                    }
                    description={
                      <Text size={200} className="text-text-secondary">
                        {notification.message}
                      </Text>
                    }
                  />
                </Card>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
