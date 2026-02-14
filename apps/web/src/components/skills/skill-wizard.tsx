'use client';

import { useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import JSZip from 'jszip';
import { ArrowLeft, Bot, ClipboardList, FileUp, Loader2, Sparkles, Upload } from 'lucide-react';
import type { GenerateSkillRequestPayload } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { toast } from 'sonner';

interface SkillWizardProps {
  isGenerating: boolean;
  onGenerate: (payload: GenerateSkillRequestPayload) => Promise<void>;
  onImportMarkdown: (markdown: string) => void;
}

type WizardStep = 'menu' | 'manual' | 'upload';

const SKILL_CREATOR_PREFILL =
  "Let's create a skill together using your skill-creator skill. First ask me what the skill should do.";

const SUPPORTED_UPLOAD_EXTENSIONS = ['.zip', '.skill', '.md'];

const isSupportedSkillFile = (fileName: string): boolean =>
  SUPPORTED_UPLOAD_EXTENSIONS.some((extension) => fileName.toLowerCase().endsWith(extension));

export function SkillWizard({ isGenerating, onGenerate, onImportMarkdown }: SkillWizardProps) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<WizardStep>('menu');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [instructions, setInstructions] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isImporting, setIsImporting] = useState(false);

  const handleCreateWithClaude = () => {
    if (typeof window !== 'undefined') {
      window.sessionStorage.setItem('iudex.skillCreator.prefill', SKILL_CREATOR_PREFILL);
    }
    setOpen(false);
    setStep('menu');
    router.push('/ask');
  };

  const handleCreateByInstructions = async () => {
    if (!instructions.trim()) {
      toast.error('Descreva o objetivo da skill antes de gerar.');
      return;
    }

    await onGenerate({
      directive: instructions.trim(),
      name: name.trim() || undefined,
      description: description.trim() || undefined,
      citation_style: 'abnt',
      output_format: 'document',
      audience: 'both',
    });
  };

  const extractMarkdownFromUpload = async (file: File): Promise<string> => {
    const lowerName = file.name.toLowerCase();

    if (lowerName.endsWith('.md') || lowerName.endsWith('.skill')) {
      return file.text();
    }

    if (lowerName.endsWith('.zip')) {
      const archive = await JSZip.loadAsync(file);
      const candidates = Object.values(archive.files)
        .filter((entry) => !entry.dir)
        .filter((entry) => entry.name.toLowerCase().endsWith('.md') || entry.name.toLowerCase().endsWith('.skill'))
        .sort((a, b) => a.name.localeCompare(b.name));

      if (!candidates.length) {
        throw new Error('ZIP sem arquivos .md/.skill para importacao.');
      }

      return candidates[0].async('string');
    }

    throw new Error('Formato nao suportado.');
  };

  const handleImport = async () => {
    if (!selectedFile) {
      toast.error('Selecione um arquivo antes de importar.');
      return;
    }

    setIsImporting(true);
    try {
      const markdown = (await extractMarkdownFromUpload(selectedFile)).trim();
      if (!markdown) {
        toast.error('Arquivo vazio. Selecione um arquivo valido.');
        return;
      }
      onImportMarkdown(markdown);
      setSelectedFile(null);
      setStep('menu');
      toast.success('Skill importada para o editor avancado.');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Falha ao importar skill.';
      toast.error(message);
    } finally {
      setIsImporting(false);
    }
  };

  const handleCloseDialog = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (!nextOpen) {
      setStep('menu');
      setSelectedFile(null);
      setIsImporting(false);
    }
  };

  const renderStepHeader = (title: string) => (
    <div className="flex items-center justify-between">
      <h3 className="text-2xl font-semibold tracking-tight text-foreground">{title}</h3>
      {step !== 'menu' ? (
        <Button variant="ghost" size="icon" onClick={() => setStep('menu')} aria-label="Voltar">
          <ArrowLeft className="h-5 w-5" />
        </Button>
      ) : null}
    </div>
  );

  const renderManualStep = () => (
    <div className="space-y-6">
      <DialogHeader className="text-left">
        <DialogTitle asChild>{renderStepHeader('Escreva as instrucoes da skill')}</DialogTitle>
      </DialogHeader>
      <div className="space-y-5">
        <div className="space-y-2">
          <Label htmlFor="skill-name">Nome da skill</Label>
          <Input
            id="skill-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="relatorio-status-semanal"
            className="h-11 rounded-lg"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="skill-description">Descricao</Label>
          <Textarea
            id="skill-description"
            rows={4}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Gere relatorios de status semanais com foco em progresso e proximos passos."
            className="rounded-lg"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="skill-instructions">Instrucoes</Label>
          <Textarea
            id="skill-instructions"
            rows={12}
            value={instructions}
            onChange={(event) => setInstructions(event.target.value)}
            placeholder="Resuma meu trabalho recente em tres secoes: conquistas, obstaculos e proximos passos..."
            className="rounded-lg"
          />
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => setStep('menu')}>
            Cancelar
          </Button>
          <Button disabled={isGenerating || !instructions.trim()} onClick={handleCreateByInstructions}>
            {isGenerating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Criar
          </Button>
        </div>
      </div>
    </div>
  );

  const renderUploadStep = () => (
    <div className="space-y-6">
      <DialogHeader className="text-left">
        <DialogTitle asChild>{renderStepHeader('Fazer upload de uma habilidade')}</DialogTitle>
      </DialogHeader>
      <div className="space-y-4">
        <input
          ref={fileInputRef}
          className="hidden"
          type="file"
          accept=".zip,.skill,.md,text/markdown"
          onChange={(event) => {
            const file = event.target.files?.[0] ?? null;
            if (!file) return;
            if (!isSupportedSkillFile(file.name)) {
              toast.error('Formato invalido. Use .zip, .skill ou .md.');
              return;
            }
            setSelectedFile(file);
          }}
        />

        <button
          type="button"
          className="flex w-full items-center gap-3 rounded-xl border border-dashed border-border bg-muted/30 px-4 py-6 text-left transition hover:bg-muted/50"
          onClick={() => fileInputRef.current?.click()}
        >
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <FileUp className="h-5 w-5" />
          </div>
          <div className="space-y-2">
            <p className="text-sm font-medium text-foreground">Selecionar arquivo</p>
            <p className="text-sm text-muted-foreground">Importe um arquivo .zip, .skill ou .md</p>
          </div>
        </button>

        {selectedFile ? (
          <div className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-muted-foreground">
            Arquivo selecionado: <span className="font-medium text-foreground">{selectedFile.name}</span>
          </div>
        ) : null}

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => setStep('menu')}>
            Cancelar
          </Button>
          <Button disabled={!selectedFile || isImporting} onClick={handleImport}>
            {isImporting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Importar
          </Button>
        </div>
      </div>
    </div>
  );

  const renderMenuStep = () => (
    <div className="space-y-6">
      <DialogHeader className="text-left">
        <DialogTitle className="text-2xl font-semibold text-foreground">Nova skill</DialogTitle>
      </DialogHeader>
      <div className="space-y-3">
        <button
          type="button"
          className="flex w-full items-center gap-4 rounded-xl border border-border bg-card p-5 text-left transition hover:bg-accent/30"
          onClick={handleCreateWithClaude}
        >
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <Bot className="h-5 w-5" />
          </div>
          <div>
            <p className="text-base font-semibold text-foreground">Criar com o Claude</p>
            <p className="text-sm text-muted-foreground">Crie skills complexas atraves de conversa</p>
          </div>
        </button>

        <button
          type="button"
          className="flex w-full items-center gap-4 rounded-xl border border-border bg-card p-5 text-left transition hover:bg-accent/30"
          onClick={() => setStep('manual')}
        >
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <ClipboardList className="h-5 w-5" />
          </div>
          <div>
            <p className="text-base font-semibold text-foreground">Escreva as instrucoes da skill</p>
            <p className="text-sm text-muted-foreground">Ideal para skills faceis de descrever</p>
          </div>
        </button>

        <button
          type="button"
          className="flex w-full items-center gap-4 rounded-xl border border-border bg-card p-5 text-left transition hover:bg-accent/30"
          onClick={() => setStep('upload')}
        >
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <Upload className="h-5 w-5" />
          </div>
          <div>
            <p className="text-base font-semibold text-foreground">Fazer upload de uma habilidade</p>
            <p className="text-sm text-muted-foreground">Importar um arquivo .zip, .skill ou .md</p>
          </div>
        </button>
      </div>
    </div>
  );

  return (
    <div className="rounded-2xl border border-white/70 bg-white/95 p-6 shadow-soft">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-foreground">Criacao assistida de skills</p>
          <p className="text-sm text-muted-foreground">
            Abra o modal para criar por conversa, instrucoes ou upload.
          </p>
        </div>
        <Button onClick={() => setOpen(true)}>
          <Sparkles className="mr-2 h-4 w-4" />
          Nova skill
        </Button>
      </div>

      <Dialog open={open} onOpenChange={handleCloseDialog}>
        <DialogContent className="max-w-[820px] border-border bg-background p-0">
          <div className="p-6 sm:p-8">
            {step === 'menu' ? renderMenuStep() : null}
            {step === 'manual' ? renderManualStep() : null}
            {step === 'upload' ? renderUploadStep() : null}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
