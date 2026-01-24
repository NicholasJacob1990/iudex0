"use client";

import { useEffect, useMemo, useState, type DragEvent } from 'react';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import apiClient from '@/lib/api-client';
import { parseMarkdownToHtmlSync } from '@/lib/markdown-parser';
import {
    CheckCircle2,
    Circle,
    GripVertical,
    LayoutList,
    Sparkles,
    Wand2,
    Sliders,
    FormInput,
    ListChecks,
    Pencil,
    Trash2,
    AlertTriangle,
    Lightbulb,
    ChevronDown,
    RefreshCw,
    Loader2,
} from 'lucide-react';

const inputClass =
    'bg-white border-slate-200 text-slate-900 placeholder:text-slate-400 dark:bg-slate-950/80 dark:border-slate-700 dark:text-slate-100 dark:placeholder:text-slate-500';
const selectTriggerClass =
    'bg-white border-slate-200 text-slate-900 dark:bg-slate-950/80 dark:border-slate-700 dark:text-slate-100';
const panelClass =
    'rounded-2xl border border-slate-200 bg-white/90 shadow-sm dark:border-slate-800 dark:bg-slate-900/70 dark:shadow-none';

const wizardCardClass =
    'group relative overflow-hidden rounded-3xl border border-slate-200 bg-white/95 px-7 py-7 shadow-sm transition hover:border-slate-300 dark:border-slate-800 dark:bg-slate-950/55 dark:hover:border-slate-700';

const stepTitleClass = 'text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400';

const previewCardClass =
    'rounded-2xl border border-slate-200 bg-slate-50/80 p-4 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-200';

const stepIconClass = 'h-4 w-4 text-emerald-600';

const dragHandleClass = 'text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300';

const badgeClass =
    'inline-flex items-center rounded-full border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold uppercase text-slate-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300';

const gradientBorderBase =
    'relative rounded-3xl p-[1px] bg-gradient-to-br from-slate-200/80 to-slate-300/50 dark:from-slate-800/60 dark:to-slate-700/20';
const gradientBorderManual =
    'bg-gradient-to-br from-sky-400/40 via-indigo-400/25 to-slate-300/40 dark:from-sky-400/25 dark:via-indigo-400/20 dark:to-slate-800/30';
const gradientBorderMagic =
    'bg-gradient-to-br from-fuchsia-400/35 via-violet-400/25 to-slate-300/40 dark:from-fuchsia-400/20 dark:via-violet-400/20 dark:to-slate-800/30';

type TemplateFormat = {
    numbering: 'ROMAN' | 'ARABIC' | 'CLAUSE' | 'NONE';
    tone: 'very_formal' | 'formal' | 'neutral' | 'executive';
    verbosity: 'short' | 'medium' | 'long';
    voice: 'first_person' | 'third_person' | 'impersonal';
};

type TemplateSection = {
    title: string;
    required: boolean;
    notes?: string;
};

type TemplateField = {
    name: string;
    type: 'text' | 'number' | 'date' | 'list' | 'id' | 'reference';
    required: boolean;
    on_missing: 'block' | 'mark_pending';
};

type TemplateChecklistItem = {
    id: string;
    level: 'required' | 'recommended' | 'conditional' | 'forbidden';
    rule: 'has_section' | 'has_field' | 'mentions_any' | 'forbidden_phrase_any';
    value: string | string[];
    condition: 'none' | 'if_tutela' | 'if_personal_data' | 'if_appeal';
    note?: string;
};

type UserTemplateV1 = {
    version: 1;
    name: string;
    doc_kind: string;
    doc_subtype: string;
    format: TemplateFormat;
    sections: TemplateSection[];
    required_fields: TemplateField[];
    checklist: TemplateChecklistItem[];
};

type CatalogTypes = Record<string, string[]>;

type WizardStep = 1 | 2 | 3 | 4 | 5;

type WizardPhase = 'start' | 'preview' | 'wizard';

function toRoman(num: number): string {
    if (!Number.isFinite(num) || num <= 0) return '';
    const romanMap: Array<[number, string]> = [
        [1000, 'M'],
        [900, 'CM'],
        [500, 'D'],
        [400, 'CD'],
        [100, 'C'],
        [90, 'XC'],
        [50, 'L'],
        [40, 'XL'],
        [10, 'X'],
        [9, 'IX'],
        [5, 'V'],
        [4, 'IV'],
        [1, 'I'],
    ];
    let n = Math.floor(num);
    let out = '';
    for (const [value, symbol] of romanMap) {
        while (n >= value) {
            out += symbol;
            n -= value;
        }
    }
    return out;
}

function sectionNumberLabel(fmt: TemplateFormat['numbering'], idx1: number): string {
    if (fmt === 'NONE') return '';
    if (fmt === 'ROMAN') return `${toRoman(idx1)} -`;
    if (fmt === 'ARABIC') return `${idx1}.`;
    if (fmt === 'CLAUSE') return `Cláusula ${idx1}.`;
    return '';
}

function buildTemplatePreviewMarkdown(
    tpl: UserTemplateV1,
    opts?: { maxSections?: number; includeFields?: boolean; includeChecklist?: boolean }
): string {
    const maxSections = Math.max(1, Math.min(opts?.maxSections ?? 6, 20));
    const includeFields = opts?.includeFields ?? true;
    const includeChecklist = opts?.includeChecklist ?? false;

    const title = (tpl.name || '').trim() || 'Sem título';
    const subtitle = `${tpl.doc_kind || 'DOCUMENTO'} / ${tpl.doc_subtype || 'SUBTIPO'}`;

    const lines: string[] = [];
    lines.push(`# ${title}`);
    lines.push(`_${subtitle}_`);
    lines.push('');

    const sections = (tpl.sections || [])
        .filter((s) => String(s?.title || '').trim())
        .slice(0, maxSections)
        .map((s, i) => {
            const label = sectionNumberLabel(tpl.format?.numbering || 'NONE', i + 1);
            const header = label ? `## ${label} ${s.title}` : `## ${s.title}`;
            const parts: string[] = [header, ''];
            const notes = String(s.notes || '').trim();
            if (notes) {
                parts.push(`> ${notes}`);
                parts.push('');
            }
            parts.push('_[Conteúdo será gerado aqui]_');
            return parts.join('\n');
        });

    if (sections.length) lines.push(sections.join('\n\n'));

    if (includeFields && (tpl.required_fields || []).length) {
        lines.push('');
        lines.push('---');
        lines.push('### Campos');
        for (const f of (tpl.required_fields || []).slice(0, 8)) {
            const name = String(f?.name || '').trim();
            if (!name) continue;
            lines.push(`- \`${name}\`${f.required ? ' _(obrigatório)_' : ''}`);
        }
    }

    if (includeChecklist && (tpl.checklist || []).length) {
        lines.push('');
        lines.push('---');
        lines.push('### Checklist');
        for (const item of (tpl.checklist || []).slice(0, 6)) {
            const id = String(item?.id || '').trim() || '(sem id)';
            lines.push(`- \`${id}\` — ${item.level}`);
        }
    }

    return lines.join('\n').trim();
}

const defaultTemplate: UserTemplateV1 = {
    version: 1,
    name: '',
    doc_kind: 'PLEADING',
    doc_subtype: 'PETICAO_INICIAL',
    format: {
        numbering: 'ROMAN',
        tone: 'formal',
        verbosity: 'medium',
        voice: 'third_person',
    },
    sections: [],
    required_fields: [],
    checklist: [],
};

interface TemplateWizardDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onCreated?: () => void;
}

export function TemplateWizardDialog({ open, onOpenChange, onCreated }: TemplateWizardDialogProps) {
    const [phase, setPhase] = useState<WizardPhase>('start');
    const [step, setStep] = useState<WizardStep>(1);
    const [catalogTypes, setCatalogTypes] = useState<CatalogTypes>({});
    const [description, setDescription] = useState('');
    const [loading, setLoading] = useState(false);
    const [elapsedTime, setElapsedTime] = useState(0);
    const [selectedModel, setSelectedModel] = useState('');
    const [showAdvanced, setShowAdvanced] = useState(false);
    const [template, setTemplate] = useState<UserTemplateV1>(defaultTemplate);
    const [dragIndex, setDragIndex] = useState<number | null>(null);
    const [variableSample, setVariableSample] = useState('');

    useEffect(() => {
        if (!open) return;
        setPhase('start');
        setStep(1);
        setDescription('');
        setVariableSample('');
        setTemplate(defaultTemplate);
        setElapsedTime(0);
        setSelectedModel('');
        setShowAdvanced(false);
        apiClient
            .getTemplateCatalogTypes()
            .then((data) => setCatalogTypes(data.types || {}))
            .catch(() => setCatalogTypes({}));
    }, [open]);

    // Timer for loading state
    useEffect(() => {
        if (!loading) {
            setElapsedTime(0);
            return;
        }
        const interval = setInterval(() => {
            setElapsedTime((prev) => prev + 1);
        }, 1000);
        return () => clearInterval(interval);
    }, [loading]);

    const docKinds = useMemo(() => Object.keys(catalogTypes || {}), [catalogTypes]);
    const docSubtypes = useMemo(
        () => catalogTypes[template.doc_kind] || [],
        [catalogTypes, template.doc_kind]
    );

    const steps = [
        { id: 1, label: 'Identidade', icon: LayoutList },
        { id: 2, label: 'Estrutura', icon: LayoutList },
        { id: 3, label: 'Estilo', icon: Sliders },
        { id: 4, label: 'Campos', icon: FormInput },
        { id: 5, label: 'Checklist', icon: ListChecks },
    ];

    const updateTemplate = (patch: Partial<UserTemplateV1>) => {
        setTemplate((prev) => ({ ...prev, ...patch }));
    };

    const handleLoadDefaults = async () => {
        if (!template.doc_kind || !template.doc_subtype) return;
        try {
            setLoading(true);
            const data = await apiClient.getTemplateCatalogDefaults(template.doc_kind, template.doc_subtype);
            const spec = data?.template || {};
            updateTemplate({
                format: {
                    numbering: spec.numbering || template.format.numbering,
                    tone: (spec.style?.tone as TemplateFormat['tone']) || template.format.tone,
                    verbosity: (spec.style?.verbosity as TemplateFormat['verbosity']) || template.format.verbosity,
                    voice: (spec.style?.voice as TemplateFormat['voice']) || template.format.voice,
                },
                sections: (spec.sections || []).map((title: string) => ({ title, required: true })),
                required_fields: (spec.required_fields || []).map((name: string) => ({
                    name,
                    type: 'text' as const,
                    required: true,
                    on_missing: 'block' as const,
                })),
                checklist: (spec.checklist_base || []).map((item: any) => ({
                    id: item.id || '',
                    level: item.kind || 'required',
                    rule: item.check || 'has_section',
                    value: item.value || '',
                    condition: 'none' as const,
                    note: item.note || '',
                })),
            });
        } catch (e) {
            toast.error('Falha ao carregar template base.');
        } finally {
            setLoading(false);
        }
    };

    const handleStartManual = () => {
        setPhase('wizard');
        setStep(1);
    };

    const handleGenerateFromDescription = async () => {
        if (!description.trim()) {
            toast.error('Informe uma descricao.');
            return;
        }
        try {
            setLoading(true);
            const data = await apiClient.parseTemplateDescription({
                description: description.trim(),
                doc_kind: template.doc_kind,
                doc_subtype: template.doc_subtype,
                model_id: selectedModel && selectedModel !== '__auto__' ? selectedModel : undefined,
            });
            const parsed = data?.template;
            if (parsed) {
                setTemplate(parsed);
                setPhase('preview');
            }
        } catch (e) {
            toast.error('Falha ao gerar template.');
        } finally {
            setLoading(false);
        }
    };

    const handleAcceptPreview = () => {
        setPhase('wizard');
        setStep(2);
    };

    const handleRetryGeneration = () => {
        setPhase('start');
    };

    const buildTemplateContent = (tpl: UserTemplateV1) => {
        const meta = {
            version: '1.0.0',
            document_type: tpl.doc_subtype,
            doc_kind: tpl.doc_kind,
            doc_subtype: tpl.doc_subtype,
            user_template_v1: tpl,
            output_mode: 'text',
        };
        const frontmatter = `<!-- IUDX_TEMPLATE_V1\n${JSON.stringify(meta, null, 2)}\n-->`;
        const body = tpl.sections
            .map((section, idx) => `## ${idx + 1}. ${section.title}\n\n[[PENDENTE: conteudo da secao]]`)
            .join('\n\n');
        return `${frontmatter}\n\n${body || '[[PENDENTE: conteudo]]'}`;
    };

    const handleSave = async () => {
        if (!template.name.trim()) {
            toast.error('Informe o nome do template.');
            return;
        }
        try {
            setLoading(true);
            await apiClient.validateTemplateCatalog(template);
            const descriptionText = buildTemplateContent(template);
            await apiClient.createTemplate({
                name: template.name.trim(),
                description: descriptionText,
                document_type: template.doc_subtype,
            });
            toast.success('Template criado.');
            onOpenChange(false);
            onCreated?.();
        } catch (e) {
            toast.error('Falha ao salvar template.');
        } finally {
            setLoading(false);
        }
    };

    const moveSection = (from: number, to: number) => {
        setTemplate((prev) => {
            const next = [...prev.sections];
            const [item] = next.splice(from, 1);
            next.splice(to, 0, item);
            return { ...prev, sections: next };
        });
    };

    const handleDragStart = (index: number) => (event: DragEvent<HTMLDivElement>) => {
        setDragIndex(index);
        event.dataTransfer.effectAllowed = 'move';
    };

    const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
        event.preventDefault();
    };

    const handleDrop = (index: number) => (event: DragEvent<HTMLDivElement>) => {
        event.preventDefault();
        if (dragIndex === null || dragIndex === index) return;
        moveSection(dragIndex, index);
        setDragIndex(null);
    };

    const detectVariables = () => {
        const raw = variableSample.trim();
        if (!raw) return;
        const matches = Array.from(raw.matchAll(/\{([a-zA-Z0-9_]+)\}/g))
            .map((match) => match[1])
            .filter(Boolean);
        if (!matches.length) {
            toast.error('Nenhuma variavel encontrada. Use {nome_variavel}.');
            return;
        }
        const existing = new Set(template.required_fields.map((field) => field.name));
        const additions = matches.filter((name) => !existing.has(name));
        if (!additions.length) {
            toast.success('Variaveis ja adicionadas.');
            return;
        }
        updateTemplate({
            required_fields: [
                ...template.required_fields,
                ...additions.map((name) => ({
                    name,
                    type: 'text' as const,
                    required: true,
                    on_missing: 'block' as const,
                })),
            ],
        });
    };

    const validationWarnings = useMemo(() => {
        const warnings: string[] = [];
        if (!template.name.trim()) warnings.push('Defina um nome para o template.');
        if (!template.doc_kind || !template.doc_subtype) warnings.push('Selecione o tipo do documento.');
        if (!template.sections.length) warnings.push('Adicione ao menos uma secao.');
        return warnings;
    }, [template]);

    const previewSummary = useMemo(() => {
        return {
            sections: template.sections.slice(0, 8),
            requiredFields: template.required_fields.slice(0, 6),
            checklistItems: template.checklist.slice(0, 6),
        };
    }, [template]);

    const miniPreviewHtml = useMemo(() => {
        const md = buildTemplatePreviewMarkdown(template, {
            maxSections: 6,
            includeFields: false,
            includeChecklist: false,
        });
        return parseMarkdownToHtmlSync(md);
    }, [template]);

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[1120px] max-h-[92vh] overflow-hidden flex flex-col bg-white dark:bg-slate-950">
                <DialogHeader>
                    <DialogTitle className="sr-only">Template Wizard</DialogTitle>
                </DialogHeader>

                {phase === 'start' && (
                    <div className="flex-1 overflow-y-auto">
                        <div className="relative overflow-hidden rounded-3xl border border-slate-200 bg-slate-50 p-6 dark:border-slate-900 dark:bg-slate-950">
                            <div className="pointer-events-none absolute inset-0 opacity-80 dark:opacity-100">
                                <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(99,102,241,0.14),transparent_55%)] dark:bg-[radial-gradient(ellipse_at_top,rgba(99,102,241,0.22),transparent_55%)]" />
                                <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom,rgba(168,85,247,0.10),transparent_60%)] dark:bg-[radial-gradient(ellipse_at_bottom,rgba(168,85,247,0.18),transparent_60%)]" />
                                <div className="absolute inset-0 opacity-60 dark:opacity-35 bg-dotted-grid" />
                            </div>

                            <div className="relative space-y-6">
                                <div>
                                    <p className={stepTitleClass}>Start Screen</p>
                                    <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
                                        Gerador de Documento Legal
                                    </h2>
                                    <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                                        Selecione seu ponto de partida
                                    </p>
                                </div>

                                <div className="grid gap-4 lg:grid-cols-2">
                                    <div className={`${gradientBorderBase} ${gradientBorderManual} group relative transition-all duration-500 hover:shadow-[0_0_40px_-10px_rgba(6,182,212,0.3)] hover:-translate-y-1`}>
                                        <div className={wizardCardClass + ' flex flex-col items-center text-center pt-8 pb-8 h-full'}>
                                            <div className="relative mb-6 transform transition-transform duration-500 group-hover:scale-110">
                                                <div className="absolute inset-0 blur-2xl bg-cyan-500/20 rounded-full" />
                                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                                <img
                                                    src="/icon_wizard_manual.png"
                                                    alt="Wizard Manual"
                                                    className="relative h-24 w-24 object-contain drop-shadow-[0_0_15px_rgba(6,182,212,0.6)]"
                                                />
                                            </div>

                                            <h3 className="text-xl font-bold bg-gradient-to-r from-slate-900 to-slate-700 bg-clip-text text-transparent dark:from-white dark:to-slate-300">
                                                Wizard Manual
                                            </h3>

                                            <p className="mt-3 text-sm leading-relaxed text-slate-600 dark:text-slate-400 max-w-[240px]">
                                                Drag & drop seções, defina campos e configure o checklist granularmente.
                                            </p>

                                            <Button
                                                className="mt-8 w-full rounded-xl bg-slate-900 text-white shadow-lg shadow-slate-900/20 hover:bg-slate-800 hover:shadow-slate-900/30 dark:bg-cyan-950/50 dark:text-cyan-200 dark:hover:bg-cyan-900/50 dark:border dark:border-cyan-800/50 transition-all"
                                                onClick={handleStartManual}
                                                disabled={loading}
                                            >
                                                Começar Manual
                                            </Button>
                                        </div>
                                    </div>

                                    <div className={`${gradientBorderBase} ${gradientBorderMagic} group relative transition-all duration-500 hover:shadow-[0_0_40px_-10px_rgba(168,85,247,0.3)] hover:-translate-y-1`}>
                                        <div className={wizardCardClass + ' flex flex-col items-center text-center pt-8 pb-8 h-full'}>
                                            <div className="relative mb-6 transform transition-transform duration-500 group-hover:scale-110">
                                                <div className="absolute inset-0 blur-2xl bg-fuchsia-500/20 rounded-full" />
                                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                                <img
                                                    src="/icon_wizard_magic.png"
                                                    alt="AI Magic"
                                                    className="relative h-24 w-24 object-contain drop-shadow-[0_0_15px_rgba(168,85,247,0.6)]"
                                                />
                                            </div>

                                            <h3 className="text-xl font-bold bg-gradient-to-r from-indigo-600 to-fuchsia-600 bg-clip-text text-transparent dark:from-indigo-400 dark:to-fuchsia-400">
                                                Descrever em Texto
                                            </h3>

                                            <p className="mt-3 text-sm leading-relaxed text-slate-600 dark:text-slate-400 max-w-[240px]">
                                                Descreva seu documento e a IA cria o rascunho completo automaticamente.
                                            </p>

                                            <div className="mt-4 space-y-3 w-full min-w-[320px]">
                                                <Textarea
                                                    rows={6}
                                                    value={description}
                                                    onChange={(e) => setDescription(e.target.value)}
                                                    placeholder='Ex: "Contrato de Vesting para Startup de SaaS, com cliff de 1 ano e vesting de 4 anos."'
                                                    className={`${inputClass} min-w-full`}
                                                    disabled={loading}
                                                />

                                                <button
                                                    type="button"
                                                    onClick={() => setShowAdvanced(!showAdvanced)}
                                                    className="flex items-center gap-1 text-xs font-semibold text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200"
                                                >
                                                    <ChevronDown className={`h-3 w-3 transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
                                                    Opções avançadas
                                                </button>

                                                {showAdvanced && (
                                                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/40 space-y-3">
                                                        <div className="grid gap-3 md:grid-cols-2">
                                                            <div className="space-y-2">
                                                                <Label className="text-xs">Modelo de IA</Label>
                                                                <Select value={selectedModel} onValueChange={setSelectedModel}>
                                                                    <SelectTrigger className={selectTriggerClass}>
                                                                        <SelectValue placeholder="Automático (padrão)" />
                                                                    </SelectTrigger>
                                                                    <SelectContent>
                                                                        <SelectItem value="__auto__">Automático</SelectItem>
                                                                        <SelectItem value="gemini-2.0-flash-001">Gemini 2.0 Flash</SelectItem>
                                                                        <SelectItem value="gpt-4o">GPT-4o</SelectItem>
                                                                        <SelectItem value="claude-sonnet-4-20250514">Claude Sonnet 4</SelectItem>
                                                                    </SelectContent>
                                                                </Select>
                                                            </div>
                                                            <div className="space-y-2">
                                                                <Label className="text-xs">Base do sistema</Label>
                                                                <Button
                                                                    size="sm"
                                                                    variant="outline"
                                                                    onClick={handleLoadDefaults}
                                                                    disabled={loading}
                                                                    className="w-full"
                                                                >
                                                                    Carregar base
                                                                </Button>
                                                            </div>
                                                        </div>
                                                    </div>
                                                )}

                                                <Button
                                                    onClick={handleGenerateFromDescription}
                                                    disabled={loading}
                                                    className="w-full rounded-full bg-fuchsia-600 text-white hover:bg-fuchsia-700 dark:bg-fuchsia-500/20 dark:text-fuchsia-100 dark:hover:bg-fuchsia-500/30"
                                                >
                                                    {loading ? (
                                                        <span className="flex items-center justify-center gap-2">
                                                            <Loader2 className="h-4 w-4 animate-spin" />
                                                            Gerando... {elapsedTime}s
                                                        </span>
                                                    ) : (
                                                        'Gerar com IA'
                                                    )}
                                                </Button>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-500">
                                    <span>Wizard Steps</span>
                                    <span>{Object.keys(catalogTypes || {}).length ? 'Catálogo carregado' : 'Carregando catálogo...'}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {phase === 'preview' && (
                    <div className="flex-1 overflow-y-auto bg-slate-100/50 dark:bg-black/20 p-8 flex flex-col items-center">
                        <div className="w-full max-w-[800px] space-y-8">
                            {/* Header */}
                            <div className="text-center space-y-2">
                                <div className="inline-flex items-center justify-center p-3 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded-2xl mb-2 ring-1 ring-emerald-500/20">
                                    <Sparkles className="h-6 w-6" />
                                </div>
                                <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Review do Template Gerado</h2>
                                <p className="text-slate-500 dark:text-slate-400">Verifique a estrutura antes de prosseguir para a edição.</p>
                            </div>

                            <div className="grid lg:grid-cols-[1fr_300px] gap-8 items-start">
                                {/* Document Preview - Paper Appearance */}
                                <div className="bg-white text-slate-900 shadow-2xl shadow-slate-200/50 dark:shadow-black/50 rounded-sm min-h-[600px] p-12 relative mx-auto w-full transition-transform hover:scale-[1.005] duration-500">
                                    {/* Paper Texture/Gradient */}
                                    <div className="absolute inset-0 bg-gradient-to-b from-white via-slate-50/30 to-slate-100/50 pointer-events-none" />

                                    <div className="relative space-y-8 font-serif">
                                        <div className="text-center pb-8 border-b-2 border-slate-900/10">
                                            <h1 className="text-3xl font-bold uppercase tracking-wide text-slate-900">{template.name || 'MINUTA SEM TÍTULO'}</h1>
                                            <p className="mt-4 text-sm text-slate-500 uppercase tracking-widest">{template.doc_kind} • {template.doc_subtype}</p>
                                        </div>

                                        <div className="space-y-6">
                                            {template.sections.map((section, idx) => (
                                                <div key={idx} className="group">
                                                    <h4 className="font-bold text-slate-800 uppercase text-sm mb-2 flex items-center gap-2">
                                                        <span className="text-slate-400 text-xs">{idx + 1}.</span>
                                                        {section.title}
                                                    </h4>
                                                    <div className="h-16 rounded bg-slate-100/50 border border-dashed border-slate-200 p-3 text-xs text-slate-400 group-hover:bg-slate-100 transition-colors">
                                                        [Conteúdo da seção: {section.title}]
                                                    </div>
                                                </div>
                                            ))}
                                        </div>

                                        {template.sections.length === 0 && (
                                            <div className="text-center py-20 text-slate-400 italic">
                                                Nenhuma seção definida.
                                            </div>
                                        )}
                                    </div>
                                </div>

                                {/* Sidebar Stats */}
                                <div className="space-y-4 sticky top-4">
                                    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-5 shadow-sm space-y-4">
                                        <h3 className="font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                                            <ListChecks className="h-4 w-4" /> Resumo
                                        </h3>
                                        <div className="space-y-3">
                                            <div className="flex items-center justify-between text-sm">
                                                <span className="text-slate-500">Seções</span>
                                                <span className="font-mono font-medium bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded text-slate-700 dark:text-slate-300">{template.sections.length}</span>
                                            </div>
                                            <div className="flex items-center justify-between text-sm">
                                                <span className="text-slate-500">Campos</span>
                                                <span className="font-mono font-medium bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded text-slate-700 dark:text-slate-300">{template.required_fields.length}</span>
                                            </div>
                                            <div className="flex items-center justify-between text-sm">
                                                <span className="text-slate-500">Regras</span>
                                                <span className="font-mono font-medium bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded text-slate-700 dark:text-slate-300">{template.checklist.length}</span>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="bg-amber-50 dark:bg-amber-950/30 border-l-4 border-amber-400 p-4 rounded-r-xl">
                                        <div className="flex items-start gap-3">
                                            <Sparkles className="h-5 w-5 text-amber-500 mt-0.5" />
                                            <div>
                                                <p className="text-xs font-bold text-amber-700 dark:text-amber-400 uppercase">Sugestão da IA</p>
                                                <p className="text-sm text-amber-900/80 dark:text-amber-200/80 mt-1">
                                                    Revise a ordem das seções. Você pode arrastá-las no próximo passo.
                                                </p>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="pt-4 space-y-3">
                                        <Button className="w-full h-11" onClick={handleAcceptPreview}>
                                            <CheckCircle2 className="h-4 w-4 mr-2" />
                                            Aceitar e Editar
                                        </Button>
                                        <Button variant="ghost" className="w-full text-slate-500 hover:text-slate-900 dark:hover:text-white" onClick={handleRetryGeneration}>
                                            <RefreshCw className="h-4 w-4 mr-2" />
                                            Tentar Novamente
                                        </Button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {phase === 'wizard' && (
                    <div className="flex-1 overflow-y-auto space-y-6">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className={stepTitleClass}>Wizard Steps</p>
                                <h2 className="mt-1 text-xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
                                    Wizard de Criação: {steps.find((s) => s.id === step)?.label || 'Template'}
                                </h2>
                            </div>
                        </div>

                        <div className="grid gap-6 lg:grid-cols-[220px_1fr_300px]">
                            <aside className="space-y-4">
                                <div className={panelClass + ' p-4'}>
                                    <p className={stepTitleClass}>Passos</p>
                                    <div className="relative mt-4 space-y-3">
                                        <div className="pointer-events-none absolute left-[13px] top-2 bottom-2 w-px bg-slate-200 dark:bg-slate-800" />
                                        {steps.map((item) => {
                                            const Icon = item.icon;
                                            const isActive = step === item.id;
                                            const isComplete = step > item.id;
                                            const stepLabel = `Passo ${item.id}`;
                                            return (
                                                <button
                                                    key={item.id}
                                                    type="button"
                                                    onClick={() => setStep(item.id as WizardStep)}
                                                    className={`relative flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm transition ${isActive
                                                        ? 'bg-slate-900 text-white dark:bg-slate-200 dark:text-slate-900'
                                                        : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
                                                        }`}
                                                >
                                                    <span className="relative flex h-6 w-6 items-center justify-center">
                                                        {isComplete ? (
                                                            <CheckCircle2 className={stepIconClass} />
                                                        ) : isActive ? (
                                                            <Circle className="h-5 w-5 text-white dark:text-slate-900" />
                                                        ) : (
                                                            <Circle className="h-5 w-5 text-slate-300 dark:text-slate-700" />
                                                        )}
                                                        <span className="absolute text-[10px] font-bold">
                                                            {isComplete ? '' : item.id}
                                                        </span>
                                                    </span>
                                                    <div className="min-w-0">
                                                        <p className="text-[10px] font-semibold uppercase tracking-wide opacity-70">{stepLabel}</p>
                                                        <p className="truncate font-semibold">{item.label}</p>
                                                    </div>
                                                    <Icon
                                                        className={`ml-auto h-4 w-4 opacity-70 ${isActive ? 'text-white dark:text-slate-900' : 'text-slate-500 dark:text-slate-400'
                                                            }`}
                                                    />
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>
                            </aside>

                            <section className={panelClass + ' p-6'}>
                                {step === 1 && (
                                    <div className="space-y-5">
                                        <div>
                                            <p className={stepTitleClass}>Identidade</p>
                                            <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Defina o template base</h3>
                                        </div>

                                        <div className="space-y-2">
                                            <Label>Nome do template</Label>
                                            <Input
                                                value={template.name}
                                                onChange={(e) => updateTemplate({ name: e.target.value })}
                                                placeholder="Ex: Apelacao objetiva"
                                                className={inputClass}
                                            />
                                        </div>

                                        <div className="grid gap-4 md:grid-cols-2">
                                            <div className="space-y-2">
                                                <Label>Doc kind</Label>
                                                <Select
                                                    value={template.doc_kind}
                                                    onValueChange={(value) =>
                                                        updateTemplate({
                                                            doc_kind: value,
                                                            doc_subtype: (catalogTypes[value] || [])[0] || '',
                                                        })
                                                    }
                                                >
                                                    <SelectTrigger className={selectTriggerClass}>
                                                        <SelectValue placeholder="Selecione" />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        {docKinds.map((kind) => (
                                                            <SelectItem key={kind} value={kind}>
                                                                {kind}
                                                            </SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            </div>
                                            <div className="space-y-2">
                                                <Label>Doc subtype</Label>
                                                <Select
                                                    value={template.doc_subtype}
                                                    onValueChange={(value) => updateTemplate({ doc_subtype: value })}
                                                >
                                                    <SelectTrigger className={selectTriggerClass}>
                                                        <SelectValue placeholder="Selecione" />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        {docSubtypes.map((sub) => (
                                                            <SelectItem key={sub} value={sub}>
                                                                {sub}
                                                            </SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            </div>
                                        </div>

                                        <Button variant="outline" onClick={handleLoadDefaults} disabled={loading}>
                                            Carregar base do catalogo
                                        </Button>
                                    </div>
                                )}

                                {step === 2 && (
                                    <div className="space-y-4">
                                        <div className="flex items-center justify-between">
                                            <div>
                                                <p className={stepTitleClass}>Estrutura</p>
                                                <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Organize as secoes</h3>
                                            </div>
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                onClick={() =>
                                                    updateTemplate({
                                                        sections: [...template.sections, { title: '', required: true }],
                                                    })
                                                }
                                            >
                                                Adicionar secao
                                            </Button>
                                        </div>

                                        <div className="space-y-2">
                                            {template.sections.map((section, index) => (
                                                <div
                                                    key={`${section.title}-${index}`}
                                                    draggable
                                                    onDragStart={handleDragStart(index)}
                                                    onDragOver={handleDragOver}
                                                    onDrop={handleDrop(index)}
                                                    onDragEnd={() => setDragIndex(null)}
                                                    className={`group rounded-2xl border p-4 shadow-sm transition ${dragIndex === index
                                                        ? 'border-slate-400 bg-slate-100 ring-2 ring-emerald-300/60 dark:border-slate-500 dark:bg-slate-900/40'
                                                        : 'border-slate-200 bg-white hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950/50 dark:hover:bg-slate-900/40'
                                                        }`}
                                                >
                                                    <div className="flex items-center gap-3">
                                                        <GripVertical className={`h-5 w-5 ${dragHandleClass}`} />
                                                        <Input
                                                            id={`tpl-section-${index}`}
                                                            value={section.title}
                                                            onChange={(e) => {
                                                                const next = [...template.sections];
                                                                next[index] = { ...next[index], title: e.target.value };
                                                                updateTemplate({ sections: next });
                                                            }}
                                                            placeholder={`Secao ${index + 1}`}
                                                            className={inputClass}
                                                        />

                                                        <div className="ml-auto flex items-center gap-1 opacity-70 transition group-hover:opacity-100">
                                                            <Button
                                                                size="icon"
                                                                variant="ghost"
                                                                className="h-8 w-8"
                                                                title="Editar"
                                                                onClick={() => {
                                                                    const input = document.getElementById(`tpl-section-${index}`) as HTMLInputElement | null;
                                                                    input?.focus();
                                                                }}
                                                            >
                                                                <Pencil className="h-4 w-4" />
                                                            </Button>
                                                            <Button
                                                                size="icon"
                                                                variant="ghost"
                                                                className="h-8 w-8 text-rose-600 hover:text-rose-700 dark:text-rose-400 dark:hover:text-rose-300"
                                                                title="Excluir"
                                                                onClick={() =>
                                                                    updateTemplate({ sections: template.sections.filter((_, i) => i !== index) })
                                                                }
                                                            >
                                                                <Trash2 className="h-4 w-4" />
                                                            </Button>
                                                        </div>
                                                    </div>

                                                    <div className="mt-3 flex items-center justify-between">
                                                        <label className="flex items-center gap-2 text-xs font-semibold text-slate-600 dark:text-slate-300">
                                                            <Checkbox
                                                                checked={section.required}
                                                                onCheckedChange={(checked) => {
                                                                    const next = [...template.sections];
                                                                    next[index] = { ...next[index], required: Boolean(checked) };
                                                                    updateTemplate({ sections: next });
                                                                }}
                                                            />
                                                            Obrigatória
                                                        </label>
                                                        <span className="text-[11px] text-slate-500 dark:text-slate-500">
                                                            Arraste para reordenar
                                                        </span>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {step === 3 && (
                                    <div className="space-y-4">
                                        <div>
                                            <p className={stepTitleClass}>Estilo</p>
                                            <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Formate o tom do documento</h3>
                                        </div>

                                        <div className="grid gap-4 md:grid-cols-2">
                                            <div className="space-y-2">
                                                <Label>Numeracao</Label>
                                                <Select
                                                    value={template.format.numbering}
                                                    onValueChange={(value) =>
                                                        updateTemplate({
                                                            format: { ...template.format, numbering: value as TemplateFormat['numbering'] },
                                                        })
                                                    }
                                                >
                                                    <SelectTrigger className={selectTriggerClass}>
                                                        <SelectValue />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        {['ROMAN', 'ARABIC', 'CLAUSE', 'NONE'].map((opt) => (
                                                            <SelectItem key={opt} value={opt}>
                                                                {opt}
                                                            </SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            </div>

                                            <div className="space-y-2">
                                                <Label>Tom</Label>
                                                <Select
                                                    value={template.format.tone}
                                                    onValueChange={(value) =>
                                                        updateTemplate({
                                                            format: { ...template.format, tone: value as TemplateFormat['tone'] },
                                                        })
                                                    }
                                                >
                                                    <SelectTrigger className={selectTriggerClass}>
                                                        <SelectValue />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        {['very_formal', 'formal', 'neutral', 'executive'].map((opt) => (
                                                            <SelectItem key={opt} value={opt}>
                                                                {opt}
                                                            </SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            </div>

                                            <div className="space-y-2">
                                                <Label>Extensao</Label>
                                                <Select
                                                    value={template.format.verbosity}
                                                    onValueChange={(value) =>
                                                        updateTemplate({
                                                            format: { ...template.format, verbosity: value as TemplateFormat['verbosity'] },
                                                        })
                                                    }
                                                >
                                                    <SelectTrigger className={selectTriggerClass}>
                                                        <SelectValue />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        {['short', 'medium', 'long'].map((opt) => (
                                                            <SelectItem key={opt} value={opt}>
                                                                {opt}
                                                            </SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            </div>

                                            <div className="space-y-2">
                                                <Label>Voz</Label>
                                                <Select
                                                    value={template.format.voice}
                                                    onValueChange={(value) =>
                                                        updateTemplate({
                                                            format: { ...template.format, voice: value as TemplateFormat['voice'] },
                                                        })
                                                    }
                                                >
                                                    <SelectTrigger className={selectTriggerClass}>
                                                        <SelectValue />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        {['first_person', 'third_person', 'impersonal'].map((opt) => (
                                                            <SelectItem key={opt} value={opt}>
                                                                {opt}
                                                            </SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {step === 4 && (
                                    <div className="space-y-4">
                                        <div>
                                            <p className={stepTitleClass}>Campos</p>
                                            <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Defina variaveis do template</h3>
                                        </div>

                                        <div className="space-y-2">
                                            <Label>Detectar variaveis</Label>
                                            <Textarea
                                                rows={3}
                                                value={variableSample}
                                                onChange={(e) => setVariableSample(e.target.value)}
                                                placeholder="Cole um trecho com {variaveis} para detectar automaticamente."
                                                className={inputClass}
                                            />
                                            <Button variant="outline" size="sm" onClick={detectVariables}>
                                                Detectar campos
                                            </Button>
                                        </div>

                                        <div className="flex items-center justify-between">
                                            <Label>Campos obrigatorios</Label>
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                onClick={() =>
                                                    updateTemplate({
                                                        required_fields: [
                                                            ...template.required_fields,
                                                            { name: '', type: 'text' as const, required: true, on_missing: 'block' as const },
                                                        ],
                                                    })
                                                }
                                            >
                                                Adicionar
                                            </Button>
                                        </div>

                                        {template.required_fields.map((field, index) => (
                                            <div key={`${field.name}-${index}`} className="space-y-2 rounded-xl border border-slate-200 bg-white p-3">
                                                <Input
                                                    value={field.name}
                                                    onChange={(e) => {
                                                        const next = [...template.required_fields];
                                                        next[index] = { ...next[index], name: e.target.value };
                                                        updateTemplate({ required_fields: next });
                                                    }}
                                                    placeholder="nome_variavel"
                                                    className={inputClass}
                                                />
                                                <div className="grid gap-2 md:grid-cols-3">
                                                    <Select
                                                        value={field.type}
                                                        onValueChange={(value) => {
                                                            const next = [...template.required_fields];
                                                            next[index] = { ...next[index], type: value as TemplateField['type'] };
                                                            updateTemplate({ required_fields: next });
                                                        }}
                                                    >
                                                        <SelectTrigger className={selectTriggerClass}>
                                                            <SelectValue />
                                                        </SelectTrigger>
                                                        <SelectContent>
                                                            {['text', 'number', 'date', 'list', 'id', 'reference'].map((opt) => (
                                                                <SelectItem key={opt} value={opt}>
                                                                    {opt}
                                                                </SelectItem>
                                                            ))}
                                                        </SelectContent>
                                                    </Select>

                                                    <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-950/60 dark:text-slate-300">
                                                        <Checkbox
                                                            checked={field.required}
                                                            onCheckedChange={(checked) => {
                                                                const next = [...template.required_fields];
                                                                next[index] = { ...next[index], required: Boolean(checked) };
                                                                updateTemplate({ required_fields: next });
                                                            }}
                                                        />
                                                        Obrigatorio
                                                    </div>

                                                    <Select
                                                        value={field.on_missing}
                                                        onValueChange={(value) => {
                                                            const next = [...template.required_fields];
                                                            next[index] = { ...next[index], on_missing: value as TemplateField['on_missing'] };
                                                            updateTemplate({ required_fields: next });
                                                        }}
                                                    >
                                                        <SelectTrigger className={selectTriggerClass}>
                                                            <SelectValue />
                                                        </SelectTrigger>
                                                        <SelectContent>
                                                            {['block', 'mark_pending'].map((opt) => (
                                                                <SelectItem key={opt} value={opt}>
                                                                    {opt}
                                                                </SelectItem>
                                                            ))}
                                                        </SelectContent>
                                                    </Select>
                                                </div>
                                                <Button
                                                    size="sm"
                                                    variant="ghost"
                                                    onClick={() =>
                                                        updateTemplate({
                                                            required_fields: template.required_fields.filter((_, i) => i !== index),
                                                        })
                                                    }
                                                >
                                                    Remover
                                                </Button>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {step === 5 && (
                                    <div className="space-y-4">
                                        <div>
                                            <p className={stepTitleClass}>Checklist</p>
                                            <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Regras de ouro do documento</h3>
                                        </div>

                                        <div className="flex items-center justify-between">
                                            <Label>Checklist</Label>
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                onClick={() =>
                                                    updateTemplate({
                                                        checklist: [
                                                            ...template.checklist,
                                                            { id: '', level: 'required', rule: 'has_section', value: '', condition: 'none' },
                                                        ],
                                                    })
                                                }
                                            >
                                                Adicionar
                                            </Button>
                                        </div>

                                        {template.checklist.map((item, index) => (
                                            <div key={`${item.id}-${index}`} className="space-y-2 rounded-xl border border-slate-200 bg-white p-3">
                                                <Input
                                                    value={item.id}
                                                    onChange={(e) => {
                                                        const next = [...template.checklist];
                                                        next[index] = { ...next[index], id: e.target.value };
                                                        updateTemplate({ checklist: next });
                                                    }}
                                                    placeholder="ex: pedido_gratuidade"
                                                    className={inputClass}
                                                />
                                                <div className="grid gap-2 md:grid-cols-3">
                                                    <Select
                                                        value={item.level}
                                                        onValueChange={(value) => {
                                                            const next = [...template.checklist];
                                                            next[index] = { ...next[index], level: value as TemplateChecklistItem['level'] };
                                                            updateTemplate({ checklist: next });
                                                        }}
                                                    >
                                                        <SelectTrigger className={selectTriggerClass}>
                                                            <SelectValue />
                                                        </SelectTrigger>
                                                        <SelectContent>
                                                            {['required', 'recommended', 'conditional', 'forbidden'].map((opt) => (
                                                                <SelectItem key={opt} value={opt}>
                                                                    {opt}
                                                                </SelectItem>
                                                            ))}
                                                        </SelectContent>
                                                    </Select>
                                                    <Select
                                                        value={item.rule}
                                                        onValueChange={(value) => {
                                                            const next = [...template.checklist];
                                                            next[index] = { ...next[index], rule: value as TemplateChecklistItem['rule'] };
                                                            updateTemplate({ checklist: next });
                                                        }}
                                                    >
                                                        <SelectTrigger className={selectTriggerClass}>
                                                            <SelectValue />
                                                        </SelectTrigger>
                                                        <SelectContent>
                                                            {['has_section', 'has_field', 'mentions_any', 'forbidden_phrase_any'].map((opt) => (
                                                                <SelectItem key={opt} value={opt}>
                                                                    {opt}
                                                                </SelectItem>
                                                            ))}
                                                        </SelectContent>
                                                    </Select>
                                                    <Select
                                                        value={item.condition}
                                                        onValueChange={(value) => {
                                                            const next = [...template.checklist];
                                                            next[index] = { ...next[index], condition: value as TemplateChecklistItem['condition'] };
                                                            updateTemplate({ checklist: next });
                                                        }}
                                                    >
                                                        <SelectTrigger className={selectTriggerClass}>
                                                            <SelectValue />
                                                        </SelectTrigger>
                                                        <SelectContent>
                                                            {['none', 'if_tutela', 'if_personal_data', 'if_appeal'].map((opt) => (
                                                                <SelectItem key={opt} value={opt}>
                                                                    {opt}
                                                                </SelectItem>
                                                            ))}
                                                        </SelectContent>
                                                    </Select>
                                                </div>
                                                <Textarea
                                                    rows={2}
                                                    value={Array.isArray(item.value) ? item.value.join(', ') : String(item.value || '')}
                                                    onChange={(e) => {
                                                        const raw = e.target.value;
                                                        const next = [...template.checklist];
                                                        next[index] = {
                                                            ...next[index],
                                                            value: raw.includes(',')
                                                                ? raw.split(',').map((v) => v.trim()).filter(Boolean)
                                                                : raw,
                                                        };
                                                        updateTemplate({ checklist: next });
                                                    }}
                                                    placeholder="ex: deve conter pedido de gratuidade"
                                                    className={inputClass}
                                                />
                                                <Button
                                                    size="sm"
                                                    variant="ghost"
                                                    onClick={() =>
                                                        updateTemplate({
                                                            checklist: template.checklist.filter((_, i) => i !== index),
                                                        })
                                                    }
                                                >
                                                    Remover
                                                </Button>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </section>

                            <aside className="space-y-6">
                                {/* Visualização e Validações Title */}
                                <div className="flex items-center justify-between pb-2 border-b border-slate-200 dark:border-slate-800">
                                    <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Visualização e Validações</h4>
                                </div>

                                {/* Mini Document Preview */}
                                <div className="relative group [perspective:1000px]">
                                    <div className="bg-white min-h-[420px] w-full rounded-sm shadow-xl shadow-slate-200/60 dark:shadow-black/60 p-6 relative transition-transform transform-gpu group-hover:rotate-[0.25deg] group-hover:scale-[1.01] duration-500 border border-slate-100 dark:border-slate-800">
                                        {/* Paper Texture */}
                                        <div className="absolute inset-0 bg-gradient-to-b from-white via-slate-50/50 to-slate-100/30 pointer-events-none" />

                                        {/* Header */}
                                        <div className="relative text-center mb-6 border-b-2 border-slate-900/10 pb-4">
                                            <h5 className="text-[10px] uppercase tracking-[0.2em] text-slate-400 mb-1">
                                                {template.doc_kind || 'DOCUMENTO'}
                                            </h5>
                                            <h3 className="font-serif text-lg font-bold text-slate-800 leading-tight">
                                                {template.name || 'Sem Título'}
                                            </h3>
                                        </div>

                                        {/* Body - Real Preview */}
                                        <div className="relative max-h-[260px] overflow-auto pr-2">
                                            {!template.sections.length ? (
                                                <div className="flex flex-col items-center justify-center py-12 text-slate-300 gap-2">
                                                    <LayoutList className="h-8 w-8 opacity-20" />
                                                    <span className="text-xs italic">Documento vazio</span>
                                                </div>
                                            ) : (
                                                <div
                                                    className="chat-markdown font-serif text-[11px] leading-relaxed text-slate-800 [&_h1]:text-[14px] [&_h2]:text-[12px] [&_h3]:text-[11px] [&_p]:text-[11px]"
                                                    dangerouslySetInnerHTML={{ __html: miniPreviewHtml }}
                                                />
                                            )}
                                        </div>

                                        {/* Footer - Stats Overlays */}
                                        <div className="absolute bottom-4 left-4 right-4 flex justify-between">
                                            {template.required_fields.length > 0 && (
                                                <div className="bg-emerald-50 text-emerald-700 text-[10px] px-2 py-0.5 rounded-full border border-emerald-100 font-medium">
                                                    {template.required_fields.length} Campos
                                                </div>
                                            )}
                                            {template.checklist.length > 0 && (
                                                <div className="bg-indigo-50 text-indigo-700 text-[10px] px-2 py-0.5 rounded-full border border-indigo-100 font-medium">
                                                    {template.checklist.length} Regras
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>

                                {/* Validations / Alerts */}
                                <div className="space-y-3">
                                    <h5 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                                        Alertas de Validação
                                    </h5>

                                    {validationWarnings.length === 0 ? (
                                        <div className="bg-emerald-50 dark:bg-emerald-950/20 border-l-4 border-emerald-500 p-3 rounded-r-md flex gap-3">
                                            <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0 mt-0.5" />
                                            <p className="text-xs text-emerald-800 dark:text-emerald-300">
                                                Tudo pronto! O template parece completo.
                                            </p>
                                        </div>
                                    ) : (
                                        validationWarnings.map((warning, idx) => (
                                            <div key={idx} className="bg-amber-50 dark:bg-amber-950/20 border-l-4 border-amber-500 p-3 rounded-r-md flex gap-3">
                                                <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
                                                <p className="text-xs text-amber-800 dark:text-amber-300">
                                                    {warning}
                                                </p>
                                            </div>
                                        ))
                                    )}

                                    {/* Pro Tip */}
                                    <div className="bg-sky-50 dark:bg-sky-950/20 border-l-4 border-sky-500 p-3 rounded-r-md flex gap-3">
                                        <Lightbulb className="h-4 w-4 text-sky-600 shrink-0 mt-0.5" />
                                        <p className="text-xs text-sky-800 dark:text-sky-300">
                                            Dica: Adicione cláusulas de foro no final.
                                        </p>
                                    </div>
                                </div>
                            </aside>
                        </div>

                        <DialogFooter className="gap-2">
                            <Button
                                variant="outline"
                                onClick={() => setStep((prev) => (prev > 1 ? ((prev - 1) as WizardStep) : prev))}
                                disabled={loading}
                            >
                                Voltar
                            </Button>
                            {step < 5 && (
                                <Button onClick={() => setStep((prev) => ((prev + 1) as WizardStep))} disabled={loading}>
                                    Próximo: {steps.find((s) => s.id === ((step + 1) as WizardStep))?.label || 'Continuar'}
                                </Button>
                            )}
                            {step === 5 && (
                                <Button onClick={handleSave} disabled={loading}>
                                    Salvar Template
                                </Button>
                            )}
                        </DialogFooter>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}
