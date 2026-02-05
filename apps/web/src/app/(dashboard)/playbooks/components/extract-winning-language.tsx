'use client';

import { useState, useCallback } from 'react';
import {
  FileText,
  X,
  ChevronRight,
  ChevronLeft,
  Check,
  Search,
  Trophy,
  Loader2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Checkbox } from '@/components/ui/checkbox';
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
  AREA_LABELS,
  SEVERITY_LABELS,
  SEVERITY_COLORS,
  useExtractWinningLanguage,
  usePlaybook,
} from '../hooks';
import { useCorpusDocuments } from '../../corpus/hooks/use-corpus';

interface ExtractWinningLanguageProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onComplete: (playbookId: string) => void;
}

type Step = 'select' | 'config' | 'processing' | 'review';

interface SelectedDocument {
  id: string;
  name: string;
}

export function ExtractWinningLanguage({
  open,
  onOpenChange,
  onComplete,
}: ExtractWinningLanguageProps) {
  const [step, setStep] = useState<Step>('select');
  const [selectedDocs, setSelectedDocs] = useState<SelectedDocument[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [area, setArea] = useState<PlaybookArea>('outro');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [progress, setProgress] = useState(0);
  const [generatedPlaybookId, setGeneratedPlaybookId] = useState<string | null>(null);

  const extractMutation = useExtractWinningLanguage();
  const { data: generatedPlaybook } = usePlaybook(generatedPlaybookId ?? undefined);

  // Fetch corpus documents for selection
  const { data: corpusData, isLoading: isLoadingDocs } = useCorpusDocuments({
    scope: 'private',
    per_page: 50,
  });

  const documents = corpusData?.items ?? [];

  // Filter documents by search
  const filteredDocuments = documents.filter((doc) => {
    if (!searchQuery.trim()) return true;
    const query = searchQuery.toLowerCase();
    return doc.name.toLowerCase().includes(query);
  });

  const toggleDocument = useCallback(
    (doc: { id: string; name: string }) => {
      setSelectedDocs((prev) => {
        const exists = prev.find((d) => d.id === doc.id);
        if (exists) {
          return prev.filter((d) => d.id !== doc.id);
        }
        if (prev.length >= 10) return prev; // Max 10
        return [...prev, { id: doc.id, name: doc.name }];
      });
    },
    []
  );

  const removeDoc = (id: string) => {
    setSelectedDocs((prev) => prev.filter((d) => d.id !== id));
  };

  const handleExtract = async () => {
    setStep('processing');
    setProgress(0);

    const progressInterval = setInterval(() => {
      setProgress((prev) => Math.min(prev + Math.random() * 12, 90));
    }, 600);

    try {
      const result = await extractMutation.mutateAsync({
        documentIds: selectedDocs.map((d) => d.id),
        area,
        name: name || `Winning Language - ${AREA_LABELS[area]}`,
        description:
          description ||
          `Linguagem vencedora extraida de ${selectedDocs.length} contrato(s) na area de ${AREA_LABELS[area]}.`,
      });

      clearInterval(progressInterval);
      setProgress(100);

      setGeneratedPlaybookId(result.playbook_id);

      setTimeout(() => {
        setStep('review');
      }, 500);
    } catch {
      clearInterval(progressInterval);
      setStep('config');
    }
  };

  const handleSave = () => {
    if (generatedPlaybookId) {
      onComplete(generatedPlaybookId);
      handleClose();
    }
  };

  const handleClose = () => {
    setStep('select');
    setSelectedDocs([]);
    setSearchQuery('');
    setArea('outro');
    setName('');
    setDescription('');
    setProgress(0);
    setGeneratedPlaybookId(null);
    onOpenChange(false);
  };

  // Map generated playbook rules for review display
  const reviewRules = generatedPlaybook?.rules ?? [];

  const stepIndicators = [
    { key: 'select', label: '1. Selecionar' },
    { key: 'config', label: '2. Configurar' },
    { key: 'processing', label: '3. Extraindo' },
    { key: 'review', label: '4. Revisar' },
  ];

  const currentStepIdx = stepIndicators.findIndex((s) => s.key === step);

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Trophy className="h-5 w-5 text-amber-500" />
            Extrair Winning Language
          </DialogTitle>
          <DialogDescription>
            Selecione contratos ja negociados e assinados. A IA extraira a linguagem
            vencedora — clausulas aceitas por ambas as partes — para criar um playbook.
          </DialogDescription>
        </DialogHeader>

        {/* Step indicators */}
        <div className="flex items-center gap-2 py-2">
          {stepIndicators.map((s, idx) => (
            <div key={s.key} className="flex items-center gap-2">
              {idx > 0 && (
                <div className="h-px w-4 bg-slate-200 dark:bg-slate-700" />
              )}
              <span
                className={cn(
                  'text-xs font-medium px-2 py-1 rounded-full transition-colors',
                  idx === currentStepIdx
                    ? 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300'
                    : idx < currentStepIdx
                      ? 'bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-300'
                      : 'text-slate-400'
                )}
              >
                {idx < currentStepIdx && (
                  <Check className="h-3 w-3 inline mr-1" />
                )}
                {s.label}
              </span>
            </div>
          ))}
        </div>

        {/* Step 1: Select documents */}
        {step === 'select' && (
          <div className="space-y-4 py-2">
            <div className="rounded-lg bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-800 p-3 flex items-start gap-2">
              <Trophy className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
              <div className="text-xs text-amber-700 dark:text-amber-300">
                <p className="font-semibold mb-1">
                  O que e Winning Language?
                </p>
                <p>
                  Selecione contratos que ja foram negociados e assinados com sucesso.
                  A IA analisara as clausulas aceitas para identificar padroes e criar
                  regras baseadas na linguagem que realmente funcionou nas negociacoes.
                </p>
              </div>
            </div>

            {/* Search */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Buscar documentos no corpus..."
                className="pl-9"
              />
            </div>

            {/* Document list */}
            <div className="max-h-[300px] overflow-y-auto space-y-1 border rounded-lg p-2">
              {isLoadingDocs ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-5 w-5 text-slate-400 animate-spin" />
                  <span className="text-sm text-slate-400 ml-2">
                    Carregando documentos...
                  </span>
                </div>
              ) : filteredDocuments.length === 0 ? (
                <div className="text-center py-8">
                  <FileText className="h-8 w-8 text-slate-300 mx-auto mb-2" />
                  <p className="text-sm text-slate-400">
                    {searchQuery
                      ? 'Nenhum documento encontrado para esta busca'
                      : 'Nenhum documento disponivel no corpus'}
                  </p>
                </div>
              ) : (
                filteredDocuments.map((doc) => {
                  const isSelected = selectedDocs.some((d) => d.id === doc.id);
                  return (
                    <button
                      key={doc.id}
                      onClick={() => toggleDocument(doc)}
                      className={cn(
                        'w-full flex items-center gap-3 p-2.5 rounded-lg text-left transition-all',
                        isSelected
                          ? 'bg-amber-50 border border-amber-200 dark:bg-amber-500/10 dark:border-amber-700'
                          : 'hover:bg-slate-50 dark:hover:bg-slate-800 border border-transparent'
                      )}
                    >
                      <Checkbox
                        checked={isSelected}
                        className="shrink-0"
                      />
                      <FileText className="h-4 w-4 text-slate-400 shrink-0" />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-slate-700 dark:text-slate-300 truncate">
                          {doc.name}
                        </p>
                        <p className="text-[10px] text-slate-400">
                          {doc.file_type?.toUpperCase() ?? 'DOC'}
                          {doc.size_bytes
                            ? ` - ${(doc.size_bytes / 1024).toFixed(0)} KB`
                            : ''}
                        </p>
                      </div>
                    </button>
                  );
                })
              )}
            </div>

            {/* Selected count */}
            {selectedDocs.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-slate-500">
                  {selectedDocs.length} contrato(s) selecionado(s){' '}
                  <span className="text-slate-400">(max. 10)</span>
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {selectedDocs.map((doc) => (
                    <Badge
                      key={doc.id}
                      variant="secondary"
                      className="gap-1 text-[11px] pr-1"
                    >
                      {doc.name.length > 30
                        ? doc.name.slice(0, 30) + '...'
                        : doc.name}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          removeDoc(doc.id);
                        }}
                        className="ml-0.5 hover:text-red-500 transition-colors"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            <div className="flex justify-end">
              <Button
                onClick={() => setStep('config')}
                disabled={selectedDocs.length === 0}
                className="bg-amber-600 hover:bg-amber-500 text-white gap-1"
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
                placeholder="Ex: Winning Language - Contratos SaaS"
              />
            </div>
            <div className="space-y-2">
              <Label>Descricao</Label>
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Descricao opcional do playbook..."
                rows={2}
              />
            </div>
            <div className="space-y-2">
              <Label>Area Juridica *</Label>
              <Select
                value={area}
                onValueChange={(v) => setArea(v as PlaybookArea)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(
                    Object.entries(AREA_LABELS) as [PlaybookArea, string][]
                  ).map(([key, label]) => (
                    <SelectItem key={key} value={key}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="rounded-lg bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-800 p-3 flex items-start gap-2">
              <Trophy className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
              <p className="text-xs text-amber-700 dark:text-amber-300">
                A IA analisara os {selectedDocs.length} contrato(s) como{' '}
                <strong>linguagem vencedora</strong> — clausulas que ja foram
                aceitas em negociacoes reais. O processo extrai posicoes padrao,
                variacoes aceitaveis e termos a evitar. Pode levar alguns minutos.
              </p>
            </div>

            <div className="flex justify-between">
              <Button
                variant="outline"
                onClick={() => setStep('select')}
                className="gap-1"
              >
                <ChevronLeft className="h-4 w-4" />
                Voltar
              </Button>
              <Button
                onClick={handleExtract}
                className="bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white gap-2"
              >
                <Trophy className="h-4 w-4" />
                Extrair Winning Language
              </Button>
            </div>
          </div>
        )}

        {/* Step 3: Processing */}
        {step === 'processing' && (
          <div className="py-12 text-center space-y-6">
            <div className="relative mx-auto h-16 w-16">
              <div className="absolute inset-0 rounded-full bg-gradient-to-br from-amber-500 to-orange-600 animate-spin [animation-duration:3s] opacity-30" />
              <div className="absolute inset-[3px] rounded-full bg-background" />
              <div className="absolute inset-0 flex items-center justify-center">
                <Trophy className="h-6 w-6 text-amber-500 animate-pulse" />
              </div>
            </div>
            <div>
              <p className="text-lg font-semibold text-slate-800 dark:text-slate-200">
                Extraindo winning language...
              </p>
              <p className="text-sm text-slate-500 mt-1">
                Analisando clausulas aceitas em {selectedDocs.length} contrato(s)
              </p>
            </div>
            <div className="max-w-xs mx-auto space-y-2">
              <Progress value={progress} className="h-2" />
              <p className="text-xs text-slate-400">
                {Math.round(progress)}% concluido
              </p>
            </div>
            <div className="space-y-1 text-xs text-slate-400">
              {progress < 25 && <p>Carregando textos dos contratos...</p>}
              {progress >= 25 && progress < 50 && (
                <p>Identificando clausulas recorrentes...</p>
              )}
              {progress >= 50 && progress < 75 && (
                <p>Extraindo linguagem vencedora...</p>
              )}
              {progress >= 75 && progress < 90 && (
                <p>Gerando posicoes e regras...</p>
              )}
              {progress >= 90 && <p>Finalizando playbook...</p>}
            </div>
          </div>
        )}

        {/* Step 4: Review */}
        {step === 'review' && (
          <div className="space-y-4 py-2">
            <div className="rounded-lg bg-green-50 dark:bg-green-900/10 border border-green-200 dark:border-green-800 p-3 flex items-center gap-2">
              <Check className="h-4 w-4 text-green-600 shrink-0" />
              <p className="text-sm text-green-700 dark:text-green-300">
                {reviewRules.length} regra(s) de winning language extraida(s).
                Revise e abra o playbook para ajustes finos.
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
                      <Badge
                        className={cn(
                          'text-[10px] border-0',
                          SEVERITY_COLORS[rule.severity]
                        )}
                      >
                        {SEVERITY_LABELS[rule.severity]}
                      </Badge>
                    </div>
                  </div>

                  <div className="text-xs space-y-1">
                    <p className="text-green-700 dark:text-green-400">
                      <span className="font-semibold">Linguagem Vencedora:</span>{' '}
                      {rule.preferred_position}
                    </p>
                    {rule.fallback_positions.length > 0 && (
                      <p className="text-yellow-700 dark:text-yellow-400">
                        <span className="font-semibold">Variacoes Aceitas:</span>{' '}
                        {rule.fallback_positions.join(' | ')}
                      </p>
                    )}
                    {rule.rejected_positions.length > 0 && (
                      <p className="text-red-700 dark:text-red-400">
                        <span className="font-semibold">Posicoes a Evitar:</span>{' '}
                        {rule.rejected_positions.join(' | ')}
                      </p>
                    )}
                    {rule.guidance_notes && (
                      <p className="text-slate-500 italic">
                        <span className="font-semibold not-italic">Notas:</span>{' '}
                        {rule.guidance_notes}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <div className="flex justify-between pt-2">
              <Button
                variant="outline"
                onClick={() => setStep('config')}
                className="gap-1"
              >
                <ChevronLeft className="h-4 w-4" />
                Voltar
              </Button>
              <Button
                onClick={handleSave}
                disabled={reviewRules.length === 0}
                className="bg-amber-600 hover:bg-amber-500 text-white gap-2"
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
