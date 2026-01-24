"use client";

import { useMemo } from "react";
import { AlertCircle, CheckCircle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { MarkdownPreview } from "@/components/dashboard/markdown-editor-panel";
import { buildPreventiveAuditStatus, type PreventiveAuditStatus } from "@/lib/preventive-audit";

interface PreventiveAuditPanelProps {
    audit?: any | null;
    auditMarkdown?: string | null;
    recommendation?: any | null;
    status?: PreventiveAuditStatus;
    loading?: boolean;
    error?: string | null;
    isAuditOutdated?: boolean;
    hasRawForHil?: boolean;
    hasDocument?: boolean;
    onConvertAlerts?: () => void;
    onGoToHil?: () => void;
    onDownloadReport?: (key: "preventive_fidelity_md_path" | "preventive_fidelity_json_path") => void;
    canDownloadMd?: boolean;
    canDownloadJson?: boolean;
    onRecompute?: () => void;
    canRecompute?: boolean;
    onReload?: () => void;
}

const formatCount = (value?: number | null) => {
    if (typeof value !== "number" || !Number.isFinite(value)) return "-";
    return Math.round(value).toLocaleString();
};

const formatPercent = (value?: number | null) => {
    if (typeof value !== "number" || !Number.isFinite(value)) return "-";
    return `${(value * 100).toFixed(1)}%`;
};

export function PreventiveAuditPanel({
    audit,
    auditMarkdown,
    recommendation,
    status,
    loading = false,
    error,
    isAuditOutdated = false,
    hasRawForHil = false,
    hasDocument = false,
    onConvertAlerts,
    onGoToHil,
    onDownloadReport,
    canDownloadMd = false,
    canDownloadJson = false,
    onRecompute,
    canRecompute = false,
    onReload,
}: PreventiveAuditPanelProps) {
    const effectiveRecommendation = recommendation ?? audit?.recomendacao_hil ?? null;
    const resolvedStatus = useMemo(
        () =>
            status
                ?? buildPreventiveAuditStatus({
                    audit,
                    auditMarkdown,
                    loading,
                    recommendation: effectiveRecommendation,
                }),
        [status, audit, auditMarkdown, loading, effectiveRecommendation]
    );
    const statusVariant = resolvedStatus.statusVariant as BadgeProps["variant"];
    const shouldBlock = resolvedStatus.shouldBlock;
    const shouldBlockDisplay = resolvedStatus.shouldBlockDisplay;

    const metrics = audit?.metricas ?? {};
    const sources = audit?.auditoria_fontes ?? null;
    const counts = {
        omissoes: Array.isArray(audit?.omissoes_criticas) ? audit.omissoes_criticas.length : 0,
        distorcoes: Array.isArray(audit?.distorcoes) ? audit.distorcoes.length : 0,
        alucinacoes: Array.isArray(audit?.alucinacoes) ? audit.alucinacoes.length : 0,
        estruturais: Array.isArray(audit?.problemas_estruturais) ? audit.problemas_estruturais.length : 0,
        contexto: Array.isArray(audit?.problemas_contexto) ? audit.problemas_contexto.length : 0,
        fontes_erros: Array.isArray(sources?.erros_criticos) ? sources.erros_criticos.length : 0,
        fontes_ambiguidades: Array.isArray(sources?.ambiguidades) ? sources.ambiguidades.length : 0,
    };
    const issueTotal =
        counts.omissoes + counts.distorcoes + counts.alucinacoes + counts.estruturais + counts.contexto;
    const hasAlerts = issueTotal > 0;
    const areas = Array.isArray(effectiveRecommendation?.areas_criticas)
        ? effectiveRecommendation?.areas_criticas
        : [];

    return (
        <div className="border rounded-md p-4 space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="space-y-1">
                    <div className="flex items-center gap-2 text-sm font-medium">
                        {shouldBlockDisplay ? (
                            <AlertCircle className="h-4 w-4 text-orange-600" />
                        ) : (
                            <CheckCircle className="h-4 w-4 text-emerald-600" />
                        )}
                        Auditoria preventiva de fidelidade
                        <Badge variant={statusVariant}>{resolvedStatus.statusLabel}</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                        {effectiveRecommendation?.motivo
                            ? effectiveRecommendation.motivo
                            : loading
                                ? "Carregando relatório preventivo..."
                                : audit
                                    ? shouldBlock
                                        ? "Revisão humana recomendada pela auditoria preventiva."
                                        : "Nenhum alerta crítico recomendado pela auditoria preventiva."
                                    : auditMarkdown
                                        ? "Relatório preventivo disponível (MD)."
                                        : "Relatório preventivo ainda não disponível."}
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    {canDownloadMd && onDownloadReport && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => onDownloadReport("preventive_fidelity_md_path")}
                        >
                            Baixar MD
                        </Button>
                    )}
                    {canDownloadJson && onDownloadReport && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => onDownloadReport("preventive_fidelity_json_path")}
                        >
                            Baixar JSON
                        </Button>
                    )}
                    {onRecompute && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={onRecompute}
                            disabled={!canRecompute}
                            title="Reexecuta a auditoria preventiva e atualiza os relatórios do job"
                        >
                            Regerar
                        </Button>
                    )}
                </div>
            </div>

            {audit && (
                <div className="rounded-md border border-orange-200 bg-orange-50 p-3 text-xs text-orange-900 space-y-2">
                    <div className="font-semibold flex items-center gap-2">
                        Aplicar correcoes da auditoria preventiva
                        {isAuditOutdated && (
                            <span className="text-[10px] bg-orange-200 text-orange-800 px-1.5 py-0.5 rounded font-normal">
                                Desatualizado
                            </span>
                        )}
                    </div>
                    <p className="text-xs text-orange-800">
                        {onGoToHil
                            ? "1) Converta os alertas em issues HIL. 2) Abra a Revisao HIL, selecione e clique em \"Aplicar Correcoes\"."
                            : "Converta os alertas em issues HIL para revisar os ajustes sugeridos."}
                    </p>
                    <div className="text-[11px] text-orange-700">
                        {hasAlerts
                            ? `${issueTotal} alerta(s) prontos para converter.`
                            : "Nenhum alerta preventivo para converter."}
                        {isAuditOutdated && " (Atenção: valores baseados na versão original)"}
                    </div>
                    {!hasRawForHil && (
                        <div className="text-[11px] text-orange-700">
                            RAW necessario para aplicar correcoes de conteudo.
                        </div>
                    )}
                    <div className="flex flex-wrap gap-2">
                        {onConvertAlerts && (
                            <Button
                                size="sm"
                                onClick={onConvertAlerts}
                                disabled={!hasAlerts || loading}
                            >
                                Converter alertas em issues HIL
                            </Button>
                        )}
                        {onGoToHil && (
                            <Button
                                size="sm"
                                variant="outline"
                                onClick={onGoToHil}
                                disabled={!hasDocument}
                            >
                                Abrir Revisao HIL
                            </Button>
                        )}
                    </div>
                </div>
            )}

            {loading && (
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Carregando auditoria preventiva...
                </div>
            )}

            {error && (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-xs text-destructive">
                    <span>{error}</span>
                    {onReload && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={onReload}
                            disabled={loading}
                        >
                            Recarregar
                        </Button>
                    )}
                </div>
            )}

            {auditMarkdown && !audit && (
                <div className="space-y-3">
                    <div className="text-[10px] font-semibold uppercase text-muted-foreground">
                        Relatório (MD)
                    </div>
                    <MarkdownPreview content={auditMarkdown} className="max-h-[420px]" />
                </div>
            )}

            {audit && (
                <>
                    <div className="flex flex-wrap gap-2">
                        <Badge variant="outline">Omissões críticas: {counts.omissoes}</Badge>
                        <Badge variant="outline">Distorções: {counts.distorcoes}</Badge>
                        <Badge variant="outline">Alucinações: {counts.alucinacoes}</Badge>
                        <Badge variant="outline">Estruturais: {counts.estruturais}</Badge>
                        <Badge variant="outline">Contexto: {counts.contexto}</Badge>
                        {sources && (
                            <Badge variant="outline">Autoria (fontes): {counts.fontes_erros} erro(s)</Badge>
                        )}
                    </div>

                    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                        <div className="border rounded-md p-3 space-y-2">
                            <div className="text-[10px] font-semibold uppercase text-muted-foreground">
                                Métricas
                            </div>
                            <div className="space-y-1 text-sm text-muted-foreground">
                                <div>
                                    <span className="text-foreground">Palavras RAW:</span>{" "}
                                    {formatCount(metrics.palavras_raw)}
                                </div>
                                <div>
                                    <span className="text-foreground">Palavras formatado:</span>{" "}
                                    {formatCount(metrics.palavras_formatado)}
                                </div>
                                <div>
                                    <span className="text-foreground">Taxa de retenção:</span>{" "}
                                    {formatPercent(metrics.taxa_retencao)}
                                </div>
                                <div>
                                    <span className="text-foreground">Dispositivos legais RAW:</span>{" "}
                                    {formatCount(metrics.dispositivos_legais_raw)}
                                </div>
                                <div>
                                    <span className="text-foreground">Dispositivos legais formatado:</span>{" "}
                                    {formatCount(metrics.dispositivos_legais_formatado)}
                                </div>
                                <div>
                                    <span className="text-foreground">Preservação de dispositivos:</span>{" "}
                                    {formatPercent(metrics.taxa_preservacao_dispositivos)}
                                </div>
                            </div>
                        </div>

                        <div className="border rounded-md p-3 space-y-2">
                            <div className="text-[10px] font-semibold uppercase text-muted-foreground">
                                Recomendação HIL
                            </div>
                            <div className="space-y-2 text-sm text-muted-foreground">
                                <div>
                                    <span className="text-foreground">Pausar para revisão:</span>{" "}
                                    {shouldBlock ? "Sim" : "Não"}
                                </div>
                                {areas.length > 0 ? (
                                    <ul className="list-disc space-y-1 pl-4 text-xs">
                                        {areas.map((area: string, idx: number) => (
                                            <li key={`${area}-${idx}`}>{area}</li>
                                        ))}
                                    </ul>
                                ) : (
                                    <div className="text-xs text-muted-foreground">
                                        Nenhuma área crítica apontada.
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    {sources && (
                        <div className="border rounded-md p-3 space-y-2">
                            <div className="text-[10px] font-semibold uppercase text-muted-foreground">
                                Auditoria de fontes (integrada)
                            </div>
                            <div className="space-y-1 text-sm text-muted-foreground">
                                <div>
                                    <span className="text-foreground">Status:</span>{" "}
                                    {sources?.aprovado ? "Aprovado" : "Revisão recomendada"}
                                </div>
                                <div>
                                    <span className="text-foreground">Nota:</span>{" "}
                                    {typeof sources?.nota_consistencia === "number"
                                        ? `${sources.nota_consistencia}/10`
                                        : "—"}
                                </div>
                                <div>
                                    <span className="text-foreground">Erros críticos:</span>{" "}
                                    {counts.fontes_erros}
                                </div>
                                <div>
                                    <span className="text-foreground">Ambiguidades:</span>{" "}
                                    {counts.fontes_ambiguidades}
                                </div>
                            </div>
                        </div>
                    )}

                    {audit?.observacoes_gerais && (
                        <div className="border rounded-md p-3">
                            <div className="text-[10px] font-semibold uppercase text-muted-foreground mb-2">
                                Observações gerais
                            </div>
                            <div className="text-sm text-muted-foreground whitespace-pre-wrap">
                                {audit.observacoes_gerais}
                            </div>
                        </div>
                    )}
                </>
            )}

            {!audit && !auditMarkdown && !loading && !error && (
                <div className="text-xs text-muted-foreground">
                    Relatório preventivo ainda não disponível para este job.
                </div>
            )}
        </div>
    );
}
