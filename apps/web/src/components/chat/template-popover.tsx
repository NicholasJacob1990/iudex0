'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { FileText } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useChatStore } from '@/stores/chat-store';
import apiClient from '@/lib/api-client';
import { toast } from 'sonner';

export const TemplatePopover = React.memo(function TemplatePopover() {
  const {
    useTemplates,
    templateFilters,
    templateId,
    templateName,
    setTemplateId,
    setTemplateName,
    setUseTemplates,
    setTemplateFilters,
  } = useChatStore();

  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<'structure' | 'base'>('structure');
  const [query, setQuery] = useState('');
  const [templates, setTemplates] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const filteredTemplates = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return templates;
    return templates.filter((item) => {
      const name = String(item?.name || item?.title || '').toLowerCase();
      const docType = String(item?.document_type || '').toLowerCase();
      return name.includes(q) || docType.includes(q);
    });
  }, [query, templates]);

  const updateFilters = (patch: Record<string, any>) => {
    setTemplateFilters({ ...(templateFilters || {}), ...patch });
  };

  useEffect(() => {
    if (!open) return;
    if (templates.length > 0) return;
    setLoading(true);
    apiClient
      .getTemplates(0, 50)
      .then((data) => setTemplates(data.templates || []))
      .catch(() => setTemplates([]))
      .finally(() => setLoading(false));
  }, [open, templates.length]);

  const handleSelect = (model: any) => {
    if (!model?.id) return;
    setTemplateId(model.id);
    setTemplateName(model.name || model.title || null);
    setOpen(false);
    toast.success(`Template "${model.name || model.title || 'selecionado'}" aplicado.`);
  };

  const handleClear = () => {
    setTemplateId(null);
    setTemplateName(null);
    toast.info('Template removido.');
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          title={templateName ? `Template: ${templateName}` : 'Selecionar template'}
          className={cn(
            'h-7 w-7 rounded-full transition-colors',
            templateId
              ? 'text-emerald-600 bg-emerald-500/10'
              : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'
          )}
        >
          <FileText className="h-3.5 w-3.5" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-3 space-y-3" align="start">
        <div className="flex items-center rounded-full bg-slate-100 p-1 text-[10px] font-semibold text-slate-500">
          <button
            type="button"
            onClick={() => setTab('structure')}
            className={cn(
              'flex-1 rounded-full px-2 py-1 transition',
              tab === 'structure'
                ? 'bg-white text-slate-700 shadow-sm'
                : 'hover:text-slate-700'
            )}
          >
            Estrutura
          </button>
          <button
            type="button"
            onClick={() => setTab('base')}
            className={cn(
              'flex-1 rounded-full px-2 py-1 transition',
              tab === 'base'
                ? 'bg-white text-slate-700 shadow-sm'
                : 'hover:text-slate-700'
            )}
          >
            Base / RAG
          </button>
        </div>

        {tab === 'structure' ? (
          <>
            <div className="space-y-1">
              <Label className="text-xs font-semibold text-muted-foreground">
                Buscar template
              </Label>
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Digite o nome do template"
                className="h-8"
              />
            </div>

            <div className="max-h-56 space-y-1 overflow-y-auto">
              {loading ? (
                <p className="text-xs text-muted-foreground">Carregando templates...</p>
              ) : filteredTemplates.length === 0 ? (
                <p className="text-xs text-muted-foreground">Nenhum template encontrado.</p>
              ) : (
                filteredTemplates.map((item) => {
                  const isActive = templateId === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => handleSelect(item)}
                      className={cn(
                        'flex w-full items-center justify-between rounded-lg border px-2 py-2 text-left text-xs transition',
                        isActive
                          ? 'border-emerald-200 bg-emerald-500/10 text-emerald-700'
                          : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                      )}
                    >
                      <span className="truncate font-semibold">
                        {item.name || item.title || 'Template'}
                      </span>
                      <span className="ml-2 text-[10px] text-muted-foreground">
                        {item.document_type || 'Modelo'}
                      </span>
                    </button>
                  );
                })
              )}
            </div>

            <div className="flex items-center justify-between">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleClear}
                disabled={!templateId}
              >
                Limpar
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  window.location.href = '/models';
                }}
              >
                Abrir biblioteca
              </Button>
            </div>
          </>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-2 py-2">
              <div>
                <Label className="text-xs font-semibold text-slate-600">
                  Usar modelos no RAG
                </Label>
                <p className="text-[10px] text-muted-foreground">
                  Inclui pecas modelo na busca contextual.
                </p>
              </div>
              <Switch checked={useTemplates} onCheckedChange={setUseTemplates} />
            </div>

            <div className={cn('grid gap-2', !useTemplates && 'opacity-50')}>
              <Input
                value={templateFilters?.tipoPeca || ''}
                onChange={(e) => updateFilters({ tipoPeca: e.target.value })}
                placeholder="Tipo (ex: peticao_inicial)"
                className="h-8"
                disabled={!useTemplates}
              />
              <div className="grid grid-cols-2 gap-2">
                <Input
                  value={templateFilters?.area || ''}
                  onChange={(e) => updateFilters({ area: e.target.value })}
                  placeholder="Area"
                  className="h-8"
                  disabled={!useTemplates}
                />
                <Input
                  value={templateFilters?.rito || ''}
                  onChange={(e) => updateFilters({ rito: e.target.value })}
                  placeholder="Rito"
                  className="h-8"
                  disabled={!useTemplates}
                />
              </div>
              <div className="flex items-center gap-2 text-[11px] text-slate-600">
                <Checkbox
                  checked={!!templateFilters?.apenasClauseBank}
                  onCheckedChange={(checked) =>
                    updateFilters({ apenasClauseBank: Boolean(checked) })
                  }
                  disabled={!useTemplates}
                />
                Apenas Clause Bank
              </div>
            </div>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
});
