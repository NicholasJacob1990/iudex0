'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { MinuteHistoryGrid, QuickActions, StatCard } from '@/components/dashboard';
import { useChatStore } from '@/stores';
import { differenceInCalendarDays } from 'date-fns';
import apiClient from '@/lib/api-client';
import { StaggerContainer } from '@/components/ui/animated-container';
import { MotionDiv, fadeUp } from '@/components/ui/motion';
import { AnimatedCounter } from '@/components/ui/animated-counter';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { BookOpen, Database, Table2, Plus } from 'lucide-react';

// ---------------------------------------------------------------------------
// Types for new sections
// ---------------------------------------------------------------------------

interface RecentPlaybook {
  id: string;
  name: string;
  updated_at: string;
  rule_count: number;
}

interface RecentCorpusProject {
  id: string;
  name: string;
  document_count: number;
  updated_at: string;
}

interface RecentReviewTable {
  id: string;
  name: string;
  status: string;
  processed_documents: number;
  total_documents: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatRelativeDate(isoString: string): string {
  if (!isoString) return '';
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  const diffHr = Math.floor(diffMs / 3_600_000);
  const diffDay = Math.floor(diffMs / 86_400_000);

  if (diffMin < 1) return 'agora';
  if (diffMin < 60) return `${diffMin}min`;
  if (diffHr < 24) return `${diffHr}h`;
  if (diffDay === 1) return 'ontem';
  if (diffDay < 7) return `${diffDay}d`;
  return date.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' });
}

const statusConfig: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  created: { label: 'Criada', variant: 'outline' },
  processing: { label: 'Processando', variant: 'secondary' },
  completed: { label: 'Concluída', variant: 'default' },
  failed: { label: 'Erro', variant: 'destructive' },
};

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

  // New state for Playbooks, Corpus, Review Tables
  const [recentPlaybooks, setRecentPlaybooks] = useState<RecentPlaybook[]>([]);
  const [recentCorpus, setRecentCorpus] = useState<RecentCorpusProject[]>([]);
  const [recentReviews, setRecentReviews] = useState<RecentReviewTable[]>([]);
  const [playbooksTotal, setPlaybooksTotal] = useState(0);
  const [reviewsTotal, setReviewsTotal] = useState(0);

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
        const docs = await apiClient.getDocuments(0, 1);
        if (!mounted) return;
        setDocumentsTotal(docs.total ?? 0);
      } catch {
        // Silencioso
      }
    };
    loadCounts();
    return () => {
      mounted = false;
    };
  }, []);

  // Load new data: Playbooks, Corpus, Review Tables
  useEffect(() => {
    let mounted = true;
    const loadNewData = async () => {
      try {
        const data = await apiClient.getDashboardRecentActivity();
        if (!mounted) return;

        setRecentPlaybooks(data.recent_playbooks || []);
        setRecentCorpus(data.recent_corpus_projects || []);
        setRecentReviews(data.recent_review_tables || []);
        setPlaybooksTotal(data.stats?.total_playbooks || 0);
        setReviewsTotal(data.stats?.total_review_tables || 0);
      } catch {
        // Silencioso - dados opcionais
      }
    };
    loadNewData();
    return () => { mounted = false; };
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
      label: 'Playbooks',
      value: String(playbooksTotal),
      trend: 'Regras de revisão',
      color: 'from-clay to-primary',
    },
    {
      label: 'Revisões',
      value: String(reviewsTotal),
      trend: 'Tabelas de análise',
      color: 'from-emerald to-primary',
    },
  ]), [chats.length, documentsTotal, playbooksTotal, reviewsTotal, weeklyChats]);

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

      {/* New Feature Sections: Playbooks, Corpus, Review Tables */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Recent Playbooks */}
        <MotionDiv
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.4 }}
        >
          <Card className="h-full">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <BookOpen className="h-4 w-4 text-violet-500" />
                Playbooks Recentes
              </CardTitle>
              <Link href="/playbooks">
                <Button variant="ghost" size="sm" className="h-7 text-xs">
                  Ver todos
                </Button>
              </Link>
            </CardHeader>
            <CardContent className="space-y-3">
              {recentPlaybooks.length === 0 ? (
                <div className="text-center py-6">
                  <BookOpen className="h-8 w-8 mx-auto text-muted-foreground/50 mb-2" />
                  <p className="text-sm text-muted-foreground">Nenhum playbook criado</p>
                  <Link href="/playbooks/new">
                    <Button variant="outline" size="sm" className="mt-3">
                      <Plus className="h-3 w-3 mr-1" />
                      Criar Playbook
                    </Button>
                  </Link>
                </div>
              ) : (
                recentPlaybooks.slice(0, 4).map((pb) => (
                  <Link key={pb.id} href={`/playbooks/${pb.id}`} className="block">
                    <div className="flex items-center justify-between p-2 rounded-lg hover:bg-muted/50 transition-colors">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate">{pb.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {pb.rule_count} regra{pb.rule_count !== 1 ? 's' : ''}
                        </p>
                      </div>
                      <span className="text-xs text-muted-foreground ml-2">
                        {formatRelativeDate(pb.updated_at)}
                      </span>
                    </div>
                  </Link>
                ))
              )}
            </CardContent>
          </Card>
        </MotionDiv>

        {/* Corpus Projects */}
        <MotionDiv
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.5 }}
        >
          <Card className="h-full">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Database className="h-4 w-4 text-emerald-500" />
                Projetos de Corpus
              </CardTitle>
              <Link href="/corpus">
                <Button variant="ghost" size="sm" className="h-7 text-xs">
                  Ver todos
                </Button>
              </Link>
            </CardHeader>
            <CardContent className="space-y-3">
              {recentCorpus.length === 0 ? (
                <div className="text-center py-6">
                  <Database className="h-8 w-8 mx-auto text-muted-foreground/50 mb-2" />
                  <p className="text-sm text-muted-foreground">Nenhum projeto de corpus</p>
                  <Link href="/corpus/new">
                    <Button variant="outline" size="sm" className="mt-3">
                      <Plus className="h-3 w-3 mr-1" />
                      Criar Projeto
                    </Button>
                  </Link>
                </div>
              ) : (
                recentCorpus.slice(0, 4).map((cp) => (
                  <Link key={cp.id} href={`/corpus/${cp.id}`} className="block">
                    <div className="flex items-center justify-between p-2 rounded-lg hover:bg-muted/50 transition-colors">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate">{cp.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {cp.document_count} documento{cp.document_count !== 1 ? 's' : ''}
                        </p>
                      </div>
                      <span className="text-xs text-muted-foreground ml-2">
                        {formatRelativeDate(cp.updated_at)}
                      </span>
                    </div>
                  </Link>
                ))
              )}
            </CardContent>
          </Card>
        </MotionDiv>

        {/* Review Tables */}
        <MotionDiv
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.6 }}
        >
          <Card className="h-full">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Table2 className="h-4 w-4 text-amber-500" />
                Tabelas de Revisão
              </CardTitle>
              <Link href="/review-tables">
                <Button variant="ghost" size="sm" className="h-7 text-xs">
                  Ver todas
                </Button>
              </Link>
            </CardHeader>
            <CardContent className="space-y-3">
              {recentReviews.length === 0 ? (
                <div className="text-center py-6">
                  <Table2 className="h-8 w-8 mx-auto text-muted-foreground/50 mb-2" />
                  <p className="text-sm text-muted-foreground">Nenhuma tabela de revisão</p>
                  <Link href="/review-tables/new">
                    <Button variant="outline" size="sm" className="mt-3">
                      <Plus className="h-3 w-3 mr-1" />
                      Criar Tabela
                    </Button>
                  </Link>
                </div>
              ) : (
                recentReviews.slice(0, 4).map((rv) => (
                  <Link key={rv.id} href={`/review-tables/${rv.id}`} className="block">
                    <div className="flex items-center justify-between p-2 rounded-lg hover:bg-muted/50 transition-colors">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate">{rv.name}</p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <Badge variant={statusConfig[rv.status]?.variant || 'outline'} className="text-[10px] h-4">
                            {statusConfig[rv.status]?.label || rv.status}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            {rv.processed_documents}/{rv.total_documents} docs
                          </span>
                        </div>
                      </div>
                    </div>
                  </Link>
                ))
              )}
            </CardContent>
          </Card>
        </MotionDiv>
      </div>
    </div>
  );
}
