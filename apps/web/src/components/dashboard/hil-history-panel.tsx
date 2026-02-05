"use client";

import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import {
    CheckCircle2,
    XCircle,
    Edit3,
    Clock,
    User,
    MessageSquare,
    FileText,
    GitCompare,
    ChevronDown,
    History,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface HilEntry {
    id: string;
    timestamp: string;
    checkpoint: string;
    section_title?: string | null;
    user_id?: string;
    user_email?: string;
    decision: "approved" | "rejected" | "edited";
    approved: boolean;
    original_content?: string | null;
    edited_content?: string | null;
    instructions?: string | null;
    proposal?: string | null;
    iteration: number;
}

interface HilHistoryPanelProps {
    metadata?: {
        hil_history?: HilEntry[];
    };
    events?: any[];
    className?: string;
}

const CHECKPOINT_LABELS: Record<string, string> = {
    outline: "Outline",
    section: "Seção",
    divergence: "Divergências",
    final: "Documento Final",
    finalize: "Finalização",
    correction: "Correções",
    style: "Estilo",
    document_gate: "Gate Documental",
};

const getCheckpointLabel = (checkpoint: string): string => {
    return CHECKPOINT_LABELS[checkpoint] || checkpoint;
};

const formatTimestamp = (ts: string): string => {
    try {
        const date = new Date(ts);
        return date.toLocaleString("pt-BR", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    } catch {
        return ts;
    }
};

const getDecisionMeta = (decision: string, approved: boolean) => {
    if (decision === "edited") {
        return {
            icon: Edit3,
            label: "Editado",
            className: "text-blue-600",
            badgeClass: "bg-blue-50 text-blue-700 border-blue-200",
        };
    }
    if (approved || decision === "approved") {
        return {
            icon: CheckCircle2,
            label: "Aprovado",
            className: "text-emerald-600",
            badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200",
        };
    }
    return {
        icon: XCircle,
        label: "Rejeitado",
        className: "text-red-600",
        badgeClass: "bg-red-50 text-red-700 border-red-200",
    };
};

function ContentDiff({ original, edited }: { original?: string | null; edited?: string | null }) {
    const [expanded, setExpanded] = useState(false);

    if (!original && !edited) return null;

    const hasOriginal = original && original.trim();
    const hasEdited = edited && edited.trim();

    return (
        <div className="space-y-2">
            <div className="flex items-center gap-2">
                <GitCompare className="h-3.5 w-3.5 text-violet-600" />
                <span className="text-xs font-semibold">Comparação de Conteúdo</span>
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setExpanded(!expanded)}
                    className="h-5 px-2 text-[10px] ml-auto"
                >
                    <ChevronDown className={cn("h-3 w-3 mr-1 transition-transform", expanded && "rotate-180")} />
                    {expanded ? "Recolher" : "Expandir"}
                </Button>
            </div>

            {expanded && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    {hasOriginal && (
                        <div className="rounded-lg border border-red-200 bg-red-50/50 p-2">
                            <div className="text-[10px] font-semibold text-red-700 mb-1 flex items-center gap-1">
                                <XCircle className="h-3 w-3" /> Original
                            </div>
                            <pre className="text-[10px] text-red-600/80 whitespace-pre-wrap font-sans max-h-40 overflow-y-auto">
                                {original}
                            </pre>
                        </div>
                    )}
                    {hasEdited && (
                        <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-2">
                            <div className="text-[10px] font-semibold text-emerald-700 mb-1 flex items-center gap-1">
                                <CheckCircle2 className="h-3 w-3" /> Editado
                            </div>
                            <pre className="text-[10px] text-emerald-600/80 whitespace-pre-wrap font-sans max-h-40 overflow-y-auto">
                                {edited}
                            </pre>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

function HilEntryCard({ entry }: { entry: HilEntry }) {
    const decision = getDecisionMeta(entry.decision, entry.approved);
    const DecisionIcon = decision.icon;

    return (
        <AccordionItem
            value={entry.id}
            className="border rounded-xl overflow-hidden bg-card"
        >
            <AccordionTrigger className="px-4 py-3 hover:bg-muted/50 hover:no-underline">
                <div className="flex items-center justify-between w-full pr-2">
                    <div className="flex items-center gap-3">
                        <div className={cn("h-8 w-8 rounded-full flex items-center justify-center", decision.badgeClass)}>
                            <DecisionIcon className={cn("h-4 w-4", decision.className)} />
                        </div>
                        <div className="text-left">
                            <div className="text-sm font-semibold">
                                {getCheckpointLabel(entry.checkpoint)}
                                {entry.section_title && (
                                    <span className="font-normal text-muted-foreground"> — {entry.section_title}</span>
                                )}
                            </div>
                            <div className="text-[10px] text-muted-foreground flex items-center gap-2">
                                <Clock className="h-3 w-3" />
                                {formatTimestamp(entry.timestamp)}
                                {entry.user_email && (
                                    <>
                                        <span>•</span>
                                        <User className="h-3 w-3" />
                                        {entry.user_email}
                                    </>
                                )}
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-[10px] h-5">
                            Round {entry.iteration}
                        </Badge>
                        <Badge variant="outline" className={cn("text-[10px] h-5", decision.badgeClass)}>
                            {decision.label}
                        </Badge>
                    </div>
                </div>
            </AccordionTrigger>
            <AccordionContent className="px-4 pb-4 pt-2 border-t border-outline/10 bg-muted/5">
                <div className="space-y-3">
                    {/* Instructions */}
                    {entry.instructions && (
                        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                            <div className="flex items-center gap-2 mb-1">
                                <MessageSquare className="h-3.5 w-3.5 text-amber-600" />
                                <span className="text-xs font-semibold text-amber-700">Instruções ao Agente</span>
                            </div>
                            <p className="text-xs text-amber-600/80 whitespace-pre-wrap">
                                {entry.instructions}
                            </p>
                        </div>
                    )}

                    {/* Proposal */}
                    {entry.proposal && (
                        <div className="rounded-lg border border-violet-200 bg-violet-50 p-3">
                            <div className="flex items-center gap-2 mb-1">
                                <FileText className="h-3.5 w-3.5 text-violet-600" />
                                <span className="text-xs font-semibold text-violet-700">Proposta do Usuário</span>
                            </div>
                            <p className="text-xs text-violet-600/80 whitespace-pre-wrap">
                                {entry.proposal}
                            </p>
                        </div>
                    )}

                    {/* Content Diff */}
                    <ContentDiff original={entry.original_content} edited={entry.edited_content} />

                    {/* No details */}
                    {!entry.instructions && !entry.proposal && !entry.original_content && !entry.edited_content && (
                        <div className="text-xs text-muted-foreground text-center py-2">
                            Aprovação direta sem edições ou instruções.
                        </div>
                    )}
                </div>
            </AccordionContent>
        </AccordionItem>
    );
}

export function HilHistoryPanel({ metadata, events, className }: HilHistoryPanelProps) {
    // Get hil_history from metadata or reconstruct from events
    const history = useMemo(() => {
        // First try metadata
        if (metadata?.hil_history && Array.isArray(metadata.hil_history) && metadata.hil_history.length > 0) {
            return metadata.hil_history;
        }

        // Fallback: reconstruct from hil_response events
        if (events && Array.isArray(events)) {
            const hilResponses = events.filter(e => e?.type === "hil_response" && e?.hil_entry);
            if (hilResponses.length > 0) {
                return hilResponses.map(e => e.hil_entry);
            }
        }

        return [];
    }, [metadata, events]);

    const stats = useMemo(() => {
        let approved = 0;
        let rejected = 0;
        let edited = 0;

        history.forEach(entry => {
            if (entry.decision === "edited") edited++;
            else if (entry.approved || entry.decision === "approved") approved++;
            else rejected++;
        });

        return { approved, rejected, edited, total: history.length };
    }, [history]);

    // Sort by timestamp descending (most recent first)
    const sortedHistory = useMemo(() => {
        if (!history.length) return [];
        return [...history].sort((a, b) => {
            const dateA = new Date(a.timestamp).getTime();
            const dateB = new Date(b.timestamp).getTime();
            return dateB - dateA;
        });
    }, [history]);

    if (!history.length) {
        return (
            <div className={cn("rounded-xl border border-outline/20 bg-card p-6 text-center", className)}>
                <History className="h-8 w-8 mx-auto mb-2 text-muted-foreground/30" />
                <p className="text-sm text-muted-foreground">
                    Nenhuma interação HIL registrada.
                </p>
                <p className="text-xs text-muted-foreground/70 mt-1">
                    As interações humanas são registradas quando o documento passa por checkpoints de revisão.
                </p>
            </div>
        );
    }

    return (
        <div className={cn("space-y-4", className)}>
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <History className="h-5 w-5 text-indigo-600" />
                    <h3 className="text-sm font-bold">Histórico de Interações HIL</h3>
                </div>
                <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-[10px] h-5">
                        {stats.total} interações
                    </Badge>
                    {stats.approved > 0 && (
                        <Badge variant="outline" className="text-[10px] h-5 border-emerald-200 bg-emerald-50 text-emerald-700">
                            {stats.approved} aprovadas
                        </Badge>
                    )}
                    {stats.edited > 0 && (
                        <Badge variant="outline" className="text-[10px] h-5 border-blue-200 bg-blue-50 text-blue-700">
                            {stats.edited} editadas
                        </Badge>
                    )}
                    {stats.rejected > 0 && (
                        <Badge variant="outline" className="text-[10px] h-5 border-red-200 bg-red-50 text-red-700">
                            {stats.rejected} rejeitadas
                        </Badge>
                    )}
                </div>
            </div>

            {/* Timeline */}
            <Accordion type="multiple" className="space-y-2">
                {sortedHistory.map(entry => (
                    <HilEntryCard key={entry.id} entry={entry} />
                ))}
            </Accordion>
        </div>
    );
}
