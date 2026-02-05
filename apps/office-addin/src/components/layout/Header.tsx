import { useAuthStore } from '@/stores/auth-store';
import { useDocumentStore } from '@/stores/document-store';

export function Header() {
  const { user, logout } = useAuthStore();
  const metadata = useDocumentStore((s) => s.metadata);

  return (
    <header className="flex items-center justify-between border-b border-gray-200 px-office-md py-office-sm">
      <div className="flex items-center gap-2">
        <span className="text-office-lg font-bold text-brand">Vorbium</span>
        {metadata && (
          <span
            className="max-w-[120px] truncate text-office-xs text-text-tertiary"
            title={metadata.title}
          >
            {metadata.title}
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
