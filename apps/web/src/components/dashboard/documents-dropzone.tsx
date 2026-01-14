'use client';

import { ChangeEvent, useEffect, useState } from 'react';
import { UploadCloud, FileText, Download, FolderDown, Link as LinkIcon, Type } from 'lucide-react';
import { useDocumentStore } from '@/stores';
import { formatFileSize } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import apiClient from '@/lib/api-client';

export function DocumentsDropzone() {
  const { uploadDocument, fetchDocuments, documents, total, isUploading } = useDocumentStore();
  const [urlDialogOpen, setUrlDialogOpen] = useState(false);
  const [textDialogOpen, setTextDialogOpen] = useState(false);
  const [url, setUrl] = useState('');
  const [textContent, setTextContent] = useState('');
  const [textTitle, setTextTitle] = useState('');

  useEffect(() => {
    fetchDocuments().catch(() => undefined);
  }, [fetchDocuments]);

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      await uploadDocument(file);
      toast.success(`Documento "${file.name}" enviado com sucesso.`);
    } catch (error) {
      // handled by interceptor
    } finally {
      event.target.value = '';
    }
  };

  const handleTranscribe = () => {
    toast.info('Funcionalidade de transcrição será implementada em breve');
  };

  const handleUrlSubmit = async () => {
    if (!url.trim()) {
      toast.error('Por favor, insira uma URL válida');
      return;
    }
    try {
      toast.info(`Importando conteúdo de: ${url}`);
      await apiClient.createDocumentFromUrl({ url: url.trim() });
      await fetchDocuments();
      toast.success('Conteúdo importado com sucesso!');
      setUrl('');
      setUrlDialogOpen(false);
    } catch (error) {
      toast.error('Erro ao importar a URL.');
    }
  };

  const handleTextSubmit = async () => {
    if (!textContent.trim()) {
      toast.error('Por favor, insira algum texto');
      return;
    }
    if (!textTitle.trim()) {
      toast.error('Informe um título para o texto.');
      return;
    }
    try {
      toast.info('Salvando texto...');
      await apiClient.createDocumentFromText({
        title: textTitle.trim(),
        content: textContent.trim(),
      });
      await fetchDocuments();
      toast.success('Texto adicionado com sucesso!');
      setTextContent('');
      setTextTitle('');
      setTextDialogOpen(false);
    } catch (error) {
      toast.error('Erro ao salvar texto.');
    }
  };

  return (
    <>
      <section className="rounded-3xl border border-white/80 bg-white/95 p-6 shadow-soft">
        <div className="flex flex-col gap-3 text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-3xl bg-primary/10 text-primary">
            <UploadCloud className="h-7 w-7" />
          </div>
          <h2 className="font-display text-2xl text-foreground">Arraste e solte os documentos aqui</h2>
          <p className="text-sm text-muted-foreground">
            Integre processos, petições, decisões, peças e mais. OCR automático para PDFs escaneados.
          </p>
        </div>

        <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
          <label className="cursor-pointer">
            <input type="file" className="hidden" onChange={handleUpload} disabled={isUploading} />
            <span className="chip bg-sand text-foreground hover:bg-sand/80 transition-colors">Arquivos</span>
          </label>
          <button
            onClick={handleTranscribe}
            className="chip bg-sand text-foreground hover:bg-sand/80 transition-colors"
          >
            Transcrever
          </button>
          <button
            onClick={() => setUrlDialogOpen(true)}
            className="chip bg-sand text-foreground hover:bg-sand/80 transition-colors"
          >
            URL
          </button>
          <button
            onClick={() => setTextDialogOpen(true)}
            className="chip bg-sand text-foreground hover:bg-sand/80 transition-colors"
          >
            Inserir texto
          </button>
        </div>

      <label className="mt-6 flex cursor-pointer flex-col items-center justify-center rounded-3xl border-2 border-dashed border-outline/60 bg-sand/60 py-10 text-center transition hover:border-primary hover:bg-primary/5">
        <input type="file" className="hidden" onChange={handleUpload} disabled={isUploading} />
        <p className="text-sm font-semibold text-primary">
          {isUploading ? 'Processando...' : 'Clique ou arraste arquivos'}
        </p>
        <p className="text-xs text-muted-foreground">PDF, DOCX, ODT, ZIP, HTML, imagens, áudio, vídeo até 500MB</p>
        <p className="text-[10px] text-muted-foreground mt-2">
          OCR, áudio e vídeo são processados em segundo plano. Acompanhe o status no card do documento.
        </p>
      </label>

        <div className="mt-6 flex flex-wrap items-center gap-3">
          <Button variant="outline" className="rounded-full">
            <Download className="mr-2 h-4 w-4" />
            Ver documentos salvos ({total})
          </Button>
          <Button variant="ghost" className="rounded-full text-primary">
            <FolderDown className="mr-2 h-4 w-4" />
            Exportar direto para Minuta
          </Button>
        </div>

        <div className="mt-6 grid gap-3 md:grid-cols-2">
          {documents.map((doc) => (
            <div
              key={doc.id}
              className="flex items-center justify-between rounded-2xl border border-outline/40 bg-white/80 px-4 py-3"
            >
              <div className="flex items-center gap-3">
                <span className="rounded-2xl bg-primary/10 p-2 text-primary">
                  <FileText className="h-4 w-4" />
                </span>
                <div>
                  <p className="text-sm font-semibold text-foreground">{doc.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {formatFileSize(doc.file_size ?? doc.size ?? 0)} • {doc.status}
                  </p>
                </div>
              </div>
              <Button variant="ghost" size="sm" className="rounded-full text-primary">
                Detalhes
              </Button>
            </div>
          ))}
        </div>
      </section>

      {/* URL Dialog */}
      <Dialog open={urlDialogOpen} onOpenChange={setUrlDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <LinkIcon className="h-5 w-5 text-primary" />
              Importar de URL
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="url">URL do documento ou site</Label>
              <Input
                id="url"
                placeholder="https://exemplo.com/documento.pdf"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleUrlSubmit()}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setUrlDialogOpen(false)}>
              Cancelar
            </Button>
            <Button onClick={handleUrlSubmit}>Importar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Text Dialog */}
      <Dialog open={textDialogOpen} onOpenChange={setTextDialogOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Type className="h-5 w-5 text-primary" />
              Inserir Texto Manualmente
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="text-title">Título do documento</Label>
              <Input
                id="text-title"
                placeholder="Ex: Resumo da audiência"
                value={textTitle}
                onChange={(e) => setTextTitle(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="text-content">Conteúdo</Label>
              <textarea
                id="text-content"
                className="w-full min-h-[200px] rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                placeholder="Cole ou digite o texto aqui..."
                value={textContent}
                onChange={(e) => setTextContent(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTextDialogOpen(false)}>
              Cancelar
            </Button>
            <Button onClick={handleTextSubmit}>Adicionar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
