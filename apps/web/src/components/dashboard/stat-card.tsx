import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface StatCardProps {
  label: string;
  value: ReactNode;
  trend: string;
  color: string;
}

export function StatCard({ label, value, trend, color }: StatCardProps) {
  return (
    <div className="rounded-3xl border border-black/[0.06] bg-white/80 p-5 shadow-soft backdrop-blur-sm dark:border-white/[0.06] dark:bg-white/[0.04]">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-2 font-display text-3xl text-foreground">{value}</p>
      <p className="text-sm text-muted-foreground">{trend}</p>
      <div className="mt-4 h-2 w-full rounded-full bg-sand">
        <div className={cn('h-full rounded-full bg-gradient-to-r', color)} />
      </div>
    </div>
  );
}

