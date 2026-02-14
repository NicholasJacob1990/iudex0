import { Badge } from '@/components/ui/badge';
import { Bot, CheckCircle2, Loader2, AlertTriangle, XCircle } from 'lucide-react';

export interface SectionCardItem {
    title: string;
    status: 'pending' | 'generating' | 'done' | 'review' | 'error';
    stage?: string;
    qualityScore?: number | null;
    hasDivergence?: boolean;
    mergedPreview?: string;
    review?: {
        critiqueSummary?: string;
        issuesCount?: number;
        issuesPreview?: string[];
        changelogCount?: number;
        unresolvedCount?: number;
        mergeRationale?: string;
        mergeDecisionsCount?: number;
        decisionsPreview?: string[];
    };
    agentPreviews: Array<{ label: string; preview: string }>;
}

const statusMeta = (status: SectionCardItem['status']) => {
    switch (status) {
        case 'done':
            return { icon: CheckCircle2, label: 'Concluida', className: 'text-emerald-600' };
        case 'generating':
            return { icon: Loader2, label: 'Gerando', className: 'text-blue-600 animate-spin' };
        case 'error':
            return { icon: XCircle, label: 'Erro', className: 'text-rose-600' };
        case 'review':
            return { icon: AlertTriangle, label: 'Revisao', className: 'text-amber-600' };
        default:
            return { icon: Bot, label: 'Pendente', className: 'text-muted-foreground' };
    }
};

const stageMeta = (stage?: string) => {
    if (!stage) return null;
    const normalized = stage.toLowerCase();
    switch (normalized) {
        case 'draft':
            return { label: 'Rascunho', className: 'border-sky-200 text-sky-700' };
        case 'critique':
            return { label: 'Critica', className: 'border-amber-200 text-amber-700' };
        case 'revise':
            return { label: 'Revisao', className: 'border-violet-200 text-violet-700' };
        case 'merge':
            return { label: 'Consolidacao', className: 'border-emerald-200 text-emerald-700' };
        case 'done':
            return { label: 'Concluida', className: 'border-emerald-200 text-emerald-700' };
        default:
            return { label: stage, className: 'border-outline/30 text-muted-foreground' };
    }
};

export function SectionCards({ sections }: { sections: SectionCardItem[] }) {
    if (!sections.length) {
        return (
            <div className="rounded-2xl border border-black/[0.06] bg-white/80 p-4 text-xs text-muted-foreground backdrop-blur-sm dark:border-white/[0.06] dark:bg-white/[0.04]">
                Nenhuma secao processada ainda.
            </div>
        );
    }

    return (
        <div className="space-y-3">
            {sections.map((section) => {
                const status = statusMeta(section.status);
                const stage = stageMeta(section.stage);
                const Icon = status.icon;
                const review = section.review;
                const hasReview = Boolean(
                    (review?.issuesCount || 0) > 0
                    || (review?.changelogCount || 0) > 0
                    || (review?.unresolvedCount || 0) > 0
                    || (review?.mergeDecisionsCount || 0) > 0
                    || (review?.issuesPreview && review.issuesPreview.length > 0)
                    || (review?.decisionsPreview && review.decisionsPreview.length > 0)
                    || (review?.critiqueSummary || '')
                    || (review?.mergeRationale || '')
                );
                return (
                    <div key={section.title} className="rounded-2xl border border-black/[0.06] bg-white/80 p-4 shadow-sm backdrop-blur-sm dark:border-white/[0.06] dark:bg-white/[0.04]">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="text-sm font-semibold text-foreground/90">{section.title}</div>
                            <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                                <Icon className={`h-3.5 w-3.5 ${status.className}`} />
                                <span>{status.label}</span>
                                {stage && (
                                    <Badge variant="outline" className={`text-[10px] ${stage.className}`}>
                                        {stage.label}
                                    </Badge>
                                )}
                                {typeof section.qualityScore === 'number' && (
                                    <Badge variant="secondary" className="text-[10px]">
                                        Nota {section.qualityScore.toFixed(1)}
                                    </Badge>
                                )}
                                {section.hasDivergence && (
                                    <Badge variant="destructive" className="text-[10px]">Divergencia</Badge>
                                )}
                            </div>
                        </div>

                        {section.mergedPreview && (
                            <p className="mt-3 text-[11px] text-muted-foreground whitespace-pre-wrap">
                                {section.mergedPreview}
                            </p>
                        )}

                        {hasReview && (
                            <div className="mt-3 rounded-xl border border-outline/10 bg-muted/20 p-2 text-[11px] text-muted-foreground">
                                <div className="flex flex-wrap gap-2 text-[10px]">
                                    {typeof review?.issuesCount === 'number' && (
                                        <span>Critica: {review.issuesCount}</span>
                                    )}
                                    {typeof review?.changelogCount === 'number' && (
                                        <span>Revisao: {review.changelogCount}</span>
                                    )}
                                    {typeof review?.unresolvedCount === 'number' && review.unresolvedCount > 0 && (
                                        <span>Pendentes: {review.unresolvedCount}</span>
                                    )}
                                    {typeof review?.mergeDecisionsCount === 'number' && (
                                        <span>Merge: {review.mergeDecisionsCount}</span>
                                    )}
                                </div>
                                {review?.critiqueSummary && (
                                    <div className="mt-2">
                                        <span className="font-semibold text-foreground/80">Resumo critica:</span> {review.critiqueSummary}
                                    </div>
                                )}
                                {review?.mergeRationale && (
                                    <div className="mt-2">
                                        <span className="font-semibold text-foreground/80">Racional merge:</span> {review.mergeRationale}
                                    </div>
                                )}
                                {Array.isArray(review?.issuesPreview) && review.issuesPreview.length > 0 && (
                                    <div className="mt-2">
                                        <div className="font-semibold text-foreground/80">Principais issues:</div>
                                        <ul className="mt-1 list-disc space-y-1 pl-4">
                                            {review.issuesPreview.map((issue, idx) => (
                                                <li key={`issue-${idx}`}>{issue}</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                                {Array.isArray(review?.decisionsPreview) && review.decisionsPreview.length > 0 && (
                                    <div className="mt-2">
                                        <div className="font-semibold text-foreground/80">Decisoes do merge:</div>
                                        <ul className="mt-1 list-disc space-y-1 pl-4">
                                            {review.decisionsPreview.map((decision, idx) => (
                                                <li key={`decision-${idx}`}>{decision}</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                            </div>
                        )}

                        {section.agentPreviews.length > 0 && (
                            <div className="mt-3 space-y-2">
                                {section.agentPreviews.map((preview, idx) => (
                                    <div key={`${preview.label}-${idx}`} className="rounded-lg border border-outline/10 bg-muted/10 p-2 text-[11px]">
                                        <div className="font-semibold text-foreground/80">{preview.label}</div>
                                        <div className="text-muted-foreground">{preview.preview}</div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
}
