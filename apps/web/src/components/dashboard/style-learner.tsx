import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Upload, FileText, CheckCircle2, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useUploadLimits } from '@/lib/use-upload-limits';

export function StyleLearner() {
    const [isDragging, setIsDragging] = useState(false);
    const [file, setFile] = useState<File | null>(null);
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [analysisComplete, setAnalysisComplete] = useState(false);
    const { maxUploadLabel, maxUploadBytes } = useUploadLimits();

    const handleDragOver = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(true);
    };

    const handleDragLeave = () => {
        setIsDragging(false);
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        const droppedFile = e.dataTransfer.files[0];
        if (droppedFile && (droppedFile.type === 'application/pdf' || droppedFile.name.endsWith('.docx'))) {
            if (droppedFile.size > maxUploadBytes) {
                toast.error(`Arquivo excede o limite de ${maxUploadLabel}.`);
                return;
            }
            setFile(droppedFile);
        } else {
            toast.error('Por favor, envie apenas arquivos PDF ou DOCX.');
        }
    };

    const handleAnalyze = () => {
        if (!file) return;
        setIsAnalyzing(true);

        // Simulate AI analysis
        setTimeout(() => {
            setIsAnalyzing(false);
            setAnalysisComplete(true);
            toast.success('Estilo de escrita analisado com sucesso!');
        }, 2000);
    };

    return (
        <div className="rounded-3xl border border-white/70 bg-white/90 p-6 shadow-soft">
            <div className="mb-6">
                <h2 className="font-display text-xl text-foreground flex items-center gap-2">
                    <FileText className="h-5 w-5 text-indigo-500" />
                    Perfis de Redação
                </h2>
                <p className="text-sm text-muted-foreground">
                    Crie perfis de escrita baseados em suas petições anteriores.
                </p>
            </div>

            {!analysisComplete ? (
                <div className="space-y-4">
                    <div
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                        className={cn(
                            "relative flex flex-col items-center justify-center rounded-2xl border-2 border-dashed p-8 transition-all",
                            isDragging ? "border-indigo-500 bg-indigo-50/50" : "border-outline/30 bg-sand/30",
                            file ? "border-indigo-500/50 bg-indigo-50/30" : ""
                        )}
                    >
                        {file ? (
                            <div className="flex flex-col items-center gap-2">
                                <FileText className="h-10 w-10 text-indigo-500" />
                                <p className="font-medium text-foreground">{file.name}</p>
                                <p className="text-xs text-muted-foreground">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="mt-2 text-destructive hover:text-destructive"
                                    onClick={() => setFile(null)}
                                >
                                    Remover
                                </Button>
                            </div>
                        ) : (
                            <div className="flex flex-col items-center gap-2 text-center">
                                <Upload className="h-10 w-10 text-muted-foreground" />
                                <p className="font-medium text-foreground">Arraste suas petições aqui</p>
                                <p className="text-xs text-muted-foreground">PDF ou DOCX até {maxUploadLabel}</p>
                                <Button variant="outline" size="sm" className="mt-2">
                                    Selecionar Arquivo
                                </Button>
                            </div>
                        )}
                    </div>

                    <Button
                        className="w-full rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white"
                        disabled={!file || isAnalyzing}
                        onClick={handleAnalyze}
                    >
                        {isAnalyzing ? (
                            <span className="flex items-center gap-2">
                                <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                                Analisando Estilo...
                            </span>
                        ) : (
                            'Analisar e Aprender Estilo'
                        )}
                    </Button>
                </div>
            ) : (
                <div className="flex flex-col items-center justify-center py-8 text-center animate-in fade-in zoom-in duration-300">
                    <div className="mb-4 rounded-full bg-green-100 p-3">
                        <CheckCircle2 className="h-8 w-8 text-green-600" />
                    </div>
                    <h3 className="text-lg font-bold text-foreground">Estilo Aprendido!</h3>
                    <p className="mb-6 text-sm text-muted-foreground max-w-xs">
                        A IA identificou seu padrão de escrita: <strong>Formal, Conciso e com Citações Diretas</strong>.
                    </p>
                    <Button
                        variant="outline"
                        onClick={() => {
                            setFile(null);
                            setAnalysisComplete(false);
                        }}
                    >
                        Analisar Outro Documento
                    </Button>
                </div>
            )}
        </div>
    );
}
