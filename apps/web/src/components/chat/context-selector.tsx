import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, FileText, X, Paperclip, Mic, Link as LinkIcon, Gavel } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';

interface ContextFile {
    id: string;
    name: string;
    size: number;
    type: string;
}

interface ContextSelectorProps {
    onContextChange?: (files: ContextFile[]) => void;
}

export function ContextSelector({ onContextChange }: ContextSelectorProps) {
    const [files, setFiles] = useState<ContextFile[]>([]);
    const [isExpanded, setIsExpanded] = useState(false);
    const [activeTab, setActiveTab] = useState('files');

    const onDrop = useCallback((acceptedFiles: File[]) => {
        const newFiles = acceptedFiles.map(file => ({
            id: Math.random().toString(36).substring(7),
            name: file.name,
            size: file.size,
            type: file.type
        }));

        setFiles(prev => {
            const updated = [...prev, ...newFiles];
            onContextChange?.(updated);
            return updated;
        });
    }, [onContextChange]);

    const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop });

    const removeFile = (id: string) => {
        setFiles(prev => {
            const updated = prev.filter(f => f.id !== id);
            onContextChange?.(updated);
            return updated;
        });
    };

    return (
        <div className="border-b border-border/50 bg-background/50 p-4 backdrop-blur-sm">
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                    <Paperclip className="h-4 w-4 text-primary" />
                    <span>Contexto</span>
                    <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] text-primary">
                        {files.length}
                    </span>
                </div>
                <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 text-xs"
                    onClick={() => setIsExpanded(!isExpanded)}
                >
                    {isExpanded ? 'Ocultar' : 'Adicionar'}
                </Button>
            </div>

            {isExpanded && (
                <div className="animate-in slide-in-from-top-2 duration-200">
                    <Tabs defaultValue="files" className="w-full" onValueChange={setActiveTab}>
                        <TabsList className="grid w-full grid-cols-4 mb-4 bg-muted/50">
                            <TabsTrigger value="files" className="text-xs"><FileText className="h-3 w-3 mr-2" />Arquivos</TabsTrigger>
                            <TabsTrigger value="audio" className="text-xs"><Mic className="h-3 w-3 mr-2" />Áudio</TabsTrigger>
                            <TabsTrigger value="url" className="text-xs"><LinkIcon className="h-3 w-3 mr-2" />Link</TabsTrigger>
                            <TabsTrigger value="juris" className="text-xs"><Gavel className="h-3 w-3 mr-2" />Juris</TabsTrigger>
                        </TabsList>

                        <TabsContent value="files" className="space-y-3 mt-0">
                            <div
                                {...getRootProps()}
                                className={cn(
                                    "cursor-pointer rounded-lg border-2 border-dashed border-muted-foreground/25 p-4 text-center transition-colors hover:bg-muted/50",
                                    isDragActive && "border-primary bg-primary/5"
                                )}
                            >
                                <input {...getInputProps()} />
                                <Upload className="mx-auto h-6 w-6 text-muted-foreground" />
                                <p className="mt-2 text-xs text-muted-foreground">
                                    Arraste arquivos ou clique para selecionar
                                </p>
                                <p className="text-[10px] text-muted-foreground/60 mt-1">
                                    PDF, DOCX, TXT (Max 50MB)
                                </p>
                            </div>
                        </TabsContent>

                        <TabsContent value="audio" className="mt-0">
                            <div className="rounded-lg border border-dashed border-muted-foreground/25 p-8 text-center">
                                <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-muted">
                                    <Mic className="h-6 w-6 text-muted-foreground" />
                                </div>
                                <p className="text-xs text-muted-foreground">Gravar ou carregar áudio</p>
                                <Button variant="outline" size="sm" className="mt-3 text-xs">
                                    Iniciar Gravação
                                </Button>
                            </div>
                        </TabsContent>

                        <TabsContent value="url" className="mt-0">
                            <div className="space-y-3">
                                <div className="flex gap-2">
                                    <Input placeholder="Cole a URL do processo ou notícia..." className="h-8 text-xs" />
                                    <Button size="sm" className="h-8 text-xs">Adicionar</Button>
                                </div>
                                <p className="text-[10px] text-muted-foreground">
                                    O Iudex irá ler e extrair o conteúdo da página.
                                </p>
                            </div>
                        </TabsContent>

                        <TabsContent value="juris" className="mt-0">
                            <div className="space-y-3">
                                <div className="flex gap-2">
                                    <Input placeholder="Digite palavras-chave ou nº do processo..." className="h-8 text-xs" />
                                    <Button size="sm" className="h-8 text-xs">Buscar</Button>
                                </div>
                                <div className="rounded-md bg-muted/30 p-2 text-[10px] text-muted-foreground text-center">
                                    Conectado ao Jusbrasil e Tribunais Superiores
                                </div>
                            </div>
                        </TabsContent>
                    </Tabs>

                    {files.length > 0 && activeTab === 'files' && (
                        <div className="mt-3 space-y-2 max-h-[150px] overflow-y-auto pr-1">
                            {files.map((file) => (
                                <div
                                    key={file.id}
                                    className="flex items-center justify-between rounded-md border border-border bg-background p-2 text-xs group"
                                >
                                    <div className="flex items-center gap-2 overflow-hidden">
                                        <FileText className="h-3 w-3 text-primary flex-shrink-0" />
                                        <span className="truncate">{file.name}</span>
                                    </div>
                                    <button
                                        onClick={() => removeFile(file.id)}
                                        className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
                                    >
                                        <X className="h-3 w-3" />
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
