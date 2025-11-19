'use client';

import { useMemo } from 'react';
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

  const greeting = useMemo(() => {
    const now = new Date().getHours();
    if (now < 12) return 'Bom dia';
    if (now < 18) return 'Boa tarde';
    return 'Boa noite';
  }, []);

  const firstName = user?.name?.split(' ')[0] ?? 'jurista';

  return (
    <header className="sticky top-0 z-40 border-b border-outline/60 bg-panel/80 backdrop-blur-2xl">
      <div className="flex flex-col gap-4 px-6 py-4 md:flex-row md:items-center md:justify-between">
        <div className="flex items-start gap-3">
          <button
            type="button"
            className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-white/70 bg-white/80 shadow-soft lg:hidden"
            onClick={toggleSidebar}
            aria-label="Alternar menu"
          >
            <Menu className="h-4 w-4" />
          </button>
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">{greeting}</p>
            <h1 className="font-display text-2xl font-semibold text-foreground">
              {firstName}, o futuro jurídico está pronto.
            </h1>
          </div>
        </div>

        <div className="flex flex-1 flex-col gap-3 md:flex-row md:items-center md:justify-end">
          <div className="relative flex-1 md:max-w-[360px]">
            <Search className="absolute left-4 top-3 h-4 w-4 text-muted-foreground" />
            <Input
              className="h-11 rounded-full border-transparent bg-white/80 pl-11 pr-4 shadow-soft focus-visible:ring-0"
              placeholder="Busque minutas, legislações, processos CNJ..."
            />
          </div>

          <div className="flex items-center justify-end gap-2">
            <Button
              variant="ghost"
              size="icon"
              className="rounded-full border border-white/60 bg-white/70 shadow-soft hover:bg-white"
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            >
              {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>

            <IconButton icon={Sparkles} label="Insights da IA" />
            <IconButton icon={HelpCircle} label="Central de ajuda" />
            <IconButton icon={Bell} label="Notificações" indicator />

            <div className="flex items-center gap-2 rounded-full border border-white/70 bg-white px-3 py-1 shadow-soft">
              <div className="h-8 w-8 rounded-full bg-primary/10 text-center text-sm font-semibold leading-8 text-primary">
                {firstName.charAt(0).toUpperCase()}
              </div>
              <div className="hidden text-left md:block">
                <p className="text-xs font-semibold leading-tight">{firstName}</p>
                <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  Conta profissional
                </p>
              </div>
            </div>
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
      className="relative flex h-11 w-11 items-center justify-center rounded-full border border-white/70 bg-white/80 shadow-soft transition hover:-translate-y-0.5 hover:bg-white"
      aria-label={label}
      title={label}
    >
      <Icon className="h-4 w-4 text-foreground" />
      {indicator ? (
        <span
          className={cn(
            'absolute right-2 top-2 h-2 w-2 rounded-full',
            'bg-gradient-to-r from-rose-500 to-primary animate-pulse'
          )}
        />
      ) : null}
    </button>
  );
}

