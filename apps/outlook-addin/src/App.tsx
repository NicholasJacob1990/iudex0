import { useAuthStore } from '@/stores/auth-store';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { TaskPane } from '@/components/layout/TaskPane';

export function App() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  return (
    <div className="h-screen w-full overflow-hidden bg-surface">
      {isAuthenticated ? <TaskPane /> : <AuthGuard />}
    </div>
  );
}
