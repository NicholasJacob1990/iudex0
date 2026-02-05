'use client';

import { useState, useEffect } from 'react';
import { Plus, Minus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog';
import {
  type PlaybookRule,
  type RuleSeverity,
  type RejectAction,
  SEVERITY_LABELS,
  REJECT_ACTION_LABELS,
} from '../hooks';

interface PlaybookRuleFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  playbookId: string;
  initialData?: PlaybookRule;
  onSubmit: (data: Omit<PlaybookRule, 'id' | 'created_at' | 'updated_at'>) => void;
}

const CLAUSE_TYPES = [
  'SLA',
  'PI',
  'LGPD',
  'NDA',
  'Vigencia',
  'Rescisao',
  'Responsabilidade',
  'Penalidades',
  'Garantia',
  'Foro',
  'Pagamento',
  'Reajuste',
  'Subcontratacao',
  'Forca Maior',
  'Outro',
];

export function PlaybookRuleForm({
  open,
  onOpenChange,
  playbookId,
  initialData,
  onSubmit,
}: PlaybookRuleFormProps) {
  const [name, setName] = useState(initialData?.name || '');
  const [clauseType, setClauseType] = useState(initialData?.clause_type || '');
  const [severity, setSeverity] = useState<RuleSeverity>(initialData?.severity || 'media');
  const [preferredPosition, setPreferredPosition] = useState(initialData?.preferred_position || '');
  const [fallbackPositions, setFallbackPositions] = useState<string[]>(
    initialData?.fallback_positions || ['']
  );
  const [rejectedPositions, setRejectedPositions] = useState<string[]>(
    initialData?.rejected_positions || ['']
  );
  const [rejectAction, setRejectAction] = useState<RejectAction>(initialData?.reject_action || 'suggest');
  const [guidanceNotes, setGuidanceNotes] = useState(initialData?.guidance_notes || '');
  const [isActive, setIsActive] = useState(initialData?.is_active ?? true);

  const resetForm = () => {
    setName('');
    setClauseType('');
    setSeverity('media');
    setPreferredPosition('');
    setFallbackPositions(['']);
    setRejectedPositions(['']);
    setRejectAction('suggest');
    setGuidanceNotes('');
    setIsActive(true);
  };

  // Re-initialize form when initialData changes (reuse for editing different rules)
  useEffect(() => {
    if (initialData) {
      setName(initialData.name || '');
      setClauseType(initialData.clause_type || '');
      setSeverity(initialData.severity || 'media');
      setPreferredPosition(initialData.preferred_position || '');
      setFallbackPositions(initialData.fallback_positions?.length ? initialData.fallback_positions : ['']);
      setRejectedPositions(initialData.rejected_positions?.length ? initialData.rejected_positions : ['']);
      setRejectAction(initialData.reject_action || 'suggest');
      setGuidanceNotes(initialData.guidance_notes || '');
      setIsActive(initialData.is_active ?? true);
    } else {
      resetForm();
    }
  }, [initialData]);

  const handleSubmit = () => {
    if (!name.trim() || !clauseType || !preferredPosition.trim()) return;

    onSubmit({
      playbook_id: playbookId,
      name: name.trim(),
      clause_type: clauseType,
      severity,
      preferred_position: preferredPosition.trim(),
      fallback_positions: fallbackPositions.filter((p) => p.trim()),
      rejected_positions: rejectedPositions.filter((p) => p.trim()),
      reject_action: rejectAction,
      guidance_notes: guidanceNotes.trim(),
      is_active: isActive,
      order: initialData?.order ?? 999,
    });

    onOpenChange(false);
    resetForm();
  };

  const addFallback = () => setFallbackPositions([...fallbackPositions, '']);
  const removeFallback = (idx: number) =>
    setFallbackPositions(fallbackPositions.filter((_, i) => i !== idx));
  const updateFallback = (idx: number, value: string) => {
    const copy = [...fallbackPositions];
    copy[idx] = value;
    setFallbackPositions(copy);
  };

  const addRejected = () => setRejectedPositions([...rejectedPositions, '']);
  const removeRejected = (idx: number) =>
    setRejectedPositions(rejectedPositions.filter((_, i) => i !== idx));
  const updateRejected = (idx: number, value: string) => {
    const copy = [...rejectedPositions];
    copy[idx] = value;
    setRejectedPositions(copy);
  };

  const isValid = name.trim() && clauseType && preferredPosition.trim();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{initialData ? 'Editar Regra' : 'Nova Regra'}</DialogTitle>
          <DialogDescription>
            Defina as posicoes preferidas, alternativas e rejeitadas para esta clausula.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-2">
          {/* Name + Clause Type */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Nome da Regra *</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Ex: Clausula de SLA"
              />
            </div>
            <div className="space-y-2">
              <Label>Tipo de Clausula *</Label>
              <Select value={clauseType} onValueChange={setClauseType}>
                <SelectTrigger>
                  <SelectValue placeholder="Selecione..." />
                </SelectTrigger>
                <SelectContent>
                  {CLAUSE_TYPES.map((type) => (
                    <SelectItem key={type} value={type}>
                      {type}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Severity + Action */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Severidade</Label>
              <Select value={severity} onValueChange={(v) => setSeverity(v as RuleSeverity)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.entries(SEVERITY_LABELS) as [RuleSeverity, string][]).map(([key, label]) => (
                    <SelectItem key={key} value={key}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Acao ao Rejeitar</Label>
              <Select value={rejectAction} onValueChange={(v) => setRejectAction(v as RejectAction)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.entries(REJECT_ACTION_LABELS) as [RejectAction, string][]).map(([key, label]) => (
                    <SelectItem key={key} value={key}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Preferred Position */}
          <div className="space-y-2">
            <Label>Posicao Preferida *</Label>
            <Textarea
              value={preferredPosition}
              onChange={(e) => setPreferredPosition(e.target.value)}
              placeholder="Descreva a posicao ideal para esta clausula..."
              rows={3}
            />
          </div>

          {/* Fallback Positions */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Posicoes Alternativas</Label>
              <Button variant="ghost" size="sm" onClick={addFallback} className="gap-1 h-7 text-xs">
                <Plus className="h-3 w-3" />
                Adicionar
              </Button>
            </div>
            <div className="space-y-2">
              {fallbackPositions.map((pos, idx) => (
                <div key={idx} className="flex gap-2">
                  <Textarea
                    value={pos}
                    onChange={(e) => updateFallback(idx, e.target.value)}
                    placeholder={`Alternativa ${idx + 1}...`}
                    rows={2}
                    className="flex-1"
                  />
                  {fallbackPositions.length > 1 && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 shrink-0 text-slate-400 hover:text-red-500"
                      onClick={() => removeFallback(idx)}
                    >
                      <Minus className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Rejected Positions */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Posicoes Rejeitadas</Label>
              <Button variant="ghost" size="sm" onClick={addRejected} className="gap-1 h-7 text-xs">
                <Plus className="h-3 w-3" />
                Adicionar
              </Button>
            </div>
            <div className="space-y-2">
              {rejectedPositions.map((pos, idx) => (
                <div key={idx} className="flex gap-2">
                  <Textarea
                    value={pos}
                    onChange={(e) => updateRejected(idx, e.target.value)}
                    placeholder={`Posicao rejeitada ${idx + 1}...`}
                    rows={2}
                    className="flex-1"
                  />
                  {rejectedPositions.length > 1 && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 shrink-0 text-slate-400 hover:text-red-500"
                      onClick={() => removeRejected(idx)}
                    >
                      <Minus className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Guidance Notes */}
          <div className="space-y-2">
            <Label>Notas de Orientacao</Label>
            <Textarea
              value={guidanceNotes}
              onChange={(e) => setGuidanceNotes(e.target.value)}
              placeholder="Orientacoes adicionais para o revisor..."
              rows={2}
            />
          </div>

          {/* Active toggle */}
          <div className="flex items-center gap-3">
            <Switch checked={isActive} onCheckedChange={setIsActive} />
            <Label className="cursor-pointer">Regra ativa</Label>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!isValid}
            className="bg-indigo-600 hover:bg-indigo-500 text-white"
          >
            {initialData ? 'Salvar Alteracoes' : 'Criar Regra'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
