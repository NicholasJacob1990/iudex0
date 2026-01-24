'use client';

import { useMemo } from 'react';
import { Badge } from '@/components/ui/badge';
import { ProcessTimeline, type TimelineGroup } from './process-timeline';
import { SectionCards, type SectionCardItem } from './section-cards';
import { ResearchPanel, type ResearchPanelData } from './research-panel';
import { useBillingStore } from '@/stores/billing-store';

type RawEvent = any;

interface NormalizedEvent {
    type: string;
    phase?: string;
    section?: string;
    agent?: string;
    ts?: string;
    data: any;
}

const LEGACY_TYPE_MAP: Record<string, string> = {
    outline_done: 'outline_generated',
    deep_research_start: 'research_start',
    deep_research_done: 'research_done',
    section_processed: 'section_completed',
    debate_done: 'section_completed',
    audit_done: 'audit_result',
    document_gate_done: 'documentgate_result',
    human_review_required: 'hil_required',
};

const TYPE_PHASE_MAP: Record<string, string> = {
    workflow_start: 'outline',
    outline_generated: 'outline',
    planner_decision: 'research',
    research_start: 'research',
    research_done: 'research',
    deepresearch_step: 'research',
    section_start: 'debate',
    section_context_start: 'research',
    section_context_ready: 'research',
    rag_routing: 'research',
    rag_gate: 'research',
    rag_results: 'research',
    agent_start: 'debate',
    agent_output: 'debate',
    agent_end: 'debate',
    section_stage: 'debate',
    section_completed: 'debate',
    section_error: 'debate',
    divergence_detected: 'debate',
    audit_result: 'audit',
    stylecheck_result: 'quality',
    documentgate_result: 'quality',
    hil_required: 'hil',
    hil_response: 'hil',
    workflow_end: 'final',
};

const PHASES = [
    { id: 'outline', label: 'Outline' },
    { id: 'research', label: 'Pesquisa' },
    { id: 'debate', label: 'Debate' },
    { id: 'audit', label: 'Auditoria' },
    { id: 'quality', label: 'Qualidade' },
    { id: 'final', label: 'Final' },
];

const normalizeEvent = (raw: RawEvent): NormalizedEvent => {
    const data = raw?.data && typeof raw.data === 'object' ? raw.data : (raw || {});
    const rawType = raw?.type || data?.type || '';
    const type = LEGACY_TYPE_MAP[rawType] || rawType;
    const phase = raw?.phase || TYPE_PHASE_MAP[type];
    const section = raw?.section || data?.section || data?.section_title || data?.sectionName;
    const agent = raw?.agent || data?.agent;
    const ts = raw?.ts || data?.ts;
    return { type, phase, section, agent, ts, data };
};

const pickLatest = <T,>(items: T[], predicate: (item: T) => boolean): T | null => {
    for (let i = items.length - 1; i >= 0; i -= 1) {
        if (predicate(items[i])) return items[i];
    }
    return null;
};

const truncate = (value: string, max = 140) => {
    const text = String(value || '').trim();
    if (!text) return '';
    if (text.length <= max) return text;
    const sliced = text.slice(0, max);
    return `${sliced.replace(/\s+\S*$/, '').trim()}...`;
};

const normalizeReview = (raw: any) => {
    const review = raw && typeof raw === 'object' ? raw : null;
    if (!review) return undefined;

    const critique = review.critique && typeof review.critique === 'object' ? review.critique : null;
    const revision = review.revision && typeof review.revision === 'object' ? review.revision : null;
    const merge = review.merge && typeof review.merge === 'object' ? review.merge : null;

    const rawIssues: any[] = Array.isArray(critique?.issues) ? critique?.issues : [];
    const rawDecisions: any[] = Array.isArray(merge?.decisions) ? merge?.decisions : [];

    const issueLabels = rawIssues
        .map((issue: any) => {
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
        .slice(0, 3)
        .map((item: string) => truncate(String(item), 120));

    const decisionLabels = rawDecisions
        .map((decision: any) => {
            if (typeof decision === 'string') return decision;
            if (!decision || typeof decision !== 'object') return String(decision || '').trim();
            return String(
                decision.decision
                ?? decision.choice
                ?? decision.summary
                ?? decision.rationale
                ?? decision.message
                ?? ''
            ).trim();
        })
        .filter(Boolean)
        .slice(0, 3)
        .map((item: string) => truncate(String(item), 120));

    return {
        critiqueSummary: typeof critique?.summary === 'string' ? truncate(critique.summary, 160) : '',
        issuesCount: rawIssues.length,
        issuesPreview: issueLabels,
        changelogCount: Array.isArray(revision?.changelog) ? revision?.changelog.length : 0,
        unresolvedCount: Array.isArray(revision?.unresolved) ? revision?.unresolved.length : 0,
        mergeRationale: typeof merge?.rationale === 'string' ? truncate(merge.rationale, 160) : '',
        mergeDecisionsCount: rawDecisions.length,
        decisionsPreview: decisionLabels,
    };
};

interface ProcessViewProps {
    events: RawEvent[];
    outline: string[];
    metadata?: any;
    costInfo?: any;
    reviewData?: any;
}

export function ProcessView({ events, outline, metadata, costInfo, reviewData }: ProcessViewProps) {
    const { billing } = useBillingStore();
    const normalizedEvents = useMemo(() => (events || []).map(normalizeEvent).filter((ev) => ev.type), [events]);

    const lastPhase = useMemo(() => {
        for (let i = normalizedEvents.length - 1; i >= 0; i -= 1) {
            const phase = normalizedEvents[i].phase;
            if (phase) return phase;
        }
        return null;
    }, [normalizedEvents]);

    const phaseStatus = useMemo(() => {
        const done = new Set<string>();
        const hasType = (type: string) => normalizedEvents.some((ev) => ev.type === type);
        if (hasType('outline_generated')) done.add('outline');
        if (hasType('research_done')) done.add('research');
        if (hasType('audit_result')) done.add('audit');
        if (hasType('stylecheck_result') || hasType('documentgate_result')) done.add('quality');
        if (hasType('workflow_end')) done.add('final');

        const totalSections = outline?.length || 0;
        const completedSections = new Set(
            normalizedEvents
                .filter((ev) => ev.type === 'section_completed' && ev.section)
                .map((ev) => ev.section),
        );
        if (totalSections > 0 && completedSections.size >= totalSections) {
            done.add('debate');
        }
        return done;
    }, [normalizedEvents, outline]);

    const progress = useMemo(() => {
        const latest = pickLatest(normalizedEvents, (ev) => ev.type === 'progress');
        const totalFromProgress = latest?.data?.total;
        const currentFromProgress = latest?.data?.current;
        const total = Number(totalFromProgress || outline?.length || 0);
        const completed = new Set(
            normalizedEvents
                .filter((ev) => ev.type === 'section_completed' && ev.section)
                .map((ev) => ev.section),
        );
        const current = Number(currentFromProgress || completed.size || 0);
        return { current, total };
    }, [normalizedEvents, outline]);

    const summaryLabel = useMemo(() => {
        if (progress.total > 0) {
            return `Debate ${progress.current}/${progress.total} secoes`;
        }
        return lastPhase ? `Fase: ${lastPhase}` : 'Processando...';
    }, [progress, lastPhase]);

    const sections = useMemo<SectionCardItem[]>(() => {
        const map = new Map<string, SectionCardItem>();
        const outlineList = Array.isArray(outline) ? outline : [];
        outlineList.forEach((title) => {
            map.set(title, {
                title,
                status: 'pending',
                agentPreviews: [],
            });
        });
        const getEntry = (title: string): SectionCardItem => {
            return map.get(title) || {
                title,
                status: 'pending',
                agentPreviews: [],
            };
        };

        const processedSections = metadata?.processed_sections || [];
        if (Array.isArray(processedSections)) {
            processedSections.forEach((sec: any) => {
                const title = sec?.section_title || sec?.section || sec?.title;
                if (!title) return;
                const entry = getEntry(title);
                entry.status = 'done';
                entry.hasDivergence = Boolean(sec?.has_significant_divergence || sec?.divergence_details);
                entry.qualityScore = sec?.quality_score;
                entry.mergedPreview = truncate(sec?.merged_content || '');
                entry.review = normalizeReview(sec?.review);
                map.set(title, entry);
            });
        }

        normalizedEvents.forEach((ev) => {
            if (!ev.section) return;
            const entry = getEntry(ev.section);
            if (ev.type === 'section_start') entry.status = 'generating';
            if (ev.type === 'section_stage') {
                entry.status = 'generating';
                entry.stage = ev.data?.stage || entry.stage;
            }
            if (ev.type === 'section_completed') {
                entry.status = 'done';
                entry.hasDivergence = Boolean(
                    ev.data?.hassignificantdivergence
                    ?? ev.data?.has_divergence
                    ?? ev.data?.has_significant_divergence
                );
                entry.qualityScore = ev.data?.qualityscore ?? entry.qualityScore;
                if (ev.data?.review) {
                    entry.review = normalizeReview(ev.data.review);
                }
            }
            if (ev.type === 'section_error') entry.status = 'error';
            if (ev.type === 'agent_output' && ev.data?.preview) {
                const label = ev.agent || 'Agente';
                entry.agentPreviews = [
                    { label, preview: ev.data.preview },
                    ...(entry.agentPreviews || []),
                ].slice(0, 3);
            }
            if (ev.type === 'section_completed' && ev.data?.merged_preview) {
                entry.mergedPreview = truncate(ev.data.merged_preview);
            }
            map.set(ev.section, entry);
        });

        const ordered = outlineList.length
            ? outlineList.map((title) => map.get(title)).filter(Boolean) as SectionCardItem[]
            : Array.from(map.values());
        return ordered;
    }, [normalizedEvents, outline, metadata]);

    const timelineGroups = useMemo<TimelineGroup[]>(() => {
        const items = normalizedEvents.filter((ev) => ev.type !== 'progress');
        const grouped = new Map<string, NormalizedEvent[]>();
        items.forEach((ev) => {
            const key = ev.section || 'Geral';
            const current = grouped.get(key) || [];
            current.push(ev);
            grouped.set(key, current);
        });

        const outlineOrder = Array.isArray(outline) ? outline : [];
        const orderedKeys = [
            ...(grouped.has('Geral') ? ['Geral'] : []),
            ...outlineOrder.filter((title) => grouped.has(title)),
            ...Array.from(grouped.keys()).filter((key) => key !== 'Geral' && !outlineOrder.includes(key)),
        ];

        return orderedKeys.map((key) => ({
            title: key,
            events: grouped.get(key) || [],
        }));
    }, [normalizedEvents, outline]);

    const researchPanelData = useMemo<ResearchPanelData>(() => {
        const planner = pickLatest(normalizedEvents, (ev) => ev.type === 'planner_decision');
        const researchDone = normalizedEvents.filter((ev) => ev.type === 'research_done');
        const deepSteps = normalizedEvents.filter((ev) => ev.type === 'deepresearch_step');

        const ragBySection = new Map<string, any>();
        normalizedEvents.forEach((ev) => {
            if (!ev.section) return;
            if (ev.type === 'rag_routing') {
                ragBySection.set(ev.section, {
                    ...(ragBySection.get(ev.section) || {}),
                    routing: ev.data,
                });
            }
            if (ev.type === 'rag_gate') {
                ragBySection.set(ev.section, {
                    ...(ragBySection.get(ev.section) || {}),
                    gate: ev.data,
                });
            }
        });

        return {
            planner: planner?.data || null,
            research: {
                latest: researchDone.slice(-2),
                steps: deepSteps.slice(-6).map((ev) => ev.data?.step || ''),
            },
            ragDecisions: Array.from(ragBySection.entries()).map(([section, data]) => ({
                section,
                routing: data.routing,
                gate: data.gate,
            })),
        };
    }, [normalizedEvents]);

    const totalTokensRaw = costInfo?.total_tokens;
    const pointsTotalRaw = costInfo?.points_total;
    const totalTokens = Number.isFinite(Number(totalTokensRaw)) ? Number(totalTokensRaw) : null;
    const pointsTotal = Number.isFinite(Number(pointsTotalRaw)) ? Number(pointsTotalRaw) : null;
    const usdPerPoint = useMemo(() => {
        const raw = billing?.points_anchor?.usd_per_point;
        const parsed = typeof raw === 'number' ? raw : Number(raw);
        return Number.isFinite(parsed) ? parsed : 0.00003;
    }, [billing]);
    const totalCost = useMemo(() => {
        const rawCost = costInfo?.total_cost;
        const parsedCost = typeof rawCost === 'number' ? rawCost : Number(rawCost);
        if (Number.isFinite(parsedCost)) return parsedCost;
        if (pointsTotal != null) return pointsTotal * usdPerPoint;
        return 0;
    }, [costInfo, pointsTotal, usdPerPoint]);

    return (
        <div className="space-y-4">
            <div className="rounded-2xl border border-outline/20 bg-muted/10 px-4 py-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold uppercase text-muted-foreground">Pipeline</span>
                        {reviewData && (
                            <Badge variant="secondary" className="text-[10px]">HIL pendente</Badge>
                        )}
                    </div>
                    <div className="text-xs text-muted-foreground">{summaryLabel}</div>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-6">
                    {PHASES.map((phase) => {
                        const isDone = phaseStatus.has(phase.id);
                        const isActive = !isDone && lastPhase === phase.id;
                        return (
                            <div key={phase.id} className="flex flex-col gap-1">
                                <span className="text-[10px] uppercase text-muted-foreground">{phase.label}</span>
                                <div className={`h-1.5 rounded-full ${isDone ? 'bg-emerald-400' : isActive ? 'bg-blue-400' : 'bg-muted'}`} />
                            </div>
                        );
                    })}
                </div>
                <div className="mt-3 flex flex-wrap gap-3 text-[11px] text-muted-foreground">
                    <span>Tempo: {metadata?.latency?.toFixed?.(1) || '-'}s</span>
                    {totalTokens != null && <span>Tokens: {totalTokens}</span>}
                    {pointsTotal != null && <span>Pontos: {pointsTotal}</span>}
                    <span>Custo: ${totalCost.toFixed(4)}</span>
                </div>
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(220px,1fr)_minmax(320px,2fr)_minmax(240px,1fr)]">
                <ProcessTimeline groups={timelineGroups} />
                <SectionCards sections={sections} />
                <ResearchPanel data={researchPanelData} />
            </div>
        </div>
    );
}
