import { useState, type FormEvent } from 'react';
import { useAuthStore } from '@/stores/auth-store';

export function LoginForm() {
  const { login, isLoading, error, clearError } = useAuthStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    clearError();
    try {
      await login(email, password);
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
            IA Jurídica para Microsoft Word
          </p>
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

          {error && (
            <p className="rounded bg-red-50 p-2 text-office-sm text-status-error">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={isLoading || !email || !password}
            className="office-btn-primary w-full"
          >
            {isLoading ? 'Entrando...' : 'Entrar'}
          </button>
        </form>

        <p className="mt-4 text-center text-office-xs text-text-tertiary">
          Use suas credenciais do Vorbium
        </p>
      </div>
    </div>
  );
}
