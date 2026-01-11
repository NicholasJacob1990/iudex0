'use client';

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore } from '@/stores';
import { TopNav, SidebarPro } from '@/components/layout';
import { useUIStore } from '@/stores';

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const { isAuthenticated, fetchProfile, isLoading } = useAuthStore();
  const { sidebarOpen, setSidebarOpen } = useUIStore();
  const [isHydrated, setIsHydrated] = useState(false);

  // Aguardar hidratação do Zustand persist
  useEffect(() => {
    setIsHydrated(true);
  }, []);

  useEffect(() => {
    if (!isHydrated || isLoading) return;

    if (!isAuthenticated) {
      router.push('/login');
    } else {
      fetchProfile();
    }
  }, [isAuthenticated, isHydrated, isLoading, router, fetchProfile]);

  // Mostrar loading enquanto hidrata ou verifica autenticação
  if (!isHydrated || isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-primary border-r-transparent"></div>
          <p className="mt-4 text-sm text-muted-foreground">Carregando...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <div
        className={`fixed inset-0 z-30 bg-black/20 transition-opacity lg:hidden ${sidebarOpen ? 'opacity-100' : 'pointer-events-none opacity-0'
          }`}
        onClick={() => setSidebarOpen(false)}
      />
      <SidebarPro />
      <div className="flex flex-1 flex-col">
        <TopNav />
        <div className="flex flex-1 min-h-0 overflow-hidden">
          <main className={`flex-1 min-h-0 ${pathname === '/minuta' ? 'flex h-full flex-col p-0 overflow-hidden' : 'overflow-y-auto px-4 pt-4 md:px-6 pb-4'}`}>{children}</main>
        </div>
      </div>
    </div>
  );
}
