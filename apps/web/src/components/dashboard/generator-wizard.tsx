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
import { HumanReviewModal } from '@/components/chat/human-review-modal';
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

export function GeneratorWizard({ caseId, caseThesis }: { caseId: string, caseThesis?: string }) {
    const [step, setStep] = useState(1);
    const store = useChatStore();
    const canvas = useCanvasStore();

    // Local state for wizard specific interactions not yet in store or direct mappings
    const [activeTab, setActiveTab] = useState("setup");
    const [advancedMode, setAdvancedMode] = useState(false);

    const [loading, setLoading] = useState(false);
    const effortRangeLabel = store.effortLevel === 1 ? '5-8' : store.effortLevel === 2 ? '10-15' : '20-30';
    const pageRangeLabel = (store.minPages > 0 || store.maxPages > 0)
        ? `${store.minPages}-${store.maxPages} págs`
        : `Auto (${effortRangeLabel} págs)`;

    // Sync thesis on init
    // useEffect(() => { if(caseThesis) store.setThesis(caseThesis) }, [caseThesis]);

    const nextStep = () => setStep(s => Math.min(s + 1, 3));
    const prevStep = () => setStep(s => Math.max(s - 1, 1));

    const handleStartGeneration = async () => {
        try {
            setLoading(true);

            // 1. Ensure a chat exists or create one
            if (!store.currentChat) {
                await store.createChat();
            }

            // 2. Advance to Cockpit immediately for UX
            setStep(3);

            // 3. Trigger generation (LangGraph Job + SSE -> Outline/Sections)
            // Nota: isso habilita "documentos grandes" por seções, e alimenta o Cockpit com outline real.
            await store.startLangGraphJob(store.thesis || "Gerar documento base");

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
                                            <TabsList className="grid w-full grid-cols-2 mb-4">
                                                <TabsTrigger value="rag_local">Autos do Processo</TabsTrigger>
                                                <TabsTrigger value="upload_cache">Arquivos Soltos (Upload)</TabsTrigger>
                                            </TabsList>

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
                                                        PDFs, DOCX, TXT (até 2GB). Bom para poucos arquivos sem estrutura.
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
                                            <Layout className="h-4 w-4" /> Dimensões
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
                                                    <div className="flex gap-1 pt-2">
                                                        {[1, 2, 3].map(level => (
                                                            <div
                                                                key={level}
                                                                onClick={() => {
                                                                    const preset = level === 1 ? [5, 8] : level === 2 ? [10, 15] : [20, 30];
                                                                    store.setEffortLevel(level);
                                                                    store.setPageRange({ minPages: preset[0], maxPages: preset[1] });
                                                                }}
                                                                className={cn(
                                                                    "flex-1 h-2 rounded-full cursor-pointer transition-colors",
                                                                    store.effortLevel >= level ? "bg-primary" : "bg-muted"
                                                                )}
                                                            />
                                                        ))}
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
                                                        Se vazio, usa o esforço para estimar o tamanho.
                                                    </p>
                                                </div>
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
                                                        onCheckedChange={store.setUseMultiAgent}
                                                    />
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
                                            <FileText className="h-4 w-4" /> Fontes de Pesquisa (RAG)
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
                                        <Scale className="h-4 w-4" /> Qualidade
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

                                            {/* Section-level HIL */}
                                            <div className="space-y-2 pt-3 border-t">
                                                <Label className="text-xs uppercase text-muted-foreground font-bold">Revisão Humana por Seção (HIL)</Label>
                                                <p className="text-[10px] text-muted-foreground">
                                                    Se marcado, o workflow vai pausar para você aprovar/editar seções específicas antes de continuar.
                                                </p>
                                                {(() => {
                                                    const docType = store.documentType || '';
                                                    const outlineReal = (store.jobOutline || []).map((t: any) => String(t).trim()).filter(Boolean);
                                                    const template =
                                                        docType.includes('PARECER') ? [
                                                            "I - INTRODUÇÃO E OBJETO DA CONSULTA",
                                                            "II - DOS FATOS",
                                                            "III - ANÁLISE JURÍDICA",
                                                            "IV - CONCLUSÃO E PARECER"
                                                        ] :
                                                            (docType.includes('CONTESTACAO') ? [
                                                                "I - SÍNTESE DA INICIAL",
                                                                "II - PRELIMINARES",
                                                                "III - DO MÉRITO",
                                                                "IV - DOS PEDIDOS"
                                                            ] : [
                                                                "I - DOS FATOS",
                                                                "II - DO DIREITO",
                                                                "III - DOS PEDIDOS"
                                                            ]);

                                                    const outline = outlineReal.length > 0 ? outlineReal : template;
                                                    const sourceLabel = outlineReal.length > 0 ? "Outline real" : "Template (fallback)";

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

                                                const completedCount = outline.reduce((acc, t) => acc + (completedTitles.has(t) ? 1 : 0), 0);
                                                const workingIndex = store.isAgentRunning ? Math.min(completedCount, outline.length - 1) : -1;

                                                return outline.map((item: string, i: number) => {
                                                    const isDone = completedTitles.has(item) || (!store.isAgentRunning && completedCount >= outline.length);
                                                    const isWorking = store.isAgentRunning && i === workingIndex && !isDone;

                                                    return (
                                                        <div key={`${item}-${i}`} className="flex items-center gap-2 text-sm p-2 rounded hover:bg-white/50 transition-colors">
                                                            {isDone ? (
                                                                <CheckCircle2 className="h-3 w-3 text-green-500" />
                                                            ) : isWorking ? (
                                                                <div className="h-3 w-3 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                                                            ) : (
                                                                <div className="h-3 w-3 rounded-full border border-muted" />
                                                            )}
                                                            <span className={isWorking ? "font-medium text-primary" : isDone ? "text-foreground" : "text-muted-foreground"}>
                                                                {item}
                                                            </span>
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

            {/* HIL (Human-in-the-loop) modal for LangGraph jobs */}
            <HumanReviewModal
                isOpen={!!store.reviewData}
                data={store.reviewData}
                onSubmit={store.submitReview}
            />
        </div>
    );
}
