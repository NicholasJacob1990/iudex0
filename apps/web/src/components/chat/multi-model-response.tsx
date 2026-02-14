'use client';

import { useMemo, useState, type CSSProperties } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ChatMessage } from './chat-message';
import { TokenUsageCircle } from './token-usage-circle';
import { cn } from '@/lib/utils';
import { Sparkles, Columns2, PanelTop } from 'lucide-react';
import { getModelConfig, ModelId } from '@/config/models';
import Image from 'next/image';
import { Button } from '@/components/ui/button';
import { useChatStore } from '@/stores/chat-store';
import { toast } from 'sonner';

interface MultiModelResponseProps {
    messages: any[]; // Using any to avoid type duplication issues, matches ChatMessage structure
    onCopy?: (message: any) => void;
    onRegenerate?: (message: any) => void;
    disableRegenerate?: boolean;
    assistantBubbleStyle?: CSSProperties;
}

export function MultiModelResponse({ messages, onCopy, onRegenerate, disableRegenerate, assistantBubbleStyle }: MultiModelResponseProps) {
    const { multiModelView, setMultiModelView, setChatMode, setSelectedModels, setSelectedModel, consolidateTurn } = useChatStore();
    const [isConsolidating, setIsConsolidating] = useState(false);

    const isConsolidated = (msg: any) =>
        msg?.metadata?.is_consolidated || String(msg?.metadata?.model || '').toLowerCase() === 'consolidado';

    const ordered = useMemo(() => {
        const list = messages ? [...messages] : [];
        return list.sort((a, b) => {
            const ac = isConsolidated(a) ? 0 : 1;
            const bc = isConsolidated(b) ? 0 : 1;
            if (ac !== bc) return ac - bc;
            return 0;
        });
    }, [messages]);

    if (ordered.length === 0) return null;

    const consolidated = ordered.find((m) => isConsolidated(m)) || null;
    const candidates = ordered.filter((m) => !isConsolidated(m));
    const uniqueCandidateModels = new Set(candidates.map((m) => m?.metadata?.model).filter(Boolean));
    const canConsolidate = !consolidated && uniqueCandidateModels.size >= 2;
    const turnId = (ordered[0] as any)?.metadata?.turn_id as string | undefined;

    // Find default: prefer consolidated if present
    const defaultTab = ordered[0].id;

    return (
        <div className="my-4 rounded-xl border border-indigo-100 bg-indigo-50/30 p-4 animate-fade-in">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-xs font-semibold text-indigo-600">
                    <Sparkles className="h-3.5 w-3.5" />
                    <span>Resposta Multi-Modelo</span>
                </div>

                <div className="flex items-center gap-2">
                    <div className="flex items-center rounded-lg border border-indigo-100 bg-white/50 p-1">
                        <Button
                            type="button"
                            size="sm"
                            variant={multiModelView === 'tabs' ? 'secondary' : 'ghost'}
                            className="h-7 px-2 text-xs"
                            onClick={() => setMultiModelView('tabs')}
                            title="Visualização por Tabs"
                        >
                            <PanelTop className="mr-1 h-3.5 w-3.5" />
                            Tabs
                        </Button>
                        <Button
                            type="button"
                            size="sm"
                            variant={multiModelView === 'columns' ? 'secondary' : 'ghost'}
                            className="h-7 px-2 text-xs"
                            onClick={() => setMultiModelView('columns')}
                            title="Visualização lado a lado"
                        >
                            <Columns2 className="mr-1 h-3.5 w-3.5" />
                            Lado a lado
                        </Button>
                    </div>

                    {canConsolidate && (
                        <Button
                            type="button"
                            size="sm"
                            className="h-7 text-[11px]"
                            disabled={isConsolidating || !turnId}
                            onClick={async () => {
                                if (!turnId) return;
                                try {
                                    setIsConsolidating(true);
                                    await consolidateTurn(turnId);
                                } catch (e) {
                                    console.error(e);
                                    toast.error('Erro ao gerar Consolidado');
                                } finally {
                                    setIsConsolidating(false);
                                }
                            }}
                            title="Gera uma resposta 'juiz/merge' (consome tokens adicionais)"
                        >
                            Gerar Consolidado
                        </Button>
                    )}
                </div>
            </div>

            {multiModelView === 'tabs' ? (
                <Tabs defaultValue={defaultTab} className="w-full">
                    <TabsList className="w-full justify-start rounded-lg bg-white/50 p-1 border border-indigo-100/50 h-auto flex-wrap gap-1">
                        {ordered.map((msg) => {
                            const modelId = msg.metadata?.model as ModelId;
                            const config = getModelConfig(modelId);
                            const consolidatedTab = isConsolidated(msg);

                            return (
                                <TabsTrigger
                                    key={msg.id}
                                    value={msg.id}
                                    className="flex-1 min-w-[120px] text-xs data-[state=active]:bg-white data-[state=active]:text-indigo-700 data-[state=active]:shadow-sm transition-all"
                                >
                                    <div className="flex flex-col items-center gap-1.5 py-1">
                                        <div className="flex items-center gap-2">
                                            {consolidatedTab ? (
                                                <div className="relative flex h-4 w-4 items-center justify-center rounded-sm bg-indigo-100 text-indigo-600">
                                                    <Sparkles className="h-2.5 w-2.5" />
                                                </div>
                                            ) : config?.icon ? (
                                                <div className="relative h-4 w-4 overflow-hidden rounded-sm">
                                                    <Image src={config.icon} alt={config.label} fill className="object-cover" />
                                                </div>
                                            ) : (
                                                <div className="relative flex h-4 w-4 items-center justify-center rounded-sm bg-muted text-muted-foreground">
                                                    <div className="h-2 w-2 rounded-full bg-current" />
                                                </div>
                                            )}
                                            <span className="font-semibold">
                                                {consolidatedTab ? 'Consolidado' : (config?.label || msg.metadata?.model || 'Modelo')}
                                            </span>
                                        </div>

                                        {/* Token usage circular per model */}
                                        {msg.metadata?.token_usage && (
                                            <TokenUsageCircle data={msg.metadata.token_usage} size="sm" showLabel={true} />
                                        )}
                                    </div>
                                </TabsTrigger>
                            );
                        })}
                    </TabsList>

                    {ordered.map((msg) => (
                        <TabsContent key={msg.id} value={msg.id} className="mt-4 focus-visible:outline-none">
                            {!isConsolidated(msg) && msg.metadata?.model && (
                                <div className="mb-2 flex justify-end">
                                    <Button
                                        type="button"
                                        size="sm"
                                        variant="outline"
                                        className="h-7 text-[11px]"
                                        onClick={() => {
                                            const model = String(msg.metadata.model);
                                            setSelectedModel(model);
                                            setSelectedModels([model]);
                                            setChatMode('standard');
                                            toast.success(`Escolhida a resposta de ${model}`);
                                        }}
                                    >
                                        Escolher esta resposta
                                    </Button>
                                </div>
                            )}
                            <ChatMessage
                                message={msg}
                                onCopy={onCopy}
                                onRegenerate={onRegenerate}
                                disableRegenerate={disableRegenerate}
                                assistantBubbleStyle={assistantBubbleStyle}
                            />
                        </TabsContent>
                    ))}
                </Tabs>
            ) : (
                <div className="space-y-3">
                    {consolidated && (
                        <div className="rounded-xl border border-indigo-100 bg-white/60 p-3">
                            <div className="mb-2 flex items-center gap-2 text-xs font-bold text-indigo-800">
                                <div className="relative flex h-4 w-4 items-center justify-center rounded-sm bg-indigo-100 text-indigo-600">
                                    <Sparkles className="h-2.5 w-2.5" />
                                </div>
                                Consolidado
                            </div>
                            <ChatMessage
                                message={consolidated}
                                onCopy={onCopy}
                                onRegenerate={onRegenerate}
                                disableRegenerate={disableRegenerate}
                                assistantBubbleStyle={assistantBubbleStyle}
                            />
                        </div>
                    )}

                    <div className={cn("grid gap-3", candidates.length >= 2 ? "md:grid-cols-2" : "grid-cols-1")}>
                        {candidates.map((msg) => {
                            const modelId = msg.metadata?.model as ModelId;
                            const config = getModelConfig(modelId);
                            return (
                                <div key={msg.id} className="rounded-xl border border-indigo-100 bg-white/60 p-3">
                                    <div className="mb-2 flex items-center justify-between gap-2">
                                        <div className="flex items-center gap-2 text-xs font-bold text-indigo-800">
                                            {config?.icon ? (
                                                <div className="relative h-4 w-4 overflow-hidden rounded-sm">
                                                    <Image src={config.icon} alt={config.label} fill className="object-cover" />
                                                </div>
                                            ) : (
                                                <div className="relative flex h-4 w-4 items-center justify-center rounded-sm bg-muted text-muted-foreground">
                                                    <div className="h-2 w-2 rounded-full bg-current" />
                                                </div>
                                            )}
                                            <span>{config?.label || msg.metadata?.model || 'Modelo'}</span>
                                            {/* Token usage circular per model */}
                                            {msg.metadata?.token_usage && (
                                                <TokenUsageCircle data={msg.metadata.token_usage} size="sm" showLabel={true} />
                                            )}
                                        </div>
                                        <Button
                                            type="button"
                                            size="sm"
                                            variant="outline"
                                            className="h-7 text-[11px]"
                                            onClick={() => {
                                                const model = String(msg.metadata?.model || '');
                                                if (!model) return;
                                                setSelectedModel(model);
                                                setSelectedModels([model]);
                                                setChatMode('standard');
                                                toast.success(`Escolhida a resposta de ${model}`);
                                            }}
                                        >
                                            Escolher esta resposta
                                        </Button>
                                    </div>
                                    <ChatMessage
                                        message={msg}
                                        onCopy={onCopy}
                                        onRegenerate={onRegenerate}
                                        disableRegenerate={disableRegenerate}
                                        assistantBubbleStyle={assistantBubbleStyle}
                                    />
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            <div className="mt-2 text-xs text-center text-muted-foreground/60">
                Compare as respostas, escolha um modelo para continuar, ou gere um consolidado (opcional).
            </div>
        </div>
    );
}
