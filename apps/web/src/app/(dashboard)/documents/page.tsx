'use client';

import { useEffect, useState } from 'react';
import { useDocumentStore } from '@/stores';
import { DocumentsDropzone, DocumentViewerDialog, DocumentActionsMenu } from '@/components/dashboard';
import { FileText, Eye, Trash2, Sparkles, BookmarkPlus, Mic, Podcast, Network } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { formatDate, formatFileSize } from '@/lib/utils';
import { toast } from 'sonner';
import apiClient from '@/lib/api-client';
import { AnimatedContainer } from '@/components/ui/animated-container';

export default function DocumentsPage() {
  const { documents, fetchDocuments, deleteDocument } = useDocumentStore();
  const [selectedDoc, setSelectedDoc] = useState<any>(null);
  const [viewerOpen, setViewerOpen] = useState(false);
  const [autoClean, setAutoClean] = useState(true);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [summaryDocName, setSummaryDocName] = useState('');
  const [summaryContent, setSummaryContent] = useState('');
  const [summaryLoading, setSummaryLoading] = useState(false);

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

  const handleExpand = (doc: any) => {
    setSelectedDoc(null);
    apiClient
      .getDocument(doc.id)
      .then((fullDoc) => {
        setSelectedDoc(fullDoc);
        setViewerOpen(true);
      })
      .catch(() => {
        toast.error('Não foi possível carregar o documento.');
      });
  };

  const handleSummarize = (doc: any) => {
    setSummaryDocName(doc.name);
    setSummaryContent('');
    setSummaryLoading(true);
    setSummaryOpen(true);
    apiClient
      .getDocumentSummary(doc.id)
      .then((result) => {
        const summary = String(result?.summary || '').trim();
        setSummaryContent(summary || 'Resumo indisponível para este documento.');
      })
      .catch(() => {
        setSummaryOpen(false);
        toast.error('Não foi possível gerar o resumo.');
      })
      .finally(() => {
        setSummaryLoading(false);
      });
  };

  const handleSaveToLibrary = (doc: any) => {
    toast.info(`Salvando "${doc.name}" na biblioteca...`);
    apiClient
      .getDocument(doc.id)
      .then((fullDoc) => {
        const text = String(fullDoc?.extracted_text || fullDoc?.content || '').trim();
        const tokenCount = text ? Math.ceil(text.length / 4) : 0;
        const description = text ? text.slice(0, 800) : undefined;
        return apiClient.createLibraryItem({
          type: 'DOCUMENT',
          name: fullDoc?.name || doc.name,
          description,
          tags: Array.isArray(fullDoc?.tags) ? fullDoc.tags : [],
          folder_id: fullDoc?.folder_id,
          resource_id: doc.id,
          token_count: tokenCount,
        });
      })
      .then(() => {
        toast.success('Documento salvo na biblioteca!');
      })
      .catch(() => {
        toast.error('Não foi possível salvar na biblioteca.');
      });
  };

  const handleBulkAction = (action: string) => {
    toast.info(`Selecione um documento e use "${action}" na lista abaixo.`);
  };

  return (
    <div className="space-y-8">
      <AnimatedContainer>
      <div className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft">
        <p className="text-xs font-semibold uppercase text-muted-foreground">Documentos</p>
        <h1 className="font-display text-3xl text-foreground">Organize seus arquivos jurídicos.</h1>
        <p className="text-sm text-muted-foreground">
          Centralize minutas, anexos, mídias e gravações com OCR automático e unificação por pastas.
        </p>
      </div>
      </AnimatedContainer>

      <DocumentsDropzone onOpenDocument={handleExpand} />

      {documents.length > 0 && (
        <div id="documents-list" className="rounded-3xl border border-white/70 bg-white/95 p-5 shadow-soft space-y-4">
          {/* Menu Controls */}
          <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-outline/20">
            <div className="flex items-center gap-4">
              <div className="flex items-center space-x-2">
                <Switch id="auto-clean" checked={autoClean} onCheckedChange={setAutoClean} />
                <Label htmlFor="auto-clean" className="text-xs font-medium cursor-pointer">
                  Limpeza automática
                </Label>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                className="rounded-full gap-2 text-xs"
                onClick={() => handleBulkAction('Resumir todos')}
              >
                <Sparkles className="h-3 w-3" />
                Resumir
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="rounded-full gap-2 text-xs"
                onClick={() => handleBulkAction('Resumo em Áudio')}
              >
                <Mic className="h-3 w-3" />
                Áudio
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="rounded-full gap-2 text-xs"
                onClick={() => handleBulkAction('Gerar Podcast')}
              >
                <Podcast className="h-3 w-3" />
                Podcast
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="rounded-full gap-2 text-xs"
                onClick={() => handleBulkAction('Criar Diagrama')}
              >
                <Network className="h-3 w-3" />
                Diagrama
              </Button>
              <Button
                size="sm"
                className="rounded-full gap-2 text-xs bg-primary text-primary-foreground"
                onClick={() => handleBulkAction('Salvar na biblioteca')}
              >
                <BookmarkPlus className="h-3 w-3" />
                Salvar
              </Button>
            </div>
          </div>

          {/* Documents List */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="font-display text-xl text-foreground">Seus documentos</h2>
                <p className="text-sm text-muted-foreground">{documents.length} itens carregados</p>
              </div>
            </div>

            <div className="space-y-3">
              {documents.map((doc) => (
                <div
                  key={doc.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-outline/40 bg-sand/60 px-4 py-3"
                >
                  <div className="flex items-center gap-3">
                    <FileText className="h-5 w-5 text-primary" />
                    <div>
                      <p className="font-semibold text-foreground">{doc.name}</p>
                      <div className="flex items-center gap-3 text-xs text-muted-foreground">
                        <span>{formatFileSize(doc.file_size)}</span>
                        <span>•</span>
                        <span>{formatDate(doc.created_at)}</span>
                        <span>•</span>
                        <span className="text-primary font-semibold">~1,200 tokens</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="chip bg-white text-foreground text-xs">{doc.status}</span>
                    <Button
                      variant="outline"
                      size="sm"
                      className="rounded-full gap-1 text-xs"
                      onClick={() => handleExpand(doc)}
                    >
                      <Eye className="h-3 w-3" />
                      Expandir
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="rounded-full gap-1 text-xs"
                      onClick={() => handleSummarize(doc)}
                    >
                      <Sparkles className="h-3 w-3" />
                      Resumir
                    </Button>
                    <DocumentActionsMenu documentId={doc.id} documentName={doc.name} />
                    <Button
                      variant="outline"
                      size="sm"
                      className="rounded-full gap-1 text-xs"
                      onClick={() => handleSaveToLibrary(doc)}
                    >
                      <BookmarkPlus className="h-3 w-3" />
                      Salvar
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
          </div>
        </div>
      )}

      {selectedDoc && (
        <DocumentViewerDialog
          open={viewerOpen}
          onOpenChange={setViewerOpen}
          document={selectedDoc}
        />
      )}

      <Dialog open={summaryOpen} onOpenChange={setSummaryOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Resumo de {summaryDocName}</DialogTitle>
          </DialogHeader>
          <div className="max-h-[60vh] overflow-y-auto whitespace-pre-wrap text-sm text-foreground">
            {summaryLoading ? 'Gerando resumo...' : summaryContent}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
