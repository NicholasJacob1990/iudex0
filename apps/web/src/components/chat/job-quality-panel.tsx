import { useEffect, useMemo, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Button } from '@/components/ui/button';
import { AlertTriangle, ShieldAlert, ChevronDown, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

type ClaimRequiringCitation = {
  claim?: string;
  suggested_citation?: string | null;
  why?: string;
};

type RemovedClaim = {
  claim?: string;
  why_removed?: string;
};

type SectionProcessedEvent = {
  type: 'section_processed';
  section?: string;
  has_divergence?: boolean;
  pending_citations_count?: number;
  removed_claims_count?: number;
  risk_flags?: string[];
  claims_requiring_citation?: ClaimRequiringCitation[];
  removed_claims?: RemovedClaim[];
  divergence_details?: string;
  review?: {
    critique?: {
      issues?: any[];
      summary?: string;
    };
  };
};

interface JobQualityPanelProps {
  isVisible: boolean;
  events: any[];
}

const truncate = (value: string, max = 140) => {
  const text = String(value || '').trim();
  if (!text) return '';
  if (text.length <= max) return text;
  const sliced = text.slice(0, max);
  return `${sliced.replace(/\s+\S*$/, '').trim()}...`;
};

const extractReviewIssues = (review: SectionProcessedEvent['review'], limit = 3) => {
  const critique = review?.critique;
  const rawIssues = Array.isArray(critique?.issues) ? critique?.issues : [];
  const issues = rawIssues
    .map((issue) => {
      if (typeof issue === 'string') return issue;
      if (!issue || typeof issue !== 'object') return String(issue || '').trim();
      const message =
        String(
          issue.message
          ?? issue.summary
          ?? issue.label
          ?? issue.issue
          ?? issue.text
          ?? ''
        ).trim();
      const issueType = String(issue.type || '').trim();
      if (issueType && message && !message.startsWith(`${issueType}:`)) {
        return `${issueType}: ${message}`;
      }
      return message || issueType;
    })
    .filter(Boolean)
    .slice(0, limit)
    .map((item) => truncate(String(item), 160));
  const summary = typeof critique?.summary === 'string' ? truncate(critique.summary, 160) : '';
  return { count: rawIssues.length, issues, summary };
};

export function JobQualityPanel({ isVisible, events }: JobQualityPanelProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  const sections = useMemo(() => {
    const bySection = new Map<string, SectionProcessedEvent>();
    for (const e of events || []) {
      if (!e || e.type !== 'section_processed') continue;
      const ev = e as SectionProcessedEvent;
      const key = ev.section || 'Seção';
      bySection.set(key, ev); // latest snapshot wins
    }
    return Array.from(bySection.entries()).map(([section, ev]) => ({
      section,
      ev,
      reviewInfo: extractReviewIssues(ev.review),
    }));
  }, [events]);

  const summary = useMemo(() => {
    let pending = 0;
    let removed = 0;
    const riskFlags = new Set<string>();
    let divergences = 0;
    let reviewIssues = 0;

    for (const { ev, reviewInfo } of sections) {
      pending += ev.pending_citations_count || (ev.claims_requiring_citation?.length || 0);
      removed += ev.removed_claims_count || (ev.removed_claims?.length || 0);
      if (ev.has_divergence) divergences += 1;
      (ev.risk_flags || []).forEach((rf) => rf && riskFlags.add(rf));
      reviewIssues += reviewInfo.count;
    }

    return { pending, removed, riskFlags: Array.from(riskFlags), divergences, reviewIssues };
  }, [sections]);

  // Auto-collapse when nothing to show
  useEffect(() => {
    if (!isVisible) return;
    if (sections.length === 0) return;
    setIsExpanded(true);
  }, [isVisible, sections.length]);

  if (!isVisible || sections.length === 0) return null;

  return (
    <Card className="my-3 border-amber-500/25 bg-amber-500/5 overflow-hidden">
      <div
        className="flex items-center justify-between p-3 cursor-pointer hover:bg-white/5 transition-colors"
        onClick={() => setIsExpanded((v) => !v)}
      >
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-amber-400" />
          <span className="text-sm font-medium text-amber-100">Qualidade & Pendências</span>

          <div className="ml-2 flex flex-wrap gap-1">
            <Badge variant="outline" className="border-amber-500/30 text-[10px] text-amber-200">
              {summary.pending} pendência(s)
            </Badge>
            <Badge variant="outline" className="border-amber-500/30 text-[10px] text-amber-200">
              {summary.removed} removido(s)
            </Badge>
            <Badge
              variant="outline"
              className={cn(
                'border-amber-500/30 text-[10px]',
                summary.divergences > 0 ? 'text-amber-200' : 'text-emerald-200 border-emerald-500/30'
              )}
            >
              {summary.divergences} seção(ões) com divergência
            </Badge>
            {summary.reviewIssues > 0 && (
              <Badge variant="outline" className="border-amber-500/30 text-[10px] text-amber-200">
                {summary.reviewIssues} issue(s)
              </Badge>
            )}
          </div>
        </div>

        {isExpanded ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        )}
      </div>

      {isExpanded && (
        <div className="border-t border-amber-500/10 bg-black/20">
          <div className="p-3 flex flex-wrap gap-2 items-center">
            {summary.riskFlags.length > 0 ? (
              summary.riskFlags.slice(0, 8).map((rf) => (
                <Badge key={rf} className="bg-amber-500/20 text-amber-100 hover:bg-amber-500/25">
                  {rf}
                </Badge>
              ))
            ) : (
              <span className="text-xs text-muted-foreground">Sem riscos explícitos reportados.</span>
            )}
          </div>

          <ScrollArea className="h-[240px] w-full p-3">
            <div className="space-y-3">
              {sections.map(({ section, ev, reviewInfo }) => (
                <div key={section} className="rounded-lg border border-amber-500/15 bg-white/5 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-semibold text-amber-50">{section}</div>
                    <div className="flex gap-1">
                      <Badge variant="outline" className="border-amber-500/30 text-[10px] text-amber-200">
                        {(ev.claims_requiring_citation?.length ?? ev.pending_citations_count ?? 0) || 0} pend.
                      </Badge>
                      <Badge variant="outline" className="border-amber-500/30 text-[10px] text-amber-200">
                        {(ev.removed_claims?.length ?? ev.removed_claims_count ?? 0) || 0} remov.
                      </Badge>
                      {ev.has_divergence && (
                        <Badge className="bg-amber-500/20 text-amber-100">divergência</Badge>
                      )}
                      {reviewInfo.count > 0 && (
                        <Badge variant="outline" className="border-amber-500/30 text-[10px] text-amber-200">
                          {reviewInfo.count} issue(s)
                        </Badge>
                      )}
                    </div>
                  </div>

                  {/* Pending citations */}
                  {ev.claims_requiring_citation && ev.claims_requiring_citation.length > 0 && (
                    <div className="mt-2 space-y-2">
                      <div className="flex items-center gap-2 text-xs font-semibold text-amber-200">
                        <AlertTriangle className="h-3.5 w-3.5" />
                        Citações pendentes
                      </div>
                      <div className="space-y-2">
                        {ev.claims_requiring_citation.map((c, idx) => (
                          <div key={idx} className="rounded-md border border-amber-500/15 bg-black/20 p-2">
                            <div className="text-xs text-amber-50">{c.claim || '(item)'} </div>
                            {(c.why || c.suggested_citation) && (
                              <div className="mt-1 text-[11px] text-muted-foreground">
                                {c.why ? <span>{c.why}</span> : null}
                                {c.suggested_citation ? (
                                  <span className="ml-2">Sugestão: {c.suggested_citation}</span>
                                ) : null}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Removed claims */}
                  {ev.removed_claims && ev.removed_claims.length > 0 && (
                    <div className="mt-3 space-y-2">
                      <div className="text-xs font-semibold text-amber-200">Trechos removidos</div>
                      <div className="space-y-2">
                        {ev.removed_claims.map((c, idx) => (
                          <div key={idx} className="rounded-md border border-amber-500/15 bg-black/20 p-2">
                            <div className="text-xs text-amber-50">{c.claim || '(trecho)'} </div>
                            {c.why_removed && (
                              <div className="mt-1 text-[11px] text-muted-foreground">{c.why_removed}</div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {(reviewInfo.count > 0 || reviewInfo.summary) && (
                    <div className="mt-3 space-y-2">
                      <div className="text-xs font-semibold text-amber-200">Issues do review</div>
                      {reviewInfo.summary && (
                        <p className="text-[11px] text-amber-100/80">{reviewInfo.summary}</p>
                      )}
                      {reviewInfo.issues.length > 0 && (
                        <ul className="list-disc space-y-1 pl-4 text-[11px] text-amber-100/80">
                          {reviewInfo.issues.map((issue, idx) => (
                            <li key={`issue-${idx}`}>{issue}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}

                  {/* Divergence details (raw) */}
                  {ev.has_divergence && ev.divergence_details && (
                    <div className="mt-3">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 px-2 text-[11px] text-amber-200 hover:bg-white/10"
                        onClick={() => {
                          navigator.clipboard?.writeText(ev.divergence_details || '');
                        }}
                      >
                        Copiar divergências (raw)
                      </Button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </ScrollArea>
        </div>
      )}
    </Card>
  );
}







