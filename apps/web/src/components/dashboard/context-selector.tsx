import { Button } from '@/components/ui/button';
import { FileText, Upload, BookOpen, Scale, X, Link as LinkIcon, Mic, Search, File, Folder as FolderIcon } from 'lucide-react';
import { toast } from 'sonner';
import { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';

import { useContextStore } from '@/stores/context-store';
import { useChatStore } from '@/stores/chat-store';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ChevronDown, Bot, Sparkles as SparklesIcon, Layout } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';

export function ContextSelector() {
    const { items, addItem, removeItem, activeTab, setActiveTab } = useContextStore();
    const { selectedModel, setSelectedModel,
        gptModel, setGptModel,
        claudeModel, setClaudeModel,
        effortLevel, setEffortLevel,
        minPages, maxPages, setPageRange, resetPageRange,
        useMultiAgent,
        useTemplates, setUseTemplates,
        templateFilters, setTemplateFilters,
        promptExtra, setPromptExtra,
        documentType, setDocumentType,
        thesis, setThesis,
        formattingOptions, setFormattingOptions
    } = useChatStore();
    const [ocrEnabled, setOcrEnabled] = useState(false);
    const [rigorousSearch, setRigorousSearch] = useState(false);
    const effortRangeLabel = effortLevel === 1 ? '5-8' : effortLevel === 2 ? '10-15' : '20-30';
    const pageRangeLabel = (minPages > 0 || maxPages > 0)
        ? `${minPages}-${maxPages} págs`
        : `Auto (${effortRangeLabel} págs)`;
    const applyPresetRange = (level: number, min: number, max: number) => {
        setEffortLevel(level);
        setPageRange({ minPages: min, maxPages: max });
    };

    const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files[0]) {
            const file = e.target.files[0];
            try {
                // Real API Upload
                // Assumes apiClient.uploadDocument returns { id: string, ... }
                // Use default import if apiClient is default exported, or named import.
                // Dynamic import to avoid SSR issues if any, or just standard import.
                const { apiClient } = await import('@/lib/api-client');
                const response = await apiClient.uploadDocument(file, { ocr: ocrEnabled });

                addItem({
                    id: response.id || Math.random().toString(), // Fallback if ID missing
                    type: 'file',
                    name: file.name,
                    meta: ocrEnabled ? 'OCR Ativado' : undefined
                });
                toast.success('Arquivo enviado com sucesso!');
            } catch (error) {
                console.error('Upload failed:', error);
                toast.error('Erro ao enviar arquivo.');
            }
        }
    };

    // Helper to allow directory selection
    const onFolderInputClick = (e: React.MouseEvent) => {
        const input = document.getElementById('folder-upload') as HTMLInputElement;
        if (input) {
            input.value = '';
            input.click();
        }
    }

    const handleFolderChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files.length > 0) {
            const files = Array.from(e.target.files);
            const folderName = files[0].webkitRelativePath.split('/')[0] || 'Pasta sem nome';

            // In a real implementation, we would upload all files or the path
            // For now, we mock the folder item creation
            addItem({
                id: Math.random().toString(),
                type: 'folder',
                name: folderName,
                meta: `${files.length} arquivos (RAG Local)`
            });
            toast.success(`Pasta "${folderName}" adicionada como Autos (RAG Local)!`);
        }
    };

    const handleRemove = (id: string) => {
        removeItem(id);
    };

    return (
        <div className="flex flex-col gap-4 rounded-2xl border border-outline/30 bg-sand/20 p-4">
            <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase text-muted-foreground">Adicionar Contexto</span>
            </div>

            <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                <TabsList className="w-full justify-start bg-transparent p-0 border-b border-outline/20 rounded-none h-auto">
                    <TabsTrigger value="files" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 py-2 text-xs">Arquivos</TabsTrigger>
                    <TabsTrigger value="library" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 py-2 text-xs">Biblioteca</TabsTrigger>
                    <TabsTrigger value="audio" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 py-2 text-xs">Áudio</TabsTrigger>
                    <TabsTrigger value="link" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 py-2 text-xs">Link</TabsTrigger>
                    <TabsTrigger value="juris" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 py-2 text-xs">Juris</TabsTrigger>
                </TabsList>

                <TabsContent value="files" className="mt-4 space-y-4">
                    <div className="flex gap-2">
                        {/* File Upload */}
                        <div
                            className="flex-1 h-32 cursor-pointer flex flex-col items-center justify-center rounded-xl border border-dashed border-outline/40 bg-white/50 transition-colors hover:bg-white"
                            onClick={() => document.getElementById('context-upload')?.click()}
                        >
                            <input
                                id="context-upload"
                                type="file"
                                className="hidden"
                                accept=".pdf,.docx,.txt"
                                onChange={handleFileChange}
                            />
                            <Upload className="h-6 w-6 text-muted-foreground/50 mb-2" />
                            <p className="text-sm font-medium text-foreground">Arquivo Único</p>
                            <p className="text-[10px] text-muted-foreground">PDF, DOCX</p>
                        </div>

                        {/* Folder Upload (RAG Local) */}
                        <div
                            className="flex-1 h-32 cursor-pointer flex flex-col items-center justify-center rounded-xl border border-dashed border-blue-300/50 bg-blue-50/30 transition-colors hover:bg-blue-50/50"
                            onClick={onFolderInputClick}
                        >
                            <input
                                id="folder-upload"
                                type="file"
                                className="hidden"
                                // @ts-ignore - webkitdirectory is not standard in React types yet
                                webkitdirectory=""
                                directory=""
                                onChange={handleFolderChange}
                            />
                            <FolderIcon className="h-6 w-6 text-blue-500/70 mb-2" />
                            <p className="text-sm font-medium text-foreground">Autos (Pasta)</p>
                            <p className="text-[10px] text-muted-foreground">RAG Local (Processo)</p>
                        </div>
                    </div>
                    <div className="flex items-center space-x-2">
                        <Switch id="ocr-mode" checked={ocrEnabled} onCheckedChange={setOcrEnabled} />
                        <Label htmlFor="ocr-mode" className="text-xs font-medium">Ler imagens/scanned (OCR)</Label>
                    </div>
                </TabsContent>

                <TabsContent value="library" className="mt-4 space-y-4">
                    <div className="relative">
                        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                        <Input placeholder="Buscar modelos..." className="pl-9 bg-white" />
                    </div>
                    <div className="flex items-center space-x-2">
                        <Switch id="rigorous-mode" checked={rigorousSearch} onCheckedChange={setRigorousSearch} />
                        <Label htmlFor="rigorous-mode" className="text-xs font-medium">Busca Rigorosa</Label>
                    </div>
                </TabsContent>

                <TabsContent value="audio" className="mt-4 space-y-4">
                    <div
                        className="flex h-32 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-orange-300/60 bg-orange-50/30 transition-colors hover:bg-orange-50"
                        onClick={() => document.getElementById('audio-upload')?.click()}
                    >
                        <input
                            id="audio-upload"
                            type="file"
                            className="hidden"
                            accept=".mp3,.wav,.m4a,.aac,.ogg,.flac,.mp4,.avi,.mov,.wmv,.webm,.mkv"
                            onChange={async (e) => {
                                if (e.target.files && e.target.files[0]) {
                                    const file = e.target.files[0];
                                    toast.info(`Enviando ${file.name} para transcrição...`);
                                    try {
                                        const { apiClient } = await import('@/lib/api-client');
                                        const response = await apiClient.uploadDocument(file, { transcribe: true });
                                        addItem({
                                            id: response.id || Math.random().toString(),
                                            type: 'audio',
                                            name: file.name,
                                            meta: 'Transcrição automática'
                                        });
                                        toast.success('Áudio/Vídeo transcrito com sucesso!');
                                    } catch (error) {
                                        console.error('Transcription failed:', error);
                                        toast.error('Erro ao transcrever mídia.');
                                    }
                                }
                            }}
                        />
                        <div className="bg-orange-100 p-3 rounded-full mb-2">
                            <Mic className="h-6 w-6 text-orange-600" />
                        </div>
                        <p className="text-sm font-medium text-foreground">Arraste áudio/vídeo ou clique</p>
                        <p className="text-xs text-muted-foreground">MP3, MP4, MKV, WAV (transcrição automática)</p>
                    </div>
                    <p className="text-[10px] text-muted-foreground text-center">
                        Powered by Whisper MLX - O áudio será transcrito automaticamente e adicionado ao contexto.
                    </p>
                </TabsContent>

                <TabsContent value="link" className="mt-4 space-y-4">
                    <div className="flex gap-2">
                        <Input placeholder="Cole uma URL aqui..." className="bg-white" />
                        <Button size="sm" variant="secondary">Adicionar</Button>
                    </div>
                </TabsContent>

                <TabsContent value="juris" className="mt-4 space-y-4">
                    <div className="relative">
                        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                        <Input placeholder="Buscar jurisprudência..." className="pl-9 bg-white" />
                    </div>
                </TabsContent>
            </Tabs>

            {/* AI Selection Section */}
            <div className="mt-4 pt-4 border-t border-outline/20">
                <div className="flex items-center gap-2 mb-3">
                    <SparklesIcon className="h-3.5 w-3.5 text-amber-500" />
                    <span className="text-xs font-semibold uppercase text-muted-foreground">Seleção de IA (Comitê de Agentes)</span>
                </div>
                <p className="text-[10px] text-muted-foreground -mt-2 mb-3">
                    Usado na geração em <strong>Comitê</strong> (Multi‑Agente). Não confundir com <strong>Comparar modelos</strong> (modo do chat).
                </p>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    {/* Orchestrator (Gemini) */}
                    <div className="space-y-1.5">
                        <Label className="text-[10px] uppercase text-muted-foreground ml-1">Juiz (Gemini)</Label>
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <Button variant="outline" className="w-full h-9 justify-between rounded-xl border-outline/30 bg-white/50 px-3 text-xs font-medium hover:bg-white">
                                    <div className="flex items-center gap-2">
                                        <Bot className="h-3.5 w-3.5 text-primary" />
                                        <span className="truncate">
                                            {selectedModel === 'gemini-3-pro' ? 'Gemini 3 Pro' :
                                                selectedModel === 'gemini-3-flash' ? 'Gemini 3 Flash' : 'Selecionar Juiz'}
                                        </span>
                                    </div>
                                    <ChevronDown className="h-3 w-3 opacity-50" />
                                </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent className="w-56">
                                <DropdownMenuItem onClick={() => setSelectedModel('gemini-3-pro')}>Gemini 3 Pro (Raciocínio)</DropdownMenuItem>
                                <DropdownMenuItem onClick={() => setSelectedModel('gemini-3-flash')}>Gemini 3 Flash (Velocidade)</DropdownMenuItem>
                            </DropdownMenuContent>
                        </DropdownMenu>
                    </div>

                    {/* Agent GPT */}
                    <div className="space-y-1.5">
                        <Label className="text-[10px] uppercase text-muted-foreground ml-1">Agente GPT</Label>
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <Button variant="outline" className="w-full h-9 justify-between rounded-xl border-outline/30 bg-white/50 px-3 text-xs font-medium hover:bg-white" disabled={!useMultiAgent}>
                                    <div className="flex items-center gap-2">
                                        <SparklesIcon className="h-3.5 w-3.5 text-blue-500" />
                                        <span className="truncate">
                                            {gptModel === 'gpt-5.2' ? 'GPT-5.2' :
                                                gptModel === 'gpt-5' ? 'GPT-5' : 'Selecionar GPT'}
                                        </span>
                                    </div>
                                    <ChevronDown className="h-3 w-3 opacity-50" />
                                </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent className="w-56">
                                <DropdownMenuItem onClick={() => setGptModel('gpt-5.2')}>GPT-5.2 (Standard)</DropdownMenuItem>
                                <DropdownMenuItem onClick={() => setGptModel('gpt-5')}>GPT-5</DropdownMenuItem>
                            </DropdownMenuContent>
                        </DropdownMenu>
                    </div>

                    {/* Agent Claude */}
                    <div className="space-y-1.5">
                        <Label className="text-[10px] uppercase text-muted-foreground ml-1">Agente Claude</Label>
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <Button variant="outline" className="w-full h-9 justify-between rounded-xl border-outline/30 bg-white/50 px-3 text-xs font-medium hover:bg-white" disabled={!useMultiAgent}>
                                    <div className="flex items-center gap-2">
                                        <SparklesIcon className="h-3.5 w-3.5 text-orange-500" />
                                        <span className="truncate">
                                            {claudeModel === 'claude-4.5-sonnet' ? 'Claude 4.5 Sonnet' :
                                                claudeModel === 'claude-4.5-opus' ? 'Claude 4.5 Opus' : 'Selecionar Claude'}
                                        </span>
                                    </div>
                                    <ChevronDown className="h-3 w-3 opacity-50" />
                                </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent className="w-56">
                                <DropdownMenuItem onClick={() => setClaudeModel('claude-4.5-sonnet')}>Claude 4.5 Sonnet</DropdownMenuItem>
                                <DropdownMenuItem onClick={() => setClaudeModel('claude-4.5-opus')}>Claude 4.5 Opus (Heavy Duty)</DropdownMenuItem>
                            </DropdownMenuContent>
                        </DropdownMenu>
                    </div>
                </div>

                {/* --- NEW SECTION: GENERATION CONFIG --- */}
                <div className="mt-4 pt-4 border-t border-outline/20 space-y-4">
                    <div className="flex items-center gap-2 mb-1">
                        <Layout className="h-3.5 w-3.5 text-blue-500" />
                        <span className="text-xs font-semibold uppercase text-muted-foreground">Configurações de Geração</span>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {/* Intervalo de páginas */}
                        <div className="space-y-2 p-3 rounded-xl border border-outline/20 bg-white/30">
                            <div className="flex justify-between items-center">
                                <Label className="text-[10px] uppercase text-muted-foreground">Intervalo de páginas</Label>
                                <span className="text-xs font-mono font-bold">{pageRangeLabel}</span>
                            </div>
                            <div className="grid grid-cols-2 gap-2">
                                <div className="space-y-1">
                                    <Label className="text-[10px] text-muted-foreground">Mín.</Label>
                                    <Input
                                        type="number"
                                        min={0}
                                        className="h-7 text-[11px] bg-white"
                                        placeholder="Auto"
                                        value={minPages === 0 ? '' : minPages}
                                        onChange={(e) => {
                                            const next = parseInt(e.target.value, 10);
                                            setPageRange({ minPages: Number.isNaN(next) ? 0 : next });
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
                                        value={maxPages === 0 ? '' : maxPages}
                                        onChange={(e) => {
                                            const next = parseInt(e.target.value, 10);
                                            setPageRange({ maxPages: Number.isNaN(next) ? 0 : next });
                                        }}
                                    />
                                </div>
                            </div>
                            <div className="flex gap-1 pt-1">
                                <button
                                    type="button"
                                    onClick={() => resetPageRange()}
                                    className={`flex-1 h-8 rounded-lg text-xs font-medium border transition-colors ${minPages === 0 && maxPages === 0
                                            ? 'bg-primary text-primary-foreground border-primary'
                                            : 'bg-white text-muted-foreground border-outline/30 hover:bg-white/80'
                                        }`}
                                >
                                    Auto
                                </button>
                                <button
                                    type="button"
                                    onClick={() => applyPresetRange(1, 5, 8)}
                                    className={`flex-1 h-8 rounded-lg text-xs font-medium border transition-colors ${minPages === 5 && maxPages === 8
                                            ? 'bg-primary text-primary-foreground border-primary'
                                            : 'bg-white text-muted-foreground border-outline/30 hover:bg-white/80'
                                        }`}
                                >
                                    Curta
                                </button>
                                <button
                                    type="button"
                                    onClick={() => applyPresetRange(2, 10, 15)}
                                    className={`flex-1 h-8 rounded-lg text-xs font-medium border transition-colors ${minPages === 10 && maxPages === 15
                                            ? 'bg-primary text-primary-foreground border-primary'
                                            : 'bg-white text-muted-foreground border-outline/30 hover:bg-white/80'
                                        }`}
                                >
                                    Média
                                </button>
                                <button
                                    type="button"
                                    onClick={() => applyPresetRange(3, 20, 30)}
                                    className={`flex-1 h-8 rounded-lg text-xs font-medium border transition-colors ${minPages === 20 && maxPages === 30
                                            ? 'bg-primary text-primary-foreground border-primary'
                                            : 'bg-white text-muted-foreground border-outline/30 hover:bg-white/80'
                                        }`}
                                >
                                    Longa
                                </button>
                            </div>
                            <p className="text-[10px] text-muted-foreground">
                                Se vazio, usa o nível de esforço para estimar o tamanho.
                            </p>
                        </div>

                        {/* RAG Sources & Top-K */}
                        <div className="space-y-1.5 p-3 rounded-xl border border-outline/20 bg-white/30">
                            <Label className="text-[10px] uppercase text-muted-foreground ml-1">Fontes RAG & Top-K</Label>
                            <div className="space-y-2">
                                <div className="flex gap-2 flex-wrap">
                                    {['lei', 'juris', 'pecas_modelo'].map(source => (
                                        <div key={source} className="flex items-center space-x-1">
                                            <Checkbox
                                                id={`source-${source}`}
                                                checked={useChatStore().ragSources.includes(source)}
                                                onCheckedChange={(checked) => {
                                                    const current = useChatStore().ragSources;
                                                    if (checked) useChatStore().setRagSources([...current, source]);
                                                    else useChatStore().setRagSources(current.filter(s => s !== source));
                                                }}
                                            />
                                            <Label htmlFor={`source-${source}`} className="text-[10px] uppercase">{source}</Label>
                                        </div>
                                    ))}
                                </div>
                                <div className="flex items-center gap-2 mt-2">
                                    <Label className="text-[10px] text-muted-foreground whitespace-nowrap">Top-K:</Label>
                                    <Input
                                        type="number"
                                        className="h-6 w-16 text-[10px] bg-white text-center"
                                        value={useChatStore().ragTopK}
                                        onChange={(e) => useChatStore().setRagTopK(parseInt(e.target.value) || 5)}
                                    />
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {/* Tipo de Peça */}
                        <div className="space-y-1.5">
                            <Label className="text-[10px] uppercase text-muted-foreground ml-1">Tipo de Peça (--mode)</Label>
                            <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                    <Button variant="outline" className="w-full h-9 justify-between rounded-xl border-outline/30 bg-white/50 px-3 text-xs font-medium hover:bg-white">
                                        <span>{useChatStore().documentType}</span>
                                        <ChevronDown className="h-3 w-3 opacity-50" />
                                    </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent className="w-56">
                                    {['PETICAO_INICIAL', 'CONTESTACAO', 'RECURSO', 'PARECER', 'OUTRO'].map(type => (
                                        <DropdownMenuItem key={type} onClick={() => setDocumentType(type)}>
                                            {type}
                                        </DropdownMenuItem>
                                    ))}
                                </DropdownMenuContent>
                            </DropdownMenu>
                        </div>

                        {/* Modelos de Peça (RAG) */}
                        <div className="space-y-1.5 p-3 rounded-xl border border-blue-200 bg-blue-50/20">
                            <div className="flex items-center justify-between">
                                <Label className="text-[10px] uppercase text-blue-600 font-bold">Modelos de Peça (RAG)</Label>
                                <Switch
                                    checked={useTemplates}
                                    onCheckedChange={setUseTemplates}
                                />
                            </div>

                            {useTemplates && (
                                <div className="space-y-2 pt-2">
                                    <div className="flex gap-2">
                                        <div className="flex-1 space-y-1">
                                            <Label className="text-[9px] text-muted-foreground ml-1">Área</Label>
                                            <Input
                                                className="h-7 text-[10px] bg-white"
                                                placeholder="Ex: Tributário"
                                                value={templateFilters.area}
                                                onChange={(e) => setTemplateFilters({ area: e.target.value })}
                                            />
                                        </div>
                                        <div className="flex-1 space-y-1">
                                            <Label className="text-[9px] text-muted-foreground ml-1">Rito</Label>
                                            <Input
                                                className="h-7 text-[10px] bg-white"
                                                placeholder="Ex: Ordinário"
                                                value={templateFilters.rito}
                                                onChange={(e) => setTemplateFilters({ rito: e.target.value })}
                                            />
                                        </div>
                                    </div>
                                    <div className="flex items-center space-x-2">
                                        <Checkbox
                                            id="clause-bank-only"
                                            checked={templateFilters.apenasClauseBank}
                                            onCheckedChange={(checked) => setTemplateFilters({ apenasClauseBank: !!checked })}
                                        />
                                        <Label htmlFor="clause-bank-only" className="text-[10px] text-muted-foreground">Apenas Clause Bank</Label>
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Formatting Options */}
                        <div className="space-y-1.5">
                            <Label className="text-[10px] uppercase text-muted-foreground ml-1">Formatação</Label>
                            <div className="grid grid-cols-1 gap-2 p-2 rounded-xl border border-outline/20 bg-white/30">
                                <div className="flex items-center space-x-2">
                                    <Checkbox
                                        id="include-toc"
                                        checked={useChatStore().formattingOptions.includeToc}
                                        onCheckedChange={(checked) => useChatStore().setFormattingOptions({ includeToc: !!checked })}
                                    />
                                    <Label htmlFor="include-toc" className="text-[10px] font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">Sumário (TOC)</Label>
                                </div>
                                <div className="flex items-center space-x-2">
                                    <Checkbox
                                        id="include-summaries"
                                        checked={useChatStore().formattingOptions.includeSummaries}
                                        onCheckedChange={(checked) => useChatStore().setFormattingOptions({ includeSummaries: !!checked })}
                                    />
                                    <Label htmlFor="include-summaries" className="text-[10px] font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">Resumos por Seção</Label>
                                </div>
                                <div className="flex items-center space-x-2">
                                    <Checkbox
                                        id="include-summary-table"
                                        checked={useChatStore().formattingOptions.includeSummaryTable}
                                        onCheckedChange={(checked) => useChatStore().setFormattingOptions({ includeSummaryTable: !!checked })}
                                    />
                                    <Label htmlFor="include-summary-table" className="text-[10px] font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">Tabela de Resumo</Label>
                                </div>
                                <div className="flex items-center space-x-2 pt-1 border-t border-outline/10">
                                    <Checkbox
                                        id="run-audit"
                                        checked={useChatStore().audit}
                                        onCheckedChange={(checked) => useChatStore().setAudit(!!checked)}
                                        className="data-[state=checked]:bg-indigo-600 data-[state=checked]:border-indigo-600"
                                    />
                                    <Label htmlFor="run-audit" className="text-[10px] font-bold text-indigo-700 leading-none cursor-pointer flex items-center gap-1">
                                        <Scale className="h-3 w-3" />
                                        Rodar Auditoria Jurídica (Relatório)
                                    </Label>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Tese / Instruções */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="space-y-1.5">
                            <Label className="text-[10px] uppercase text-muted-foreground ml-1">Tese / Instruções Livres (--tese)</Label>
                            <textarea
                                className="w-full min-h-[80px] rounded-xl border border-outline/30 bg-white/50 p-3 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                                placeholder="Descreva a tese jurídica ou instruções específicas para esta peça..."
                                value={thesis}
                                onChange={(e) => setThesis(e.target.value)}
                            />
                        </div>
                        <div className="space-y-1.5">
                            <Label className="text-[10px] uppercase text-muted-foreground ml-1">Prompt Adicional (Intent)</Label>
                            <textarea
                                className="w-full min-h-[80px] rounded-xl border border-outline/30 bg-white/50 p-3 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
                                placeholder="E.g. 'Use modelos tributários e priorize blocos de preliminares...'"
                                value={promptExtra}
                                onChange={(e) => setPromptExtra(e.target.value)}
                            />
                        </div>
                    </div>
                </div>
            </div>

            {items.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-2 pt-4 border-t border-outline/20">
                    {items.map((item) => (
                        <div
                            key={item.id}
                            className="flex items-center gap-2 rounded-lg border border-outline/40 bg-white px-3 py-1.5 text-xs shadow-sm"
                        >
                            {item.type === 'file' && <FileText className="h-3 w-3 text-blue-500" />}
                            {item.type === 'model' && <BookOpen className="h-3 w-3 text-purple-500" />}
                            {item.type === 'legislation' && <Scale className="h-3 w-3 text-green-500" />}
                            {item.type === 'audio' && <Mic className="h-3 w-3 text-orange-500" />}
                            {item.type === 'link' && <LinkIcon className="h-3 w-3 text-cyan-500" />}
                            {item.type === 'link' && <LinkIcon className="h-3 w-3 text-cyan-500" />}
                            {item.type === 'jurisprudence' && <Scale className="h-3 w-3 text-red-500" />}
                            {item.type === 'folder' && <FolderIcon className="h-3 w-3 text-indigo-500" />}
                            <div className="flex flex-col">
                                <span className="max-w-[150px] truncate font-medium">{item.name}</span>
                                {item.meta && <span className="text-[10px] text-muted-foreground">{item.meta}</span>}
                            </div>
                            <button onClick={() => handleRemove(item.id)} className="ml-1 text-muted-foreground hover:text-destructive">
                                <X className="h-3 w-3" />
                            </button>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
