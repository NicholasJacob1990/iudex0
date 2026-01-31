'use client';

import { useEffect, useMemo, useState } from 'react';
import { MinuteHistoryGrid, QuickActions, StatCard } from '@/components/dashboard';
import { useChatStore } from '@/stores';
import { differenceInCalendarDays } from 'date-fns';
import apiClient from '@/lib/api-client';
import { StaggerContainer } from '@/components/ui/animated-container';
import { MotionDiv, fadeUp } from '@/components/ui/motion';
import { AnimatedCounter } from '@/components/ui/animated-counter';

const DRAFT_STORAGE_PREFIX = 'iudex_chat_drafts_';
const QUALITY_SUMMARY_PREFIX = 'iudex_quality_summary:';
const QUALITY_CHAT_PREFIX = 'chat:';

type AuditSummary = {
  status?: string;
  date?: string;
};

type QualitySummary = {
  score?: number;
  approved?: boolean;
  validated_at?: string;
  total_issues?: number;
  total_content_issues?: number;
  analyzed_at?: string;
};

const loadLocalJson = (key: string) => {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
};

const normalizeAuditSummary = (audit: any): AuditSummary | null => {
  if (!audit) return null;
  const statusRaw = audit.status || audit.audit_status || audit.auditStatus;
  const approved = typeof audit.approved === 'boolean' ? audit.approved : null;
  let status = statusRaw;
  if (!status && approved !== null) status = approved ? 'aprovado' : 'reprovado';
  if (!status && (audit.audit_report_markdown || audit.markdown)) status = 'disponível';
  if (!status) return null;
  const normalized = String(status).toLowerCase();
  const normalizedStatus =
    normalized.includes('aprov') ? 'aprovado'
    : normalized.includes('reprov') ? 'reprovado'
    : normalized.includes('pend') || normalized.includes('revis') ? 'em revisão'
    : normalized.includes('dispon') ? 'disponível'
    : String(status);
  const date = audit.audit_date || audit.date || audit.validated_at || audit.created_at;
  return { status: normalizedStatus, date: typeof date === 'string' ? date : undefined };
};

const loadQualitySummary = (chatId: string): QualitySummary | null => {
  const key = `${QUALITY_SUMMARY_PREFIX}${QUALITY_CHAT_PREFIX}${chatId}`;
  const raw = loadLocalJson(key);
  if (!raw) return null;
  return {
    score: typeof raw.score === 'number' ? raw.score : undefined,
    approved: typeof raw.approved === 'boolean' ? raw.approved : undefined,
    validated_at: typeof raw.validated_at === 'string' ? raw.validated_at : undefined,
    total_issues: typeof raw.total_issues === 'number' ? raw.total_issues : undefined,
    total_content_issues: typeof raw.total_content_issues === 'number' ? raw.total_content_issues : undefined,
    analyzed_at: typeof raw.analyzed_at === 'string' ? raw.analyzed_at : undefined,
  };
};

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
  }, [chats]);

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
      const draftMeta = loadLocalJson(`${DRAFT_STORAGE_PREFIX}${chat.id}`);
      const auditPayload = draftMeta?.audit
        || chat.context?.audit
        || (chat.context?.audit_status ? { audit_status: chat.context.audit_status } : null);
      const auditSummary = normalizeAuditSummary(auditPayload);
      const qualitySummary = loadQualitySummary(chat.id);
      return {
        id: chat.id,
        title: chat.title || 'Minuta sem título',
        date: chat.updated_at,
        group,
        jurisdiction: chat.mode || 'Chat',
        tokens: chat.context ? Object.keys(chat.context).length * 100 : 0,
        audit: auditSummary ?? undefined,
        quality: qualitySummary ?? undefined,
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
      <StaggerContainer as="section" className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {stats.map((stat) => {
          const numericValue = Number(stat.value);
          const isNumeric = !isNaN(numericValue) && stat.value !== '--';
          return (
            <MotionDiv key={stat.label} variants={fadeUp}>
              <StatCard
                {...stat}
                value={
                  isNumeric ? (
                    <AnimatedCounter to={numericValue} duration={1.2} />
                  ) : (
                    stat.value
                  )
                }
              />
            </MotionDiv>
          );
        })}
      </StaggerContainer>

      <MotionDiv
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.3 }}
      >
        <MinuteHistoryGrid items={historyItems} />
      </MotionDiv>

      <QuickActions />
    </div>
  );
}
