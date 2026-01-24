"use client";

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
    CheckCircle2,
    ArrowRight,
    FileText,
    Settings,
    Play,
    Upload,
    Gavel,
    Scale,
    File,
    Bot,
    Sparkles,
    ChevronRight,
    TerminalSquare,
    Layout,
    HelpCircle
} from 'lucide-react';
import { useChatStore } from '@/stores/chat-store';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { Checkbox } from '@/components/ui/checkbox';
import {
    Accordion,
    AccordionContent,
    AccordionItem,
    AccordionTrigger,
} from "@/components/ui/accordion";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'; // Assuming you have a utils file
import ReactMarkdown from 'react-markdown';
import { useCanvasStore } from '@/stores/canvas-store';
import { DeepResearchViewer } from '@/components/chat/deep-research-viewer';
import { JobQualityPanel } from '@/components/chat/job-quality-panel';
import { JobQualityPipelinePanel } from '@/components/chat/job-quality-pipeline-panel';
import { useUploadLimits } from '@/lib/use-upload-limits';
import { listModels } from '@/config/models';
import { toast } from 'sonner';

export function GeneratorWizard({
    caseId,
    caseThesis,
    chatId,
}: {
    caseId: string;
    caseThesis?: string;
    chatId?: string;
}) {
    const [step, setStep] = useState(1);
    const store = useChatStore();
    const canvas = useCanvasStore();
    const { maxUploadLabel } = useUploadLimits();

    // Local state for wizard specific interactions not yet in store or direct mappings
    const [activeTab, setActiveTab] = useState("setup");
    const [advancedMode, setAdvancedMode] = useState(false);
    const [showQualityDetails, setShowQualityDetails] = useState(false);

    const [loading, setLoading] = useState(false);
    const effortLevelLabel = Number.isFinite(store.effortLevel)
        ? Math.max(1, Math.min(5, Math.floor(store.effortLevel)))
        : 3;
    const pageRangeLabel = (store.minPages > 0 || store.maxPages > 0)
        ? `${store.minPages}-${store.maxPages} págs`
        : `Auto (rigor ${effortLevelLabel}/5)`;

    const profileDefaults = (() => {
        const profile = String(store.qualityProfile || 'padrao').toLowerCase();
        if (profile === 'rapido')
            return { maxRounds: 1, targetFinalScore: 9.0, targetSectionScore: 8.5, styleRefineMaxRounds: 1 };
        if (profile === 'rigoroso')
            return { maxRounds: 4, targetFinalScore: 9.8, targetSectionScore: 9.4, styleRefineMaxRounds: 3 };
        if (profile === 'auditoria')
            return { maxRounds: 6, targetFinalScore: 10.0, targetSectionScore: 9.6, styleRefineMaxRounds: 4 };
        return { maxRounds: 2, targetFinalScore: 9.4, targetSectionScore: 9.0, styleRefineMaxRounds: 2 }; // padrao
    })();

    const temperatureFromMode =
        store.creativityMode === 'rigoroso' ? 0.1 : store.creativityMode === 'criativo' ? 0.6 : 0.3;
    const effectiveTemperature =
        typeof store.temperatureOverride === 'number' ? store.temperatureOverride : temperatureFromMode;

    const MAX_ROLE_MODELS = 3;
    const agentModelOptions = listModels({ forAgents: true });
    const baseModelOptions = listModels({ forJuridico: true });
    const agentChatModelOptions = agentModelOptions.filter((m) => m.capabilities.includes('chat'));
    const baseChatModelOptions = baseModelOptions.filter((m) => m.capabilities.includes('chat'));
    const webSearchModelOptions = agentModelOptions.filter(
        (m) =>
            ['openai', 'anthropic', 'google', 'perplexity'].includes(m.provider)
            && m.capabilities.includes('chat')
            && !m.capabilities.includes('deep_research')
    );
    const getModelLabel = (modelId: string) => {
        const found =
            agentModelOptions.find((m) => m.id === modelId) || baseModelOptions.find((m) => m.id === modelId);
        return found?.label || modelId;
    };
    const effectiveDrafterModels = (
        store.agentDrafterModels?.length
            ? store.agentDrafterModels
            : [store.gptModel, store.claudeModel, store.selectedModel]
    ).filter((m): m is string => Boolean(m && String(m).trim()));
    const effectiveReviewerModels = (
        store.agentReviewerModels?.length ? store.agentReviewerModels : effectiveDrafterModels
    ).filter((m): m is string => Boolean(m && String(m).trim()));
    const committeeAgentsCount = new Set([...effectiveDrafterModels, ...effectiveReviewerModels]).size;

    const toggleCommitteeRoleModel = (
        current: string[],
        modelId: string,
        setter: (models: string[]) => void
    ) => {
        if (current.includes(modelId)) {
            setter(current.filter((m) => m !== modelId));
            return;
        }
        if (current.length >= MAX_ROLE_MODELS) {
            toast.info(`Limite de ${MAX_ROLE_MODELS} modelos por papel no comitê.`);
            return;
        }
        setter([...current, modelId]);
    };

    const canWebSearch = store.auditMode !== 'sei_only';
    const strictGateMode =
        store.strictDocumentGateOverride == null ? 'auto' : store.strictDocumentGateOverride ? 'on' : 'off';
    const hilSectionPolicyMode =
        store.hilSectionPolicyOverride == null ? 'auto' : store.hilSectionPolicyOverride;
    const hilFinalRequiredMode =
        store.hilFinalRequiredOverride == null ? 'auto' : store.hilFinalRequiredOverride ? 'on' : 'off';
    const expandScopeMode =
        store.qualityRagRetryExpandScope == null ? 'auto' : store.qualityRagRetryExpandScope ? 'on' : 'off';

    const [criticalChecklistText, setCriticalChecklistText] = useState(() => {
        const items = Array.isArray(store.documentChecklist) ? store.documentChecklist : [];
        return items.filter((i: any) => i?.critical).map((i: any) => String(i.label || '').trim()).filter(Boolean).join('\n');
    });
    const [nonCriticalChecklistText, setNonCriticalChecklistText] = useState(() => {
        const items = Array.isArray(store.documentChecklist) ? store.documentChecklist : [];
        return items.filter((i: any) => !i?.critical).map((i: any) => String(i.label || '').trim()).filter(Boolean).join('\n');
    });

    const updateDocumentChecklist = (criticalText: string, nonCriticalText: string) => {
        const critical = String(criticalText || '')
            .split('\n')
            .map((s) => s.trim())
            .filter(Boolean)
            .map((label) => ({ label, critical: true }));
        const nonCritical = String(nonCriticalText || '')
            .split('\n')
            .map((s) => s.trim())
            .filter(Boolean)
            .map((label) => ({ label, critical: false }));
        store.setDocumentChecklist([...critical, ...nonCritical]);
    };

    // Sync thesis on init
    // useEffect(() => { if(caseThesis) store.setThesis(caseThesis) }, [caseThesis]);

    const nextStep = () => setStep(s => Math.min(s + 1, 3));
    const prevStep = () => setStep(s => Math.max(s - 1, 1));

    const handleStartGeneration = async () => {
        try {
            setLoading(true);

            // 1. Ensure a chat exists or create one
            const api = useChatStore.getState();
            if (chatId) {
                await api.setCurrentChat(chatId);
            }
            if (!useChatStore.getState().currentChat) {
                await api.createChat();
            }

            // 2. Advance to Cockpit immediately for UX
            setStep(3);

            // 3. Trigger generation (LangGraph Job + SSE -> Outline/Sections)
            // Nota: isso habilita "documentos grandes" por seções, e alimenta o Cockpit com outline real.
            const thesis = useChatStore.getState().thesis;
            await useChatStore.getState().startLangGraphJob(thesis || "Gerar documento base");

        } catch (error) {
            console.error(error);
            // toast.error("Erro ao iniciar geração"); 
            // setStep(2); // Go back on error
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="space-y-6">
            {/* Stepper Header */}
            <div className="flex items-center justify-between px-4">
                <div className="flex items-center gap-4 w-full">
                    {[
                        { id: 1, label: 'Contexto & Fatos', icon: FileText },
                        { id: 2, label: 'Configuração', icon: Settings },
                        { id: 3, label: 'Execução (Cockpit)', icon: Play }
                    ].map((s, idx) => (
                        <div key={s.id} className="flex items-center flex-1">
                            <div className={cn(
                                "flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                                step === s.id ? "bg-primary/10 text-primary border border-primary/20" :
                                    step > s.id ? "text-muted-foreground" : "text-muted-foreground/60"
                            )}>
                                <div className={cn(
                                    "h-6 w-6 rounded-full flex items-center justify-center text-xs border",
                                    step === s.id ? "border-primary bg-primary text-primary-foreground" :
                                        step > s.id ? "border-primary text-primary" : "border-muted-foreground/30"
                                )}>
                                    {step > s.id ? <CheckCircle2 className="h-4 w-4" /> : s.id}
                                </div>
                                {s.label}
                            </div>
                            {idx < 2 && <div className="h-[1px] flex-1 bg-border mx-4" />}
                        </div>
                    ))}
                </div>
            </div>

            {/* Steps Content */}
            <Card className="min-h-[500px] border-none shadow-none bg-transparent">
                <CardContent className="p-0">

                    {/* STEP 1: CONTEXTO */}
                    {step === 1 && (
                        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                {/* Left: Type & Files */}
                                <div className="space-y-6">
                                    <div className="space-y-3">
                                        <Label className="text-base">Tipo de Peça</Label>
                                        <div className="grid grid-cols-2 gap-3">
                                            {['PETICAO_INICIAL', 'CONTESTACAO', 'RECURSO', 'PARECER'].map(type => (
                                                <div
                                                    key={type}
                                                    onClick={() => store.setDocumentType(type as any)}
                                                    className={cn(
                                                        "cursor-pointer rounded-xl border p-4 hover:border-primary/50 transition-all text-left",
                                                        store.documentType === type ? "border-primary bg-primary/5 ring-1 ring-primary/20" : "bg-card"
                                                    )}
                                                >
                                                    <div className="font-semibold text-sm mb-1">{type.replace('_', ' ')}</div>
                                                    <div className="text-[10px] text-muted-foreground">Template padrão</div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    <div className="space-y-3">
                                        <div className="flex items-center gap-1">
                                            <Label className="text-base">Fonte de Contexto</Label>
                                            <TooltipProvider>
                                                <Tooltip>
                                                    <TooltipTrigger>
                                                        <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                                                    </TooltipTrigger>
                                                    <TooltipContent side="right" className="max-w-xs text-xs">
                                                        <p>Escolha onde a IA vai buscar os fatos do processo. “Autos” usa uma pasta estruturada (SEI/PJe/eproc). “Upload/Cache” usa arquivos soltos enviados aqui.</p>
                                                    </TooltipContent>
                                                </Tooltip>
                                            </TooltipProvider>
                                        </div>
                                        <Tabs
                                            value={store.contextMode}
                                            onValueChange={(v) => store.setContextMode(v as any)}
                                            className="w-full"
                                        >
                                            <TabsList className="grid w-full grid-cols-3 mb-4">
                                                <TabsTrigger value="auto">Auto</TabsTrigger>
                                                <TabsTrigger value="rag_local">Autos do Processo</TabsTrigger>
                                                <TabsTrigger value="upload_cache">Arquivos Soltos (Upload)</TabsTrigger>
                                            </TabsList>

                                            <TabsContent value="auto">
                                                <div className="border-2 border-dashed border-emerald-200/60 rounded-xl p-6 text-center bg-emerald-50/20 hover:bg-emerald-50/30 transition-colors">
                                                    <Sparkles className="h-8 w-8 mx-auto text-emerald-500 mb-3" />
                                                    <p className="text-sm font-medium">Modo Automático</p>
                                                    <p className="text-xs text-muted-foreground mt-1">
                                                        O sistema escolhe entre RAG local e upload/cache conforme tamanho e tipo.
                                                    </p>
                                                </div>
                                            </TabsContent>

                                            <TabsContent value="rag_local">
                                                <div className="border-2 border-dashed border-muted-foreground/20 rounded-xl p-8 text-center bg-muted/5 hover:bg-muted/10 transition-colors cursor-pointer">
                                                    <Upload className="h-8 w-8 mx-auto text-muted-foreground mb-3" />
                                                    <p className="text-sm font-medium">Pasta do Processo (RAG Local)</p>
                                                    <p className="text-xs text-muted-foreground mt-1">
                                                        Estrutura de pastas (SEI, PJe, eproc). Ideal para citar fatos dos autos.
                                                    </p>
                                                    <Button size="sm" variant="secondary" className="mt-4">
                                                        Selecionar Pasta
                                                    </Button>
                                                </div>
                                            </TabsContent>

                                            <TabsContent value="upload_cache">
                                                <div className="border-2 border-dashed border-indigo-200/50 rounded-xl p-6 text-center bg-indigo-50/10 hover:bg-indigo-50/20 transition-colors cursor-pointer">
                                                    <File className="h-8 w-8 mx-auto text-indigo-400 mb-3" />
                                                    <p className="text-sm font-medium">Arquivos Soltos (Upload/Cache)</p>
                                                    <p className="text-xs text-muted-foreground mt-1 mb-3">
                                                        PDFs, DOCX, TXT (até {maxUploadLabel}). Bom para poucos arquivos sem estrutura.
                                                    </p>

                                                    {store.contextFiles.length > 0 ? (
                                                        <div className="space-y-1 text-left bg-background p-2 rounded border">
                                                            {store.contextFiles.map((f, i) => (
                                                                <div key={i} className="text-[10px] flex items-center gap-2">
                                                                    <FileText className="h-3 w-3" /> {f.split('/').pop()}
                                                                </div>
                                                            ))}
                                                        </div>
                                                    ) : (
                                                        <Button size="sm" className="bg-indigo-600 hover:bg-indigo-700 text-white">
                                                            Escolher Arquivos
                                                        </Button>
                                                    )}

                                                    <div className="mt-4 flex items-center justify-center gap-2 text-[10px] text-muted-foreground">
                                                        <Switch checked={true} disabled className="scale-75" />
                                                        Cache Ativo (60 min)
                                                    </div>
                                                </div>
                                            </TabsContent>
                                        </Tabs>
                                    </div>
                                </div>

                                {/* Right: Facts & Thesis */}
                                <div className="space-y-4">
                                    <div className="flex justify-between items-center">
                                        <Label className="text-base">Tese & Fatos</Label>
                                        <Button variant="ghost" size="sm" className="h-6 text-xs text-amber-600">
                                            <Sparkles className="h-3 w-3 mr-1" />
                                            Gerar Resumo Automático
                                        </Button>
                                    </div>

                                    <Textarea
                                        placeholder="Cole o resumo dos fatos aqui ou descreva a tese central..."
                                        className="min-h-[350px] resize-none p-4 leading-relaxed bg-card"
                                        value={store.thesis}
                                        onChange={(e) => store.setThesis(e.target.value)}
                                    />
                                </div>
                            </div>

	                            <div className="flex justify-end pt-4">
	                                <Button onClick={nextStep} className="pl-8 pr-6 rounded-xl">
	                                    Próximo: Configuração <ArrowRight className="ml-2 h-4 w-4" />
	                                </Button>
	                            </div>
	                        </div>
	                    )}

                    {/* STEP 2: CONFIGURAÇÃO */}
                    {step === 2 && (
                        <div className="space-y-6 animate-in fade-in slide-in-from-right-4">

                            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                {/* Column 1: Basics */}
                                <div className="space-y-6">
                                    <div>
                                        <h3 className="text-sm font-semibold uppercase text-muted-foreground mb-4 flex items-center gap-2">
                                            <Layout className="h-4 w-4" /> ① Geração
                                        </h3>
                                        <Card>
	                                            <CardContent className="p-4 space-y-4">
	                                                <div className="space-y-2">
	                                                    <div className="flex justify-between">
	                                                        <Label>Intervalo de páginas</Label>
	                                                        <span className="text-xs font-mono bg-muted px-2 py-0.5 rounded">
	                                                            {pageRangeLabel}
	                                                        </span>
	                                                    </div>
	                                                    <div className="grid grid-cols-2 gap-2 pt-2">
	                                                        <div className="space-y-1">
	                                                            <Label className="text-[10px] text-muted-foreground">Mín.</Label>
                                                            <Input
                                                                type="number"
                                                                min={0}
                                                                className="h-7 text-[11px] bg-white"
                                                                placeholder="Auto"
                                                                value={store.minPages === 0 ? '' : store.minPages}
                                                                onChange={(e) => {
                                                                    const next = parseInt(e.target.value, 10);
                                                                    store.setPageRange({ minPages: Number.isNaN(next) ? 0 : next });
                                                                }}
                                                            />
                                                        </div>
                                                        <div className="space-y-1">
                                                            <Label className="text-[10px] text-muted-foreground">Máx.</Label>
                                                            <Input
                                                                type="number"
                                                                min={0}
                                                                className="h-7 text-[11px] bg-white"
                                                                placeholder="Auto"
                                                                value={store.maxPages === 0 ? '' : store.maxPages}
                                                                onChange={(e) => {
                                                                    const next = parseInt(e.target.value, 10);
                                                                    store.setPageRange({ maxPages: Number.isNaN(next) ? 0 : next });
                                                                }}
                                                            />
                                                        </div>
                                                    </div>
                                                    <div className="flex gap-1 pt-2">
                                                        <Button
                                                            type="button"
                                                            variant={store.minPages === 0 && store.maxPages === 0 ? "default" : "outline"}
                                                            className="h-7 text-[10px] px-2"
                                                            onClick={() => store.resetPageRange()}
                                                        >
                                                            Auto
                                                        </Button>
                                                        <Button
                                                            type="button"
                                                            variant={store.minPages === 5 && store.maxPages === 8 ? "default" : "outline"}
                                                            className="h-7 text-[10px] px-2"
                                                            onClick={() => {
                                                                store.setEffortLevel(1);
                                                                store.setPageRange({ minPages: 5, maxPages: 8 });
                                                            }}
                                                        >
                                                            Curta
                                                        </Button>
                                                        <Button
                                                            type="button"
                                                            variant={store.minPages === 10 && store.maxPages === 15 ? "default" : "outline"}
                                                            className="h-7 text-[10px] px-2"
                                                            onClick={() => {
                                                                store.setEffortLevel(2);
                                                                store.setPageRange({ minPages: 10, maxPages: 15 });
                                                            }}
                                                        >
                                                            Média
                                                        </Button>
                                                        <Button
                                                            type="button"
                                                            variant={store.minPages === 20 && store.maxPages === 30 ? "default" : "outline"}
                                                            className="h-7 text-[10px] px-2"
                                                            onClick={() => {
                                                                store.setEffortLevel(3);
                                                                store.setPageRange({ minPages: 20, maxPages: 30 });
                                                            }}
                                                        >
	                                                            Longa
	                                                        </Button>
	                                                    </div>
	                                                    <p className="text-[10px] text-muted-foreground pt-1">
	                                                        Se vazio, usa o nível de rigor para estimar o tamanho.
	                                                    </p>
	                                                </div>

	                                                <div className="space-y-2 pt-2 border-t">
	                                                    <div className="flex items-center gap-1">
	                                                        <Label>Nível de rigor</Label>
	                                                        <TooltipProvider>
	                                                            <Tooltip>
	                                                                <TooltipTrigger>
	                                                                    <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
	                                                                </TooltipTrigger>
	                                                                <TooltipContent side="right" className="max-w-xs text-xs">
	                                                                    <p>
	                                                                        Backend: <span className="font-mono">effort_level</span> (1–5). Aumenta a insistência em
	                                                                        checagens e correções; pode elevar latência/custo.
	                                                                    </p>
	                                                                </TooltipContent>
	                                                            </Tooltip>
	                                                        </TooltipProvider>
	                                                    </div>
	                                                    <div className="flex items-center gap-1">
	                                                        {[1, 2, 3, 4, 5].map((level) => (
	                                                            <Button
	                                                                key={level}
	                                                                type="button"
	                                                                onClick={() => store.setEffortLevel(level)}
	                                                                className={cn(
	                                                                    "h-8 flex-1 rounded-md text-xs font-bold transition-all",
	                                                                    store.effortLevel >= level
	                                                                        ? "bg-indigo-600 text-white hover:bg-indigo-600"
	                                                                        : "bg-white text-indigo-300 border border-indigo-200/60 hover:bg-indigo-50"
	                                                                )}
	                                                                variant="outline"
	                                                            >
	                                                                {level}
	                                                            </Button>
	                                                        ))}
	                                                    </div>
	                                                </div>
	                                            </CardContent>
	                                        </Card>
	                                    </div>

	                                    <div>
	                                        <h3 className="text-sm font-semibold uppercase text-muted-foreground mb-4 flex items-center gap-2">
	                                            <TerminalSquare className="h-4 w-4" /> ⚡ Performance
	                                        </h3>
	                                        <Card>
	                                            <CardContent className="p-4 space-y-4">
	                                                <Accordion type="single" collapsible>
	                                                    <AccordionItem value="performance">
	                                                        <AccordionTrigger className="text-xs font-semibold">
	                                                            Ajustes avançados (latência × qualidade)
	                                                        </AccordionTrigger>
	                                                        <AccordionContent className="pt-3 space-y-4">
	                                                            <div className="space-y-2">
	                                                                <div className="flex items-center gap-1">
	                                                                    <Label className="text-xs">Nível de raciocínio</Label>
	                                                                    <TooltipProvider>
	                                                                        <Tooltip>
	                                                                            <TooltipTrigger>
	                                                                                <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
	                                                                            </TooltipTrigger>
	                                                                            <TooltipContent side="right" className="max-w-xs text-xs">
	                                                                                <p>
	                                                                                    Controla o <span className="font-mono">thinking_level</span> do workflow.
	                                                                                    Mais alto tende a melhorar consistência e correções, mas aumenta latência/custo.
	                                                                                </p>
	                                                                            </TooltipContent>
	                                                                        </Tooltip>
	                                                                    </TooltipProvider>
	                                                                </div>
	                                                                <div className="grid grid-cols-3 gap-2">
	                                                                    {[
	                                                                        { value: 'none', label: 'Nenhum' },
	                                                                        { value: 'minimal', label: 'Mínimo' },
	                                                                        { value: 'low', label: 'Baixo' },
	                                                                        { value: 'medium', label: 'Médio' },
	                                                                        { value: 'high', label: 'Alto' },
	                                                                        { value: 'xhigh', label: 'X‑Alto' },
	                                                                    ].map((opt) => (
	                                                                        <Button
	                                                                            key={opt.value}
	                                                                            type="button"
	                                                                            variant={store.reasoningLevel === (opt.value as any) ? "default" : "outline"}
	                                                                            className="h-7 text-[10px] px-2"
	                                                                            onClick={() => store.setReasoningLevel(opt.value as any)}
	                                                                        >
	                                                                            {opt.label}
	                                                                        </Button>
	                                                                    ))}
	                                                                </div>
	                                                            </div>

	                                                            <div className="space-y-2 pt-3 border-t">
	                                                                <div className="flex items-center gap-1">
	                                                                    <Label className="text-xs">Criatividade</Label>
	                                                                    <TooltipProvider>
	                                                                        <Tooltip>
	                                                                            <TooltipTrigger>
	                                                                                <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
	                                                                            </TooltipTrigger>
	                                                                            <TooltipContent side="right" className="max-w-xs text-xs">
	                                                                                <p>
	                                                                                    Presets de temperatura. Se ativar “temperatura custom”, ela sobrepõe este preset.
	                                                                                </p>
	                                                                            </TooltipContent>
	                                                                        </Tooltip>
	                                                                    </TooltipProvider>
	                                                                </div>
	                                                                <div className="flex gap-2">
	                                                                    {[
	                                                                        { value: 'rigoroso', label: 'Rigoroso' },
	                                                                        { value: 'padrao', label: 'Padrão' },
	                                                                        { value: 'criativo', label: 'Criativo' },
	                                                                    ].map((opt) => (
	                                                                        <Button
	                                                                            key={opt.value}
	                                                                            type="button"
	                                                                            variant={store.creativityMode === (opt.value as any) ? "default" : "outline"}
	                                                                            className="h-7 text-[10px] px-2 flex-1"
	                                                                            onClick={() => {
	                                                                                store.setCreativityMode(opt.value as any);
	                                                                                store.setTemperatureOverride(null);
	                                                                            }}
	                                                                        >
	                                                                            {opt.label}
	                                                                        </Button>
	                                                                    ))}
	                                                                </div>

	                                                                <div className="flex items-center justify-between text-[10px] text-muted-foreground">
	                                                                    <span>Temperatura efetiva</span>
	                                                                    <span className="font-mono">{effectiveTemperature.toFixed(2)}</span>
	                                                                </div>

	                                                                <div className="flex items-center justify-between pt-1">
	                                                                    <div className="flex items-center gap-1">
	                                                                        <Label className="text-[10px] text-muted-foreground">Temperatura custom</Label>
	                                                                        <TooltipProvider>
	                                                                            <Tooltip>
	                                                                                <TooltipTrigger>
	                                                                                    <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
	                                                                                </TooltipTrigger>
	                                                                                <TooltipContent side="right" className="max-w-xs text-xs">
	                                                                                    <p>
	                                                                                        Substitui o preset por um valor contínuo (0.0–1.0). Em geral:
	                                                                                        0.1–0.3 conservador; 0.4–0.7 mais variado.
	                                                                                    </p>
	                                                                                </TooltipContent>
	                                                                            </Tooltip>
	                                                                        </TooltipProvider>
	                                                                    </div>
	                                                                    <Switch
	                                                                        checked={store.temperatureOverride != null}
	                                                                        onCheckedChange={(enabled) => {
	                                                                            if (!enabled) store.setTemperatureOverride(null);
	                                                                            else store.setTemperatureOverride(effectiveTemperature);
	                                                                        }}
	                                                                    />
	                                                                </div>
	                                                                {store.temperatureOverride != null && (
	                                                                    <Slider
	                                                                        value={[store.temperatureOverride]}
	                                                                        onValueChange={([v]) => store.setTemperatureOverride(v)}
	                                                                        min={0}
	                                                                        max={1}
	                                                                        step={0.05}
	                                                                    />
	                                                                )}
	                                                            </div>

	                                                            <div className="space-y-3 pt-3 border-t">
	                                                                <div className="flex items-center justify-between">
	                                                                    <div className="space-y-0.5">
	                                                                        <div className="flex items-center gap-1">
	                                                                            <Label className="text-xs">Rodadas do comitê</Label>
	                                                                            <TooltipProvider>
	                                                                                <Tooltip>
	                                                                                    <TooltipTrigger>
	                                                                                        <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
	                                                                                    </TooltipTrigger>
	                                                                                    <TooltipContent side="right" className="max-w-xs text-xs">
	                                                                                        <p>
	                                                                                            Backend: <span className="font-mono">max_rounds</span>. Mais rodadas = mais
	                                                                                            debate/checagens; aumenta latência e custo.
	                                                                                        </p>
	                                                                                    </TooltipContent>
	                                                                                </Tooltip>
	                                                                            </TooltipProvider>
	                                                                        </div>
	                                                                        <p className="text-[10px] text-muted-foreground">
	                                                                            Auto segue o perfil (<span className="font-mono">{store.qualityProfile}</span>).
	                                                                        </p>
	                                                                    </div>
	                                                                    <Switch
	                                                                        checked={store.qualityMaxRounds != null}
	                                                                        onCheckedChange={(enabled) => {
	                                                                            if (!enabled) store.setQualityMaxRounds(null);
	                                                                            else store.setQualityMaxRounds(profileDefaults.maxRounds);
	                                                                        }}
	                                                                    />
	                                                                </div>
	                                                                {store.qualityMaxRounds != null && (
	                                                                    <div className="space-y-2">
	                                                                        <div className="flex justify-between items-center text-[10px]">
	                                                                            <span className="text-muted-foreground">max_rounds</span>
	                                                                            <span className="font-mono bg-muted px-1 rounded">{store.qualityMaxRounds}</span>
	                                                                        </div>
	                                                                        <Slider
	                                                                            value={[store.qualityMaxRounds]}
	                                                                            onValueChange={([v]) => store.setQualityMaxRounds(v)}
	                                                                            min={1}
	                                                                            max={6}
	                                                                            step={1}
	                                                                        />
	                                                                    </div>
	                                                                )}
	                                                            </div>

	                                                            <div className="space-y-3 pt-3 border-t">
	                                                                <div className="flex items-center justify-between">
	                                                                    <div className="space-y-0.5">
	                                                                        <div className="flex items-center gap-1">
	                                                                            <Label className="text-xs">Refinamentos finais</Label>
	                                                                            <TooltipProvider>
	                                                                                <Tooltip>
	                                                                                    <TooltipTrigger>
	                                                                                        <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
	                                                                                    </TooltipTrigger>
	                                                                                    <TooltipContent side="right" className="max-w-xs text-xs">
	                                                                                        <p>
	                                                                                            Backend: <span className="font-mono">max_final_review_loops</span>. Passagens finais
	                                                                                            de polimento (pós-comitê) antes do gate final.
	                                                                                        </p>
	                                                                                    </TooltipContent>
	                                                                                </Tooltip>
	                                                                            </TooltipProvider>
	                                                                        </div>
	                                                                        <p className="text-[10px] text-muted-foreground">
	                                                                            Auto tende a seguir <span className="font-mono">max_rounds</span> (limitado pelo plano).
	                                                                        </p>
	                                                                    </div>
	                                                                    <Switch
	                                                                        checked={store.qualityMaxFinalReviewLoops != null}
	                                                                        onCheckedChange={(enabled) => {
	                                                                            if (!enabled) store.setQualityMaxFinalReviewLoops(null);
	                                                                            else store.setQualityMaxFinalReviewLoops(profileDefaults.maxRounds);
	                                                                        }}
	                                                                    />
	                                                                </div>
	                                                                {store.qualityMaxFinalReviewLoops != null && (
	                                                                    <div className="space-y-2">
	                                                                        <div className="flex justify-between items-center text-[10px]">
	                                                                            <span className="text-muted-foreground">max_final_review_loops</span>
	                                                                            <span className="font-mono bg-muted px-1 rounded">{store.qualityMaxFinalReviewLoops}</span>
	                                                                        </div>
	                                                                        <Slider
	                                                                            value={[store.qualityMaxFinalReviewLoops]}
	                                                                            onValueChange={([v]) => store.setQualityMaxFinalReviewLoops(v)}
	                                                                            min={0}
	                                                                            max={6}
	                                                                            step={1}
	                                                                        />
	                                                                    </div>
	                                                                )}
	                                                            </div>
	                                                        </AccordionContent>
	                                                    </AccordionItem>
	                                                </Accordion>
	                                            </CardContent>
	                                        </Card>
	                                    </div>

	                                    <div>
	                                        <h3 className="text-sm font-semibold uppercase text-muted-foreground mb-4 flex items-center gap-2">
	                                            <Bot className="h-4 w-4" /> Agentes
	                                        </h3>
                                        <Card>
                                            <CardContent className="p-4 space-y-4">
	                                                <div className="flex items-center justify-between">
	                                                    <div className="space-y-0.5">
	                                                        <Label>Modo Agente</Label>
	                                                        <p className="text-[10px] text-muted-foreground">Minuta (Agentes)</p>
	                                                    </div>
	                                                    <Switch
	                                                        checked={store.useMultiAgent}
	                                                        onCheckedChange={(enabled) => {
	                                                            const nextEnabled = Boolean(enabled);
	                                                            const currentSelectedModel = store.selectedModel;
	                                                            store.setUseMultiAgent(nextEnabled);
	                                                            if (
	                                                                nextEnabled
	                                                                && currentSelectedModel
	                                                                && !agentChatModelOptions.some((m) => m.id === currentSelectedModel)
	                                                            ) {
	                                                                store.setSelectedModel('gemini-3-flash');
	                                                            }
	                                                        }}
	                                                    />
	                                                </div>

	                                                <div className="space-y-1">
	                                                    <div className="flex items-center gap-1">
	                                                        <Label className="text-[10px]">
	                                                            {store.useMultiAgent ? 'Modelo Juiz' : 'Modelo (modo rápido)'}
	                                                        </Label>
	                                                        <TooltipProvider>
	                                                            <Tooltip>
	                                                                <TooltipTrigger>
	                                                                    <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
	                                                                </TooltipTrigger>
	                                                                <TooltipContent side="right" className="max-w-xs text-xs">
	                                                                    {store.useMultiAgent ? (
	                                                                        <p>
	                                                                            Modelo “juiz” que consolida e decide no modo multi‑agente.
	                                                                            Dica: <span className="font-mono">gemini-3-flash</span> tende a ser mais rápido;
	                                                                            modelos mais “pesados” aumentam custo/latência.
	                                                                        </p>
	                                                                    ) : (
	                                                                        <p>
	                                                                            Modelo usado no modo rápido (um único modelo).
	                                                                            No modo agente, o “juiz” pode ser diferente e o comitê pode ter múltiplos modelos.
	                                                                        </p>
	                                                                    )}
	                                                                </TooltipContent>
	                                                            </Tooltip>
	                                                        </TooltipProvider>
	                                                    </div>
	                                                    <Select
	                                                        value={store.selectedModel}
	                                                        onValueChange={store.setSelectedModel}
	                                                    >
	                                                        <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
	                                                        <SelectContent>
	                                                            {(store.useMultiAgent ? agentChatModelOptions : baseChatModelOptions).map((m) => (
	                                                                <SelectItem key={m.id} value={m.id}>
	                                                                    {m.label}
	                                                                </SelectItem>
	                                                            ))}
	                                                        </SelectContent>
	                                                    </Select>
	                                                </div>

	                                                {store.useMultiAgent && (
	                                                    <div className="pt-2 space-y-3 animate-in fade-in zoom-in-95">
	                                                        <div className="space-y-1">
	                                                            <Label className="text-[10px]">Agente GPT</Label>
                                                            <Select value={store.gptModel} onValueChange={store.setGptModel}>
                                                                <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                                                                <SelectContent>
                                                                    <SelectItem value="gpt-5.2">GPT-5.2</SelectItem>
                                                                    <SelectItem value="gpt-4o">GPT-4o</SelectItem>
                                                                    <SelectItem value="gpt-5">GPT-5</SelectItem>
                                                                </SelectContent>
                                                            </Select>
                                                        </div>
	                                                        <div className="space-y-1">
	                                                            <Label className="text-[10px]">Agente Claude</Label>
	                                                            <Select value={store.claudeModel} onValueChange={store.setClaudeModel}>
	                                                                <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
	                                                                <SelectContent>
	                                                                    <SelectItem value="claude-4.5-sonnet">Claude 4.5 Sonnet</SelectItem>
	                                                                    <SelectItem value="claude-4.5-opus">Claude 4.5 Opus</SelectItem>
	                                                                </SelectContent>
	                                                            </Select>
	                                                        </div>

                                                            <Accordion type="single" collapsible className="w-full pt-2 border-t">
                                                                <AccordionItem value="committee-advanced" className="border-none">
                                                                    <AccordionTrigger className="py-2 text-xs">
                                                                        <div className="flex items-center gap-2">
                                                                            <span>Comitê (avançado)</span>
                                                                            <Badge variant="secondary" className="text-[10px]">
                                                                                Agentes no comitê: {committeeAgentsCount}
                                                                            </Badge>
                                                                        </div>
                                                                    </AccordionTrigger>
                                                                    <AccordionContent className="pt-2">
                                                                        <div className="space-y-3">
                                                                            <div className="text-[10px] text-muted-foreground">
                                                                                Controla quem participa da geração via LangGraph:
                                                                                <span className="font-mono"> drafter_models</span> e <span className="font-mono"> reviewer_models</span>.
                                                                                Deixe vazio para “Auto” (usa GPT + Claude + Juiz).
                                                                            </div>

                                                                            <div className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                                                                                <span className="rounded-full border bg-background px-2 py-0.5">
                                                                                    Juiz: {getModelLabel(store.selectedModel)}
                                                                                </span>
                                                                                <span className="rounded-full border bg-background px-2 py-0.5">
                                                                                    Estrategista: {getModelLabel(store.agentStrategistModel)}
                                                                                </span>
                                                                                <span className="rounded-full border bg-background px-2 py-0.5">
                                                                                    Limite: {MAX_ROLE_MODELS} modelos por papel
                                                                                </span>
                                                                            </div>

                                                                            <div className="space-y-1">
                                                                                <div className="flex items-center gap-1">
                                                                                    <Label className="text-[10px]">Estrategista (planejamento)</Label>
                                                                                    <TooltipProvider>
                                                                                        <Tooltip>
                                                                                            <TooltipTrigger>
                                                                                                <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
                                                                                            </TooltipTrigger>
                                                                                            <TooltipContent side="right" className="max-w-xs text-xs">
                                                                                                <p>
                                                                                                    Backend: <span className="font-mono">strategist_model</span>. Modelo que ajuda a
                                                                                                    planejar a estratégia antes da redação/revisão.
                                                                                                </p>
                                                                                            </TooltipContent>
                                                                                        </Tooltip>
                                                                                    </TooltipProvider>
                                                                                </div>
                                                                                <Select value={store.agentStrategistModel} onValueChange={store.setAgentStrategistModel}>
                                                                                    <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                                                                                    <SelectContent>
                                                                                        {agentModelOptions.map((m) => (
                                                                                            <SelectItem key={m.id} value={m.id}>
                                                                                                {m.label}
                                                                                            </SelectItem>
                                                                                        ))}
                                                                                    </SelectContent>
                                                                                </Select>
                                                                            </div>

                                                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                                                                <div className="space-y-2">
                                                                                    <div className="flex items-center justify-between">
                                                                                        <div className="flex items-center gap-1">
                                                                                            <Label className="text-[10px]">Redatores</Label>
                                                                                            <TooltipProvider>
                                                                                                <Tooltip>
                                                                                                    <TooltipTrigger>
                                                                                                        <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
                                                                                                    </TooltipTrigger>
                                                                                                    <TooltipContent side="right" className="max-w-xs text-xs">
                                                                                                        <p>
                                                                                                            Backend: <span className="font-mono">drafter_models</span>. Quem produz os
                                                                                                            rascunhos das seções. Vazio = auto (GPT + Claude + Juiz).
                                                                                                        </p>
                                                                                                    </TooltipContent>
                                                                                                </Tooltip>
                                                                                            </TooltipProvider>
                                                                                        </div>
                                                                                        <Button
                                                                                            type="button"
                                                                                            variant="ghost"
                                                                                            size="sm"
                                                                                            className="h-6 px-2 text-[10px]"
                                                                                            onClick={() => store.setAgentDrafterModels([])}
                                                                                        >
                                                                                            Auto
                                                                                        </Button>
                                                                                    </div>
                                                                                    <div className="rounded-md border bg-background p-2">
                                                                                        <ScrollArea className="h-40 pr-2">
                                                                                            <div className="space-y-2">
                                                                                                {agentModelOptions.map((model) => {
                                                                                                    const current = store.agentDrafterModels || [];
                                                                                                    const checked = current.includes(model.id);
                                                                                                    const disabled = !checked && current.length >= MAX_ROLE_MODELS;
                                                                                                    return (
                                                                                                        <div
                                                                                                            key={`drafter-${model.id}`}
                                                                                                            className={cn(
                                                                                                                "flex items-center space-x-2",
                                                                                                                disabled ? "opacity-60" : ""
                                                                                                            )}
                                                                                                        >
                                                                                                            <Checkbox
                                                                                                                id={`wiz-drafter-${model.id}`}
                                                                                                                checked={checked}
                                                                                                                disabled={disabled}
                                                                                                                onCheckedChange={() =>
                                                                                                                    toggleCommitteeRoleModel(
                                                                                                                        current,
                                                                                                                        model.id,
                                                                                                                        store.setAgentDrafterModels
                                                                                                                    )
                                                                                                                }
                                                                                                            />
                                                                                                            <Label htmlFor={`wiz-drafter-${model.id}`} className="text-[11px]">
                                                                                                                {model.label}
                                                                                                            </Label>
                                                                                                        </div>
                                                                                                    );
                                                                                                })}
                                                                                            </div>
                                                                                        </ScrollArea>
                                                                                    </div>
                                                                                </div>

                                                                                <div className="space-y-2">
                                                                                    <div className="flex items-center justify-between">
                                                                                        <div className="flex items-center gap-1">
                                                                                            <Label className="text-[10px]">Revisores</Label>
                                                                                            <TooltipProvider>
                                                                                                <Tooltip>
                                                                                                    <TooltipTrigger>
                                                                                                        <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
                                                                                                    </TooltipTrigger>
                                                                                                    <TooltipContent side="right" className="max-w-xs text-xs">
                                                                                                        <p>
                                                                                                            Backend: <span className="font-mono">reviewer_models</span>. Quem critica,
                                                                                                            aponta riscos e sugere melhorias. Vazio = usa os mesmos modelos dos redatores.
                                                                                                        </p>
                                                                                                    </TooltipContent>
                                                                                                </Tooltip>
                                                                                            </TooltipProvider>
                                                                                        </div>
                                                                                        <Button
                                                                                            type="button"
                                                                                            variant="ghost"
                                                                                            size="sm"
                                                                                            className="h-6 px-2 text-[10px]"
                                                                                            onClick={() => store.setAgentReviewerModels([])}
                                                                                        >
                                                                                            Auto
                                                                                        </Button>
                                                                                    </div>
                                                                                    <div className="rounded-md border bg-background p-2">
                                                                                        <ScrollArea className="h-40 pr-2">
                                                                                            <div className="space-y-2">
                                                                                                {agentModelOptions.map((model) => {
                                                                                                    const current = store.agentReviewerModels || [];
                                                                                                    const checked = current.includes(model.id);
                                                                                                    const disabled = !checked && current.length >= MAX_ROLE_MODELS;
                                                                                                    return (
                                                                                                        <div
                                                                                                            key={`reviewer-${model.id}`}
                                                                                                            className={cn(
                                                                                                                "flex items-center space-x-2",
                                                                                                                disabled ? "opacity-60" : ""
                                                                                                            )}
                                                                                                        >
                                                                                                            <Checkbox
                                                                                                                id={`wiz-reviewer-${model.id}`}
                                                                                                                checked={checked}
                                                                                                                disabled={disabled}
                                                                                                                onCheckedChange={() =>
                                                                                                                toggleCommitteeRoleModel(
                                                                                                                    current,
                                                                                                                    model.id,
                                                                                                                    store.setAgentReviewerModels
                                                                                                                )
                                                                                                                }
                                                                                                            />
                                                                                                            <Label htmlFor={`wiz-reviewer-${model.id}`} className="text-[11px]">
                                                                                                                {model.label}
                                                                                                            </Label>
                                                                                                        </div>
                                                                                                    );
                                                                                                })}
                                                                                            </div>
                                                                                        </ScrollArea>
                                                                                    </div>
                                                                                </div>
                                                                            </div>
                                                                        </div>
                                                                    </AccordionContent>
                                                                </AccordionItem>
                                                            </Accordion>
	                                                    </div>
	                                                )}
                                            </CardContent>
                                        </Card>
                                    </div>
                                </div>

                                {/* Column 2: RAG */}
                                <div className="space-y-6">
                                    <div className="flex items-center justify-between mb-4">
                                        <h3 className="text-sm font-semibold uppercase text-muted-foreground flex items-center gap-2">
                                            <FileText className="h-4 w-4" /> ② Pesquisa (RAG)
                                        </h3>
                                        <div className="flex items-center gap-2">
                                            <Label className="text-xs text-muted-foreground">Modo Básico</Label>
                                            <Switch checked={advancedMode} onCheckedChange={setAdvancedMode} />
                                            <Label className="text-xs text-muted-foreground">Modo Avançado</Label>
                                            <TooltipProvider>
                                                <Tooltip>
                                                    <TooltipTrigger>
                                                        <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                                                    </TooltipTrigger>
                                                    <TooltipContent side="right" className="max-w-xs text-xs">
                                                        <p>No modo básico você escolhe só as fontes. RAG básico busca trechos relevantes e responde com base neles. No modo avançado aparecem estratégias extras de recuperação. Passe o mouse nos ícones para detalhes técnicos.</p>
                                                    </TooltipContent>
                                                </Tooltip>
                                            </TooltipProvider>
                                        </div>
                                    </div>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        className="h-7 text-xs border-indigo-200 text-indigo-700 hover:bg-indigo-50"
                                        onClick={() => {
                                            // Preset Recomendado: Lei + Juris, Adaptive, CRAG, Top-K = 8
                                            store.setRagSources(['lei', 'juris']);
                                            store.setAdaptiveRouting(true);
                                            store.setCragGate(true);
                                            store.setRagTopK(8);
                                        }}
                                    >
                                        ⚡ Preset Recomendado
                                    </Button>
                                    <Card>
                                        <CardContent className="p-4 space-y-4">
                                            <div className="space-y-3">
                                                <div className="flex items-center gap-1">
                                                    <Label className="text-xs uppercase text-muted-foreground font-bold">Bases Jurídicas (Globais)</Label>
                                                    <TooltipProvider>
                                                        <Tooltip>
                                                            <TooltipTrigger><HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" /></TooltipTrigger>
                                                            <TooltipContent side="right" className="max-w-xs text-xs">
                                                                <p>Fontes para fundamentação: Leis, Jurisprudência e Modelos de peças. Use “Modelos” se quiser um estilo padrão.</p>
                                                            </TooltipContent>
                                                        </Tooltip>
                                                    </TooltipProvider>
                                                </div>
                                                <div className="space-y-2">
                                                    {['lei', 'juris', 'pecas_modelo'].map(source => (
                                                        <div key={source} className="flex items-center space-x-2">
                                                            <Checkbox
                                                                id={`wiz-source-${source}`}
                                                                checked={store.ragSources.includes(source)}
                                                                onCheckedChange={(checked) => {
                                                                    const current = store.ragSources;
                                                                    if (checked) store.setRagSources([...current, source]);
                                                                    else store.setRagSources(current.filter(s => s !== source));
                                                                }}
                                                            />
                                                            <Label htmlFor={`wiz-source-${source}`} className="text-sm">
                                                                {source === 'lei' ? 'Leis (legislação)' : source === 'juris' ? 'Jurisprudência' : 'Modelos de Peças'}
                                                            </Label>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>

                                            <div className="space-y-3 pt-2 border-t">
                                                <div className="flex justify-between items-center">
                                                    <div className="flex items-center gap-1">
                                                        <Label className="text-xs">Quantidade de Trechos (Top‑K)</Label>
                                                        <TooltipProvider>
                                                            <Tooltip>
                                                                <TooltipTrigger><HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" /></TooltipTrigger>
                                                                <TooltipContent side="right" className="max-w-xs text-xs">
                                                                    <p>Quantos trechos serão trazidos por seção. Mais trechos = mais contexto, mas pode aumentar ruído.</p>
                                                                </TooltipContent>
                                                            </Tooltip>
                                                        </TooltipProvider>
                                                    </div>
                                                    <span className="text-xs font-mono">{store.ragTopK}</span>
                                                </div>
                                                <Slider
                                                    value={[store.ragTopK]}
                                                    onValueChange={([v]) => store.setRagTopK(v)}
                                                    max={20} min={3} step={1}
                                                />
                                            </div>

                                            {store.ragSources.includes('pecas_modelo') && (
                                                <div className="pt-2 space-y-2 animate-in fade-in">
                                                    <Label className="text-[10px] text-blue-600 font-bold">Filtros de Modelos</Label>
                                                    <Input
                                                        placeholder="Área (Ex: Tributário)"
                                                        className="h-7 text-xs"
                                                        value={store.templateFilters.area}
                                                        onChange={e => store.setTemplateFilters({ area: e.target.value })}
                                                    />
                                                    <div className="flex items-center space-x-2">
                                                        <Switch
                                                            id="clause-bank"
                                                            checked={store.templateFilters.apenasClauseBank}
                                                            onCheckedChange={c => store.setTemplateFilters({ apenasClauseBank: c })}
                                                        />
                                                        <Label htmlFor="clause-bank" className="text-[10px]">Somente blocos prontos (Clause Bank)</Label>
                                                    </div>
                                                </div>
                                            )}
                                        </CardContent>
                                    </Card>

                                    {advancedMode && (
                                        <>
                                            <h3 className="text-sm font-semibold uppercase text-muted-foreground mb-4 mt-6 flex items-center gap-2">
                                                <Sparkles className="h-4 w-4 text-indigo-500" /> Ajustes Avançados de Busca
                                            </h3>
                                            <Card className="border-indigo-100 bg-indigo-50/20">
                                                <CardContent className="p-4 space-y-4">
                                                    <div className="flex items-center justify-between">
                                                        <div className="space-y-0.5">
                                                            <div className="flex items-center gap-1">
                                                                <Label className="text-xs font-semibold text-indigo-900">Estratégia automática</Label>
                                                                <TooltipProvider>
                                                                    <Tooltip>
                                                                        <TooltipTrigger><HelpCircle className="h-3 w-3 text-indigo-400 cursor-help" /></TooltipTrigger>
                                                                        <TooltipContent side="right" className="max-w-xs text-xs">
                                                                            <p>Nome técnico: Adaptive Routing. Escolhe automaticamente a melhor estratégia de busca para cada seção.</p>
                                                                        </TooltipContent>
                                                                    </Tooltip>
                                                                </TooltipProvider>
                                                            </div>
                                                            <p className="text-[10px] text-indigo-700">Recomendado para a maioria dos casos</p>
                                                        </div>
                                                        <Switch
                                                            checked={store.adaptiveRouting}
                                                            onCheckedChange={store.setAdaptiveRouting}
                                                        />
                                                    </div>

                                                    <div className="flex items-center justify-between border-t border-indigo-100 pt-3">
                                                        <div className="space-y-0.5">
                                                            <div className="flex items-center gap-1">
                                                                <Label className="text-xs font-semibold text-indigo-900">Rascunho inteligente</Label>
                                                                <TooltipProvider>
                                                                    <Tooltip>
                                                                        <TooltipTrigger><HelpCircle className="h-3 w-3 text-indigo-400 cursor-help" /></TooltipTrigger>
                                                                        <TooltipContent side="right" className="max-w-xs text-xs">
                                                                            <p>HyDE (Hypothetical Document Embeddings). Cria um rascunho para recuperar melhor quando o pedido é vago.</p>
                                                                        </TooltipContent>
                                                                    </Tooltip>
                                                                </TooltipProvider>
                                                            </div>
                                                            <p className="text-[10px] text-indigo-700">Ajuda quando o pedido é vago</p>
                                                        </div>
                                                        <Switch
                                                            checked={store.hydeEnabled}
                                                            onCheckedChange={store.setHydeEnabled}
                                                        />
                                                    </div>

                                                    <div className="flex items-center justify-between border-t border-indigo-100 pt-3">
                                                        <div className="space-y-0.5">
                                                            <div className="flex items-center gap-1">
                                                                <Label className="text-xs font-semibold text-indigo-900">Verificação extra</Label>
                                                                <TooltipProvider>
                                                                    <Tooltip>
                                                                        <TooltipTrigger><HelpCircle className="h-3 w-3 text-indigo-400 cursor-help" /></TooltipTrigger>
                                                                        <TooltipContent side="right" className="max-w-xs text-xs">
                                                                            <p>CRAG (Corrective RAG). Reavalia a qualidade das evidências antes de responder.</p>
                                                                        </TooltipContent>
                                                                    </Tooltip>
                                                                </TooltipProvider>
                                                            </div>
                                                            <p className="text-[10px] text-indigo-700">Checagem extra das fontes</p>
                                                        </div>
                                                        <Switch
                                                            checked={store.cragGate}
                                                            onCheckedChange={store.setCragGate}
                                                        />
                                                    </div>

                                                    <div className="space-y-3 border-t border-indigo-100 pt-3">
                                                        <div className="flex items-center justify-between">
                                                            <div className="space-y-0.5">
                                                                <div className="flex items-center gap-1">
                                                                    <Label className="text-xs font-semibold text-indigo-900">Relações entre fatos</Label>
                                                                    <TooltipProvider>
                                                                        <Tooltip>
                                                                            <TooltipTrigger><HelpCircle className="h-3 w-3 text-indigo-400 cursor-help" /></TooltipTrigger>
                                                                            <TooltipContent side="right" className="max-w-xs text-xs">
                                                                                <p>GraphRAG. Conecta documentos e conceitos relacionados para ampliar o contexto. Profundidade define os saltos nas relações.</p>
                                                                            </TooltipContent>
                                                                        </Tooltip>
                                                                    </TooltipProvider>
                                                                </div>
                                                                <p className="text-[10px] text-indigo-700">Conecta documentos e conceitos relacionados</p>
                                                            </div>
                                                            <Switch
                                                                checked={store.graphRagEnabled}
                                                                onCheckedChange={store.setGraphRagEnabled}
                                                            />
                                                        </div>
                                                        {store.graphRagEnabled && (
                                                            <div className="space-y-2 pt-1 animate-in slide-in-from-top-1">
                                                                <div className="flex justify-between items-center text-[10px]">
                                                                    <span className="text-indigo-600">Profundidade</span>
                                                                    <span className="font-mono bg-white px-1 rounded border">{store.graphHops}</span>
                                                                </div>
                                                                <Slider
                                                                    value={[store.graphHops]}
                                                                    onValueChange={([v]) => store.setGraphHops(v)}
                                                                    max={3} min={1} step={1}
                                                                    className="py-2"
                                                                />
                                                            </div>
                                                        )}
                                                    </div>
                                                </CardContent>
                                            </Card>
                                        </>
                                    )}
                                </div>

                                {/* Column 3: Audit & Extra */}
                                <div className="space-y-6">
                                    <h3 className="text-sm font-semibold uppercase text-muted-foreground mb-4 flex items-center gap-2">
                                        <Scale className="h-4 w-4" /> ③ Qualidade & Revisão
                                    </h3>
                                    <Card>
                                        <CardContent className="p-4 space-y-4">
                                            <div className="flex items-center justify-between p-2 rounded-lg bg-indigo-50 border border-indigo-100">
                                                <div className="space-y-0.5">
                                                    <Label className="text-indigo-900 font-bold">Auditoria Jurídica</Label>
                                                    <p className="text-[10px] text-indigo-700">Validação pós-geração</p>
                                                </div>
                                                <Switch
                                                    checked={store.audit}
                                                    onCheckedChange={store.setAudit}
                                                    className="data-[state=checked]:bg-indigo-600"
                                                />
                                            </div>

	                                            <div className="space-y-2 pt-2">
	                                                <Label className="text-xs">Formatação</Label>
	                                                <div className="grid grid-cols-1 gap-2">
	                                                    <div className="flex items-center space-x-2">
	                                                        <Checkbox
	                                                            checked={store.formattingOptions.includeToc}
	                                                            onCheckedChange={c => store.setFormattingOptions({ includeToc: !!c })}
	                                                        />
	                                                        <Label className="text-[10px]">Sumário (TOC)</Label>
	                                                    </div>
	                                                    <div className="flex items-center space-x-2">
	                                                        <Checkbox
	                                                            checked={store.formattingOptions.includeSummaries}
	                                                            onCheckedChange={c => store.setFormattingOptions({ includeSummaries: !!c })}
	                                                        />
	                                                        <Label className="text-[10px]">Resumos por Seção</Label>
	                                                    </div>
	                                                    <div className="flex items-center space-x-2">
	                                                        <Checkbox
	                                                            checked={store.formattingOptions.includeSummaryTable}
	                                                            onCheckedChange={c => store.setFormattingOptions({ includeSummaryTable: !!c })}
	                                                        />
	                                                        <Label className="text-[10px]">Tabela Síntese</Label>
	                                                    </div>
	                                                </div>
	                                            </div>

                                            <div className="space-y-2 pt-3 border-t">
                                                <Label className="text-xs uppercase text-muted-foreground font-bold">Estilo de Citação</Label>
                                                <p className="text-[10px] text-muted-foreground">
                                                    Autos permanecem no padrão forense <span className="font-mono">[TIPO - Doc. X, p. Y]</span>. ABNT aplica “Referências” e citação acadêmica quando cabível.
                                                </p>
	                                                <Select value={store.citationStyle} onValueChange={(v) => store.setCitationStyle(v as any)}>
	                                                    <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
	                                                    <SelectContent>
	                                                        <SelectItem value="forense">Forense (padrão)</SelectItem>
	                                                        <SelectItem value="hibrido">Híbrido (forense + referências ABNT)</SelectItem>
	                                                        <SelectItem value="abnt">ABNT (referências + citações acadêmicas)</SelectItem>
	                                                    </SelectContent>
	                                                </Select>
	                                            </div>

	                                            <div className="pt-3 border-t">
	                                                <Accordion type="single" collapsible>
	                                                    <AccordionItem value="quality-advanced">
	                                                        <AccordionTrigger className="text-xs font-semibold">
	                                                            Ajustes avançados de qualidade (gate/HIL)
	                                                        </AccordionTrigger>
	                                                        <AccordionContent className="pt-3 space-y-4">
	                                                            <div className="space-y-2">
	                                                                <div className="flex items-center gap-1">
	                                                                    <Label className="text-xs uppercase text-muted-foreground font-bold">Perfil de Qualidade</Label>
	                                                                    <TooltipProvider>
	                                                                        <Tooltip>
	                                                                            <TooltipTrigger>
	                                                                                <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
	                                                                            </TooltipTrigger>
	                                                                            <TooltipContent side="right" className="max-w-xs text-xs">
	                                                                                <p>
	                                                                                    Define presets (nota-alvo, rodadas e políticas). Os “overrides” abaixo
	                                                                                    substituem o perfil apenas para esta geração.
	                                                                                </p>
	                                                                            </TooltipContent>
	                                                                        </Tooltip>
	                                                                    </TooltipProvider>
	                                                                </div>
	                                                                <Select value={store.qualityProfile} onValueChange={(v) => store.setQualityProfile(v as any)}>
	                                                                    <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
	                                                                    <SelectContent>
	                                                                        <SelectItem value="rapido">Rápido (menos custo)</SelectItem>
	                                                                        <SelectItem value="padrao">Padrão (equilíbrio)</SelectItem>
	                                                                        <SelectItem value="rigoroso">Rigoroso (mais qualidade)</SelectItem>
	                                                                        <SelectItem value="auditoria">Auditoria (máximo rigor)</SelectItem>
	                                                                    </SelectContent>
		                                                                </Select>
		                                                            </div>

		                                                            <div className="space-y-3 pt-2 border-t">
		                                                                <div className="flex items-center justify-between">
		                                                                    <div className="space-y-0.5">
		                                                                        <div className="flex items-center gap-1">
		                                                                            <Label className="text-xs">Aprovar outline (HIL)</Label>
		                                                                            <TooltipProvider>
		                                                                                <Tooltip>
		                                                                                    <TooltipTrigger>
		                                                                                        <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
		                                                                                    </TooltipTrigger>
		                                                                                    <TooltipContent side="right" className="max-w-xs text-xs">
		                                                                                        <p>
		                                                                                            Backend: <span className="font-mono">hil_outline_enabled</span>. Pausa o fluxo para você
		                                                                                            aprovar/editar a outline antes de redigir as seções.
		                                                                                        </p>
		                                                                                    </TooltipContent>
		                                                                                </Tooltip>
		                                                                            </TooltipProvider>
		                                                                        </div>
		                                                                        <p className="text-[10px] text-muted-foreground">
		                                                                            Útil quando o intervalo de páginas é alto ou a peça é sensível.
		                                                                        </p>
		                                                                    </div>
		                                                                    <Switch
		                                                                        checked={store.hilOutlineEnabled}
		                                                                        onCheckedChange={store.setHilOutlineEnabled}
		                                                                    />
		                                                                </div>

		                                                                <div className="flex items-center justify-between">
		                                                                    <div className="space-y-0.5">
		                                                                        <div className="flex items-center gap-1">
		                                                                            <Label className="text-xs">Nunca interromper (auto‑aprovar HIL)</Label>
		                                                                            <TooltipProvider>
		                                                                                <Tooltip>
		                                                                                    <TooltipTrigger>
		                                                                                        <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
		                                                                                    </TooltipTrigger>
		                                                                                    <TooltipContent side="right" className="max-w-xs text-xs">
		                                                                                        <p>
		                                                                                            Backend: <span className="font-mono">auto_approve_hil</span>. Mantém os cálculos de HIL,
		                                                                                            mas não interrompe o workflow para aprovações manuais.
		                                                                                        </p>
		                                                                                    </TooltipContent>
		                                                                                </Tooltip>
		                                                                            </TooltipProvider>
		                                                                        </div>
		                                                                        <p className="text-[10px] text-muted-foreground">
		                                                                            Use quando você quer velocidade e aceita revisões automáticas.
		                                                                        </p>
		                                                                    </div>
		                                                                    <Switch
		                                                                        checked={store.autoApproveHil}
		                                                                        onCheckedChange={store.setAutoApproveHil}
		                                                                    />
		                                                                </div>
		                                                            </div>

		                                                            <div className="space-y-3 pt-2 border-t">
		                                                                <div className="flex items-center justify-between">
		                                                                    <div className="space-y-0.5">
		                                                                        <div className="flex items-center gap-1">
	                                                                            <Label className="text-xs">Nota mínima final</Label>
	                                                                            <TooltipProvider>
	                                                                                <Tooltip>
	                                                                                    <TooltipTrigger>
	                                                                                        <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
	                                                                                    </TooltipTrigger>
	                                                                                    <TooltipContent side="right" className="max-w-xs text-xs">
	                                                                                        <p>
	                                                                                            Backend: <span className="font-mono">target_final_score</span>. Se a nota final atingir
	                                                                                            esse valor, aprova automaticamente; abaixo disso, aumenta chance de correções/HIL.
	                                                                                        </p>
	                                                                                    </TooltipContent>
	                                                                                </Tooltip>
	                                                                            </TooltipProvider>
	                                                                        </div>
	                                                                        <p className="text-[10px] text-muted-foreground">Auto segue o perfil.</p>
	                                                                    </div>
	                                                                    <Switch
	                                                                        checked={store.qualityTargetFinalScore != null}
	                                                                        onCheckedChange={(enabled) => {
	                                                                            if (!enabled) store.setQualityTargetFinalScore(null);
	                                                                            else store.setQualityTargetFinalScore(profileDefaults.targetFinalScore);
	                                                                        }}
	                                                                    />
	                                                                </div>
	                                                                {store.qualityTargetFinalScore != null && (
	                                                                    <div className="space-y-2">
	                                                                        <div className="flex justify-between items-center text-[10px]">
	                                                                            <span className="text-muted-foreground">target_final_score</span>
	                                                                            <span className="font-mono bg-muted px-1 rounded">{store.qualityTargetFinalScore.toFixed(1)}</span>
	                                                                        </div>
	                                                                        <Slider
	                                                                            value={[store.qualityTargetFinalScore]}
	                                                                            onValueChange={([v]) => store.setQualityTargetFinalScore(Number(v.toFixed(1)))}
	                                                                            min={0}
	                                                                            max={10}
	                                                                            step={0.1}
	                                                                        />
	                                                                    </div>
	                                                                )}
	                                                            </div>

	                                                            <div className="space-y-3 pt-3 border-t">
	                                                                <div className="flex items-center justify-between">
	                                                                    <div className="space-y-0.5">
	                                                                        <div className="flex items-center gap-1">
	                                                                            <Label className="text-xs">Refino de estilo</Label>
	                                                                            <TooltipProvider>
	                                                                                <Tooltip>
	                                                                                    <TooltipTrigger>
	                                                                                        <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
	                                                                                    </TooltipTrigger>
	                                                                                    <TooltipContent side="right" className="max-w-xs text-xs">
	                                                                                        <p>
	                                                                                            Backend: <span className="font-mono">style_refine_max_rounds</span>. Número máximo de
	                                                                                            loops para ajustar tom/forma. Mais loops = mais polido, porém mais lento.
	                                                                                        </p>
	                                                                                    </TooltipContent>
	                                                                                </Tooltip>
	                                                                            </TooltipProvider>
	                                                                        </div>
	                                                                        <p className="text-[10px] text-muted-foreground">Auto segue o perfil.</p>
	                                                                    </div>
	                                                                    <Switch
	                                                                        checked={store.qualityStyleRefineMaxRounds != null}
	                                                                        onCheckedChange={(enabled) => {
	                                                                            if (!enabled) store.setQualityStyleRefineMaxRounds(null);
	                                                                            else store.setQualityStyleRefineMaxRounds(profileDefaults.styleRefineMaxRounds);
	                                                                        }}
	                                                                    />
	                                                                </div>
	                                                                {store.qualityStyleRefineMaxRounds != null && (
	                                                                    <div className="space-y-2">
	                                                                        <div className="flex justify-between items-center text-[10px]">
	                                                                            <span className="text-muted-foreground">style_refine_max_rounds</span>
	                                                                            <span className="font-mono bg-muted px-1 rounded">{store.qualityStyleRefineMaxRounds}</span>
	                                                                        </div>
	                                                                        <Slider
	                                                                            value={[store.qualityStyleRefineMaxRounds]}
	                                                                            onValueChange={([v]) => store.setQualityStyleRefineMaxRounds(v)}
	                                                                            min={0}
	                                                                            max={6}
	                                                                            step={1}
	                                                                        />
	                                                                    </div>
	                                                                )}
	                                                            </div>

	                                                            <div className="space-y-3 pt-3 border-t">
	                                                                <div className="flex items-center justify-between">
	                                                                    <div className="space-y-0.5">
	                                                                        <div className="flex items-center gap-1">
	                                                                            <Label className="text-xs">Rodadas de divergência (HIL)</Label>
	                                                                            <TooltipProvider>
	                                                                                <Tooltip>
	                                                                                    <TooltipTrigger>
	                                                                                        <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
	                                                                                    </TooltipTrigger>
	                                                                                    <TooltipContent side="right" className="max-w-xs text-xs">
	                                                                                        <p>
	                                                                                            Backend: <span className="font-mono">max_divergence_hil_rounds</span>. Limita quantas
	                                                                                            vezes o workflow volta para resolver divergências via revisão humana.
	                                                                                        </p>
	                                                                                    </TooltipContent>
	                                                                                </Tooltip>
	                                                                            </TooltipProvider>
	                                                                        </div>
	                                                                        <p className="text-[10px] text-muted-foreground">Auto usa 2 (se não configurado).</p>
	                                                                    </div>
	                                                                    <Switch
	                                                                        checked={store.maxDivergenceHilRounds != null}
	                                                                        onCheckedChange={(enabled) => {
	                                                                            if (!enabled) store.setMaxDivergenceHilRounds(null);
	                                                                            else store.setMaxDivergenceHilRounds(2);
	                                                                        }}
	                                                                    />
	                                                                </div>
	                                                                {store.maxDivergenceHilRounds != null && (
	                                                                    <div className="space-y-2">
	                                                                        <div className="flex justify-between items-center text-[10px]">
	                                                                            <span className="text-muted-foreground">max_divergence_hil_rounds</span>
	                                                                            <span className="font-mono bg-muted px-1 rounded">{store.maxDivergenceHilRounds}</span>
	                                                                        </div>
	                                                                        <Slider
	                                                                            value={[store.maxDivergenceHilRounds]}
	                                                                            onValueChange={([v]) => store.setMaxDivergenceHilRounds(v)}
	                                                                            min={1}
	                                                                            max={5}
	                                                                            step={1}
	                                                                        />
	                                                                    </div>
	                                                                )}
	                                                            </div>

	                                                            <div className="flex items-center justify-between pt-3 border-t">
	                                                                <div className="space-y-0.5">
	                                                                    <div className="flex items-center gap-1">
	                                                                        <Label className="text-xs">Debate granular</Label>
	                                                                        <TooltipProvider>
	                                                                            <Tooltip>
	                                                                                <TooltipTrigger>
	                                                                                    <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
	                                                                                </TooltipTrigger>
	                                                                                <TooltipContent side="right" className="max-w-xs text-xs">
	                                                                                    <p>
	                                                                                        Backend: <span className="font-mono">force_granular_debate</span>. Força o subgrafo
	                                                                                        granular em todas as seções. Útil para casos sensíveis/debug, mas aumenta latência.
	                                                                                    </p>
	                                                                                </TooltipContent>
	                                                                            </Tooltip>
	                                                                        </TooltipProvider>
	                                                                    </div>
	                                                                    <p className="text-[10px] text-muted-foreground">Mais rigor, mais lento.</p>
	                                                                </div>
		                                                                <Switch
		                                                                    checked={store.forceGranularDebate}
		                                                                    onCheckedChange={store.setForceGranularDebate}
		                                                                />
		                                                            </div>

		                                                            <div className="space-y-3 pt-3 border-t">
		                                                                <div className="flex items-center justify-between">
		                                                                    <div className="space-y-0.5">
		                                                                        <div className="flex items-center gap-1">
		                                                                            <Label className="text-xs">Ajustes finos</Label>
		                                                                            <TooltipProvider>
		                                                                                <Tooltip>
		                                                                                    <TooltipTrigger>
		                                                                                        <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
		                                                                                    </TooltipTrigger>
		                                                                                    <TooltipContent side="right" className="max-w-xs text-xs">
		                                                                                        <p>
		                                                                                            Controles adicionais inspirados no painel de <span className="font-mono">/minuta</span>.
		                                                                                            Deixe em “Auto” se não tiver certeza.
		                                                                                        </p>
		                                                                                    </TooltipContent>
		                                                                                </Tooltip>
		                                                                            </TooltipProvider>
		                                                                        </div>
		                                                                        <p className="text-[10px] text-muted-foreground">
		                                                                            Mostrar configurações avançadas do pipeline.
		                                                                        </p>
		                                                                    </div>
		                                                                    <Switch checked={showQualityDetails} onCheckedChange={setShowQualityDetails} />
		                                                                </div>

		                                                                {showQualityDetails && (
		                                                                    <div className="space-y-4 pt-1">
		                                                                        <div className="grid grid-cols-1 gap-3">
		                                                                            <div className="space-y-1">
		                                                                                <div className="flex items-center gap-1">
		                                                                                    <Label className="text-[10px] uppercase text-muted-foreground font-bold">Modo de auditoria</Label>
		                                                                                    <TooltipProvider>
		                                                                                        <Tooltip>
		                                                                                            <TooltipTrigger>
		                                                                                                <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
		                                                                                            </TooltipTrigger>
		                                                                                            <TooltipContent side="right" className="max-w-xs text-xs">
		                                                                                                <p>
		                                                                                                    <span className="font-mono">sei_only</span>: restringe a base aos autos/contexto local.
		                                                                                                    <span className="font-mono"> research</span>: permite enriquecimento/pesquisa (quando habilitada).
		                                                                                                </p>
		                                                                                            </TooltipContent>
		                                                                                        </Tooltip>
		                                                                                    </TooltipProvider>
		                                                                                </div>
		                                                                                <Select value={store.auditMode} onValueChange={(v) => store.setAuditMode(v as any)}>
		                                                                                    <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
		                                                                                    <SelectContent>
		                                                                                        <SelectItem value="sei_only">Somente base local</SelectItem>
		                                                                                        <SelectItem value="research">Pesquisa / Enriquecimento</SelectItem>
		                                                                                    </SelectContent>
		                                                                                </Select>
		                                                                            </div>

		                                                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
		                                                                                <div className="space-y-1">
		                                                                                    <div className="flex items-center gap-1">
		                                                                                        <Label className="text-[10px] uppercase text-muted-foreground font-bold">Meta por seção</Label>
		                                                                                        <TooltipProvider>
		                                                                                            <Tooltip>
		                                                                                                <TooltipTrigger>
		                                                                                                    <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
		                                                                                                </TooltipTrigger>
		                                                                                                <TooltipContent side="right" className="max-w-xs text-xs">
		                                                                                                    <p>
		                                                                                                        Backend: <span className="font-mono">target_section_score</span>. Quando definido,
		                                                                                                        o pipeline tenta elevar cada seção antes de aceitar.
		                                                                                                    </p>
		                                                                                                </TooltipContent>
		                                                                                            </Tooltip>
		                                                                                        </TooltipProvider>
		                                                                                    </div>
		                                                                                    <Input
		                                                                                        type="number"
		                                                                                        min={0}
		                                                                                        max={10}
		                                                                                        step={0.1}
		                                                                                        className="h-8 text-xs"
		                                                                                        placeholder="Auto (perfil)"
		                                                                                        value={store.qualityTargetSectionScore ?? ''}
		                                                                                        onChange={(e) => {
		                                                                                            const raw = String(e.target.value || '').trim();
		                                                                                            if (!raw) return store.setQualityTargetSectionScore(null);
		                                                                                            const parsed = Number(raw.replace(',', '.'));
		                                                                                            if (!Number.isFinite(parsed)) return;
		                                                                                            const clamped = Math.max(0, Math.min(10, parsed));
		                                                                                            store.setQualityTargetSectionScore(Number(clamped.toFixed(1)));
		                                                                                        }}
		                                                                                    />
		                                                                                </div>

		                                                                                <div className="space-y-1">
		                                                                                    <div className="flex items-center gap-1">
		                                                                                        <Label className="text-[10px] uppercase text-muted-foreground font-bold">Gate estrito</Label>
		                                                                                        <TooltipProvider>
		                                                                                            <Tooltip>
		                                                                                                <TooltipTrigger>
		                                                                                                    <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
		                                                                                                </TooltipTrigger>
		                                                                                                <TooltipContent side="right" className="max-w-xs text-xs">
		                                                                                                    <p>
		                                                                                                        Backend: <span className="font-mono">strict_document_gate</span>. Pode bloquear
		                                                                                                        a entrega se faltar item crítico no checklist.
		                                                                                                    </p>
		                                                                                                </TooltipContent>
		                                                                                            </Tooltip>
		                                                                                        </TooltipProvider>
		                                                                                    </div>
		                                                                                    <Select
		                                                                                        value={strictGateMode}
		                                                                                        onValueChange={(v) => {
		                                                                                            if (v === 'auto') store.setStrictDocumentGateOverride(null);
		                                                                                            else store.setStrictDocumentGateOverride(v === 'on');
		                                                                                        }}
		                                                                                    >
		                                                                                        <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
		                                                                                        <SelectContent>
		                                                                                            <SelectItem value="auto">Auto (perfil)</SelectItem>
		                                                                                            <SelectItem value="on">Ativar</SelectItem>
		                                                                                            <SelectItem value="off">Desativar</SelectItem>
		                                                                                        </SelectContent>
		                                                                                    </Select>
		                                                                                </div>
		                                                                            </div>

		                                                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
		                                                                                <div className="space-y-1">
		                                                                                    <div className="flex items-center gap-1">
		                                                                                        <Label className="text-[10px] uppercase text-muted-foreground font-bold">HIL por seção</Label>
		                                                                                        <TooltipProvider>
		                                                                                            <Tooltip>
		                                                                                                <TooltipTrigger>
		                                                                                                    <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
		                                                                                                </TooltipTrigger>
		                                                                                                <TooltipContent side="right" className="max-w-xs text-xs">
		                                                                                                    <p>
		                                                                                                        Backend: <span className="font-mono">hil_section_policy</span>. Controla se o HIL é
		                                                                                                        opcional/obrigatório (além das seções marcadas).
		                                                                                                    </p>
		                                                                                                </TooltipContent>
		                                                                                            </Tooltip>
		                                                                                        </TooltipProvider>
		                                                                                    </div>
		                                                                                    <Select
		                                                                                        value={hilSectionPolicyMode}
		                                                                                        onValueChange={(v) => {
		                                                                                            if (v === 'auto') store.setHilSectionPolicyOverride(null);
		                                                                                            else store.setHilSectionPolicyOverride(v as any);
		                                                                                        }}
		                                                                                    >
		                                                                                        <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
		                                                                                        <SelectContent>
		                                                                                            <SelectItem value="auto">Auto (perfil)</SelectItem>
		                                                                                            <SelectItem value="none">Desligado</SelectItem>
		                                                                                            <SelectItem value="optional">Opcional</SelectItem>
		                                                                                            <SelectItem value="required">Obrigatório</SelectItem>
		                                                                                        </SelectContent>
		                                                                                    </Select>
		                                                                                </div>

		                                                                                <div className="space-y-1">
		                                                                                    <div className="flex items-center gap-1">
		                                                                                        <Label className="text-[10px] uppercase text-muted-foreground font-bold">HIL final</Label>
		                                                                                        <TooltipProvider>
		                                                                                            <Tooltip>
		                                                                                                <TooltipTrigger>
		                                                                                                    <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
		                                                                                                </TooltipTrigger>
		                                                                                                <TooltipContent side="right" className="max-w-xs text-xs">
		                                                                                                    <p>
		                                                                                                        Backend: <span className="font-mono">hil_final_required</span>. Controla se há
		                                                                                                        aprovação humana antes de finalizar.
		                                                                                                    </p>
		                                                                                                </TooltipContent>
		                                                                                            </Tooltip>
		                                                                                        </TooltipProvider>
		                                                                                    </div>
		                                                                                    <Select
		                                                                                        value={hilFinalRequiredMode}
		                                                                                        onValueChange={(v) => {
		                                                                                            if (v === 'auto') store.setHilFinalRequiredOverride(null);
		                                                                                            else store.setHilFinalRequiredOverride(v === 'on');
		                                                                                        }}
		                                                                                    >
		                                                                                        <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
		                                                                                        <SelectContent>
		                                                                                            <SelectItem value="auto">Auto (perfil)</SelectItem>
		                                                                                            <SelectItem value="on">Exigir</SelectItem>
		                                                                                            <SelectItem value="off">Não exigir</SelectItem>
		                                                                                        </SelectContent>
		                                                                                    </Select>
		                                                                                </div>
		                                                                            </div>

		                                                                            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
		                                                                                <div className="space-y-1">
		                                                                                    <Label className="text-[10px] uppercase text-muted-foreground font-bold">Tentativas de pesquisa</Label>
		                                                                                    <Input
		                                                                                        type="number"
		                                                                                        min={0}
		                                                                                        max={5}
		                                                                                        step={1}
		                                                                                        className="h-8 text-xs"
		                                                                                        placeholder="Auto (perfil)"
		                                                                                        value={store.qualityMaxResearchVerifierAttempts ?? ''}
		                                                                                        onChange={(e) => {
		                                                                                            const raw = String(e.target.value || '').trim();
		                                                                                            if (!raw) return store.setQualityMaxResearchVerifierAttempts(null);
		                                                                                            const parsed = Number(raw);
		                                                                                            if (!Number.isFinite(parsed)) return;
		                                                                                            store.setQualityMaxResearchVerifierAttempts(Math.max(0, Math.min(5, Math.floor(parsed))));
		                                                                                        }}
		                                                                                    />
		                                                                                </div>

		                                                                                <div className="space-y-1">
		                                                                                    <Label className="text-[10px] uppercase text-muted-foreground font-bold">Retentativas no RAG</Label>
		                                                                                    <Input
		                                                                                        type="number"
		                                                                                        min={0}
		                                                                                        max={5}
		                                                                                        step={1}
		                                                                                        className="h-8 text-xs"
		                                                                                        placeholder="Auto (perfil)"
		                                                                                        value={store.qualityMaxRagRetries ?? ''}
		                                                                                        onChange={(e) => {
		                                                                                            const raw = String(e.target.value || '').trim();
		                                                                                            if (!raw) return store.setQualityMaxRagRetries(null);
		                                                                                            const parsed = Number(raw);
		                                                                                            if (!Number.isFinite(parsed)) return;
		                                                                                            store.setQualityMaxRagRetries(Math.max(0, Math.min(5, Math.floor(parsed))));
		                                                                                        }}
		                                                                                    />
		                                                                                </div>

		                                                                                <div className="space-y-1">
		                                                                                    <div className="flex items-center gap-1">
		                                                                                        <Label className="text-[10px] uppercase text-muted-foreground font-bold">Expandir fontes</Label>
		                                                                                        <TooltipProvider>
		                                                                                            <Tooltip>
		                                                                                                <TooltipTrigger>
		                                                                                                    <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
		                                                                                                </TooltipTrigger>
		                                                                                                <TooltipContent side="right" className="max-w-xs text-xs">
		                                                                                                    <p>
		                                                                                                        Backend: <span className="font-mono">rag_retry_expand_scope</span>. Se não achar prova
		                                                                                                        nos autos, permite expandir para bases globais. Depende de modo de auditoria.
		                                                                                                    </p>
		                                                                                                </TooltipContent>
		                                                                                            </Tooltip>
		                                                                                        </TooltipProvider>
		                                                                                    </div>
		                                                                                    <Select
		                                                                                        value={expandScopeMode}
		                                                                                        onValueChange={(v) => {
		                                                                                            if (v === 'auto') store.setQualityRagRetryExpandScope(null);
		                                                                                            else store.setQualityRagRetryExpandScope(v === 'on');
		                                                                                        }}
		                                                                                    >
		                                                                                        <SelectTrigger className="h-8 text-xs" disabled={!canWebSearch}>
		                                                                                            <SelectValue />
		                                                                                        </SelectTrigger>
		                                                                                        <SelectContent>
		                                                                                            <SelectItem value="auto">Auto (perfil)</SelectItem>
		                                                                                            <SelectItem value="on">Permitir</SelectItem>
		                                                                                            <SelectItem value="off">Bloquear</SelectItem>
		                                                                                        </SelectContent>
		                                                                                    </Select>
		                                                                                    {!canWebSearch && (
		                                                                                        <div className="text-[10px] text-muted-foreground">
		                                                                                            Bloqueado em <span className="font-mono">sei_only</span>.
		                                                                                        </div>
		                                                                                    )}
		                                                                                </div>
		                                                                            </div>

		                                                                            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
		                                                                                <div className="space-y-1">
		                                                                                    <Label className="text-[10px] uppercase text-muted-foreground font-bold">CRAG (melhor fonte)</Label>
		                                                                                    <Input
		                                                                                        type="number"
		                                                                                        min={0}
		                                                                                        max={1}
		                                                                                        step={0.05}
		                                                                                        className="h-8 text-xs"
		                                                                                        placeholder="Auto (perfil)"
		                                                                                        value={store.cragMinBestScoreOverride ?? ''}
		                                                                                        disabled={!store.cragGate}
		                                                                                        onChange={(e) => {
		                                                                                            const raw = String(e.target.value || '').trim();
		                                                                                            if (!raw) return store.setCragMinBestScoreOverride(null);
		                                                                                            const parsed = Number(raw.replace(',', '.'));
		                                                                                            if (!Number.isFinite(parsed)) return;
		                                                                                            store.setCragMinBestScoreOverride(Math.max(0, Math.min(1, parsed)));
		                                                                                        }}
		                                                                                    />
		                                                                                    {!store.cragGate && (
		                                                                                        <div className="text-[10px] text-muted-foreground">Ative o CRAG para usar.</div>
		                                                                                    )}
		                                                                                </div>

		                                                                                <div className="space-y-1">
		                                                                                    <Label className="text-[10px] uppercase text-muted-foreground font-bold">CRAG (média top 3)</Label>
		                                                                                    <Input
		                                                                                        type="number"
		                                                                                        min={0}
		                                                                                        max={1}
		                                                                                        step={0.05}
		                                                                                        className="h-8 text-xs"
		                                                                                        placeholder="Auto (perfil)"
		                                                                                        value={store.cragMinAvgScoreOverride ?? ''}
		                                                                                        disabled={!store.cragGate}
		                                                                                        onChange={(e) => {
		                                                                                            const raw = String(e.target.value || '').trim();
		                                                                                            if (!raw) return store.setCragMinAvgScoreOverride(null);
		                                                                                            const parsed = Number(raw.replace(',', '.'));
		                                                                                            if (!Number.isFinite(parsed)) return;
		                                                                                            store.setCragMinAvgScoreOverride(Math.max(0, Math.min(1, parsed)));
		                                                                                        }}
		                                                                                    />
		                                                                                    {!store.cragGate && (
		                                                                                        <div className="text-[10px] text-muted-foreground">Ative o CRAG para usar.</div>
		                                                                                    )}
		                                                                                </div>

		                                                                                <div className="space-y-1">
		                                                                                    <Label className="text-[10px] uppercase text-muted-foreground font-bold">Limite de recursão</Label>
		                                                                                    <Input
		                                                                                        type="number"
		                                                                                        min={20}
		                                                                                        max={500}
		                                                                                        step={10}
		                                                                                        className="h-8 text-xs"
		                                                                                        placeholder="Auto (perfil)"
		                                                                                        value={store.recursionLimitOverride ?? ''}
		                                                                                        onChange={(e) => {
		                                                                                            const raw = String(e.target.value || '').trim();
		                                                                                            if (!raw) return store.setRecursionLimitOverride(null);
		                                                                                            const parsed = Number(raw);
		                                                                                            if (!Number.isFinite(parsed)) return;
		                                                                                            store.setRecursionLimitOverride(Math.max(20, Math.min(500, Math.floor(parsed))));
		                                                                                        }}
		                                                                                    />
		                                                                                </div>
			                                                                            </div>

			                                                                            <div className="space-y-2 pt-2 border-t">
			                                                                                <div className="space-y-1">
			                                                                                    <div className="flex items-center gap-1">
			                                                                                        <Label className="text-xs">Pesquisa</Label>
			                                                                                        <TooltipProvider>
			                                                                                            <Tooltip>
			                                                                                                <TooltipTrigger>
			                                                                                                    <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
			                                                                                                </TooltipTrigger>
			                                                                                                <TooltipContent side="right" className="max-w-xs text-xs">
			                                                                                                    <p>
			                                                                                                        Backend: <span className="font-mono">research_policy</span>. “Auto” deixa o
			                                                                                                        workflow decidir quando usar Web/Deep Research. “Manual” respeita apenas os
			                                                                                                        toggles abaixo.
			                                                                                                    </p>
			                                                                                                </TooltipContent>
			                                                                                            </Tooltip>
			                                                                                        </TooltipProvider>
			                                                                                    </div>
			                                                                                    <div className="flex gap-2">
			                                                                                        <Button
			                                                                                            type="button"
			                                                                                            variant={store.researchPolicy === 'auto' ? 'default' : 'outline'}
			                                                                                            className="h-7 text-[10px] px-2 flex-1"
			                                                                                            onClick={() => store.setResearchPolicy('auto')}
			                                                                                        >
			                                                                                            Auto
			                                                                                        </Button>
			                                                                                        <Button
			                                                                                            type="button"
			                                                                                            variant={store.researchPolicy === 'force' ? 'default' : 'outline'}
			                                                                                            className="h-7 text-[10px] px-2 flex-1"
			                                                                                            onClick={() => store.setResearchPolicy('force')}
			                                                                                        >
			                                                                                            Manual
			                                                                                        </Button>
			                                                                                    </div>
			                                                                                </div>

			                                                                                <div className="space-y-2 pt-2">
			                                                                                <div className="flex items-center justify-between">
			                                                                                    <div className="space-y-0.5">
			                                                                                        <Label className="text-xs">Pesquisa na web</Label>
			                                                                                        <div className="text-[10px] text-muted-foreground">
		                                                                                            Requer <span className="font-mono">audit_mode=research</span>.
		                                                                                        </div>
		                                                                                    </div>
		                                                                                    <Switch
		                                                                                        checked={store.webSearch}
		                                                                                        onCheckedChange={store.setWebSearch}
		                                                                                        disabled={!canWebSearch}
		                                                                                    />
		                                                                                </div>
			                                                                                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
			                                                                                    <div className="space-y-1">
			                                                                                        <Label className="text-[10px] uppercase text-muted-foreground font-bold">Modo de busca</Label>
			                                                                                        <Select
			                                                                                            value={store.searchMode}
			                                                                                            onValueChange={(v) => store.setSearchMode(v as any)}
			                                                                                        >
			                                                                                            <SelectTrigger className="h-8 text-xs" disabled={!store.webSearch || !canWebSearch}>
			                                                                                                <SelectValue />
			                                                                                            </SelectTrigger>
				                                                                                            <SelectContent>
				                                                                                                <SelectItem value="shared">Compartilhada</SelectItem>
				                                                                                                <SelectItem value="native">Nativa por modelo</SelectItem>
				                                                                                                <SelectItem value="hybrid">Híbrida</SelectItem>
				                                                                                                <SelectItem value="perplexity">Perplexity</SelectItem>
				                                                                                            </SelectContent>
				                                                                                        </Select>
				                                                                                    </div>
		                                                                                    <div className="space-y-1">
		                                                                                        <Label className="text-[10px] uppercase text-muted-foreground font-bold">Estratégia</Label>
		                                                                                        <div className="flex items-center gap-2 h-8">
		                                                                                            <label className="flex items-center gap-2 text-[10px] text-muted-foreground">
		                                                                                                <Checkbox
		                                                                                                    checked={store.multiQuery}
		                                                                                                    onCheckedChange={(c) => store.setMultiQuery(!!c)}
		                                                                                                    disabled={!store.webSearch || !canWebSearch}
		                                                                                                />
		                                                                                                Multi‑query
		                                                                                            </label>
		                                                                                            <label className="flex items-center gap-2 text-[10px] text-muted-foreground">
		                                                                                                <Checkbox
		                                                                                                    checked={store.breadthFirst}
		                                                                                                    onCheckedChange={(c) => store.setBreadthFirst(!!c)}
		                                                                                                    disabled={!store.webSearch || !canWebSearch}
		                                                                                                />
		                                                                                                Breadth‑first
		                                                                                            </label>
		                                                                                        </div>
				                                                                                    </div>
				                                                                                </div>

				                                                                                <div className="space-y-1 pt-2">
				                                                                                    <div className="flex items-center gap-1">
				                                                                                        <Label className="text-[10px] uppercase text-muted-foreground font-bold">Modelo de pesquisa (LangGraph)</Label>
				                                                                                        <TooltipProvider>
				                                                                                            <Tooltip>
				                                                                                                <TooltipTrigger>
				                                                                                                    <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
				                                                                                                </TooltipTrigger>
				                                                                                                <TooltipContent side="right" className="max-w-xs text-xs">
				                                                                                                    <p>
				                                                                                                        Backend: <span className="font-mono">web_search_model</span>. “Auto” escolhe o
				                                                                                                        melhor disponível. Você pode fixar um modelo específico para estabilidade de
				                                                                                                        resultado/custo.
				                                                                                                    </p>
				                                                                                                </TooltipContent>
				                                                                                            </Tooltip>
				                                                                                        </TooltipProvider>
				                                                                                    </div>
				                                                                                    <Select
				                                                                                        value={store.webSearchModel}
				                                                                                        onValueChange={store.setWebSearchModel}
				                                                                                    >
				                                                                                        <SelectTrigger className="h-8 text-xs" disabled={!store.webSearch || !canWebSearch}>
				                                                                                            <SelectValue />
				                                                                                        </SelectTrigger>
				                                                                                        <SelectContent>
				                                                                                            <SelectItem value="auto">Auto</SelectItem>
				                                                                                            {webSearchModelOptions.map((m) => (
				                                                                                                <SelectItem key={m.id} value={m.id}>
				                                                                                                    {m.label}
				                                                                                                </SelectItem>
				                                                                                            ))}
				                                                                                        </SelectContent>
				                                                                                    </Select>
				                                                                                </div>
				                                                                            </div>

				                                                                            <div className="space-y-2 pt-2 border-t">
				                                                                                <div className="flex items-center justify-between">
			                                                                                    <div className="space-y-0.5">
			                                                                                        <div className="flex items-center gap-1">
			                                                                                            <Label className="text-xs">Deep Research</Label>
			                                                                                            <TooltipProvider>
			                                                                                                <Tooltip>
			                                                                                                    <TooltipTrigger>
			                                                                                                        <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
			                                                                                                    </TooltipTrigger>
			                                                                                                    <TooltipContent side="right" className="max-w-xs text-xs">
			                                                                                                        <p>
			                                                                                                            Backend: <span className="font-mono">dense_research</span>. Pesquisa mais profunda e
			                                                                                                            demorada (maior cobertura). Requer <span className="font-mono">audit_mode=research</span>.
			                                                                                                        </p>
			                                                                                                    </TooltipContent>
			                                                                                                </Tooltip>
			                                                                                            </TooltipProvider>
			                                                                                        </div>
			                                                                                        <div className="text-[10px] text-muted-foreground">Mais cobertura; mais custo/latência.</div>
			                                                                                    </div>
			                                                                                    <Switch
			                                                                                        checked={store.denseResearch}
			                                                                                        onCheckedChange={store.setDenseResearch}
			                                                                                        disabled={!canWebSearch}
			                                                                                    />
			                                                                                </div>

			                                                                                <div className={cn("space-y-2", (!store.denseResearch || !canWebSearch) && "opacity-60 pointer-events-none")}>
			                                                                                    <div className="space-y-1">
			                                                                                        <div className="flex items-center gap-1">
			                                                                                            <Label className="text-[10px] uppercase text-muted-foreground font-bold">Backend do Deep Research</Label>
			                                                                                            <TooltipProvider>
			                                                                                                <Tooltip>
			                                                                                                    <TooltipTrigger>
			                                                                                                        <HelpCircle className="h-3 w-3 text-muted-foreground cursor-help" />
			                                                                                                    </TooltipTrigger>
			                                                                                                    <TooltipContent side="right" className="max-w-xs text-xs">
			                                                                                                        <p>
			                                                                                                            Backend: <span className="font-mono">deep_research_provider</span>. “Google” tende a
			                                                                                                            funcionar melhor como agente no LangGraph; “Perplexity” é útil quando você quer o
			                                                                                                            stack Sonar.
			                                                                                                        </p>
			                                                                                                    </TooltipContent>
			                                                                                                </Tooltip>
			                                                                                            </TooltipProvider>
			                                                                                        </div>
			                                                                                        <div className="flex gap-2">
			                                                                                            <Button
			                                                                                                type="button"
			                                                                                                variant={store.deepResearchProvider === 'auto' ? 'default' : 'outline'}
			                                                                                                className="h-7 text-[10px] px-2 flex-1"
			                                                                                                onClick={() => store.setDeepResearchProvider('auto')}
			                                                                                            >
			                                                                                                Auto
			                                                                                            </Button>
			                                                                                            <Button
			                                                                                                type="button"
			                                                                                                variant={store.deepResearchProvider === 'google' ? 'default' : 'outline'}
			                                                                                                className="h-7 text-[10px] px-2 flex-1"
			                                                                                                onClick={() => store.setDeepResearchProvider('google')}
			                                                                                            >
			                                                                                                Google
			                                                                                            </Button>
			                                                                                            <Button
			                                                                                                type="button"
			                                                                                                variant={store.deepResearchProvider === 'perplexity' ? 'default' : 'outline'}
			                                                                                                className="h-7 text-[10px] px-2 flex-1"
			                                                                                                onClick={() => store.setDeepResearchProvider('perplexity')}
			                                                                                            >
			                                                                                                Perplexity
			                                                                                            </Button>
			                                                                                        </div>
			                                                                                    </div>

			                                                                                    {store.deepResearchProvider === 'perplexity' && (
			                                                                                        <div className="space-y-1">
			                                                                                            <Label className="text-[10px] uppercase text-muted-foreground font-bold">Modelo (Perplexity Deep Research)</Label>
			                                                                                            <div className="flex gap-2">
			                                                                                                <Button
			                                                                                                    type="button"
			                                                                                                    variant="outline"
			                                                                                                    className="h-7 text-[10px] px-2"
			                                                                                                    onClick={() => store.setDeepResearchModel('sonar-deep-research')}
			                                                                                                >
			                                                                                                    Sonar Deep Research
			                                                                                                </Button>
			                                                                                            </div>
			                                                                                            <div className="text-[10px] text-muted-foreground">
			                                                                                                Dica: para atuar como agente, prefira <span className="font-semibold">Google</span>.
			                                                                                            </div>
			                                                                                        </div>
			                                                                                    )}
			                                                                                </div>
			                                                                            </div>

			                                                                            <div className="space-y-2 pt-2 border-t">
			                                                                                <Label className="text-xs uppercase text-muted-foreground font-bold">Checklist complementar</Label>
			                                                                                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
		                                                                                    <div className="space-y-1">
		                                                                                        <Label className="text-[10px] text-rose-600/80 font-bold">Críticos</Label>
		                                                                                        <Textarea
		                                                                                            value={criticalChecklistText}
		                                                                                            onChange={(e) => {
		                                                                                                const next = e.target.value;
		                                                                                                setCriticalChecklistText(next);
		                                                                                                updateDocumentChecklist(next, nonCriticalChecklistText);
		                                                                                            }}
		                                                                                            placeholder={"Ex.: Procuração\nContrato\nAta de licitação"}
		                                                                                            className="min-h-[80px] text-xs"
		                                                                                        />
		                                                                                    </div>
		                                                                                    <div className="space-y-1">
		                                                                                        <Label className="text-[10px] text-muted-foreground font-bold">Não críticos</Label>
		                                                                                        <Textarea
		                                                                                            value={nonCriticalChecklistText}
		                                                                                            onChange={(e) => {
		                                                                                                const next = e.target.value;
		                                                                                                setNonCriticalChecklistText(next);
		                                                                                                updateDocumentChecklist(criticalChecklistText, next);
		                                                                                            }}
		                                                                                            placeholder={"Ex.: Endereçamento\nPedidos alternativos"}
		                                                                                            className="min-h-[80px] text-xs"
		                                                                                        />
		                                                                                    </div>
		                                                                                </div>
		                                                                            </div>
		                                                                        </div>
		                                                                    </div>
		                                                                </div>
		                                                                )}
		                                                            </div>
		                                                        </AccordionContent>
		                                                    </AccordionItem>
		                                                </Accordion>
		                                            </div>

	                                            {/* Section-level HIL */}
	                                            <div className="space-y-2 pt-3 border-t">
	                                                <Label className="text-xs uppercase text-muted-foreground font-bold">Revisão Humana por Seção (HIL)</Label>
	                                                <p className="text-[10px] text-muted-foreground">
	                                                    Se marcado, o workflow vai pausar para você aprovar/editar seções específicas antes de continuar.
	                                                </p>
	                                                {(() => {
	                                                    const outlineReal = (store.jobOutline || []).map((t: any) => String(t).trim()).filter(Boolean);
	                                                    const customTemplate = String(store.minutaOutlineTemplate || '')
	                                                        .split('\n')
	                                                        .map((s) => s.trim())
	                                                        .filter(Boolean);
		                                                    const template = customTemplate.length > 0 ? customTemplate : [
		                                                        "I - DOS FATOS",
		                                                        "II - DO DIREITO",
		                                                        "III - DOS PEDIDOS"
		                                                    ];
		                                                    const outline = outlineReal.length > 0 ? outlineReal : template;
		                                                    const sourceLabel = outlineReal.length > 0 ? "Outline real" : "Template (base)";

	                                                    const selected = new Set(store.hilTargetSections || []);
	                                                    return (
	                                                        <div className="space-y-2">
	                                                            <div className="text-[10px] text-muted-foreground">{sourceLabel}</div>
		                                                            {outline.map((title) => (
                                                                <div key={title} className="flex items-center space-x-2">
                                                                    <Checkbox
                                                                        checked={selected.has(title)}
                                                                        onCheckedChange={(checked) => {
                                                                            const next = new Set(selected);
                                                                            if (checked) next.add(title);
                                                                            else next.delete(title);
                                                                            store.setHilTargetSections(Array.from(next));
                                                                        }}
                                                                    />
                                                                    <Label className="text-[11px]">{title}</Label>
	                                                                </div>
		                                                            ))}
		                                                            <div className="pt-2 space-y-1">
		                                                                <div className="flex items-center justify-between gap-2">
		                                                                    <Label className="text-[10px] uppercase text-muted-foreground font-bold">
		                                                                        ESTRUTURA BASE (FALLBACK) — CUSTOMIZÁVEL
		                                                                    </Label>
		                                                                    <Button
		                                                                        type="button"
		                                                                        variant="ghost"
	                                                                        size="sm"
	                                                                        className="h-7 px-2 text-[10px]"
	                                                                        onClick={() => store.setMinutaOutlineTemplate([
	                                                                            'I - DOS FATOS',
	                                                                            'II - DO DIREITO',
	                                                                            'III - DOS PEDIDOS',
	                                                                        ].join('\n'))}
	                                                                    >
	                                                                        Restaurar padrão
	                                                                    </Button>
		                                                                </div>
		                                                                <p className="text-[10px] text-muted-foreground">
		                                                                    Usada quando não há template por tipo, ou quando o template do tipo inclui {"{{BASE}}"}.
		                                                                </p>
	                                                                <Textarea
	                                                                    value={store.minutaOutlineTemplate || ''}
	                                                                    onChange={(e) => store.setMinutaOutlineTemplate(e.target.value)}
	                                                                    className="min-h-[90px] text-[11px]"
	                                                                    placeholder={"I - DOS FATOS\nII - DO DIREITO\nIII - DOS PEDIDOS"}
	                                                                />
	                                                            </div>
	                                                        </div>
	                                                    );
	                                                })()}
	                                            </div>
                                        </CardContent>
                                    </Card>
                                </div>
                            </div>

                            <div className="flex justify-between pt-6 border-t">
                                <Button variant="ghost" onClick={prevStep}>Voltar</Button>
                                <Button
                                    onClick={handleStartGeneration}
                                    disabled={loading}
                                    className="pl-8 pr-6 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 text-white shadow-md"
                                >
                                    {loading ? (
                                        <>Iniciando... <div className="ml-2 h-4 w-4 animate-spin rounded-full border-2 border-white/50 border-r-transparent" /></>
                                    ) : (
                                        <>Iniciar Geração <Play className="ml-2 h-4 w-4 fill-current" /></>
                                    )}
                                </Button>
                            </div>
                        </div>
                    )}

                    {/* STEP 3: COCKPIT (EXECUTION) */}
                    {step === 3 && (
                        <div className="space-y-6 animate-in fade-in">
                            <div className="grid grid-cols-12 gap-6 min-h-[500px]">
                                {/* Left Side: Outline & Status */}
                                <div className="col-span-3 space-y-4">
                                    <Card className="h-full border-muted/40 bg-muted/5">
                                        <CardHeader className="pb-2">
                                            <CardTitle className="text-sm uppercase text-muted-foreground">Estrutura (Live)</CardTitle>
                                        </CardHeader>
                                        <CardContent className="space-y-2">
                                            {/* Outline Real (via SSE Job) */}
                                            {(() => {
                                                const outline = (store.jobOutline && store.jobOutline.length > 0)
                                                    ? store.jobOutline
                                                    : [];

                                                // Fallback: se ainda não chegou outline, mostra placeholder
                                                if (outline.length === 0) {
                                                    return (
                                                        <div className="text-xs text-muted-foreground p-2">
                                                            {store.isAgentRunning ? 'Aguardando outline...' : 'Inicie a geração para ver a outline.'}
                                                        </div>
                                                    );
                                                }

                                                const completedTitles = new Set(
                                                    (store.jobEvents || [])
                                                        .filter((e: any) => e?.type === 'section_processed' && e?.section)
                                                        .map((e: any) => e.section)
                                                );
                                                const stageBySection = new Map<string, string>();
                                                (store.jobEvents || []).forEach((e: any) => {
                                                    if (e?.type !== 'section_stage' || !e?.section) return;
                                                    const stage = e?.data?.stage;
                                                    if (typeof stage === 'string' && stage.trim()) {
                                                        stageBySection.set(e.section, stage);
                                                    }
                                                });
                                                const stageLabel = (stage?: string) => {
                                                    const normalized = String(stage || '').toLowerCase();
                                                    switch (normalized) {
                                                        case 'draft':
                                                            return 'Rascunho';
                                                        case 'critique':
                                                            return 'Critica';
                                                        case 'revise':
                                                            return 'Revisao';
                                                        case 'merge':
                                                            return 'Consolidacao';
                                                        default:
                                                            return stage || '';
                                                    }
                                                };
                                                const stageClass = (stage?: string) => {
                                                    const normalized = String(stage || '').toLowerCase();
                                                    switch (normalized) {
                                                        case 'draft':
                                                            return 'border-sky-200 text-sky-700';
                                                        case 'critique':
                                                            return 'border-amber-200 text-amber-700';
                                                        case 'revise':
                                                            return 'border-violet-200 text-violet-700';
                                                        case 'merge':
                                                            return 'border-emerald-200 text-emerald-700';
                                                        default:
                                                            return 'border-outline/30 text-muted-foreground';
                                                    }
                                                };

                                                const completedCount = outline.reduce((acc, t) => acc + (completedTitles.has(t) ? 1 : 0), 0);
                                                const workingIndex = store.isAgentRunning ? Math.min(completedCount, outline.length - 1) : -1;

                                                return outline.map((item: string, i: number) => {
                                                    const isDone = completedTitles.has(item) || (!store.isAgentRunning && completedCount >= outline.length);
                                                    const isWorking = store.isAgentRunning && i === workingIndex && !isDone;
                                                    const stage = stageBySection.get(item);
                                                    const stageText = stageLabel(stage);

                                                    return (
                                                        <div key={`${item}-${i}`} className="flex items-center gap-2 text-sm p-2 rounded hover:bg-white/50 transition-colors">
                                                            {isDone ? (
                                                                <CheckCircle2 className="h-3 w-3 text-green-500" />
                                                            ) : isWorking ? (
                                                                <div className="h-3 w-3 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                                                            ) : (
                                                                <div className="h-3 w-3 rounded-full border border-muted" />
                                                            )}
                                                            <span className={`${isWorking ? "font-medium text-primary" : isDone ? "text-foreground" : "text-muted-foreground"} flex-1`}>
                                                                {item}
                                                            </span>
                                                            {stageText && (
                                                                <Badge variant="outline" className={`bg-white text-[10px] ${stageClass(stage)}`}>
                                                                    {stageText}
                                                                </Badge>
                                                            )}
                                                        </div>
                                                    );
                                                });
                                            })()}
                                        </CardContent>
                                    </Card>
                                </div>

                                {/* Center: Stream Preview */}
                                <div className="col-span-6 space-y-4">
                                    <Card className="h-full shadow-lg border-primary/20">
                                        <CardHeader className="pb-2 bg-gradient-to-r from-indigo-50/50 to-purple-50/50 border-b">
                                            <div className="flex justify-between items-center">
                                                <CardTitle className="text-sm font-bold text-primary flex items-center gap-2">
                                                    <Sparkles className="h-3.5 w-3.5" />
                                                    {store.documentType} - Preview
                                                </CardTitle>
                                                {store.isAgentRunning ? (
                                                    <Badge variant="outline" className="bg-white text-[10px] animate-pulse">Gerando...</Badge>
                                                ) : (
                                                    <Badge variant="outline" className="bg-white text-[10px]">Pronto</Badge>
                                                )}
                                            </div>
                                        </CardHeader>
                                        <CardContent className="p-4">
                                            <ScrollArea className="h-[420px] w-full pr-2">
                                                <div className="prose prose-sm max-w-none dark:prose-invert">
                                                    <ReactMarkdown>
                                                        {(() => {
                                                            // Prefer canvas content (final/live), fallback to last debate preview, else placeholder
                                                            const content = canvas.content?.trim();
                                                            if (content) return content;
                                                            const lastPreview = [...(store.jobEvents || [])]
                                                                .reverse()
                                                                .find((e: any) => e?.type === 'debate_done' && e?.document_preview)?.document_preview;
                                                            if (lastPreview) return String(lastPreview);
                                                            return store.isAgentRunning ? "Aguardando conteúdo..." : "Inicie a geração para ver o preview.";
                                                        })()}
                                                    </ReactMarkdown>
                                                </div>
                                            </ScrollArea>
                                        </CardContent>
                                    </Card>
                                </div>

                                {/* Right: Logs & Metrics */}
                                <div className="col-span-3 space-y-4">
                                    <Card className="h-1/2 bg-black text-green-400 font-mono text-xs border-none shadow-inner">
                                        <CardHeader className="pb-1 px-3 pt-3">
                                            <CardTitle className="text-xs uppercase text-muted-foreground flex items-center gap-2">
                                                <TerminalSquare className="h-3 w-3" /> Logs
                                            </CardTitle>
                                        </CardHeader>
                                        <CardContent className="p-3">
                                            <ScrollArea className="h-full">
                                                <div className="space-y-1 opacity-80">
                                                    {(store.jobEvents || []).slice(-80).map((e: any, idx: number) => {
                                                        const t = e?.type || 'event';
                                                        const msg =
                                                            e?.message ||
                                                            e?.status ||
                                                            e?.section ||
                                                            e?.checkpoint ||
                                                            e?.diff_summary ||
                                                            e?.divergence_summary ||
                                                            '';
                                                        return (
                                                            <div key={idx} className={t === 'error' ? 'text-red-400' : t.includes('warn') ? 'text-yellow-400' : ''}>
                                                                [{String(t).toUpperCase()}] {String(msg).slice(0, 180)}
                                                            </div>
                                                        );
                                                    })}
                                                    {store.isAgentRunning && <div className="animate-pulse">_</div>}
                                                </div>
                                            </ScrollArea>
                                        </CardContent>
                                    </Card>

                                    <Card className="h-auto">
                                        <CardHeader className="pb-2">
                                            <CardTitle className="text-xs uppercase text-muted-foreground">Métricas</CardTitle>
                                        </CardHeader>
                                        <CardContent className="space-y-3 text-xs">
                                            {(() => {
                                                const events = store.jobEvents || [];
                                                const lastAudit = [...events].reverse().find((e: any) => e?.type === 'audit_done');
                                                const lastHil = [...events].reverse().find((e: any) => e?.type === 'hil_evaluated');
                                                const lastDebate = [...events].reverse().find((e: any) => e?.type === 'debate_done');
                                                const lastGate = [...events].reverse().find((e: any) => e?.type === 'quality_gate_done');

                                                return (
                                                    <>
                                                        <div className="flex justify-between">
                                                            <span className="text-muted-foreground">Seções</span>
                                                            <span className="font-mono">{lastDebate?.sections_count ?? store.jobOutline?.length ?? '—'}</span>
                                                        </div>
                                                        <div className="flex justify-between">
                                                            <span className="text-muted-foreground">Auditoria</span>
                                                            <span className="font-mono">{lastAudit?.status ?? '—'}</span>
                                                        </div>
                                                        <div className="flex justify-between">
                                                            <span className="text-muted-foreground">Issues (audit)</span>
                                                            <span className="font-mono">{lastAudit?.issues_count ?? '—'}</span>
                                                        </div>
                                                        <div className="flex justify-between">
                                                            <span className="text-muted-foreground">HIL</span>
                                                            <span className="font-mono">{lastHil?.hil_level ?? '—'}</span>
                                                        </div>
                                                        <div className="flex justify-between">
                                                            <span className="text-muted-foreground">Quality Gate</span>
                                                            <span className="font-mono">
                                                                {lastGate ? (lastGate.passed ? 'passou' : 'falhou') : '—'}
                                                            </span>
                                                        </div>
                                                    </>
                                                );
                                            })()}
                                        </CardContent>
                                    </Card>

                                    {/* Reuse the same job panels used in the main chat UI */}
                                    <DeepResearchViewer jobId={store.currentJobId || ''} isVisible={!!store.currentJobId} events={store.jobEvents} />
                                    <JobQualityPanel isVisible={!!store.currentJobId} events={store.jobEvents} />
                                    <JobQualityPipelinePanel isVisible={!!store.currentJobId} events={store.jobEvents} />
                                </div>
                            </div>

                            <div className="flex justify-between pt-4">
                                <Button variant="ghost" onClick={prevStep} disabled>Voltar</Button>
                                <Button variant="outline" className="text-destructive hover:bg-destructive/10">Cancelar Geração</Button>
                            </div>
                        </div>
                    )}
                </CardContent>
            </Card>

        </div>
    );
}
