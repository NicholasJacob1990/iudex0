import { useState, type FormEvent } from 'react';
import { useAuthStore } from '@/stores/auth-store';

export function LoginForm() {
  const { login, loginWithMicrosoft, isLoading, error, clearError } =
    useAuthStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showEmailLogin, setShowEmailLogin] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    clearError();
    try {
      await login(email, password);
    } catch {
      // Error is handled by the store
    }
  };

  const handleMicrosoftLogin = async () => {
    clearError();
    try {
      await loginWithMicrosoft();
    } catch {
      // Error is handled by the store
    }
  };

  return (
    <div className="flex h-full flex-col items-center justify-center p-office-lg">
      <div className="w-full max-w-[280px]">
        {/* Logo */}
        <div className="mb-6 text-center">
          <h1 className="text-xl font-bold text-brand">Vorbium</h1>
          <p className="mt-1 text-office-sm text-text-secondary">
            IA Juridica para Microsoft Word
          </p>
        </div>

        {/* Microsoft SSO - Primary */}
        <button
          type="button"
          onClick={handleMicrosoftLogin}
          disabled={isLoading}
          className="office-btn-primary flex w-full items-center justify-center gap-2"
        >
          <svg width="16" height="16" viewBox="0 0 21 21" fill="none">
            <rect x="1" y="1" width="9" height="9" fill="#F25022" />
            <rect x="11" y="1" width="9" height="9" fill="#7FBA00" />
            <rect x="1" y="11" width="9" height="9" fill="#00A4EF" />
            <rect x="11" y="11" width="9" height="9" fill="#FFB900" />
          </svg>
          {isLoading ? 'Entrando...' : 'Entrar com Microsoft'}
        </button>

        {error && (
          <p className="mt-3 rounded bg-red-50 p-2 text-office-sm text-status-error">
            {error}
          </p>
        )}

        {/* Divider + email/password fallback */}
        {!showEmailLogin ? (
          <button
            type="button"
            onClick={() => setShowEmailLogin(true)}
            className="mt-4 w-full text-center text-office-xs text-text-tertiary hover:text-text-secondary"
          >
            Entrar com email e senha
          </button>
        ) : (
          <>
            <div className="my-4 flex items-center gap-2">
              <div className="h-px flex-1 bg-border-light" />
              <span className="text-office-xs text-text-tertiary">ou</span>
              <div className="h-px flex-1 bg-border-light" />
            </div>

            <form onSubmit={handleSubmit} className="space-y-3">
              <div>
                <label
                  htmlFor="email"
                  className="mb-1 block text-office-sm font-medium text-text-secondary"
                >
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="office-input"
                  placeholder="seu@email.com"
                  required
                  disabled={isLoading}
                />
              </div>

              <div>
                <label
                  htmlFor="password"
                  className="mb-1 block text-office-sm font-medium text-text-secondary"
                >
                  Senha
                </label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="office-input"
                  placeholder="Sua senha"
                  required
                  disabled={isLoading}
                />
              </div>

              <button
                type="submit"
                disabled={isLoading || !email || !password}
                className="office-btn-primary w-full"
              >
                {isLoading ? 'Entrando...' : 'Entrar'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
