'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Home,
  PenTool,
  Upload,
  Layers,
  Scale,
  Gavel,
  Library,
  Globe,
  Users,
  Share2,
  Mic,
  Bot,
} from 'lucide-react';
import { Input } from '@/components/ui/input';
import { cn, formatDate } from '@/lib/utils';
import { resourceShortcuts, minuteHistory } from '@/data/mock';
import { useUIStore } from '@/stores';

const mainNav = [
  { href: '/dashboard', label: 'Início', icon: Home },
  { href: '/minuta', label: 'Minuta', icon: PenTool },
  { href: '/documents', label: 'Documentos', icon: Upload },
  { href: '/models', label: 'Modelos', icon: Layers },
  { href: '/legislation', label: 'Legislação', icon: Scale },
  { href: '/jurisprudence', label: 'Jurisprudência', icon: Gavel },
  { href: '/web', label: 'Web', icon: Globe },
  { href: '/library', label: 'Biblioteca', icon: Library },
];

const resourceIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  Podcasts: Mic,
  Diagramas: Share2,
  Compartilhamentos: Users,
  'Metadados CNJ': Scale,
  'Comunicações DJEN': Bot,
};

export function SidebarPro() {
  const pathname = usePathname();
  const { sidebarOpen, setSidebarOpen } = useUIStore();

  return (
    <aside
      className={cn(
        'flex h-full w-72 flex-col border-r border-white/5 bg-[#0F1115] text-sidebar-fg transition-all duration-300',
        !sidebarOpen && 'lg:hidden'
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-8">
        <div className="flex items-center gap-3">
          <div className="group flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 shadow-lg shadow-indigo-500/20 transition-all duration-300 hover:shadow-indigo-500/40">
            <Scale className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display text-xl font-bold tracking-tight text-white">Iudex</h1>
            <p className="text-[10px] font-medium uppercase tracking-wider text-indigo-400/80">
              Intelligent Workspace
            </p>
          </div>
        </div>
        <button
          onClick={() => setSidebarOpen(false)}
          className="rounded-lg p-1 text-muted-foreground hover:bg-white/10 hover:text-white lg:hidden"
        >
          ✕
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-4 py-6">
        {mainNav.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'group flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-all duration-300',
                isActive
                  ? 'bg-white/10 text-white shadow-inner shadow-white/5 ring-1 ring-white/10'
                  : 'text-muted-foreground hover:bg-white/5 hover:text-white hover:pl-5'
              )}
            >
              <Icon className={cn('h-4 w-4 transition-colors', isActive ? 'text-indigo-400' : 'text-muted-foreground group-hover:text-indigo-300')} />
              {item.label}
              {isActive && (
                <div className="ml-auto h-1.5 w-1.5 rounded-full bg-indigo-400 shadow-[0_0_8px_rgba(129,140,248,0.8)]" />
              )}
            </Link>
          );
        })}

        <div className="my-6 border-t border-white/5 px-2 py-6">
          <p className="mb-4 px-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground/40">
            Ferramentas Rápidas
          </p>
          <div className="space-y-1">
            {resourceShortcuts.slice(0, 3).map((shortcut) => {
              const Icon = resourceIcons[shortcut.label] ?? Share2;
              return (
                <button
                  key={shortcut.id}
                  className="group flex w-full items-center gap-3 rounded-lg px-3 py-2 text-xs font-medium text-muted-foreground transition-all hover:bg-white/5 hover:text-white"
                >
                  <div className="flex h-6 w-6 items-center justify-center rounded-md bg-white/5 transition-colors group-hover:bg-indigo-500/20">
                    <Icon className="h-3 w-3 opacity-70 group-hover:text-indigo-300 group-hover:opacity-100" />
                  </div>
                  <span className="truncate">{shortcut.label}</span>
                </button>
              )
            })}
          </div>
        </div>
      </nav>

      {/* User / Footer */}
      <div className="border-t border-white/5 p-4">
        <div className="group relative overflow-hidden rounded-2xl bg-gradient-to-br from-white/5 to-white/[0.02] p-4 transition-all hover:bg-white/10">
          <div className="flex items-center gap-3">
            <div className="relative h-10 w-10 rounded-full bg-gradient-to-br from-indigo-400 to-purple-400 p-0.5">
              <div className="h-full w-full rounded-full bg-black/40 backdrop-blur-sm" />
              <div className="absolute inset-0 flex items-center justify-center text-xs font-bold text-white">
                NJ
              </div>
            </div>
            <div className="flex-1 overflow-hidden">
              <p className="truncate text-sm font-medium text-white group-hover:text-indigo-200">Dr. Nicholas</p>
              <p className="truncate text-xs text-muted-foreground">Plano Premium</p>
            </div>
          </div>
          {/* Glow effect */}
          <div className="absolute -right-4 -top-4 h-16 w-16 rounded-full bg-indigo-500/20 blur-2xl transition-all group-hover:bg-indigo-500/30" />
        </div>
      </div>
    </aside>
  );
}

