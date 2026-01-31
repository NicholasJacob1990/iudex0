'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useMemo } from 'react';
import {
  Home,
  Folder,
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
  Newspaper,
  ChevronsLeft,
  ChevronsRight,
  EyeOff,
  Network,
} from 'lucide-react';
import { cn, formatDate } from '@/lib/utils';
import { useUIStore, useChatStore, useAuthStore, useOrgStore } from '@/stores';
import { RichTooltip } from '@/components/ui/rich-tooltip';
import { Building2 } from 'lucide-react';

const resourceShortcuts = [
  { id: 'podcasts', label: 'Podcasts', description: 'Resumo em áudio de decisões', icon: 'Mic' },
  { id: 'diagrams', label: 'Diagramas', description: 'Mapas mentais automáticos', icon: 'Share2' },
  { id: 'sharing', label: 'Compartilhamentos', description: 'Pastas e grupos', icon: 'Users' },
  { id: 'cnj', label: 'Metadados CNJ e Comunicacoes DJEN', description: 'Processos e publicacoes oficiais', icon: 'Newspaper' },
];

const mainNav = [
  { href: '/dashboard', label: 'Início', icon: Home },
  { href: '/cases', label: 'Casos', icon: Folder },
  { href: '/transcription', label: 'Transcrição', icon: Mic },
  { href: '/minuta', label: 'Minuta', icon: PenTool },
  { href: '/documents', label: 'Documentos', icon: Upload },
  { href: '/models', label: 'Modelos', icon: Layers },
  { href: '/legislation', label: 'Legislação', icon: Scale },
  { href: '/jurisprudence', label: 'Jurisprudência', icon: Gavel },
  { href: '/cnj', label: 'Metadados CNJ + DJEN', icon: Newspaper },
  { href: '/web', label: 'Web', icon: Globe },
  { href: '/library', label: 'Biblioteca', icon: Library },
  { href: '/graph', label: 'Grafos', icon: Network },
  { href: '/bibliotecarios', label: 'Bibliotecários', icon: Users },
];

const resourceIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  Podcasts: Mic,
  Diagramas: Share2,
  Compartilhamentos: Users,
  'Metadados CNJ e Comunicacoes DJEN': Newspaper,
};

export function SidebarPro() {
  const pathname = usePathname();
  const { sidebarState, setSidebarState, toggleSidebarCollapse } = useUIStore();
  const { chats, fetchChats } = useChatStore();
  const { user } = useAuthStore();
  const { organization, fetchOrganization } = useOrgStore();
  const isCollapsed = sidebarState === 'collapsed';
  const isHidden = sidebarState === 'hidden';

  useEffect(() => {
    fetchChats().catch(() => undefined);
    if (user?.organization_id) {
      fetchOrganization().catch(() => undefined);
    }
  }, [fetchChats, fetchOrganization, user?.organization_id]);

  const recentChats = useMemo(() => chats.slice(0, 3), [chats]);

  return (
    <aside
      id="dashboard-sidebar"
      className={cn(
        // Mobile: behaves like a drawer (fixed + slide), so it does NOT squeeze the main content.
        // Desktop: stays in the normal layout flow and can collapse to free space.
        'fixed inset-y-0 left-0 z-50 flex h-full w-72 flex-col border-r border-white/5 bg-[#0F1115] text-sidebar-fg',
        'transform transition-all duration-300 lg:static lg:z-auto lg:translate-x-0',
        sidebarState === 'hidden' ? '-translate-x-full lg:w-0 lg:border-r-0 lg:opacity-0 lg:pointer-events-none' : 'translate-x-0',
        sidebarState === 'collapsed' && 'lg:w-16'
      )}
      aria-hidden={isHidden}
    >
      {/* Header */}
      <div className={cn('flex items-center justify-between px-6 py-8', isCollapsed && 'lg:px-3 lg:py-6')}>
        <div className={cn('flex items-center gap-3', isCollapsed && 'lg:w-full lg:justify-center')}>
          <div className="group flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 shadow-lg shadow-indigo-500/20 transition-all duration-300 hover:shadow-indigo-500/40">
            <Scale className="h-5 w-5 text-white" />
          </div>
          <div className={cn(isCollapsed && 'lg:hidden')}>
            <h1 className="font-display text-xl font-bold tracking-tight text-white">Iudex</h1>
            <p className="text-[10px] font-medium uppercase tracking-wider text-indigo-400/80">
              Intelligent Workspace
            </p>
          </div>
        </div>
        <button
          onClick={() => setSidebarState('hidden')}
          className="rounded-lg p-1 text-muted-foreground hover:bg-white/10 hover:text-white lg:hidden"
        >
          ✕
        </button>
      </div>

      <div
        className={cn(
          'hidden lg:flex items-center gap-2 px-6 pb-2',
          isCollapsed && 'flex-col px-2'
        )}
      >
        <button
          type="button"
          onClick={toggleSidebarCollapse}
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 text-muted-foreground transition hover:bg-white/10 hover:text-white"
          aria-label={isCollapsed ? 'Expandir menu' : 'Colapsar menu'}
          title={isCollapsed ? 'Expandir menu' : 'Colapsar menu'}
        >
          {isCollapsed ? <ChevronsRight className="h-4 w-4" /> : <ChevronsLeft className="h-4 w-4" />}
        </button>
        <button
          type="button"
          onClick={() => setSidebarState('hidden')}
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 text-muted-foreground transition hover:bg-white/10 hover:text-white"
          aria-label="Ocultar menu"
          title="Ocultar menu"
        >
          <EyeOff className="h-4 w-4" />
        </button>
      </div>

      {/* Navigation */}
      <nav className={cn('flex-1 space-y-1 px-4 py-6', isCollapsed && 'lg:px-2')}>
        {mainNav.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href || pathname?.startsWith(`${item.href}/`);
          const link = (
            <Link
              href={item.href}
              aria-label={item.label}
              title={isCollapsed ? item.label : undefined}
              className={cn(
                'group flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-all duration-300',
                isCollapsed && 'lg:justify-center lg:px-2',
                isActive
                  ? 'bg-white/10 text-white shadow-inner shadow-white/5 ring-1 ring-white/10'
                  : cn(
                      'text-muted-foreground hover:bg-white/5 hover:text-white',
                      !isCollapsed && 'hover:pl-5'
                    )
              )}
            >
              <Icon className={cn('h-4 w-4 transition-colors', isActive ? 'text-indigo-400' : 'text-muted-foreground group-hover:text-indigo-300')} />
              <span className={cn(isCollapsed && 'lg:hidden')}>{item.label}</span>
              {isActive && (
                <div
                  className={cn(
                    'ml-auto h-1.5 w-1.5 rounded-full bg-indigo-400 shadow-[0_0_8px_rgba(129,140,248,0.8)]',
                    isCollapsed && 'lg:hidden'
                  )}
                />
              )}
            </Link>
          );

          if (item.href === '/bibliotecarios') {
            return (
              <RichTooltip
                key={item.href}
                title="Bibliotecários"
                description="Ative agentes especialistas (ex: Tributário, Civil) para revisar pontos específicos da sua minuta."
                badge="Agentes"
                icon={<Users className="h-3.5 w-3.5" />}
              >
                {link}
              </RichTooltip>
            );
          }

          return (
            <span key={item.href} className="contents">
              {link}
            </span>
          );
        })}

        <div className={cn(isCollapsed && 'lg:hidden')}>
          <div className="my-6 border-t border-white/5 px-2 py-6">
            <p className="mb-4 px-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground/40">
              Ferramentas Rápidas
            </p>
            <div className="space-y-1">
              {resourceShortcuts.map((shortcut) => {
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
                );
              })}
            </div>
          </div>
          <div className="mt-6 space-y-2">
            <p className="px-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground/40">
              Recentes
            </p>
            {recentChats.map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between rounded-xl px-3 py-2 text-[11px] text-muted-foreground transition hover:bg-white/5 hover:text-white"
              >
                <div className="flex-1 overflow-hidden">
                  <p className="truncate font-semibold text-white/90">{item.title || 'Minuta sem título'}</p>
                  <p className="text-[10px] leading-tight text-muted-foreground">
                    {item.mode || 'Chat'} • {formatDate(new Date(item.updated_at))}
                  </p>
                </div>
                <div className="ml-2 h-1.5 w-1.5 rounded-full bg-indigo-400" />
              </div>
            ))}
          </div>
        </div>
      </nav>

      {/* User / Footer */}
      <div className={cn('border-t border-white/5 p-4', isCollapsed && 'lg:hidden')}>
        {organization && (
          <Link
            href="/organization"
            className="mb-3 flex items-center gap-2 rounded-xl px-3 py-2 text-xs text-muted-foreground transition-all hover:bg-white/5 hover:text-white"
          >
            <Building2 className="h-3.5 w-3.5 text-indigo-400" />
            <span className="truncate">{organization.name}</span>
          </Link>
        )}
        <div className="group relative overflow-hidden rounded-2xl bg-gradient-to-br from-white/5 to-white/[0.02] p-4 transition-all hover:bg-white/10">
          <div className="flex items-center gap-3">
            <div className="relative h-10 w-10 rounded-full bg-gradient-to-br from-indigo-400 to-purple-400 p-0.5">
              <div className="h-full w-full rounded-full bg-black/40 backdrop-blur-sm" />
              <div className="absolute inset-0 flex items-center justify-center text-xs font-bold text-white">
                {user?.name?.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase() || '??'}
              </div>
            </div>
            <div className="flex-1 overflow-hidden">
              <p className="truncate text-sm font-medium text-white group-hover:text-indigo-200">{user?.name || 'Usuário'}</p>
              <p className="truncate text-xs text-muted-foreground">{user?.plan ? `Plano ${user.plan}` : 'Carregando...'}</p>
            </div>
          </div>
          {/* Glow effect */}
          <div className="absolute -right-4 -top-4 h-16 w-16 rounded-full bg-indigo-500/20 blur-2xl transition-all group-hover:bg-indigo-500/30" />
        </div>
      </div>
    </aside>
  );
}
