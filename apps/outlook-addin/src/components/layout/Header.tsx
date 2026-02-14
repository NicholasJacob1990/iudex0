import { useAuthStore } from '@/stores/auth-store';
import { useEmailStore } from '@/stores/email-store';

export function Header() {
  const { user, logout } = useAuthStore();
  const currentEmail = useEmailStore((s) => s.currentEmail);

  return (
    <header className="flex items-center justify-between border-b border-gray-200 px-office-md py-office-sm">
      <div className="flex items-center gap-2">
        <span className="text-office-lg font-bold text-brand">Vorbium</span>
        {currentEmail && (
          <span
            className="max-w-[120px] truncate text-office-xs text-text-tertiary"
            title={currentEmail.subject}
          >
            {currentEmail.subject}
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        {user && (
          <span
            className="max-w-[80px] truncate text-office-xs text-text-secondary"
            title={user.name}
          >
            {user.name.split(' ')[0]}
          </span>
        )}
        <button
          onClick={logout}
          className="rounded px-2 py-1 text-office-xs text-text-tertiary hover:bg-surface-tertiary hover:text-text-secondary"
        >
          Sair
        </button>
      </div>
    </header>
  );
}
