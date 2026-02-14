'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
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
  Workflow,
  Grid3X3,
  Store,
  Database,
  BookCheck,
  BarChart3,
  Shield,
  SlidersHorizontal,
  Sparkles,
  Sun,
  Moon,
  Palette,
  Settings,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTheme } from 'next-themes';
import { cn, formatDate } from '@/lib/utils';
import { useUIStore, useChatStore, useAuthStore, useOrgStore } from '@/stores';
import { tintToColor, buildGradientTrack, LIGHT_STOPS, DARK_STOPS } from '@/components/layout/top-nav';
import { RichTooltip } from '@/components/ui/rich-tooltip';
import { BackgroundTasks } from '@/components/chat/background-tasks';
import { Building2 } from 'lucide-react';
import { springTransition } from '@/components/ui/motion';
import { usePrefetchOnHover, prefetchFns } from '@/lib/prefetch';

// =============================================================================
// PREFETCH CONFIGS — mapeia href de navegacao para funcoes de prefetch
// =============================================================================

const NAV_PREFETCH_MAP: Record<string, (qc: any) => void> = {
  '/corpus': (qc) => {
    prefetchFns.corpusStats(qc);
    prefetchFns.corpusCollections(qc);
  },
  '/playbooks': (qc) => {
    prefetchFns.playbooksList(qc);
  },
  '/workflows': (qc) => {
    prefetchFns.workflowsList(qc);
  },
  '/workflows/catalog': (_qc) => {
    // no-op: catalog page fetches with filters; keep sidebar hover lightweight
  },
  '/library': (qc) => {
    prefetchFns.libraryItems(qc);
  },
  '/skills': (qc) => {
    prefetchFns.skillsList(qc);
  },
};

const resourceShortcuts = [
  { id: 'podcasts', label: 'Podcasts', description: 'Resumo em áudio de decisões', icon: 'Mic' },
  { id: 'diagrams', label: 'Diagramas', description: 'Mapas mentais automáticos', icon: 'Share2' },
  { id: 'sharing', label: 'Compartilhamentos', description: 'Pastas e grupos', icon: 'Users' },
  { id: 'cnj', label: 'Metadados CNJ e Comunicacoes DJEN', description: 'Processos e publicacoes oficiais', icon: 'Newspaper' },
];

type MainNavItem = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  adminOnly?: boolean;
};

const mainNav: MainNavItem[] = [
  { href: '/dashboard', label: 'Início', icon: Home },
  { href: '/ask', label: 'Ask', icon: Sparkles },
  { href: '/cases', label: 'Casos', icon: Folder },
  { href: '/transcription', label: 'Transcrição', icon: Mic },
  { href: '/minuta', label: 'Minuta', icon: PenTool },
  { href: '/documents', label: 'Documentos', icon: Upload },
  { href: '/models', label: 'Modelos', icon: Layers },
  { href: '/legislation', label: 'Legislação', icon: Scale },
  { href: '/jurisprudence', label: 'Jurisprudência', icon: Gavel },
  { href: '/cnj', label: 'Metadados CNJ + DJEN', icon: Newspaper },
  { href: '/web', label: 'Web', icon: Globe },
  { href: '/corpus', label: 'Corpus', icon: Database },
  { href: '/library', label: 'Biblioteca', icon: Library },
  { href: '/skills', label: 'Skills', icon: Sparkles },
  { href: '/graph', label: 'Grafos', icon: Network },
  { href: '/graph/risk', label: 'Risco (Grafo)', icon: Shield },
  { href: '/workflows', label: 'Workflows', icon: Workflow },
  { href: '/workflows/catalog', label: 'Templates', icon: Grid3X3 },
  { href: '/playbooks', label: 'Playbooks', icon: BookCheck },
  { href: '/analytics', label: 'Analytics', icon: BarChart3 },
  { href: '/marketplace', label: 'Marketplace', icon: Store },
  { href: '/spaces', label: 'Spaces', icon: Share2 },
  { href: '/settings', label: 'Configurações', icon: Settings },
  { href: '/bibliotecarios', label: 'Bibliotecários', icon: Users },
  { href: '/admin/feature-flags', label: 'Feature Flags', icon: SlidersHorizontal, adminOnly: true },
  { href: '/admin/audit-logs', label: 'Audit Logs', icon: Shield },
];

const resourceIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  Podcasts: Mic,
  Diagramas: Share2,
  Compartilhamentos: Users,
  'Metadados CNJ e Comunicacoes DJEN': Newspaper,
};

// =============================================================================
// THEME TOKENS — Microsoft Office light (#737373 base) vs dark
// =============================================================================

const themeTokens = {
  dark: {
    bg: 'bg-[#0F1115]',
    text: 'text-sidebar-fg',
    border: 'border-white/5',
    titleText: 'text-white',
    subtitleText: 'text-indigo-400/80',
    closeBtn: 'text-muted-foreground hover:bg-white/10 hover:text-white',
    controlBtn: 'border-white/10 text-muted-foreground hover:bg-white/10 hover:text-white',
    navItemActive: 'text-white',
    navItemInactive: 'text-muted-foreground hover:bg-white/5 hover:text-white',
    activeIndicator: 'bg-white/10 shadow-inner shadow-white/5 ring-1 ring-white/10',
    iconActive: 'text-indigo-400',
    iconInactive: 'text-muted-foreground group-hover:text-indigo-300',
    sectionBorder: 'border-white/5',
    sectionLabel: 'text-muted-foreground/40',
    shortcutBtn: 'text-muted-foreground hover:bg-white/5 hover:text-white',
    shortcutIconBg: 'bg-white/5 group-hover:bg-indigo-500/20',
    shortcutIconColor: 'opacity-70 group-hover:text-indigo-300 group-hover:opacity-100',
    recentItem: 'text-muted-foreground hover:bg-white/5 hover:text-white',
    recentTitle: 'text-white/90',
    footerBorder: 'border-white/5',
    orgLink: 'text-muted-foreground hover:bg-white/5 hover:text-white',
    userCard: 'bg-gradient-to-br from-white/5 to-white/[0.02] hover:bg-white/10',
    avatarInnerBg: 'bg-black/40',
    userName: 'text-white group-hover:text-indigo-200',
    userPlan: 'text-muted-foreground',
    glow: 'bg-indigo-500/20 group-hover:bg-indigo-500/30',
  },
  light: {
    bg: 'bg-[#F5F5F5]',
    text: 'text-[#404040]',
    border: 'border-black/[0.08]',
    titleText: 'text-[#1A1A1A]',
    subtitleText: 'text-indigo-600/80',
    closeBtn: 'text-[#737373] hover:bg-black/5 hover:text-[#1A1A1A]',
    controlBtn: 'border-black/10 text-[#737373] hover:bg-black/5 hover:text-[#1A1A1A]',
    navItemActive: 'text-[#1A1A1A]',
    navItemInactive: 'text-[#737373] hover:bg-black/[0.04] hover:text-[#1A1A1A]',
    activeIndicator: 'bg-black/[0.06] ring-1 ring-black/[0.08]',
    iconActive: 'text-indigo-600',
    iconInactive: 'text-[#737373] group-hover:text-indigo-500',
    sectionBorder: 'border-black/[0.08]',
    sectionLabel: 'text-[#737373]/60',
    shortcutBtn: 'text-[#737373] hover:bg-black/[0.04] hover:text-[#1A1A1A]',
    shortcutIconBg: 'bg-black/[0.04] group-hover:bg-indigo-500/10',
    shortcutIconColor: 'opacity-70 group-hover:text-indigo-500 group-hover:opacity-100',
    recentItem: 'text-[#737373] hover:bg-black/[0.04] hover:text-[#1A1A1A]',
    recentTitle: 'text-[#1A1A1A]',
    footerBorder: 'border-black/[0.08]',
    orgLink: 'text-[#737373] hover:bg-black/[0.04] hover:text-[#1A1A1A]',
    userCard: 'bg-black/[0.03] hover:bg-black/[0.06]',
    avatarInnerBg: 'bg-black/[0.03]',
    userName: 'text-[#1A1A1A] group-hover:text-indigo-700',
    userPlan: 'text-[#737373]',
    glow: 'bg-indigo-500/10 group-hover:bg-indigo-500/15',
  },
} as const;

/**
 * Wrapper que adiciona prefetch on hover para links de navegacao.
 * Se nao houver prefetch configurado para o href, renderiza sem handlers extras.
 */
function PrefetchableNavItem({ href, children }: { href: string; children: React.ReactNode }) {
  const prefetchFn = NAV_PREFETCH_MAP[href];
  const stableFn = useCallback((qc: any) => prefetchFn?.(qc), [prefetchFn]);
  const handlers = usePrefetchOnHover(stableFn, 200);

  if (!prefetchFn) {
    return <span className="contents">{children}</span>;
  }

  return (
    <span className="contents" {...handlers}>
      {children}
    </span>
  );
}

export function SidebarPro() {
  const pathname = usePathname();
  const { sidebarState, setSidebarState, toggleSidebarCollapse, sidebarTheme, toggleSidebarTheme, chatBgTintLight, chatBgTintDark, setChatBgTintLight, setChatBgTintDark } = useUIStore();
  const { chats, fetchChats } = useChatStore();
  const { user } = useAuthStore();
  const { organization, fetchOrganization } = useOrgStore();
  const { resolvedTheme } = useTheme();
  const pageTheme = (resolvedTheme === 'dark' ? 'dark' : 'light') as 'light' | 'dark';
  const isCollapsed = sidebarState === 'collapsed';
  const isHidden = sidebarState === 'hidden';
  const isAdmin = String(user?.role || '').toUpperCase() === 'ADMIN';
  const isLight = sidebarTheme === 'light';
  const t = themeTokens[sidebarTheme];
  const activeTint = isLight ? chatBgTintLight : chatBgTintDark;
  const setActiveTint = isLight ? setChatBgTintLight : setChatBgTintDark;
  const sidebarBg = useMemo(
    () => tintToColor(activeTint, isLight ? LIGHT_STOPS : DARK_STOPS),
    [activeTint, isLight],
  );
  const sidebarGradientH = useMemo(
    () => buildGradientTrack(isLight ? LIGHT_STOPS : DARK_STOPS),
    [isLight],
  );
  const handleTintChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => setActiveTint(Number(e.target.value)),
    [setActiveTint],
  );

  // Tint bar: click to open (fixed position to escape overflow clipping)
  const [sidebarTintOpen, setSidebarTintOpen] = useState(false);
  const [tintBarPos, setTintBarPos] = useState({ top: 0, left: 0 });
  const sidebarTintRef = useRef<HTMLDivElement>(null);
  const tintBarRef = useRef<HTMLDivElement>(null);

  const handleSidebarThemeToggle = useCallback(() => {
    toggleSidebarTheme(pageTheme);
  }, [toggleSidebarTheme, pageTheme]);

  const handleSidebarTintToggle = useCallback(() => {
    setSidebarTintOpen((prev) => {
      if (!prev && sidebarTintRef.current) {
        const btn = sidebarTintRef.current.querySelector('button');
        if (btn) {
          const rect = btn.getBoundingClientRect();
          setTintBarPos({ top: rect.top + rect.height / 2, left: rect.right + 8 });
        }
      }
      return !prev;
    });
  }, []);

  useEffect(() => {
    if (!sidebarTintOpen) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        sidebarTintRef.current && !sidebarTintRef.current.contains(target) &&
        tintBarRef.current && !tintBarRef.current.contains(target)
      ) {
        setSidebarTintOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [sidebarTintOpen]);

  useEffect(() => {
    fetchChats().catch(() => undefined);
    if (user?.organization_id) {
      fetchOrganization().catch(() => undefined);
    }
  }, [fetchChats, fetchOrganization, user?.organization_id]);

  const recentChats = useMemo(() => chats.slice(0, 3), [chats]);
  const visibleMainNav = useMemo(
    () => mainNav.filter((item) => !item.adminOnly || isAdmin),
    [isAdmin]
  );

  const sidebar = (
    <aside
      id="dashboard-sidebar"
      className={cn(
        'fixed inset-y-0 left-0 z-50 flex h-full w-72 flex-col border-r',
        t.text, t.border,
        'transform transition-all duration-300 lg:static lg:z-auto lg:translate-x-0',
        sidebarState === 'hidden' ? '-translate-x-full lg:w-0 lg:border-r-0 lg:opacity-0 lg:pointer-events-none' : 'translate-x-0',
        sidebarState === 'collapsed' && 'lg:w-16'
      )}
      style={{ backgroundColor: sidebarBg }}
      aria-hidden={isHidden}
    >
      {/* Header */}
      <div className={cn('flex items-center justify-between px-6 py-8', isCollapsed && 'lg:px-3 lg:py-6')}>
        <div className={cn('flex items-center gap-3', isCollapsed && 'lg:w-full lg:justify-center')}>
          <div className="group flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 shadow-lg shadow-indigo-500/20 transition-all duration-300 hover:shadow-indigo-500/40">
            <Scale className="h-5 w-5 text-white" />
          </div>
          <div className={cn(isCollapsed && 'lg:hidden')}>
            <h1 className={cn('font-display text-xl font-bold tracking-tight', t.titleText)}>Iudex</h1>
            <p className={cn('text-[10px] font-medium uppercase tracking-wider', t.subtitleText)}>
              Intelligent Workspace
            </p>
          </div>
        </div>
        <button
          onClick={() => setSidebarState('hidden')}
          className={cn('rounded-lg p-1 lg:hidden', t.closeBtn)}
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
          className={cn('inline-flex h-8 w-8 items-center justify-center rounded-lg border transition', t.controlBtn)}
          aria-label={isCollapsed ? 'Expandir menu' : 'Colapsar menu'}
          title={isCollapsed ? 'Expandir menu' : 'Colapsar menu'}
        >
          {isCollapsed ? <ChevronsRight className="h-4 w-4" /> : <ChevronsLeft className="h-4 w-4" />}
        </button>
        <button
          type="button"
          onClick={() => setSidebarState('hidden')}
          className={cn('inline-flex h-8 w-8 items-center justify-center rounded-lg border transition', t.controlBtn)}
          aria-label="Ocultar menu"
          title="Ocultar menu"
        >
          <EyeOff className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={handleSidebarThemeToggle}
          className={cn('inline-flex h-8 w-8 items-center justify-center rounded-lg border transition', t.controlBtn)}
          aria-label={isLight ? 'Tema escuro' : 'Tema claro'}
          title={isLight ? 'Tema escuro' : 'Tema claro'}
        >
          {isLight ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
        </button>
        <div ref={sidebarTintRef} className="relative">
          <button
            type="button"
            onClick={handleSidebarTintToggle}
            className={cn(
              'inline-flex h-8 w-8 items-center justify-center rounded-lg border transition',
              t.controlBtn,
              sidebarTintOpen && (isLight ? 'bg-black/[0.06]' : 'bg-white/10'),
            )}
            aria-label="Ajustar tom do fundo"
            title="Ajustar tom do fundo"
          >
            <Palette className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Navigation */}
      <nav className={cn('flex-1 space-y-1 overflow-y-auto scrollbar-none px-4 py-6', isCollapsed && 'lg:px-2')}>
        {visibleMainNav.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href || pathname?.startsWith(`${item.href}/`);
          const link = (
            <Link
              href={item.href}
              aria-label={item.label}
              title={isCollapsed ? item.label : undefined}
              className={cn(
                'group relative flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-all duration-300',
                isCollapsed && 'lg:justify-center lg:px-2',
                isActive
                  ? t.navItemActive
                  : cn(
                      t.navItemInactive,
                      !isCollapsed && 'hover:pl-5'
                    )
              )}
            >
              {isActive && (
                <motion.div
                  layoutId="sidebar-active"
                  className={cn('absolute inset-0 rounded-xl', t.activeIndicator)}
                  transition={springTransition}
                />
              )}
              <Icon className={cn('relative z-10 h-4 w-4 transition-colors', isActive ? t.iconActive : t.iconInactive)} />
              <AnimatePresence mode="wait">
                {!isCollapsed && (
                  <motion.span
                    key={`label-${item.href}`}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -8 }}
                    transition={{ duration: 0.2 }}
                    className={cn('relative z-10', isCollapsed && 'lg:hidden')}
                  >
                    {item.label}
                  </motion.span>
                )}
              </AnimatePresence>
              {isActive && (
                <div
                  className={cn(
                    'relative z-10 ml-auto h-1.5 w-1.5 rounded-full bg-indigo-400 shadow-[0_0_8px_rgba(129,140,248,0.8)]',
                    isLight && 'bg-indigo-600 shadow-[0_0_8px_rgba(79,70,229,0.6)]',
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
            <PrefetchableNavItem key={item.href} href={item.href}>
              {link}
            </PrefetchableNavItem>
          );
        })}

        <div className={cn(isCollapsed && 'lg:hidden')}>
          <div className={cn('my-6 border-t px-2 py-6', t.sectionBorder)}>
            <p className={cn('mb-4 px-2 text-[10px] font-bold uppercase tracking-widest', t.sectionLabel)}>
              Ferramentas Rápidas
            </p>
            <div className="space-y-1">
              {resourceShortcuts.map((shortcut) => {
                const Icon = resourceIcons[shortcut.label] ?? Share2;
                return (
                  <button
                    key={shortcut.id}
                    className={cn('group flex w-full items-center gap-3 rounded-lg px-3 py-2 text-xs font-medium transition-all', t.shortcutBtn)}
                  >
                    <div className={cn('flex h-6 w-6 items-center justify-center rounded-md transition-colors', t.shortcutIconBg)}>
                      <Icon className={cn('h-3 w-3', t.shortcutIconColor)} />
                    </div>
                    <span className="truncate">{shortcut.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
          <div className="mt-6 space-y-2">
            <p className={cn('px-2 text-[10px] font-bold uppercase tracking-widest', t.sectionLabel)}>
              Recentes
            </p>
            {recentChats.map((item) => (
              <div
                key={item.id}
                className={cn('flex items-center justify-between rounded-xl px-3 py-2 text-[11px] transition', t.recentItem)}
              >
                <div className="flex-1 overflow-hidden">
                  <p className={cn('truncate font-semibold', t.recentTitle)}>{item.title || 'Minuta sem título'}</p>
                  <p className="text-[10px] leading-tight text-muted-foreground">
                    {item.mode || 'Chat'} • {formatDate(new Date(item.updated_at))}
                  </p>
                </div>
                <div className={cn('ml-2 h-1.5 w-1.5 rounded-full', isLight ? 'bg-indigo-600' : 'bg-indigo-400')} />
              </div>
            ))}
          </div>
        </div>
      </nav>

      {/* Background Agents */}
      {!isCollapsed && <BackgroundTasks />}

      {/* User / Footer */}
      <div className={cn('border-t p-4', t.footerBorder, isCollapsed && 'lg:hidden')}>
        {organization && (
          <Link
            href="/organization"
            className={cn('mb-3 flex items-center gap-2 rounded-xl px-3 py-2 text-xs transition-all', t.orgLink)}
          >
            <Building2 className={cn('h-3.5 w-3.5', isLight ? 'text-indigo-600' : 'text-indigo-400')} />
            <span className="truncate">{organization.name}</span>
          </Link>
        )}
        <div className={cn('group relative overflow-hidden rounded-2xl p-4 transition-all', t.userCard)}>
          <div className="flex items-center gap-3">
            <div className="relative h-10 w-10 rounded-full bg-gradient-to-br from-indigo-400 to-purple-400 p-0.5">
              <div className={cn('h-full w-full rounded-full backdrop-blur-sm', t.avatarInnerBg)} />
              <div className="absolute inset-0 flex items-center justify-center text-xs font-bold text-white">
                {user?.name?.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase() || '??'}
              </div>
            </div>
            <div className="flex-1 overflow-hidden">
              <p className={cn('truncate text-sm font-medium', t.userName)}>{user?.name || 'Usuário'}</p>
              <p className={cn('truncate text-xs', t.userPlan)}>{user?.plan ? `Plano ${user.plan}` : 'Carregando...'}</p>
            </div>
          </div>
          {/* Glow effect */}
          <div className={cn('absolute -right-4 -top-4 h-16 w-16 rounded-full blur-2xl transition-all', t.glow)} />
        </div>
      </div>

    </aside>
  );

  // Portal: tint bar rendered at document.body to escape transform containing block
  const tintBarPortal = sidebarTintOpen && typeof document !== 'undefined'
    ? createPortal(
        <div
          ref={tintBarRef}
          className="fixed z-[9999] -translate-y-1/2"
          style={{ top: tintBarPos.top, left: tintBarPos.left }}
        >
          <div className="relative w-48 rounded-full border border-border/50 shadow-md backdrop-blur-md">
            <div className="h-4 w-full rounded-full" style={{ background: sidebarGradientH }} />
            <input
              type="range" min={0} max={100} step={1}
              value={activeTint} onChange={handleTintChange}
              className="chat-tint-slider absolute inset-0 h-4 w-full cursor-pointer appearance-none bg-transparent"
              aria-label="Ajustar tom do fundo"
            />
          </div>
        </div>,
        document.body,
      )
    : null;

  return (
    <>
      {sidebar}
      {tintBarPortal}
    </>
  );
}
