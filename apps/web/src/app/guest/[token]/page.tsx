'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Users, Shield, Clock, ArrowRight, LogIn } from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || '/api';

interface GuestSessionResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  guest: {
    id: string;
    display_name: string;
    is_guest: boolean;
    expires_at: string;
    space_id: string | null;
    permissions: Record<string, unknown>;
    created_at: string;
  };
}

export default function GuestAccessPage({ params }: { params: { token: string } }) {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState('');

  const handleGuestAccess = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_URL}/auth/guest/from-share/${params.token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          display_name: displayName.trim() || undefined,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Erro ao criar sessao de visitante');
      }

      const data: GuestSessionResponse = await res.json();

      // Salvar tokens guest no localStorage
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('guest_session', JSON.stringify(data.guest));

      // Atualizar auth-storage do Zustand
      const authStorage = {
        state: {
          user: {
            id: data.guest.id,
            name: data.guest.display_name,
            email: '',
            role: 'GUEST',
            plan: 'FREE',
            account_type: 'GUEST',
            organization_id: null,
            created_at: data.guest.created_at,
            is_guest: true,
          },
          isAuthenticated: true,
          isGuest: true,
          guestSession: data.guest,
        },
        version: 0,
      };
      localStorage.setItem('auth-storage', JSON.stringify(authStorage));

      // Redirecionar para o space se disponivel
      if (data.guest.space_id) {
        router.push(`/collaboration/spaces/${data.guest.space_id}`);
      } else {
        router.push('/');
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Erro inesperado';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSignIn = () => {
    // Salvar token de share para usar apos login
    localStorage.setItem('pending_share_token', params.token);
    router.push('/auth');
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-indigo-900 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Card principal */}
        <div className="bg-white/10 backdrop-blur-xl rounded-2xl border border-white/20 overflow-hidden">
          {/* Header */}
          <div className="bg-gradient-to-r from-indigo-600/30 to-purple-600/30 px-6 py-8 text-center">
            <div className="bg-indigo-500/20 p-4 rounded-full w-16 h-16 mx-auto mb-4 flex items-center justify-center">
              <Users className="h-8 w-8 text-indigo-300" />
            </div>
            <h1 className="text-2xl font-bold text-white mb-2">
              Acesso Compartilhado
            </h1>
            <p className="text-slate-300 text-sm">
              Voce recebeu um convite para visualizar documentos no Iudex
            </p>
          </div>

          {/* Body */}
          <div className="px-6 py-6 space-y-4">
            {/* Informacoes de acesso */}
            <div className="flex items-start gap-3 text-sm text-slate-300">
              <Shield className="h-4 w-4 mt-0.5 text-green-400 shrink-0" />
              <span>Acesso somente leitura, seguro e controlado</span>
            </div>
            <div className="flex items-start gap-3 text-sm text-slate-300">
              <Clock className="h-4 w-4 mt-0.5 text-amber-400 shrink-0" />
              <span>Sessao temporaria valida por 24 horas</span>
            </div>

            {/* Nome do visitante (opcional) */}
            <div>
              <label htmlFor="display-name" className="block text-sm font-medium text-slate-300 mb-1.5">
                Seu nome (opcional)
              </label>
              <input
                id="display-name"
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Visitante"
                className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent text-sm"
                maxLength={200}
              />
            </div>

            {/* Erro */}
            {error && (
              <div className="bg-red-500/20 border border-red-500/30 rounded-lg px-3 py-2 text-sm text-red-300">
                {error}
              </div>
            )}

            {/* Botao principal: continuar como visitante */}
            <button
              onClick={handleGuestAccess}
              disabled={isLoading}
              className="w-full flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-600/50 text-white font-medium py-2.5 px-4 rounded-lg transition-colors text-sm"
            >
              {isLoading ? (
                <div className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <>
                  Continuar como Visitante
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>

            {/* Divider */}
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-white/10" />
              </div>
              <div className="relative flex justify-center text-xs">
                <span className="px-2 bg-transparent text-slate-500">ou</span>
              </div>
            </div>

            {/* Login para acesso completo */}
            <button
              onClick={handleSignIn}
              className="w-full flex items-center justify-center gap-2 bg-white/10 hover:bg-white/20 border border-white/20 text-white font-medium py-2.5 px-4 rounded-lg transition-colors text-sm"
            >
              <LogIn className="h-4 w-4" />
              Entrar para acesso completo
            </button>
          </div>
        </div>

        {/* Footer */}
        <p className="text-center text-xs text-slate-500 mt-4">
          Powered by Iudex — Plataforma Juridica com IA
        </p>
      </div>
    </div>
  );
}
