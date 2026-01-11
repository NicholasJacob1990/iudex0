import { useMemo, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ChevronDown, ChevronRight, ShieldCheck, Wrench, FileText, Puzzle } from 'lucide-react';
import { cn } from '@/lib/utils';

type QualityEvent =
  | { type: 'quality_gate_done'; passed?: boolean; force_hil?: boolean; results_count?: number; results?: any[] }
  | { type: 'structural_fix_done'; result?: any }
  | { type: 'targeted_patch_done'; used?: boolean; patch_result?: any; patches_applied?: any[] }
  | { type: 'quality_report_done'; report?: any; markdown_preview?: string };

interface JobQualityPipelinePanelProps {
  isVisible: boolean;
  events: any[];
}

function lastOfType<T extends QualityEvent['type']>(events: any[], type: T): Extract<QualityEvent, { type: T }> | null {
  for (let i = (events?.length || 0) - 1; i >= 0; i--) {
    const e = events[i];
    if (e?.type === type) return e as any;
  }
  return null;
}

export function JobQualityPipelinePanel({ isVisible, events }: JobQualityPipelinePanelProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  const snapshot = useMemo(() => {
    const gate = lastOfType(events, 'quality_gate_done');
    const fix = lastOfType(events, 'structural_fix_done');
    const patch = lastOfType(events, 'targeted_patch_done');
    const report = lastOfType(events, 'quality_report_done');
    return { gate, fix, patch, report };
  }, [events]);

  const hasAny = !!(snapshot.gate || snapshot.fix || snapshot.patch || snapshot.report);
  if (!isVisible || !hasAny) return null;

  const gatePassed = snapshot.gate?.passed;
  const gateForceHil = snapshot.gate?.force_hil;
  const patchesApplied = snapshot.patch?.patch_result?.patches_applied ?? (snapshot.patch?.patches_applied?.length || 0);
  const duplicatesRemoved = snapshot.fix?.result?.duplicates_removed ?? 0;

  return (
    <Card className="my-3 border-emerald-500/25 bg-emerald-500/5 overflow-hidden">
      <div
        className="flex items-center justify-between p-3 cursor-pointer hover:bg-white/5 transition-colors"
        onClick={() => setIsExpanded((v) => !v)}
      >
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-emerald-400" />
          <span className="text-sm font-medium text-emerald-100">Quality Pipeline (v2.25)</span>

          <div className="ml-2 flex flex-wrap gap-1">
            <Badge
              variant="outline"
              className={cn(
                'text-[10px]',
                gatePassed === false ? 'border-red-500/30 text-red-200' : 'border-emerald-500/30 text-emerald-200'
              )}
            >
              Gate: {gatePassed === false ? 'falhou' : gatePassed === true ? 'passou' : '—'}
            </Badge>
            <Badge
              variant="outline"
              className={cn(
                'text-[10px]',
                gateForceHil ? 'border-amber-500/30 text-amber-200' : 'border-emerald-500/30 text-emerald-200'
              )}
            >
              HIL: {gateForceHil ? 'forçado' : '—'}
            </Badge>
            <Badge variant="outline" className="border-emerald-500/30 text-[10px] text-emerald-200">
              Dups remov.: {duplicatesRemoved}
            </Badge>
            <Badge variant="outline" className="border-emerald-500/30 text-[10px] text-emerald-200">
              Patches: {patchesApplied}
            </Badge>
          </div>
        </div>

        {isExpanded ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        )}
      </div>

      {isExpanded && (
        <div className="border-t border-emerald-500/10 bg-black/20">
          <ScrollArea className="h-[240px] w-full p-3">
            <div className="space-y-3">
              {snapshot.gate && (
                <div className="rounded-lg border border-emerald-500/15 bg-white/5 p-3">
                  <div className="flex items-center gap-2 text-sm font-semibold text-emerald-50">
                    <Puzzle className="h-4 w-4" /> Quality Gate
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    Resultados: {snapshot.gate.results_count ?? snapshot.gate.results?.length ?? 0} (mostrando até 10)
                  </div>
                  {Array.isArray(snapshot.gate.results) && snapshot.gate.results.length > 0 && (
                    <div className="mt-2 space-y-2">
                      {snapshot.gate.results.slice(0, 10).map((r, idx) => (
                        <div key={idx} className="rounded-md border border-emerald-500/15 bg-black/20 p-2">
                          <div className="text-xs text-emerald-50">{r?.section || `Seção ${idx + 1}`}</div>
                          <div className="mt-1 text-[11px] text-muted-foreground">
                            passed={String(r?.passed ?? '—')} ratio={String(r?.compression_ratio ?? '—')}
                            {Array.isArray(r?.missing_references) && r.missing_references.length > 0
                              ? ` missing_refs=${r.missing_references.length}`
                              : ''}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {snapshot.fix && (
                <div className="rounded-lg border border-emerald-500/15 bg-white/5 p-3">
                  <div className="flex items-center gap-2 text-sm font-semibold text-emerald-50">
                    <Wrench className="h-4 w-4" /> Structural Fix
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                    <div>duplicados: {snapshot.fix.result?.duplicates_removed ?? 0}</div>
                    <div>headings: {snapshot.fix.result?.headings_normalized ?? 0}</div>
                    <div>artefatos: {snapshot.fix.result?.artifacts_cleaned ?? 0}</div>
                    <div>renumerou: {String(snapshot.fix.result?.sections_renumbered ?? false)}</div>
                  </div>
                </div>
              )}

              {snapshot.patch && (
                <div className="rounded-lg border border-emerald-500/15 bg-white/5 p-3">
                  <div className="flex items-center gap-2 text-sm font-semibold text-emerald-50">
                    <Wrench className="h-4 w-4" /> Targeted Patch
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    usado={String(snapshot.patch.used ?? false)} gerados={snapshot.patch.patch_result?.patches_generated ?? 0}{' '}
                    aplicados={snapshot.patch.patch_result?.patches_applied ?? 0}
                  </div>
                  {Array.isArray(snapshot.patch.patches_applied) && snapshot.patch.patches_applied.length > 0 && (
                    <div className="mt-2 space-y-2">
                      {snapshot.patch.patches_applied.slice(0, 10).map((p, idx) => (
                        <div key={idx} className="rounded-md border border-emerald-500/15 bg-black/20 p-2">
                          <div className="text-xs text-emerald-50">
                            {p?.status || '—'} · {p?.position || '—'}
                          </div>
                          {p?.reason && <div className="mt-1 text-[11px] text-muted-foreground">{String(p.reason)}</div>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {snapshot.report && (
                <div className="rounded-lg border border-emerald-500/15 bg-white/5 p-3">
                  <div className="flex items-center gap-2 text-sm font-semibold text-emerald-50">
                    <FileText className="h-4 w-4" /> Relatório
                  </div>
                  <div className="mt-2 text-xs text-muted-foreground">
                    seções={snapshot.report.report?.total_sections ?? '—'} palavras={snapshot.report.report?.total_words ?? '—'}{' '}
                    audit={snapshot.report.report?.audit_status ?? '—'} hil={String(snapshot.report.report?.hil_required ?? false)}
                  </div>
                  {snapshot.report.markdown_preview ? (
                    <pre className="mt-2 whitespace-pre-wrap text-[11px] text-emerald-100/90 bg-black/20 p-2 rounded border border-emerald-500/15">
                      {snapshot.report.markdown_preview}
                    </pre>
                  ) : null}
                </div>
              )}
            </div>
          </ScrollArea>
        </div>
      )}
    </Card>
  );
}

