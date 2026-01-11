
import { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { AlertTriangle, Check, X, Edit2, ShieldAlert, GitBranch, FileCheck, FileWarning, Plus, RotateCcw, Trash2, GripVertical, ListOrdered } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Reorder, useDragControls, motion, AnimatePresence } from 'framer-motion';

interface DivergenceItem {
    secao: string;
    divergencias: string;
    drafts: Record<string, string>;
}

interface HumanReviewModalProps {
    isOpen: boolean;
    data: {
        checkpoint: 'divergence' | 'final' | 'correction' | 'section' | 'outline';
        document?: string;
        document_preview?: string;
        audit_status?: string;
        audit_report?: any;
        committee_review_report?: {
            score: number;
            requires_hil: boolean;
            agents_participated: string[];
            individual_reviews: Record<string, string>;
            critical_problems: string[];
            markdown: string;
        };
        divergencias?: DivergenceItem[];
        suspicious?: any[];
        // Outline checkpoint
        outline?: string[];
        hil_target_sections?: string[];
        // Section checkpoint specific
        section_title?: string;
        merged_content?: string;
        drafts?: Record<string, any>;
        divergence_details?: string;
        instructions?: string;
        // Correction checkpoint specific
        original_document?: string;
        proposed_corrections?: string;
        corrections_diff?: string;
        audit_issues?: string[];
    } | null;
    onSubmit: (decision: {
        checkpoint: string;
        approved: boolean;
        edits?: string;
        instructions?: string;
        hil_target_sections?: string[];
    }) => void;
}

// Draggable outline item component
function OutlineItem({ item, idx, onUpdate, onRemove }: { item: string; idx: number; onUpdate: (val: string) => void; onRemove: () => void }) {
    const controls = useDragControls();

    return (
        <Reorder.Item
            value={item}
            dragListener={false}
            dragControls={controls}
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, x: -20, transition: { duration: 0.15 } }}
            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
            className="group flex items-center gap-2 bg-background rounded-lg border shadow-sm hover:shadow-md transition-shadow p-2"
        >
            {/* Drag handle */}
            <div
                onPointerDown={(e) => controls.start(e)}
                className="cursor-grab active:cursor-grabbing touch-none p-1 rounded hover:bg-muted"
            >
                <GripVertical className="h-4 w-4 text-muted-foreground" />
            </div>

            {/* Index badge */}
            <div className="text-[10px] font-medium text-muted-foreground bg-muted rounded px-1.5 py-0.5 min-w-[20px] text-center">
                {idx + 1}
            </div>

            {/* Input */}
            <Input
                value={item}
                placeholder="Ex: II - DO DIREITO"
                onChange={(e) => onUpdate(e.target.value)}
                className="flex-1 h-8 text-sm"
            />

            {/* Delete button (visible on hover) */}
            <Button
                variant="ghost"
                size="icon"
                onClick={onRemove}
                className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
                aria-label="Remover tópico"
            >
                <Trash2 className="h-4 w-4" />
            </Button>
        </Reorder.Item>
    );
}

export function HumanReviewModal({ isOpen, data, onSubmit }: HumanReviewModalProps) {
    const [mode, setMode] = useState<'view' | 'edit' | 'reject'>('view');
    const [editedText, setEditedText] = useState('');
    const [instructions, setInstructions] = useState('');
    const [showOriginal, setShowOriginal] = useState(true);
    const [outlineItems, setOutlineItems] = useState<string[]>([]);
    const [originalOutline, setOriginalOutline] = useState<string[]>([]);
    const [hilTargets, setHilTargets] = useState<string[]>([]);
    const [activeTab, setActiveTab] = useState<string | null>(null);

    // Reset state when data changes
    useEffect(() => {
        if (data) {
            // For correction checkpoint, start with proposed corrections
            if (data.checkpoint === 'correction') {
                setEditedText(data.proposed_corrections || '');
            } else if (data.checkpoint === 'outline') {
                const initial = (data.outline || []).map((x) => String(x)).map((s) => s.trim()).filter(Boolean);
                setOriginalOutline(initial);
                setOutlineItems(initial);
                setEditedText(initial.join('\n'));
                const targets = Array.isArray(data.hil_target_sections) ? data.hil_target_sections : [];
                setHilTargets(targets.filter((t) => initial.includes(t)));
            } else if (data.checkpoint === 'section') {
                setEditedText(data.merged_content || '');
            } else {
                setEditedText(data.document || data.document_preview || '');
            }
            setMode('view');
            setInstructions('');
            setShowOriginal(true);
            setActiveTab(null);
        }
    }, [data]);

    if (!data) return null;

    const isDivergenceCheckpoint = data.checkpoint === 'divergence';
    const isFinalCheckpoint = data.checkpoint === 'final';
    const isCorrectionCheckpoint = data.checkpoint === 'correction';
    const isSectionCheckpoint = data.checkpoint === 'section';
    const isOutlineCheckpoint = data.checkpoint === 'outline';

    const handleApprove = () => {
        const outlineText = outlineItems.map((s) => (s || '').trim()).filter(Boolean).join('\n');
        onSubmit({
            checkpoint: data.checkpoint,
            approved: true,
            // For correction/section checkpoint, send the (possibly edited) text
            edits: isOutlineCheckpoint ? outlineText : (isCorrectionCheckpoint || isSectionCheckpoint) ? editedText : undefined,
            ...(isOutlineCheckpoint ? { hil_target_sections: hilTargets } : {})
        });
    };

    const handleReject = () => {
        onSubmit({
            checkpoint: data.checkpoint,
            approved: false,
            instructions
        });
    };

    const handleEditSubmit = () => {
        const outlineText = outlineItems.map((s) => (s || '').trim()).filter(Boolean).join('\n');
        onSubmit({
            checkpoint: data.checkpoint,
            approved: true,
            edits: isOutlineCheckpoint ? outlineText : editedText,
            ...(isOutlineCheckpoint ? { hil_target_sections: hilTargets } : {})
        });
    };

    return (
        <Dialog open={isOpen}>
            <DialogContent className="max-w-5xl max-h-[90vh] flex flex-col">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        {isDivergenceCheckpoint ? (
                            <>
                                <GitBranch className="h-5 w-5 text-amber-500" />
                                Divergências Detectadas
                            </>
                        ) : isOutlineCheckpoint ? (
                            <>
                                <FileCheck className="h-5 w-5 text-blue-500" />
                                Aprovação do Sumário (Outline)
                            </>
                        ) : isSectionCheckpoint ? (
                            <>
                                <FileCheck className="h-5 w-5 text-indigo-500" />
                                Revisão de Seção
                            </>
                        ) : isCorrectionCheckpoint ? (
                            <>
                                <FileWarning className="h-5 w-5 text-orange-500" />
                                Correções Baseadas na Auditoria
                            </>
                        ) : (
                            <>
                                <FileCheck className="h-5 w-5 text-blue-500" />
                                Aprovação Final
                            </>
                        )}
                    </DialogTitle>
                    <DialogDescription>
                        {isDivergenceCheckpoint
                            ? "Os agentes (GPT/Claude/Gemini) tiveram divergências. Revise antes de prosseguir."
                            : isOutlineCheckpoint
                                ? "A IA propôs o esqueleto do sumário. Edite e aprove antes de iniciar a pesquisa/geração."
                                : isSectionCheckpoint
                                    ? `Revise e aprove a seção ${data.section_title ? `"${data.section_title}"` : ""}. Se você rejeitar com instruções, o sistema refaz a seção por IA e reabre a aprovação.`
                                    : isCorrectionCheckpoint
                                        ? "A auditoria encontrou problemas. Revise as correções propostas antes de aplicar."
                                        : "O documento está pronto. Aprove para gerar a versão final."
                        }
                    </DialogDescription>
                </DialogHeader>

                <div className="flex-1 overflow-y-auto py-4 space-y-4">

                    {/* Final Committee Review Report */}
                    {isFinalCheckpoint && data.committee_review_report && (
                        <div className="space-y-4 mb-6">
                            <div className="flex items-center justify-between p-4 bg-slate-50 border rounded-lg">
                                <div>
                                    <h4 className="font-semibold text-sm flex items-center gap-2">
                                        <Users className="h-4 w-4 text-indigo-600" />
                                        Relatório do Comitê de Agentes
                                    </h4>
                                    <p className="text-xs text-muted-foreground mt-1">
                                        Revisão realizada por: {data.committee_review_report.agents_participated.join(", ")}
                                    </p>
                                    {data.committee_review_report.score_disagreement && (
                                        <p className="text-xs text-amber-700 mt-1">
                                            Divergência extrema detectada (Δ {data.committee_review_report.score_spread?.toFixed(1) ?? '—'})
                                        </p>
                                    )}
                                </div>
                                <div className="text-right">
                                    <div className={cn(
                                        "text-2xl font-bold",
                                        data.committee_review_report.score >= 7 ? "text-green-600" : "text-amber-600"
                                    )}>
                                        {data.committee_review_report.score.toFixed(1)}
                                        <span className="text-sm font-normal text-muted-foreground">/10</span>
                                    </div>
                                    <p className="text-[10px] text-muted-foreground">Nota Média</p>
                                </div>
                            </div>

                            {/* Critical Problems */}
                            {data.committee_review_report.critical_problems.length > 0 && (
                                <Alert variant="destructive" className="bg-red-50 border-red-200">
                                    <AlertTriangle className="h-4 w-4 text-red-600" />
                                    <AlertTitle className="text-red-800">Problemas Críticos Identificados</AlertTitle>
                                    <AlertDescription className="mt-2 space-y-1">
                                        {data.committee_review_report.critical_problems.map((prob, i) => (
                                            <div key={i} className="text-xs text-red-700 flex gap-2">
                                                <span>•</span>
                                                <span>{prob}</span>
                                            </div>
                                        ))}
                                    </AlertDescription>
                                </Alert>
                            )}
                            {data.committee_review_report.score_disagreement && (
                                <Alert variant="default" className="bg-amber-50 border-amber-200">
                                    <AlertTriangle className="h-4 w-4 text-amber-600" />
                                    <AlertTitle className="text-amber-800">Divergência Entre Agentes</AlertTitle>
                                    <AlertDescription className="mt-2 text-xs text-amber-800">
                                        Há diferença relevante entre as notas dos agentes (Δ {data.committee_review_report.score_spread?.toFixed(1) ?? '—'}).
                                        Recomenda-se revisão humana antes de finalizar.
                                    </AlertDescription>
                                </Alert>
                            )}

                            {/* Individual Reviews Accordion */}
                            <div className="space-y-2">
                                <h5 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Pareceres Individuais</h5>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                    {Object.entries(data.committee_review_report.individual_reviews).map(([agent, review]) => (
                                        <div key={agent} className="border rounded-md overflow-hidden flex flex-col">
                                            <div className="bg-muted/50 px-3 py-2 border-b flex items-center justify-between">
                                                <span className="text-xs font-semibold">{agent}</span>
                                                {/* Parsing score from review text roughly for badge */}
                                                {(review.match(/nota.*?(\d+(?:[.,]\d+)?)/i) || [])[1] && (
                                                    <span className={cn(
                                                        "text-[10px] px-1.5 py-0.5 rounded-full font-medium",
                                                        parseFloat((review.match(/nota.*?(\d+(?:[.,]\d+)?)/i) || [])[1]!.replace(',', '.')) >= 7
                                                            ? "bg-green-100 text-green-700"
                                                            : "bg-amber-100 text-amber-700"
                                                    )}>
                                                        {(review.match(/nota.*?(\d+(?:[.,]\d+)?)/i) || [])[1]}
                                                    </span>
                                                )}
                                            </div>
                                            <div className="p-3 text-[10px] text-muted-foreground h-[150px] overflow-y-auto whitespace-pre-wrap bg-white">
                                                {review}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Correction Checkpoint: Show audit issues */}
                    {isCorrectionCheckpoint && data.audit_issues && data.audit_issues.length > 0 && (
                        <div className="space-y-2">
                            <h4 className="font-medium text-sm flex items-center gap-2">
                                <AlertTriangle className="h-4 w-4 text-orange-500" />
                                Problemas Encontrados na Auditoria:
                            </h4>
                            <div className="bg-orange-50 border border-orange-200 rounded-md p-3 space-y-1">
                                {data.audit_issues.map((issue, i) => (
                                    <div key={i} className="text-sm text-orange-800 flex items-start gap-2">
                                        <span className="text-orange-500">•</span>
                                        {issue}
                                    </div>
                                ))}
                            </div>
                            {data.corrections_diff && (
                                <div className="text-xs text-muted-foreground">
                                    Resumo: {data.corrections_diff}
                                </div>
                            )}
                        </div>
                    )}

                    {/* Correction Checkpoint: Side-by-side diff view */}
                    {isCorrectionCheckpoint && mode === 'view' && (
                        <div className="space-y-2">
                            <div className="flex items-center justify-between">
                                <h4 className="font-medium text-sm">Comparação:</h4>
                                <div className="flex gap-2">
                                    <Button
                                        variant={showOriginal ? "default" : "outline"}
                                        size="sm"
                                        onClick={() => setShowOriginal(true)}
                                    >
                                        Original
                                    </Button>
                                    <Button
                                        variant={!showOriginal ? "default" : "outline"}
                                        size="sm"
                                        onClick={() => setShowOriginal(false)}
                                    >
                                        Corrigido
                                    </Button>
                                </div>
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                {/* Original */}
                                <div className={`space-y-1 ${!showOriginal ? 'opacity-50' : ''}`}>
                                    <div className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                                        <X className="h-3 w-3 text-red-500" />
                                        Documento Original
                                    </div>
                                    <div className="whitespace-pre-wrap bg-red-50 border border-red-200 p-3 rounded-md text-xs font-mono max-h-[250px] overflow-y-auto">
                                        {data.original_document || "[Original não disponível]"}
                                    </div>
                                </div>

                                {/* Corrected */}
                                <div className={`space-y-1 ${showOriginal ? 'opacity-50' : ''}`}>
                                    <div className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                                        <Check className="h-3 w-3 text-green-500" />
                                        Proposta de Correção
                                    </div>
                                    <div className="whitespace-pre-wrap bg-green-50 border border-green-200 p-3 rounded-md text-xs font-mono max-h-[250px] overflow-y-auto">
                                        {data.proposed_corrections || "[Correção não disponível]"}
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Divergence Checkpoint: Show divergencias list */}
                    {isDivergenceCheckpoint && data.divergencias && data.divergencias.length > 0 && (
                        <div className="space-y-3">
                            <h4 className="font-medium text-sm">Divergências por Seção:</h4>
                            {data.divergencias.map((div, i) => (
                                <Alert key={i} variant="default" className="bg-amber-50 border-amber-200">
                                    <AlertTriangle className="h-4 w-4 text-amber-600" />
                                    <AlertTitle>{div.secao}</AlertTitle>
                                    <AlertDescription className="text-xs mt-1">
                                        {div.divergencias || "Divergência não especificada"}
                                    </AlertDescription>
                                </Alert>
                            ))}
                        </div>
                    )}

                    {/* Final Checkpoint: Show audit status (Legacy Audit) */}
                    {isFinalCheckpoint && data.audit_status && data.audit_status !== 'aprovado' && (
                        <Alert variant="destructive">
                            <AlertTriangle className="h-4 w-4" />
                            <AlertTitle>Status da Auditoria Técnica: {data.audit_status.toUpperCase()}</AlertTitle>
                            <AlertDescription>
                                Revise o documento antes de aprovar.
                            </AlertDescription>
                        </Alert>
                    )}

                    {isFinalCheckpoint && data.audit_status === 'aprovado' && (
                        <Alert className="bg-green-50 border-green-200">
                            <Check className="h-4 w-4 text-green-600" />
                            <AlertTitle>Auditoria Técnica Aprovada</AlertTitle>
                            <AlertDescription>
                                O documento passou na auditoria automática (citações e procedimentos).
                            </AlertDescription>
                        </Alert>
                    )}


                    {/* Outline Checkpoint: Modern Drag-and-Drop Editor */}
                    {isOutlineCheckpoint && mode === 'view' && (
                        <div className="space-y-4">
                            {/* Header with instructions */}
                            <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                <ListOrdered className="h-4 w-4" />
                                <span>Arraste para reordenar • Cada item é um tópico do sumário</span>
                            </div>

                            {/* Action buttons */}
                            <div className="flex items-center gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => setOutlineItems((prev) => [...prev, ''])}
                                    className="gap-2"
                                >
                                    <Plus className="h-4 w-4" />
                                    Adicionar
                                </Button>
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => setOutlineItems(originalOutline)}
                                    disabled={originalOutline.length === 0}
                                    className="gap-2 text-muted-foreground hover:text-foreground"
                                >
                                    <RotateCcw className="h-4 w-4" />
                                    Reset (IA)
                                </Button>
                            </div>

                            {/* Sortable list container */}
                            <div className="border rounded-lg bg-gradient-to-b from-muted/30 to-muted/10 p-3 max-h-[380px] overflow-y-auto">
                                <AnimatePresence mode="popLayout">
                                    {outlineItems.length === 0 ? (
                                        <motion.div
                                            initial={{ opacity: 0 }}
                                            animate={{ opacity: 1 }}
                                            exit={{ opacity: 0 }}
                                            className="flex flex-col items-center justify-center py-12 text-center"
                                        >
                                            <ListOrdered className="h-10 w-10 text-muted-foreground/40 mb-3" />
                                            <p className="text-sm text-muted-foreground">Nenhum tópico ainda</p>
                                            <p className="text-xs text-muted-foreground/60">Clique em "Adicionar" para começar</p>
                                        </motion.div>
                                    ) : (
                                        <Reorder.Group
                                            axis="y"
                                            values={outlineItems}
                                            onReorder={setOutlineItems}
                                            className="space-y-2"
                                        >
                                            {outlineItems.map((item, idx) => (
                                                <OutlineItem
                                                    key={`item-${idx}`}
                                                    item={item}
                                                    idx={idx}
                                                    onUpdate={(value) => {
                                                        setOutlineItems((prev) => prev.map((p, i) => (i === idx ? value : p)));
                                                    }}
                                                    onRemove={() => {
                                                        setOutlineItems((prev) => {
                                                            const next = prev.filter((_, i) => i !== idx);
                                                            return next.length > 0 ? next : [];
                                                        });
                                                    }}
                                                />
                                            ))}
                                        </Reorder.Group>
                                    )}
                                </AnimatePresence>
                            </div>

                            {/* Live preview */}
                            {outlineItems.length > 0 && (
                                <div className="border rounded-lg bg-card p-3 space-y-1">
                                    <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-2">Preview do Sumário</p>
                                    {outlineItems.filter(Boolean).map((item, i) => (
                                        <div key={`preview-${i}`} className="text-sm text-foreground/80 flex items-center gap-2">
                                            <span className="text-xs text-muted-foreground w-5">{i + 1}.</span>
                                            <span>{item}</span>
                                        </div>
                                    ))}
                                </div>
                            )}

                            {outlineItems.length > 0 && (
                                <div className="border rounded-lg bg-card p-3 space-y-2">
                                    <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Revisao Humana por Secao (HIL)</p>
                                    <p className="text-[11px] text-muted-foreground">
                                        Selecione as secoes do sumario real que devem ser aprovadas uma a uma.
                                    </p>
                                    <div className="space-y-2">
                                        {outlineItems.map((item) => {
                                            const title = (item || '').trim();
                                            if (!title) return null;
                                            const checked = hilTargets.includes(title);
                                            return (
                                                <label key={title} className="flex items-center gap-2 text-xs">
                                                    <input
                                                        type="checkbox"
                                                        checked={checked}
                                                        onChange={(e) => {
                                                            const next = new Set(hilTargets);
                                                            if (e.target.checked) next.add(title);
                                                            else next.delete(title);
                                                            setHilTargets(Array.from(next));
                                                        }}
                                                    />
                                                    <span>{title}</span>
                                                </label>
                                            );
                                        })}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Document Preview / Edit (for non-correction checkpoints in view mode) */}
                    {!isCorrectionCheckpoint && !isSectionCheckpoint && !isOutlineCheckpoint && mode === 'view' && (
                        <div className="whitespace-pre-wrap bg-muted/50 p-4 rounded-md text-sm font-mono border max-h-[300px] overflow-y-auto">
                            {data.document || data.document_preview || "[Documento não disponível]"}
                        </div>
                    )}

                    {/* Section Checkpoint: preview */}
                    {isSectionCheckpoint && mode === 'view' && (
                        <div className="space-y-2">
                            {data.divergence_details && (
                                <Alert variant="default" className="bg-amber-50 border-amber-200">
                                    <ShieldAlert className="h-4 w-4 text-amber-600" />
                                    <AlertTitle>Divergências / Alertas</AlertTitle>
                                    <AlertDescription className="text-xs mt-1">
                                        {data.divergence_details}
                                    </AlertDescription>
                                </Alert>
                            )}
                            <div className="whitespace-pre-wrap bg-muted/50 p-4 rounded-md text-sm font-mono border max-h-[300px] overflow-y-auto">
                                {data.merged_content || "[Seção não disponível]"}
                            </div>
                        </div>
                    )}

                    {mode === 'edit' && (
                        <Textarea
                            value={editedText}
                            onChange={(e) => setEditedText(e.target.value)}
                            className="min-h-[400px] font-mono text-sm"
                        />
                    )}

                    {mode === 'reject' && (
                        <div className="space-y-2">
                            <label className="text-sm font-medium">
                                {isSectionCheckpoint ? 'Instruções para Refazer com IA:' : 'Instruções para Correção:'}
                            </label>
                            <Textarea
                                value={instructions}
                                onChange={(e) => setInstructions(e.target.value)}
                                placeholder={isSectionCheckpoint
                                    ? "Ex: Reescreva esta seção com base no art. X, inclua jurisprudência do STJ, remova afirmações sem fonte..."
                                    : "Ex: Refaça a seção 2 focando em tal lei, ajuste a fundamentação..."}
                                className="min-h-[200px]"
                            />
                        </div>
                    )}

                </div>

                <DialogFooter className="gap-2 sm:gap-0">
                    {mode === 'view' && (
                        <>
                            <Button variant="destructive" onClick={() => setMode('reject')}>
                                <X className="mr-2 h-4 w-4" /> Rejeitar / Corrigir
                            </Button>
                            <Button variant="outline" onClick={() => setMode('edit')}>
                                <Edit2 className="mr-2 h-4 w-4" /> Editar Manualmente
                            </Button>
                            <Button className="bg-green-600 hover:bg-green-700" onClick={handleApprove}>
                                <Check className="mr-2 h-4 w-4" />
                                {isDivergenceCheckpoint
                                    ? "Aprovar e Continuar"
                                    : isCorrectionCheckpoint
                                        ? "Aplicar Correções"
                                        : isSectionCheckpoint
                                            ? "Aprovar Seção"
                                            : isOutlineCheckpoint
                                                ? "Aprovar Outline"
                                                : "Aprovar Documento Final"
                                }
                            </Button>
                        </>
                    )}

                    {mode === 'edit' && (
                        <>
                            <Button variant="ghost" onClick={() => setMode('view')}>Cancelar</Button>
                            <Button onClick={handleEditSubmit}>Salvar e Aprovar</Button>
                        </>
                    )}

                    {mode === 'reject' && (
                        <>
                            <Button variant="ghost" onClick={() => setMode('view')}>Cancelar</Button>
                            <Button variant="destructive" onClick={handleReject}>
                                {isSectionCheckpoint ? 'Refazer com IA' : 'Enviar Correção'}
                            </Button>
                        </>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
