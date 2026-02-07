'use client';

import { useMemo, useState } from 'react';
import { Loader2, Sparkles } from 'lucide-react';
import type { GenerateSkillRequestPayload } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { toast } from 'sonner';

interface SkillWizardProps {
  isGenerating: boolean;
  onGenerate: (payload: GenerateSkillRequestPayload) => Promise<void>;
}

const splitLines = (value: string): string[] =>
  value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);

export function SkillWizard({ isGenerating, onGenerate }: SkillWizardProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [directive, setDirective] = useState('');
  const [examplesInput, setExamplesInput] = useState('');
  const [guardrailsInput, setGuardrailsInput] = useState('');
  const [citationStyle, setCitationStyle] = useState('abnt');
  const [outputFormat, setOutputFormat] = useState<'chat' | 'document' | 'checklist' | 'json'>('document');
  const [audience, setAudience] = useState<'beginner' | 'advanced' | 'both'>('both');

  const examples = useMemo(() => splitLines(examplesInput), [examplesInput]);
  const guardrails = useMemo(() => splitLines(guardrailsInput), [guardrailsInput]);

  const handleGenerate = async () => {
    if (!directive.trim()) {
      toast.error('Descreva o objetivo da skill antes de gerar.');
      return;
    }

    await onGenerate({
      directive: directive.trim(),
      name: name.trim() || undefined,
      description: description.trim() || undefined,
      citation_style: citationStyle,
      output_format: outputFormat,
      audience,
      examples: examples.length ? examples : undefined,
      guardrails: guardrails.length ? guardrails : undefined,
    });
  };

  return (
    <Card className="border-white/70 bg-white/95 shadow-soft">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="h-4 w-4 text-indigo-500" />
          Construtor Assistido (Basico)
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="skill-name">Nome tecnico (opcional)</Label>
            <Input
              id="skill-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="ex: analise-contrato-trabalhista"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="skill-description">Descricao curta (opcional)</Label>
            <Input
              id="skill-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Resumo da finalidade da skill"
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="skill-directive">Objetivo da skill</Label>
          <Textarea
            id="skill-directive"
            rows={6}
            value={directive}
            onChange={(event) => setDirective(event.target.value)}
            placeholder="Explique como a skill deve atuar, quando deve ser acionada e quais riscos deve evitar."
          />
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="skill-examples">Exemplos de prompts (1 por linha)</Label>
            <Textarea
              id="skill-examples"
              rows={4}
              value={examplesInput}
              onChange={(event) => setExamplesInput(event.target.value)}
              placeholder={'analisar peticao inicial\nrevisar clausulas de risco'}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="skill-guardrails">Guardrails (1 por linha)</Label>
            <Textarea
              id="skill-guardrails"
              rows={4}
              value={guardrailsInput}
              onChange={(event) => setGuardrailsInput(event.target.value)}
              placeholder={'nao inventar jurisprudencia\nmarcar duvidas como verificar'}
            />
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <div className="space-y-2">
            <Label>Publico-alvo</Label>
            <Select value={audience} onValueChange={(value: 'beginner' | 'advanced' | 'both') => setAudience(value)}>
              <SelectTrigger>
                <SelectValue placeholder="Selecione o publico" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="both">Basico e avancado</SelectItem>
                <SelectItem value="beginner">Basico</SelectItem>
                <SelectItem value="advanced">Avancado</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Estilo de citacao padrao</Label>
            <Select value={citationStyle} onValueChange={setCitationStyle}>
              <SelectTrigger>
                <SelectValue placeholder="Selecione o estilo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="abnt">ABNT</SelectItem>
                <SelectItem value="forense_br">Forense BR</SelectItem>
                <SelectItem value="bluebook">Bluebook</SelectItem>
                <SelectItem value="harvard">Harvard</SelectItem>
                <SelectItem value="apa">APA</SelectItem>
                <SelectItem value="oscola">OSCOLA</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Formato de saida</Label>
            <Select
              value={outputFormat}
              onValueChange={(value) => setOutputFormat(value as 'chat' | 'document' | 'checklist' | 'json')}
            >
              <SelectTrigger>
                <SelectValue placeholder="Selecione o formato" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="document">Documento</SelectItem>
                <SelectItem value="chat">Chat</SelectItem>
                <SelectItem value="checklist">Checklist</SelectItem>
                <SelectItem value="json">JSON</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex justify-end">
          <Button onClick={handleGenerate} disabled={isGenerating}>
            {isGenerating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Gerar rascunho
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
