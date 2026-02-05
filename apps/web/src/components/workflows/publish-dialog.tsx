'use client';

import React, { useState } from 'react';
import { Globe, Copy, Check, Link2, X, Loader2, Unlink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { apiClient } from '@/lib/api-client';
import { toast } from 'sonner';

interface PublishDialogProps {
  open: boolean;
  onClose: () => void;
  workflowId: string;
  workflowName: string;
  currentSlug?: string | null;
  onPublished?: (slug: string) => void;
  onUnpublished?: () => void;
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 60);
}

export function PublishDialog({
  open,
  onClose,
  workflowId,
  workflowName,
  currentSlug,
  onPublished,
  onUnpublished,
}: PublishDialogProps) {
  const [slug, setSlug] = useState(currentSlug || slugify(workflowName));
  const [requireAuth, setRequireAuth] = useState(true);
  const [publishing, setPublishing] = useState(false);
  const [unpublishing, setUnpublishing] = useState(false);
  const [published, setPublished] = useState(!!currentSlug);
  const [activeSlug, setActiveSlug] = useState(currentSlug || '');
  const [copied, setCopied] = useState(false);

  if (!open) return null;

  const appUrl = typeof window !== 'undefined'
    ? `${window.location.origin}/app/${activeSlug || slug}`
    : `/app/${activeSlug || slug}`;

  const handlePublish = async () => {
    setPublishing(true);
    try {
      const res = await apiClient.fetchWithAuth(`/workflows/${workflowId}/publish`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slug, require_auth: requireAuth }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Erro ao publicar');
      }
      const data = await res.json();
      setPublished(true);
      setActiveSlug(data.slug || slug);
      toast.success('Workflow publicado como app!');
      onPublished?.(data.slug || slug);
    } catch (err: any) {
      toast.error(err.message || 'Erro ao publicar');
    } finally {
      setPublishing(false);
    }
  };

  const handleUnpublish = async () => {
    setUnpublishing(true);
    try {
      const res = await apiClient.fetchWithAuth(`/workflows/${workflowId}/unpublish`, {
        method: 'POST',
      });
      if (!res.ok) {
        throw new Error('Erro ao despublicar');
      }
      setPublished(false);
      setActiveSlug('');
      toast.success('App despublicado');
      onUnpublished?.();
    } catch (err: any) {
      toast.error(err.message || 'Erro ao despublicar');
    } finally {
      setUnpublishing(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(appUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center">
      <div className="bg-white dark:bg-slate-900 rounded-xl shadow-xl w-full max-w-md p-5">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Globe className="h-5 w-5 text-emerald-500" />
            <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
              Publicar Workflow
            </h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4">
          {/* Slug input */}
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">
              URL do App
            </label>
            <div className="flex gap-2">
              <div className="flex-1 flex items-center gap-0 border rounded-md overflow-hidden dark:border-slate-700">
                <span className="px-2 py-1.5 bg-slate-50 dark:bg-slate-800 text-xs text-slate-400 border-r dark:border-slate-700 whitespace-nowrap">
                  /app/
                </span>
                <input
                  value={published ? activeSlug : slug}
                  onChange={(e) =>
                    setSlug(
                      e.target.value
                        .toLowerCase()
                        .replace(/[^a-z0-9-]/g, '-')
                    )
                  }
                  className="flex-1 px-2 py-1.5 text-sm bg-transparent outline-none dark:text-slate-200"
                  disabled={published}
                  placeholder="meu-workflow"
                />
              </div>
              {published && (
                <Button
                  size="icon"
                  variant="outline"
                  onClick={handleCopy}
                  className="shrink-0"
                  title="Copiar URL"
                >
                  {copied ? (
                    <Check className="h-3.5 w-3.5 text-emerald-500" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" />
                  )}
                </Button>
              )}
            </div>
          </div>

          {/* Auth toggle */}
          {!published && (
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-slate-700 dark:text-slate-300">
                  Requer autenticacao
                </p>
                <p className="text-[10px] text-slate-400">
                  Usuarios precisam fazer login para acessar
                </p>
              </div>
              <button
                onClick={() => setRequireAuth(!requireAuth)}
                className={`relative w-9 h-5 rounded-full transition-colors ${
                  requireAuth ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-600'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                    requireAuth ? 'translate-x-4' : ''
                  }`}
                />
              </button>
            </div>
          )}

          {/* Published status */}
          {published && (
            <div className="bg-emerald-50 dark:bg-emerald-950/50 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-1">
                <Link2 className="h-3.5 w-3.5 text-emerald-600" />
                <span className="text-xs font-medium text-emerald-700 dark:text-emerald-300">
                  Publicado
                </span>
              </div>
              <p className="text-xs text-emerald-600 dark:text-emerald-400 break-all">
                {appUrl}
              </p>
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-2 pt-2">
            <Button
              variant="outline"
              size="sm"
              className="flex-1"
              onClick={onClose}
            >
              Fechar
            </Button>
            {published ? (
              <Button
                size="sm"
                variant="outline"
                className="flex-1 border-red-300 text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950"
                onClick={handleUnpublish}
                disabled={unpublishing}
              >
                {unpublishing ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
                ) : (
                  <Unlink className="h-3.5 w-3.5 mr-1" />
                )}
                Despublicar
              </Button>
            ) : (
              <Button
                size="sm"
                className="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white"
                onClick={handlePublish}
                disabled={publishing || !slug}
              >
                {publishing ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
                ) : (
                  <Globe className="h-3.5 w-3.5 mr-1" />
                )}
                Publicar
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
