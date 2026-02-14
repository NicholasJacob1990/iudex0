'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Sparkles } from 'lucide-react';
import apiClient, {
  type GenerateSkillRequestPayload,
  type SkillLibraryItem,
  type ValidateSkillResponsePayload,
} from '@/lib/api-client';
import { SkillEditor, SkillList, SkillWizard } from '@/components/skills';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';

type BuilderMode = 'wizard' | 'editor';

const toErrorMessage = (error: unknown): string => {
  if (typeof error === 'string') return error;
  if (error && typeof error === 'object') {
    const anyError = error as { response?: { data?: { detail?: unknown } }; message?: string };
    const detail = anyError.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map(String).join(' | ');
    if (anyError.message) return anyError.message;
  }
  return 'Falha ao processar a requisicao.';
};

export default function SkillsPage() {
  const searchParams = useSearchParams();
  const initialMode = useMemo<BuilderMode>(
    () => (searchParams.get('mode') === 'editor' ? 'editor' : 'wizard'),
    [searchParams]
  );

  const [mode, setMode] = useState<BuilderMode>(initialMode);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [markdown, setMarkdown] = useState('');
  const [generateWarnings, setGenerateWarnings] = useState<string[]>([]);
  const [validation, setValidation] = useState<ValidateSkillResponsePayload | null>(null);
  const [skills, setSkills] = useState<SkillLibraryItem[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);
  const [isLoadingSkills, setIsLoadingSkills] = useState(false);

  useEffect(() => {
    setMode(initialMode);
  }, [initialMode]);

  const loadSkills = useCallback(async () => {
    setIsLoadingSkills(true);
    try {
      const items = await apiClient.listSkillsFromLibrary();
      setSkills(items);
    } catch (error) {
      toast.error(toErrorMessage(error));
    } finally {
      setIsLoadingSkills(false);
    }
  }, []);

  useEffect(() => {
    void loadSkills();
  }, [loadSkills]);

  const handleGenerate = useCallback(async (payload: GenerateSkillRequestPayload) => {
    setIsGenerating(true);
    try {
      const response = await apiClient.generateSkill(payload);
      setDraftId(response.draft_id);
      setMarkdown(response.skill_markdown);
      setGenerateWarnings(response.warnings || []);
      setValidation(null);
      setMode('editor');
      toast.success('Rascunho de skill gerado.');
    } catch (error) {
      toast.error(toErrorMessage(error));
    } finally {
      setIsGenerating(false);
    }
  }, []);

  const handleImportMarkdown = useCallback((importedMarkdown: string) => {
    if (!importedMarkdown.trim()) {
      toast.error('Skill importada esta vazia.');
      return;
    }
    setDraftId(null);
    setMarkdown(importedMarkdown);
    setGenerateWarnings([]);
    setValidation(null);
    setMode('editor');
  }, []);

  const handleValidate = useCallback(async () => {
    if (!markdown.trim()) {
      toast.error('Inclua o markdown da skill antes de validar.');
      return;
    }
    setIsValidating(true);
    try {
      const result = await apiClient.validateSkill({
        draft_id: draftId ?? undefined,
        skill_markdown: markdown,
      });
      setValidation(result);
      toast.success(result.valid ? 'Skill valida.' : 'Validacao concluida com pendencias.');
    } catch (error) {
      toast.error(toErrorMessage(error));
    } finally {
      setIsValidating(false);
    }
  }, [draftId, markdown]);

  const handlePublish = useCallback(
    async (options: { activate: boolean; visibility: 'personal' | 'organization' | 'public' }) => {
      if (!markdown.trim()) {
        toast.error('Inclua o markdown da skill antes de publicar.');
        return;
      }
      setIsPublishing(true);
      try {
        const result = await apiClient.publishSkill({
          draft_id: draftId ?? undefined,
          skill_markdown: markdown,
          activate: options.activate,
          visibility: options.visibility,
        });
        toast.success(`Skill publicada (${result.status}) na versao ${result.version}.`);
        await loadSkills();
      } catch (error) {
        toast.error(toErrorMessage(error));
      } finally {
        setIsPublishing(false);
      }
    },
    [draftId, loadSkills, markdown]
  );

  return (
    <div className="space-y-6">
      <div className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/10 text-indigo-600">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase text-muted-foreground">Skill Builder</p>
            <h1 className="text-2xl font-semibold">Construa skills para usuarios basicos e avancados</h1>
          </div>
          <Badge variant="secondary" className="ml-auto">
            Prompt-to-Skill
          </Badge>
        </div>
        <p className="mt-3 text-sm text-muted-foreground">
          Modo basico com assistente guiado e modo avancado com edicao YAML/Markdown completa.
        </p>
      </div>

      {generateWarnings.length > 0 ? (
        <Alert>
          <AlertDescription>{generateWarnings.join(' | ')}</AlertDescription>
        </Alert>
      ) : null}

      <Tabs value={mode} onValueChange={(value) => setMode(value as BuilderMode)} className="space-y-4">
        <TabsList>
          <TabsTrigger value="wizard">Basico (Wizard)</TabsTrigger>
          <TabsTrigger value="editor">Avancado (Editor)</TabsTrigger>
        </TabsList>
        <TabsContent value="wizard">
          <SkillWizard
            isGenerating={isGenerating}
            onGenerate={handleGenerate}
            onImportMarkdown={handleImportMarkdown}
          />
        </TabsContent>
        <TabsContent value="editor">
          <SkillEditor
            draftId={draftId}
            markdown={markdown}
            validation={validation}
            isValidating={isValidating}
            isPublishing={isPublishing}
            onMarkdownChange={setMarkdown}
            onValidate={handleValidate}
            onPublish={handlePublish}
          />
        </TabsContent>
      </Tabs>

      <SkillList items={skills} loading={isLoadingSkills} onRefresh={loadSkills} />
    </div>
  );
}
