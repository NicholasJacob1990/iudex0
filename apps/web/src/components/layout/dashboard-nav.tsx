'use client';

import { useAuthStore, useUIStore } from '@/stores';
import { Button } from '@/components/ui/button';
import { Menu, Moon, Sun, LogOut, User } from 'lucide-react';
import { useTheme } from 'next-themes';

export function DashboardNav() {
  const { user, logout } = useAuthStore();
  const { toggleSidebar } = useUIStore();
  const { theme, setTheme } = useTheme();

  return (
    <nav className="flex items-center justify-between border-b bg-card px-6 py-4">
      <div className="flex items-center space-x-4">
        <Button variant="ghost" size="icon" onClick={toggleSidebar}>
          <Menu className="h-5 w-5" />
        </Button>
        <h2 className="text-xl font-bold">Iudex</h2>
      </div>

      <div className="flex items-center space-x-2">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        >
          {theme === 'dark' ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </Button>

        <div className="flex items-center space-x-2 rounded-lg border px-3 py-2">
          <User className="h-4 w-4" />
          <span className="text-sm font-medium">{user?.name}</span>
        </div>

        <Button variant="ghost" size="icon" onClick={logout}>
          <LogOut className="h-5 w-5" />
        </Button>
      </div>
    </nav>
  );
}

