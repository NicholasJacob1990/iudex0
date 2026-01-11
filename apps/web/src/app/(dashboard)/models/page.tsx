'use client';

import { useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Plus, FileUp } from 'lucide-react';
import { ApplyTemplateDialog, ModelsBoard } from '@/components/dashboard';
import { StyleLearner } from '@/components/dashboard/style-learner';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';
import { Checkbox } from '@/components/ui/checkbox';

export default function ModelsPage() {
  const [refreshKey, setRefreshKey] = useState(0);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [isDocxOpen, setIsDocxOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isIndexing, setIsIndexing] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    documentType: 'PETICAO_INICIAL',
    description: '',
  });
  const [ragFiles, setRagFiles] = useState<File[]>([]);
  const [ragMeta, setRagMeta] = useState({
    tipo_peca: 'peticao_inicial',
    area: 'geral',
    rito: 'ordinario',
    aprovado: true,
    chunk: true,
  });
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const handleCreate = async () => {
    if (!formData.name.trim() || !formData.description.trim()) {
      toast.error('Preencha nome e conteúdo do modelo.');
      return;
    }

    setIsSaving(true);
    try {
      await apiClient.createTemplate({
        name: formData.name.trim(),
        description: formData.description.trim(),
        document_type: formData.documentType || undefined,
      });
      toast.success('Modelo criado com sucesso.');
      setIsDialogOpen(false);
      setFormData({ name: '', documentType: 'PETICAO_INICIAL', description: '' });
      setRefreshKey((prev) => prev + 1);
    } catch (e) {
      console.error(e);
      toast.error('Erro ao criar modelo.');
    } finally {
      setIsSaving(false);
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
        <DialogContent className="sm:max-w-[640px]">
          <DialogHeader>
            <DialogTitle>Novo Modelo Estrutural</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="model-name">Nome</Label>
              <Input
                id="model-name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="Ex.: Petição Inicial Trabalhista"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="model-type">Tipo de Documento</Label>
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
              <Label htmlFor="model-body">Conteúdo do Modelo</Label>
              <Textarea
                id="model-body"
                rows={10}
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Cole aqui a estrutura, títulos e instruções do modelo..."
              />
            </div>
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

      <ApplyTemplateDialog open={isDocxOpen} onOpenChange={setIsDocxOpen} />
    </div>
  );
}
