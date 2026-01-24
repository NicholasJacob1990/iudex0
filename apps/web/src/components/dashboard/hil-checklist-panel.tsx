"use client";

import { useMemo } from "react";
import { Badge } from "@/components/ui/badge";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { AlertTriangle, CheckCircle2, ClipboardList, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";

type HilChecklist = Record<string, any>;

type HilEvaluatedEvent = {
    type: "hil_evaluated";
    requires_hil?: boolean;
    hil_level?: string;
    triggered_factors?: string[];
    score_confianca?: number;
    evaluation_notes?: string[];
    hil_checklist?: HilChecklist;
    hil_risk_score?: number | null;
    hil_risk_level?: string | null;
};

const lastOfType = (events: any[], type: HilEvaluatedEvent["type"]): HilEvaluatedEvent | null => {
    for (let i = (events?.length || 0) - 1; i >= 0; i--) {
        const e = events[i];
        if (e?.type === type) return e as HilEvaluatedEvent;
    }
    return null;
};

const formatScore = (value: any) => {
    const n = typeof value === "number" ? value : Number(value);
    if (!Number.isFinite(n)) return "—";
    return n.toFixed(2);
};

const boolTriggered = (value: any) => Boolean(value);
const countTriggered = (value: any, min = 1) => {
    const n = typeof value === "number" ? value : Number(value);
    if (!Number.isFinite(n)) return false;
    return n >= min;
};
const scoreTriggered = (value: any, threshold = 0.7) => {
    const n = typeof value === "number" ? value : Number(value);
    if (!Number.isFinite(n)) return false;
    return n < threshold;
};

export function HilChecklistPanel({ events, metadata, className }: { events: any[]; metadata?: any; className?: string }) {
    const ev = useMemo(() => lastOfType(events, "hil_evaluated"), [events]);
    const checklist = useMemo(() => {
        const candidates = [
            ev?.hil_checklist,
            metadata?.hil_checklist,
            metadata?.quality?.hil_checklist,
            metadata?.quality_payload?.hil_checklist,
            metadata?.qualityPayload?.hil_checklist,
        ];
        for (const candidate of candidates) {
            if (candidate && typeof candidate === "object" && !Array.isArray(candidate)) {
                return candidate as HilChecklist;
            }
        }
        return null;
    }, [ev, metadata]);

    const hasAny =
        Boolean(checklist)
        || typeof ev?.requires_hil === "boolean"
        || Array.isArray(ev?.triggered_factors)
        || typeof ev?.score_confianca === "number";
    if (!hasAny) return null;

    const requiresHil =
        typeof checklist?.requires_hil === "boolean"
            ? checklist.requires_hil
            : typeof ev?.requires_hil === "boolean"
                ? ev.requires_hil
                : false;
    const score = checklist?.score_confianca ?? ev?.score_confianca;

    const rows = [
        { key: "destino_externo", label: "Destino externo", value: checklist?.destino_externo, triggered: boolTriggered(checklist?.destino_externo) },
        { key: "risco_alto", label: "Risco alto", value: checklist?.risco_alto, triggered: boolTriggered(checklist?.risco_alto) },
        { key: "novas_teses_ou_pedidos", label: "Novas teses/pedidos", value: checklist?.novas_teses_ou_pedidos, triggered: boolTriggered(checklist?.novas_teses_ou_pedidos) },
        { key: "desvio_playbook", label: "Desvio de playbook", value: checklist?.desvio_playbook, triggered: boolTriggered(checklist?.desvio_playbook) },
        { key: "num_citacoes_externas", label: "Citações externas", value: checklist?.num_citacoes_externas, triggered: countTriggered(checklist?.num_citacoes_externas) },
        { key: "num_citacoes_suspeitas", label: "Citações suspeitas", value: checklist?.num_citacoes_suspeitas, triggered: countTriggered(checklist?.num_citacoes_suspeitas) },
        { key: "num_citacoes_pendentes", label: "Citações pendentes", value: checklist?.num_citacoes_pendentes, triggered: countTriggered(checklist?.num_citacoes_pendentes) },
        { key: "contradicao_interna", label: "Contradição interna", value: checklist?.contradicao_interna, triggered: boolTriggered(checklist?.contradicao_interna) },
        { key: "fato_inventado", label: "Fato inventado", value: checklist?.fato_inventado, triggered: boolTriggered(checklist?.fato_inventado) },
        { key: "fato_relevante_ignorado", label: "Fato relevante ignorado", value: checklist?.fato_relevante_ignorado, triggered: boolTriggered(checklist?.fato_relevante_ignorado) },
        { key: "score_confianca", label: "Score de confiança", value: score, triggered: scoreTriggered(score) },
    ];

    const triggeredFactors = (Array.isArray(checklist?.triggered_factors) ? checklist.triggered_factors : ev?.triggered_factors) || [];
    const evaluationNotes = (Array.isArray(checklist?.evaluation_notes) ? checklist.evaluation_notes : ev?.evaluation_notes) || [];

    return (
        <div className={cn("space-y-3", className)}>
            <div className="flex items-center justify-between gap-3">
                <h4 className="text-sm font-bold flex items-center gap-2">
                    <ClipboardList className="h-4 w-4 text-indigo-600" />
                    HIL Checklist (10 fatores)
                </h4>
                <div className="flex items-center gap-2">
                    <Badge
                        variant={requiresHil ? "destructive" : "outline"}
                        className={cn(!requiresHil && "border-emerald-200 bg-emerald-50 text-emerald-700", "text-[10px] h-5")}
                    >
                        {requiresHil ? "HIL obrigatório" : "HIL dispensado"}
                    </Badge>
                </div>
            </div>

            <div className="rounded-xl border border-outline/20 bg-card p-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {rows.map((row) => (
                        <div key={row.key} className="flex items-center justify-between gap-3 text-xs">
                            <div className="flex items-center gap-2 min-w-0">
                                {row.triggered ? (
                                    <AlertTriangle className="h-3.5 w-3.5 text-amber-600 shrink-0" />
                                ) : (
                                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 shrink-0" />
                                )}
                                <span className="font-medium truncate">{row.label}</span>
                            </div>
                            <span className="text-muted-foreground shrink-0">
                                {typeof row.value === "boolean"
                                    ? row.value ? "Sim" : "Não"
                                    : row.key === "score_confianca"
                                        ? formatScore(row.value)
                                        : (row.value ?? "—")}
                            </span>
                        </div>
                    ))}
                </div>
            </div>

            {(triggeredFactors.length > 0 || evaluationNotes.length > 0) && (
                <Accordion type="single" collapsible className="w-full">
                    <AccordionItem value="why" className="border rounded-xl px-0 overflow-hidden bg-card">
                        <AccordionTrigger className="px-3 py-2 hover:bg-muted/50 hover:no-underline font-medium text-xs">
                            <div className="flex items-center gap-2">
                                <ShieldAlert className="h-4 w-4 text-amber-600" />
                                <span>Por que o HIL foi (ou seria) acionado</span>
                            </div>
                        </AccordionTrigger>
                        <AccordionContent className="px-3 pb-3 pt-1 border-t border-border/40 bg-muted/10">
                            {triggeredFactors.length > 0 && (
                                <div className="mt-2 space-y-2">
                                    <div className="text-xs font-semibold text-foreground">Fatores acionados</div>
                                    <ul className="list-disc pl-5 text-xs text-muted-foreground space-y-1">
                                        {triggeredFactors.slice(0, 12).map((item: any, idx: number) => (
                                            <li key={idx}>{String(item)}</li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                            {evaluationNotes.length > 0 && (
                                <div className={cn("space-y-2", triggeredFactors.length > 0 ? "mt-3" : "mt-2")}>
                                    <div className="text-xs font-semibold text-foreground">Notas</div>
                                    <ul className="list-disc pl-5 text-xs text-muted-foreground space-y-1">
                                        {evaluationNotes.slice(0, 12).map((item: any, idx: number) => (
                                            <li key={idx}>{String(item)}</li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                        </AccordionContent>
                    </AccordionItem>
                </Accordion>
            )}
        </div>
    );
}
