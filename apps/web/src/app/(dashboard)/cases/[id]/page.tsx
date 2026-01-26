"use client";

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ArrowLeft, Save, Upload, Sparkles, Folder, MessageSquare, FileText, CheckCircle, Clock, X, Plus, Database, Network } from 'lucide-react';
import { toast } from 'sonner';
import apiClient from '@/lib/api-client';
import { GeneratorWizard } from '@/components/dashboard/generator-wizard';
import { ChatInterface } from '@/components/chat/chat-interface';
import { useChatStore } from '@/stores/chat-store';
import { useContextStore } from '@/stores/context-store';
import { MessageBudgetModal } from '@/components/billing/message-budget-modal';
import { useCanvasStore } from '@/stores/canvas-store';
import { CanvasContainer } from '@/components/dashboard';

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
    const canvasState = useCanvasStore((s) => s.state);

    // Stores
    const {
        setThesis,
        setContext,
        billingModal,
        closeBillingModal,
        retryWithBudgetOverride,
        createChat,
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

                {/* TAB: Generation */}
                <TabsContent value="generation">
                    <div className="max-w-5xl mx-auto">
                        <GeneratorWizard caseId={id} caseThesis={caseData.thesis} chatId={caseGeneratorChatId ?? undefined} />
                    </div>
                </TabsContent>

                {/* TAB: Documents */}
                <TabsContent value="documents">
                    <Card>
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
        </div>
    );
}
