"use client";

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ArrowLeft, Save, Upload, Sparkles, Folder, MessageSquare } from 'lucide-react';
import { toast } from 'sonner';
import apiClient from '@/lib/api-client';
import { ContextSelector } from '@/components/dashboard/context-selector';
import { GeneratorWizard } from '@/components/dashboard/generator-wizard';
import { ChatInterface } from '@/components/dashboard/chat-interface';
import { useChatStore } from '@/stores/chat-store';
import { useContextStore } from '@/stores/context-store';

export default function CaseDetailPage() {
    const params = useParams();
    const router = useRouter();
    const id = params.id as string;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const [caseData, setCaseData] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    // Stores
    const { setThesis, contextFiles } = useChatStore();
    // const { clearItems } = useContextStore(); // Might use later

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
        <div className="container py-6 space-y-6 max-w-7xl mx-auto">
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

            <Tabs defaultValue="generation" className="space-y-4">
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
                        <GeneratorWizard caseId={id} caseThesis={caseData.thesis} />
                    </div>
                </TabsContent>

                {/* TAB: Documents */}
                <TabsContent value="documents">
                    <Card>
                        <CardHeader>
                            <CardTitle>Arquivos do Caso (RAG Local)</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="flex flex-col items-center justify-center p-12 border-2 border-dashed rounded-xl border-muted bg-muted/10">
                                <Upload className="h-8 w-8 text-muted-foreground mb-4" />
                                <p className="text-sm text-muted-foreground mb-4">
                                    Arraste arquivos ou pastas (Autos) para indexação local.
                                </p>
                                <Button>Carregar Arquivos</Button>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* TAB: Chat with Documents */}
                <TabsContent value="chat">
                    <div className="max-w-5xl mx-auto">
                        <ChatInterface caseId={id} caseContextFiles={contextFiles} />
                    </div>
                </TabsContent>
            </Tabs>
        </div>
    );
}
