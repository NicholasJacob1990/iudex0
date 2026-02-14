import { useAuthStore } from '@/stores/auth-store';
import {
  Button,
  Spinner,
  Text,
  Title3,
} from '@fluentui/react-components';
import { PersonRegular } from '@fluentui/react-icons';

export function LoginForm() {
  const { login, isLoading, error, clearError } = useAuthStore();

  const handleLogin = async () => {
    clearError();
    try {
      await login();
    } catch {
      // Erro tratado pelo store
    }
  };

  return (
    <div className="flex h-full flex-col items-center justify-center p-office-lg">
      <div className="w-full max-w-[280px] text-center">
        {/* Logo */}
        <div className="mb-6">
          <Title3 className="text-brand">Vorbium</Title3>
          <Text size={200} className="mt-1 block text-text-secondary">
            IA Juridica para Microsoft Outlook
          </Text>
        </div>

        {/* Microsoft SSO Button */}
        <Button
          appearance="primary"
          size="large"
          icon={<PersonRegular />}
          onClick={handleLogin}
          disabled={isLoading}
          className="w-full"
        >
          {isLoading ? (
            <Spinner size="tiny" label="Entrando..." />
          ) : (
            'Entrar com Microsoft'
          )}
        </Button>

        {/* Error message */}
        {error && (
          <p className="mt-3 rounded bg-red-50 p-2 text-office-sm text-status-error">
            {error}
          </p>
        )}

        <Text size={100} className="mt-4 block text-text-tertiary">
          Use sua conta Microsoft organizacional
        </Text>
      </div>
    </div>
  );
}
