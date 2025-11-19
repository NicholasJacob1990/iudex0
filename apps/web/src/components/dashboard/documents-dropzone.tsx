'use client';

import { ChangeEvent } from 'react';
import { UploadCloud, FileText, Download, FolderDown } from 'lucide-react';
import { useDocumentStore } from '@/stores';
import { documentUploads } from '@/data/mock';
import { formatFileSize } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';

export function DocumentsDropzone() {
  const { uploadDocument, isUploading } = useDocumentStore();

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

  return (
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

      <div className="mt-5 flex flex-wrap items-center justify-center gap-3 text-xs font-semibold uppercase text-muted-foreground">
        <span className="chip bg-sand text-foreground">Arquivos</span>
        <span className="chip bg-sand text-foreground">Google Drive</span>
        <span className="chip bg-sand text-foreground">Transcrever</span>
        <span className="chip bg-sand text-foreground">URL</span>
        <span className="chip bg-sand text-foreground">Inserir texto</span>
      </div>

      <label className="mt-6 flex cursor-pointer flex-col items-center justify-center rounded-3xl border-2 border-dashed border-outline/60 bg-sand/60 py-10 text-center transition hover:border-primary hover:bg-primary/5">
        <input type="file" className="hidden" onChange={handleUpload} disabled={isUploading} />
        <p className="text-sm font-semibold text-primary">
          {isUploading ? 'Processando...' : 'Clique ou arraste arquivos'}
        </p>
        <p className="text-xs text-muted-foreground">PDF, DOCX, ZIP, HTML, imagens até 500MB</p>
      </label>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <Button variant="outline" className="rounded-full">
          <Download className="mr-2 h-4 w-4" />
          Ver documentos salvos (112)
        </Button>
        <Button variant="ghost" className="rounded-full text-primary">
          <FolderDown className="mr-2 h-4 w-4" />
          Exportar direto para Minuta
        </Button>
      </div>

      <div className="mt-6 grid gap-3 md:grid-cols-2">
        {documentUploads.map((doc) => (
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
                  {doc.size ?? formatFileSize(0)} • {doc.status}
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
  );
}

