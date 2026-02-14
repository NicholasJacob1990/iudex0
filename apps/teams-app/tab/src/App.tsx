import { useEffect, useState } from 'react';
import { app } from '@microsoft/teams-js';
import { Spinner, Title1, Text } from '@fluentui/react-components';
import { useAuthStore } from '@/stores/auth-store';
import { loginWithTeamsSSO } from '@/auth/teams-auth';
import { Dashboard } from '@/components/Dashboard';

type InitState = 'loading' | 'ready' | 'error';

export function App() {
  const [initState, setInitState] = useState<InitState>('loading');
  const [errorMessage, setErrorMessage] = useState<string>('');
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const setAuth = useAuthStore((s) => s.setAuth);

  useEffect(() => {
    async function initialize() {
      try {
        await app.initialize();

        if (!isAuthenticated) {
          const authResponse = await loginWithTeamsSSO();
          setAuth(authResponse.user, authResponse.access_token, authResponse.refresh_token);
        }

        setInitState('ready');
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Erro ao inicializar o Teams SDK';
        setErrorMessage(message);
        setInitState('error');
      }
    }

    initialize();
  }, [isAuthenticated, setAuth]);

  if (initState === 'loading') {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Spinner size="large" />
          <Text>Inicializando Vorbium...</Text>
        </div>
      </div>
    );
  }

  if (initState === 'error') {
    return (
      <div className="flex h-screen items-center justify-center p-8">
        <div className="flex flex-col items-center gap-4 text-center">
          <Title1>Erro ao carregar</Title1>
          <Text>{errorMessage}</Text>
          <Text size={200} className="text-text-secondary">
            Verifique se o app esta sendo executado dentro do Microsoft Teams.
          </Text>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen w-full overflow-hidden bg-surface">
      <Dashboard />
    </div>
  );
}
