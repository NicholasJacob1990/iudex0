'use client';

import { useEffect } from 'react';
import { useDocumentStore } from '@/stores';
import { DocumentsDropzone } from '@/components/dashboard';
import { FileText, Eye, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { formatDate, formatFileSize } from '@/lib/utils';
import { toast } from 'sonner';

export default function DocumentsPage() {
  const { documents, fetchDocuments, deleteDocument } = useDocumentStore();

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Deseja realmente excluir "${name}"?`)) return;

    try {
      await deleteDocument(id);
      toast.success('Documento excluído com sucesso!');
    } catch (error) {
      // tratado no interceptor
    }
  };

  return (
    <div className="space-y-8">
      <div className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft">
        <p className="text-xs font-semibold uppercase text-muted-foreground">Documentos</p>
        <h1 className="font-display text-3xl text-foreground">Organize seus arquivos jurídicos.</h1>
        <p className="text-sm text-muted-foreground">
          Centralize minutas, anexos, mídias e gravações com OCR automático e unificação por pastas.
        </p>
      </div>

      <DocumentsDropzone />

      <section className="rounded-3xl border border-white/70 bg-white/95 p-5 shadow-soft">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-display text-xl text-foreground">Seus documentos</h2>
            <p className="text-sm text-muted-foreground">{documents.length} itens carregados</p>
          </div>
        </div>

        {documents.length === 0 ? (
          <p className="py-12 text-center text-muted-foreground">
            Nenhum documento ainda. Envie seu primeiro arquivo.
          </p>
        ) : (
          <div className="mt-4 space-y-3">
            {documents.map((doc) => (
              <div
                key={doc.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-outline/40 bg-sand/60 px-4 py-3"
              >
                <div className="flex items-center gap-3">
                  <FileText className="h-5 w-5 text-primary" />
                  <div>
                    <p className="font-semibold text-foreground">{doc.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatFileSize(doc.file_size)} • {formatDate(doc.created_at)}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 text-xs font-semibold">
                  <span className="chip bg-white text-foreground">{doc.status}</span>
                  <Button variant="ghost" size="icon" className="rounded-full">
                    <Eye className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="rounded-full text-destructive"
                    onClick={() => handleDelete(doc.id, doc.name)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

