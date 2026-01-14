'use client';

import { SidebarPro } from './sidebar-pro';
import { cn } from '@/lib/utils';
import { Menu } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useUIStore } from '@/stores';

interface MainLayoutProps {
    children: React.ReactNode;
}

export function MainLayout({ children }: MainLayoutProps) {
    const { sidebarState, setSidebarState } = useUIStore();

    return (
        <div className="flex h-screen overflow-hidden bg-background">
            {/* Mobile Sidebar Overlay */}
            <div
                className={cn(
                    'fixed inset-0 z-40 bg-black/50 backdrop-blur-sm transition-opacity lg:hidden',
                    sidebarState !== 'hidden' ? 'opacity-100' : 'pointer-events-none opacity-0'
                )}
                onClick={() => setSidebarState('hidden')}
            />

            {/* Sidebar */}
            <div
                className={cn(
                    'fixed inset-y-0 left-0 z-50 w-72 transform transition-transform duration-300 ease-in-out lg:static lg:translate-x-0',
                    sidebarState !== 'hidden' ? 'translate-x-0' : '-translate-x-full',
                    sidebarState === 'collapsed' && 'lg:w-16',
                    sidebarState === 'expanded' && 'lg:w-72',
                    sidebarState === 'hidden' && 'lg:w-0 lg:pointer-events-none'
                )}
            >
                <SidebarPro />
            </div>

            {/* Main Content */}
            <div className="flex min-w-0 flex-1 flex-col transition-all duration-300">
                {/* Mobile Header */}
                <header className="flex h-16 items-center justify-between border-b border-border bg-background/80 px-4 backdrop-blur-md lg:hidden">
                    <div className="flex items-center gap-3">
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setSidebarState('expanded')}
                            className="lg:hidden"
                        >
                            <Menu className="h-5 w-5" />
                        </Button>
                        <span className="font-display text-lg font-semibold">Iudex</span>
                    </div>
                </header>

                <main className="flex-1 overflow-hidden">
                    {children}
                </main>
            </div>
        </div>
    );
}
