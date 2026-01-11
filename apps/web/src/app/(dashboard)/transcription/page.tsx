'use client';

import { useState } from 'react';
import { Upload, FileAudio, FileVideo, Mic, CheckCircle, AlertCircle, Loader2, Download, FileText, FileType, Book, MessageSquare, ChevronUp, ChevronDown, X, Plus } from 'lucide-react';
import { toast } from 'sonner';
import apiClient from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
// import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
// import { Textarea } from '@/components/ui/textarea';
// import { ScrollArea } from '@/components/ui/scroll-area';
// import { Separator } from '@/components/ui/separator';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { QualityPanel } from '@/components/dashboard/quality-panel';
import { TranscriptionPromptPicker } from '@/components/dashboard/transcription-prompt-picker';

export default function TranscriptionPage() {
    const [files, setFiles] = useState<File[]>([]);
    const [mode, setMode] = useState('APOSTILA');
    const [thinkingLevel, setThinkingLevel] = useState('medium');
    const [customPrompt, setCustomPrompt] = useState('');
    const [highAccuracy, setHighAccuracy] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);
    const [selectedModel, setSelectedModel] = useState('gemini-3-flash-preview');
    const [result, setResult] = useState<string | null>(null);
    const [report, setReport] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState('preview');

    // SSE Progress State
    const [progressStage, setProgressStage] = useState<string>('');
    const [progressPercent, setProgressPercent] = useState<number>(0);
    const [progressMessage, setProgressMessage] = useState<string>('');
    const [logs, setLogs] = useState<{ timestamp: string; message: string }[]>([]);

    // HIL Audit State
    const [auditIssues, setAuditIssues] = useState<any[]>([]);
    const [selectedIssues, setSelectedIssues] = useState<Set<string>>(new Set());
    const [isApplyingFixes, setIsApplyingFixes] = useState(false);

    const handleFilesChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files.length > 0) {
            const newFiles = Array.from(e.target.files);
            setFiles(prev => [...prev, ...newFiles]);
        }
        e.target.value = '';
    };

    const removeFile = (index: number) => {
        setFiles(prev => prev.filter((_, i) => i !== index));
    };

    const moveFileUp = (index: number) => {
        if (index === 0) return;
        setFiles(prev => {
            const newFiles = [...prev];
            [newFiles[index - 1], newFiles[index]] = [newFiles[index], newFiles[index - 1]];
            return newFiles;
        });
    };

    const moveFileDown = (index: number) => {
        if (index === files.length - 1) return;
        setFiles(prev => {
            const newFiles = [...prev];
            [newFiles[index], newFiles[index + 1]] = [newFiles[index + 1], newFiles[index]];
            return newFiles;
        });
    };

    const processResponse = (content: string) => {
        // Extrair relatório (<!-- RELATÓRIO: ... -->)
        const reportRegex = /<!--\s*RELATÓRIO:([\s\S]*?)-->/i;
        const match = content.match(reportRegex);

        if (match) {
            setReport(match[1].trim());
        } else {
            setReport(null);
        }
        setResult(content);
    };

    const handleSubmit = async () => {
        if (files.length === 0) {
            toast.error('Selecione pelo menos um arquivo de áudio ou vídeo.');
            return;
        }

        setIsProcessing(true);
        setResult(null);
        setReport(null);
        setProgressStage('starting');
        setProgressPercent(0);
        setProgressMessage('Iniciando...');
        setLogs([]); // Clear logs

        const options = {
            mode,
            thinking_level: thinkingLevel,
            custom_prompt: customPrompt || undefined,
            model_selection: selectedModel,
            high_accuracy: highAccuracy
        };

        const onProgress = (stage: string, progress: number, message: string) => {
            console.log('[SSE Progress]', { stage, progress, message });
            setProgressStage(stage);
            setProgressPercent(progress);
            setProgressMessage(message);

            // Append log with timestamp
            const now = new Date();
            const timestamp = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;

            const percentLabel = typeof progress === 'number' ? `[${progress}%] ` : '';
            setLogs(prev => [...prev, { timestamp, message: `${percentLabel}${message}` }]);

            // Handle audit_complete event with issues
            if (stage === 'audit_complete') {
                try {
                    const auditData = JSON.parse(message);
                    if (auditData.issues && auditData.issues.length > 0) {
                        setAuditIssues(auditData.issues);
                        // Pre-select all issues by default
                        setSelectedIssues(new Set(auditData.issues.map((i: any) => i.id)));
                    }
                } catch (e) {
                    console.warn('Failed to parse audit data:', e);
                }
            }
        };

        const onError = (error: string) => {
            console.error(error);
            toast.error(`Erro ao transcrever: ${error}`);
            setIsProcessing(false);
            setProgressStage('');
        };

        if (files.length === 1) {
            // Single file - use regular endpoint
            await apiClient.transcribeVomoStream(
                files[0],
                options,
                onProgress,
                (content) => {
                    processResponse(content);
                    setIsProcessing(false);
                    setProgressPercent(100);
                    toast.success('Transcrição concluída com sucesso!');
                },
                onError
            );
        } else {
            // Multiple files - use batch endpoint
            await apiClient.transcribeVomoBatchStream(
                files,
                options,
                onProgress,
                (content, filenames, totalFiles) => {
                    processResponse(content);
                    setIsProcessing(false);
                    setProgressPercent(100);
                    toast.success(`${totalFiles} arquivos transcritos e unificados!`);
                },
                onError
            );
        }
    };

    const handleExportMD = () => {
        if (!result) return;
        const blob = new Blob([result], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `transcricao-${new Date().getTime()}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        toast.success('Arquivo Markdown baixado!');
    };

    // New: HIL Validation Helper
    const handleImportMD = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (event) => {
            const content = event.target?.result as string;
            if (content) {
                processResponse(content);
                toast.success('Arquivo carregado para revisão!');
            }
        };
        reader.readAsText(file);
    };
    const handleExportDocx = async () => {
        if (!result) return;
        try {
            const blob = await apiClient.exportDocx(result, `transcricao-${new Date().getTime()}.docx`);
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `transcricao-${new Date().getTime()}.docx`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            toast.success('Arquivo Word baixado!');
        } catch (error) {
            console.error(error);
            toast.error('Erro ao exportar Word.');
        }
    };

    const handleSaveToLibrary = async (andChat = false) => {
        if (!result || files.length === 0) return;
        const displayName = files.length === 1 ? files[0].name : `${files.length}_aulas_unificadas`;
        try {
            toast.info('Salvando na biblioteca...');
            const doc = await apiClient.createDocumentFromText({
                title: `Transcrição: ${displayName}`,
                content: result,
                tags: `transcricao,${mode.toLowerCase()}`
            });
            toast.success('Salvo na Biblioteca!');

            if (andChat) {
                // Criar chat e redirecionar
                toast.info('Criando chat...');
                const chat = await apiClient.createChat({
                    title: `Chat: ${displayName}`,
                    mode: 'DOCUMENT',
                    context: { initial_document_id: doc.id }
                });
                // Redireciona
                window.location.href = `/chat/${chat.id}?doc=${doc.id}`;
            }
        } catch (error: any) {
            console.error(error);
            toast.error('Erro ao salvar: ' + (error.message || 'Erro desconhecido'));
        }
    };

    const handleApplyFixes = async () => {
        if (!result || selectedIssues.size === 0) return;

        setIsApplyingFixes(true);
        try {
            const approvedIssues = auditIssues.filter(i => selectedIssues.has(i.id));

            const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api'}/transcription/apply-revisions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    content: result,
                    approved_issues: approvedIssues
                })
            });

            if (!response.ok) throw new Error('Falha ao aplicar correções');

            const data = await response.json();
            setResult(data.revised_content);
            setAuditIssues([]);  // Clear issues after applying
            setSelectedIssues(new Set());
            toast.success(`${data.changes_made} correções aplicadas!`);
        } catch (error: any) {
            console.error(error);
            toast.error('Erro ao aplicar correções: ' + (error.message || 'Erro desconhecido'));
        } finally {
            setIsApplyingFixes(false);
        }
    };

    const toggleIssue = (id: string) => {
        setSelectedIssues(prev => {
            const newSet = new Set(prev);
            if (newSet.has(id)) {
                newSet.delete(id);
            } else {
                newSet.add(id);
            }
            return newSet;
        });
    };

    return (
        <div className="flex h-full flex-col gap-6 p-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Transcrição de Aulas (VomoMLX)</h1>
                    <p className="text-muted-foreground">
                        Transforme vídeos e áudios em apostilas ou transcrições fiéis usando IA.
                    </p>
                </div>
            </div>

            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3 h-full">
                {/* Configuração */}
                <Card className="col-span-1 h-fit">
                    <CardHeader>
                        <CardTitle>Configuração</CardTitle>
                        <CardDescription>Ajuste os parâmetros de processamento.</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">

                        {/* Upload */}
                        <div className="space-y-2">
                            <Label>Arquivos (Áudio/Vídeo)</Label>
                            <div className="flex items-center gap-2">
                                <div className="relative w-full">
                                    <Button variant="outline" className="w-full justify-start text-left font-normal">
                                        <Plus className="mr-2 h-4 w-4" />
                                        Adicionar arquivos...
                                    </Button>
                                    <input
                                        id="file-upload"
                                        type="file"
                                        multiple
                                        className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                                        accept="audio/*,video/*,.mp3,.wav,.m4a,.aac,.mp4,.mov,.mkv"
                                        onClick={(e) => {
                                            (e.currentTarget as HTMLInputElement).value = '';
                                        }}
                                        onChange={handleFilesChange}
                                    />
                                </div>
                            </div>
                            {files.length > 0 && (
                                <div className="space-y-1 mt-2 max-h-40 overflow-y-auto">
                                    {files.map((file, idx) => (
                                        <div key={idx} className="flex items-center gap-1 text-xs bg-muted/50 rounded px-2 py-1">
                                            <span className="font-mono text-muted-foreground w-5">{idx + 1}.</span>
                                            {file.type.startsWith('video') ? <FileVideo className="h-3 w-3 flex-shrink-0" /> : <FileAudio className="h-3 w-3 flex-shrink-0" />}
                                            <span className="truncate flex-1" title={file.name}>{file.name}</span>
                                            <span className="text-muted-foreground flex-shrink-0">{(file.size / (1024 * 1024)).toFixed(1)}MB</span>
                                            <Button variant="ghost" size="icon" className="h-5 w-5" onClick={() => moveFileUp(idx)} disabled={idx === 0}>
                                                <ChevronUp className="h-3 w-3" />
                                            </Button>
                                            <Button variant="ghost" size="icon" className="h-5 w-5" onClick={() => moveFileDown(idx)} disabled={idx === files.length - 1}>
                                                <ChevronDown className="h-3 w-3" />
                                            </Button>
                                            <Button variant="ghost" size="icon" className="h-5 w-5 text-destructive" onClick={() => removeFile(idx)}>
                                                <X className="h-3 w-3" />
                                            </Button>
                                        </div>
                                    ))}
                                    <p className="text-xs text-muted-foreground mt-1">
                                        {files.length > 1 ? `📚 ${files.length} arquivos serão unificados na ordem acima` : ''}
                                    </p>
                                </div>
                            )}
                        </div>

                        <div className="border-t border-border" />

                        {/* Modo */}
                        <div className="space-y-2">
                            <Label>Modo de Formatação</Label>
                            <select
                                className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                                value={mode}
                                onChange={(e) => setMode(e.target.value)}
                            >
                                <option value="APOSTILA">📚 Apostila (Didático)</option>
                                <option value="FIDELIDADE">🎯 Fidelidade (Literal)</option>
                                <option value="RAW">📝 Raw (Apenas Transcrição)</option>
                            </select>
                        </div>

                        {/* High Accuracy Switch */}
                        <div className="flex items-center justify-between space-x-2 border p-3 rounded-md">
                            <Label htmlFor="high-accuracy" className="flex flex-col space-y-1">
                                <span>Alta Precisão (Beam Search)</span>
                                <span className="font-normal text-xs text-muted-foreground">
                                    Mais lento, mas ideal para termos jurídicos complexos.
                                </span>
                            </Label>
                            <Switch
                                id="high-accuracy"
                                checked={highAccuracy}
                                onCheckedChange={setHighAccuracy}
                            />
                        </div>

                        {/* Thinking Level */}
                        <div className="space-y-2">
                            <Label>Nível de Pensamento (Thinking Budget)</Label>
                            <select
                                className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                                value={thinkingLevel}
                                onChange={(e) => setThinkingLevel(e.target.value)}
                            >
                                <option value="low">Baixo (Rápido - 8k tokens)</option>
                                <option value="medium">Médio (Padrão - 16k tokens)</option>
                                <option value="high">Alto (Complexo - 32k tokens)</option>
                            </select>
                        </div>

                        {/* Seleção de Modelo */}
                        <div className="space-y-2">
                            <Label>Modelo de IA</Label>
                            <select
                                className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                                value={selectedModel}
                                onChange={(e) => setSelectedModel(e.target.value)}
                            >
                                <option value="gemini-3-flash-preview">Gemini 3 Flash (Recomendado)</option>
                                <option value="gpt-5-mini">GPT-5 Mini</option>
                            </select>
                        </div>

                        {/* Prompt Customizado */}
                        <div className="space-y-2">
                            <Label>Prompt Customizado (Opcional)</Label>
                            <p className="text-[10px] text-muted-foreground mt-1 mb-2">
                                ⚠️ Nota: Ao customizar, defina apenas <strong>ESTILO e TABELAS</strong>. O sistema preserva automaticamente papéis, estrutura e regras anti-duplicação.
                            </p>
                            <TranscriptionPromptPicker
                                onReplace={(tpl) => setCustomPrompt(tpl)}
                                onAppend={(tpl) => setCustomPrompt((prev) => (prev ? `${prev}\n\n${tpl}` : tpl))}
                            />
                            <textarea
                                placeholder="Sobrescreva as instruções padrão..."
                                className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 resize-none h-32"
                                value={customPrompt}
                                onChange={(e) => setCustomPrompt(e.target.value)}
                            />
                        </div>

                        <Button
                            className="w-full"
                            onClick={handleSubmit}
                            disabled={isProcessing || files.length === 0}
                        >
                            {isProcessing ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Processando...
                                </>
                            ) : (
                                <>
                                    <Mic className="mr-2 h-4 w-4" /> Transcrever
                                </>
                            )}
                        </Button>

                        <div className="relative w-full mt-4 border-t pt-4">
                            <Label className="mb-2 block text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                                Validação HIL (Offline)
                            </Label>
                            <div className="relative">
                                <input
                                    type="file"
                                    accept=".md,.txt"
                                    onChange={handleImportMD}
                                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                                />
                                <Button variant="secondary" className="w-full" disabled={isProcessing}>
                                    <Upload className="mr-2 h-4 w-4" />
                                    Carregar Markdown Existente
                                </Button>
                            </div>
                            <p className="text-[10px] text-muted-foreground mt-1 text-center">
                                Carregue um arquivo local (.md) para usar o Painel de Qualidade.
                            </p>
                        </div>

                    </CardContent>
                </Card>

                {/* Resultado */}
                <Card className="col-span-1 md:col-span-1 lg:col-span-2 flex flex-col h-full min-h-[500px]">
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <div className="space-y-1">
                            <CardTitle>Resultado</CardTitle>
                            <CardDescription>
                                {result ? 'Visualização do documento gerado.' : 'Aguardando processamento...'}
                            </CardDescription>
                        </div>
                        {result && (
                            <div className="flex items-center gap-2">
                                <Button variant="outline" size="sm" onClick={() => handleSaveToLibrary(false)}>
                                    <Book className="mr-2 h-4 w-4" /> Salvar
                                </Button>
                                <Button size="sm" onClick={() => handleSaveToLibrary(true)}>
                                    <MessageSquare className="mr-2 h-4 w-4" /> Conversar
                                </Button>
                                <div className="h-4 w-[1px] bg-border mx-1" />
                                <Button variant="ghost" size="icon" onClick={handleExportMD} title="Baixar Markdown">
                                    <FileText className="h-4 w-4" />
                                </Button>
                                <Button variant="ghost" size="icon" onClick={handleExportDocx} title="Baixar Word">
                                    <FileType className="h-4 w-4" />
                                </Button>
                            </div>
                        )}
                    </CardHeader>
                    <CardContent className="flex-1 p-0">
                        {result ? (
                            <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-col h-[600px] w-full">
                                <div className="px-4 pt-2 border-b">
                                    <TabsList className="w-full justify-start">
                                        <TabsTrigger value="preview">Visualização</TabsTrigger>
                                        {auditIssues.length > 0 && <TabsTrigger value="hil" className="text-orange-600">⚠️ Revisão HIL ({auditIssues.length})</TabsTrigger>}
                                        <TabsTrigger value="quality">Controle de Qualidade</TabsTrigger>
                                        {report && <TabsTrigger value="report">Relatório IA</TabsTrigger>}
                                    </TabsList>
                                </div>

                                {/* HIL Audit Issues Tab */}
                                <TabsContent value="hil" className="flex-1 overflow-y-auto p-4 m-0 space-y-4">
                                    <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
                                        <h3 className="font-semibold text-orange-800 mb-2 flex items-center gap-2">
                                            <AlertCircle className="h-5 w-5" />
                                            Issues Detectados pela Auditoria
                                        </h3>
                                        <p className="text-sm text-orange-700 mb-4">
                                            Selecione os issues que deseja corrigir. A IA revisará o documento com base nas suas escolhas.
                                        </p>

                                        <div className="space-y-2 max-h-[300px] overflow-y-auto">
                                            {auditIssues.map((issue) => (
                                                <label
                                                    key={issue.id}
                                                    className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${selectedIssues.has(issue.id)
                                                            ? 'bg-orange-100 border-orange-300'
                                                            : 'bg-white border-gray-200 hover:bg-gray-50'
                                                        }`}
                                                >
                                                    <input
                                                        type="checkbox"
                                                        checked={selectedIssues.has(issue.id)}
                                                        onChange={() => toggleIssue(issue.id)}
                                                        className="mt-1 h-4 w-4 rounded border-gray-300 text-orange-600 focus:ring-orange-500"
                                                    />
                                                    <div className="flex-1">
                                                        <div className="flex items-center gap-2">
                                                            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${issue.severity === 'warning' ? 'bg-yellow-100 text-yellow-800' : 'bg-blue-100 text-blue-800'
                                                                }`}>
                                                                {issue.type}
                                                            </span>
                                                        </div>
                                                        <p className="text-sm text-gray-700 mt-1">{issue.description}</p>
                                                        <p className="text-xs text-gray-500 mt-1">💡 {issue.suggestion}</p>
                                                    </div>
                                                </label>
                                            ))}
                                        </div>

                                        <div className="flex justify-between items-center mt-4 pt-4 border-t border-orange-200">
                                            <span className="text-sm text-orange-700">
                                                {selectedIssues.size} de {auditIssues.length} selecionados
                                            </span>
                                            <Button
                                                onClick={handleApplyFixes}
                                                disabled={selectedIssues.size === 0 || isApplyingFixes}
                                                className="bg-orange-600 hover:bg-orange-700"
                                            >
                                                {isApplyingFixes ? (
                                                    <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Aplicando...</>
                                                ) : (
                                                    <><CheckCircle className="mr-2 h-4 w-4" /> Aplicar Correções</>
                                                )}
                                            </Button>
                                        </div>
                                    </div>
                                </TabsContent>

                                <TabsContent value="preview" className="flex-1 overflow-hidden p-0 m-0 data-[state=active]:flex flex-col">
                                    <div className="flex-1 overflow-y-auto p-4 bg-muted/50">
                                        <pre className="whitespace-pre-wrap text-sm font-mono text-foreground">
                                            {result.replace(/<!--\s*RELATÓRIO:[\s\S]*?-->/i, '')}
                                        </pre>
                                    </div>
                                </TabsContent>

                                <TabsContent value="quality" className="flex-1 overflow-y-auto p-4 m-0">
                                    <QualityPanel
                                        rawContent={result} // TODO: In a real flow, we'd have separate Raw vs Formatted. For now, using result as base.
                                        formattedContent={result}
                                        documentName={files[0]?.name || 'Documento'}
                                        onContentUpdated={setResult}
                                    />
                                </TabsContent>

                                {report && (
                                    <TabsContent value="report" className="flex-1 overflow-y-auto p-4 m-0">
                                        <div className="bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 p-3 rounded-md text-sm font-medium whitespace-pre-wrap">
                                            {report}
                                        </div>
                                    </TabsContent>
                                )}
                            </Tabs>
                        ) : (
                            <div className="flex h-full items-center justify-center text-muted-foreground p-8">
                                {isProcessing ? (
                                    <div className="text-center p-8 w-full max-w-2xl mx-auto">
                                        <Loader2 className="h-12 w-12 animate-spin mx-auto mb-4 text-primary" />
                                        <p className="text-lg font-medium mb-2">{progressMessage}</p>

                                        <div className="w-full bg-muted rounded-full h-3 overflow-hidden mb-6">
                                            <div
                                                className="bg-primary h-3 rounded-full transition-all duration-500 ease-out"
                                                style={{ width: `${progressPercent}%` }}
                                            />
                                        </div>

                                        <div className="flex justify-between text-xs text-muted-foreground mt-2 mb-6">
                                            <span className={progressStage === 'audio_optimization' ? 'text-primary font-medium' : ''}>
                                                🔊 Áudio
                                            </span>
                                            <span className={progressStage === 'transcription' ? 'text-primary font-medium' : ''}>
                                                🎙️ Transcrição
                                            </span>
                                            <span className={progressStage === 'formatting' ? 'text-primary font-medium' : ''}>
                                                ✨ Formatação
                                            </span>
                                        </div>

                                        {/* Terminal Logs */}
                                        <div className="mt-4 text-left font-mono text-xs">
                                            <div className="bg-black/90 text-green-400 p-3 rounded-md h-48 overflow-y-auto border border-green-900/50 shadow-inner flex flex-col-reverse">
                                                {logs.length === 0 ? (
                                                    <span className="opacity-50">AGUARDANDO LOGS...</span>
                                                ) : (
                                                    logs.slice().reverse().map((log, i) => (
                                                        <div key={i} className="whitespace-pre-wrap break-words border-b border-white/5 last:border-0 pb-1 mb-1">
                                                            <span className="text-gray-500 mr-2">
                                                                [{log.timestamp}]
                                                            </span>
                                                            <span dangerouslySetInnerHTML={{
                                                                __html: log.message
                                                                    .replace(/\[(.*?)\]/g, '<span class="text-yellow-400 font-bold">[$1]</span>')
                                                                    .replace(/(Erro|Falha)/gi, '<span class="text-red-500 font-bold">$1</span>')
                                                                    .replace(/(Sucesso|Concluído)/gi, '<span class="text-green-400 font-bold">$1</span>')
                                                            }} />
                                                        </div>
                                                    ))
                                                )}
                                            </div>
                                            <p className="text-[10px] text-muted-foreground mt-1 text-right">
                                                Output em tempo real do servidor
                                            </p>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="text-center">
                                        <FileAudio className="h-12 w-12 mx-auto mb-4 opacity-20" />
                                        <p>Faça upload de um arquivo para começar.</p>
                                    </div>
                                )}
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
