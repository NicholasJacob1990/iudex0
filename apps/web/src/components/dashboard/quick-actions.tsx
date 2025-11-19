'use client';

import { quickActions } from '@/data/mock';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Feather, Upload, Gavel } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

const iconMap: Record<string, LucideIcon> = {
  Feather,
  Upload,
  Gavel,
};

export function QuickActions() {
  return (
    <section className="grid gap-4 md:grid-cols-3">
      {quickActions.map((action) => {
        const Icon = iconMap[action.icon] ?? Feather;
        return (
          <div
            key={action.id}
            className="rounded-3xl border border-white/80 bg-white/90 p-5 shadow-soft"
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="font-display text-lg text-foreground">{action.title}</p>
                <p className="text-sm text-muted-foreground">{action.description}</p>
              </div>
              <span
                className={cn(
                  'flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-primary/10 to-rose-100 text-primary'
                )}
              >
                <Icon className="h-5 w-5" />
              </span>
            </div>
            <Button className="mt-4 rounded-2xl bg-primary text-primary-foreground shadow-soft">
              Acessar
            </Button>
          </div>
        );
      })}
    </section>
  );
}

