'use client';

import { useState } from 'react';
import { FileText, Sparkles, LayoutTemplate, Upload, Trophy } from 'lucide-react';
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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog';
import { type PlaybookArea, type PartyPerspective, AREA_LABELS, PARTY_PERSPECTIVE_LABELS } from '../hooks';

type CreateMode = 'scratch' | 'template' | 'contracts';

interface CreatePlaybookDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreateFromScratch: (data: { name: string; description: string; area: PlaybookArea; scope: string; party_perspective?: PartyPerspective }) => void;
  onCreateFromTemplate: (templateId: string, data: { name: string; area: PlaybookArea }) => void;
  onCreateFromContracts: () => void;
  onImportFromDocument?: () => void;
  onExtractWinningLanguage?: () => void;
}

const TEMPLATES = [
  {
    id: 'tpl-1',
    name: 'Contratos de TI - Padrao',
    description: 'Modelo completo para revisao de contratos de tecnologia.',
    area: 'ti' as PlaybookArea,
    ruleCount: 15,
  },
  {
    id: 'tpl-2',
    name: 'Due Diligence M&A',
    description: 'Checklist de clausulas para processos de fusao e aquisicao.',
    area: 'ma' as PlaybookArea,
    ruleCount: 24,
  },
  {
    id: 'tpl-3',
    name: 'Contrato de Trabalho - CLT',
    description: 'Modelo para revisao de contratos trabalhistas CLT.',
    area: 'trabalhista' as PlaybookArea,
    ruleCount: 18,
  },
  {
    id: 'tpl-4',
    name: 'Contrato de Locacao Comercial',
    description: 'Revisao de contratos de locacao com foco em clausulas comerciais.',
    area: 'imobiliario' as PlaybookArea,
    ruleCount: 12,
  },
];

export function CreatePlaybookDialog({
  open,
  onOpenChange,
  onCreateFromScratch,
  onCreateFromTemplate,
  onCreateFromContracts,
  onImportFromDocument,
  onExtractWinningLanguage,
}: CreatePlaybookDialogProps) {
  const [mode, setMode] = useState<CreateMode | null>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [area, setArea] = useState<PlaybookArea>('outro');
  const [scope, setScope] = useState('');
  const [partyPerspective, setPartyPerspective] = useState<PartyPerspective>('neutro');
  const [selectedTemplate, setSelectedTemplate] = useState<string>('');

  const resetForm = () => {
    setMode(null);
    setName('');
    setDescription('');
    setArea('outro');
    setScope('');
    setPartyPerspective('neutro');
    setSelectedTemplate('');
  };

  const handleClose = (open: boolean) => {
    if (!open) resetForm();
    onOpenChange(open);
  };

  const handleSubmitScratch = () => {
    if (!name.trim()) return;
    onCreateFromScratch({ name: name.trim(), description: description.trim(), area, scope: scope.trim(), party_perspective: partyPerspective });
    handleClose(false);
  };

  const handleSubmitTemplate = () => {
    if (!selectedTemplate || !name.trim()) return;
    onCreateFromTemplate(selectedTemplate, { name: name.trim(), area });
    handleClose(false);
  };

  const handleFromContracts = () => {
    handleClose(false);
    onCreateFromContracts();
  };

  const handleExtractWinningLanguage = () => {
    handleClose(false);
    onExtractWinningLanguage?.();
  };

  const handleImportFromDocument = () => {
    if (!onImportFromDocument) return;
    handleClose(false);
    onImportFromDocument();
  };

  // Step 1: Choose mode
  if (!mode) {
    return (
      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Criar Playbook</DialogTitle>
            <DialogDescription>
              Escolha como deseja criar seu novo playbook de revisao.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-3 py-4">
            <button
              onClick={() => setMode('scratch')}
              className="flex items-center gap-4 p-4 rounded-xl border border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-700 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-all text-left"
            >
              <div className="h-10 w-10 rounded-lg bg-indigo-100 dark:bg-indigo-500/20 flex items-center justify-center shrink-0">
                <FileText className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
              </div>
              <div>
                <h4 className="font-medium text-sm text-slate-800 dark:text-slate-200">
                  Do zero
                </h4>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  Comece com um playbook vazio e adicione regras manualmente.
                </p>
              </div>
            </button>

            <button
              onClick={() => setMode('template')}
              className="flex items-center gap-4 p-4 rounded-xl border border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-700 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-all text-left"
            >
              <div className="h-10 w-10 rounded-lg bg-purple-100 dark:bg-purple-500/20 flex items-center justify-center shrink-0">
                <LayoutTemplate className="h-5 w-5 text-purple-600 dark:text-purple-400" />
              </div>
              <div>
                <h4 className="font-medium text-sm text-slate-800 dark:text-slate-200">
                  A partir de template
                </h4>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  Use um modelo pre-definido como ponto de partida.
                </p>
              </div>
            </button>

            <button
              onClick={handleFromContracts}
              className="flex items-center gap-4 p-4 rounded-xl border border-indigo-200 dark:border-indigo-700 bg-indigo-50 dark:bg-indigo-500/10 hover:bg-indigo-100 dark:hover:bg-indigo-500/20 transition-all text-left"
            >
              <div className="h-10 w-10 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shrink-0">
                <Sparkles className="h-5 w-5 text-white" />
              </div>
              <div>
                <h4 className="font-medium text-sm text-slate-800 dark:text-slate-200">
                  A partir de contratos (IA)
                </h4>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  Envie 1 a 10 contratos e a IA gerara regras automaticamente.
                </p>
              </div>
            </button>

            {onExtractWinningLanguage && (
              <button
                onClick={handleExtractWinningLanguage}
                className="flex items-center gap-4 p-4 rounded-xl border border-amber-200 dark:border-amber-700 bg-amber-50 dark:bg-amber-500/10 hover:bg-amber-100 dark:hover:bg-amber-500/20 transition-all text-left"
              >
                <div className="h-10 w-10 rounded-lg bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center shrink-0">
                  <Trophy className="h-5 w-5 text-white" />
                </div>
                <div>
                  <h4 className="font-medium text-sm text-slate-800 dark:text-slate-200">
                    Extrair Winning Language
                  </h4>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    Extraia clausulas vencedoras de contratos ja negociados.
                  </p>
                </div>
              </button>
            )}

            {onImportFromDocument && (
              <button
                onClick={handleImportFromDocument}
                className="flex items-center gap-4 p-4 rounded-xl border border-emerald-200 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-500/10 hover:bg-emerald-100 dark:hover:bg-emerald-500/20 transition-all text-left"
              >
                <div className="h-10 w-10 rounded-lg bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shrink-0">
                  <Upload className="h-5 w-5 text-white" />
                </div>
                <div>
                  <h4 className="font-medium text-sm text-slate-800 dark:text-slate-200">
                    Importar de documento
                  </h4>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    Envie um PDF/DOCX de playbook e a IA extraira as regras.
                  </p>
                </div>
              </button>
            )}
          </div>
        </DialogContent>
      </Dialog>
    );
  }

  // Step 2: From scratch
  if (mode === 'scratch') {
    return (
      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Novo Playbook</DialogTitle>
            <DialogDescription>
              Preencha as informacoes basicas do playbook.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label>Nome *</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Ex: Revisao de Contratos de TI"
                autoFocus
              />
            </div>
            <div className="space-y-2">
              <Label>Descricao</Label>
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Descreva o objetivo deste playbook..."
                rows={3}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Area</Label>
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
              <div className="space-y-2">
                <Label>Escopo</Label>
                <Input
                  value={scope}
                  onChange={(e) => setScope(e.target.value)}
                  placeholder="Ex: Contratos SaaS"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Perspectiva da Parte</Label>
              <Select value={partyPerspective} onValueChange={(v) => setPartyPerspective(v as PartyPerspective)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.entries(PARTY_PERSPECTIVE_LABELS) as [PartyPerspective, string][]).map(([key, label]) => (
                    <SelectItem key={key} value={key}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                Define o ponto de vista da analise: contratante, contratado ou neutro.
              </p>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setMode(null)}>
              Voltar
            </Button>
            <Button
              onClick={handleSubmitScratch}
              disabled={!name.trim()}
              className="bg-indigo-600 hover:bg-indigo-500 text-white"
            >
              Criar Playbook
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  // Step 2: From template
  if (mode === 'template') {
    return (
      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Criar a partir de Template</DialogTitle>
            <DialogDescription>
              Selecione um template e personalize o nome.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label>Template</Label>
              <div className="grid gap-2">
                {TEMPLATES.map((tpl) => (
                  <button
                    key={tpl.id}
                    onClick={() => {
                      setSelectedTemplate(tpl.id);
                      if (!name) setName(tpl.name);
                      setArea(tpl.area);
                    }}
                    className={`flex items-center gap-3 p-3 rounded-lg border text-left transition-all ${
                      selectedTemplate === tpl.id
                        ? 'border-indigo-400 bg-indigo-50 dark:bg-indigo-500/10 dark:border-indigo-600'
                        : 'border-slate-200 dark:border-slate-700 hover:border-slate-300'
                    }`}
                  >
                    <LayoutTemplate className="h-4 w-4 text-slate-400 shrink-0" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-slate-700 dark:text-slate-200 truncate">
                        {tpl.name}
                      </p>
                      <p className="text-[11px] text-slate-500 dark:text-slate-400 truncate">
                        {tpl.description} ({tpl.ruleCount} regras)
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <Label>Nome do Playbook *</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Nome do seu playbook"
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setMode(null)}>
              Voltar
            </Button>
            <Button
              onClick={handleSubmitTemplate}
              disabled={!selectedTemplate || !name.trim()}
              className="bg-indigo-600 hover:bg-indigo-500 text-white"
            >
              Criar a partir do Template
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  return null;
}
