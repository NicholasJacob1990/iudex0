import { useMemo, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ShieldCheck, Wrench, FileText, Puzzle, CheckCircle2, ChevronDown, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
    Accordion,
    AccordionContent,
    AccordionItem,
    AccordionTrigger,
} from "@/components/ui/accordion";

type QualityEvent =
    | { type: 'quality_gate_done'; passed?: boolean; force_hil?: boolean; results_count?: number; results?: any[] }
    | { type: 'structural_fix_done'; result?: any }
    | { type: 'targeted_patch_done'; used?: boolean; patch_result?: any; patches_applied?: any[] }
    | { type: 'quality_report_done'; report?: any; markdown_preview?: string };

interface JobQualityPipelinePanelProps {
    events: any[];
}

function lastOfType<T extends QualityEvent['type']>(events: any[], type: T): Extract<QualityEvent, { type: T }> | null {
    for (let i = (events?.length || 0) - 1; i >= 0; i--) {
        const e = events[i];
        if (e?.type === type) return e as any;
    }
    return null;
}

export function JobQualityPipelinePanel({ events }: JobQualityPipelinePanelProps) {
    const snapshot = useMemo(() => {
        const gate = lastOfType(events, 'quality_gate_done');
        const fix = lastOfType(events, 'structural_fix_done');
        const patch = lastOfType(events, 'targeted_patch_done');
        const report = lastOfType(events, 'quality_report_done');
        return { gate, fix, patch, report };
    }, [events]);

    const hasAny = !!(snapshot.gate || snapshot.fix || snapshot.patch || snapshot.report);
    if (!hasAny) return null;

    const gatePassed = snapshot.gate?.passed;

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-border/40">
                <h3 className="text-sm font-bold flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-emerald-600" />
                    Quality Pipeline
                </h3>
                <Badge variant={gatePassed === false ? "destructive" : "outline"} className={cn("text-[10px]", gatePassed && "border-emerald-200 bg-emerald-50 text-emerald-700")}>
                    Gate: {gatePassed === false ? 'Reprovado' : gatePassed === true ? 'Aprovado' : 'Pendente'}
                </Badge>
            </div>

            <Accordion type="multiple" defaultValue={['gate', 'report']} className="w-full space-y-3">
                {/* Quality Gate */}
                {snapshot.gate && (
                    <AccordionItem value="gate" className="border rounded-xl px-0 overflow-hidden bg-card">
                        <AccordionTrigger className="px-3 py-2 hover:bg-muted/50 hover:no-underline font-medium text-xs">
                            <div className="flex items-center gap-2">
                                <Puzzle className="h-4 w-4 text-slate-500" />
                                <span>Quality Gate Checks</span>
                            </div>
                            {snapshot.gate.force_hil && (
                                <Badge variant="secondary" className="ml-2 text-[10px] h-5">HIL Forçado</Badge>
                            )}
                        </AccordionTrigger>
                        <AccordionContent className="px-3 pb-3 pt-1 border-t border-border/40 bg-muted/10">
                            <div className="space-y-2 mt-2">
                                {Array.isArray(snapshot.gate.results) && snapshot.gate.results.slice(0, 10).map((r, idx) => (
                                    <div key={idx} className="flex items-start justify-between gap-3 text-xs p-2 rounded-lg bg-background border shadow-sm">
                                        <div>
                                            <span className="font-semibold block mb-0.5">{r?.section || `Seção ${idx + 1}`}</span>
                                            <div className="text-muted-foreground text-[10px]">
                                                Taxa comp.: {r?.compression_ratio ? Number(r.compression_ratio).toFixed(2) : '—'}
                                            </div>
                                        </div>
                                        <div className="text-right">
                                            {r?.passed ? (
                                                <span className="inline-flex items-center text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded text-[10px] font-medium border border-emerald-100">
                                                    Passou
                                                </span>
                                            ) : (
                                                <span className="inline-flex items-center text-red-600 bg-red-50 px-1.5 py-0.5 rounded text-[10px] font-medium border border-red-100">
                                                    Falhou
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                ))}
                                {(!snapshot.gate.results || snapshot.gate.results.length === 0) && (
                                    <p className="text-xs text-muted-foreground p-2">Nenhum resultado detalhado.</p>
                                )}
                            </div>
                        </AccordionContent>
                    </AccordionItem>
                )}

                {/* Structural Fix */}
                {snapshot.fix && (
                    <AccordionItem value="fix" className="border rounded-xl px-0 overflow-hidden bg-card">
                        <AccordionTrigger className="px-3 py-2 hover:bg-muted/50 hover:no-underline font-medium text-xs">
                            <div className="flex items-center gap-2">
                                <Wrench className="h-4 w-4 text-slate-500" />
                                <span>Correções Estruturais</span>
                            </div>
                        </AccordionTrigger>
                        <AccordionContent className="px-3 pb-3 pt-1 border-t border-border/40 bg-muted/10">
                            <div className="grid grid-cols-2 gap-2 mt-2">
                                <div className="p-2 rounded bg-background border flex flex-col items-center justify-center text-center">
                                    <span className="text-lg font-bold text-slate-700">{snapshot.fix.result?.duplicates_removed ?? 0}</span>
                                    <span className="text-[10px] text-muted-foreground uppercase">Duplicados</span>
                                </div>
                                <div className="p-2 rounded bg-background border flex flex-col items-center justify-center text-center">
                                    <span className="text-lg font-bold text-slate-700">{snapshot.fix.result?.headings_normalized ?? 0}</span>
                                    <span className="text-[10px] text-muted-foreground uppercase">Headings</span>
                                </div>
                                <div className="p-2 rounded bg-background border flex flex-col items-center justify-center text-center">
                                    <span className="text-lg font-bold text-slate-700">{snapshot.fix.result?.artifacts_cleaned ?? 0}</span>
                                    <span className="text-[10px] text-muted-foreground uppercase">Artefatos</span>
                                </div>
                                <div className="p-2 rounded bg-background border flex flex-col items-center justify-center text-center">
                                    <span className="text-lg font-bold text-slate-700">{snapshot.fix.result?.sections_renumbered ? 'Sim' : 'Não'}</span>
                                    <span className="text-[10px] text-muted-foreground uppercase">Renumeração</span>
                                </div>
                            </div>
                        </AccordionContent>
                    </AccordionItem>
                )}

                {/* Targeted Patch */}
                {snapshot.patch && (snapshot.patch.used || (snapshot.patch.patch_result?.patches_applied ?? 0) > 0) && (
                    <AccordionItem value="patch" className="border rounded-xl px-0 overflow-hidden bg-card">
                        <AccordionTrigger className="px-3 py-2 hover:bg-muted/50 hover:no-underline font-medium text-xs">
                            <div className="flex items-center gap-2">
                                <Wrench className="h-4 w-4 text-orange-500" />
                                <span>Patches Aplicados</span>
                                <Badge variant="outline" className="ml-auto text-[10px] bg-orange-50 text-orange-700 border-orange-200">
                                    {snapshot.patch.patch_result?.patches_applied ?? 0}
                                </Badge>
                            </div>
                        </AccordionTrigger>
                        <AccordionContent className="px-3 pb-3 pt-1 border-t border-border/40 bg-muted/10">
                            <div className="space-y-2 mt-2">
                                {Array.isArray(snapshot.patch.patches_applied) && snapshot.patch.patches_applied.map((p, idx) => (
                                    <div key={idx} className="p-2 rounded bg-background border text-xs">
                                        <div className="flex justify-between items-start mb-1">
                                            <Badge variant="outline">{p?.status}</Badge>
                                            <span className="text-[10px] text-muted-foreground">{p?.position}</span>
                                        </div>
                                        {p?.reason && <p className="text-muted-foreground italic">&quot;{p.reason}&quot;</p>}
                                    </div>
                                ))}
                            </div>
                        </AccordionContent>
                    </AccordionItem>
                )}

                {/* Final Report */}
                {snapshot.report && (
                    <AccordionItem value="report" className="border rounded-xl px-0 overflow-hidden bg-card">
                        <AccordionTrigger className="px-3 py-2 hover:bg-muted/50 hover:no-underline font-medium text-xs">
                            <div className="flex items-center gap-2">
                                <FileText className="h-4 w-4 text-slate-500" />
                                <span>Relatório Final</span>
                            </div>
                        </AccordionTrigger>
                        <AccordionContent className="px-3 pb-3 pt-1 border-t border-border/40 bg-muted/10">
                            <div className="grid grid-cols-2 gap-2 mt-2 mb-3">
                                <div className="text-xs">
                                    <span className="text-muted-foreground">Total Seções:</span> <span className="font-medium">{snapshot.report.report?.total_sections ?? '—'}</span>
                                </div>
                                <div className="text-xs">
                                    <span className="text-muted-foreground">Palavras:</span> <span className="font-medium">{snapshot.report.report?.total_words ?? '—'}</span>
                                </div>
                                <div className="text-xs">
                                    <span className="text-muted-foreground">Status Audit:</span> <span className="font-medium">{snapshot.report.report?.audit_status ?? '—'}</span>
                                </div>
                            </div>
                            {snapshot.report.markdown_preview && (
                                <div className="rounded-lg border bg-background p-3 text-xs text-muted-foreground max-h-[200px] overflow-y-auto">
                                    <pre className="whitespace-pre-wrap font-mono text-[10px] leading-relaxed">
                                        {snapshot.report.markdown_preview}
                                    </pre>
                                </div>
                            )}
                        </AccordionContent>
                    </AccordionItem>
                )}
            </Accordion>
        </div>
    );
}
