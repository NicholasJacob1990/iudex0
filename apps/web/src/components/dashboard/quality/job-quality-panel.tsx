import { useEffect, useMemo, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Button } from '@/components/ui/button';
import { AlertTriangle, ShieldAlert, ChevronDown, ChevronRight, Copy } from 'lucide-react';
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

export function JobQualityPanel({ events }: JobQualityPanelProps) {
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

    if (sections.length === 0) return null;

    return (
        <div className="space-y-4">
            {/* Header Summary Card */}
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                <div className="flex items-center gap-3 mb-3">
                    <div className="h-8 w-8 rounded-full bg-amber-100 flex items-center justify-center">
                        <ShieldAlert className="h-4 w-4 text-amber-600" />
                    </div>
                    <div>
                        <h3 className="text-sm font-bold text-amber-900">Qualidade & Pendências</h3>
                        <p className="text-xs text-amber-700/80">Monitoramento de riscos e citações da minuta</p>
                    </div>
                </div>

                <div className="flex flex-wrap gap-2">
                    <Badge variant="outline" className="bg-white border-amber-200 text-amber-700">
                        {summary.pending} pendência(s)
                    </Badge>
                    <Badge variant="outline" className="bg-white border-amber-200 text-amber-700">
                        {summary.removed} removido(s)
                    </Badge>
                    {summary.divergences > 0 && (
                        <Badge className="bg-amber-100 text-amber-800 border-amber-200 hover:bg-amber-200">
                            {summary.divergences} divergência(s)
                        </Badge>
                    )}
                    {summary.reviewIssues > 0 && (
                        <Badge variant="outline" className="bg-white border-amber-200 text-amber-700">
                            {summary.reviewIssues} issue(s)
                        </Badge>
                    )}
                </div>

                {summary.riskFlags.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-amber-200/60 flex flex-wrap gap-2">
                        {summary.riskFlags.slice(0, 8).map((rf) => (
                            <Badge key={rf} variant="secondary" className="bg-white/80 text-amber-800 text-[10px]">
                                {rf}
                            </Badge>
                        ))}
                    </div>
                )}
            </div>

            {/* Sections List */}
            <div className="space-y-3">
                {sections.map(({ section, ev, reviewInfo }) => (
                    <div key={section} className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
                        <div className="p-3 bg-muted/30 border-b border-border/50 flex items-center justify-between">
                            <h4 className="text-xs font-semibold text-foreground">{section}</h4>
                            <div className="flex gap-1.5">
                                {(ev.claims_requiring_citation?.length ?? ev.pending_citations_count ?? 0) > 0 && (
                                    <Badge variant="outline" className="text-[10px] border-amber-200 text-amber-600 bg-amber-50">
                                        {(ev.claims_requiring_citation?.length ?? ev.pending_citations_count ?? 0)} cit. pendentes
                                    </Badge>
                                )}
                                {(ev.removed_claims?.length ?? ev.removed_claims_count ?? 0) > 0 && (
                                    <Badge variant="outline" className="text-[10px] border-orange-200 text-orange-600 bg-orange-50">
                                        {(ev.removed_claims?.length ?? ev.removed_claims_count ?? 0)} rem.
                                    </Badge>
                                )}
                                {ev.has_divergence && (
                                    <Badge variant="destructive" className="text-[10px] h-5">Divergência</Badge>
                                )}
                                {reviewInfo.count > 0 && (
                                    <Badge variant="outline" className="text-[10px] border-amber-200 text-amber-600 bg-amber-50">
                                        {reviewInfo.count} issue(s)
                                    </Badge>
                                )}
                            </div>
                        </div>

                        <div className="p-3 space-y-4">
                            {/* Pending citations */}
                            {ev.claims_requiring_citation && ev.claims_requiring_citation.length > 0 && (
                                <div className="space-y-2">
                                    <div className="flex items-center gap-1.5 text-xs font-medium text-amber-600">
                                        <AlertTriangle className="h-3.5 w-3.5" />
                                        Citações necessárias
                                    </div>
                                    <div className="space-y-2">
                                        {ev.claims_requiring_citation.map((c, idx) => (
                                            <div key={idx} className="rounded-lg bg-amber-50/50 border border-amber-100 p-2.5 text-xs">
                                                <p className="text-amber-900 mb-1">&quot;{c.claim}&quot;</p>
                                                {(c.why || c.suggested_citation) && (
                                                    <div className="pl-2 border-l-2 border-amber-200 text-amber-700/80 space-y-0.5">
                                                        {c.why && <p>{c.why}</p>}
                                                        {c.suggested_citation && (
                                                            <p className="font-medium text-amber-800">Sugestão: {c.suggested_citation}</p>
                                                        )}
                                                    </div>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Removed claims */}
                            {ev.removed_claims && ev.removed_claims.length > 0 && (
                                <div className="space-y-2">
                                    <div className="flex items-center gap-1.5 text-xs font-medium text-orange-600">
                                        <ShieldAlert className="h-3.5 w-3.5" />
                                        Trechos removidos (Segurança)
                                    </div>
                                    <div className="space-y-2">
                                        {ev.removed_claims.map((c, idx) => (
                                            <div key={idx} className="rounded-lg bg-orange-50/50 border border-orange-100 p-2.5 text-xs">
                                                <p className="text-orange-900 mb-1 line-through opacity-80">&quot;{c.claim}&quot;</p>
                                                {c.why_removed && (
                                                    <p className="text-orange-700/80 italic">{c.why_removed}</p>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {(reviewInfo.count > 0 || reviewInfo.summary) && (
                                <div className="space-y-2">
                                    <div className="flex items-center gap-1.5 text-xs font-medium text-amber-600">
                                        <AlertTriangle className="h-3.5 w-3.5" />
                                        Issues do review
                                    </div>
                                    {reviewInfo.summary && (
                                        <p className="text-xs text-amber-900/80">{reviewInfo.summary}</p>
                                    )}
                                    {reviewInfo.issues.length > 0 && (
                                        <ul className="list-disc space-y-1 pl-4 text-xs text-amber-900/80">
                                            {reviewInfo.issues.map((issue, idx) => (
                                                <li key={`issue-${idx}`}>{issue}</li>
                                            ))}
                                        </ul>
                                    )}
                                </div>
                            )}

                            {/* Divergence details */}
                            {ev.has_divergence && ev.divergence_details && (
                                <div className="pt-2">
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        className="w-full justify-between h-8 text-[11px] hover:bg-muted/50"
                                        onClick={() => {
                                            navigator.clipboard?.writeText(ev.divergence_details || '');
                                        }}
                                    >
                                        <span>Copiar detalhes da divergência (RAW)</span>
                                        <Copy className="h-3 w-3 ml-2 text-muted-foreground" />
                                    </Button>
                                </div>
                            )}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
