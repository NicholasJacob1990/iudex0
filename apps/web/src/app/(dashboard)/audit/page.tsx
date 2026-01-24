'use client';

import { useState } from 'react';
import { Upload, FileText, CheckCircle, AlertTriangle, Download, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api-client';
import { useUploadLimits } from '@/lib/use-upload-limits';

export default function AuditPage() {
    const [file, setFile] = useState<File | null>(null);
    const [isUploading, setIsUploading] = useState(false);
    const [resultBlob, setResultBlob] = useState<Blob | null>(null);
    const { maxUploadLabel, maxUploadBytes } = useUploadLimits();

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files[0]) {
            const nextFile = e.target.files[0];
            if (nextFile.size > maxUploadBytes) {
                toast.error(`Arquivo excede o limite de ${maxUploadLabel}.`);
                e.target.value = '';
                return;
            }
            setFile(nextFile);
            setResultBlob(null); // Reset previous result
        }
    };

    const handleDragOver = (e: React.DragEvent) => {
        e.preventDefault();
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            const nextFile = e.dataTransfer.files[0];
            if (nextFile.size > maxUploadBytes) {
                toast.error(`Arquivo excede o limite de ${maxUploadLabel}.`);
                return;
            }
            setFile(nextFile);
            setResultBlob(null);
        }
    };

    const handleAudit = async () => {
        if (!file) return;

        setIsUploading(true);
        try {
            const blob = await apiClient.runAudit(file);
            setResultBlob(blob);
            toast.success('Auditoria concluída com sucesso!');
        } catch (error) {
            console.error('Audit error:', error);
            toast.error('Erro ao realizar auditoria. Tente novamente.');
        } finally {
            setIsUploading(false);
        }
    };

    const handleDownload = () => {
        if (!resultBlob) return;

        // Create download link
        const url = window.URL.createObjectURL(resultBlob);
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', `Auditoria_${file?.name || 'documento'}.docx`);
        document.body.appendChild(link);
        link.click();
        link.remove();
    };

    return (
        <div className="flex flex-col gap-6 p-6 max-w-4xl mx-auto h-full">
            <div className="text-center space-y-2">
                <h1 className="font-display text-3xl font-bold text-foreground">Auditoria Jurídica</h1>
                <p className="text-muted-foreground">
                    Envie sua peça para análise automática de estrutura, lógica e citações.
                </p>
            </div>

            <div className="flex flex-col gap-8 flex-1">
                {/* Upload Area */}
                <div
                    className={`flex flex-col items-center justify-center p-12 border-2 border-dashed rounded-xl transition-colors cursor-pointer bg-white/50 hover:bg-white ${file ? 'border-primary/50 bg-primary/5' : 'border-outline/40'
                        }`}
                    onDragOver={handleDragOver}
                    onDrop={handleDrop}
                    onClick={() => document.getElementById('file-upload')?.click()}
                >
                    <input
                        id="file-upload"
                        type="file"
                        className="hidden"
                        accept=".pdf,.docx,.txt"
                        onChange={handleFileChange}
                    />

                    <div className="bg-sand p-4 rounded-full mb-4">
                        {file ? (
                            <FileText className="h-8 w-8 text-primary" />
                        ) : (
                            <Upload className="h-8 w-8 text-muted-foreground" />
                        )}
                    </div>

                    {file ? (
                        <div className="text-center">
                            <p className="font-medium text-lg">{file.name}</p>
                            <p className="text-sm text-muted-foreground">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                            <Button variant="ghost" className="mt-2 text-destructive hover:text-destructive" onClick={(e) => { e.stopPropagation(); setFile(null); setResultBlob(null); }}>
                                Remover
                            </Button>
                        </div>
                    ) : (
                        <div className="text-center space-y-1">
                            <p className="font-medium text-lg text-foreground">Clique para enviar ou arraste aqui</p>
                            <p className="text-sm text-muted-foreground">PDF, DOCX ou TXT (até {maxUploadLabel})</p>
                        </div>
                    )}
                </div>

                {/* Action Button */}
                <div className="flex justify-center">
                    <Button
                        size="lg"
                        className="w-full max-w-sm rounded-full text-lg h-12"
                        onClick={handleAudit}
                        disabled={!file || isUploading}
                    >
                        {isUploading ? (
                            <>
                                <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                                Auditando Documento...
                            </>
                        ) : (
                            <>
                                Inspecionar Peça
                                <CheckCircle className="ml-2 h-5 w-5" />
                            </>
                        )}
                    </Button>
                </div>

                {/* Result Area */}
                {resultBlob && (
                    <Card className="p-6 bg-white border-green-200 shadow-sm animate-in fade-in slide-in-from-bottom-4">
                        <div className="flex items-start gap-4">
                            <div className="bg-green-100 p-3 rounded-full">
                                <CheckCircle className="h-6 w-6 text-green-600" />
                            </div>
                            <div className="flex-1">
                                <h3 className="text-lg font-semibold text-foreground mb-1">Auditoria Concluída!</h3>
                                <p className="text-sm text-muted-foreground mb-4">
                                    Seu relatório de auditoria foi gerado com sucesso. Ele contém análise de estrutura, detecção de falhas lógicas e verificação de citações.
                                </p>
                                <Button onClick={handleDownload} className="gap-2 bg-green-600 hover:bg-green-700 text-white">
                                    <Download className="h-4 w-4" />
                                    Baixar Relatório (.docx)
                                </Button>
                            </div>
                        </div>
                    </Card>
                )}
            </div>
        </div>
    );
}
