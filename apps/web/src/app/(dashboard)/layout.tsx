'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore, useChatStore } from '@/stores';
import { TopNav, SidebarPro } from '@/components/layout';
import { useUIStore } from '@/stores';
import { useTheme } from 'next-themes';
import { tintToColor, deriveTintTokens, LIGHT_STOPS, DARK_STOPS } from '@/components/layout/top-nav';
import { HumanReviewModal } from '@/components/chat/human-review-modal';
import { PageTransition } from '@/components/providers/page-transition';
import { Scale } from 'lucide-react';

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const { isAuthenticated, fetchProfile, isLoading, user, isGuest } = useAuthStore();
  const { sidebarState, setSidebarState, chatBgTintLight, chatBgTintDark, tintMode } = useUIStore();
  const { reviewData, submitReview } = useChatStore();
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';
  const isGuestSession =
    isGuest ||
    user?.is_guest === true ||
    String(user?.role || '').toUpperCase() === 'GUEST';
  const activeTint = isDark ? chatBgTintDark : chatBgTintLight;
  const contentBg = useMemo(
    () => tintToColor(activeTint, isDark ? DARK_STOPS : LIGHT_STOPS),
    [activeTint, isDark],
  );
  const tintTokens = useMemo(
    () => deriveTintTokens(contentBg, isDark),
    [contentBg, isDark],
  );
  const [isHydrated, setIsHydrated] = useState(false);

  // Aguardar hidratação do Zustand persist
  useEffect(() => {
    setIsHydrated(true);
  }, []);

  // Sync sidebar theme whenever the page theme changes (covers system pref changes too)
  useEffect(() => {
    if (!resolvedTheme) return;
    useUIStore.getState().syncSidebarTheme(resolvedTheme === 'dark' ? 'dark' : 'light');
  }, [resolvedTheme]);

  useEffect(() => {
    if (!isHydrated || isLoading) return;

    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    const hasGuestSession =
      typeof window !== 'undefined' ? !!localStorage.getItem('guest_session') : false;
    console.log('[DashboardLayout] Auth check:', { isAuthenticated, hasToken: !!token, tokenPreview: token?.substring(0, 20) });

    if (token && (isGuestSession || hasGuestSession)) {
      return;
    }

    if (!isAuthenticated && !token) {
      console.log('[DashboardLayout] Sem auth e sem token, redirecionando para login');
      router.push('/login');
    } else if (token) {
      // Verify token is still valid by fetching profile
      console.log('[DashboardLayout] Token encontrado, verificando com fetchProfile...');
      fetchProfile()
        .then(() => {
          console.log('[DashboardLayout] fetchProfile OK!');
        })
        .catch((err) => {
          // If fetchProfile fails (403/401), the token is invalid
          // Clear any stale auth state and redirect to login
          console.error('[DashboardLayout] fetchProfile FALHOU:', err?.response?.status, err?.response?.data || err?.message);
          if (typeof window !== 'undefined') {
            localStorage.removeItem('access_token');
            localStorage.removeItem('refresh_token');
            localStorage.removeItem('auth-storage');
          }
          router.push('/login');
        });
    } else if (isAuthenticated && !token) {
      // isAuthenticated is true in zustand store but no token exists
      // This is a stale state, clear it and redirect
      console.warn('[DashboardLayout] Estado de auth inconsistente, redirecionando para login');
      if (typeof window !== 'undefined') {
        localStorage.removeItem('auth-storage');
      }
      router.push('/login');
    }
  }, [isAuthenticated, isGuestSession, isHydrated, isLoading, router, fetchProfile]);

  // Mostrar loading enquanto hidrata ou verifica autenticação
  if (!isHydrated || isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4 animate-blur-in">
          <div className="relative flex h-14 w-14 items-center justify-center">
            <div className="absolute inset-0 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 animate-spin [animation-duration:3s]" />
            <div className="absolute inset-[2px] rounded-[10px] bg-background" />
            <Scale className="relative h-6 w-6 text-indigo-500" />
          </div>
          <p className="text-sm text-muted-foreground animate-pulse">Carregando Iudex...</p>
        </div>
      </div>
    );
  }

  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;

  if (!isAuthenticated && !token) {
    return null;
  }

  return (
    <div
      className={`dashboard-shell flex h-screen overflow-hidden bg-background${tintMode === 'uniform' ? ' tint-homogenized' : ''}${tintMode === 'blended' ? ' tint-blended' : ''}${tintMode === 'inset' ? ' tint-inset' : ''}`}
      style={tintTokens as React.CSSProperties}
    >
      <div
        className={`fixed inset-0 z-30 bg-black/20 transition-opacity lg:hidden ${sidebarState !== 'hidden' ? 'opacity-100' : 'pointer-events-none opacity-0'
          }`}
        onClick={() => setSidebarState('hidden')}
      />
      <SidebarPro />
      <div className="flex flex-1 flex-col">
        <TopNav />
        <div className="flex flex-1 min-h-0 overflow-hidden transition-colors duration-500 ease-out bg-background">
          <main className={`flex-1 min-h-0 ${pathname?.startsWith('/minuta') || pathname?.startsWith('/ask') ? 'flex h-full flex-col p-0 overflow-hidden' : 'overflow-y-auto px-4 pt-4 md:px-6 pb-4'}`}>
            <PageTransition>{children}</PageTransition>
          </main>
        </div>
      </div>
      <HumanReviewModal
        isOpen={!!reviewData}
        data={reviewData}
        onSubmit={submitReview}
      />
    </div>
  );
}
