'use client';

import { useEffect, useRef, useState, type DragEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Plus, FileUp, HelpCircle, Trash2 } from 'lucide-react';
import { ApplyTemplateDialog, ModelsBoard, TemplateWizardDialog } from '@/components/dashboard';
import { StyleLearner } from '@/components/dashboard/style-learner';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';
import { Checkbox } from '@/components/ui/checkbox';
import { useChatStore } from '@/stores';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

type BlockDraft = {
  id: string;
  title: string;
  kind: string;
  promptFragment: string;
  text: string;
  clauseId: string;
  lockable: boolean;
  editable: boolean;
  condition: string;
  insertVariable?: string;
};

export default function ModelsPage() {
  const [refreshKey, setRefreshKey] = useState(0);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [isDocxOpen, setIsDocxOpen] = useState(false);
  const [isClauseDialogOpen, setIsClauseDialogOpen] = useState(false);
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isIndexing, setIsIndexing] = useState(false);
  const [isClauseSaving, setIsClauseSaving] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    documentType: 'PETICAO_INICIAL',
    description: '',
  });
  const [useBlockTemplate, setUseBlockTemplate] = useState(false);
  const [templateMetaId, setTemplateMetaId] = useState('');
  const [templateVersion, setTemplateVersion] = useState('1.0.0');
  const [systemInstructions, setSystemInstructions] = useState('');
  const [outputFormat, setOutputFormat] = useState('');
  const [templateBody, setTemplateBody] = useState('');
  const [defaultLockedBlocksText, setDefaultLockedBlocksText] = useState('');
  const [showRawBlockText, setShowRawBlockText] = useState(false);
  const [variablesDraft, setVariablesDraft] = useState<Array<{
    name: string;
    label: string;
    type: string;
    required: boolean;
  }>>([
    { name: 'consulente_nome', label: 'Nome do Consulente', type: 'string', required: true },
  ]);
  const [blocks, setBlocks] = useState<BlockDraft[]>([]);
  const [ragFiles, setRagFiles] = useState<File[]>([]);
  const [ragMeta, setRagMeta] = useState({
    tipo_peca: 'peticao_inicial',
    area: 'geral',
    rito: 'ordinario',
    aprovado: true,
    chunk: true,
  });
  const {
    templateDocumentId,
    setTemplateDocumentId,
    templateDocumentName,
    setTemplateDocumentName,
  } = useChatStore();
  const [templateDocQuery, setTemplateDocQuery] = useState('');
  const [templateDocResults, setTemplateDocResults] = useState<any[]>([]);
  const [templateDocLoading, setTemplateDocLoading] = useState(false);
  const [clauses, setClauses] = useState<any[]>([]);
  const [clausesLoading, setClausesLoading] = useState(false);
  const [clausesRefreshKey, setClausesRefreshKey] = useState(0);
  const [clauseForm, setClauseForm] = useState({
    name: '',
    documentType: '',
    content: '',
  });
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const query = templateDocQuery.trim();
    if (!query) {
      setTemplateDocResults([]);
      setTemplateDocLoading(false);
      return;
    }

    const timer = setTimeout(async () => {
      setTemplateDocLoading(true);
      try {
        const data = await apiClient.getDocuments(0, 6, query);
        setTemplateDocResults(data.documents || []);
      } catch {
        setTemplateDocResults([]);
      } finally {
        setTemplateDocLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [templateDocQuery]);

  useEffect(() => {
    if (!templateDocumentId || templateDocumentName) return;

    let active = true;
    apiClient.getDocument(templateDocumentId)
      .then((doc) => {
        if (!active) return;
        setTemplateDocumentName(doc?.name || doc?.original_name || doc?.title || null);
      })
      .catch(() => {
        if (!active) return;
        setTemplateDocumentName(null);
      });

    return () => {
      active = false;
    };
  }, [templateDocumentId, templateDocumentName, setTemplateDocumentName]);

  useEffect(() => {
    setClausesLoading(true);
    apiClient
      .getClauses()
      .then((data) => setClauses(data.clauses || []))
      .catch(() => setClauses([]))
      .finally(() => setClausesLoading(false));
  }, [clausesRefreshKey]);

  const handleSelectTemplateDoc = (doc: any) => {
    if (!doc?.id) return;
    setTemplateDocumentId(doc.id);
    setTemplateDocumentName(doc.name || doc.original_name || doc.title || 'Documento');
    setTemplateDocQuery('');
    setTemplateDocResults([]);
  };

  const handleClearTemplateDoc = () => {
    setTemplateDocumentId(null);
    setTemplateDocumentName(null);
  };

  const handleCreate = async () => {
    const name = formData.name.trim();
    if (!name) {
      toast.error('Preencha o nome do modelo.');
      return;
    }

    let description = formData.description.trim();

    if (useBlockTemplate) {
      const parsedSchema: Record<string, any> = {};
      variablesDraft.forEach((field) => {
        const key = field.name.trim();
        if (!key) return;
        parsedSchema[key] = {
          type: field.type || 'string',
          label: field.label || key,
          required: field.required,
        };
      });

      const cleanBlocks = blocks
        .map((block) => ({
          id: block.id.trim(),
          title: block.title.trim() || undefined,
          kind: block.kind || undefined,
          prompt_fragment: block.promptFragment.trim() || undefined,
          text: block.text.trim() || undefined,
          clause_id: block.clauseId.trim() || undefined,
          lockable: block.lockable,
          editable: block.editable,
          condition: block.condition.trim() || undefined,
        }))
        .filter((block) => block.id);

      let body = templateBody.trim();
      if (!body && cleanBlocks.length > 0) {
        body = cleanBlocks
          .map((block) => `# ${block.title || block.id}\n{{BLOCK:${block.id}}}`)
          .join('\n\n');
      }

      if (!body) {
        toast.error('Defina o corpo do template ou adicione blocos.');
        return;
      }

      const defaultLocked = defaultLockedBlocksText
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean);

      const meta: Record<string, any> = {
        id: templateMetaId.trim() || undefined,
        version: templateVersion.trim() || undefined,
        document_type: formData.documentType || undefined,
        system_instructions: systemInstructions.trim() || undefined,
        output_format: outputFormat.trim() || undefined,
        variables_schema: parsedSchema,
        blocks: cleanBlocks,
        default_locked_blocks: defaultLocked.length ? defaultLocked : undefined,
        output_mode: 'blocks',
      };

      const metaText = JSON.stringify(meta, null, 2);
      description = `<!-- IUDX_TEMPLATE_V1\n${metaText}\n-->\n${body}`;
    }

    if (!description.trim()) {
      toast.error('Preencha o conteúdo do modelo.');
      return;
    }

    setIsSaving(true);
    try {
      await apiClient.createTemplate({
        name,
        description,
        document_type: formData.documentType || undefined,
      });
      toast.success('Modelo criado com sucesso.');
      setIsDialogOpen(false);
      setFormData({ name: '', documentType: 'PETICAO_INICIAL', description: '' });
      setUseBlockTemplate(false);
      setTemplateMetaId('');
      setTemplateVersion('1.0.0');
      setSystemInstructions('');
      setOutputFormat('');
      setTemplateBody('');
      setDefaultLockedBlocksText('');
      setBlocks([]);
      setShowRawBlockText(false);
      setVariablesDraft([{ name: 'consulente_nome', label: 'Nome do Consulente', type: 'string', required: true }]);
      setRefreshKey((prev) => prev + 1);
    } catch (e) {
      console.error(e);
      toast.error('Erro ao criar modelo.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleAddBlock = () => {
    setBlocks((prev) => [
      ...prev,
      {
        id: `bloco_${prev.length + 1}`,
        title: '',
        kind: 'llm',
        promptFragment: '',
        text: '',
        clauseId: '',
        lockable: true,
        editable: true,
        condition: '',
        insertVariable: '',
      },
    ]);
  };

  const handleAddVariable = () => {
    setVariablesDraft((prev) => [
      ...prev,
      { name: '', label: '', type: 'string', required: false },
    ]);
  };

  const handleUpdateVariable = (index: number, patch: Partial<typeof variablesDraft[number]>) => {
    setVariablesDraft((prev) => prev.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  };

  const handleRemoveVariable = (index: number) => {
    setVariablesDraft((prev) => prev.filter((_, i) => i !== index));
  };

  const replaceVariablesForPreview = (text: string) => {
    if (!text) return '';
    return text.replace(/{{\s*([\w\-]+)\s*}}/g, (_, key) => {
      const found = variablesDraft.find((field) => field.name === key);
      const label = found?.label || key;
      return `【${label}】`;
    });
  };

  const insertVariableToken = (index: number, target: 'text' | 'prompt') => {
    if (!variablesDraft.length) return;
    const selectedKey = blocks[index]?.insertVariable?.trim();
    const key = selectedKey || variablesDraft[0]?.name?.trim();
    if (!key) return;
    const token = `{{${key}}}`;
    if (target === 'text') {
      handleUpdateBlock(index, { text: (blocks[index]?.text || '') + ` ${token}` });
    } else {
      handleUpdateBlock(index, { promptFragment: (blocks[index]?.promptFragment || '') + ` ${token}` });
    }
  };

  const handleUpdateBlock = (index: number, patch: Partial<BlockDraft>) => {
    setBlocks((prev) => prev.map((block, i) => (i === index ? { ...block, ...patch } : block)));
  };

  const handleRemoveBlock = (index: number) => {
    setBlocks((prev) => prev.filter((_, i) => i !== index));
  };

  const moveBlock = (index: number, direction: 'up' | 'down') => {
    setBlocks((prev) => {
      const next = [...prev];
      const target = direction === 'up' ? index - 1 : index + 1;
      if (target < 0 || target >= next.length) return prev;
      const [item] = next.splice(index, 1);
      next.splice(target, 0, item);
      return next;
    });
  };

  const [draggedBlockIndex, setDraggedBlockIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

  const moveBlockTo = (from: number, to: number) => {
    if (from === to) return;
    setBlocks((prev) => {
      if (from < 0 || to < 0 || from >= prev.length || to >= prev.length) return prev;
      const next = [...prev];
      const [item] = next.splice(from, 1);
      next.splice(to, 0, item);
      return next;
    });
  };

  const handleDragStart = (index: number, event: DragEvent<HTMLElement>) => {
    setDraggedBlockIndex(index);
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', String(index));
  };

  const handleDragOver = (index: number, event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    if (dragOverIndex !== index) {
      setDragOverIndex(index);
    }
  };

  const handleDrop = (index: number, event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const fromRaw = event.dataTransfer.getData('text/plain');
    const from = draggedBlockIndex ?? (fromRaw ? Number(fromRaw) : null);
    if (from === null || Number.isNaN(from)) return;
    moveBlockTo(from, index);
    setDraggedBlockIndex(null);
    setDragOverIndex(null);
  };

  const handleDragEnd = () => {
    setDraggedBlockIndex(null);
    setDragOverIndex(null);
  };

  const handleCreateClause = async () => {
    if (!clauseForm.name.trim() || !clauseForm.content.trim()) {
      toast.error('Preencha nome e conteúdo da cláusula.');
      return;
    }

    setIsClauseSaving(true);
    try {
      await apiClient.createClause({
        name: clauseForm.name.trim(),
        content: clauseForm.content.trim(),
        document_type: clauseForm.documentType || undefined,
      });
      toast.success('Cláusula criada com sucesso.');
      setClauseForm({ name: '', documentType: '', content: '' });
      setIsClauseDialogOpen(false);
      setClausesRefreshKey((prev) => prev + 1);
    } catch (e) {
      console.error(e);
      toast.error('Erro ao criar cláusula.');
    } finally {
      setIsClauseSaving(false);
    }
  };

  const handleDeleteClause = async (clauseId: string) => {
    try {
      await apiClient.deleteClause(clauseId);
      toast.success('Cláusula removida.');
      setClausesRefreshKey((prev) => prev + 1);
    } catch (e) {
      console.error(e);
      toast.error('Erro ao remover cláusula.');
    }
  };

  const addRagFiles = (incoming: File[]) => {
    setRagFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}-${f.size}-${f.lastModified}`));
      const next = [...prev];
      for (const file of incoming) {
        const key = `${file.name}-${file.size}-${file.lastModified}`;
        if (!seen.has(key)) {
          next.push(file);
          seen.add(key);
        }
      }
      return next;
    });
  };

  const handleIndexRag = async () => {
    if (ragFiles.length === 0) {
      toast.error('Selecione arquivos para indexar.');
      return;
    }

    setIsIndexing(true);
    try {
      const paths = ragFiles.map((f) => (f as any).webkitRelativePath || f.name);
      const result = await apiClient.indexRagModels(ragFiles, {
        tipo_peca: ragMeta.tipo_peca,
        area: ragMeta.area,
        rito: ragMeta.rito,
        aprovado: ragMeta.aprovado,
        chunk: ragMeta.chunk,
        paths,
      });
      toast.success(`Indexação concluída: ${result.indexed}/${result.total_files} arquivos.`);
      if (result.errors?.length) {
        toast.warning(`${result.errors.length} arquivo(s) com erro.`);
      }
      setRagFiles([]);
      if (fileInputRef.current) fileInputRef.current.value = '';
      if (folderInputRef.current) folderInputRef.current.value = '';
    } catch (e) {
      console.error(e);
      toast.error('Erro ao indexar modelos.');
    } finally {
      setIsIndexing(false);
    }
  };

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase text-muted-foreground">Modelos & Estilo</p>
          <h1 className="font-display text-3xl text-foreground">Padronize a escrita jurídica.</h1>
          <p className="text-sm text-muted-foreground">
            Gerencie modelos e treine a IA para escrever exatamente como você.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            className="rounded-full"
            onClick={() => setIsDocxOpen(true)}
          >
            <FileUp className="mr-2 h-4 w-4" />
            Aplicar Template DOCX
          </Button>
          <Button
            variant="outline"
            className="rounded-full"
            onClick={() => setIsWizardOpen(true)}
          >
            <Plus className="mr-2 h-4 w-4" />
            Wizard de Templates
          </Button>
          <Button
            className="rounded-full bg-primary text-primary-foreground"
            onClick={() => setIsDialogOpen(true)}
          >
            <Plus className="mr-2 h-4 w-4" />
            Novo Modelo
          </Button>
        </div>
      </div>

      <div className="grid gap-8 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ModelsBoard refreshKey={refreshKey} />
        </div>
        <div>
          <StyleLearner />
        </div>
      </div>

      <section className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase text-muted-foreground">Clausulas</p>
            <h2 className="font-display text-2xl text-foreground">Biblioteca de Clausulas</h2>
            <p className="text-sm text-muted-foreground">
              Crie cláusulas reutilizáveis para compor templates por blocos.
            </p>
          </div>
          <Button
            className="rounded-full bg-primary text-primary-foreground"
            onClick={() => setIsClauseDialogOpen(true)}
          >
            <Plus className="mr-2 h-4 w-4" />
            Nova Clausula
          </Button>
        </div>

        <div className="mt-4 grid gap-3">
          {clausesLoading ? (
            <p className="py-4 text-center text-sm text-muted-foreground">Carregando cláusulas...</p>
          ) : clauses.length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">Nenhuma cláusula cadastrada.</p>
          ) : (
            clauses.map((clause) => (
              <div
                key={clause.id}
                className="flex flex-col gap-3 rounded-2xl border border-outline/40 bg-sand/60 px-4 py-3 md:flex-row md:items-center md:justify-between"
              >
                <div className="space-y-1">
                  <p className="font-semibold text-foreground">{clause.name || clause.title}</p>
                  <p className="text-xs text-muted-foreground">{clause.document_type || 'Geral'}</p>
                  <p className="max-w-xl text-xs text-muted-foreground">
                    {(clause.content || clause.description || '').slice(0, 160)}
                    {(clause.content || clause.description || '').length > 160 ? '...' : ''}
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="rounded-full border-rose-200 text-rose-600"
                  onClick={() => handleDeleteClause(clause.id)}
                >
                  <Trash2 className="mr-2 h-3.5 w-3.5" />
                  Remover
                </Button>
              </div>
            ))
          )}
        </div>
      </section>

      <section className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <p className="text-xs font-semibold uppercase text-muted-foreground">Documento base (RAG)</p>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <HelpCircle className="h-3.5 w-3.5 text-muted-foreground" />
                  </TooltipTrigger>
                  <TooltipContent className="max-w-xs text-xs">
                    Usa um documento real como referencia de estrutura e estilo. Diferente do Template ID, que aplica um molde fixo.
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
            <h2 className="font-display text-2xl text-foreground">Usar um documento específico como modelo</h2>
            <p className="text-sm text-muted-foreground">
              Escolha um documento da base para orientar a estrutura e o estilo da minuta.
            </p>
          </div>
          {templateDocumentId && (
            <Button variant="outline" className="rounded-full" onClick={handleClearTemplateDoc}>
              Limpar seleção
            </Button>
          )}
        </div>

        <div className="mt-4 space-y-3">
          <Input
            value={templateDocQuery}
            onChange={(e) => setTemplateDocQuery(e.target.value)}
            placeholder="Buscar documento na base..."
          />

          {templateDocQuery.trim() && (
            <div className="max-h-48 overflow-y-auto rounded-2xl border border-outline/40 bg-white shadow-sm">
              {templateDocLoading ? (
                <div className="px-4 py-3 text-xs text-muted-foreground">Buscando documentos...</div>
              ) : templateDocResults.length > 0 ? (
                templateDocResults.map((doc) => (
                  <button
                    key={doc.id}
                    type="button"
                    className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-xs text-foreground hover:bg-sand/50"
                    onClick={() => handleSelectTemplateDoc(doc)}
                  >
                    <span className="truncate">{doc.name || doc.original_name || doc.title || 'Documento'}</span>
                    <span className="text-[10px] text-muted-foreground">
                      {new Date(doc.created_at || Date.now()).toLocaleDateString()}
                    </span>
                  </button>
                ))
              ) : (
                <div className="px-4 py-3 text-xs text-muted-foreground">Nenhum documento encontrado.</div>
              )}
            </div>
          )}

          {templateDocumentId && (
            <div className="rounded-2xl border border-outline/40 bg-sand/60 px-4 py-3 text-xs text-foreground">
              <span className="font-semibold text-muted-foreground">Selecionado:</span>{' '}
              {templateDocumentName || templateDocumentId}
            </div>
          )}
        </div>
      </section>

      <section className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase text-muted-foreground">Indexação RAG</p>
            <h2 className="font-display text-2xl text-foreground">Indexar modelos em lote</h2>
            <p className="text-sm text-muted-foreground">
              Envie arquivos ou pastas para alimentar a base de modelos do RAG.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              className="rounded-full"
              onClick={() => fileInputRef.current?.click()}
            >
              Selecionar arquivos
            </Button>
            <Button
              variant="outline"
              className="rounded-full"
              onClick={() => folderInputRef.current?.click()}
            >
              Selecionar pasta
            </Button>
            <Button
              className="rounded-full bg-primary text-primary-foreground"
              onClick={handleIndexRag}
              disabled={isIndexing || ragFiles.length === 0}
            >
              {isIndexing ? 'Indexando...' : 'Indexar modelos'}
            </Button>
          </div>
        </div>

        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          multiple
          accept=".pdf,.docx,.txt,.md"
          onChange={(e) => {
            if (e.target.files?.length) {
              addRagFiles(Array.from(e.target.files));
              e.currentTarget.value = '';
            }
          }}
        />
        <input
          ref={folderInputRef}
          type="file"
          className="hidden"
          multiple
          // @ts-ignore - webkitdirectory is not standard in React types yet
          webkitdirectory=""
          directory=""
          onChange={(e) => {
            if (e.target.files?.length) {
              addRagFiles(Array.from(e.target.files));
              e.currentTarget.value = '';
            }
          }}
        />

        <div className="mt-4 grid gap-4 md:grid-cols-4">
          <div className="space-y-2">
            <Label htmlFor="rag-tipo">Tipo de Peça</Label>
            <Input
              id="rag-tipo"
              value={ragMeta.tipo_peca}
              onChange={(e) => setRagMeta({ ...ragMeta, tipo_peca: e.target.value })}
              placeholder="peticao_inicial"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="rag-area">Área</Label>
            <Input
              id="rag-area"
              value={ragMeta.area}
              onChange={(e) => setRagMeta({ ...ragMeta, area: e.target.value })}
              placeholder="civil, trabalhista..."
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="rag-rito">Rito</Label>
            <Input
              id="rag-rito"
              value={ragMeta.rito}
              onChange={(e) => setRagMeta({ ...ragMeta, rito: e.target.value })}
              placeholder="ordinario"
            />
          </div>
          <div className="space-y-2">
            <Label>Opções</Label>
            <div className="flex flex-col gap-2 rounded-lg border border-border/60 bg-muted/20 p-2">
              <label className="flex items-center gap-2 text-xs">
                <Checkbox
                  checked={ragMeta.aprovado}
                  onCheckedChange={(checked) => setRagMeta({ ...ragMeta, aprovado: !!checked })}
                />
                Aprovado
              </label>
              <label className="flex items-center gap-2 text-xs">
                <Checkbox
                  checked={ragMeta.chunk}
                  onCheckedChange={(checked) => setRagMeta({ ...ragMeta, chunk: !!checked })}
                />
                Fazer chunking
              </label>
            </div>
          </div>
        </div>

        <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
          <span>{ragFiles.length} arquivo(s) selecionado(s)</span>
          {ragFiles.length > 0 && (
            <button
              type="button"
              className="text-primary hover:underline"
              onClick={() => setRagFiles([])}
            >
              Limpar lista
            </button>
          )}
        </div>
      </section>

      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="sm:max-w-[720px] max-h-[90vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle>Novo Modelo Estrutural</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 overflow-y-auto flex-1 pr-2">
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Label htmlFor="model-name">Nome</Label>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                    </TooltipTrigger>
                    <TooltipContent className="max-w-xs text-xs">
                      Nome identificador do modelo. Será exibido na lista de templates disponíveis para geração de minutas.
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
              <Input
                id="model-name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="Ex.: Petição Inicial Trabalhista"
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Label htmlFor="model-type">Tipo de Documento</Label>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                    </TooltipTrigger>
                    <TooltipContent className="max-w-xs text-xs">
                      Categoria jurídica do documento. A IA usará prompts especializados para cada tipo, garantindo estrutura e linguagem adequadas.
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
              <select
                id="model-type"
                className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                value={formData.documentType}
                onChange={(e) => setFormData({ ...formData, documentType: e.target.value })}
              >
                <option value="PETICAO_INICIAL">Petição Inicial</option>
                <option value="CONTESTACAO">Contestação</option>
                <option value="RECURSO">Recurso / Apelação</option>
                <option value="PARECER">Parecer Jurídico</option>
                <option value="MANDADO_SEGURANCA">Mandado de Segurança</option>
                <option value="HABEAS_CORPUS">Habeas Corpus</option>
                <option value="RECLAMACAO_TRABALHISTA">Reclamação Trabalhista</option>
                <option value="DIVORCIO">Divórcio Consensual</option>
                <option value="CONTRATO">Contrato</option>
                <option value="NOTA_TECNICA">Nota Técnica</option>
                <option value="SENTENCA">Sentença</option>
              </select>
            </div>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Label>Modelo por blocos (IUDX_TEMPLATE_V1)</Label>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                    </TooltipTrigger>
                    <TooltipContent className="max-w-xs text-xs">
                      <p className="font-semibold mb-1">Modo avançado de templates</p>
                      <p>Permite criar documentos com seções fixas (contratos, disclaimers) e variáveis dinâmicas. Ideal para padronizar minutas com partes que nunca mudam.</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <Checkbox
                  checked={useBlockTemplate}
                  onCheckedChange={(checked) => setUseBlockTemplate(!!checked)}
                />
                Usar frontmatter + blocos (recomendado para partes fixas/variáveis)
              </label>
            </div>

            {useBlockTemplate ? (
              <div className="space-y-4 rounded-xl border border-border/60 bg-muted/10 p-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Label htmlFor="model-meta-id">ID interno (opcional)</Label>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                          </TooltipTrigger>
                          <TooltipContent className="max-w-xs text-xs">
                            Identificador único usado pelo sistema para referenciar este modelo em automações e APIs. Use snake_case sem espaços.
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </div>
                    <Input
                      id="model-meta-id"
                      value={templateMetaId}
                      onChange={(e) => setTemplateMetaId(e.target.value)}
                      placeholder="Ex.: parecer_tecnico_v1"
                    />
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Label htmlFor="model-version">Versão</Label>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                          </TooltipTrigger>
                          <TooltipContent className="max-w-xs text-xs">
                            Controle de versão semântico (ex: 1.0.0). Útil para rastrear alterações e manter histórico de templates.
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </div>
                    <Input
                      id="model-version"
                      value={templateVersion}
                      onChange={(e) => setTemplateVersion(e.target.value)}
                      placeholder="1.0.0"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <Label htmlFor="model-system">Instruções fixas (system)</Label>
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                        </TooltipTrigger>
                        <TooltipContent className="max-w-xs text-xs">
                          <p className="font-semibold mb-1">Regras imutáveis do modelo</p>
                          <p>Instruções que a IA sempre seguirá: tom, estilo, disclaimers obrigatórios, limitações. Ex: &quot;Use linguagem formal, nunca cite doutrina sem fonte.&quot;</p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </div>
                  <Textarea
                    id="model-system"
                    rows={3}
                    value={systemInstructions}
                    onChange={(e) => setSystemInstructions(e.target.value)}
                    placeholder="Regras obrigatórias, estilo, disclaimers..."
                  />
                </div>

                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <Label htmlFor="model-format">Formato de saída</Label>
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                        </TooltipTrigger>
                        <TooltipContent className="max-w-xs text-xs">
                          <p className="font-semibold mb-1">Estrutura do documento</p>
                          <p>Defina a estrutura esperada usando marcadores de seção. Ex: &quot;# 1. QUALIFICAÇÃO DAS PARTES&quot;, &quot;# 2. DOS FATOS&quot;. A IA seguirá esta organização.</p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </div>
                  <Textarea
                    id="model-format"
                    rows={4}
                    value={outputFormat}
                    onChange={(e) => setOutputFormat(e.target.value)}
                    placeholder="# 1. Identificacao&#10;# 2. Objeto..."
                  />
                </div>

                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Label>Campos do modelo</Label>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                          </TooltipTrigger>
                          <TooltipContent className="max-w-xs text-xs">
                            <p className="font-semibold mb-1">Variáveis dinâmicas</p>
                            <p>
                              Campos que serão preenchidos em um formulário antes da geração. Use{' '}
                              {'{{ nome_do_campo }}'} nos blocos para inserir valores. Ex: {'{{ nome_cliente }}'},{' '}
                              {'{{ valor_contrato }}'}
                            </p>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="rounded-full"
                      onClick={handleAddVariable}
                    >
                      <Plus className="mr-2 h-3.5 w-3.5" />
                      Adicionar campo
                    </Button>
                  </div>
                  {variablesDraft.length === 0 ? (
                    <p className="text-xs text-muted-foreground">Adicione campos para o formulário guiado.</p>
                  ) : (
                    <div className="space-y-3">
                      {variablesDraft.map((field, index) => (
                        <div
                          key={`field-${index}`}
                          className="grid gap-3 rounded-lg border border-border/60 bg-white/90 p-3 md:grid-cols-4"
                        >
                          <div className="space-y-1 md:col-span-2">
                            <Label>Nome interno</Label>
                            <Input
                              value={field.name}
                              onChange={(e) => handleUpdateVariable(index, { name: e.target.value })}
                              placeholder="consulente_nome"
                            />
                          </div>
                          <div className="space-y-1 md:col-span-2">
                            <Label>Rótulo</Label>
                            <Input
                              value={field.label}
                              onChange={(e) => handleUpdateVariable(index, { label: e.target.value })}
                              placeholder="Nome do Consulente"
                            />
                          </div>
                          <div className="space-y-1">
                            <Label>Tipo</Label>
                            <select
                              className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                              value={field.type}
                              onChange={(e) => handleUpdateVariable(index, { type: e.target.value })}
                            >
                              <option value="string">Texto</option>
                              <option value="number">Número</option>
                              <option value="date">Data</option>
                              <option value="boolean">Sim/Não</option>
                            </select>
                          </div>
                          <div className="flex items-center gap-2">
                            <Checkbox
                              checked={field.required}
                              onCheckedChange={(checked) => handleUpdateVariable(index, { required: !!checked })}
                            />
                            <span className="text-xs text-muted-foreground">Obrigatório</span>
                          </div>
                          <div className="md:col-span-4">
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              className="rounded-full text-rose-600"
                              onClick={() => handleRemoveVariable(index)}
                            >
                              <Trash2 className="mr-1 h-3.5 w-3.5" />
                              Remover campo
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Label>Blocos</Label>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                          </TooltipTrigger>
                          <TooltipContent className="max-w-xs text-xs">
                            <p className="font-semibold mb-1">Seções do documento</p>
                            <p>Cada bloco é uma seção. Tipos:</p>
                            <ul className="list-disc pl-4 mt-1 space-y-1">
                              <li><strong>LLM:</strong> IA gera conteúdo baseado no prompt</li>
                              <li><strong>Fixo:</strong> Texto imutável (disclaimers, cláusulas padrão)</li>
                              <li><strong>Cláusula:</strong> Referencia cláusulas da biblioteca</li>
                              <li><strong>Variável:</strong> Inserção de campo dinâmico</li>
                            </ul>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="rounded-full"
                      onClick={handleAddBlock}
                    >
                      <Plus className="mr-2 h-3.5 w-3.5" />
                      Adicionar bloco
                    </Button>
                  </div>
                  {blocks.length === 0 ? (
                    <p className="text-xs text-muted-foreground">Adicione blocos para montar o template.</p>
                  ) : (
                    <div className="space-y-3">
                      {blocks.map((block, index) => (
                        <div
                          key={`${block.id}-${index}`}
                          className={`space-y-3 rounded-lg border border-border/60 bg-white/90 p-3 ${dragOverIndex === index ? 'ring-2 ring-indigo-200' : ''
                            }`}
                          onDragOver={(event) => handleDragOver(index, event)}
                          onDrop={(event) => handleDrop(index, event)}
                          onDragLeave={() => {
                            if (dragOverIndex === index) setDragOverIndex(null);
                          }}
                        >
                          <div className="grid gap-3 md:grid-cols-3">
                            <div className="space-y-1">
                              <Label>ID</Label>
                              <Input
                                value={block.id}
                                onChange={(e) => handleUpdateBlock(index, { id: e.target.value })}
                                placeholder="ex.: fatos"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label>Título</Label>
                              <Input
                                value={block.title}
                                onChange={(e) => handleUpdateBlock(index, { title: e.target.value })}
                                placeholder="Fatos relevantes"
                              />
                            </div>
                            <div className="space-y-1">
                              <Label>Tipo</Label>
                              <select
                                className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                                value={block.kind}
                                onChange={(e) => handleUpdateBlock(index, { kind: e.target.value })}
                              >
                                <option value="llm">LLM</option>
                                <option value="fixed">Fixo</option>
                                <option value="clause">Cláusula</option>
                                <option value="variable">Variável</option>
                              </select>
                            </div>
                          </div>

                          <div className="space-y-2">
                            <Label>Condição (opcional)</Label>
                            <Input
                              value={block.condition}
                              onChange={(e) => handleUpdateBlock(index, { condition: e.target.value })}
                              placeholder="ex.: incluir_jurisprudencia == true"
                            />
                          </div>

                          {block.kind === 'clause' && (
                            <div className="space-y-2">
                              <Label>Clause ID</Label>
                              <Input
                                value={block.clauseId}
                                onChange={(e) => handleUpdateBlock(index, { clauseId: e.target.value })}
                                placeholder="ID da clausula"
                              />
                            </div>
                          )}

                          {(block.kind === 'llm' || block.kind === 'variable') && (
                            <div className="space-y-2">
                              <Label>Prompt do bloco</Label>
                              {showRawBlockText ? (
                                <Textarea
                                  rows={3}
                                  value={block.promptFragment}
                                  onChange={(e) => handleUpdateBlock(index, { promptFragment: e.target.value })}
                                  placeholder="Instrucao para o modelo preencher este bloco..."
                                />
                              ) : (
                                <div className="rounded-lg border border-border/60 bg-muted/10 p-3 text-xs text-muted-foreground">
                                  {replaceVariablesForPreview(block.promptFragment || '') || 'Defina o prompt do bloco.'}
                                </div>
                              )}
                              <div className="flex flex-wrap items-center gap-2">
                                <select
                                  className="rounded-full border border-input bg-white px-3 py-1 text-xs"
                                  value={block.insertVariable || ''}
                                  onChange={(e) => handleUpdateBlock(index, { insertVariable: e.target.value })}
                                >
                                  <option value="">Inserir campo...</option>
                                  {variablesDraft.map((field) => (
                                    <option key={field.name} value={field.name}>
                                      {field.label || field.name}
                                    </option>
                                  ))}
                                </select>
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  className="rounded-full"
                                  onClick={() => insertVariableToken(index, 'prompt')}
                                >
                                  Inserir
                                </Button>
                              </div>
                            </div>
                          )}

                          {block.kind === 'fixed' && (
                            <div className="space-y-2">
                              <Label>Texto fixo</Label>
                              {showRawBlockText ? (
                                <Textarea
                                  rows={3}
                                  value={block.text}
                                  onChange={(e) => handleUpdateBlock(index, { text: e.target.value })}
                                  placeholder="Texto imutavel..."
                                />
                              ) : (
                                <div className="rounded-lg border border-border/60 bg-muted/10 p-3 text-xs text-muted-foreground">
                                  {replaceVariablesForPreview(block.text || '') || 'Defina o texto fixo.'}
                                </div>
                              )}
                              <div className="flex flex-wrap items-center gap-2">
                                <select
                                  className="rounded-full border border-input bg-white px-3 py-1 text-xs"
                                  value={block.insertVariable || ''}
                                  onChange={(e) => handleUpdateBlock(index, { insertVariable: e.target.value })}
                                >
                                  <option value="">Inserir campo...</option>
                                  {variablesDraft.map((field) => (
                                    <option key={field.name} value={field.name}>
                                      {field.label || field.name}
                                    </option>
                                  ))}
                                </select>
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  className="rounded-full"
                                  onClick={() => insertVariableToken(index, 'text')}
                                >
                                  Inserir
                                </Button>
                              </div>
                            </div>
                          )}

                          <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
                            <label className="flex items-center gap-2">
                              <Checkbox
                                checked={block.lockable}
                                onCheckedChange={(checked) => handleUpdateBlock(index, { lockable: !!checked })}
                              />
                              Travável pelo usuário
                            </label>
                            <label className="flex items-center gap-2">
                              <Checkbox
                                checked={block.editable}
                                onCheckedChange={(checked) => handleUpdateBlock(index, { editable: !!checked })}
                              />
                              Editável pelo usuário
                            </label>
                            <div className="flex items-center gap-2">
                              <span
                                draggable
                                onDragStart={(event) => handleDragStart(index, event)}
                                onDragEnd={handleDragEnd}
                                className="cursor-move rounded-full border border-indigo-200 bg-indigo-50 px-2 py-1 text-[10px] font-semibold text-indigo-700"
                                title="Arraste para reordenar"
                              >
                                Drag
                              </span>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                className="rounded-full text-slate-500"
                                onClick={() => moveBlock(index, 'up')}
                              >
                                ↑
                              </Button>
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                className="rounded-full text-slate-500"
                                onClick={() => moveBlock(index, 'down')}
                              >
                                ↓
                              </Button>
                            </div>
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              className="rounded-full text-rose-600"
                              onClick={() => handleRemoveBlock(index)}
                            >
                              <Trash2 className="mr-1 h-3.5 w-3.5" />
                              Remover
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="space-y-2">
                  <Label>Cláusulas disponíveis</Label>
                  {clausesLoading ? (
                    <p className="text-xs text-muted-foreground">Carregando cláusulas...</p>
                  ) : clauses.length === 0 ? (
                    <p className="text-xs text-muted-foreground">Nenhuma cláusula cadastrada.</p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {clauses.map((clause) => (
                        <Button
                          key={clause.id}
                          type="button"
                          variant="outline"
                          size="sm"
                          className="rounded-full"
                          onClick={() => {
                            setBlocks((prev) => [
                              ...prev,
                              {
                                id: `clause_${prev.length + 1}`,
                                title: clause.name || clause.title || 'Cláusula',
                                kind: 'clause',
                                promptFragment: '',
                                text: '',
                                clauseId: clause.id,
                                lockable: true,
                                editable: false,
                                condition: '',
                                insertVariable: '',
                              },
                            ]);
                          }}
                        >
                          {clause.name || clause.title}
                        </Button>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex items-center justify-between rounded-lg border border-border/60 bg-white/80 px-3 py-2 text-xs text-muted-foreground">
                  <span>Mostrar texto bruto (avançado)</span>
                  <Checkbox
                    checked={showRawBlockText}
                    onCheckedChange={(checked) => setShowRawBlockText(!!checked)}
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="model-default-locked">Blocos travados por padrão</Label>
                  <Input
                    id="model-default-locked"
                    value={defaultLockedBlocksText}
                    onChange={(e) => setDefaultLockedBlocksText(e.target.value)}
                    placeholder="ex.: disclaimer, foro"
                  />
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="model-body">Corpo do template</Label>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="rounded-full"
                      onClick={() => {
                        if (!blocks.length) return;
                        const body = blocks
                          .filter((block) => block.id.trim())
                          .map((block) => `# ${block.title || block.id}\n{{BLOCK:${block.id.trim()}}}`)
                          .join('\n\n');
                        setTemplateBody(body);
                      }}
                    >
                      Gerar com blocos
                    </Button>
                  </div>
                  <Textarea
                    id="model-body"
                    rows={10}
                    value={templateBody}
                    onChange={(e) => setTemplateBody(e.target.value)}
                    placeholder="# 1. Identificacao&#10;{{BLOCK:identificacao}}"
                  />
                  <div className="rounded-lg border border-border/60 bg-muted/10 p-3 text-xs text-muted-foreground">
                    {replaceVariablesForPreview(templateBody || '') || 'Preview do corpo do template.'}
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <Label htmlFor="model-body">Conteúdo do Modelo</Label>
                <Textarea
                  id="model-body"
                  rows={10}
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Cole aqui a estrutura, títulos e instruções do modelo..."
                />
              </div>
            )}
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setIsDialogOpen(false)} disabled={isSaving}>
              Cancelar
            </Button>
            <Button onClick={handleCreate} disabled={isSaving}>
              {isSaving ? 'Salvando...' : 'Salvar Modelo'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={isClauseDialogOpen} onOpenChange={setIsClauseDialogOpen}>
        <DialogContent className="sm:max-w-[520px]">
          <DialogHeader>
            <DialogTitle>Nova Clausula</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="clause-name">Nome</Label>
              <Input
                id="clause-name"
                value={clauseForm.name}
                onChange={(e) => setClauseForm({ ...clauseForm, name: e.target.value })}
                placeholder="Ex.: Clausula de Foro"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="clause-type">Tipo de Documento (opcional)</Label>
              <Input
                id="clause-type"
                value={clauseForm.documentType}
                onChange={(e) => setClauseForm({ ...clauseForm, documentType: e.target.value })}
                placeholder="Ex.: contrato, escritura"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="clause-content">Conteúdo</Label>
              <Textarea
                id="clause-content"
                rows={6}
                value={clauseForm.content}
                onChange={(e) => setClauseForm({ ...clauseForm, content: e.target.value })}
                placeholder="Texto da clausula..."
              />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setIsClauseDialogOpen(false)} disabled={isClauseSaving}>
              Cancelar
            </Button>
            <Button onClick={handleCreateClause} disabled={isClauseSaving}>
              {isClauseSaving ? 'Salvando...' : 'Salvar Clausula'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <TemplateWizardDialog
        open={isWizardOpen}
        onOpenChange={setIsWizardOpen}
        onCreated={() => setRefreshKey((prev) => prev + 1)}
      />

      <ApplyTemplateDialog open={isDocxOpen} onOpenChange={setIsDocxOpen} />
    </div>
  );
}
