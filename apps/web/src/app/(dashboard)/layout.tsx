'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores';
import { TopNav, SidebarPro } from '@/components/layout';
import { ResourceDock, PromptFooter, FloatingControls } from '@/components/dashboard';
import { useUIStore } from '@/stores';

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { isAuthenticated, fetchProfile } = useAuthStore();
  const { sidebarOpen, setSidebarOpen } = useUIStore();

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/login');
    } else {
      fetchProfile();
    }
  }, [isAuthenticated, router, fetchProfile]);

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <div
        className={`fixed inset-0 z-30 bg-black/20 transition-opacity lg:hidden ${
          sidebarOpen ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
        onClick={() => setSidebarOpen(false)}
      />
      <SidebarPro />
      <div className="flex flex-1 flex-col">
        <TopNav />
        <div className="flex flex-1 overflow-hidden">
          <main className="flex-1 overflow-y-auto px-4 pb-32 pt-6 md:px-8">{children}</main>
          <ResourceDock />
        </div>
        <PromptFooter />
      </div>
      <FloatingControls />
    </div>
  );
}

