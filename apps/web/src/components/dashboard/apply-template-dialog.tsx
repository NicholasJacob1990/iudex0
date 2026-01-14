import { useState, useRef } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Upload, FileText, Download, Loader2, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import apiClient from '@/lib/api-client';

interface ApplyTemplateDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

interface TemplateVariable {
    name: string;
    value: string;
}

export function ApplyTemplateDialog({ open, onOpenChange }: ApplyTemplateDialogProps) {
    const fileInputRef = useRef<HTMLInputElement>(null);

    const [step, setStep] = useState<'upload' | 'fill' | 'download'>('upload');
    const [file, setFile] = useState<File | null>(null);
    const [loading, setLoading] = useState(false);
    const [variables, setVariables] = useState<TemplateVariable[]>([]);
    const [generatedFile, setGeneratedFile] = useState<{ filename: string; downloadUrl: string } | null>(null);

    const handleDownload = async () => {
        if (!generatedFile?.downloadUrl) return;
        setLoading(true);
        try {
            // downloadUrl vem como "/api/documents/download/generated/<file>"
            // O ApiClient já está configurado com baseURL ".../api", então precisamos remover o prefixo "/api".
            const endpoint = generatedFile.downloadUrl.replace(/^\/api/, '');
            const res = await apiClient.fetchWithAuth(endpoint, { method: 'GET' });
            if (!res.ok) {
                throw new Error(`Falha ao baixar (HTTP ${res.status})`);
            }
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = generatedFile.filename || 'documento.docx';
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        } catch (e) {
            console.error(e);
            toast.error('Erro ao baixar documento');
        } finally {
            setLoading(false);
        }
    };

    const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const selectedFile = e.target.files?.[0];
        if (!selectedFile) return;

        if (!selectedFile.name.endsWith('.docx')) {
            toast.error("Formato inválido", { description: "Por favor, selecione um arquivo DOCX." });
            return;
        }

        setFile(selectedFile);
        extractVariables(selectedFile);
    };

    const extractVariables = async (fileToProcess: File) => {
        setLoading(true);
        try {
            const res = await apiClient.extractTemplateVariables(fileToProcess);
            const extractedVars = (res.variables || []).map((v: string) => ({
                name: v,
                value: ''
            }));

            if (extractedVars.length === 0) {
                toast.warning("Nenhuma variável encontrada", { description: "O arquivo não contém variáveis no formato {{variavel}}." });
            }

            setVariables(extractedVars);
            setStep('fill');
        } catch (error) {
            console.error(error);
            toast.error("Erro ao processar arquivo", { description: "Não foi possível extrair as variáveis do template." });
            setFile(null);
        } finally {
            setLoading(false);
        }
    };

    const handleVariableChange = (name: string, value: string) => {
        setVariables(prev =>
            prev.map(v => v.name === name ? { ...v, value } : v)
        );
    };

    const handleApplyTemplate = async () => {
        if (!file) return;

        setLoading(true);
        try {
            const variablesDict = variables.reduce((acc, curr) => ({ ...acc, [curr.name]: curr.value }), {} as Record<string, string>);
            const response = await apiClient.applyTemplate(file, variablesDict);

            if (response.success) {
                setGeneratedFile({
                    filename: response.generated_file,
                    downloadUrl: response.download_url
                });
                setStep('download');
                toast.success("Template aplicado!", { description: `${response.replacements} substituições realizadas com sucesso.` });
            }
        } catch (error) {
            console.error(error);
            toast.error("Erro ao aplicar template", { description: "Ocorreu um erro ao gerar o documento." });
        } finally {
            setLoading(false);
        }
    };

    const handleReset = () => {
        setStep('upload');
        setFile(null);
        setVariables([]);
        setGeneratedFile(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[500px]">
                <DialogHeader>
                    <DialogTitle>Aplicar Template DOCX</DialogTitle>
                    <DialogDescription>
                        Gere um DOCX automaticamente a partir de um template com variáveis (ex.: <span className="font-mono">{'{{'}nome_cliente{'}}'}</span>).
                        <span className="block mt-1">Passo a passo: 1) Envie o template 2) Preencha os campos 3) Baixe o documento gerado.</span>
                    </DialogDescription>
                </DialogHeader>

                <div className="py-4">
                    {step === 'upload' && (
                        <div className="flex flex-col items-center justify-center p-8 border-2 border-dashed rounded-lg border-muted-foreground/25 hover:bg-muted/50 transition-colors cursor-pointer"
                            onClick={() => fileInputRef.current?.click()}>
                            <input
                                type="file"
                                ref={fileInputRef}
                                className="hidden"
                                accept=".docx"
                                onChange={handleFileSelect}
                            />
                            <div className="flex flex-col items-center gap-2 text-center">
                                <div className="p-3 rounded-full bg-primary/10">
                                    <Upload className="w-6 h-6 text-primary" />
                                </div>
                                <div>
                                    <p className="font-medium">Clique para selecionar</p>
                                    <p className="text-sm text-muted-foreground">Arquivos .docx com variáveis {'{{'} ... {'}}'}</p>
                                </div>
                            </div>
                        </div>
                    )}

                    {step === 'fill' && (
                        <div className="space-y-4">
                            <div className="flex items-center gap-2 p-3 rounded-md bg-muted/50">
                                <FileText className="w-4 h-4 text-primary" />
                                <span className="text-sm font-medium truncate flex-1">{file?.name}</span>
                                <Button variant="ghost" size="icon" onClick={handleReset} className="h-6 w-6">
                                    <RefreshCw className="w-3 h-3" />
                                </Button>
                            </div>

                            <div className="max-h-[300px] overflow-y-auto space-y-3 pr-2">
                                {variables.length > 0 ? (
                                    variables.map((variable) => (
                                        <div key={variable.name} className="space-y-1">
                                            <Label htmlFor={variable.name}>{variable.name}</Label>
                                            <Input
                                                id={variable.name}
                                                value={variable.value}
                                                onChange={(e) => handleVariableChange(variable.name, e.target.value)}
                                                placeholder={`Valor para ${variable.name}`}
                                            />
                                        </div>
                                    ))
                                ) : (
                                    <div className="text-center py-8 text-muted-foreground">
                                        Nenhuma variável encontrada neste arquivo.
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {step === 'download' && generatedFile && (
                        <div className="flex flex-col items-center justify-center py-8 space-y-4">
                            <div className="p-4 rounded-full bg-green-100 dark:bg-green-900/20">
                                <FileText className="w-8 h-8 text-green-600 dark:text-green-400" />
                            </div>
                            <div className="text-center">
                                <h3 className="font-medium text-lg">Documento Gerado!</h3>
                                <p className="text-sm text-muted-foreground">{generatedFile.filename}</p>
                            </div>
                            <Button className="w-full max-w-xs" onClick={handleDownload} disabled={loading}>
                                {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                                {!loading && <Download className="w-4 h-4 mr-2" />}
                                Baixar Documento
                            </Button>
                            <Button variant="ghost" onClick={handleReset}>
                                Aplicar outro template
                            </Button>
                        </div>
                    )}
                </div>

                <DialogFooter>
                    {step === 'upload' && (
                        <Button variant="outline" onClick={() => onOpenChange(false)}>
                            Cancelar
                        </Button>
                    )}

                    {step === 'fill' && (
                        <>
                            <Button variant="outline" onClick={handleReset}>
                                Voltar
                            </Button>
                            <Button onClick={handleApplyTemplate} disabled={loading}>
                                {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                                Gerar Documento
                            </Button>
                        </>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
