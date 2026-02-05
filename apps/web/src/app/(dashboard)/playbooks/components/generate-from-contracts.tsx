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
  type PlaybookRule,
  AREA_LABELS,
  SEVERITY_LABELS,
  SEVERITY_COLORS,
  REJECT_ACTION_LABELS,
  useGeneratePlaybook,
  usePlaybook,
} from '../hooks';

interface GenerateFromContractsProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onComplete: (playbookId: string) => void;
}

type Step = 'upload' | 'config' | 'processing' | 'review';

interface UploadedFile {
  id: string;
  name: string;
  size: number;
  file: File;
}

export function GenerateFromContracts({
  open,
  onOpenChange,
  onComplete,
}: GenerateFromContractsProps) {
  const [step, setStep] = useState<Step>('upload');
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [area, setArea] = useState<PlaybookArea>('outro');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [progress, setProgress] = useState(0);
  const [generatedPlaybookId, setGeneratedPlaybookId] = useState<string | null>(null);
  const [generatedRules, setGeneratedRules] = useState<
    Omit<PlaybookRule, 'id' | 'playbook_id' | 'created_at' | 'updated_at'>[]
  >([]);
  const [editingRules, setEditingRules] = useState<
    Omit<PlaybookRule, 'id' | 'playbook_id' | 'created_at' | 'updated_at'>[]
  >([]);

  const generateMutation = useGeneratePlaybook();
  // Fetch generated playbook details for review
  const { data: generatedPlaybook } = usePlaybook(generatedPlaybookId ?? undefined);

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selected = e.target.files;
      if (!selected) return;

      const newFiles: UploadedFile[] = [];
      const maxFiles = 10 - files.length;

      for (let i = 0; i < Math.min(selected.length, maxFiles); i++) {
        newFiles.push({
          id: `file-${Date.now()}-${i}`,
          name: selected[i].name,
          size: selected[i].size,
          file: selected[i],
        });
      }

      setFiles((prev) => [...prev, ...newFiles]);
      e.target.value = '';
    },
    [files.length]
  );

  const removeFile = (id: string) => {
    setFiles(files.filter((f) => f.id !== id));
  };

  const handleGenerate = async () => {
    setStep('processing');
    setProgress(0);

    // Simulate progress while the backend processes
    const progressInterval = setInterval(() => {
      setProgress((prev) => Math.min(prev + Math.random() * 15, 90));
    }, 500);

    try {
      // Backend creates the playbook and rules in one call
      const result = await generateMutation.mutateAsync({
        documentIds: files.map((f) => f.id),
        area,
        name: name || `Playbook gerado - ${AREA_LABELS[area]}`,
        description: description || `Playbook gerado automaticamente a partir de ${files.length} contrato(s).`,
      });

      clearInterval(progressInterval);
      setProgress(100);

      // Store the generated playbook ID so we can fetch its rules for review
      setGeneratedPlaybookId(result.playbook_id);

      setTimeout(() => {
        setStep('review');
      }, 500);
    } catch {
      clearInterval(progressInterval);
      setStep('config');
    }
  };

  // When generatedPlaybook loads, populate the rules for review
  const reviewRules: Omit<PlaybookRule, 'id' | 'playbook_id' | 'created_at' | 'updated_at'>[] =
    generatedPlaybook?.rules?.map((r) => ({
      name: r.name,
      clause_type: r.clause_type,
      severity: r.severity,
      preferred_position: r.preferred_position,
      fallback_positions: r.fallback_positions,
      rejected_positions: r.rejected_positions,
      reject_action: r.reject_action,
      guidance_notes: r.guidance_notes,
      is_active: r.is_active,
      order: r.order,
    })) ?? editingRules;

  const handleSave = async () => {
    // The backend already created the playbook; just navigate to it
    if (generatedPlaybookId) {
      onComplete(generatedPlaybookId);
      handleClose();
    }
  };

  const handleClose = () => {
    setStep('upload');
    setFiles([]);
    setArea('outro');
    setName('');
    setDescription('');
    setProgress(0);
    setGeneratedRules([]);
    setEditingRules([]);
    setGeneratedPlaybookId(null);
    onOpenChange(false);
  };

  const toggleRuleActive = (idx: number) => {
    const copy = [...editingRules];
    copy[idx] = { ...copy[idx], is_active: !copy[idx].is_active };
    setEditingRules(copy);
  };

  const removeRule = (idx: number) => {
    setEditingRules(editingRules.filter((_, i) => i !== idx));
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const stepIndicators = [
    { key: 'upload', label: '1. Upload' },
    { key: 'config', label: '2. Configurar' },
    { key: 'processing', label: '3. Processando' },
    { key: 'review', label: '4. Revisar' },
  ];

  const currentStepIdx = stepIndicators.findIndex((s) => s.key === step);

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-indigo-500" />
            Gerar Playbook a partir de Contratos
          </DialogTitle>
          <DialogDescription>
            Envie contratos existentes e a IA identificara padroes e gerara regras automaticamente.
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
                    ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300'
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

        {/* Step 1: Upload */}
        {step === 'upload' && (
          <div className="space-y-4 py-2">
            <div className="border-2 border-dashed border-slate-200 dark:border-slate-700 rounded-xl p-8 text-center hover:border-indigo-300 dark:hover:border-indigo-700 transition-colors">
              <Upload className="h-8 w-8 text-slate-400 mx-auto mb-3" />
              <p className="text-sm text-slate-600 dark:text-slate-300 mb-1">
                Arraste contratos aqui ou clique para selecionar
              </p>
              <p className="text-xs text-slate-400 mb-3">
                PDF, DOCX ou TXT - Maximo 10 arquivos
              </p>
              <label>
                <input
                  type="file"
                  multiple
                  accept=".pdf,.docx,.doc,.txt"
                  onChange={handleFileSelect}
                  className="hidden"
                />
                <Button variant="outline" className="gap-2" asChild>
                  <span>
                    <Upload className="h-4 w-4" />
                    Selecionar Arquivos
                  </span>
                </Button>
              </label>
            </div>

            {/* File list */}
            {files.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-slate-500">
                  {files.length} arquivo(s) selecionado(s)
                </p>
                {files.map((file) => (
                  <div
                    key={file.id}
                    className="flex items-center gap-3 p-2 rounded-lg bg-slate-50 dark:bg-slate-800"
                  >
                    <FileText className="h-4 w-4 text-slate-400 shrink-0" />
                    <span className="text-sm text-slate-700 dark:text-slate-300 flex-1 truncate">
                      {file.name}
                    </span>
                    <span className="text-[10px] text-slate-400 shrink-0">
                      {formatFileSize(file.size)}
                    </span>
                    <button
                      onClick={() => removeFile(file.id)}
                      className="text-slate-400 hover:text-red-500 transition-colors shrink-0"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="flex justify-end">
              <Button
                onClick={() => setStep('config')}
                disabled={files.length === 0}
                className="bg-indigo-600 hover:bg-indigo-500 text-white gap-1"
              >
                Proximo
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}

        {/* Step 2: Config */}
        {step === 'config' && (
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label>Nome do Playbook</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Ex: Revisao de Contratos de Locacao"
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

            <div className="rounded-lg bg-blue-50 dark:bg-blue-900/10 border border-blue-200 dark:border-blue-800 p-3 flex items-start gap-2">
              <AlertCircle className="h-4 w-4 text-blue-500 shrink-0 mt-0.5" />
              <p className="text-xs text-blue-700 dark:text-blue-300">
                A IA analisara os {files.length} contrato(s) para identificar clausulas comuns, padroes
                de negociacao e gerar regras de revisao automaticamente. O processo pode levar alguns minutos.
              </p>
            </div>

            <div className="flex justify-between">
              <Button variant="outline" onClick={() => setStep('upload')} className="gap-1">
                <ChevronLeft className="h-4 w-4" />
                Voltar
              </Button>
              <Button
                onClick={handleGenerate}
                className="bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white gap-2"
              >
                <Sparkles className="h-4 w-4" />
                Gerar Regras com IA
              </Button>
            </div>
          </div>
        )}

        {/* Step 3: Processing */}
        {step === 'processing' && (
          <div className="py-12 text-center space-y-6">
            <div className="relative mx-auto h-16 w-16">
              <div className="absolute inset-0 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 animate-spin [animation-duration:3s] opacity-30" />
              <div className="absolute inset-[3px] rounded-full bg-background" />
              <div className="absolute inset-0 flex items-center justify-center">
                <Sparkles className="h-6 w-6 text-indigo-500 animate-pulse" />
              </div>
            </div>
            <div>
              <p className="text-lg font-semibold text-slate-800 dark:text-slate-200">
                Analisando contratos...
              </p>
              <p className="text-sm text-slate-500 mt-1">
                A IA esta identificando clausulas e gerando regras de revisao
              </p>
            </div>
            <div className="max-w-xs mx-auto space-y-2">
              <Progress value={progress} className="h-2" />
              <p className="text-xs text-slate-400">{Math.round(progress)}% concluido</p>
            </div>
            <div className="space-y-1 text-xs text-slate-400">
              {progress < 30 && <p>Extraindo texto dos documentos...</p>}
              {progress >= 30 && progress < 60 && <p>Identificando clausulas e padroes...</p>}
              {progress >= 60 && progress < 90 && <p>Gerando regras de revisao...</p>}
              {progress >= 90 && <p>Finalizando...</p>}
            </div>
          </div>
        )}

        {/* Step 4: Review */}
        {step === 'review' && (
          <div className="space-y-4 py-2">
            <div className="rounded-lg bg-green-50 dark:bg-green-900/10 border border-green-200 dark:border-green-800 p-3 flex items-center gap-2">
              <Check className="h-4 w-4 text-green-600 shrink-0" />
              <p className="text-sm text-green-700 dark:text-green-300">
                {reviewRules.length} regra(s) gerada(s) com sucesso. Revise antes de confirmar.
              </p>
            </div>

            <div className="space-y-3 max-h-[50vh] overflow-y-auto pr-1">
              {reviewRules.map((rule, idx) => (
                <div
                  key={idx}
                  className={cn(
                    'rounded-lg border p-4 space-y-2 transition-opacity',
                    rule.is_active
                      ? 'border-slate-200 dark:border-slate-700'
                      : 'border-slate-100 dark:border-slate-800 opacity-50'
                  )}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <h4 className="font-medium text-sm text-slate-800 dark:text-slate-200">
                        {rule.name}
                      </h4>
                      <Badge variant="outline" className="text-[10px]">
                        {rule.clause_type}
                      </Badge>
                      <Badge className={cn('text-[10px] border-0', SEVERITY_COLORS[rule.severity])}>
                        {SEVERITY_LABELS[rule.severity]}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => toggleRuleActive(idx)}
                        className={cn(
                          'text-xs px-2 py-0.5 rounded',
                          rule.is_active
                            ? 'text-green-600 bg-green-50 dark:bg-green-900/20'
                            : 'text-slate-400 bg-slate-100 dark:bg-slate-800'
                        )}
                      >
                        {rule.is_active ? 'Ativa' : 'Inativa'}
                      </button>
                      <button
                        onClick={() => removeRule(idx)}
                        className="text-slate-400 hover:text-red-500 transition-colors"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>

                  <div className="text-xs space-y-1">
                    <p className="text-green-700 dark:text-green-400">
                      <span className="font-semibold">Preferida:</span> {rule.preferred_position}
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
                      {REJECT_ACTION_LABELS[rule.reject_action]}
                    </p>
                  </div>
                </div>
              ))}
            </div>

            <div className="flex justify-between pt-2">
              <Button variant="outline" onClick={() => setStep('config')} className="gap-1">
                <ChevronLeft className="h-4 w-4" />
                Voltar
              </Button>
              <Button
                onClick={handleSave}
                disabled={reviewRules.length === 0}
                className="bg-indigo-600 hover:bg-indigo-500 text-white gap-2"
              >
                <Check className="h-4 w-4" />
                Abrir Playbook ({reviewRules.length} regras)
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
