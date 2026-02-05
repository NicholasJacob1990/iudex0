'use client';

import React, { useState, useCallback } from 'react';
import { Upload, X, FileText, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useWorkflowStore } from '@/stores/workflow-store';
import { toast } from 'sonner';

interface EmbeddedFile {
  id: string;
  name: string;
  size: number;
  mime_type: string;
  uploaded_at?: string;
}

export function EmbeddedFilesPanel() {
  const store = useWorkflowStore();
  const [isOpen, setIsOpen] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [files, setFiles] = useState<EmbeddedFile[]>([]);
  const [loaded, setLoaded] = useState(false);

  const loadFiles = useCallback(async () => {
    if (!store.id || loaded) return;
    try {
      const resp = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/workflows/${store.id}/files`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
      });
      if (resp.ok) {
        const data = await resp.json();
        setFiles(data.files || []);
      }
    } catch {}
    setLoaded(true);
  }, [store.id, loaded]);

  const handleUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!store.id || !e.target.files?.length) return;
    setIsUploading(true);
    try {
      for (const file of Array.from(e.target.files)) {
        const formData = new FormData();
        formData.append('file', file);
        const resp = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/workflows/${store.id}/files`,
          {
            method: 'POST',
            headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
            body: formData,
          }
        );
        if (resp.ok) {
          const data = await resp.json();
          setFiles((prev) => [...prev, data.file]);
        } else {
          toast.error(`Erro ao enviar ${file.name}`);
        }
      }
      toast.success('Arquivos enviados');
    } catch {
      toast.error('Erro ao enviar arquivos');
    } finally {
      setIsUploading(false);
      e.target.value = '';
    }
  }, [store.id]);

  const handleRemove = useCallback(async (fileId: string) => {
    if (!store.id) return;
    try {
      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/workflows/${store.id}/files/${fileId}`,
        {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
        }
      );
      if (resp.ok) {
        setFiles((prev) => prev.filter((f) => f.id !== fileId));
        toast.success('Arquivo removido');
      }
    } catch {
      toast.error('Erro ao remover');
    }
  }, [store.id]);

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
  };

  if (!store.id) return null;

  return (
    <div className="relative">
      <Button
        variant="outline"
        size="sm"
        onClick={() => {
          setIsOpen(!isOpen);
          if (!loaded) loadFiles();
        }}
        className="gap-1.5 text-xs"
      >
        <Upload className="h-3.5 w-3.5" />
        Arquivos ({files.length}/50)
      </Button>

      {isOpen && (
        <div className="absolute top-full right-0 mt-2 w-80 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg shadow-xl z-50">
          <div className="p-3 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
            <h4 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
              Arquivos Embutidos
            </h4>
            <button onClick={() => setIsOpen(false)} className="text-slate-400 hover:text-slate-600">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="max-h-60 overflow-auto">
            {files.length === 0 && (
              <p className="text-xs text-slate-400 text-center py-4">
                Nenhum arquivo embutido. Arquivos ficam disponíveis para todos os prompts.
              </p>
            )}
            {files.map((f) => (
              <div key={f.id} className="flex items-center gap-2 px-3 py-2 hover:bg-slate-50 dark:hover:bg-slate-800 group">
                <FileText className="h-4 w-4 text-slate-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-slate-700 dark:text-slate-300 truncate">{f.name}</p>
                  <p className="text-[10px] text-slate-400">{formatSize(f.size)}</p>
                </div>
                <button
                  onClick={() => handleRemove(f.id)}
                  className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-600"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>

          <div className="p-3 border-t border-slate-100 dark:border-slate-800">
            <label className="flex items-center justify-center gap-2 w-full px-3 py-2 border-2 border-dashed border-slate-200 dark:border-slate-700 rounded-lg cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors">
              {isUploading ? (
                <Loader2 className="h-4 w-4 text-slate-400 animate-spin" />
              ) : (
                <Upload className="h-4 w-4 text-slate-400" />
              )}
              <span className="text-xs text-slate-500">
                {isUploading ? 'Enviando...' : 'Enviar arquivos'}
              </span>
              <input
                type="file"
                multiple
                onChange={handleUpload}
                disabled={isUploading || files.length >= 50}
                className="hidden"
              />
            </label>
          </div>
        </div>
      )}
    </div>
  );
}
