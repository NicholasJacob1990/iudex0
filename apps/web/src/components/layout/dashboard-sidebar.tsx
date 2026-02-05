'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useUIStore } from '@/stores';
import { cn } from '@/lib/utils';
import {
  Home,
  FileText,
  Upload,
  BookOpen,
  Scale,
  Gavel,
  Folder,
  Settings,
  FolderOpen,
  Mic,
  Sparkles,
} from 'lucide-react';

const navItems = [
  { href: '/dashboard', label: 'Início', icon: Home },
  { href: '/ask', label: 'Ask', icon: Sparkles },
  { href: '/minuta', label: 'Nova Minuta', icon: FileText },
  { href: '/transcription', label: 'Transcrições', icon: Mic },
  { href: '/cases', label: 'Casos', icon: FolderOpen },
  { href: '/documents', label: 'Documentos', icon: Upload },
  { href: '/models', label: 'Modelos', icon: BookOpen },
  { href: '/legislation', label: 'Legislação', icon: Scale },
  { href: '/jurisprudence', label: 'Jurisprudência', icon: Gavel },
  { href: '/library', label: 'Biblioteca', icon: Folder },
  { href: '/settings', label: 'Configurações', icon: Settings },
];

export function DashboardSidebar() {
  const pathname = usePathname();
  const { sidebarState } = useUIStore();
  const isCollapsed = sidebarState === 'collapsed';

  if (sidebarState === 'hidden') return null;

  return (
    <aside className={cn('w-64 border-r bg-card', isCollapsed && 'lg:w-16')}>
      <nav className={cn('space-y-1 p-4', isCollapsed && 'lg:px-2')}>
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'flex items-center space-x-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                isCollapsed && 'lg:justify-center lg:px-2',
                isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              )}
            >
              <Icon className="h-5 w-5" />
              <span className={cn(isCollapsed && 'lg:hidden')}>{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
