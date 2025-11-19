'use client';

import { quickStats, minuteHistory } from '@/data/mock';
import { MinuteHistoryGrid, QuickActions, StatCard } from '@/components/dashboard';

export default function DashboardPage() {
  return (
    <div className="space-y-8">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {quickStats.map((stat) => (
          <StatCard key={stat.label} {...stat} />
        ))}
      </section>

      <MinuteHistoryGrid items={minuteHistory} />

      <QuickActions />
    </div>
  );
}

