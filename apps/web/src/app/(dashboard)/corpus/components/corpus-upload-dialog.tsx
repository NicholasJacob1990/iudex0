'use client';

import { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, FileText, X, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import type { CorpusScope } from '../hooks/use-corpus';
import { formatFileSize } from '@/lib/utils';
import { toast } from 'sonner';
import { useAuthStore } from '@/stores/auth-store';
import apiClient from '@/lib/api-client';

interface CorpusUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultScope?: CorpusScope;
}

const ACCEPTED_FORMATS = ['.pdf', '.docx', '.doc', '.txt', '.odt', '.rtf', '.csv', '.xlsx'];
const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50 MB

export function CorpusUploadDialog({
  open,
  onOpenChange,
  defaultScope = 'private',
}: CorpusUploadDialogProps) {
  const { user } = useAuthStore();
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [scope, setScope] = useState<CorpusScope>(defaultScope);
  const [collection, setCollection] = useState<string>('');
  const [groupIds, setGroupIds] = useState<string[]>([]);
  const [myTeams, setMyTeams] = useState<Array<{ id: string; name: string }>>([]);
  const [teamsLoading, setTeamsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (!user?.organization_id) return;
    if (myTeams.length > 0) return;

    setTeamsLoading(true);
    apiClient
      .getMyOrgTeams()
      .then((res) => {
        const teams = Array.isArray(res) ? res : [];
        setMyTeams(
          teams
            .map((t: any) => ({
              id: String(t?.id || '').trim(),
              name: String(t?.name || '').trim(),
            }))
            .filter((t: any) => t.id && t.name)
        );
      })
      .catch(() => setMyTeams([]))
      .finally(() => setTeamsLoading(false));
  }, [open, user?.organization_id, myTeams.length]);

  useEffect(() => {
    if (scope !== 'group' && groupIds.length > 0) {
      setGroupIds([]);
    }
  }, [scope, groupIds.length]);

  const onDrop = useCallback((accepted: File[]) => {
    setSelectedFiles((prev) => [...prev, ...accepted]);
  }, []);

  const { getRootProps, getInputProps, isDragActive, fileRejections } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/msword': ['.doc'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'text/plain': ['.txt'],
      'application/vnd.oasis.opendocument.text': ['.odt'],
      'application/rtf': ['.rtf'],
      'text/csv': ['.csv'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
    },
    maxSize: MAX_FILE_SIZE,
    disabled: isSubmitting,
  });

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async () => {
    if (selectedFiles.length === 0) {
      toast.error('Selecione ao menos um arquivo.');
      return;
    }
    if (scope === 'group' && groupIds.length === 0) {
      toast.error('Selecione ao menos um departamento.');
      return;
    }

    setIsSubmitting(true);
    const uploadedIds: string[] = [];
    let uploadFailCount = 0;

    try {
      for (const file of selectedFiles) {
        try {
          const uploaded = await apiClient.uploadDocument(file, {
            source: 'corpus_upload_dialog',
          });
          const uploadedId = String(uploaded?.id || '').trim();
          if (uploadedId) {
            uploadedIds.push(uploadedId);
          } else {
            uploadFailCount += 1;
          }
        } catch {
          uploadFailCount += 1;
        }
      }

      if (uploadedIds.length === 0) {
        throw new Error('Nenhum documento foi enviado com sucesso.');
      }

      await apiClient.ingestCorpusDocuments({
        document_ids: uploadedIds,
        scope,
        collection: collection || 'local',
        group_ids: scope === 'group' ? groupIds : undefined,
      });

      const queuedMessage =
        uploadedIds.length > 0
          ? `${uploadedIds.length} documento(s) enviado(s) para ingestão.`
          : 'Ingestão enviada.';
      toast.success(queuedMessage);
      if (uploadFailCount > 0) {
        toast.error(`${uploadFailCount} arquivo(s) falharam no upload.`);
      }
    } catch {
      toast.error('Não foi possível enviar para o Corpus.');
      if (uploadedIds.length > 0) {
        toast.info(
          `${uploadedIds.length} arquivo(s) foram enviados em Documentos, mas falharam na ingestão.`
        );
      }
    }

    setIsSubmitting(false);

    setSelectedFiles([]);
    setCollection('');
    setGroupIds([]);
    onOpenChange(false);
  };

  const handleClose = (open: boolean) => {
    if (!isSubmitting) {
      if (!open) {
        setSelectedFiles([]);
        setCollection('');
        setGroupIds([]);
      }
      onOpenChange(open);
    }
  };

  const toggleGroup = (id: string) => {
    const gid = String(id || '').trim();
    if (!gid) return;
    setGroupIds((prev) => (prev.includes(gid) ? prev.filter((g) => g !== gid) : [...prev, gid]));
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Enviar documentos ao Corpus</DialogTitle>
          <DialogDescription>
            Arraste arquivos ou selecione para ingestao na base de conhecimento.
          </DialogDescription>
        </DialogHeader>

        {/* Dropzone */}
        <div
          {...getRootProps()}
          className={`
            flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-8
            transition-colors cursor-pointer
            ${isDragActive ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/50'}
            ${isSubmitting ? 'opacity-50 cursor-not-allowed' : ''}
          `}
        >
          <input {...getInputProps()} />
          <Upload className="h-10 w-10 text-muted-foreground mb-3" />
          {isDragActive ? (
            <p className="text-sm text-primary">Solte os arquivos aqui...</p>
          ) : (
            <>
              <p className="text-sm text-muted-foreground mb-1">
                Arraste arquivos aqui ou clique para selecionar
              </p>
              <p className="text-[10px] text-muted-foreground">
                Formatos: {ACCEPTED_FORMATS.join(', ')} (max. {formatFileSize(MAX_FILE_SIZE)})
              </p>
            </>
          )}
        </div>

        {/* File Rejections */}
        {fileRejections.length > 0 && (
          <div className="space-y-1">
            {fileRejections.map(({ file, errors }, i) => (
              <p key={i} className="text-xs text-destructive">
                {file.name}: {errors.map((e) => e.message).join(', ')}
              </p>
            ))}
          </div>
        )}

        {/* Selected Files */}
        {selectedFiles.length > 0 && (
          <div className="space-y-2 max-h-40 overflow-y-auto">
            {selectedFiles.map((file, i) => (
              <div
                key={`${file.name}-${i}`}
                className="flex items-center justify-between rounded-lg border px-3 py-2"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <FileText className="h-4 w-4 text-primary shrink-0" />
                  <div className="min-w-0">
                    <p className="text-xs font-medium truncate">{file.name}</p>
                    <p className="text-[10px] text-muted-foreground">{formatFileSize(file.size)}</p>
                  </div>
                </div>
                <button
                  onClick={() => removeFile(i)}
                  className="ml-2 rounded-full p-1 hover:bg-muted"
                  disabled={isSubmitting}
                >
                  <X className="h-3 w-3 text-muted-foreground" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Options */}
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label className="text-xs">Escopo</Label>
            <Select value={scope} onValueChange={(v) => setScope(v as CorpusScope)}>
              <SelectTrigger className="rounded-xl">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="private">Privado (escritorio)</SelectItem>
                {user?.organization_id && <SelectItem value="group">Departamento</SelectItem>}
                <SelectItem value="local">Local (temporario, 7 dias)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label className="text-xs">Colecao (opcional)</Label>
            <Select value={collection} onValueChange={setCollection}>
              <SelectTrigger className="rounded-xl">
                <SelectValue placeholder="Selecionar..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="lei">Legislacao</SelectItem>
                <SelectItem value="juris">Jurisprudencia</SelectItem>
                <SelectItem value="doutrina">Doutrina</SelectItem>
                <SelectItem value="pecas_modelo">Pecas Modelo</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {scope === 'group' && (
          <div className="space-y-2">
            <Label className="text-xs">Departamentos</Label>
            {teamsLoading ? (
              <p className="text-xs text-muted-foreground">Carregando...</p>
            ) : myTeams.length > 0 ? (
              <div className="max-h-40 overflow-y-auto rounded-xl border p-3 space-y-2">
                {myTeams.map((t) => (
                  <label key={t.id} className="flex items-center gap-2 text-sm cursor-pointer">
                    <Checkbox
                      checked={groupIds.includes(t.id)}
                      onCheckedChange={() => toggleGroup(t.id)}
                      className="h-4 w-4"
                    />
                    <span className="text-xs">{t.name}</span>
                  </label>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                Você não está em nenhum departamento.
              </p>
            )}
          </div>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            className="rounded-full"
            onClick={() => handleClose(false)}
            disabled={isSubmitting}
          >
            Cancelar
          </Button>
          <Button
            className="rounded-full gap-2"
            onClick={handleSubmit}
            disabled={isSubmitting || selectedFiles.length === 0}
          >
            {isSubmitting ? (
              <>Enviando...</>
            ) : (
              <>
                <CheckCircle2 className="h-4 w-4" />
                Enviar {selectedFiles.length > 0 ? `(${selectedFiles.length})` : ''}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
