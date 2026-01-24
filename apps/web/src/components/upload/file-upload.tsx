'use client';

import { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { useDocumentStore } from '@/stores';
import { Button } from '@/components/ui/button';
import { Upload, FileText, X } from 'lucide-react';
import { formatFileSize } from '@/lib/utils';
import { useUploadLimits } from '@/lib/use-upload-limits';
import { toast } from 'sonner';

interface FileUploadProps {
  onUploadComplete?: (documentId: string) => void;
  acceptedFormats?: string[];
}

export function FileUpload({
  onUploadComplete,
  acceptedFormats = ['.pdf', '.docx', '.doc', '.txt', '.odt'],
}: FileUploadProps) {
  const { uploadDocument, isUploading } = useDocumentStore();
  const { maxUploadBytes, maxUploadLabel } = useUploadLimits();

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      for (const file of acceptedFiles) {
        try {
          toast.info(`Enviando ${file.name}...`);
          const document = await uploadDocument(file);
          toast.success(`${file.name} enviado com sucesso!`);
          onUploadComplete?.(document.id);
        } catch (error) {
          // Erro já tratado pelo interceptor
        }
      }
    },
    [uploadDocument, onUploadComplete]
  );

  const { getRootProps, getInputProps, isDragActive, acceptedFiles, fileRejections } = useDropzone({
    onDrop,
    accept: acceptedFormats.reduce((acc, format) => ({ ...acc, [format]: [] }), {}),
    maxSize: maxUploadBytes,
    disabled: isUploading,
  });

  return (
    <div className="space-y-4">
      <div
        {...getRootProps()}
        className={`
          flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-12
          transition-colors cursor-pointer
          ${isDragActive ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/50'}
          ${isUploading ? 'opacity-50 cursor-not-allowed' : ''}
        `}
      >
        <input {...getInputProps()} />
        <Upload className="h-12 w-12 text-muted-foreground mb-4" />
        {isDragActive ? (
          <p className="text-sm text-primary">Solte os arquivos aqui...</p>
        ) : (
          <>
            <p className="text-sm text-muted-foreground mb-2">
              Arraste arquivos aqui ou clique para selecionar
            </p>
            <p className="text-xs text-muted-foreground">
              Formatos: {acceptedFormats.join(', ')} (máx. {maxUploadLabel})
            </p>
          </>
        )}
      </div>

      {/* Arquivos Aceitos */}
      {acceptedFiles.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium">Arquivos Selecionados:</h4>
          {acceptedFiles.map((file, index) => (
            <div
              key={index}
              className="flex items-center justify-between rounded-lg border p-3"
            >
              <div className="flex items-center space-x-3">
                <FileText className="h-5 w-5 text-muted-foreground" />
                <div>
                  <p className="text-sm font-medium">{file.name}</p>
                  <p className="text-xs text-muted-foreground">{formatFileSize(file.size)}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Arquivos Rejeitados */}
      {fileRejections.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-destructive">Arquivos Rejeitados:</h4>
          {fileRejections.map(({ file, errors }, index) => (
            <div key={index} className="rounded-lg border border-destructive p-3">
              <p className="text-sm font-medium">{file.name}</p>
              {errors.map((error) => (
                <p key={error.code} className="text-xs text-destructive">
                  {error.message}
                </p>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
