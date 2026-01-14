'use client';

import { useState, useRef, useEffect } from 'react';
import { Upload, FileAudio, FileVideo, Mic, CheckCircle, AlertCircle, Loader2, FileText, FileType, Book, MessageSquare, ChevronUp, ChevronDown, X, Users, Gavel, ListChecks, Star, Clock } from 'lucide-react';
import { toast } from 'sonner';
import apiClient from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
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
    const [transcriptionType, setTranscriptionType] = useState<'apostila' | 'hearing'>('apostila');
    const [mode, setMode] = useState('APOSTILA');
    const [thinkingLevel, setThinkingLevel] = useState('medium');
    const [customPrompt, setCustomPrompt] = useState('');
    const [highAccuracy, setHighAccuracy] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);
    const [selectedModel, setSelectedModel] = useState('gemini-3-flash-preview');
    const [result, setResult] = useState<string | null>(null);
    const [report, setReport] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState('preview');
    const [hearingCaseId, setHearingCaseId] = useState('');
    const [hearingGoal, setHearingGoal] = useState('alegacoes_finais');
    const [hearingPayload, setHearingPayload] = useState<any | null>(null);
    const [hearingTranscript, setHearingTranscript] = useState<string | null>(null);
    const [hearingFormatted, setHearingFormatted] = useState<string | null>(null);
    const [hearingFormatMode, setHearingFormatMode] = useState<'none' | 'audiencia' | 'depoimento' | 'custom'>('audiencia');
    const [hearingCustomPrompt, setHearingCustomPrompt] = useState('');
    const [hearingSpeakers, setHearingSpeakers] = useState<any[]>([]);
    const [enrollName, setEnrollName] = useState('');
    const [enrollRole, setEnrollRole] = useState('outro');
    const [enrollFile, setEnrollFile] = useState<File | null>(null);
    const [isEnrolling, setIsEnrolling] = useState(false);
    const [isSavingSpeakers, setIsSavingSpeakers] = useState(false);
    const [hearingCourt, setHearingCourt] = useState('');
    const [hearingCity, setHearingCity] = useState('');
    const [hearingDate, setHearingDate] = useState('');
    const [hearingNotes, setHearingNotes] = useState('');
    const [isDragActive, setIsDragActive] = useState(false);
    const [mediaUrl, setMediaUrl] = useState<string | null>(null);
    const [playbackRate, setPlaybackRate] = useState(1);
    const [currentTime, setCurrentTime] = useState(0);
    const [mediaDuration, setMediaDuration] = useState(0);
    const [activeSegmentId, setActiveSegmentId] = useState<string | null>(null);
    const [etaSeconds, setEtaSeconds] = useState<number | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const mediaRef = useRef<HTMLMediaElement | null>(null);

    // SSE Progress State
    const [progressStage, setProgressStage] = useState<string>('');
    const [progressPercent, setProgressPercent] = useState<number>(0);
    const [progressMessage, setProgressMessage] = useState<string>('');
    const [logs, setLogs] = useState<{ timestamp: string; message: string }[]>([]);

    // HIL Audit State
    const [auditIssues, setAuditIssues] = useState<any[]>([]);
    const [selectedIssues, setSelectedIssues] = useState<Set<string>>(new Set());
    const [isApplyingFixes, setIsApplyingFixes] = useState(false);
    const [recentCases, setRecentCases] = useState<any[]>([]);
    const [casesLoading, setCasesLoading] = useState(false);

    const isHearing = transcriptionType === 'hearing';
    const hearingRoles = [
        'juiz',
        'mp',
        'defesa',
        'testemunha',
        'serventuario',
        'parte',
        'perito',
        'outro',
    ];

    const formatDuration = (value?: number | null) => {
        if (value === null || value === undefined || Number.isNaN(value)) return '--:--';
        const total = Math.max(0, Math.floor(value));
        const hours = Math.floor(total / 3600);
        const minutes = Math.floor((total % 3600) / 60);
        const seconds = total % 60;
        if (hours > 0) {
            return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        }
        return `${minutes}:${String(seconds).padStart(2, '0')}`;
    };

    const formatTimestamp = (value?: number | null) => {
        if (value === null || value === undefined || Number.isNaN(value)) return '--:--';
        const total = Math.max(0, Math.floor(value));
        const hours = Math.floor(total / 3600);
        const minutes = Math.floor((total % 3600) / 60);
        const seconds = total % 60;
        return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    };

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

    const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
        e.preventDefault();
        setIsDragActive(false);
        const droppedFiles = Array.from(e.dataTransfer.files || []);
        if (droppedFiles.length === 0) return;
        setFiles(prev => [...prev, ...droppedFiles]);
    };

    const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
        e.preventDefault();
        setIsDragActive(true);
    };

    const handleDragLeave = () => {
        setIsDragActive(false);
    };

    useEffect(() => {
        if (!files[0]) {
            setMediaUrl(null);
            setMediaDuration(0);
            setCurrentTime(0);
            return;
        }
        const url = URL.createObjectURL(files[0]);
        setMediaUrl(url);
        return () => URL.revokeObjectURL(url);
    }, [files]);

    useEffect(() => {
        if (mediaRef.current) {
            mediaRef.current.playbackRate = playbackRate;
        }
    }, [playbackRate]);

    useEffect(() => {
        const loadCases = async () => {
            try {
                setCasesLoading(true);
                const data = await apiClient.getCases();
                setRecentCases(Array.isArray(data) ? data.slice(0, 5) : []);
            } catch (error) {
                console.error(error);
            } finally {
                setCasesLoading(false);
            }
        };
        loadCases();
    }, []);

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

    const buildHearingExportContent = () => {
        if (!hearingPayload) return result || '';
        const baseText = hearingFormatted || hearingTranscript || result || '';
        const segments = hearingPayload.segments || [];
        const speakers = hearingPayload.speakers || [];
        const evidence = hearingPayload.evidence || [];
        const timeline = hearingPayload.timeline || [];
        const contradictions = hearingPayload.contradictions || [];

        const metadataLines = [
            hearingCaseId ? `- Processo/Caso: ${hearingCaseId}` : null,
            hearingGoal ? `- Objetivo: ${hearingGoal}` : null,
            hearingCourt ? `- Vara/Tribunal: ${hearingCourt}` : null,
            hearingCity ? `- Comarca/Cidade: ${hearingCity}` : null,
            hearingDate ? `- Data: ${hearingDate}` : null,
            hearingNotes ? `- Observações: ${hearingNotes}` : null,
        ].filter(Boolean) as string[];

        const metadataSection = metadataLines.length
            ? ['## Metadados do Caso', '', ...metadataLines].join('\n')
            : '';

        const segmentMap = new Map(segments.map((seg: any) => [seg.id, seg]));
        const speakerMap = new Map(speakers.map((sp: any) => [sp.speaker_id, sp]));

        const evidenceLines = evidence.map((ev: any) => {
            const segId = (ev.segment_ids || [])[0];
            const seg = segmentMap.get(segId);
            const speaker = seg ? speakerMap.get(seg.speaker_id) : null;
            const labelBase = speaker?.name || speaker?.label || seg?.speaker_label || 'Falante';
            const role = speaker?.role ? ` (${speaker.role})` : '';
            const ts = seg?.timestamp_hint ? ` [${seg.timestamp_hint}]` : '';
            const reasons = (ev.relevance_reasons || []).join(', ');
            const reasonText = reasons ? ` (${reasons})` : '';
            return `| ${ev.claim_normalized || '-'} | ${ev.quote_verbatim || ''} | ${labelBase}${role}${ts} | ${ev.relevance_score ?? ''}${reasonText} |`;
        });

        const evidenceTable = [
            '## Quadro de Evidencias',
            '',
            '| Fato | Citacao | Falante | Relevancia |',
            '| --- | --- | --- | --- |',
            ...(evidenceLines.length > 0 ? evidenceLines : ['| - | - | - | - |']),
        ].join('\n');

        const timelineSection = timeline.length
            ? [
                '## Linha do tempo',
                '',
                ...timeline.map((item: any) => `- ${item.date}: ${item.summary || ''}`),
            ].join('\n')
            : '';

        const contradictionsSection = contradictions.length
            ? [
                '## Contradicoes',
                '',
                ...contradictions.map((item: any) => `- ${item.topic}: ${item.samples?.join(' | ') || ''}`),
            ].join('\n')
            : '';

        return [metadataSection, baseText, evidenceTable, timelineSection, contradictionsSection].filter(Boolean).join('\n\n');
    };

    const seekToTime = (time?: number | null) => {
        if (time === null || time === undefined || Number.isNaN(time)) return;
        if (!mediaRef.current) return;
        mediaRef.current.currentTime = Math.max(0, time);
        mediaRef.current.play().catch(() => {});
    };

    const handleSubmit = async () => {
        if (files.length === 0) {
            toast.error('Selecione pelo menos um arquivo de áudio ou vídeo.');
            return;
        }

        if (isHearing) {
            if (!hearingCaseId.trim()) {
                toast.error('Informe o número do processo/caso.');
                return;
            }
            if (files.length > 1) {
                toast.error('Para audiências/reuniões, envie apenas um arquivo por vez.');
                return;
            }
            if (hearingFormatMode === 'custom' && !hearingCustomPrompt.trim()) {
                toast.error('Informe o prompt personalizado para formatação.');
                return;
            }
        }

        setIsProcessing(true);
        setResult(null);
        setReport(null);
        setHearingPayload(null);
        setHearingTranscript(null);
        setHearingFormatted(null);
        setProgressStage('starting');
        setProgressPercent(0);
        setProgressMessage('Iniciando...');
        setLogs([]); // Clear logs
        setActiveSegmentId(null);
        setCurrentTime(0);
        const startTime = Date.now();
        setEtaSeconds(null);

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

            if (progress > 0 && progress < 100) {
                const elapsed = (Date.now() - startTime) / 1000;
                const totalEstimate = elapsed / (progress / 100);
                const remaining = Math.max(totalEstimate - elapsed, 0);
                setEtaSeconds(Math.round(remaining));
            }

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
            setEtaSeconds(null);
        };

        if (isHearing) {
            const formatEnabled = hearingFormatMode !== 'none';
            const formatMode =
                hearingFormatMode === 'custom'
                    ? 'AUDIENCIA'
                    : hearingFormatMode.toUpperCase();
            const customPrompt = hearingFormatMode === 'custom' ? hearingCustomPrompt.trim() : undefined;

            await apiClient.transcribeHearingStream(
                files[0],
                {
                    case_id: hearingCaseId.trim(),
                    goal: hearingGoal,
                    thinking_level: thinkingLevel,
                    model_selection: selectedModel,
                    high_accuracy: highAccuracy,
                    format_mode: formatMode,
                    custom_prompt: customPrompt,
                    format_enabled: formatEnabled,
                },
                onProgress,
                (payload) => {
                    const hearing = payload?.hearing || null;
                    setHearingPayload(hearing);
                    setHearingSpeakers(hearing?.speakers || []);
                    const transcript = hearing?.transcript_markdown || '';
                    const formatted = hearing?.formatted_text || null;
                    setHearingTranscript(transcript);
                    setHearingFormatted(formatted);
                    setResult(transcript);
                    setIsProcessing(false);
                    setProgressPercent(100);
                    setEtaSeconds(0);
                    setActiveTab('preview');
                    toast.success('Audiência processada com sucesso!');
                },
                onError
            );
            return;
        }

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
                    setEtaSeconds(0);
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
                    setEtaSeconds(0);
                    toast.success(`${totalFiles} arquivos transcritos e unificados!`);
                },
                onError
            );
        }
    };

    const handleExportMD = () => {
        if (isHearing ? !hearingTranscript : !result) return;
        const exportContent = isHearing ? buildHearingExportContent() : result;
        const blob = new Blob([exportContent], { type: 'text/markdown' });
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
        if (isHearing ? !hearingTranscript : !result) return;
        try {
            const exportContent = isHearing ? buildHearingExportContent() : result;
            const blob = await apiClient.exportDocx(exportContent, `transcricao-${new Date().getTime()}.docx`);
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
        if ((isHearing ? !hearingTranscript : !result) || files.length === 0) return;
        const displayName = files.length === 1 ? files[0].name : `${files.length}_aulas_unificadas`;
        try {
            toast.info('Salvando na biblioteca...');
            const content = isHearing ? buildHearingExportContent() : result;
            const doc = await apiClient.createDocumentFromText({
                title: `Transcrição: ${displayName}`,
                content,
                tags: isHearing ? 'transcricao,audiencia' : `transcricao,${mode.toLowerCase()}`
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

            const apiBase = process.env.NEXT_PUBLIC_API_URL || '/api';
            const response = await fetch(`${apiBase}/transcription/apply-revisions`, {
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

    const handleEnrollSpeaker = async () => {
        if (!enrollFile || !hearingCaseId.trim() || !enrollName.trim()) {
            toast.error('Informe caso, nome e áudio para enrollment.');
            return;
        }
        setIsEnrolling(true);
        try {
            const response = await apiClient.enrollHearingSpeaker(enrollFile, {
                case_id: hearingCaseId.trim(),
                name: enrollName.trim(),
                role: enrollRole,
            });
            toast.success('Voz cadastrada com sucesso!');
            if (response?.speaker) {
                setHearingSpeakers(prev => [...prev, response.speaker]);
            }
            setEnrollFile(null);
            setEnrollName('');
        } catch (error: any) {
            console.error(error);
            toast.error('Erro ao cadastrar voz.');
        } finally {
            setIsEnrolling(false);
        }
    };

    const handleSaveSpeakers = async () => {
        if (!hearingCaseId.trim() || hearingSpeakers.length === 0) return;
        setIsSavingSpeakers(true);
        try {
            await apiClient.updateHearingSpeakers(
                hearingCaseId.trim(),
                hearingSpeakers.map((sp: any) => ({
                    speaker_id: sp.speaker_id,
                    name: sp.name,
                    role: sp.role,
                }))
            );
            toast.success('Falantes atualizados!');
        } catch (error: any) {
            console.error(error);
            toast.error('Erro ao salvar falantes.');
        } finally {
            setIsSavingSpeakers(false);
        }
    };

    const hasOutput = isHearing ? Boolean(hearingTranscript) : Boolean(result);
    const primaryFile = files[0];
    const isVideoFile = Boolean(primaryFile?.type?.startsWith('video'));
    const hearingSegments = hearingPayload?.segments || [];
    const hearingBlocks = hearingPayload?.blocks || [];
    const speakerMap = new Map(hearingSpeakers.map((sp: any) => [sp.speaker_id, sp]));
    const blockMap = new Map(hearingBlocks.map((block: any) => [block.id, block]));
    const validationReport = hearingPayload?.reports?.validation || null;
    const analysisReport = hearingPayload?.reports?.analysis || null;
    const auditWarnings: string[] = hearingPayload?.audit?.warnings || [];

    const missingSpeakerNames = hearingSpeakers.filter((sp: any) => !sp.name || sp.name === sp.label).length;
    const segmentsMissingTime = hearingSegments.filter((seg: any) => seg.start == null && !seg.timestamp_hint).length;
    const validationItems = [
        {
            id: 'speaker_names',
            label: 'Falantes com nome definido',
            ok: missingSpeakerNames === 0,
            detail: missingSpeakerNames ? `${missingSpeakerNames} sem nome confirmado` : 'OK',
        },
        {
            id: 'timestamps',
            label: 'Segmentos com timestamp',
            ok: segmentsMissingTime === 0,
            detail: segmentsMissingTime ? `${segmentsMissingTime} sem timestamp` : 'OK',
        },
        {
            id: 'evidence',
            label: 'Evidências relevantes detectadas',
            ok: (hearingPayload?.evidence || []).length > 0,
            detail: `${(hearingPayload?.evidence || []).length} evidências`,
        },
        {
            id: 'formatting',
            label: 'Texto formatado disponível',
            ok: Boolean(hearingFormatted),
            detail: hearingFormatted ? 'Formato aplicado' : 'Sem formatação',
        },
    ];

    useEffect(() => {
        if (!isHearing || hearingSegments.length === 0) return;
        const active = hearingSegments.find((seg: any) => {
            if (typeof seg.start !== 'number' || typeof seg.end !== 'number') return false;
            return currentTime >= seg.start && currentTime < seg.end;
        });
        if (!active && activeSegmentId) {
            setActiveSegmentId(null);
            return;
        }
        if (active && active.id !== activeSegmentId) {
            setActiveSegmentId(active.id);
        }
    }, [currentTime, hearingSegments, isHearing, activeSegmentId]);

    useEffect(() => {
        if (!activeSegmentId) return;
        const el = document.getElementById(`segment-${activeSegmentId}`);
        if (el) {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }, [activeSegmentId]);

    return (
        <div className="flex h-full flex-col gap-6 p-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Transcrição (Aulas e Audiências)</h1>
                    <p className="text-muted-foreground">
                        Apostilas para aulas ou transcrição estruturada de audiências com quadro de evidências.
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
                        <div className="space-y-2">
                            <Label>Tipo de Transcrição</Label>
                            <select
                                className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                                value={transcriptionType}
                                onChange={(e) => {
                                    const value = e.target.value as 'apostila' | 'hearing';
                                    setTranscriptionType(value);
                                    setResult(null);
                                    setReport(null);
                                    setHearingPayload(null);
                                    setHearingTranscript(null);
                                    setHearingFormatted(null);
                                    setAuditIssues([]);
                                }}
                            >
                                <option value="apostila">📚 Aula / Apostila</option>
                                <option value="hearing">⚖️ Audiência / Reunião</option>
                            </select>
                        </div>

                        {/* Upload */}
                        <div className="space-y-2">
                            <Label>Arquivos (Áudio/Vídeo)</Label>
                            <div
                                className={`relative flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-4 text-center transition-colors ${isDragActive ? 'border-primary bg-primary/5' : 'border-muted-foreground/25'}`}
                                onDragOver={handleDragOver}
                                onDragLeave={handleDragLeave}
                                onDrop={handleDrop}
                            >
                                <input
                                    ref={fileInputRef}
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
                                <Upload className="h-5 w-5 text-muted-foreground" />
                                <div className="text-sm font-medium">
                                    Arraste e solte aqui ou clique para selecionar
                                </div>
                                <div className="text-xs text-muted-foreground">
                                    Áudio/Vídeo (mp3, wav, m4a, mp4, mov, mkv)
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

                        {!isHearing && (
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
                        )}

                        {isHearing && (
                            <div className="space-y-4">
                                <div className="space-y-2">
                                    <Label>Número do processo/caso</Label>
                                    <input
                                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                        placeholder="ex: 0001234-56.2024.8.26.0001"
                                        value={hearingCaseId}
                                        onChange={(e) => setHearingCaseId(e.target.value)}
                                    />
                                </div>
                                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                                    <div className="space-y-2">
                                        <Label>Vara/Tribunal</Label>
                                        <input
                                            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                            placeholder="Ex: 3ª Vara Cível"
                                            value={hearingCourt}
                                            onChange={(e) => setHearingCourt(e.target.value)}
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Comarca/Cidade</Label>
                                        <input
                                            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                            placeholder="Ex: São Paulo"
                                            value={hearingCity}
                                            onChange={(e) => setHearingCity(e.target.value)}
                                        />
                                    </div>
                                </div>
                                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                                    <div className="space-y-2">
                                        <Label>Data da audiência</Label>
                                        <input
                                            type="date"
                                            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                            value={hearingDate}
                                            onChange={(e) => setHearingDate(e.target.value)}
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Observações</Label>
                                        <input
                                            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                            placeholder="Ex: audiência de instrução"
                                            value={hearingNotes}
                                            onChange={(e) => setHearingNotes(e.target.value)}
                                        />
                                    </div>
                                </div>
                                <div className="space-y-2">
                                    <Label>Objetivo jurídico</Label>
                                    <select
                                        className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm"
                                        value={hearingGoal}
                                        onChange={(e) => setHearingGoal(e.target.value)}
                                    >
                                        <option value="peticao_inicial">Petição inicial</option>
                                        <option value="contestacao">Contestação</option>
                                        <option value="alegacoes_finais">Alegações finais</option>
                                        <option value="sentenca">Sentença</option>
                                    </select>
                                </div>
                                <div className="space-y-2">
                                    <Label>Texto formatado (opcional)</Label>
                                    <select
                                        className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm"
                                        value={hearingFormatMode}
                                        onChange={(e) => setHearingFormatMode(e.target.value as typeof hearingFormatMode)}
                                    >
                                        <option value="audiencia">Audiência (padrão)</option>
                                        <option value="depoimento">Depoimento</option>
                                        <option value="custom">Personalizado</option>
                                        <option value="none">Sem formatação</option>
                                    </select>
                                    {hearingFormatMode === 'custom' && (
                                        <textarea
                                            className="flex min-h-[90px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none"
                                            placeholder="Insira instruções de estilo/tabela para o texto formatado..."
                                            value={hearingCustomPrompt}
                                            onChange={(e) => setHearingCustomPrompt(e.target.value)}
                                        />
                                    )}
                                </div>
                                <div className="border rounded-md p-3 space-y-3">
                                    <div className="flex items-center gap-2 text-sm font-medium">
                                        <Users className="h-4 w-4" /> Enrollment de voz (opcional)
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Nome do falante</Label>
                                        <input
                                            className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                            value={enrollName}
                                            onChange={(e) => setEnrollName(e.target.value)}
                                            placeholder="Ex: Juiz Fulano"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Papel</Label>
                                        <select
                                            className="flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm"
                                            value={enrollRole}
                                            onChange={(e) => setEnrollRole(e.target.value)}
                                        >
                                            {hearingRoles.map(role => (
                                                <option key={role} value={role}>{role}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Áudio (10-30s)</Label>
                                        <input
                                            type="file"
                                            accept="audio/*,.mp3,.wav,.m4a,.aac"
                                            onChange={(e) => setEnrollFile(e.target.files?.[0] || null)}
                                        />
                                    </div>
                                    <Button variant="secondary" onClick={handleEnrollSpeaker} disabled={isEnrolling}>
                                        {isEnrolling ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Gavel className="mr-2 h-4 w-4" />}
                                        Cadastrar voz
                                    </Button>
                                </div>
                            </div>
                        )}

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

                        {!isHearing && (
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
                        )}

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

                        {!isHearing && (
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
                        )}

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
                        {hasOutput && (
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
                        {hasOutput ? (
                            <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-col h-[600px] w-full">
                                <div className="px-4 pt-2 border-b">
                                    <TabsList className="w-full justify-start">
                                        <TabsTrigger value="preview">{isHearing ? 'Transcrição' : 'Visualização'}</TabsTrigger>
                                        <TabsTrigger value="export">Exportar</TabsTrigger>
                                        {!isHearing && auditIssues.length > 0 && <TabsTrigger value="hil" className="text-orange-600">⚠️ Revisão HIL ({auditIssues.length})</TabsTrigger>}
                                        {!isHearing && <TabsTrigger value="quality">Controle de Qualidade</TabsTrigger>}
                                        {isHearing && hearingFormatted && <TabsTrigger value="formatted">Texto formatado</TabsTrigger>}
                                        {isHearing && <TabsTrigger value="speakers">Falantes</TabsTrigger>}
                                        {isHearing && <TabsTrigger value="evidence">Evidências</TabsTrigger>}
                                        {isHearing && <TabsTrigger value="validation">Validação</TabsTrigger>}
                                        {isHearing && (hearingPayload?.timeline || []).length > 0 && <TabsTrigger value="timeline">Linha do tempo</TabsTrigger>}
                                        {isHearing && (hearingPayload?.contradictions || []).length > 0 && <TabsTrigger value="contradictions">Contradições</TabsTrigger>}
                                        {isHearing && <TabsTrigger value="json">JSON</TabsTrigger>}
                                        {!isHearing && report && <TabsTrigger value="report">Relatório IA</TabsTrigger>}
                                    </TabsList>
                                </div>

                                {/* HIL Audit Issues Tab */}
                                {!isHearing && (
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
                                )}

                                <TabsContent value="preview" className="flex-1 overflow-hidden p-0 m-0 data-[state=active]:flex flex-col">
                                    {isHearing ? (
                                        <div className="flex h-full flex-col">
                                            <div className="border-b p-4 space-y-3">
                                                <div className="flex items-center justify-between text-sm">
                                                    <span className="font-medium">Reprodutor de áudio</span>
                                                    <span className="text-xs text-muted-foreground">
                                                        {formatDuration(currentTime)} / {formatDuration(mediaDuration)}
                                                    </span>
                                                </div>
                                                {mediaUrl ? (
                                                    isVideoFile ? (
                                                        <video
                                                            ref={mediaRef}
                                                            src={mediaUrl}
                                                            controls
                                                            className="w-full rounded-md border"
                                                            onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
                                                            onLoadedMetadata={(e) => setMediaDuration(e.currentTarget.duration || 0)}
                                                        />
                                                    ) : (
                                                        <audio
                                                            ref={mediaRef}
                                                            src={mediaUrl}
                                                            controls
                                                            className="w-full"
                                                            onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
                                                            onLoadedMetadata={(e) => setMediaDuration(e.currentTarget.duration || 0)}
                                                        />
                                                    )
                                                ) : (
                                                    <div className="text-xs text-muted-foreground">
                                                        Carregue um arquivo para habilitar o player.
                                                    </div>
                                                )}
                                                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                                                    <div className="flex items-center gap-2">
                                                        <span>Velocidade:</span>
                                                        <select
                                                            className="rounded-md border border-input bg-background px-2 py-1 text-xs"
                                                            value={playbackRate}
                                                            onChange={(e) => setPlaybackRate(Number(e.target.value))}
                                                        >
                                                            <option value={0.75}>0.75x</option>
                                                            <option value={1}>1x</option>
                                                            <option value={1.25}>1.25x</option>
                                                            <option value={1.5}>1.5x</option>
                                                            <option value={2}>2x</option>
                                                        </select>
                                                    </div>
                                                    <div className="flex items-center gap-1">
                                                        <Clock className="h-3 w-3" />
                                                        <span>Sincronizado por timestamp</span>
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="flex-1 overflow-y-auto p-4 space-y-2 bg-muted/50">
                                                {hearingSegments.length === 0 && (
                                                    <pre className="whitespace-pre-wrap text-sm font-mono text-foreground">
                                                        {(hearingTranscript || '').replace(/<!--\s*RELATÓRIO:[\s\S]*?-->/i, '')}
                                                    </pre>
                                                )}
                                                {hearingSegments.map((seg: any) => {
                                                    const speaker = speakerMap.get(seg.speaker_id) || {};
                                                    const label = speaker?.name || speaker?.label || seg.speaker_label || 'Falante';
                                                    const role = speaker?.role ? ` (${speaker.role})` : '';
                                                    const timeLabel = seg.timestamp_hint || formatTimestamp(seg.start);
                                                    const isActive = seg.id === activeSegmentId;
                                                    const canSeek = typeof seg.start === 'number';
                                                    return (
                                                        <div
                                                            key={seg.id}
                                                            id={`segment-${seg.id}`}
                                                            className={`rounded-md border p-3 space-y-2 ${isActive ? 'border-primary bg-primary/5' : 'border-border bg-card'}`}
                                                        >
                                                            <div className="flex items-center justify-between text-xs text-muted-foreground">
                                                                {canSeek ? (
                                                                    <button
                                                                        className="font-mono hover:text-primary"
                                                                        onClick={() => seekToTime(seg.start)}
                                                                    >
                                                                        {timeLabel}
                                                                    </button>
                                                                ) : (
                                                                    <span className="font-mono">{timeLabel}</span>
                                                                )}
                                                                <span>{seg.id}</span>
                                                            </div>
                                                            <div className="text-sm font-medium">{label}{role}</div>
                                                            <div className="text-sm text-muted-foreground whitespace-pre-wrap">{seg.text}</div>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="flex-1 overflow-y-auto p-4 bg-muted/50">
                                            <pre className="whitespace-pre-wrap text-sm font-mono text-foreground">
                                                {(result || '').replace(/<!--\s*RELATÓRIO:[\s\S]*?-->/i, '')}
                                            </pre>
                                        </div>
                                    )}
                                </TabsContent>

                                <TabsContent value="export" className="flex-1 overflow-y-auto p-4 m-0 space-y-4">
                                    <div className="border rounded-md p-4 space-y-2">
                                        <div className="text-sm font-medium">Download</div>
                                        <div className="flex flex-wrap gap-2">
                                            <Button variant="outline" onClick={handleExportMD} disabled={!hasOutput}>
                                                <FileText className="mr-2 h-4 w-4" /> Markdown
                                            </Button>
                                            <Button variant="outline" onClick={handleExportDocx} disabled={!hasOutput}>
                                                <FileType className="mr-2 h-4 w-4" /> Word
                                            </Button>
                                        </div>
                                    </div>
                                    <div className="border rounded-md p-4 space-y-2">
                                        <div className="text-sm font-medium">Envio direto</div>
                                        <div className="flex flex-wrap gap-2">
                                            <Button variant="outline" onClick={() => handleSaveToLibrary(false)} disabled={!hasOutput}>
                                                <Book className="mr-2 h-4 w-4" /> Salvar na biblioteca
                                            </Button>
                                            <Button onClick={() => handleSaveToLibrary(true)} disabled={!hasOutput}>
                                                <MessageSquare className="mr-2 h-4 w-4" /> Salvar e conversar
                                            </Button>
                                        </div>
                                    </div>
                                    <div className="border rounded-md p-4 space-y-2">
                                        <div className="text-sm font-medium">Preview</div>
                                        <Button variant="ghost" onClick={() => setActiveTab('preview')}>
                                            Abrir visualização
                                        </Button>
                                    </div>
                                </TabsContent>

                                {!isHearing && (
                                <TabsContent value="quality" className="flex-1 overflow-y-auto p-4 m-0">
                                    <QualityPanel
                                        rawContent={result} // TODO: In a real flow, we'd have separate Raw vs Formatted. For now, using result as base.
                                        formattedContent={result}
                                        documentName={files[0]?.name || 'Documento'}
                                        onContentUpdated={setResult}
                                    />
                                </TabsContent>
                                )}

                                {!isHearing && report && (
                                    <TabsContent value="report" className="flex-1 overflow-y-auto p-4 m-0">
                                        <div className="bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 p-3 rounded-md text-sm font-medium whitespace-pre-wrap">
                                            {report}
                                        </div>
                                    </TabsContent>
                                )}

                                {isHearing && (
                                    <>
                                        {hearingFormatted && (
                                            <TabsContent value="formatted" className="flex-1 overflow-y-auto p-4 m-0">
                                                <pre className="whitespace-pre-wrap text-sm font-mono text-foreground">
                                                    {hearingFormatted}
                                                </pre>
                                            </TabsContent>
                                        )}
                                        <TabsContent value="speakers" className="flex-1 overflow-y-auto p-4 m-0 space-y-4">
                                            <div className="flex items-center justify-between">
                                                <div className="text-sm text-muted-foreground">
                                                    Edite nomes e papéis. As alterações sobrescrevem o automático.
                                                </div>
                                                <Button size="sm" onClick={handleSaveSpeakers} disabled={isSavingSpeakers || hearingSpeakers.length === 0}>
                                                    {isSavingSpeakers ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                                                    Salvar falantes
                                                </Button>
                                            </div>
                                            <div className="space-y-2">
                                                {hearingSpeakers.map((sp) => (
                                                    <div key={sp.speaker_id} className="grid grid-cols-1 md:grid-cols-4 gap-2 border rounded-md p-3">
                                                        <div>
                                                            <Label className="text-xs">Label</Label>
                                                            <div className="text-sm font-mono">{sp.label}</div>
                                                        </div>
                                                        <div>
                                                            <Label className="text-xs">Nome</Label>
                                                            <input
                                                                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                                                                value={sp.name || ''}
                                                                onChange={(e) => {
                                                                    const value = e.target.value;
                                                                    setHearingSpeakers(prev => prev.map(item => item.speaker_id === sp.speaker_id ? { ...item, name: value } : item));
                                                                }}
                                                            />
                                                        </div>
                                                        <div>
                                                            <Label className="text-xs">Papel</Label>
                                                            <select
                                                                className="flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm"
                                                                value={sp.role || 'outro'}
                                                                onChange={(e) => {
                                                                    const value = e.target.value;
                                                                    setHearingSpeakers(prev => prev.map(item => item.speaker_id === sp.speaker_id ? { ...item, role: value } : item));
                                                                }}
                                                            >
                                                                {hearingRoles.map(role => (
                                                                    <option key={role} value={role}>{role}</option>
                                                                ))}
                                                            </select>
                                                        </div>
                                                        <div>
                                                            <Label className="text-xs">Confiança</Label>
                                                            <div className="text-sm">
                                                                {typeof sp.confidence === 'number'
                                                                    ? `${Math.round(sp.confidence * 100)}%`
                                                                    : '-'}
                                                            </div>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        </TabsContent>

                                        <TabsContent value="evidence" className="flex-1 overflow-y-auto p-4 m-0 space-y-3">
                                            <div className="flex items-center gap-2 text-sm font-medium">
                                                <ListChecks className="h-4 w-4" /> Quadro de evidências
                                            </div>
                                            <div className="space-y-2">
                                                {(hearingPayload?.evidence || []).length === 0 && (
                                                    <p className="text-sm text-muted-foreground">Nenhuma evidência relevante acima do limiar.</p>
                                                )}
                                                {(hearingPayload?.evidence || []).map((ev: any) => {
                                                    const block = blockMap.get(ev.block_id) || {};
                                                    const topics = (ev.topics && ev.topics.length > 0) ? ev.topics : (block.topics || []);
                                                    return (
                                                        <div key={ev.id} className="border rounded-md p-3 space-y-2">
                                                            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                                                                <span className="flex items-center gap-1">
                                                                    <Star className="h-3 w-3" />
                                                                    {ev.relevance_score ?? '-'}
                                                                </span>
                                                                {block.act_type && <span className="rounded-full bg-muted px-2 py-0.5">Tipo: {block.act_type}</span>}
                                                                {topics.length > 0 && <span className="rounded-full bg-muted px-2 py-0.5">Tema: {topics.join(', ')}</span>}
                                                                {ev.relevance_reasons?.length ? (
                                                                    <span className="rounded-full bg-muted px-2 py-0.5">Motivos: {ev.relevance_reasons.join(', ')}</span>
                                                                ) : null}
                                                            </div>
                                                            <div className="text-sm font-medium">{ev.claim_normalized || 'Fato identificado'}</div>
                                                            <div className="text-sm text-muted-foreground">{ev.quote_verbatim}</div>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </TabsContent>

                                        <TabsContent value="validation" className="flex-1 overflow-y-auto p-4 m-0 space-y-4">
                                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                                <div className="border rounded-md p-4 space-y-3">
                                                    <div className="text-sm font-medium">Checklist de qualidade</div>
                                                    <div className="space-y-2">
                                                        {validationItems.map(item => (
                                                            <div key={item.id} className="flex items-start gap-2 text-sm">
                                                                {item.ok ? (
                                                                    <CheckCircle className="h-4 w-4 text-emerald-600" />
                                                                ) : (
                                                                    <AlertCircle className="h-4 w-4 text-orange-600" />
                                                                )}
                                                                <div>
                                                                    <div className="font-medium">{item.label}</div>
                                                                    <div className="text-xs text-muted-foreground">{item.detail}</div>
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>
                                                <div className="border rounded-md p-4 space-y-3">
                                                    <div className="text-sm font-medium">Estatísticas</div>
                                                    <div className="grid grid-cols-2 gap-3 text-xs text-muted-foreground">
                                                        <div>Segmentos: <span className="text-foreground font-medium">{hearingSegments.length}</span></div>
                                                        <div>Falantes: <span className="text-foreground font-medium">{hearingSpeakers.length}</span></div>
                                                        <div>Evidências: <span className="text-foreground font-medium">{(hearingPayload?.evidence || []).length}</span></div>
                                                        <div>Claims: <span className="text-foreground font-medium">{(hearingPayload?.claims || []).length}</span></div>
                                                        <div>Contradições: <span className="text-foreground font-medium">{(hearingPayload?.contradictions || []).length}</span></div>
                                                        <div>Timeline: <span className="text-foreground font-medium">{(hearingPayload?.timeline || []).length}</span></div>
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="border rounded-md p-4 space-y-2">
                                                <div className="text-sm font-medium">Itens a revisar</div>
                                                <div className="space-y-1 text-sm text-muted-foreground">
                                                    {auditWarnings.length === 0 && !validationReport && !analysisReport && (
                                                        <div>Sem alertas adicionais.</div>
                                                    )}
                                                    {auditWarnings.length > 0 && (
                                                        <div>
                                                            <div className="font-medium text-foreground">Alertas do pipeline</div>
                                                            <ul className="list-disc list-inside">
                                                                {auditWarnings.map((warning) => (
                                                                    <li key={warning}>
                                                                        {warning === 'sem_match_enrollment' && 'Sem correspondência de enrollment'}
                                                                        {warning === 'sem_formatacao' && 'Texto sem formatação aplicada'}
                                                                        {warning === 'act_classification_truncated' && 'Classificação de atos truncada'}
                                                                        {warning === 'claims_truncated' && 'Claims truncados (limite de evidências)'}
                                                                        {!['sem_match_enrollment', 'sem_formatacao', 'act_classification_truncated', 'claims_truncated'].includes(warning) && warning}
                                                                    </li>
                                                                ))}
                                                            </ul>
                                                        </div>
                                                    )}
                                                    {validationReport && (
                                                        <div className="space-y-1">
                                                            <div className="font-medium text-foreground">Validação de fidelidade</div>
                                                            <div>Score: {validationReport.score ?? '-'} / 10</div>
                                                            {validationReport.omissions?.length ? (
                                                                <div>Omissões: {validationReport.omissions.length}</div>
                                                            ) : null}
                                                            {validationReport.structural_issues?.length ? (
                                                                <div>Problemas estruturais: {validationReport.structural_issues.length}</div>
                                                            ) : null}
                                                        </div>
                                                    )}
                                                    {analysisReport && (
                                                        <div className="space-y-1">
                                                            <div className="font-medium text-foreground">Análise estrutural</div>
                                                            <div>Issues pendentes: {analysisReport.total_issues ?? 0}</div>
                                                            {analysisReport.compression_warning && (
                                                                <div>Compressão excessiva detectada</div>
                                                            )}
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        </TabsContent>

                                        {(hearingPayload?.timeline || []).length > 0 && (
                                            <TabsContent value="timeline" className="flex-1 overflow-y-auto p-4 m-0 space-y-2">
                                                {(hearingPayload?.timeline || []).map((item: any) => (
                                                    <div key={item.id} className="border rounded-md p-3">
                                                        <div className="text-xs text-muted-foreground">{item.date}</div>
                                                        <div className="text-sm">{item.summary}</div>
                                                    </div>
                                                ))}
                                            </TabsContent>
                                        )}

                                        {(hearingPayload?.contradictions || []).length > 0 && (
                                            <TabsContent value="contradictions" className="flex-1 overflow-y-auto p-4 m-0 space-y-2">
                                                {(hearingPayload?.contradictions || []).map((item: any) => (
                                                    <div key={item.id} className="border rounded-md p-3 space-y-1">
                                                        <div className="text-sm font-medium">{item.topic}</div>
                                                        <div className="text-xs text-muted-foreground">{item.reason}</div>
                                                        <div className="text-sm">{(item.samples || []).join(' | ')}</div>
                                                    </div>
                                                ))}
                                            </TabsContent>
                                        )}

                                        <TabsContent value="json" className="flex-1 overflow-y-auto p-4 m-0">
                                            <pre className="whitespace-pre-wrap text-xs font-mono">
                                                {JSON.stringify(hearingPayload, null, 2)}
                                            </pre>
                                        </TabsContent>
                                    </>
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

                                        <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground mb-4">
                                            <Clock className="h-3 w-3" />
                                            <span>
                                                ETA {etaSeconds !== null ? formatDuration(etaSeconds) : 'calculando...'}
                                            </span>
                                        </div>

                                        <div className="flex justify-between text-xs text-muted-foreground mt-2 mb-6">
                                            <span className={progressStage === 'audio_optimization' ? 'text-primary font-medium' : ''}>
                                                🔊 Áudio
                                            </span>
                                            <span className={progressStage === 'transcription' ? 'text-primary font-medium' : ''}>
                                                🎙️ Transcrição
                                            </span>
                                            <span className={progressStage === 'formatting' || progressStage === 'structuring' ? 'text-primary font-medium' : ''}>
                                                {isHearing ? '🧾 Estruturação' : '✨ Formatação'}
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

                <Card className="col-span-1 h-fit">
                    <CardHeader>
                        <CardTitle>Dashboard de Casos</CardTitle>
                        <CardDescription>Histórico recente, status e ações rápidas.</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        {casesLoading && (
                            <div className="text-sm text-muted-foreground">Carregando casos...</div>
                        )}
                        {!casesLoading && recentCases.length === 0 && (
                            <div className="text-sm text-muted-foreground">Nenhum caso cadastrado.</div>
                        )}
                        {recentCases.map((caseItem: any) => (
                            <div key={caseItem.id} className="flex items-center justify-between gap-2 rounded-md border p-3">
                                <div className="space-y-1">
                                    <div className="text-sm font-medium">{caseItem.title}</div>
                                    <div className="text-xs text-muted-foreground">
                                        {caseItem.process_number || 'Sem nº processo'}
                                    </div>
                                </div>
                                <div className="flex items-center gap-2">
                                    <Badge variant="secondary">{caseItem.status || 'ativo'}</Badge>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => {
                                            window.location.href = `/cases/${caseItem.id}`;
                                        }}
                                    >
                                        Abrir
                                    </Button>
                                </div>
                            </div>
                        ))}
                        <Button variant="ghost" className="w-full" onClick={() => (window.location.href = '/cases')}>
                            Ver todos os casos
                        </Button>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
