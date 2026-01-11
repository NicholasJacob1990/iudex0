'use client';

import { Search, Bell, HelpCircle, Sparkles, Moon, Sun, Menu } from 'lucide-react';
import { useTheme } from 'next-themes';
import { useAuthStore, useUIStore } from '@/stores';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export function TopNav() {
  const { user } = useAuthStore();
  const { toggleSidebar } = useUIStore();
  const { theme, setTheme } = useTheme();

  const firstName = user?.name?.split(' ')[0] ?? 'Usuário';

  return (
    <header className="sticky top-0 z-40 h-14 flex-none border-b border-slate-200/60 bg-white/80 backdrop-blur-xl">
      <div className="flex h-full items-center justify-between gap-4 px-4 md:px-6">
        {/* Left: Menu toggle (mobile) */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white shadow-sm lg:hidden hover:bg-slate-50 transition"
            onClick={toggleSidebar}
            aria-label="Alternar menu"
          >
            <Menu className="h-4 w-4 text-slate-600" />
          </button>
        </div>

        {/* Center: Search */}
        <div className="relative flex-1 max-w-lg">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            className="h-9 w-full rounded-lg border-slate-200 bg-slate-50/50 pl-9 pr-4 text-sm focus-visible:ring-1 focus-visible:ring-indigo-500/50 focus-visible:border-indigo-300"
            placeholder="Buscar documentos, legislação..."
          />
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-1.5">
          <Button
            variant="ghost"
            size="icon"
            className="h-9 w-9 rounded-lg text-slate-500 hover:text-slate-700 hover:bg-slate-100"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          >
            {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>

          <IconButton icon={Sparkles} label="Insights da IA" />
          <IconButton icon={HelpCircle} label="Central de ajuda" />
          <IconButton icon={Bell} label="Notificações" indicator />

          {/* User Avatar */}
          <div className="ml-1 flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-2 py-1 shadow-sm">
            <div className="h-7 w-7 rounded-full bg-indigo-100 text-center text-sm font-semibold leading-7 text-indigo-600">
              {firstName.charAt(0).toUpperCase()}
            </div>
            <span className="hidden text-sm font-medium text-slate-700 md:inline">{firstName}</span>
          </div>
        </div>
      </div>
    </header>
  );
}

interface IconButtonProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  indicator?: boolean;
}

function IconButton({ icon: Icon, label, indicator }: IconButtonProps) {
  return (
    <button
      type="button"
      className="relative flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
      aria-label={label}
      title={label}
    >
      <Icon className="h-4 w-4" />
      {indicator && (
        <span
          className={cn(
            'absolute right-1.5 top-1.5 h-2 w-2 rounded-full',
            'bg-rose-500 animate-pulse'
          )}
        />
      )}
    </button>
  );
}
