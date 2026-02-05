'use client';

import { useState, useCallback } from 'react';
import {
  Upload,
  FileText,
  X,
  Sparkles,
  ChevronRight,
  ChevronLeft,
  Check,
  AlertCircle,
  Pencil,
  Trash2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import {
  type PlaybookArea,
  type ExtractedRule,
  AREA_LABELS,
  useExtractRulesFromUpload,
  useConfirmImportFromUpload,
} from '../hooks';

interface ImportFromDocumentProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onComplete: (playbookId: string) => void;
}

type Step = 'upload' | 'processing' | 'review';

const SEVERITY_LABELS_MAP: Record<string, string> = {
  low: 'Baixa',
  medium: 'Media',
  high: 'Alta',
  critical: 'Critica',
};

const SEVERITY_COLORS_MAP: Record<string, string> = {
  low: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  medium: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  high: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  critical: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
};

const ACTION_LABELS: Record<string, string> = {
  redline: 'Redline',
  flag: 'Sinalizar',
  block: 'Bloquear',
  suggest: 'Sugerir alteracao',
};

export function ImportFromDocument({
  open,
  onOpenChange,
  onComplete,
}: ImportFromDocumentProps) {
  const [step, setStep] = useState<Step>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [area, setArea] = useState<PlaybookArea>('outro');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [progress, setProgress] = useState(0);
  const [extractedRules, setExtractedRules] = useState<ExtractedRule[]>([]);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const extractMutation = useExtractRulesFromUpload();
  const confirmMutation = useConfirmImportFromUpload();

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selected = e.target.files?.[0];
      if (!selected) return;

      const nameLower = selected.name.toLowerCase();
      if (!nameLower.endsWith('.pdf') && !nameLower.endsWith('.docx')) {
        setError('Formato nao suportado. Envie um arquivo PDF ou DOCX.');
        return;
      }

      setFile(selected);
      setError(null);

      // Auto-fill name from filename
      if (!name) {
        const baseName = selected.name.replace(/\.(pdf|docx)$/i, '');
        setName(baseName);
      }

      e.target.value = '';
    },
    [name]
  );

  const handleExtract = async () => {
    if (!file) return;

    setStep('processing');
    setProgress(0);
    setError(null);

    // Simulate progress
    const progressInterval = setInterval(() => {
      setProgress((prev) => Math.min(prev + Math.random() * 12, 90));
    }, 600);

    try {
      const result = await extractMutation.mutateAsync({
        file,
        area,
      });

      clearInterval(progressInterval);
      setProgress(100);

      setExtractedRules(result.rules);

      setTimeout(() => {
        setStep('review');
      }, 400);
    } catch (err: any) {
      clearInterval(progressInterval);
      // Extract error message safely — err.detail may be an array (FastAPI validation)
      // or err may be an AxiosError with response.data.detail
      const rawDetail =
        err?.response?.data?.detail ??
        err?.detail ??
        err?.message ??
        'Erro ao processar o documento.';
      // Ensure we always set a string (React #185 = objects not valid as React child)
      const detail =
        typeof rawDetail === 'string'
          ? rawDetail
          : Array.isArray(rawDetail)
            ? rawDetail.map((d: any) => (typeof d === 'string' ? d : d?.msg ?? JSON.stringify(d))).join('; ')
            : JSON.stringify(rawDetail);
      setError(detail);
      setStep('upload');
    }
  };

  const handleConfirm = async () => {
    if (extractedRules.length === 0 || !name.trim()) return;

    try {
      const result = await confirmMutation.mutateAsync({
        name: name.trim(),
        area,
        description: description.trim() || undefined,
        rules: extractedRules,
      });

      if (result.playbook_id) {
        onComplete(result.playbook_id);
        handleClose();
      }
    } catch (err: any) {
      const rawDetail =
        err?.response?.data?.detail ??
        err?.detail ??
        err?.message ??
        'Erro ao criar o playbook.';
      const detail =
        typeof rawDetail === 'string'
          ? rawDetail
          : Array.isArray(rawDetail)
            ? rawDetail.map((d: any) => (typeof d === 'string' ? d : d?.msg ?? JSON.stringify(d))).join('; ')
            : JSON.stringify(rawDetail);
      setError(detail);
    }
  };

  const handleClose = () => {
    setStep('upload');
    setFile(null);
    setArea('outro');
    setName('');
    setDescription('');
    setProgress(0);
    setExtractedRules([]);
    setEditingIdx(null);
    setError(null);
    onOpenChange(false);
  };

  const removeRule = (idx: number) => {
    setExtractedRules((prev) => prev.filter((_, i) => i !== idx));
    if (editingIdx === idx) setEditingIdx(null);
  };

  const updateRule = (idx: number, updates: Partial<ExtractedRule>) => {
    setExtractedRules((prev) =>
      prev.map((rule, i) => (i === idx ? { ...rule, ...updates } : rule))
    );
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const stepIndicators = [
    { key: 'upload', label: '1. Upload e Config' },
    { key: 'processing', label: '2. Processando' },
    { key: 'review', label: '3. Revisar Regras' },
  ];

  const currentStepIdx = stepIndicators.findIndex((s) => s.key === step);

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5 text-emerald-500" />
            Importar Playbook de Documento
          </DialogTitle>
          <DialogDescription>
            Envie um PDF ou DOCX de playbook e a IA extraira as regras automaticamente.
          </DialogDescription>
        </DialogHeader>

        {/* Step indicators */}
        <div className="flex items-center gap-2 py-2">
          {stepIndicators.map((s, idx) => (
            <div key={s.key} className="flex items-center gap-2">
              {idx > 0 && <div className="h-px w-4 bg-slate-200 dark:bg-slate-700" />}
              <span
                className={cn(
                  'text-xs font-medium px-2 py-1 rounded-full transition-colors',
                  idx === currentStepIdx
                    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300'
                    : idx < currentStepIdx
                      ? 'bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-300'
                      : 'text-slate-400'
                )}
              >
                {idx < currentStepIdx && <Check className="h-3 w-3 inline mr-1" />}
                {s.label}
              </span>
            </div>
          ))}
        </div>

        {/* Step 1: Upload + Config */}
        {step === 'upload' && (
          <div className="space-y-4 py-2">
            {/* File upload */}
            <div className="border-2 border-dashed border-slate-200 dark:border-slate-700 rounded-xl p-6 text-center hover:border-emerald-300 dark:hover:border-emerald-700 transition-colors">
              {!file ? (
                <>
                  <Upload className="h-8 w-8 text-slate-400 mx-auto mb-3" />
                  <p className="text-sm text-slate-600 dark:text-slate-300 mb-1">
                    Arraste o documento aqui ou clique para selecionar
                  </p>
                  <p className="text-xs text-slate-400 mb-3">PDF ou DOCX</p>
                  <label>
                    <input
                      type="file"
                      accept=".pdf,.docx"
                      onChange={handleFileSelect}
                      className="hidden"
                    />
                    <Button variant="outline" className="gap-2" asChild>
                      <span>
                        <Upload className="h-4 w-4" />
                        Selecionar Arquivo
                      </span>
                    </Button>
                  </label>
                </>
              ) : (
                <div className="flex items-center gap-3 justify-center">
                  <FileText className="h-5 w-5 text-emerald-500 shrink-0" />
                  <span className="text-sm text-slate-700 dark:text-slate-300 truncate">
                    {file.name}
                  </span>
                  <span className="text-[10px] text-slate-400 shrink-0">
                    {formatFileSize(file.size)}
                  </span>
                  <button
                    onClick={() => setFile(null)}
                    className="text-slate-400 hover:text-red-500 transition-colors shrink-0"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
            </div>

            {error && (
              <div className="rounded-lg bg-red-50 dark:bg-red-900/10 border border-red-200 dark:border-red-800 p-3 flex items-start gap-2">
                <AlertCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
                <p className="text-xs text-red-700 dark:text-red-300">{error}</p>
              </div>
            )}

            {/* Config fields */}
            <div className="space-y-3">
              <div className="space-y-2">
                <Label>Nome do Playbook *</Label>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Ex: Playbook de Contratos de TI"
                />
              </div>
              <div className="space-y-2">
                <Label>Descricao</Label>
                <Textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Descricao opcional..."
                  rows={2}
                />
              </div>
              <div className="space-y-2">
                <Label>Area Juridica *</Label>
                <Select value={area} onValueChange={(v) => setArea(v as PlaybookArea)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(Object.entries(AREA_LABELS) as [PlaybookArea, string][]).map(([key, label]) => (
                      <SelectItem key={key} value={key}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="rounded-lg bg-blue-50 dark:bg-blue-900/10 border border-blue-200 dark:border-blue-800 p-3 flex items-start gap-2">
              <AlertCircle className="h-4 w-4 text-blue-500 shrink-0 mt-0.5" />
              <p className="text-xs text-blue-700 dark:text-blue-300">
                A IA analisara o documento para extrair regras de revisao contratual.
                Voce podera revisar e editar cada regra antes de salvar. O processo pode levar alguns minutos.
              </p>
            </div>

            <div className="flex justify-end">
              <Button
                onClick={handleExtract}
                disabled={!file || !name.trim()}
                className="bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white gap-2"
              >
                <Sparkles className="h-4 w-4" />
                Extrair Regras com IA
              </Button>
            </div>
          </div>
        )}

        {/* Step 2: Processing */}
        {step === 'processing' && (
          <div className="py-12 text-center space-y-6">
            <div className="relative mx-auto h-16 w-16">
              <div className="absolute inset-0 rounded-full bg-gradient-to-br from-emerald-500 to-teal-600 animate-spin [animation-duration:3s] opacity-30" />
              <div className="absolute inset-[3px] rounded-full bg-background" />
              <div className="absolute inset-0 flex items-center justify-center">
                <Sparkles className="h-6 w-6 text-emerald-500 animate-pulse" />
              </div>
            </div>
            <div>
              <p className="text-lg font-semibold text-slate-800 dark:text-slate-200">
                Analisando documento...
              </p>
              <p className="text-sm text-slate-500 mt-1">
                A IA esta extraindo regras de revisao do documento
              </p>
            </div>
            <div className="max-w-xs mx-auto space-y-2">
              <Progress value={progress} className="h-2" />
              <p className="text-xs text-slate-400">{Math.round(progress)}% concluido</p>
            </div>
            <div className="space-y-1 text-xs text-slate-400">
              {progress < 30 && <p>Extraindo texto do documento...</p>}
              {progress >= 30 && progress < 60 && <p>Identificando regras e clausulas...</p>}
              {progress >= 60 && progress < 90 && <p>Estruturando regras de revisao...</p>}
              {progress >= 90 && <p>Finalizando...</p>}
            </div>
          </div>
        )}

        {/* Step 3: Review */}
        {step === 'review' && (
          <div className="space-y-4 py-2">
            <div className="rounded-lg bg-green-50 dark:bg-green-900/10 border border-green-200 dark:border-green-800 p-3 flex items-center gap-2">
              <Check className="h-4 w-4 text-green-600 shrink-0" />
              <p className="text-sm text-green-700 dark:text-green-300">
                {extractedRules.length} regra(s) extraida(s) com sucesso. Revise e edite antes de confirmar.
              </p>
            </div>

            <div className="space-y-3 max-h-[50vh] overflow-y-auto pr-1">
              {extractedRules.map((rule, idx) => (
                <div
                  key={idx}
                  className="rounded-lg border border-slate-200 dark:border-slate-700 p-4 space-y-2"
                >
                  {/* Rule header */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 min-w-0">
                      <h4 className="font-medium text-sm text-slate-800 dark:text-slate-200 truncate">
                        {rule.rule_name}
                      </h4>
                      <Badge variant="outline" className="text-[10px] shrink-0">
                        {rule.clause_type}
                      </Badge>
                      <Badge
                        className={cn(
                          'text-[10px] border-0 shrink-0',
                          SEVERITY_COLORS_MAP[rule.severity] || SEVERITY_COLORS_MAP.medium
                        )}
                      >
                        {SEVERITY_LABELS_MAP[rule.severity] || rule.severity}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        onClick={() => setEditingIdx(editingIdx === idx ? null : idx)}
                        className="p-1 text-slate-400 hover:text-indigo-500 transition-colors"
                        title="Editar regra"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => removeRule(idx)}
                        className="p-1 text-slate-400 hover:text-red-500 transition-colors"
                        title="Remover regra"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* Collapsed view */}
                  {editingIdx !== idx && (
                    <div className="text-xs space-y-1">
                      <p className="text-green-700 dark:text-green-400">
                        <span className="font-semibold">Preferida:</span>{' '}
                        {rule.preferred_position || '(nao definida)'}
                      </p>
                      {rule.fallback_positions.length > 0 && (
                        <p className="text-yellow-700 dark:text-yellow-400">
                          <span className="font-semibold">Alternativas:</span>{' '}
                          {rule.fallback_positions.join(' | ')}
                        </p>
                      )}
                      {rule.rejected_positions.length > 0 && (
                        <p className="text-red-700 dark:text-red-400">
                          <span className="font-semibold">Rejeitadas:</span>{' '}
                          {rule.rejected_positions.join(' | ')}
                        </p>
                      )}
                      <p className="text-slate-500">
                        <span className="font-semibold">Acao:</span>{' '}
                        {ACTION_LABELS[rule.action_on_reject] || rule.action_on_reject}
                      </p>
                    </div>
                  )}

                  {/* Expanded edit view */}
                  {editingIdx === idx && (
                    <div className="space-y-3 pt-2 border-t border-slate-100 dark:border-slate-800">
                      <div className="grid grid-cols-2 gap-3">
                        <div className="space-y-1">
                          <Label className="text-[11px]">Nome da Regra</Label>
                          <Input
                            value={rule.rule_name}
                            onChange={(e) => updateRule(idx, { rule_name: e.target.value })}
                            className="h-8 text-sm"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-[11px]">Tipo de Clausula</Label>
                          <Input
                            value={rule.clause_type}
                            onChange={(e) => updateRule(idx, { clause_type: e.target.value })}
                            className="h-8 text-sm"
                          />
                        </div>
                      </div>

                      <div className="space-y-1">
                        <Label className="text-[11px]">Posicao Preferida</Label>
                        <Textarea
                          value={rule.preferred_position}
                          onChange={(e) => updateRule(idx, { preferred_position: e.target.value })}
                          rows={2}
                          className="text-sm"
                        />
                      </div>

                      <div className="space-y-1">
                        <Label className="text-[11px]">
                          Alternativas (uma por linha)
                        </Label>
                        <Textarea
                          value={rule.fallback_positions.join('\n')}
                          onChange={(e) =>
                            updateRule(idx, {
                              fallback_positions: e.target.value
                                .split('\n')
                                .filter((s) => s.trim()),
                            })
                          }
                          rows={2}
                          className="text-sm"
                        />
                      </div>

                      <div className="space-y-1">
                        <Label className="text-[11px]">
                          Posicoes Rejeitadas (uma por linha)
                        </Label>
                        <Textarea
                          value={rule.rejected_positions.join('\n')}
                          onChange={(e) =>
                            updateRule(idx, {
                              rejected_positions: e.target.value
                                .split('\n')
                                .filter((s) => s.trim()),
                            })
                          }
                          rows={2}
                          className="text-sm"
                        />
                      </div>

                      <div className="grid grid-cols-2 gap-3">
                        <div className="space-y-1">
                          <Label className="text-[11px]">Severidade</Label>
                          <Select
                            value={rule.severity}
                            onValueChange={(v) => updateRule(idx, { severity: v })}
                          >
                            <SelectTrigger className="h-8 text-sm">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="low">Baixa</SelectItem>
                              <SelectItem value="medium">Media</SelectItem>
                              <SelectItem value="high">Alta</SelectItem>
                              <SelectItem value="critical">Critica</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="space-y-1">
                          <Label className="text-[11px]">Acao ao Rejeitar</Label>
                          <Select
                            value={rule.action_on_reject}
                            onValueChange={(v) => updateRule(idx, { action_on_reject: v })}
                          >
                            <SelectTrigger className="h-8 text-sm">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="redline">Redline</SelectItem>
                              <SelectItem value="flag">Sinalizar</SelectItem>
                              <SelectItem value="block">Bloquear</SelectItem>
                              <SelectItem value="suggest">Sugerir alteracao</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </div>

                      <div className="space-y-1">
                        <Label className="text-[11px]">Notas de Orientacao</Label>
                        <Textarea
                          value={rule.guidance_notes || ''}
                          onChange={(e) =>
                            updateRule(idx, { guidance_notes: e.target.value || null })
                          }
                          rows={2}
                          className="text-sm"
                          placeholder="Notas para o revisor..."
                        />
                      </div>

                      <div className="flex justify-end">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setEditingIdx(null)}
                          className="text-xs"
                        >
                          Fechar edicao
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {extractedRules.length === 0 && (
                <div className="text-center py-8">
                  <p className="text-sm text-slate-400">
                    Nenhuma regra restante. Volte ao passo anterior para tentar novamente.
                  </p>
                </div>
              )}
            </div>

            <div className="flex justify-between pt-2">
              <Button
                variant="outline"
                onClick={() => {
                  setStep('upload');
                  setExtractedRules([]);
                  setEditingIdx(null);
                }}
                className="gap-1"
              >
                <ChevronLeft className="h-4 w-4" />
                Voltar
              </Button>
              <Button
                onClick={handleConfirm}
                disabled={extractedRules.length === 0 || !name.trim() || confirmMutation.isPending}
                className="bg-emerald-600 hover:bg-emerald-500 text-white gap-2"
              >
                {confirmMutation.isPending ? (
                  <>
                    <Sparkles className="h-4 w-4 animate-spin" />
                    Criando...
                  </>
                ) : (
                  <>
                    <Check className="h-4 w-4" />
                    Criar Playbook ({extractedRules.length} regras)
                  </>
                )}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
