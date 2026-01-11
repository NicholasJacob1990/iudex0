'use client';

import { useEffect, useMemo } from 'react';
import { quickStats } from '@/data/mock';
import { MinuteHistoryGrid, QuickActions, StatCard } from '@/components/dashboard';
import { useChatStore } from '@/stores';
import { differenceInCalendarDays } from 'date-fns';

export default function DashboardPage() {
  const { chats, fetchChats } = useChatStore();

  useEffect(() => {
    fetchChats().catch(() => {
      // erros tratados no interceptor
    });
  }, [fetchChats]);

  const historyItems = useMemo(() => {
    return chats.map((chat) => {
      const daysDiff = differenceInCalendarDays(new Date(), new Date(chat.updated_at));
      let group: 'Hoje' | 'Últimos 7 dias' | 'Últimos 30 dias' = 'Últimos 30 dias';
      if (daysDiff === 0) group = 'Hoje';
      else if (daysDiff <= 7) group = 'Últimos 7 dias';
      return {
        id: chat.id,
        title: chat.title || 'Minuta sem título',
        date: chat.updated_at,
        group,
        jurisdiction: chat.mode || 'Chat',
        tokens: chat.context ? Object.keys(chat.context).length * 100 : 0,
      };
    });
  }, [chats]);

  return (
    <div className="space-y-8">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {quickStats.map((stat) => (
          <StatCard key={stat.label} {...stat} />
        ))}
      </section>

      <MinuteHistoryGrid items={historyItems} />

      <QuickActions />
    </div>
  );
}
