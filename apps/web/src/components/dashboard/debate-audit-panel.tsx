"use client";

import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import {
    AlertTriangle,
    CheckCircle2,
    MessageSquare,
    Scale,
    GitMerge,
    Bot,
    FileWarning,
    ChevronDown,
    Copy,
    Check
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface Issue {
    type?: string;
    message?: string;
    summary?: string;
    severity?: string;
    agent?: string;
}

interface Decision {
    decision?: string;
    choice?: string;
    rationale?: string;
    source?: string;
}

interface Critique {
    issues?: Issue[];
    summary?: string;
    by_agent?: Record<string, any>;
}

interface Revision {
    changelog?: string[];
    resolved?: string[];
    unresolved?: string[];
}

interface Merge {
    rationale?: string;
    decisions?: Decision[];
    judge_structured?: Record<string, any>;
}

interface Review {
    critique?: Critique;
    revision?: Revision;
    merge?: Merge;
}

interface Drafts {
    drafts_by_model?: Record<string, string>;
    drafts_order?: string[];
    reviewers_order?: string[];
    reviews_by_model?: Record<string, string>;
    revisions_by_model?: Record<string, string>;
    all_reviews_history?: Array<Record<string, string>>;
    all_revisions_history?: Array<Record<string, string>>;
    committee_rounds_executed?: number;
    critique_structured?: any;
    judge_structured?: any;
    judge_model?: string;
    risk_flags?: any[];
}

interface ProcessedSection {
    section_title: string;
    merged_content?: string;
    has_significant_divergence?: boolean;
    divergence_details?: string;
    drafts?: Drafts;
    review?: Review;
    claims_requiring_citation?: any[];
    removed_claims?: any[];
    risk_flags?: any[];
    quality_score?: number;
}

interface DebateAuditPanelProps {
    metadata?: {
        processed_sections?: ProcessedSection[];
        has_any_divergence?: boolean;
        divergence_summary?: string;
        committee_config?: {
            judge_model?: string;
            strategist_model?: string;
            drafter_models?: string[];
            reviewer_models?: string[];
        };
        judge_model?: string;
        strategist_model?: string;
    };
    className?: string;
}

const MODEL_LABELS: Record<string, string> = {
    "gemini-2.0-flash-thinking-exp": "Gemini 2.0 Flash Thinking",
    "gemini-2.5-pro-preview-05-06": "Gemini 2.5 Pro",
    "gemini-2.5-flash-preview-05-20": "Gemini 2.5 Flash",
    "claude-sonnet-4-20250514": "Claude Sonnet 4",
    "claude-opus-4-20250514": "Claude Opus 4",
    "gpt-4o": "GPT-4o",
    "gpt-4-turbo": "GPT-4 Turbo",
    "o1": "OpenAI o1",
    "o1-mini": "OpenAI o1-mini",
};

const getModelLabel = (modelId: string): string => {
    return MODEL_LABELS[modelId] || modelId;
};

function CopyButton({ text }: { text: string }) {
    const [copied, setCopied] = useState(false);

    const handleCopy = async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <Button
            variant="ghost"
            size="sm"
            onClick={handleCopy}
            className="h-6 px-2 text-[10px]"
        >
            {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
        </Button>
    );
}

function DraftCard({ modelId, content }: { modelId: string; content: string }) {
    const [expanded, setExpanded] = useState(false);
    const preview = content.slice(0, 300);
    const hasMore = content.length > 300;

    return (
        <div className="rounded-lg border border-outline/20 bg-muted/5 overflow-hidden">
            <div className="flex items-center justify-between px-3 py-2 bg-muted/20 border-b border-outline/10">
                <div className="flex items-center gap-2">
                    <Bot className="h-3.5 w-3.5 text-blue-600" />
                    <span className="text-xs font-medium">{getModelLabel(modelId)}</span>
                </div>
                <CopyButton text={content} />
            </div>
            <div className="px-3 py-2">
                <pre className="text-[11px] text-muted-foreground whitespace-pre-wrap font-sans">
                    {expanded ? content : preview}
                    {!expanded && hasMore && "..."}
                </pre>
                {hasMore && (
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setExpanded(!expanded)}
                        className="mt-2 h-6 px-2 text-[10px]"
                    >
                        <ChevronDown className={cn("h-3 w-3 mr-1 transition-transform", expanded && "rotate-180")} />
                        {expanded ? "Recolher" : "Expandir"}
                    </Button>
                )}
            </div>
        </div>
    );
}

function ModelTextCard({
    modelId,
    content,
    title,
}: {
    modelId: string;
    content: string;
    title: string;
}) {
    const [expanded, setExpanded] = useState(false);
    const preview = content.slice(0, 400);
    const hasMore = content.length > 400;

    return (
        <div className="rounded-lg border border-outline/20 bg-muted/5 overflow-hidden">
            <div className="flex items-center justify-between px-3 py-2 bg-muted/20 border-b border-outline/10">
                <div className="flex items-center gap-2">
                    <Bot className="h-3.5 w-3.5 text-blue-600" />
                    <span className="text-xs font-medium">{title}</span>
                    <Badge variant="outline" className="text-[10px] h-5">
                        {getModelLabel(modelId)}
                    </Badge>
                </div>
                <CopyButton text={content} />
            </div>
            <div className="px-3 py-2">
                <pre className="text-[11px] text-muted-foreground whitespace-pre-wrap font-sans">
                    {expanded ? content : preview}
                    {!expanded && hasMore && "..."}
                </pre>
                {hasMore && (
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setExpanded(!expanded)}
                        className="mt-2 h-6 px-2 text-[10px]"
                    >
                        <ChevronDown className={cn("h-3 w-3 mr-1 transition-transform", expanded && "rotate-180")} />
                        {expanded ? "Recolher" : "Expandir"}
                    </Button>
                )}
            </div>
        </div>
    );
}

function JsonCard({ title, value }: { title: string; value: any }) {
    const [expanded, setExpanded] = useState(false);
    const content = useMemo(() => {
        try {
            return JSON.stringify(value ?? null, null, 2);
        } catch {
            return String(value ?? '');
        }
    }, [value]);
    const preview = content.slice(0, 800);
    const hasMore = content.length > 800;

    if (!content.trim()) return null;

    return (
        <div className="rounded-lg border border-outline/20 bg-muted/5 overflow-hidden">
            <div className="flex items-center justify-between px-3 py-2 bg-muted/20 border-b border-outline/10">
                <div className="flex items-center gap-2">
                    <FileWarning className="h-3.5 w-3.5 text-slate-600" />
                    <span className="text-xs font-medium">{title}</span>
                </div>
                <CopyButton text={content} />
            </div>
            <div className="px-3 py-2">
                <pre className="text-[11px] text-muted-foreground whitespace-pre-wrap font-mono">
                    {expanded ? content : preview}
                    {!expanded && hasMore && "..."}
                </pre>
                {hasMore && (
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setExpanded(!expanded)}
                        className="mt-2 h-6 px-2 text-[10px]"
                    >
                        <ChevronDown className={cn("h-3 w-3 mr-1 transition-transform", expanded && "rotate-180")} />
                        {expanded ? "Recolher" : "Expandir"}
                    </Button>
                )}
            </div>
        </div>
    );
}

function IssuesList({ issues }: { issues: Issue[] }) {
    if (!issues.length) return null;

    return (
        <div className="space-y-2">
            {issues.map((issue, idx) => {
                const message = typeof issue === 'string'
                    ? issue
                    : issue.message || issue.summary || JSON.stringify(issue);
                const type = typeof issue === 'object' ? issue.type : null;
                const severity = typeof issue === 'object' ? issue.severity : null;

                return (
                    <div
                        key={idx}
                        className={cn(
                            "rounded-lg border px-3 py-2 text-xs",
                            severity === 'critical'
                                ? "border-red-200 bg-red-50"
                                : "border-amber-200 bg-amber-50"
                        )}
                    >
                        <div className="flex items-start gap-2">
                            <AlertTriangle className={cn(
                                "h-3.5 w-3.5 mt-0.5 shrink-0",
                                severity === 'critical' ? "text-red-600" : "text-amber-600"
                            )} />
                            <div>
                                {type && (
                                    <span className="font-semibold text-foreground/80">{type}: </span>
                                )}
                                <span className="text-muted-foreground">{message}</span>
                            </div>
                        </div>
                    </div>
                );
            })}
        </div>
    );
}

function DecisionsList({ decisions }: { decisions: Decision[] }) {
    if (!decisions.length) return null;

    return (
        <div className="space-y-2">
            {decisions.map((decision, idx) => {
                const text = typeof decision === 'string'
                    ? decision
                    : decision.decision || decision.choice || decision.rationale || JSON.stringify(decision);
                const source = typeof decision === 'object' ? decision.source : null;

                return (
                    <div key={idx} className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs">
                        <div className="flex items-start gap-2">
                            <CheckCircle2 className="h-3.5 w-3.5 mt-0.5 shrink-0 text-emerald-600" />
                            <div>
                                {source && (
                                    <span className="font-semibold text-foreground/80">[{source}] </span>
                                )}
                                <span className="text-muted-foreground">{text}</span>
                            </div>
                        </div>
                    </div>
                );
            })}
        </div>
    );
}

function SectionDebateCard({ section }: { section: ProcessedSection }) {
    const drafts = section.drafts?.drafts_by_model || {};
    const draftEntries = Object.entries(drafts).filter(([_, content]) => content && typeof content === 'string');
    const reviews = section.drafts?.reviews_by_model || {};
    const reviewEntries = Object.entries(reviews).filter(([_, content]) => content && typeof content === 'string');
    const revisions = section.drafts?.revisions_by_model || {};
    const revisionEntries = Object.entries(revisions).filter(([_, content]) => content && typeof content === 'string');
    const reviewersOrder = Array.isArray(section.drafts?.reviewers_order) ? section.drafts?.reviewers_order : [];
    const draftersOrder = Array.isArray(section.drafts?.drafts_order) ? section.drafts?.drafts_order : [];
    const judgeModel = String(section.drafts?.judge_model || section.review?.merge?.judge_structured?.model || '').trim();
    const roundsExecutedRaw = section.drafts?.committee_rounds_executed;
    const roundsExecuted = Number.isFinite(Number(roundsExecutedRaw)) ? Number(roundsExecutedRaw) : null;
    const allReviewsHistory = Array.isArray(section.drafts?.all_reviews_history) ? section.drafts?.all_reviews_history : [];
    const allRevisionsHistory = Array.isArray(section.drafts?.all_revisions_history) ? section.drafts?.all_revisions_history : [];
    const review = section.review || {};
    const critique = review.critique || {};
    const merge = review.merge || {};
    const revision = review.revision || {};

    const issues = Array.isArray(critique.issues) ? critique.issues : [];
    const decisions = Array.isArray(merge.decisions) ? merge.decisions : [];
    const riskFlags = Array.isArray(section.risk_flags) ? section.risk_flags : [];
    const claimsPending = Array.isArray(section.claims_requiring_citation) ? section.claims_requiring_citation : [];
    const unresolved = Array.isArray(revision.unresolved) ? revision.unresolved : [];

    const hasDivergence = section.has_significant_divergence;
    const hasIssues = issues.length > 0 || riskFlags.length > 0 || claimsPending.length > 0;

    return (
        <AccordionItem
            value={section.section_title}
            className="border rounded-xl overflow-hidden bg-card"
        >
            <AccordionTrigger className="px-4 py-3 hover:bg-muted/50 hover:no-underline">
                <div className="flex items-center justify-between w-full pr-2">
                    <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm">{section.section_title}</span>
                    </div>
                    <div className="flex items-center gap-2">
                        {draftEntries.length > 0 && (
                            <Badge variant="outline" className="text-[10px] h-5">
                                {draftEntries.length} drafts
                            </Badge>
                        )}
                        {reviewEntries.length > 0 && (
                            <Badge variant="outline" className="text-[10px] h-5">
                                {reviewEntries.length} reviews
                            </Badge>
                        )}
                        {revisionEntries.length > 0 && (
                            <Badge variant="outline" className="text-[10px] h-5">
                                {revisionEntries.length} revisoes
                            </Badge>
                        )}
                        {judgeModel && (
                            <Badge variant="outline" className="text-[10px] h-5">
                                Juiz: {getModelLabel(judgeModel)}
                            </Badge>
                        )}
                        {roundsExecuted != null && roundsExecuted > 1 && (
                            <Badge variant="secondary" className="text-[10px] h-5">
                                {roundsExecuted} rodadas
                            </Badge>
                        )}
                        {hasDivergence && (
                            <Badge variant="destructive" className="text-[10px] h-5">
                                Divergencia
                            </Badge>
                        )}
                        {hasIssues && !hasDivergence && (
                            <Badge variant="secondary" className="text-[10px] h-5 bg-amber-100 text-amber-700">
                                {issues.length + riskFlags.length} issues
                            </Badge>
                        )}
                        {!hasDivergence && !hasIssues && (
                            <Badge variant="outline" className="text-[10px] h-5 border-emerald-200 text-emerald-700">
                                Consenso
                            </Badge>
                        )}
                    </div>
                </div>
            </AccordionTrigger>
            <AccordionContent className="px-4 pb-4 pt-2 border-t border-outline/10 bg-muted/5">
                <div className="space-y-4">
                    {/* Divergence Details */}
                    {section.divergence_details && (
                        <div className="rounded-lg border border-red-200 bg-red-50 p-3">
                            <div className="flex items-center gap-2 mb-2">
                                <AlertTriangle className="h-4 w-4 text-red-600" />
                                <span className="text-xs font-semibold text-red-700">Detalhes da Divergencia</span>
                            </div>
                            <p className="text-xs text-red-600/80 whitespace-pre-wrap">
                                {section.divergence_details}
                            </p>
                        </div>
                    )}

                    {/* Drafts by Model */}
                    {draftEntries.length > 0 && (
                        <div className="space-y-2">
                            <div className="flex items-center gap-2">
                                <Bot className="h-4 w-4 text-blue-600" />
                                <span className="text-xs font-semibold">Drafts (Drafters)</span>
                            </div>
                            {draftersOrder.length > 0 && (
                                <div className="flex flex-wrap gap-2">
                                    {draftersOrder.map((mid) => (
                                        <Badge key={`drafter-${mid}`} variant="outline" className="text-[10px] bg-white">
                                            {getModelLabel(mid)}
                                        </Badge>
                                    ))}
                                </div>
                            )}
                            <div className="space-y-2">
                                {draftEntries.map(([modelId, content]) => (
                                    <DraftCard key={modelId} modelId={modelId} content={content as string} />
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Reviews by Model (R2) */}
                    {(reviewEntries.length > 0 || allReviewsHistory.length > 0) && (
                        <div className="space-y-2">
                            <div className="flex items-center gap-2">
                                <MessageSquare className="h-4 w-4 text-amber-600" />
                                <span className="text-xs font-semibold">Críticas (Reviewers)</span>
                            </div>
                            {reviewersOrder.length > 0 && (
                                <div className="flex flex-wrap gap-2">
                                    {reviewersOrder.map((mid) => (
                                        <Badge key={`reviewer-${mid}`} variant="outline" className="text-[10px] bg-white">
                                            {getModelLabel(mid)}
                                        </Badge>
                                    ))}
                                </div>
                            )}

                            {reviewEntries.length > 0 && (
                                <div className="space-y-2">
                                    {reviewEntries.map(([modelId, content]) => (
                                        <ModelTextCard key={`review-${modelId}`} modelId={modelId} content={content as string} title="Crítica" />
                                    ))}
                                </div>
                            )}

                            {allReviewsHistory.length > 0 && (
                                <Accordion type="single" collapsible className="w-full">
                                    <AccordionItem value="reviews-history" className="border rounded-xl px-0 overflow-hidden bg-card">
                                        <AccordionTrigger className="px-3 py-2 hover:bg-muted/50 hover:no-underline font-medium text-xs">
                                            Histórico de críticas (rodadas)
                                        </AccordionTrigger>
                                        <AccordionContent className="px-3 pb-3 pt-2 border-t border-border/40 bg-muted/10">
                                            <div className="space-y-3">
                                                {allReviewsHistory.map((round, idx) => {
                                                    const entries = Object.entries(round || {}).filter(([_, c]) => c && typeof c === 'string');
                                                    if (entries.length === 0) return null;
                                                    return (
                                                        <div key={`round-${idx}`} className="space-y-2">
                                                            <div className="text-[10px] font-semibold uppercase text-muted-foreground">
                                                                Rodada {idx + 1}
                                                            </div>
                                                            <div className="space-y-2">
                                                                {entries.map(([modelId, content]) => (
                                                                    <ModelTextCard
                                                                        key={`round-${idx}-${modelId}`}
                                                                        modelId={modelId}
                                                                        content={content as string}
                                                                        title={`Crítica (R${idx + 1})`}
                                                                    />
                                                                ))}
                                                            </div>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </AccordionContent>
                                    </AccordionItem>
                                </Accordion>
                            )}
                        </div>
                    )}

                    {/* Revisions by Model (R3) */}
                    {(revisionEntries.length > 0 || allRevisionsHistory.length > 0) && (
                        <div className="space-y-2">
                            <div className="flex items-center gap-2">
                                <GitMerge className="h-4 w-4 text-violet-600" />
                                <span className="text-xs font-semibold">Revisões (Drafters)</span>
                            </div>

                            {revisionEntries.length > 0 && (
                                <div className="space-y-2">
                                    {revisionEntries.map(([modelId, content]) => (
                                        <ModelTextCard key={`revision-${modelId}`} modelId={modelId} content={content as string} title="Revisão" />
                                    ))}
                                </div>
                            )}

                            {allRevisionsHistory.length > 0 && (
                                <Accordion type="single" collapsible className="w-full">
                                    <AccordionItem value="revisions-history" className="border rounded-xl px-0 overflow-hidden bg-card">
                                        <AccordionTrigger className="px-3 py-2 hover:bg-muted/50 hover:no-underline font-medium text-xs">
                                            Histórico de revisões (rodadas)
                                        </AccordionTrigger>
                                        <AccordionContent className="px-3 pb-3 pt-2 border-t border-border/40 bg-muted/10">
                                            <div className="space-y-3">
                                                {allRevisionsHistory.map((round, idx) => {
                                                    const entries = Object.entries(round || {}).filter(([_, c]) => c && typeof c === 'string');
                                                    if (entries.length === 0) return null;
                                                    return (
                                                        <div key={`rev-round-${idx}`} className="space-y-2">
                                                            <div className="text-[10px] font-semibold uppercase text-muted-foreground">
                                                                Rodada {idx + 1}
                                                            </div>
                                                            <div className="space-y-2">
                                                                {entries.map(([modelId, content]) => (
                                                                    <ModelTextCard
                                                                        key={`rev-round-${idx}-${modelId}`}
                                                                        modelId={modelId}
                                                                        content={content as string}
                                                                        title={`Revisão (R${idx + 1})`}
                                                                    />
                                                                ))}
                                                            </div>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </AccordionContent>
                                    </AccordionItem>
                                </Accordion>
                            )}
                        </div>
                    )}

                    {/* Critique */}
                    {(critique.summary || issues.length > 0) && (
                        <div className="space-y-2">
                            <div className="flex items-center gap-2">
                                <MessageSquare className="h-4 w-4 text-amber-600" />
                                <span className="text-xs font-semibold">Critica do Comite</span>
                            </div>
                            {critique.summary && (
                                <p className="text-xs text-muted-foreground bg-muted/30 rounded-lg p-2">
                                    {critique.summary}
                                </p>
                            )}
                            <IssuesList issues={issues} />
                        </div>
                    )}

                    {/* Risk Flags */}
                    {riskFlags.length > 0 && (
                        <div className="space-y-2">
                            <div className="flex items-center gap-2">
                                <FileWarning className="h-4 w-4 text-orange-600" />
                                <span className="text-xs font-semibold">Risk Flags</span>
                            </div>
                            <div className="flex flex-wrap gap-2">
                                {riskFlags.map((flag, idx) => (
                                    <Badge key={idx} variant="outline" className="text-[10px] border-orange-200 bg-orange-50 text-orange-700">
                                        {typeof flag === 'string' ? flag : JSON.stringify(flag)}
                                    </Badge>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Claims Pending Citation */}
                    {claimsPending.length > 0 && (
                        <div className="space-y-2">
                            <div className="flex items-center gap-2">
                                <Scale className="h-4 w-4 text-violet-600" />
                                <span className="text-xs font-semibold">Claims Pendentes de Citacao</span>
                            </div>
                            <div className="space-y-1">
                                {claimsPending.slice(0, 5).map((claim, idx) => (
                                    <div key={idx} className="text-xs text-muted-foreground bg-violet-50 border border-violet-200 rounded px-2 py-1">
                                        {typeof claim === 'string' ? claim : JSON.stringify(claim)}
                                    </div>
                                ))}
                                {claimsPending.length > 5 && (
                                    <span className="text-[10px] text-muted-foreground">
                                        +{claimsPending.length - 5} mais...
                                    </span>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Merge Decision */}
                    {(merge.rationale || decisions.length > 0) && (
                        <div className="space-y-2">
                            <div className="flex items-center gap-2">
                                <GitMerge className="h-4 w-4 text-emerald-600" />
                                <span className="text-xs font-semibold">Decisao do Merge (Judge)</span>
                            </div>
                            {merge.rationale && (
                                <p className="text-xs text-muted-foreground bg-emerald-50 border border-emerald-200 rounded-lg p-2">
                                    <span className="font-semibold">Racional:</span> {merge.rationale}
                                </p>
                            )}
                            <DecisionsList decisions={decisions} />
                        </div>
                    )}

                    {merge?.judge_structured && Object.keys(merge.judge_structured || {}).length > 0 && (
                        <JsonCard title="Juiz (estrutura completa)" value={merge.judge_structured} />
                    )}

                    {/* Unresolved Issues */}
                    {unresolved.length > 0 && (
                        <div className="space-y-2">
                            <div className="flex items-center gap-2">
                                <AlertTriangle className="h-4 w-4 text-red-600" />
                                <span className="text-xs font-semibold">Issues Nao Resolvidas</span>
                            </div>
                            <div className="space-y-1">
                                {unresolved.map((item, idx) => (
                                    <div key={idx} className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1">
                                        {typeof item === 'string' ? item : JSON.stringify(item)}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </AccordionContent>
        </AccordionItem>
    );
}

export function DebateAuditPanel({ metadata, className }: DebateAuditPanelProps) {
    const sections = useMemo(() => {
        return Array.isArray(metadata?.processed_sections) ? metadata.processed_sections : [];
    }, [metadata]);

    const stats = useMemo(() => {
        let totalDivergences = 0;
        let totalIssues = 0;
        let totalDrafts = 0;

        sections.forEach(section => {
            if (section.has_significant_divergence) totalDivergences++;
            const issues = section.review?.critique?.issues || [];
            const riskFlags = section.risk_flags || [];
            totalIssues += issues.length + riskFlags.length;
            const drafts = Object.keys(section.drafts?.drafts_by_model || {});
            totalDrafts += drafts.length;
        });

        return { totalDivergences, totalIssues, totalDrafts };
    }, [sections]);

    // Sort: divergences first, then by issues count
    const sortedSections = useMemo(() => {
        if (!sections.length) return [];
        return [...sections].sort((a, b) => {
            if (a.has_significant_divergence && !b.has_significant_divergence) return -1;
            if (!a.has_significant_divergence && b.has_significant_divergence) return 1;
            const aIssues = (a.review?.critique?.issues?.length || 0) + (a.risk_flags?.length || 0);
            const bIssues = (b.review?.critique?.issues?.length || 0) + (b.risk_flags?.length || 0);
            return bIssues - aIssues;
        });
    }, [sections]);

    // Default open: sections with divergence
    const defaultOpen = useMemo(() => {
        if (!sortedSections.length) return [];
        return sortedSections
            .filter(s => s.has_significant_divergence)
            .map(s => s.section_title);
    }, [sortedSections]);

    if (!sections.length) {
        return (
            <div className={cn("rounded-xl border border-outline/20 bg-card p-6 text-center", className)}>
                <MessageSquare className="h-8 w-8 mx-auto mb-2 text-muted-foreground/30" />
                <p className="text-sm text-muted-foreground">
                    Nenhum debate registrado para este documento.
                </p>
                <p className="text-xs text-muted-foreground/70 mt-1">
                    Os debates sao registrados quando o documento e gerado com modo agente ativo.
                </p>
            </div>
        );
    }

    return (
        <div className={cn("space-y-4", className)}>
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <MessageSquare className="h-5 w-5 text-indigo-600" />
                    <h3 className="text-sm font-bold">Auditoria de Debates</h3>
                </div>
                <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-[10px] h-5">
                        {sections.length} secoes
                    </Badge>
                    <Badge variant="outline" className="text-[10px] h-5">
                        {stats.totalDrafts} drafts
                    </Badge>
                    {stats.totalDivergences > 0 && (
                        <Badge variant="destructive" className="text-[10px] h-5">
                            {stats.totalDivergences} divergencias
                        </Badge>
                    )}
                    {stats.totalIssues > 0 && (
                        <Badge variant="secondary" className="text-[10px] h-5 bg-amber-100 text-amber-700">
                            {stats.totalIssues} issues
                        </Badge>
                    )}
                </div>
            </div>

            {/* Committee config (selected models by role) */}
            {(metadata?.committee_config || metadata?.judge_model || metadata?.strategist_model) && (
                <div className="rounded-lg border border-outline/20 bg-muted/5 p-3">
                    <div className="text-[10px] font-semibold uppercase text-muted-foreground mb-2">Modelos por Papel</div>
                    <div className="flex flex-wrap gap-2">
                        {(metadata?.committee_config?.strategist_model || metadata?.strategist_model) && (
                            <Badge variant="outline" className="text-[10px] bg-white">
                                Orquestrador: {getModelLabel(String(metadata?.committee_config?.strategist_model || metadata?.strategist_model))}
                            </Badge>
                        )}
                        {(metadata?.committee_config?.judge_model || metadata?.judge_model) && (
                            <Badge variant="outline" className="text-[10px] bg-white">
                                Juiz: {getModelLabel(String(metadata?.committee_config?.judge_model || metadata?.judge_model))}
                            </Badge>
                        )}
                        {(metadata?.committee_config?.drafter_models || []).map((mid) => (
                            <Badge key={`meta-drafter-${mid}`} variant="outline" className="text-[10px] bg-white">
                                Drafter: {getModelLabel(String(mid))}
                            </Badge>
                        ))}
                        {(metadata?.committee_config?.reviewer_models || []).map((mid) => (
                            <Badge key={`meta-reviewer-${mid}`} variant="outline" className="text-[10px] bg-white">
                                Reviewer: {getModelLabel(String(mid))}
                            </Badge>
                        ))}
                    </div>
                </div>
            )}

            {/* Global Divergence Summary */}
            {metadata?.divergence_summary && metadata.has_any_divergence && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                    <div className="flex items-center gap-2 mb-2">
                        <AlertTriangle className="h-4 w-4 text-amber-600" />
                        <span className="text-xs font-semibold text-amber-700">Resumo Global de Divergencias</span>
                    </div>
                    <p className="text-xs text-amber-600/80 whitespace-pre-wrap">
                        {metadata.divergence_summary}
                    </p>
                </div>
            )}

            {/* Sections Accordion */}
            <Accordion type="multiple" defaultValue={defaultOpen} className="space-y-2">
                {sortedSections.map(section => (
                    <SectionDebateCard key={section.section_title} section={section} />
                ))}
            </Accordion>
        </div>
    );
}
