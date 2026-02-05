'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Clock, UserPlus, X } from 'lucide-react';

interface GuestSession {
  id: string;
  display_name: string;
  is_guest: boolean;
  expires_at: string;
  space_id: string | null;
  permissions: Record<string, unknown>;
  created_at: string;
}

export function GuestBanner() {
  const router = useRouter();
  const [guestSession, setGuestSession] = useState<GuestSession | null>(null);
  const [timeLeft, setTimeLeft] = useState('');
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem('guest_session');
      if (stored) {
        const session: GuestSession = JSON.parse(stored);
        if (session.is_guest) {
          setGuestSession(session);
        }
      }
    } catch {
      // Ignorar erros de parse
    }
  }, []);

  useEffect(() => {
    if (!guestSession) return;

    const updateTimeLeft = () => {
      const expiresAt = new Date(guestSession.expires_at).getTime();
      const now = Date.now();
      const diff = expiresAt - now;

      if (diff <= 0) {
        // Sessao expirada — limpar e redirecionar
        localStorage.removeItem('access_token');
        localStorage.removeItem('guest_session');
        localStorage.removeItem('auth-storage');
        router.push('/auth');
        return;
      }

      const hours = Math.floor(diff / (1000 * 60 * 60));
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));

      if (hours > 0) {
        setTimeLeft(`${hours}h ${minutes}min`);
      } else {
        setTimeLeft(`${minutes}min`);
      }
    };

    updateTimeLeft();
    const interval = setInterval(updateTimeLeft, 60000); // Atualizar a cada minuto

    return () => clearInterval(interval);
  }, [guestSession, router]);

  if (!guestSession || dismissed) return null;

  return (
    <div className="bg-amber-500/10 border-b border-amber-500/20 px-4 py-2">
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 text-sm">
          <Clock className="h-4 w-4 text-amber-500 shrink-0" />
          <span className="text-amber-700 dark:text-amber-300">
            Acesso como visitante
            {guestSession.display_name !== 'Visitante' && (
              <> ({guestSession.display_name})</>
            )}
            {' '}&mdash; Expira em {timeLeft}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => router.push('/auth')}
            className="flex items-center gap-1.5 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 transition-colors bg-indigo-50 dark:bg-indigo-500/10 px-3 py-1.5 rounded-md"
          >
            <UserPlus className="h-3.5 w-3.5" />
            Criar conta
          </button>
          <button
            onClick={() => setDismissed(true)}
            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 p-1"
            aria-label="Fechar banner"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
