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
} from 'lucide-react';

const navItems = [
  { href: '/dashboard', label: 'Início', icon: Home },
  { href: '/minuta', label: 'Nova Minuta', icon: FileText },
  { href: '/documents', label: 'Documentos', icon: Upload },
  { href: '/models', label: 'Modelos', icon: BookOpen },
  { href: '/legislation', label: 'Legislação', icon: Scale },
  { href: '/jurisprudence', label: 'Jurisprudência', icon: Gavel },
  { href: '/library', label: 'Biblioteca', icon: Folder },
  { href: '/settings', label: 'Configurações', icon: Settings },
];

export function DashboardSidebar() {
  const pathname = usePathname();
  const { sidebarOpen } = useUIStore();

  if (!sidebarOpen) return null;

  return (
    <aside className="w-64 border-r bg-card">
      <nav className="space-y-1 p-4">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'flex items-center space-x-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              )}
            >
              <Icon className="h-5 w-5" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

