"use client";

import { useMemo } from "react";
import { Badge } from "@/components/ui/badge";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Puzzle, ShieldCheck, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

type QualityGateEvent = {
    type: "quality_gate_done";
    passed?: boolean;
    force_hil?: boolean;
    results_count?: number;
    results?: any[];
};

const lastOfType = (events: any[], type: QualityGateEvent["type"]): QualityGateEvent | null => {
    for (let i = (events?.length || 0) - 1; i >= 0; i--) {
        const e = events[i];
        if (e?.type === type) return e as QualityGateEvent;
    }
    return null;
};

const formatRatio = (value: any) => {
    const n = typeof value === "number" ? value : Number(value);
    if (!Number.isFinite(n)) return "—";
    return n.toFixed(2);
};

export function QualityGatePanel({ events }: { events: any[] }) {
    const gate = useMemo(() => lastOfType(events, "quality_gate_done"), [events]);
    if (!gate) return null;

    const passed = gate.passed;
    const results = Array.isArray(gate.results) ? gate.results : [];
    const first = results[0] || {};
    const missing = Array.isArray(first?.missing_references) ? first.missing_references : [];
    const compressionRatio = first?.compression_ratio;

    const statusLabel = passed === true ? "Aprovado" : passed === false ? "Reprovado" : "Pendente";
    const statusVariant = passed === false ? "destructive" : "outline";

    return (
        <div className="space-y-3">
            <div className="flex items-center justify-between gap-3">
                <h4 className="text-sm font-bold flex items-center gap-2">
                    <Puzzle className="h-4 w-4 text-emerald-600" />
                    Quality Gate
                </h4>
                <div className="flex items-center gap-2">
                    {gate.force_hil && (
                        <Badge variant="secondary" className="text-[10px] h-5">
                            HIL Forçado
                        </Badge>
                    )}
                    <Badge
                        variant={statusVariant as any}
                        className={cn(
                            "text-[10px] h-5",
                            passed === true && "border-emerald-200 bg-emerald-50 text-emerald-700"
                        )}
                    >
                        {statusLabel}
                    </Badge>
                </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="rounded-xl border border-outline/20 bg-card p-3">
                    <div className="text-[10px] uppercase text-muted-foreground">Compressão</div>
                    <div className="text-sm font-semibold">{formatRatio(compressionRatio)}</div>
                </div>
                <div className="rounded-xl border border-outline/20 bg-card p-3">
                    <div className="text-[10px] uppercase text-muted-foreground">Refs omitidas</div>
                    <div className="text-sm font-semibold">{missing.length}</div>
                </div>
                <div className="rounded-xl border border-outline/20 bg-card p-3">
                    <div className="text-[10px] uppercase text-muted-foreground">Checks</div>
                    <div className="text-sm font-semibold">{gate.results_count ?? results.length}</div>
                </div>
            </div>

            {(missing.length > 0 || results.length > 0) && (
                <Accordion type="single" collapsible defaultValue="details" className="w-full">
                    <AccordionItem value="details" className="border rounded-xl px-0 overflow-hidden bg-card">
                        <AccordionTrigger className="px-3 py-2 hover:bg-muted/50 hover:no-underline font-medium text-xs">
                            <div className="flex items-center gap-2">
                                {missing.length > 0 ? (
                                    <AlertTriangle className="h-4 w-4 text-amber-600" />
                                ) : (
                                    <ShieldCheck className="h-4 w-4 text-emerald-600" />
                                )}
                                <span>Detalhes</span>
                            </div>
                        </AccordionTrigger>
                        <AccordionContent className="px-3 pb-3 pt-1 border-t border-border/40 bg-muted/10">
                            {missing.length > 0 && (
                                <div className="mt-2 space-y-2">
                                    <div className="text-xs font-semibold text-foreground">Referências possivelmente omitidas</div>
                                    <div className="flex flex-wrap gap-2">
                                        {missing.slice(0, 12).map((ref: string, idx: number) => (
                                            <Badge key={`${ref}-${idx}`} variant="outline" className="text-[10px] bg-white">
                                                {String(ref)}
                                            </Badge>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {results.length > 0 && (
                                <div className="mt-3 space-y-2">
                                    <div className="text-xs font-semibold text-foreground">Checks (snapshot)</div>
                                    <div className="space-y-2">
                                        {results.slice(0, 6).map((r: any, idx: number) => (
                                            <div key={idx} className="p-2 rounded-lg bg-background border text-xs flex items-start justify-between gap-3">
                                                <div>
                                                    <div className="font-medium">{r?.section || `Seção ${idx + 1}`}</div>
                                                    <div className="text-[10px] text-muted-foreground">
                                                        Compressão: {formatRatio(r?.compression_ratio)}
                                                    </div>
                                                </div>
                                                <Badge
                                                    variant={r?.passed === false ? "destructive" : "outline"}
                                                    className={cn(
                                                        "text-[10px] h-5",
                                                        r?.passed === true && "border-emerald-200 bg-emerald-50 text-emerald-700"
                                                    )}
                                                >
                                                    {r?.passed === false ? "Falhou" : r?.passed === true ? "OK" : "—"}
                                                </Badge>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </AccordionContent>
                    </AccordionItem>
                </Accordion>
            )}
        </div>
    );
}
