"use client";

import React, { useEffect, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  ArrowLeft, Save, Upload, Sparkles, Folder, MessageSquare, FileText,
  CheckCircle, Clock, X, Plus, Database, Network, BookOpen, Library,
  Settings2, Zap, Users, Scale, ChevronUp, Paperclip
} from 'lucide-react';
import { toast } from 'sonner';
import apiClient from '@/lib/api-client';
import { ChatInterface } from '@/components/chat/chat-interface';
import { useChatStore } from '@/stores/chat-store';
import { useContextStore } from '@/stores/context-store';
import { MessageBudgetModal } from '@/components/billing/message-budget-modal';
import { useCanvasStore } from '@/stores/canvas-store';
import { CanvasContainer, MinutaSettingsDrawer, OutlineApprovalModal } from '@/components/dashboard';
import { useCorpusCollections, useCorpusProjects } from '@/app/(dashboard)/corpus/hooks/use-corpus';
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import { listModels } from '@/config/models';
import { type OutlineApprovalSection } from '@/components/dashboard/outline-approval-modal';

type GenerationMode = 'individual' | 'multi-agent';

export default function CaseDetailPage() {
    const params = useParams();
    const router = useRouter();
    const id = params.id as string;

    const [caseData, setCaseData] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [caseDocuments, setCaseDocuments] = useState<any[]>([]);
    const [docsLoading, setDocsLoading] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [isDragOver, setIsDragOver] = useState(false);
    const [caseChatId, setCaseChatId] = useState<string | null>(null);
    const [caseGeneratorChatId, setCaseGeneratorChatId] = useState<string | null>(null);
    const [didInitCaseContext, setDidInitCaseContext] = useState(false);

    // New state for minuta-style layout
    const [showSettings, setShowSettings] = useState(false);
    const [mode, setMode] = useState<GenerationMode>('multi-agent');
    const [chatPanelWidth, setChatPanelWidth] = useState(45);
    const [isResizing, setIsResizing] = useState(false);
    const [showCorpus, setShowCorpus] = useState(false);
    const splitContainerRef = useRef<HTMLDivElement>(null);

    // Canvas store
    const { state: canvasState, showCanvas, hideCanvas, setState: setCanvasState } = useCanvasStore();

    // Corpus hooks
    const { data: corpusCollections, isLoading: collectionsLoading } = useCorpusCollections();
    const { data: corpusProjects, isLoading: projectsLoading } = useCorpusProjects();

    // Model options
    const agentModelOptions = listModels({ forAgents: true });
    const baseModelOptions = listModels({ forJuridico: true });

    // Stores - extended for minuta settings
    const {
        setThesis,
        setContext,
        billingModal,
        closeBillingModal,
        retryWithBudgetOverride,
        createChat,
        setUseMultiAgent,
        isSending,
        isLoading: chatIsLoading,
        startAgentGeneration,
        isAgentRunning,
        agentSteps,
        retryProgress,
        reviewData,
        submitReview,
        // Chat settings
        selectedModel,
        setSelectedModel,
        searchMode,
        setSearchMode,
        multiQuery,
        setMultiQuery,
        breadthFirst,
        setBreadthFirst,
        hilOutlineEnabled,
        setHilOutlineEnabled,
        autoApproveHil,
        setAutoApproveHil,
        chatOutlineReviewEnabled,
        setChatOutlineReviewEnabled,
        auditMode,
        setAuditMode,
        // Minuta-only (pipeline)
        qualityProfile,
        setQualityProfile,
        qualityTargetSectionScore,
        setQualityTargetSectionScore,
        qualityTargetFinalScore,
        setQualityTargetFinalScore,
        qualityMaxRounds,
        setQualityMaxRounds,
        qualityMaxFinalReviewLoops,
        setQualityMaxFinalReviewLoops,
        qualityStyleRefineMaxRounds,
        setQualityStyleRefineMaxRounds,
        qualityMaxResearchVerifierAttempts,
        setQualityMaxResearchVerifierAttempts,
        qualityMaxRagRetries,
        setQualityMaxRagRetries,
        qualityRagRetryExpandScope,
        setQualityRagRetryExpandScope,
        recursionLimitOverride,
        setRecursionLimitOverride,
        strictDocumentGateOverride,
        setStrictDocumentGateOverride,
        hilSectionPolicyOverride,
        setHilSectionPolicyOverride,
        hilFinalRequiredOverride,
        setHilFinalRequiredOverride,
        documentChecklist,
        setDocumentChecklist,
        cragMinBestScoreOverride,
        setCragMinBestScoreOverride,
        cragMinAvgScoreOverride,
        setCragMinAvgScoreOverride,
        forceGranularDebate,
        setForceGranularDebate,
        maxDivergenceHilRounds,
        setMaxDivergenceHilRounds,
        formattingOptions,
        setFormattingOptions,
        chatMode,
        setChatMode,
        selectedModels,
        setSelectedModels,
        setShowMultiModelComparator,
        webSearch,
        webSearchModel,
        setWebSearchModel,
        denseResearch,
        deepResearchProvider,
        setDeepResearchProvider,
        deepResearchModel,
        setDeepResearchModel,
        reasoningLevel,
        setReasoningLevel,
        researchPolicy,
        setResearchPolicy,
        agentStrategistModel,
        setAgentStrategistModel,
        agentDrafterModels,
        setAgentDrafterModels,
        agentReviewerModels,
        setAgentReviewerModels,
        chatPersonality,
        setChatPersonality,
        creativityMode,
        setCreativityMode,
        temperatureOverride,
        setTemperatureOverride,
        ragScope,
        setRagScope,
        effortLevel,
        setEffortLevel,
        minPages,
        maxPages,
        setPageRange,
        resetPageRange,
    } = useChatStore();
    const legacyCaseChatStorageKey = `iudex:case_chat:${id}`;
    const caseChatStorageKey = `iudex:case_chat:${id}:chat`;
    const caseGeneratorChatStorageKey = `iudex:case_chat:${id}:generator`;

    useEffect(() => {
        const loadCase = async () => {
            try {
                setLoading(true);
                const data = await apiClient.getCase(id);
                setCaseData(data);

                // Initialize Generation Context from Case Data
                if (data.thesis) setThesis(data.thesis);

                // Clear previous context files and load case files (mocked for now as we don't have separate endpoint for files yet)
                // In real impl, we would fetch apiClient.getCaseDocuments(id)
                // clearItems();

            } catch (error) {
                console.error(error);
                toast.error("Erro ao carregar caso");
                router.push('/cases');
            } finally {
                setLoading(false);
            }
        };

        if (id) loadCase();
    }, [id, setThesis, router]);

    useEffect(() => {
        const ensureCaseChats = async () => {
            if (!id) return;
            if (!caseData?.title) return;

            const loadValidChatId = async (storageKey: string) => {
                let storedId: string | null = null;
                try {
                    storedId = typeof window !== 'undefined' ? localStorage.getItem(storageKey) : null;
                } catch {
                    storedId = null;
                }

                if (!storedId) return null;
                try {
                    await apiClient.getChat(storedId);
                    return storedId;
                } catch {
                    try {
                        localStorage.removeItem(storageKey);
                    } catch {
                        // noop
                    }
                    return null;
                }
            };

            let chatId = await loadValidChatId(caseChatStorageKey);
            let generatorChatId = await loadValidChatId(caseGeneratorChatStorageKey);

            // Migration: legacy key used to store a single chat for both experiences.
            // Prefer keeping the legacy chat as the "Gerar peça" chat, and create a fresh chat for "Chat Jurídico".
            if (!generatorChatId) {
                let legacyId: string | null = null;
                try {
                    legacyId = typeof window !== 'undefined' ? localStorage.getItem(legacyCaseChatStorageKey) : null;
                } catch {
                    legacyId = null;
                }
                if (legacyId) {
                    try {
                        await apiClient.getChat(legacyId);
                        generatorChatId = legacyId;
                        try {
                            localStorage.setItem(caseGeneratorChatStorageKey, legacyId);
                            localStorage.removeItem(legacyCaseChatStorageKey);
                        } catch {
                            // noop
                        }
                    } catch {
                        try {
                            localStorage.removeItem(legacyCaseChatStorageKey);
                        } catch {
                            // noop
                        }
                    }
                }
            }

            if (!chatId) {
                const chat = await createChat(`Caso: ${caseData.title} (Chat)`);
                chatId = chat.id;
                try {
                    localStorage.setItem(caseChatStorageKey, chat.id);
                } catch {
                    // noop
                }
            }

            if (!generatorChatId) {
                const chat = await createChat(`Caso: ${caseData.title} (Gerar peça)`);
                generatorChatId = chat.id;
                try {
                    localStorage.setItem(caseGeneratorChatStorageKey, chat.id);
                } catch {
                    // noop
                }
            }

            setCaseChatId(chatId);
            setCaseGeneratorChatId(generatorChatId);
        };

        ensureCaseChats().catch((error) => {
            console.error(error);
            toast.error("Erro ao preparar o chat do caso");
        });
    }, [
        id,
        caseData?.title,
        legacyCaseChatStorageKey,
        caseChatStorageKey,
        caseGeneratorChatStorageKey,
        createChat,
    ]);

    const loadCaseDocuments = async () => {
        try {
            setDocsLoading(true);
            const data = await apiClient.getCaseDocuments(id);
            setCaseDocuments(Array.isArray(data?.documents) ? data.documents : []);
        } catch (error) {
            console.error(error);
            // Fallback to legacy tag-based loading
            try {
                const data = await apiClient.getDocuments(0, 200);
                const docs = Array.isArray(data?.documents) ? data.documents : [];
                const tagKey = `case:${id}`.toLowerCase();
                const filtered = docs.filter((doc: any) =>
                    Array.isArray(doc?.tags) && doc.tags.some((tag: string) => String(tag).toLowerCase() === tagKey)
                );
                setCaseDocuments(filtered);
            } catch {
                setCaseDocuments([]);
            }
        } finally {
            setDocsLoading(false);
        }
    };

    useEffect(() => {
        if (id) loadCaseDocuments();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id]);

    const handleFileUpload = async (files: FileList | File[]) => {
        if (!files || files.length === 0) return;

        setUploading(true);
        let successCount = 0;
        let errorCount = 0;

        for (const file of Array.from(files)) {
            try {
                await apiClient.uploadDocumentToCase(id, file, {
                    auto_ingest_rag: true,
                    auto_ingest_graph: true,
                });
                successCount++;
            } catch (error) {
                console.error(`Failed to upload ${file.name}:`, error);
                errorCount++;
            }
        }

        setUploading(false);

        if (successCount > 0) {
            toast.success(`${successCount} arquivo(s) enviado(s) com sucesso`);
            loadCaseDocuments();
        }
        if (errorCount > 0) {
            toast.error(`${errorCount} arquivo(s) falharam no upload`);
        }
    };

    const handleDetachDocument = async (docId: string, docName: string) => {
        try {
            await apiClient.detachDocumentFromCase(id, docId);
            toast.success(`"${docName}" desanexado do caso`);
            loadCaseDocuments();
        } catch (error) {
            console.error(error);
            toast.error("Erro ao desanexar documento");
        }
    };

    const handleDragOver = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragOver(true);
    };

    const handleDragLeave = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragOver(false);
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragOver(false);
        const files = e.dataTransfer.files;
        if (files?.length > 0) {
            handleFileUpload(files);
        }
    };

    useEffect(() => {
        if (!id) return;
        // Avoid leaking context across cases.
        setDidInitCaseContext(false);
        useContextStore.getState().clearItems();
        setContext([]);
    }, [id, setContext]);

    useEffect(() => {
        if (!id) return;
        if (!caseDocuments || caseDocuments.length === 0) return;

        const caseItems = caseDocuments
            .filter((doc: any) => doc && typeof doc.id === 'string')
            .map((doc: any) => ({
                id: String(doc.id),
                type: 'file' as const,
                name: String(doc.name || doc.title || doc.filename || 'Documento'),
                meta: 'Caso',
            }));
        if (caseItems.length === 0) return;

        // Merge (do not overwrite) to preserve any manual additions the user may have made.
        const currentItems = useContextStore.getState().items || [];
        const byId = new Map<string, any>();
        for (const item of currentItems) {
            if (item && typeof item.id === 'string') byId.set(item.id, item);
        }
        for (const item of caseItems) byId.set(item.id, item);

        const mergedItems = Array.from(byId.values());
        useContextStore.getState().setItems(mergedItems);
        setContext(mergedItems);

        if (!didInitCaseContext) setDidInitCaseContext(true);
    }, [id, caseDocuments, didInitCaseContext, setContext]);

    const handleSaveMetadata = async () => {
        try {
            await apiClient.updateCase(id, {
                title: caseData.title,
                thesis: caseData.thesis,
                description: caseData.description,
                process_number: caseData.process_number,
                client_name: caseData.client_name
            });
            toast.success("Dados do caso atualizados!");
        } catch (error) {
            console.error(error);
            toast.error("Erro ao salvar dados");
        }
    };

    // Sync mode with store
    useEffect(() => {
        setUseMultiAgent(mode === 'multi-agent');
    }, [mode, setUseMultiAgent]);

    useEffect(() => {
        if (mode !== 'multi-agent') return;
        if (agentStrategistModel === selectedModel) return;
        setAgentStrategistModel(selectedModel);
    }, [mode, agentStrategistModel, selectedModel, setAgentStrategistModel]);

    // Resize logic
    useEffect(() => {
        if (!isResizing) return;
        const { style } = document.body;
        const prevCursor = style.cursor;
        const prevUserSelect = style.userSelect;
        style.cursor = 'col-resize';
        style.userSelect = 'none';
        return () => {
            style.cursor = prevCursor;
            style.userSelect = prevUserSelect;
        };
    }, [isResizing]);

    useEffect(() => {
        const container = splitContainerRef.current;
        if (!container) return;
        const clampWidth = () => {
            const rect = container.getBoundingClientRect();
            if (!rect.width) return;
            const minPx = 300;
            const maxPx = rect.width * 0.7;
            const currentPx = (chatPanelWidth / 100) * rect.width;
            const clampedPx = Math.min(Math.max(currentPx, minPx), maxPx);
            const nextPercent = (clampedPx / rect.width) * 100;
            if (Math.abs(nextPercent - chatPanelWidth) > 0.1) {
                setChatPanelWidth(nextPercent);
            }
        };
        clampWidth();
        window.addEventListener('resize', clampWidth);
        return () => window.removeEventListener('resize', clampWidth);
    }, [chatPanelWidth]);

    const updateChatWidthFromPointer = (clientX: number) => {
        const container = splitContainerRef.current;
        if (!container) return;
        const rect = container.getBoundingClientRect();
        if (!rect.width) return;
        const minPx = 300;
        const maxPx = rect.width * 0.7;
        const rawPx = clientX - rect.left;
        const clampedPx = Math.min(Math.max(rawPx, minPx), maxPx);
        setChatPanelWidth((clampedPx / rect.width) * 100);
    };

    const handleDividerPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
        if (canvasState !== 'normal') return;
        event.preventDefault();
        event.currentTarget.setPointerCapture(event.pointerId);
        setIsResizing(true);
        updateChatWidthFromPointer(event.clientX);
    };

    const handleDividerPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
        if (!isResizing) return;
        updateChatWidthFromPointer(event.clientX);
    };

    const handleDividerPointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
        if (!isResizing) return;
        event.preventDefault();
        try {
            event.currentTarget.releasePointerCapture(event.pointerId);
        } catch {
            // noop
        }
        setIsResizing(false);
    };

    // Generation handlers
    const handleGenerate = async () => {
        try {
            await startAgentGeneration('Gerar minuta baseada nos documentos selecionados.');
        } catch {
            // handled by store/toast
        }
    };

    const handleSetChatMode = (next: 'standard' | 'multi-model') => {
        const DEFAULT_COMPARE_MODELS = ['gpt-5.2', 'claude-4.5-sonnet', 'gemini-3-flash'];
        if (next === 'multi-model') {
            const nextModels =
                selectedModels.length >= 2
                    ? selectedModels
                    : selectedModels.length === 1
                        ? [selectedModels[0], DEFAULT_COMPARE_MODELS.find((m) => m !== selectedModels[0]) || 'gpt-5.2']
                        : DEFAULT_COMPARE_MODELS.slice(0, 3);
            setSelectedModels(nextModels);
            setShowMultiModelComparator(true);
            setChatMode('multi-model');
            return;
        }
        if (selectedModels.length > 1) setSelectedModels([selectedModels[0]]);
        setChatMode('standard');
    };

    // Agent step labels
    const getAgentLabel = (agent: string) => {
        switch (agent) {
            case 'strategist': return 'Estrategista';
            case 'researcher': return 'Pesquisador';
            case 'drafter': return 'Redator';
            case 'reviewer': return 'Revisor';
            case 'judge': return 'Juiz';
            default: return agent;
        }
    };

    // HIL Handlers
    const handleOutlineApprove = async (sections: OutlineApprovalSection[]) => {
        try {
            await submitReview({ approved: true, outline: sections });
            toast.success('Estrutura aprovada! Agentes iniciando redação...');
        } catch {
            toast.error('Erro ao enviar aprovação.');
        }
    };

    const handleOutlineReject = async () => {
        try {
            await submitReview({ approved: false, comment: "Usuário cancelou no modal." });
            toast.info('Geração cancelada.');
        } catch {
            toast.error('Erro ao rejeitar.');
        }
    };

    // Check if HIL modal should be shown
    const isChatOutlineReview = reviewData?.checkpoint === 'outline' && (reviewData as any)?.mode === 'chat';
    const showOutlineModal = (reviewData?.checkpoint === 'outline' || reviewData?.type === 'outline_review') && !isChatOutlineReview;
    const outlinePayload = reviewData?.review_data?.outline || (reviewData as any)?.outline || [];

    // Convert generic list to typed sections if needed
    const initialSections: OutlineApprovalSection[] = Array.isArray(outlinePayload)
        ? outlinePayload.map((s: string | any, i: number) =>
            typeof s === 'string' ? { id: `sect-${i}`, title: s } : s
        )
        : [];

    // Layout mode: chat-only | split | canvas-only
    const layoutMode: 'chat' | 'split' | 'canvas' =
        canvasState === 'hidden' ? 'chat' : canvasState === 'expanded' ? 'canvas' : 'split';

    const toggleChatMode = () => {
        if (layoutMode === 'chat') {
            showCanvas();
            setCanvasState('normal');
            return;
        }
        hideCanvas();
    };

    const toggleCanvasMode = () => {
        if (layoutMode === 'canvas') {
            showCanvas();
            setCanvasState('normal');
            return;
        }
        showCanvas();
        setCanvasState('expanded');
    };

    if (loading) return <div className="p-8">Carregando caso...</div>;
    if (!caseData) return <div className="p-8">Caso não encontrado</div>;

    return (
        <div className="w-full py-4 space-y-4">
            {/* Header */}
            <div className="flex items-center gap-4 border-b border-border/40 pb-4">
                <Button variant="ghost" size="icon" onClick={() => router.push('/cases')}>
                    <ArrowLeft className="h-4 w-4" />
                </Button>
                <div className="flex-1">
                    <h1 className="text-2xl font-bold tracking-tight">{caseData.title}</h1>
                    <div className="flex items-center gap-2 text-sm text-muted-foreground mt-1">
                        <span className="font-medium text-foreground">{caseData.client_name || 'Sem cliente'}</span>
                        <span>•</span>
                        <span className="font-mono">{caseData.process_number || 'Sem n. processo'}</span>
                    </div>
                </div>
                <Button onClick={handleSaveMetadata} variant="outline" className="gap-2">
                    <Save className="h-4 w-4" />
                    Salvar Alterações
                </Button>
            </div>

            <Tabs defaultValue="generation" className="space-y-3">
                <TabsList>
                    <TabsTrigger value="overview">Visão Geral & Fatos</TabsTrigger>
                    <TabsTrigger value="generation" className="gap-2">
                        <Sparkles className="h-3 w-3 text-amber-500" />
                        Gerar Peça
                    </TabsTrigger>
                    <TabsTrigger value="documents" className="gap-2">
                        <Folder className="h-3 w-3" />
                        Arquivos / Autos
                    </TabsTrigger>
                    <TabsTrigger value="chat" className="gap-2">
                        <MessageSquare className="h-3 w-3 text-indigo-500" />
                        Chat Jurídico
                    </TabsTrigger>
                </TabsList>

                {/* TAB: Overview */}
                <TabsContent value="overview" className="gap-4 grid grid-cols-1 md:grid-cols-2">
                    <Card>
                        <CardHeader>
                            <CardTitle>Dados do Processo</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="space-y-1">
                                <Label>Título do Caso</Label>
                                <Input
                                    value={caseData.title}
                                    onChange={e => setCaseData({ ...caseData, title: e.target.value })}
                                />
                            </div>
                            <div className="space-y-1">
                                <Label>Número do Processo</Label>
                                <Input
                                    value={caseData.process_number || ''}
                                    onChange={e => setCaseData({ ...caseData, process_number: e.target.value })}
                                />
                            </div>
                            <div className="space-y-1">
                                <Label>Cliente</Label>
                                <Input
                                    value={caseData.client_name || ''}
                                    onChange={e => setCaseData({ ...caseData, client_name: e.target.value })}
                                />
                            </div>
                        </CardContent>
                    </Card>

                    <Card className="h-full">
                        <CardHeader>
                            <CardTitle>Resumo dos Fatos & Tese</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4 h-full">
                            <div className="space-y-1 h-[200px]">
                                <Label>Resumo dos Fatos (Factual)</Label>
                                <Textarea
                                    className="h-full resize-none"
                                    placeholder="Cole aqui o resumo, notas ou descrição do caso..."
                                    value={caseData.description || ''}
                                    onChange={e => setCaseData({ ...caseData, description: e.target.value })}
                                />
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* TAB: Generation - Chat + Canvas Layout */}
                <TabsContent value="generation" className="h-[calc(100vh-200px)] min-h-[600px]">
                    <div className="flex h-full flex-col gap-1">
                        {/* Compact Toolbar */}
                        <div className="flex items-center justify-between rounded-xl bg-white/90 dark:bg-slate-900/90 border border-slate-200/60 dark:border-slate-700/60 shadow-sm px-3 py-1.5">
                            {/* Left: Mode toggle */}
                            <div className="flex items-center gap-2">
                                <div className="flex items-center rounded-md border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 p-0.5">
                                    <button
                                        onClick={() => { setMode('individual'); hideCanvas(); }}
                                        className={cn(
                                            "flex items-center gap-1 rounded px-2 py-1 text-[11px] font-medium transition-all",
                                            mode === 'individual' ? "bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm" : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                                        )}
                                    >
                                        <Zap className="h-3 w-3" />
                                        Rápido
                                    </button>
                                    <button
                                        onClick={() => { setMode('multi-agent'); showCanvas(); }}
                                        className={cn(
                                            "flex items-center gap-1 rounded px-2 py-1 text-[11px] font-medium transition-all",
                                            mode === 'multi-agent' ? "bg-indigo-600 text-white shadow-sm" : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                                        )}
                                    >
                                        <Users className="h-3 w-3" />
                                        Comitê
                                    </button>
                                </div>
                            </div>

                            {/* Center: Layout toggle */}
                            <div className="flex items-center rounded-md border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 p-0.5">
                                <button
                                    type="button"
                                    onClick={toggleChatMode}
                                    className={cn(
                                        "rounded px-2 py-0.5 text-[10px] font-medium transition-all",
                                        layoutMode !== 'canvas' ? "bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm" : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                                    )}
                                >
                                    Chat
                                </button>
                                <button
                                    type="button"
                                    onClick={toggleCanvasMode}
                                    className={cn(
                                        "rounded px-2 py-0.5 text-[10px] font-medium transition-all",
                                        layoutMode !== 'chat' ? "bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm" : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                                    )}
                                >
                                    Canvas
                                </button>
                            </div>

                            {/* Right: Actions */}
                            <div className="flex items-center gap-1">
                                <Button
                                    size="sm"
                                    className="h-7 rounded-md bg-indigo-600 text-[11px] px-2.5 hover:bg-indigo-700"
                                    onClick={handleGenerate}
                                    disabled={isSending || chatIsLoading}
                                >
                                    <Sparkles className="mr-1 h-3 w-3" />
                                    Gerar
                                </Button>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className={cn("h-7 w-7 rounded-md", showSettings && "bg-slate-100 dark:bg-slate-800")}
                                    onClick={() => setShowSettings(!showSettings)}
                                >
                                    <Settings2 className="h-3.5 w-3.5" />
                                </Button>
                            </div>
                        </div>

                        {/* Settings Drawer */}
                        <MinutaSettingsDrawer
                            open={showSettings}
                            onOpenChange={setShowSettings}
                            mode={mode}
                            chatMode={chatMode}
                            onSetChatMode={handleSetChatMode}
                            chatPersonality={chatPersonality}
                            setChatPersonality={setChatPersonality}
                            documentType={useChatStore.getState().documentType || 'PETICAO_INICIAL'}
                            setDocumentType={(t) => useChatStore.getState().setDocumentType(t)}
                            minPages={minPages}
                            maxPages={maxPages}
                            setPageRange={setPageRange}
                            resetPageRange={resetPageRange}
                            formattingOptions={formattingOptions}
                            setFormattingOptions={setFormattingOptions}
                            reasoningLevel={reasoningLevel as 'low' | 'medium' | 'high'}
                            setReasoningLevel={setReasoningLevel}
                            effortLevel={effortLevel}
                            setEffortLevel={setEffortLevel}
                            creativityMode={creativityMode}
                            setCreativityMode={setCreativityMode}
                            temperatureOverride={temperatureOverride}
                            setTemperatureOverride={setTemperatureOverride}
                            qualityProfile={qualityProfile}
                            setQualityProfile={setQualityProfile}
                            qualityTargetSectionScore={qualityTargetSectionScore}
                            setQualityTargetSectionScore={setQualityTargetSectionScore}
                            qualityTargetFinalScore={qualityTargetFinalScore}
                            setQualityTargetFinalScore={setQualityTargetFinalScore}
                            qualityMaxRounds={qualityMaxRounds}
                            setQualityMaxRounds={setQualityMaxRounds}
                            researchPolicy={researchPolicy}
                            setResearchPolicy={setResearchPolicy}
                            webSearch={webSearch}
                            setWebSearch={(v) => useChatStore.getState().setWebSearch(v)}
                            denseResearch={denseResearch}
                            setDenseResearch={(v) => useChatStore.getState().setDenseResearch(v)}
                            searchMode={searchMode}
                            setSearchMode={setSearchMode}
                            multiQuery={multiQuery}
                            setMultiQuery={setMultiQuery}
                            breadthFirst={breadthFirst}
                            setBreadthFirst={setBreadthFirst}
                            deepResearchProvider={deepResearchProvider}
                            setDeepResearchProvider={setDeepResearchProvider}
                            deepResearchModel={deepResearchModel}
                            setDeepResearchModel={setDeepResearchModel}
                            webSearchModel={webSearchModel}
                            setWebSearchModel={setWebSearchModel}
                            auditMode={auditMode}
                            setAuditMode={setAuditMode}
                            selectedModel={selectedModel}
                            setSelectedModel={setSelectedModel}
                            agentStrategistModel={agentStrategistModel}
                            agentDrafterModels={agentDrafterModels}
                            setAgentDrafterModels={setAgentDrafterModels}
                            agentReviewerModels={agentReviewerModels}
                            setAgentReviewerModels={setAgentReviewerModels}
                            selectedModels={selectedModels}
                            setSelectedModels={setSelectedModels}
                            setShowMultiModelComparator={setShowMultiModelComparator}
                            baseModelOptions={baseModelOptions}
                            agentModelOptions={agentModelOptions}
                            hilOutlineEnabled={hilOutlineEnabled}
                            setHilOutlineEnabled={setHilOutlineEnabled}
                            autoApproveHil={autoApproveHil}
                            setAutoApproveHil={setAutoApproveHil}
                            chatOutlineReviewEnabled={chatOutlineReviewEnabled}
                            setChatOutlineReviewEnabled={setChatOutlineReviewEnabled}
                            hilSectionPolicyOverride={hilSectionPolicyOverride}
                            setHilSectionPolicyOverride={setHilSectionPolicyOverride}
                            hilFinalRequiredOverride={hilFinalRequiredOverride}
                            setHilFinalRequiredOverride={setHilFinalRequiredOverride}
                            qualityMaxFinalReviewLoops={qualityMaxFinalReviewLoops}
                            setQualityMaxFinalReviewLoops={setQualityMaxFinalReviewLoops}
                            qualityStyleRefineMaxRounds={qualityStyleRefineMaxRounds}
                            setQualityStyleRefineMaxRounds={setQualityStyleRefineMaxRounds}
                            qualityMaxResearchVerifierAttempts={qualityMaxResearchVerifierAttempts}
                            setQualityMaxResearchVerifierAttempts={setQualityMaxResearchVerifierAttempts}
                            qualityMaxRagRetries={qualityMaxRagRetries}
                            setQualityMaxRagRetries={setQualityMaxRagRetries}
                            qualityRagRetryExpandScope={qualityRagRetryExpandScope}
                            setQualityRagRetryExpandScope={setQualityRagRetryExpandScope}
                            recursionLimitOverride={recursionLimitOverride}
                            setRecursionLimitOverride={setRecursionLimitOverride}
                            strictDocumentGateOverride={strictDocumentGateOverride}
                            setStrictDocumentGateOverride={setStrictDocumentGateOverride}
                            forceGranularDebate={forceGranularDebate}
                            setForceGranularDebate={setForceGranularDebate}
                            maxDivergenceHilRounds={maxDivergenceHilRounds}
                            setMaxDivergenceHilRounds={setMaxDivergenceHilRounds}
                            cragMinBestScoreOverride={cragMinBestScoreOverride}
                            setCragMinBestScoreOverride={setCragMinBestScoreOverride}
                            cragMinAvgScoreOverride={cragMinAvgScoreOverride}
                            setCragMinAvgScoreOverride={setCragMinAvgScoreOverride}
                            documentChecklist={documentChecklist}
                            setDocumentChecklist={setDocumentChecklist}
                        />

                        {/* Agent Steps - Only show when running */}
                        {mode === 'multi-agent' && isAgentRunning && agentSteps.length > 0 && (
                            <div className="flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/50">
                                <div className="flex items-center gap-1.5">
                                    {agentSteps.map((step, i) => (
                                        <React.Fragment key={step.id}>
                                            {i > 0 && <span className="text-slate-300 text-[10px]">{'\u2192'}</span>}
                                            <span className={cn(
                                                "text-[11px] font-medium",
                                                step.status === 'completed' && "text-emerald-600",
                                                step.status === 'working' && "text-indigo-600",
                                                step.status === 'pending' && "text-slate-400",
                                            )}>
                                                {step.status === 'completed' && '\u2713 '}
                                                {step.status === 'working' && '\u27F3 '}
                                                {getAgentLabel(step.agent)}
                                            </span>
                                        </React.Fragment>
                                    ))}
                                </div>
                                {retryProgress?.isRetrying && (
                                    <span className="text-[10px] text-amber-600 ml-auto">
                                        Tentando novamente ({retryProgress?.progress || '...'})
                                    </span>
                                )}
                            </div>
                        )}

                        {/* Main Content: Resizable Chat + Canvas */}
                        <div
                            ref={splitContainerRef}
                            className="flex-1 h-full flex flex-row gap-0 min-h-0 overflow-hidden rounded-xl border border-slate-200/60 dark:border-slate-700/60 bg-white dark:bg-slate-900"
                        >
                            {/* Chat Panel */}
                            <div
                                className={cn(
                                    "relative flex flex-col min-w-0 transition-[width,opacity,transform] duration-300 ease-in-out will-change-[width]",
                                    layoutMode === 'split' ? 'border-r border-slate-200/60 dark:border-slate-700/60' : '',
                                    canvasState === 'expanded' ? 'hidden w-0 opacity-0' : ''
                                )}
                                style={{
                                    width: canvasState === 'normal' ? `${chatPanelWidth}%` : '100%',
                                }}
                            >
                                <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
                                    {caseGeneratorChatId ? (
                                        <ChatInterface
                                            chatId={caseGeneratorChatId}
                                            hideInput={false}
                                            autoCanvasOnDocumentRequest
                                            showCanvasButton
                                        />
                                    ) : (
                                        <div className="text-sm text-muted-foreground py-8 px-4">
                                            Preparando chat...
                                        </div>
                                    )}
                                </div>

                                {/* Bottom: Corpus toggle */}
                                <div className="flex items-center gap-1.5 px-3 py-1.5 border-t border-slate-100 dark:border-slate-800">
                                    <Popover open={showCorpus} onOpenChange={setShowCorpus}>
                                        <PopoverTrigger asChild>
                                            <button
                                                className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] text-slate-500 hover:border-indigo-300 hover:text-indigo-600 hover:bg-indigo-50/50 transition-colors"
                                            >
                                                <Library className="h-3 w-3" />
                                                <span>Corpus</span>
                                                <ChevronUp className={cn("h-3 w-3 transition-transform", showCorpus && "rotate-180")} />
                                            </button>
                                        </PopoverTrigger>
                                        <PopoverContent side="top" align="start" className="w-80 p-0" sideOffset={6}>
                                            <div className="px-3 py-2 border-b border-slate-100">
                                                <span className="text-[11px] font-semibold text-slate-600">Base de Conhecimento</span>
                                            </div>
                                            <div className="max-h-[260px] overflow-y-auto px-3 py-2 space-y-3">
                                                {/* Corpus Global */}
                                                <div>
                                                    <div className="flex items-center gap-1.5 mb-1">
                                                        <Database className="h-3 w-3 text-emerald-500" />
                                                        <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Corpus Global</span>
                                                    </div>
                                                    {collectionsLoading ? (
                                                        <div className="text-[11px] text-slate-400 pl-4">Carregando...</div>
                                                    ) : corpusCollections && corpusCollections.length > 0 ? (
                                                        corpusCollections.map((col) => (
                                                            <div key={col.name} className="flex items-center justify-between text-[11px] text-slate-600 py-1 pl-4 rounded hover:bg-slate-50">
                                                                <span className="truncate">{col.display_name}</span>
                                                                <span className="text-[10px] text-slate-400 ml-2 flex-shrink-0">{col.document_count} docs</span>
                                                            </div>
                                                        ))
                                                    ) : (
                                                        <div className="text-[11px] text-slate-400 pl-4">Nenhuma coleção</div>
                                                    )}
                                                </div>

                                                {/* Corpus Privado */}
                                                <div>
                                                    <div className="flex items-center gap-1.5 mb-1">
                                                        <BookOpen className="h-3 w-3 text-indigo-500" />
                                                        <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Corpus Privado</span>
                                                    </div>
                                                    {projectsLoading ? (
                                                        <div className="text-[11px] text-slate-400 pl-4">Carregando...</div>
                                                    ) : corpusProjects?.items && corpusProjects.items.length > 0 ? (
                                                        corpusProjects.items.map((proj) => (
                                                            <div key={proj.id} className="flex items-center justify-between text-[11px] text-slate-600 py-1 pl-4 rounded hover:bg-slate-50">
                                                                <span className="truncate">{proj.name}</span>
                                                                <span className="text-[10px] text-slate-400 ml-2 flex-shrink-0">{proj.document_count} docs</span>
                                                            </div>
                                                        ))
                                                    ) : (
                                                        <div className="text-[11px] text-slate-400 pl-4">Nenhum projeto</div>
                                                    )}
                                                </div>

                                                {/* RAG Scope */}
                                                <div className="pt-2 border-t border-slate-100">
                                                    <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide">Escopo de busca</span>
                                                    <div className="grid grid-cols-3 gap-1 mt-1.5">
                                                        {([
                                                            { value: 'case_only' as const, label: 'Anexos' },
                                                            { value: 'case_and_global' as const, label: 'Anexos+Corpus' },
                                                            { value: 'global_only' as const, label: 'Corpus' },
                                                        ] as const).map((opt) => (
                                                            <button
                                                                key={opt.value}
                                                                onClick={() => setRagScope(opt.value)}
                                                                className={cn(
                                                                    "rounded-md px-2 py-1.5 text-[10px] font-medium transition-all border",
                                                                    ragScope === opt.value
                                                                        ? "bg-indigo-50 dark:bg-indigo-900/30 border-indigo-300 dark:border-indigo-600 text-indigo-700 dark:text-indigo-400"
                                                                        : "bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-600"
                                                                )}
                                                            >
                                                                {opt.label}
                                                            </button>
                                                        ))}
                                                    </div>
                                                </div>
                                            </div>
                                        </PopoverContent>
                                    </Popover>
                                </div>
                            </div>

                            {/* Resize Divider */}
                            {canvasState === 'normal' && (
                                <div
                                    role="separator"
                                    aria-orientation="vertical"
                                    aria-label="Redimensionar painel"
                                    className={cn(
                                        "relative w-3 cursor-col-resize bg-transparent",
                                        "before:absolute before:left-1/2 before:top-0 before:h-full before:w-px before:-translate-x-1/2 before:bg-slate-200/80 dark:before:bg-slate-700/80",
                                        isResizing && "bg-slate-100/80 dark:bg-slate-800/80"
                                    )}
                                    onPointerDown={handleDividerPointerDown}
                                    onPointerMove={handleDividerPointerMove}
                                    onPointerUp={handleDividerPointerUp}
                                    onPointerCancel={handleDividerPointerUp}
                                >
                                    <div className="absolute inset-0" />
                                </div>
                            )}

                            {/* Canvas Panel */}
                            {canvasState !== 'hidden' && (
                                <div className={cn(
                                    "min-h-0 h-full overflow-hidden transition-[flex-grow,width,opacity,transform] duration-300 ease-in-out",
                                    canvasState === 'expanded' ? "flex-1" : "flex-1"
                                )}>
                                    <CanvasContainer />
                                </div>
                            )}
                        </div>
                    </div>
                </TabsContent>

                {/* TAB: Documents - Central de Contexto */}
                <TabsContent value="documents">
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                        {/* Main: Documentos do Caso */}
                        <Card className="lg:col-span-2">
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    <Folder className="h-5 w-5" />
                                    Arquivos do Caso (RAG Local)
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                            {docsLoading ? (
                                <div className="text-sm text-muted-foreground py-4">Carregando documentos do caso...</div>
                            ) : caseDocuments.length > 0 ? (
                                <div className="space-y-2 mb-6">
                                    {caseDocuments.map((doc) => (
                                        <div
                                            key={doc.id}
                                            className="flex items-center justify-between gap-3 text-sm border rounded-lg px-4 py-3 bg-card hover:bg-muted/50 transition-colors"
                                        >
                                            <div className="flex items-center gap-3 min-w-0 flex-1">
                                                <FileText className="h-5 w-5 text-muted-foreground shrink-0" />
                                                <div className="min-w-0 flex-1">
                                                    <div className="font-medium truncate">{doc.name || doc.original_name}</div>
                                                    <div className="flex items-center gap-3 text-xs text-muted-foreground mt-1">
                                                        <span>{doc.created_at ? new Date(doc.created_at).toLocaleString('pt-BR') : '—'}</span>
                                                        <span className="text-muted-foreground/50">•</span>
                                                        <span>{doc.type || 'DOC'}</span>
                                                    </div>
                                                </div>
                                            </div>

                                            {/* RAG/Graph Status */}
                                            <div className="flex items-center gap-2 shrink-0">
                                                <div
                                                    className="flex items-center gap-1 px-2 py-1 rounded-full text-xs"
                                                    title={doc.rag_ingested
                                                        ? `RAG indexado em ${doc.rag_ingested_at ? new Date(doc.rag_ingested_at).toLocaleString('pt-BR') : ''}`
                                                        : 'Aguardando indexação RAG'}
                                                >
                                                    {doc.rag_ingested ? (
                                                        <>
                                                            <Database className="h-3 w-3 text-green-600" />
                                                            <span className="text-green-700">RAG</span>
                                                        </>
                                                    ) : (
                                                        <>
                                                            <Clock className="h-3 w-3 text-amber-500" />
                                                            <span className="text-amber-600">RAG</span>
                                                        </>
                                                    )}
                                                </div>
                                                <div
                                                    className="flex items-center gap-1 px-2 py-1 rounded-full text-xs"
                                                    title={doc.graph_ingested
                                                        ? `Grafo indexado em ${doc.graph_ingested_at ? new Date(doc.graph_ingested_at).toLocaleString('pt-BR') : ''}`
                                                        : 'Aguardando indexação Graph'}
                                                >
                                                    {doc.graph_ingested ? (
                                                        <>
                                                            <Network className="h-3 w-3 text-green-600" />
                                                            <span className="text-green-700">Graph</span>
                                                        </>
                                                    ) : (
                                                        <>
                                                            <Clock className="h-3 w-3 text-amber-500" />
                                                            <span className="text-amber-600">Graph</span>
                                                        </>
                                                    )}
                                                </div>
                                            </div>

                                            {/* Actions */}
                                            <div className="flex items-center gap-1 shrink-0">
                                                <Button
                                                    size="sm"
                                                    variant="ghost"
                                                    className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
                                                    title="Desanexar documento"
                                                    onClick={() => handleDetachDocument(doc.id, doc.name || doc.original_name)}
                                                >
                                                    <X className="h-4 w-4" />
                                                </Button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="text-sm text-muted-foreground mb-6 py-4">
                                    Nenhum documento associado a este caso ainda.
                                </div>
                            )}

                            {/* Upload Area */}
                            <div
                                className={`flex flex-col items-center justify-center p-12 border-2 border-dashed rounded-xl transition-colors ${
                                    isDragOver
                                        ? 'border-primary bg-primary/5'
                                        : 'border-muted bg-muted/10 hover:border-muted-foreground/30'
                                }`}
                                onDragOver={handleDragOver}
                                onDragLeave={handleDragLeave}
                                onDrop={handleDrop}
                            >
                                {uploading ? (
                                    <>
                                        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent mb-4" />
                                        <p className="text-sm text-muted-foreground">Enviando arquivos...</p>
                                    </>
                                ) : (
                                    <>
                                        <Upload className={`h-8 w-8 mb-4 ${isDragOver ? 'text-primary' : 'text-muted-foreground'}`} />
                                        <p className="text-sm text-muted-foreground mb-2 text-center">
                                            Arraste arquivos aqui ou clique para selecionar
                                        </p>
                                        <p className="text-xs text-muted-foreground/70 mb-4 text-center">
                                            Os arquivos serão automaticamente indexados no RAG local e no Grafo de Conhecimento
                                        </p>
                                        <label className="cursor-pointer">
                                            <input
                                                type="file"
                                                multiple
                                                className="hidden"
                                                onChange={(e) => e.target.files && handleFileUpload(e.target.files)}
                                                accept=".pdf,.docx,.doc,.txt,.html,.odt,.rtf"
                                            />
                                            <Button asChild>
                                                <span>
                                                    <Plus className="h-4 w-4 mr-2" />
                                                    Carregar Arquivos
                                                </span>
                                            </Button>
                                        </label>
                                    </>
                                )}
                            </div>

                            {/* Info */}
                            <div className="mt-4 flex items-start gap-2 text-xs text-muted-foreground p-3 rounded-lg bg-muted/30">
                                <CheckCircle className="h-4 w-4 shrink-0 mt-0.5 text-green-600" />
                                <div>
                                    <span className="font-medium text-foreground">Indexação automática:</span>{' '}
                                    Arquivos enviados são automaticamente processados e indexados no RAG (busca semântica) e no Grafo (relações entre entidades legais).
                                </div>
                            </div>
                            </CardContent>
                        </Card>

                        {/* Sidebar: Corpus e Escopo */}
                        <div className="space-y-4">
                            {/* RAG Scope */}
                            <Card>
                                <CardHeader className="pb-3">
                                    <CardTitle className="text-sm flex items-center gap-2">
                                        <Scale className="h-4 w-4" />
                                        Escopo de Busca
                                    </CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-2">
                                    {([
                                        { value: 'case_only' as const, label: 'Apenas Arquivos do Caso', desc: 'Busca apenas nos documentos anexados' },
                                        { value: 'case_and_global' as const, label: 'Caso + Corpus Global', desc: 'Combina arquivos do caso com base de conhecimento' },
                                        { value: 'global_only' as const, label: 'Apenas Corpus Global', desc: 'Busca apenas na base de conhecimento' },
                                    ] as const).map((opt) => (
                                        <button
                                            key={opt.value}
                                            onClick={() => setRagScope(opt.value)}
                                            className={cn(
                                                "w-full text-left rounded-lg p-3 border transition-all",
                                                ragScope === opt.value
                                                    ? "bg-indigo-50 dark:bg-indigo-900/30 border-indigo-300 dark:border-indigo-600"
                                                    : "bg-card border-border hover:border-muted-foreground/30"
                                            )}
                                        >
                                            <div className={cn(
                                                "text-sm font-medium",
                                                ragScope === opt.value ? "text-indigo-700 dark:text-indigo-400" : "text-foreground"
                                            )}>
                                                {opt.label}
                                            </div>
                                            <div className="text-xs text-muted-foreground mt-0.5">{opt.desc}</div>
                                        </button>
                                    ))}
                                </CardContent>
                            </Card>

                            {/* Corpus Global */}
                            <Card>
                                <CardHeader className="pb-3">
                                    <CardTitle className="text-sm flex items-center gap-2">
                                        <Database className="h-4 w-4 text-emerald-500" />
                                        Corpus Global
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    {collectionsLoading ? (
                                        <div className="text-sm text-muted-foreground py-2">Carregando...</div>
                                    ) : corpusCollections && corpusCollections.length > 0 ? (
                                        <div className="space-y-2">
                                            {corpusCollections.map((col) => (
                                                <div key={col.name} className="flex items-center justify-between text-sm py-1.5 px-2 rounded hover:bg-muted/50">
                                                    <span className="truncate">{col.display_name}</span>
                                                    <span className="text-xs text-muted-foreground ml-2 flex-shrink-0">{col.document_count} docs</span>
                                                </div>
                                            ))}
                                        </div>
                                    ) : (
                                        <div className="text-sm text-muted-foreground py-2">Nenhuma coleção disponível</div>
                                    )}
                                </CardContent>
                            </Card>

                            {/* Corpus Privado */}
                            <Card>
                                <CardHeader className="pb-3">
                                    <CardTitle className="text-sm flex items-center gap-2">
                                        <BookOpen className="h-4 w-4 text-indigo-500" />
                                        Corpus Privado
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    {projectsLoading ? (
                                        <div className="text-sm text-muted-foreground py-2">Carregando...</div>
                                    ) : corpusProjects?.items && corpusProjects.items.length > 0 ? (
                                        <div className="space-y-2">
                                            {corpusProjects.items.map((proj) => (
                                                <div key={proj.id} className="flex items-center justify-between text-sm py-1.5 px-2 rounded hover:bg-muted/50">
                                                    <span className="truncate">{proj.name}</span>
                                                    <span className="text-xs text-muted-foreground ml-2 flex-shrink-0">{proj.document_count} docs</span>
                                                </div>
                                            ))}
                                        </div>
                                    ) : (
                                        <div className="text-sm text-muted-foreground py-2">Nenhum projeto privado</div>
                                    )}
                                </CardContent>
                            </Card>
                        </div>
                    </div>
                </TabsContent>

                {/* TAB: Chat with Documents */}
                <TabsContent value="chat">
                    <div className="w-full">
                        <div className="flex h-[calc(100vh-140px)] min-h-[820px] gap-2">
                            {canvasState === 'expanded' ? (
                                <div className="flex-1 min-h-0 overflow-hidden rounded-xl border border-slate-200/60 bg-white shadow-sm">
                                    <CanvasContainer mode="chat" />
                                </div>
                            ) : (
                                <>
                                    <div className={`flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200/60 bg-white shadow-sm ${canvasState !== 'hidden' ? 'flex-[2.4]' : 'flex-1'}`}>
                                        {caseChatId ? (
                                            <ChatInterface chatId={caseChatId} renderBudgetModal={false} showCanvasButton />
                                        ) : (
                                            <div className="text-sm text-muted-foreground py-8 px-4">
                                                Preparando chat...
                                            </div>
                                        )}
                                    </div>
                                    {canvasState !== 'hidden' && (
                                        <div className="flex-1 min-h-0 overflow-hidden rounded-xl border border-slate-200/60 bg-white shadow-sm">
                                            <CanvasContainer mode="chat" />
                                        </div>
                                    )}
                                </>
                            )}
                        </div>
                    </div>
                </TabsContent>
            </Tabs>

            <MessageBudgetModal
                open={billingModal.open}
                quote={billingModal.quote}
                onClose={closeBillingModal}
                onSelectBudget={retryWithBudgetOverride}
            />

            {/* HIL Modal */}
            <OutlineApprovalModal
                isOpen={showOutlineModal}
                onClose={handleOutlineReject}
                onApprove={handleOutlineApprove}
                onReject={handleOutlineReject}
                initialSections={initialSections}
                documentType={useChatStore.getState().documentType || 'Documento'}
            />
        </div>
    );
}
