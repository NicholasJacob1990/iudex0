'use client';

import { useState } from 'react';
import { CheckCircle2, Loader2, ShieldAlert } from 'lucide-react';
import type { ValidateSkillResponsePayload } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';

interface SkillEditorProps {
  draftId: string | null;
  markdown: string;
  validation: ValidateSkillResponsePayload | null;
  isValidating: boolean;
  isPublishing: boolean;
  onMarkdownChange: (value: string) => void;
  onValidate: () => Promise<void>;
  onPublish: (options: {
    activate: boolean;
    visibility: 'personal' | 'organization' | 'public';
  }) => Promise<void>;
}

export function SkillEditor({
  draftId,
  markdown,
  validation,
  isValidating,
  isPublishing,
  onMarkdownChange,
  onValidate,
  onPublish,
}: SkillEditorProps) {
  const [activate, setActivate] = useState(true);
  const [visibility, setVisibility] = useState<'personal' | 'organization' | 'public'>('personal');

  return (
    <Card className="border-white/70 bg-white/95 shadow-soft">
      <CardHeader>
        <CardTitle className="text-base">Editor Avancado (YAML + Markdown)</CardTitle>
        <p className="text-xs text-muted-foreground">
          {draftId ? `Draft ativo: ${draftId}` : 'Sem draft: publicacao direta habilitada via markdown.'}
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="skill-markdown">Skill markdown</Label>
          <Textarea
            id="skill-markdown"
            rows={20}
            value={markdown}
            onChange={(event) => onMarkdownChange(event.target.value)}
            placeholder={'---\nname: minha-skill\ntriggers:\n  - exemplo\ntools_required:\n  - search_rag\n---\n\n## Instructions\n...'}
            className="font-mono text-xs"
          />
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <div className="space-y-2">
            <Label>Visibilidade</Label>
            <Select value={visibility} onValueChange={(value: 'personal' | 'organization' | 'public') => setVisibility(value)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="personal">Pessoal</SelectItem>
                <SelectItem value="organization">Organizacao</SelectItem>
                <SelectItem value="public">Publica</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Ativar apos publicar</Label>
            <div className="flex h-10 items-center rounded-md border px-3">
              <Switch checked={activate} onCheckedChange={setActivate} />
              <span className="ml-2 text-sm">{activate ? 'Ativa' : 'Inativa'}</span>
            </div>
          </div>
          <div className="flex items-end gap-2">
            <Button
              variant="outline"
              className="w-full"
              disabled={isValidating || !markdown.trim()}
              onClick={onValidate}
            >
              {isValidating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Validar
            </Button>
          </div>
        </div>

        {validation ? (
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs">
            <div className="mb-2 flex items-center gap-2">
              {validation.valid ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              ) : (
                <ShieldAlert className="h-4 w-4 text-amber-600" />
              )}
              <strong>{validation.valid ? 'Skill valida' : 'Skill com pendencias'}</strong>
            </div>
            {validation.errors.length > 0 ? (
              <ul className="list-disc space-y-1 pl-4 text-red-700">
                {validation.errors.map((error) => (
                  <li key={error}>{error}</li>
                ))}
              </ul>
            ) : null}
            {validation.warnings.length > 0 ? (
              <ul className="mt-2 list-disc space-y-1 pl-4 text-amber-700">
                {validation.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            ) : null}
            {typeof validation.quality_score === 'number' ? (
              <p className="mt-2 text-slate-600">
                Qualidade: {(validation.quality_score * 100).toFixed(1)}% ·
                {' '}TPR: {((validation.tpr ?? 0) * 100).toFixed(1)}% ·
                {' '}FPR: {((validation.fpr ?? 0) * 100).toFixed(1)}%
              </p>
            ) : null}
            {validation.security_violations?.length ? (
              <ul className="mt-2 list-disc space-y-1 pl-4 text-red-700">
                {validation.security_violations.map((item) => (
                  <li key={item}>Violacao de seguranca: {item}</li>
                ))}
              </ul>
            ) : null}
            {validation.improvements?.length ? (
              <ul className="mt-2 list-disc space-y-1 pl-4 text-slate-700">
                {validation.improvements.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        <div className="flex justify-end">
          <Button
            disabled={isPublishing || !markdown.trim()}
            onClick={() => onPublish({ activate, visibility })}
          >
            {isPublishing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Publicar skill
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
