'use client';

import { useEffect, useMemo, useRef } from 'react';
import { cn } from '@/lib/utils';
import {
  CheckCircle2,
  ChevronDown,
  FileText,
  Paperclip,
  Search,
  AlertCircle,
  Loader2,
  Globe,
  ListFilter,
  Sparkles,
  Brain,
  Zap,
} from 'lucide-react';
import { resolveUiLang, type UiLang } from '@/lib/ui-lang';

export interface ActivityStep {
  id: string;
  title: string;
  status?: 'running' | 'done' | 'error';
  detail?: string;
  tags?: string[];
  kind?: 'assess' | 'attachment_review' | 'file_terms' | 'web_search' | 'delegate_subtask' | 'generic';
  attachments?: Array<{ name: string; kind?: string; ext?: string }>;
  terms?: string[];
  sources?: Array<{ title?: string; url: string }>;
  t?: number;
}

export interface Citation {
  number: string;
  title?: string;
  url?: string;
  quote?: string;
}

interface ActivityPanelProps {
  steps: ActivityStep[];
  citations: Citation[];
  startTime?: number | null;
  endTime?: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isStreaming: boolean;
}

function getFaviconUrl(url?: string): string | null {
  if (!url) return null;
  if (process.env.NEXT_PUBLIC_DISABLE_FAVICONS === 'true') return null;
  try {
    const hostname = new URL(url).hostname;
    return `https://www.google.com/s2/favicons?domain=${hostname}&sz=32`;
  } catch {
    return null;
  }
}

function urlDomain(url?: string): string {
  if (!url) return '';
  try {
    return new URL(url).hostname.replace(/^www\./i, '');
  } catch {
    return '';
  }
}

function dedupeStrings(items: string[] = []): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const raw of items) {
    const v = String(raw || '').trim();
    if (!v) continue;
    const k = v.toLowerCase();
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(v);
  }
  return out;
}

function normalizeStepKind(step: ActivityStep): ActivityStep['kind'] {
  if (step.kind) return step.kind;
  const id = String(step.id || '').toLowerCase();
  if (id === 'assess_query') return 'assess';
  if (id === 'reviewing_attached_file') return 'attachment_review';
  if (id === 'checking_terms') return 'file_terms';
  if (id === 'web_search') return 'web_search';
  if (id === 'delegate_subtask' || id.includes('delegate')) return 'delegate_subtask';
  return 'generic';
}

function normalizeStepTitle(step: ActivityStep, lang: UiLang): string {
  const id = String(step.id || '').toLowerCase();
  const dict = {
    pt: {
      assess_query: 'Avaliando a pergunta',
      reviewing_attached_file: 'Revisando arquivo anexado',
      checking_terms: 'Buscando termos no anexo',
      web_search: 'Pesquisando na web por informações relevantes',
      delegate_subtask: 'Delegado para Haiku',
      response_clarity: 'Preparando a resposta',
    },
    en: {
      assess_query: 'Assessing query',
      reviewing_attached_file: 'Reviewing attached file',
      checking_terms: 'Checking for terms in attached file',
      web_search: 'Searching the web for relevant information',
      delegate_subtask: 'Delegated to Haiku',
      response_clarity: 'Preparing response clarity',
    },
  } as const;
  const mapped = (dict as any)?.[lang]?.[id];
  const title = String(step.title || '').trim();
  return mapped || title || (lang === 'pt' ? 'Processando' : 'Working');
}

function normalizeSources(step: ActivityStep, citations: Citation[]): Array<{ title?: string; url: string }> {
  const sources = Array.isArray(step.sources) ? step.sources : [];
  const normalized = sources
    .map((s) => ({ title: s?.title ? String(s.title) : undefined, url: String(s?.url || '').trim() }))
    .filter((s) => s.url && /^https?:\/\//i.test(s.url));

  if (normalized.length > 0) return normalized;

  return citations
    .map((c) => ({ title: c?.title ? String(c.title) : undefined, url: String(c?.url || '').trim() }))
    .filter((s) => s.url && /^https?:\/\//i.test(s.url));
}

function StepIcon({ step, isStreaming }: { step: ActivityStep; isStreaming?: boolean }) {
  const kind = normalizeStepKind(step);
  const id = String(step.id || '').toLowerCase();

  // Spinner for running steps
  if (step.status === 'running' && isStreaming) {
    return <Loader2 className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500 animate-spin" />;
  }

  // Error state
  if (step.status === 'error') {
    return <AlertCircle className="h-3.5 w-3.5 text-red-500" />;
  }

  // Icons by kind/id (matching Harvey.ai reference)
  if (kind === 'attachment_review' || id.includes('attach') || id.includes('review')) {
    return <Paperclip className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500" />;
  }
  if (kind === 'file_terms' || id.includes('term') || id.includes('check')) {
    return <ListFilter className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500" />;
  }
  if (kind === 'web_search' || id.includes('web') || id.includes('search') || id.includes('pesquis')) {
    return <Globe className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500" />;
  }
  if (kind === 'delegate_subtask' || id.includes('delegate')) {
    return <Zap className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500" />;
  }
  if (id.includes('evaluat') || id.includes('evidence') || id.includes('avalia')) {
    return <Brain className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500" />;
  }
  if (id.includes('response') || id.includes('clarity') || id.includes('prepar') || id.includes('resposta')) {
    return <Sparkles className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500" />;
  }

  // Default bullet
  return (
    <div className="h-2 w-2 rounded-full bg-slate-300 dark:bg-slate-600 mt-1" />
  );
}

export function ActivityPanel({
  steps,
  citations,
  open,
  onOpenChange,
  isStreaming,
}: ActivityPanelProps) {
  const contentRef = useRef<HTMLDivElement>(null);
  const hasContent = (steps?.length ?? 0) > 0 || (citations?.length ?? 0) > 0;
  const lang = useMemo(() => resolveUiLang(), []);

  const labels = useMemo(() => {
    const dict = {
      pt: {
        working: 'Trabalhando...',
        finished: (n: number) => `Concluído em ${n} etapas`,
        fileBadge: (ext: string) => ext.toUpperCase(),
        unknownFile: 'Arquivo',
      },
      en: {
        working: 'Working...',
        finished: (n: number) => `Finished in ${n} steps`,
        fileBadge: (ext: string) => ext.toUpperCase(),
        unknownFile: 'File',
      },
    } as const;
    return dict[lang];
  }, [lang]);

  const displaySteps = useMemo(() => {
    const base = Array.isArray(steps) ? [...steps] : [];
    const hasWeb = base.some((s) => String(s?.id || '').toLowerCase() === 'web_search');
    if ((citations?.length ?? 0) > 0 && !hasWeb) {
      base.push({
        id: 'web_search',
        title: '',
        status: isStreaming ? 'running' : 'done',
        kind: 'web_search',
      });
    }
    if (!isStreaming && base.length > 0) {
      const has = base.some((s) => String(s?.id || '').toLowerCase() === 'response_clarity');
      if (!has) {
        base.push({ id: 'response_clarity', title: '', status: 'done', kind: 'assess' });
      }
    }
    return base;
  }, [steps, citations?.length, isStreaming]);

  useEffect(() => {
    if (!open) return;
    if (!contentRef.current) return;
    contentRef.current.scrollTop = contentRef.current.scrollHeight;
  }, [open, displaySteps.length]);

  if (!hasContent) return null;

  return (
    <div data-testid="activity-panel" className="w-full max-w-[min(92%,76ch)] mb-2">
      {isStreaming && (
        <button
          type="button"
          onClick={() => onOpenChange(!open)}
          className="flex items-center gap-2 py-1.5 px-1 w-full text-left text-[13px] text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-300 transition-colors"
        >
          <span>{labels.working}</span>
          <ChevronDown className={cn('h-3.5 w-3.5 text-slate-400 dark:text-slate-500 transition-transform', open ? '' : '-rotate-90')} />
        </button>
      )}

      {open && (
        <div ref={contentRef} className="pl-1 pr-1 max-h-[520px] overflow-y-auto">
          <div className="space-y-4">
            {displaySteps.map((step) => {
              const kind = normalizeStepKind(step);
              const title = normalizeStepTitle(step, lang);
              const detail = String(step.detail || '').trim();
              const attachments = Array.isArray(step.attachments) ? step.attachments : [];
              const terms = dedupeStrings(Array.isArray(step.terms) ? step.terms : (step.tags || []));
              const sources = normalizeSources(step, citations);

              return (
                <div key={step.id} className="flex gap-2.5">
                  <div className="pt-0.5 flex-shrink-0">
                    <StepIcon step={step} isStreaming={isStreaming} />
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className={cn(
                      'text-[13px] leading-snug',
                      step.status === 'error'
                        ? 'text-red-600 dark:text-red-400'
                        : 'text-slate-700 dark:text-slate-300'
                    )}>
                      {title}
                    </div>

                    {detail && (
                      <div className="mt-1 text-[12px] text-slate-500 dark:text-slate-400 leading-relaxed">
                        {detail}
                      </div>
                    )}

                    {kind === 'attachment_review' && attachments.length > 0 && (
                      <div className="mt-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800/50">
                        {attachments.slice(0, 6).map((att, idx) => {
                          const name = String(att?.name || '').trim() || labels.unknownFile;
                          const extRaw = String(att?.ext || att?.kind || '').trim();
                          const ext = extRaw ? labels.fileBadge(extRaw) : '';
                          return (
                            <div
                              key={`${name}-${idx}`}
                              className={cn('flex items-center gap-2 px-3 py-2', idx > 0 && 'border-t border-slate-200 dark:border-slate-700')}
                            >
                              <FileText className="h-4 w-4 text-red-500 dark:text-red-400" />
                              <div className="min-w-0 flex-1 text-[13px] text-slate-700 dark:text-slate-300 truncate">{name}</div>
                              {ext && (
                                <div className="text-[12px] text-slate-400 dark:text-slate-500 uppercase tracking-wide">{ext}</div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {kind === 'file_terms' && terms.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {terms.slice(0, 10).map((term) => (
                          <span
                            key={term}
                            className="inline-flex items-center gap-1 rounded-full bg-slate-100 dark:bg-slate-800 px-2.5 py-1 text-[12px] text-slate-600 dark:text-slate-400 border border-slate-200/60 dark:border-slate-700/60"
                          >
                            <Search className="h-3 w-3 text-slate-400 dark:text-slate-500" />
                            {term}
                          </span>
                        ))}
                      </div>
                    )}

                    {kind === 'web_search' && sources.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {sources.slice(0, 12).map((src) => {
                          const favicon = getFaviconUrl(src.url);
                          const domain = urlDomain(src.url);
                          const label = String(src.title || domain || 'source').trim();
                          return (
                            <a
                              key={src.url}
                              href={src.url}
                              target="_blank"
                              rel="noreferrer noopener"
                              className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/80 px-2.5 py-1 text-[12px] text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700/80 hover:border-slate-300 dark:hover:border-slate-600 transition-colors"
                            >
                              {favicon ? (
                                // eslint-disable-next-line @next/next/no-img-element
                                <img src={favicon} alt="" className="h-4 w-4 rounded-sm" />
                              ) : (
                                <Globe className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500" />
                              )}
                              <span className="max-w-[180px] truncate">{label}</span>
                            </a>
                          );
                        })}
                      </div>
                    )}

                    {kind === 'generic' && Array.isArray(step.tags) && step.tags.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {dedupeStrings(step.tags).slice(0, 10).map((tag) => (
                          <span key={tag} className="inline-flex items-center gap-1 rounded-full bg-slate-100 dark:bg-slate-800 px-2.5 py-1 text-[12px] text-slate-600 dark:text-slate-400">
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {!isStreaming && displaySteps.length > 0 && (
        <button
          type="button"
          onClick={() => onOpenChange(!open)}
          className="mt-2 flex items-center gap-2 py-1.5 px-1 w-full text-left text-[13px] text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-300 transition-colors"
        >
          <CheckCircle2 className="h-4 w-4 text-slate-400 dark:text-slate-500" />
          <span>{labels.finished(displaySteps.length)}</span>
          <ChevronDown className={cn('h-3.5 w-3.5 text-slate-400 dark:text-slate-500 transition-transform', open ? '' : '-rotate-90')} />
        </button>
      )}
    </div>
  );
}
