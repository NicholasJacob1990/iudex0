"use client";

import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Checkbox } from "@/components/ui/checkbox";
import { Loader2, CheckCircle, AlertTriangle, XCircle, Wrench, FileText, RefreshCw, ShieldCheck, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import apiClient from "@/lib/api-client";

interface PendingFix {
    id: string;
    type: string;
    description: string;
    action: string;
    severity: string;
    fingerprint?: string;
}

interface QualityReport {
    document_name: string;
    validated_at: string;
    approved: boolean;
    score: number;
    omissions: string[];
    distortions: string[];
    structural_issues: string[];
    observations: string;
    error?: string;
}

interface QualityPanelProps {
    rawContent: string;
    formattedContent: string;
    documentName: string;
    onContentUpdated?: (newContent: string) => void;
}

interface AnalyzeResponse {
    document_name: string;
    analyzed_at: string;
    total_issues: number;
    pending_fixes: PendingFix[];
    requires_approval: boolean;
    // v4.0 Content Issues
    compression_ratio?: number;
    compression_warning?: string;
    missing_laws?: string[];
    missing_sumulas?: string[];
    missing_decretos?: string[];
    missing_julgados?: string[];
}

export function QualityPanel({
    rawContent,
    formattedContent,
    documentName,
    onContentUpdated,
}: QualityPanelProps) {
    const [isValidating, setIsValidating] = useState(false);
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [isApplying, setIsApplying] = useState(false);
    const [report, setReport] = useState<QualityReport | null>(null);
    const [analysisResult, setAnalysisResult] = useState<AnalyzeResponse | null>(null);
    const [pendingFixes, setPendingFixes] = useState<PendingFix[]>([]);
    const [selectedFixes, setSelectedFixes] = useState<Set<string>>(new Set());
    const [suggestions, setSuggestions] = useState<string | null>(null);

    const getScoreColor = (score: number) => {
        if (score >= 8) return "text-green-600";
        if (score >= 6) return "text-yellow-600";
        return "text-red-600";
    };

    const getScoreIcon = (score: number) => {
        if (score >= 8) return <CheckCircle className="w-5 h-5 text-green-600" />;
        if (score >= 6) return <AlertTriangle className="w-5 h-5 text-yellow-600" />;
        return <XCircle className="w-5 h-5 text-red-600" />;
    };

    const handleValidate = async () => {
        setIsValidating(true);
        setReport(null);
        setSuggestions(null);
        setPendingFixes([]);

        try {
            const result = await apiClient.validateDocumentQuality({
                raw_content: rawContent,
                formatted_content: formattedContent,
                document_name: documentName,
            });

            setReport(result);

            if (result.score >= 8) {
                toast.success(`Qualidade aprovada! Nota: ${result.score}/10`);
            } else if (result.score >= 6) {
                toast.warning(`Qualidade intermediária. Nota: ${result.score}/10`);
            } else {
                toast.error(`Problemas detectados. Nota: ${result.score}/10`);
            }
        } catch (error: any) {
            toast.error("Erro ao validar: " + (error.message || "Desconhecido"));
        } finally {
            setIsValidating(false);
        }
    };

    const handleAnalyzeStructure = async () => {
        setIsAnalyzing(true);
        setPendingFixes([]);
        setAnalysisResult(null);
        setSelectedFixes(new Set());

        try {
            const result = (await apiClient.analyzeDocumentHIL({
                content: formattedContent,
                document_name: documentName,
            })) as AnalyzeResponse;

            setAnalysisResult(result);

            if (result.pending_fixes && result.pending_fixes.length > 0) {
                setPendingFixes(result.pending_fixes);
                // Pre-select all fixes by default
                setSelectedFixes(new Set(result.pending_fixes.map((f: PendingFix) => f.id)));
                toast.info(`${result.total_issues} problema(s) encontrado(s).`);
            } else {
                toast.success("Nenhum problema estrutural crítico encontrado!");
            }
        } catch (error: any) {
            toast.error("Erro ao analisar: " + (error.message || "Desconhecido"));
        } finally {
            setIsAnalyzing(false);
        }
    };

    const handleApplyApproved = async () => {
        if (selectedFixes.size === 0) {
            toast.info("Selecione ao menos uma correção para aplicar.");
            return;
        }

        setIsApplying(true);

        try {
            const result = await apiClient.applyApprovedFixes({
                content: formattedContent,
                approved_fix_ids: Array.from(selectedFixes),
            });

            if (result.success && result.fixed_content) {
                onContentUpdated?.(result.fixed_content);
                setPendingFixes([]);
                setSelectedFixes(new Set());
                toast.success(
                    `${result.fixes_applied.length} correção(ões) aplicada(s). Redução: ${result.size_reduction}`
                );
            } else {
                toast.info("Nenhuma alteração realizada.");
            }
        } catch (error: any) {
            toast.error("Erro ao aplicar: " + (error.message || "Desconhecido"));
        } finally {
            setIsApplying(false);
        }
    };

    const handleSemanticSuggestions = async () => {
        if (!report || report.omissions.length === 0) {
            toast.info("Nenhuma omissão detectada para corrigir.");
            return;
        }

        setIsApplying(true);

        try {
            const result = await apiClient.applyQualityFix({
                content: formattedContent,
                fix_type: "semantic",
                document_name: documentName,
                issues: [...report.omissions, ...report.distortions],
            });

            if (result.suggestions) {
                setSuggestions(result.suggestions);
                toast.success("Sugestões geradas! Revise abaixo.");
            } else {
                toast.info("Nenhuma sugestão gerada.");
            }
        } catch (error: any) {
            toast.error("Erro ao gerar sugestões: " + (error.message || "Desconhecido"));
        } finally {
            setIsApplying(false);
        }
    };

    const toggleFix = (id: string) => {
        const newSelected = new Set(selectedFixes);
        if (newSelected.has(id)) {
            newSelected.delete(id);
        } else {
            newSelected.add(id);
        }
        setSelectedFixes(newSelected);
    };

    return (
        <Card className="w-full">
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <ShieldCheck className="w-5 h-5 text-indigo-600" />
                    Controle de Qualidade & Auditoria
                </CardTitle>
                <CardDescription>
                    Validação jurídica, análise estrutural e correção assistida
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
                {/* Actions Toolbar */}
                <div className="flex flex-wrap gap-2">
                    <Button
                        variant="outline"
                        onClick={handleValidate}
                        disabled={isValidating || isAnalyzing}
                    >
                        {isValidating ? (
                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        ) : (
                            <FileText className="w-4 h-4 mr-2" />
                        )}
                        Validar Conteúdo
                    </Button>

                    <Button
                        variant="secondary"
                        onClick={handleAnalyzeStructure}
                        disabled={isValidating || isAnalyzing}
                    >
                        {isAnalyzing ? (
                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        ) : (
                            <Wrench className="w-4 h-4 mr-2" />
                        )}
                        Auditoria Estrutural (HIL)
                    </Button>

                    <Button
                        variant="ghost"
                        onClick={handleSemanticSuggestions}
                        disabled={!report || (report.omissions.length === 0 && report.distortions.length === 0)}
                    >
                        <RefreshCw className="w-4 h-4 mr-2" />
                        Gerar Sugestões (IA)
                    </Button>
                </div>

                {/* Validation Report Card */}
                {report && (
                    <div className="p-4 border rounded-md bg-slate-50 dark:bg-slate-900/50">
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="font-semibold flex items-center gap-2">
                                {getScoreIcon(report.score)}
                                Nota de Fidelidade: <span className={getScoreColor(report.score)}>{report.score}/10</span>
                            </h3>
                            <Badge variant={report.approved ? "default" : "destructive"}>
                                {report.approved ? "Aprovado" : "Revisão Necessária"}
                            </Badge>
                        </div>

                        {report.omissions.length > 0 && (
                            <div className="mb-3">
                                <h4 className="text-sm font-medium text-red-600 mb-1 flex items-center gap-1">
                                    <AlertCircle className="w-3 h-3" /> Omissões Graves:
                                </h4>
                                <ul className="list-disc list-inside text-sm text-slate-700 dark:text-slate-300">
                                    {report.omissions.map((o, i) => (
                                        <li key={i}>{o}</li>
                                    ))}
                                </ul>
                            </div>
                        )}

                        {/* Other report sections (distortions, structural) could go here */}
                    </div>
                )}

                {/* HIL Audit Interface */}
                {analysisResult && (analysisResult.total_issues > 0 || analysisResult.missing_laws?.length) && (
                    <div className="border rounded-lg p-4 bg-white dark:bg-slate-950 shadow-sm animate-in fade-in slide-in-from-top-2">
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="font-semibold flex items-center gap-2">
                                <Wrench className="w-4 h-4 text-orange-500" />
                                Relatório de Auditoria
                            </h3>
                            <Badge variant="outline" className="bg-orange-50 text-orange-700 border-orange-200">
                                {analysisResult.total_issues} correções pendentes
                            </Badge>
                        </div>

                        {/* Content Alerts */}
                        {(analysisResult.missing_laws?.length || analysisResult.compression_warning) && (
                            <div className="mb-4 p-3 bg-yellow-50 dark:bg-yellow-900/20 rounded-md border border-yellow-100 dark:border-yellow-900/50">
                                <h4 className="text-sm font-semibold text-yellow-800 dark:text-yellow-200 mb-2 flex items-center gap-1">
                                    <AlertTriangle className="w-3 h-3" /> Alertas de Conteúdo
                                </h4>
                                {analysisResult.compression_warning && (
                                    <p className="text-xs text-yellow-700 dark:text-yellow-300 mb-2">
                                        ⚠️ {analysisResult.compression_warning}
                                    </p>
                                )}
                                {analysisResult.missing_laws?.map((law, i) => (
                                    <div key={i} className="text-xs text-yellow-700 dark:text-yellow-300 flex items-start gap-1">
                                        <span>•</span> Possível omissão legal: <strong>{law}</strong>
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* Pending Fixes List */}
                        {pendingFixes.length > 0 && (
                            <div className="space-y-3 mb-6 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
                                {pendingFixes.map((fix) => (
                                    <div
                                        key={fix.id}
                                        className={`flex items-start gap-3 p-3 rounded-md border cursor-pointer transition-colors ${selectedFixes.has(fix.id)
                                            ? "bg-indigo-50 border-indigo-200 dark:bg-indigo-900/20 dark:border-indigo-800"
                                            : "bg-slate-50 border-slate-100 hover:bg-slate-100 dark:bg-slate-900/30 dark:border-slate-800"
                                            }`}
                                        onClick={() => toggleFix(fix.id)}
                                    >
                                        <Checkbox
                                            checked={selectedFixes.has(fix.id)}
                                            onCheckedChange={() => toggleFix(fix.id)}
                                            className="mt-1"
                                        />
                                        <div className="flex-1">
                                            <div className="flex items-center justify-between">
                                                <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                                                    {fix.type === 'duplicate_section' ? 'Seção Duplicada' : 'Parágrafo Duplicado'}
                                                </span>
                                                <Badge className="text-[10px] h-5" variant={fix.severity === 'high' ? 'destructive' : 'outline'}>
                                                    {fix.action}
                                                </Badge>
                                            </div>
                                            <p className="text-sm text-slate-700 dark:text-slate-300 mt-1 line-clamp-2">
                                                {fix.description}
                                            </p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* Action Footer */}
                        <div className="flex justify-end gap-3 pt-4 border-t">
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setAnalysisResult(null)}
                            >
                                Cancelar
                            </Button>
                            <Button
                                onClick={handleApplyApproved}
                                disabled={isApplying || selectedFixes.size === 0}
                                size="sm"
                                className="bg-indigo-600 hover:bg-indigo-700 text-white"
                            >
                                {isApplying ? (
                                    <Loader2 className="w-3 h-3 mr-2 animate-spin" />
                                ) : (
                                    <CheckCircle className="w-3 h-3 mr-2" />
                                )}
                                Aplicar {selectedFixes.size} Correções
                            </Button>
                        </div>
                    </div>
                )}

                {/* AI Suggestions Result */}
                {suggestions && (
                    <div className="p-4 border border-indigo-100 bg-indigo-50/50 rounded-md">
                        <h4 className="font-semibold text-indigo-900 mb-2 flex items-center gap-2">
                            <span className="text-lg">✨</span> Sugestões de Correção
                        </h4>
                        <pre className="whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300 font-mono bg-white dark:bg-slate-950 p-3 rounded border">
                            {suggestions}
                        </pre>
                        <p className="text-xs text-slate-500 mt-2 italic">
                            Copie o conteúdo acima e aplique manualmente no editor onde necessário.
                        </p>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

export default QualityPanel;

