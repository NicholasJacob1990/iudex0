'use client';

import { useEffect, useMemo, useState } from 'react';
import { MinuteHistoryGrid, QuickActions, StatCard } from '@/components/dashboard';
import { useChatStore } from '@/stores';
import { differenceInCalendarDays } from 'date-fns';
import apiClient from '@/lib/api-client';

export default function DashboardPage() {
  const { chats, fetchChats } = useChatStore();
  const [documentsTotal, setDocumentsTotal] = useState(0);
  const [modelsTotal, setModelsTotal] = useState(0);

  useEffect(() => {
    fetchChats().catch(() => {
      // erros tratados no interceptor
    });
  }, [fetchChats]);

  useEffect(() => {
    let mounted = true;
    const loadCounts = async () => {
      try {
        const [docs, models] = await Promise.all([
          apiClient.getDocuments(0, 1),
          apiClient.getLibraryItems(0, 1, undefined, 'MODEL'),
        ]);
        if (!mounted) return;
        setDocumentsTotal(docs.total ?? 0);
        setModelsTotal(models.total ?? 0);
      } catch {
        // Silencioso
      }
    };
    loadCounts();
    return () => {
      mounted = false;
    };
  }, []);

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

  const weeklyChats = useMemo(() => {
    return chats.filter((chat) => differenceInCalendarDays(new Date(), new Date(chat.updated_at)) <= 7).length;
  }, [chats]);

  const stats = useMemo(() => ([
    {
      label: 'Minutas Geradas',
      value: String(chats.length),
      trend: weeklyChats ? `+${weeklyChats} nos últimos 7 dias` : 'Sem atividade recente',
      color: 'from-blush to-primary',
    },
    {
      label: 'Documentos Importados',
      value: String(documentsTotal),
      trend: 'No acervo do usuário',
      color: 'from-lavender to-primary',
    },
    {
      label: 'Modelos Preferidos',
      value: String(modelsTotal),
      trend: 'Salvos na biblioteca',
      color: 'from-emerald to-primary',
    },
    {
      label: 'Tempo Médio',
      value: '--',
      trend: 'Dados insuficientes',
      color: 'from-primary to-clay',
    },
  ]), [chats.length, documentsTotal, modelsTotal, weeklyChats]);

  return (
    <div className="space-y-8">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {stats.map((stat) => (
          <StatCard key={stat.label} {...stat} />
        ))}
      </section>

      <MinuteHistoryGrid items={historyItems} />

      <QuickActions />
    </div>
  );
}
