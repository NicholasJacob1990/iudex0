import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
    DropdownMenuCheckboxItem,
    DropdownMenuRadioGroup,
    DropdownMenuRadioItem,
} from "@/components/ui/dropdown-menu";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useChatStore } from "@/stores/chat-store";
import { useBillingStore } from "@/stores/billing-store";
import { listModels, ModelId, getModelConfig } from "@/config/models";
import { getModelDescription } from "@/config/model-tooltips";
import { ChevronDown, Sparkles, Scale, Zap, Columns2, PanelTop, HelpCircle } from "lucide-react";
import Image from "next/image";
import { useModelAttachmentLimits } from "@/lib/use-model-attachment-limits";
import apiClient from "@/lib/api-client";
import { PointsPricingModal } from "@/components/billing/points-pricing-modal";

export function ModelSelector() {
    const {
        selectedModels,
        toggleModel,
        chatMode,
        setChatMode,
        showMultiModelComparator,
        setShowMultiModelComparator,
        autoConsolidate,
        setAutoConsolidate,
        multiModelView,
        setMultiModelView
    } = useChatStore();
    const { billing, fetchBilling } = useBillingStore();
    const [detailsModelId, setDetailsModelId] = useState<ModelId | null>(null);
    const detailsModel = detailsModelId ? getModelConfig(detailsModelId) : null;
    const [pointsModalOpen, setPointsModalOpen] = useState(false);
    const [pointsSummary, setPointsSummary] = useState<any | null>(null);
    const [pointsSummaryLoading, setPointsSummaryLoading] = useState(false);

    useEffect(() => {
        fetchBilling();
    }, [fetchBilling]);

    useEffect(() => {
        if (!pointsModalOpen || pointsSummaryLoading || pointsSummary) return;
        setPointsSummaryLoading(true);
        apiClient
            .getBillingSummary()
            .then((res) => setPointsSummary(res || null))
            .catch(() => setPointsSummary(null))
            .finally(() => setPointsSummaryLoading(false));
    }, [pointsModalOpen, pointsSummaryLoading, pointsSummary]);

    const attachmentLimits = useModelAttachmentLimits(selectedModels);
    const attachmentModels = attachmentLimits.perModel;
    const hasAttachmentModel = attachmentModels.length > 0;
    const attachmentCountLabel = `até ${attachmentLimits.injectionMaxFiles} (injeção) / ${attachmentLimits.ragLocalMaxFiles} (RAG)`;

    // Group models by provider for cleaner UI
    const openaiModels = listModels().filter(m => m.provider === 'openai');
    const anthropicModels = listModels().filter(m => m.provider === 'anthropic');
    const googleModels = listModels().filter(m => m.provider === 'google');
    const xaiModels = listModels().filter(m => m.provider === 'xai');
    const openrouterModels = listModels().filter(m => m.provider === 'openrouter');
    const perplexityModels = listModels().filter((m) => m.provider === 'perplexity');
    const internalModels = listModels().filter(m => m.provider === 'internal');

    // Helper to render icon
    const ModelIcon = ({ iconPath }: { iconPath: string }) => (
        <div className="relative w-4 h-4 mr-2 rounded-sm overflow-hidden bg-muted">
            <Image
                src={iconPath}
                alt=""
                fill
                sizes="16px"
                className="object-contain"
                onError={(e) => {
                    // Fallback handled by parent if needed, or simple color block
                    // For now assuming icons exist in /logos/
                }}
            />
        </div>
    );

    const usdPerPoint = useMemo(() => {
        const raw = billing?.points_anchor?.usd_per_point;
        const fallback = 0.00003;
        const parsed = typeof raw === "number" ? raw : Number(raw);
        return Number.isFinite(parsed) ? parsed : fallback;
    }, [billing]);

    const formatPoints = (value: unknown) => {
        const n = typeof value === "number" ? value : Number(value);
        if (!Number.isFinite(n)) return "—";
        return Math.round(n).toLocaleString();
    };

    const formatUsdValue = (value: unknown) => {
        const n = typeof value === "number" ? value : Number(value);
        if (!Number.isFinite(n)) return "—";
        return new Intl.NumberFormat("en-US", {
            style: "currency",
            currency: "USD",
            maximumFractionDigits: 6,
        }).format(n);
    };

    const formatUsdFromPoints = (points: unknown) => {
        const n = typeof points === "number" ? points : Number(points);
        if (!Number.isFinite(n)) return "—";
        return formatUsdValue(n * usdPerPoint);
    };

    const formatContextWindow = (tokens: unknown) => {
        const n = typeof tokens === "number" ? tokens : Number(tokens);
        if (!Number.isFinite(n) || n <= 0) return "—";
        if (n >= 1_000_000) {
            const m = n / 1_000_000;
            return Number.isInteger(m) ? `${m}M` : `${m.toFixed(1)}M`;
        }
        return `${Math.round(n / 1_000)}k`;
    };

    const activeModelId = useMemo(() => {
        const first = selectedModels && selectedModels.length > 0 ? selectedModels[0] : null;
        return (first || detailsModelId || "gpt-5.2") as ModelId;
    }, [selectedModels, detailsModelId]);

    const pointsRateTable = useMemo(() => {
        if (!billing) return [];
        const rows: { label: string; points: number; usd: number; unit: string }[] = [];
        const rateCard = billing?.llm_rate_cards?.[activeModelId];
        const deepEffort =
            billing?.perplexity?.deep_research?.effort_points ??
            billing?.tool_points?.deep_research?.effort_points;
        const deepPricing = billing?.perplexity?.deep_research_pricing;
        const pplxTokenRates = billing?.perplexity?.grounded_llm?.token_points_per_1k?.[activeModelId];
        const pplxBaseFees = billing?.perplexity?.grounded_llm?.base_fee_points?.[activeModelId];

        if (activeModelId === "sonar-deep-research" && deepPricing) {
            const tokenRates = deepPricing?.token_points_per_1k || {};
            const searchPoints = Number(deepPricing?.search_query_points ?? 0);
            const entries: Array<[string, number, string]> = [
                ["Input Tokens", Number(tokenRates?.input ?? 0), "por 1.000 tokens"],
                ["Output Tokens", Number(tokenRates?.output ?? 0), "por 1.000 tokens"],
                ["Citation Tokens", Number(tokenRates?.citation ?? 0), "por 1.000 tokens"],
                ["Reasoning Tokens", Number(tokenRates?.reasoning ?? 0), "por 1.000 tokens"],
                ["Search Queries", searchPoints, "por consulta"],
            ];
            for (const [label, points, unit] of entries) {
                if (!Number.isFinite(points) || points <= 0) continue;
                rows.push({
                    label,
                    points,
                    usd: points * usdPerPoint,
                    unit,
                });
            }
            return rows;
        }

        if (activeModelId === "sonar-deep-research" && deepEffort) {
            (["low", "medium", "high"] as const).forEach((effort) => {
                const pts = Number(deepEffort?.[effort] ?? 0);
                rows.push({
                    label: `Deep Research (${effort})`,
                    points: pts,
                    usd: pts * usdPerPoint,
                    unit: "por execução",
                });
            });
            return rows;
        }

        if (pplxTokenRates && pplxBaseFees) {
            (["low", "medium", "high"] as const).forEach((ctx) => {
                const pts = Number(pplxBaseFees?.[ctx] ?? 0);
                if (!Number.isFinite(pts) || pts <= 0) return;
                rows.push({
                    label: `Base Fee (${ctx} context)`,
                    points: pts,
                    usd: pts * usdPerPoint,
                    unit: "por chamada",
                });
            });
            const inputPoints = Number(pplxTokenRates?.input ?? 0);
            const outputPoints = Number(pplxTokenRates?.output ?? 0);
            if (Number.isFinite(inputPoints) && inputPoints > 0) {
                rows.push({
                    label: "Input Tokens",
                    points: inputPoints,
                    usd: inputPoints * usdPerPoint,
                    unit: "por 1.000 tokens",
                });
            }
            if (Number.isFinite(outputPoints) && outputPoints > 0) {
                rows.push({
                    label: "Output Tokens",
                    points: outputPoints,
                    usd: outputPoints * usdPerPoint,
                    unit: "por 1.000 tokens",
                });
            }
            return rows;
        }

        if (rateCard?.rate_table && Array.isArray(rateCard.rate_table)) {
            for (const row of rateCard.rate_table) {
                const pts = Number((row as any)?.points ?? 0);
                if (!Number.isFinite(pts)) continue;
                const usdRaw = (row as any)?.usd;
                const usd =
                    typeof usdRaw === "number" && Number.isFinite(usdRaw)
                        ? usdRaw
                        : pts * usdPerPoint;
                rows.push({
                    label: String((row as any)?.label ?? (row as any)?.key ?? "Item"),
                    points: pts,
                    usd,
                    unit: String((row as any)?.unit ?? ""),
                });
            }
            return rows;
        }

        const llmRates = billing?.llm_points_per_call?.[activeModelId];
        if (llmRates) {
            (["S", "M", "L"] as const).forEach((size) => {
                const pts = Number(llmRates?.[size] ?? 0);
                rows.push({
                    label: `LLM (${size})`,
                    points: pts,
                    usd: pts * usdPerPoint,
                    unit: "por chamada",
                });
            });
        }
        return rows;
    }, [billing, activeModelId, usdPerPoint]);

    const pointsRateNotes = useMemo(() => {
        const rateCard = billing?.llm_rate_cards?.[activeModelId];
        const notes = (rateCard as any)?.notes;
        if (Array.isArray(notes)) {
            return notes.map((t: any) => String(t));
        }
        if (activeModelId === "sonar-deep-research") {
            const deepNotes = billing?.perplexity?.deep_research_pricing?.notes;
            if (Array.isArray(deepNotes)) {
                return deepNotes.map((t: any) => String(t));
            }
        }
        if (activeModelId === "sonar" || activeModelId === "sonar-pro") {
            const pplxNotes = billing?.perplexity?.grounded_llm?.notes;
            if (Array.isArray(pplxNotes)) {
                return pplxNotes.map((t: any) => String(t));
            }
        }
        return [];
    }, [billing, activeModelId]);

    const renderRates = (modelId: ModelId) => {
        if (!billing) {
            return <div className="text-xs text-muted-foreground">Carregando taxas…</div>;
        }

        const rateCard = billing?.llm_rate_cards?.[modelId];
        const llmRates = billing?.llm_points_per_call?.[modelId];
        const pplxToken = billing?.perplexity?.grounded_llm?.token_points_per_1k?.[modelId];
        const pplxFee = billing?.perplexity?.grounded_llm?.base_fee_points?.[modelId];
        const pplxNotes = billing?.perplexity?.grounded_llm?.notes;
        const deepEffort =
            billing?.perplexity?.deep_research?.effort_points ??
            billing?.tool_points?.deep_research?.effort_points;
        const deepPricing = billing?.perplexity?.deep_research_pricing;

        if (modelId === "sonar-deep-research" && deepPricing) {
            const tokenRates = deepPricing?.token_points_per_1k || {};
            const searchPoints = Number(deepPricing?.search_query_points ?? 0);
            return (
                <div className="space-y-2">
                    <div className="text-xs font-semibold">Cobrança variável (Deep Research)</div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                        {[
                            { label: "Input Tokens", points: Number(tokenRates?.input ?? 0), unit: "por 1.000 tokens" },
                            { label: "Output Tokens", points: Number(tokenRates?.output ?? 0), unit: "por 1.000 tokens" },
                            { label: "Citation Tokens", points: Number(tokenRates?.citation ?? 0), unit: "por 1.000 tokens" },
                            { label: "Reasoning Tokens", points: Number(tokenRates?.reasoning ?? 0), unit: "por 1.000 tokens" },
                            { label: "Search Queries", points: searchPoints, unit: "por consulta" },
                        ].map((row) => (
                            <div key={row.label} className="rounded-md border p-2">
                                <div className="font-semibold">{row.label}</div>
                                <div>{formatPoints(row.points)} pts</div>
                                <div className="text-[11px] text-muted-foreground">
                                    {formatUsdFromPoints(row.points)} {row.unit}
                                </div>
                            </div>
                        ))}
                    </div>
                    {Array.isArray((deepPricing as any)?.notes) && (deepPricing as any).notes.length > 0 ? (
                        <div className="space-y-1 text-[11px] text-muted-foreground">
                            {(deepPricing as any).notes.map((t: any, idx: number) => (
                                <div key={idx}>{String(t)}</div>
                            ))}
                        </div>
                    ) : null}
                </div>
            );
        }

        if (modelId === "sonar-deep-research" && deepEffort) {
            return (
                <div className="space-y-2">
                    <div className="text-xs font-semibold">Deep Research (por execução)</div>
                    <div className="grid grid-cols-3 gap-2 text-xs">
                        {(["low", "medium", "high"] as const).map((effort) => (
                            <div key={effort} className="rounded-md border p-2">
                                <div className="font-semibold uppercase">{effort}</div>
                                <div>{formatPoints(deepEffort?.[effort])} pts</div>
                                <div className="text-[11px] text-muted-foreground">
                                    {formatUsdFromPoints(deepEffort?.[effort])}
                                </div>
                            </div>
                        ))}
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                        Esse custo é aplicado no modo <span className="font-semibold">Deep Research</span> (com CAP mensal por plano).
                    </div>
                </div>
            );
        }

        if (pplxToken && pplxFee) {
            return (
                <div className="space-y-3">
                    <div className="text-xs font-semibold">Cobrança variável (Perplexity Sonar)</div>

                    <div className="space-y-1">
                        <div className="text-[11px] text-muted-foreground">Tokens (por 1.000)</div>
                        <div className="grid grid-cols-2 gap-2 text-xs">
                            {([
                                { key: "input", label: "Input Tokens" },
                                { key: "output", label: "Output Tokens" },
                            ] as const).map((row) => (
                                <div key={row.key} className="rounded-md border p-2">
                                    <div className="font-semibold">{row.label}</div>
                                    <div>{formatPoints(pplxToken?.[row.key])} pts</div>
                                    <div className="text-[11px] text-muted-foreground">
                                        {formatUsdFromPoints(pplxToken?.[row.key])} por 1.000 tokens
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className="space-y-1">
                        <div className="text-[11px] text-muted-foreground">
                            Base fee (por chamada) • search_context_size
                        </div>
                        <div className="grid grid-cols-3 gap-2 text-xs">
                            {(["low", "medium", "high"] as const).map((ctx) => (
                                <div key={ctx} className="rounded-md border p-2">
                                    <div className="font-semibold uppercase">{ctx}</div>
                                    <div>{formatPoints(pplxFee?.[ctx])} pts</div>
                                    <div className="text-[11px] text-muted-foreground">
                                        {formatUsdFromPoints(pplxFee?.[ctx])}
                                    </div>
                                </div>
                            ))}
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                            Se <span className="font-mono">disable_search=true</span>, o request fee é 0.
                        </div>
                    </div>
                    {Array.isArray(pplxNotes) && pplxNotes.length > 0 ? (
                        <div className="space-y-1 text-[11px] text-muted-foreground">
                            {pplxNotes.map((t: any, idx: number) => (
                                <div key={idx}>{String(t)}</div>
                            ))}
                        </div>
                    ) : null}
                </div>
            );
        }

        if (rateCard?.rate_table && Array.isArray((rateCard as any).rate_table)) {
            const rows = (rateCard as any).rate_table as any[];
            const notes = (rateCard as any).notes;
            const pricingModel = String((rateCard as any).pricing_model || "").toLowerCase();
            const heading = pricingModel === "fixed" ? "Custo fixo" : "Cobrança variável";
            return (
                <div className="space-y-2">
                    <div className="text-xs font-semibold">{heading}</div>
                    <div className="overflow-hidden rounded-md border">
                        <div className="grid grid-cols-2 bg-muted/40 px-3 py-2 text-[11px] font-semibold">
                            <div>Item</div>
                            <div className="text-right">Rate</div>
                        </div>
                        {rows.map((row, idx) => {
                            const pts = Number(row?.points ?? 0);
                            const usdRaw = row?.usd;
                            const usd =
                                typeof usdRaw === "number" && Number.isFinite(usdRaw)
                                    ? usdRaw
                                    : Number.isFinite(pts)
                                        ? pts * usdPerPoint
                                        : NaN;
                            const label = String(row?.label ?? row?.key ?? "Item");
                            const unit = String(row?.unit ?? "");
                            return (
                                <div key={`${label}-${idx}`} className="grid grid-cols-2 border-t px-3 py-2 text-xs">
                                    <div>{label}</div>
                                    <div className="text-right">
                                        <span className="font-semibold">{formatPoints(pts)}</span>{" "}
                                        <span className="text-muted-foreground">({formatUsdValue(usd)})</span>{" "}
                                        <span className="text-muted-foreground">{unit}</span>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                    {Array.isArray(notes) && notes.length > 0 ? (
                        <div className="space-y-1 text-[11px] text-muted-foreground">
                            {notes.map((t: any, idx: number) => (
                                <div key={idx}>{String(t)}</div>
                            ))}
                        </div>
                    ) : null}
                </div>
            );
        }

        if (llmRates) {
            return (
                <div className="space-y-2">
                    <div className="text-xs font-semibold">Pontos por chamada (S/M/L)</div>
                    <div className="grid grid-cols-3 gap-2 text-xs">
                        {(["S", "M", "L"] as const).map((size) => (
                            <div key={size} className="rounded-md border p-2">
                                <div className="font-semibold">{size}</div>
                                <div>{formatPoints(llmRates?.[size])} pts</div>
                                <div className="text-[11px] text-muted-foreground">
                                    {formatUsdFromPoints(llmRates?.[size])}
                                </div>
                            </div>
                        ))}
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                        Tamanho S/M/L segue os perfis do produto; pode haver multiplicador por contexto longo.
                    </div>
                </div>
            );
        }

        return <div className="text-xs text-muted-foreground">Sem rate card para este modelo.</div>;
    };

    const renderModelItem = (model: any) => {
        const isSelected = selectedModels.includes(model.id);
        return (
            <DropdownMenuCheckboxItem
                key={model.id}
                checked={isSelected}
                onCheckedChange={() => toggleModel(model.id)}
                className="flex items-center"
            >
                <ModelIcon iconPath={model.icon} />
                <div className="flex w-full items-start justify-between gap-2">
                    <div className="flex flex-col">
                        <span className="font-medium">{model.label}</span>
                        <span className="text-[10px] text-muted-foreground">
                            {formatContextWindow(model.contextWindow)} ctx • {model.latencyTier} lat
                        </span>
                    </div>
                    <TooltipProvider>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <button
                                    type="button"
                                    className="ml-auto inline-flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
                                    onClick={(e) => {
                                        e.preventDefault();
                                        e.stopPropagation();
                                        setDetailsModelId(model.id);
                                    }}
                                    aria-label={`Ver detalhes de ${model.label}`}
                                >
                                    <HelpCircle className="h-4 w-4" />
                                </button>
                            </TooltipTrigger>
                            <TooltipContent side="right" className="max-w-[220px]">
                                <div className="text-xs font-semibold">Ver detalhes</div>
                                <div className="text-[11px] text-muted-foreground">
                                    Descrição + taxas (pontos) deste modelo.
                                </div>
                            </TooltipContent>
                        </Tooltip>
                    </TooltipProvider>
                </div>
            </DropdownMenuCheckboxItem>
        );
    };

    return (
        <div className="flex items-center gap-2">
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm" className="h-8 gap-2">
                        {selectedModels.length === 0 ? "Selecionar Modelo" :
                            selectedModels.length === 1 ? (
                                <>
                                    <ModelIcon iconPath={getModelConfig(selectedModels[0] as ModelId)?.icon || ''} />
                                    {getModelConfig(selectedModels[0] as ModelId)?.label}
                                </>
                            ) : (
                                <>
                                    <Sparkles className="w-4 h-4 text-primary" />
                                    {selectedModels.length} Modelos
                                </>
                            )
                        }
                        <ChevronDown className="w-3 h-3 opacity-50" />
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-[280px]">
                    <div className="px-2 py-1.5 text-xs text-muted-foreground bg-muted/50">
                        Modo: {chatMode === 'standard' ? 'Padrão' : 'Multi-Modelo'}
                    </div>
                    <div className="px-2 py-1 text-[10px] text-muted-foreground">
                        Este modelo define as respostas do chat e o juiz/estrategista da minuta.
                    </div>
                    <div className="px-2 py-2 text-[10px] text-muted-foreground border-b border-muted/50">
                        <div className="font-semibold text-slate-600">Limites de anexos</div>
                        {hasAttachmentModel ? (
                            <div className="mt-1 space-y-1">
                                {attachmentModels.map((model) => (
                                    <div key={model.id}>
                                        {model.label}: até {model.maxLabel} / arquivo
                                    </div>
                                ))}
                                {attachmentModels.length > 1 && (
                                    <div className="text-[10px] text-muted-foreground">
                                        Limite efetivo: {attachmentLimits.effectiveMaxLabel} / arquivo
                                    </div>
                                )}
                                <div>Quantidade: {attachmentCountLabel}</div>
                                <div>Tipos: {attachmentLimits.typesLabel}</div>
                            </div>
                        ) : (
                            <div className="mt-1">Selecione um modelo para ver limites.</div>
                        )}
                    </div>
                    {chatMode === 'multi-model' && (
                        <>
                            <DropdownMenuCheckboxItem
                                checked={showMultiModelComparator}
                                onCheckedChange={(v) => setShowMultiModelComparator(!!v)}
                                className="flex items-center gap-2"
                            >
                                <Columns2 className="h-3.5 w-3.5" />
                                Exibir comparador (Tabs)
                            </DropdownMenuCheckboxItem>
                            <DropdownMenuLabel className="pt-2 text-xs text-muted-foreground">Layout do comparador</DropdownMenuLabel>
                            <DropdownMenuRadioGroup
                                value={multiModelView}
                                onValueChange={(v) => setMultiModelView(v as any)}
                            >
                                <DropdownMenuRadioItem value="tabs" className="flex items-center gap-2">
                                    <PanelTop className="h-3.5 w-3.5" />
                                    Tabs
                                </DropdownMenuRadioItem>
                                <DropdownMenuRadioItem value="columns" className="flex items-center gap-2">
                                    <Columns2 className="h-3.5 w-3.5" />
                                    Lado a lado
                                </DropdownMenuRadioItem>
                            </DropdownMenuRadioGroup>
                            <DropdownMenuCheckboxItem
                                checked={autoConsolidate}
                                onCheckedChange={(v) => setAutoConsolidate(!!v)}
                                className="flex items-center gap-2"
                            >
                                <Sparkles className="h-3.5 w-3.5" />
                                Gerar consolidado automaticamente
                            </DropdownMenuCheckboxItem>
                        </>
                    )}
                    <DropdownMenuSeparator />

                    <DropdownMenuLabel>OpenAI</DropdownMenuLabel>
                    {openaiModels.map(renderModelItem)}

                    <DropdownMenuSeparator />
                    <DropdownMenuLabel>Anthropic</DropdownMenuLabel>
                    {anthropicModels.map(renderModelItem)}

                    <DropdownMenuSeparator />
                    <DropdownMenuLabel>Google</DropdownMenuLabel>
                    {googleModels.map(renderModelItem)}

                    {perplexityModels.length > 0 && (
                        <>
                            <DropdownMenuSeparator />
                            <DropdownMenuLabel>Perplexity</DropdownMenuLabel>
                            {perplexityModels.map(renderModelItem)}
                        </>
                    )}

                    {xaiModels.length > 0 && (
                        <>
                            <DropdownMenuSeparator />
                            <DropdownMenuLabel>xAI</DropdownMenuLabel>
                            {xaiModels.map(renderModelItem)}
                        </>
                    )}

                    {openrouterModels.length > 0 && (
                        <>
                            <DropdownMenuSeparator />
                            <DropdownMenuLabel>OpenRouter / Meta</DropdownMenuLabel>
                            {openrouterModels.map(renderModelItem)}
                        </>
                    )}

                    <DropdownMenuSeparator />
                    <DropdownMenuLabel>Interno</DropdownMenuLabel>
                    {internalModels.map(renderModelItem)}

                </DropdownMenuContent>
            </DropdownMenu>

            <PointsPricingModal
                open={pointsModalOpen}
                onClose={() => setPointsModalOpen(false)}
                pointsAvailable={
                    typeof pointsSummary?.available_points === "number"
                        ? pointsSummary.available_points
                        : null
                }
                planLabel={
                    typeof pointsSummary?.plan_key === "string"
                        ? String(pointsSummary.plan_key).toUpperCase()
                        : null
                }
                modelLabel={getModelConfig(activeModelId)?.label || String(activeModelId)}
                rateTable={pointsRateTable}
                notes={pointsRateNotes}
            />

            <Dialog
                open={Boolean(detailsModelId)}
                onOpenChange={(open) => {
                    if (!open) setDetailsModelId(null);
                }}
            >
                <DialogContent className="max-w-2xl">
                    <DialogHeader>
                        <DialogTitle>{detailsModel?.label || "Detalhes do modelo"}</DialogTitle>
                        <DialogDescription>
                            {detailsModelId ? getModelDescription(detailsModelId) : ""}
                        </DialogDescription>
                    </DialogHeader>
                    {detailsModel ? (
                        <div className="space-y-4">
                            <div className="grid grid-cols-2 gap-3 text-xs">
                                <div className="rounded-md border p-3">
                                    <div className="text-[11px] text-muted-foreground">Provider</div>
                                    <div className="font-semibold">{detailsModel.provider}</div>
                                </div>
                                <div className="rounded-md border p-3">
                                    <div className="text-[11px] text-muted-foreground">Contexto</div>
                                    <div className="font-semibold">
                                        {detailsModel.contextWindow.toLocaleString()} tokens
                                    </div>
                                </div>
                            </div>
                            <div className="rounded-md border p-3">
                                {renderRates(detailsModel.id)}
                            </div>
                        </div>
                    ) : null}
                </DialogContent>
            </Dialog>

            {/* Quick Toggles */}
            <div className="flex items-center bg-muted/50 rounded-lg p-0.5">
                <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => setPointsModalOpen(true)}
                    title="Pontos & tarifas"
                >
                    <HelpCircle className="w-3.5 h-3.5" />
                </Button>
                <Button
                    variant={chatMode === 'standard' ? 'secondary' : 'ghost'}
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => setChatMode('standard')}
                    title="Modo Padrão (Único Modelo)"
                >
                    <Zap className="w-3.5 h-3.5" />
                </Button>
                <Button
                    variant={chatMode === 'multi-model' ? 'secondary' : 'ghost'}
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => setChatMode('multi-model')}
                    title="Modo Multi-Modelo (Paralelo)"
                >
                    <Scale className="w-3.5 h-3.5" />
                </Button>
            </div>
        </div>
    );
}
