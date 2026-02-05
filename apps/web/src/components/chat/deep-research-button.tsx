'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Brain, ChevronDown, Info, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chat-store';

interface DeepResearchButtonProps {
  className?: string;
}

export function DeepResearchButton({ className }: DeepResearchButtonProps) {
  const [open, setOpen] = useState(false);

  const {
    denseResearch,
    setDenseResearch,
    selectedModels,
    deepResearchMode,
    setDeepResearchMode,
    deepResearchProvider,
    setDeepResearchProvider,
    deepResearchModel,
    setDeepResearchModel,
    deepResearchEffort,
    setDeepResearchEffort,
    deepResearchSearchFocus,
    setDeepResearchSearchFocus,
    deepResearchDomainFilter,
    setDeepResearchDomainFilter,
    deepResearchSearchAfterDate,
    setDeepResearchSearchAfterDate,
    deepResearchSearchBeforeDate,
    setDeepResearchSearchBeforeDate,
    deepResearchLastUpdatedAfter,
    setDeepResearchLastUpdatedAfter,
    deepResearchLastUpdatedBefore,
    setDeepResearchLastUpdatedBefore,
    deepResearchCountry,
    setDeepResearchCountry,
    deepResearchLatitude,
    setDeepResearchLatitude,
    deepResearchLongitude,
    setDeepResearchLongitude,
    hardResearchProviders,
    toggleHardResearchProvider,
    setAllHardResearchProviders,
  } = useChatStore();

  // Verifica se modelo sonar-deep-research está selecionado
  const primaryModelId = selectedModels.length === 1 ? String(selectedModels[0] || '').toLowerCase() : '';
  const isPerplexityDeepSelected = primaryModelId === 'sonar-deep-research';

  // Parâmetros Perplexity: APENAS quando provider é Perplexity OU modelo é sonar-deep-research
  const enableDeepResearchParams = isPerplexityDeepSelected || (denseResearch && deepResearchProvider === 'perplexity');

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          title="Pesquisa profunda"
          className={cn(
            'h-7 gap-1 rounded-full px-2 text-[10px] font-medium transition-colors',
            denseResearch
              ? 'text-emerald-600 bg-emerald-500/10 hover:bg-emerald-500/20'
              : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700',
            className
          )}
        >
          <Search className="h-3.5 w-3.5" />
          <ChevronDown className="h-3 w-3 opacity-50" />
        </Button>
      </PopoverTrigger>

      <PopoverContent
        className="w-80 max-h-[70vh] overflow-y-auto p-4 pr-3 space-y-4 overscroll-contain"
        align="start"
        sideOffset={8}
        collisionPadding={12}
      >
        <div className="space-y-4">
          {/* Header with toggle */}
          <div className="flex items-center justify-between">
            <div className="flex flex-col gap-0.5">
              <div className="flex items-center gap-2">
                <Label className="text-sm font-medium">Deep Research</Label>
                <span className="px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-700 text-[9px] font-bold">
                  ALPHA
                </span>
              </div>
              <span className="text-xs text-muted-foreground">
                Agente Autonomo (Lento, +Custos)
              </span>
            </div>
            <Switch checked={denseResearch} onCheckedChange={setDenseResearch} />
          </div>

          {/* Mode Selector: Standard / Hard */}
          {denseResearch && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Label className="text-xs font-medium">Modo</Label>
              </div>
              <div className="flex gap-1">
                <button
                  type="button"
                  disabled={!denseResearch}
                  onClick={() => setDeepResearchMode('standard')}
                  className={cn(
                    'rounded-full border px-3 py-1 text-[10px] font-semibold transition-colors',
                    deepResearchMode === 'standard'
                      ? 'border-indigo-300 bg-indigo-500/15 text-indigo-700'
                      : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700',
                    !denseResearch && 'pointer-events-none'
                  )}
                >
                  Standard
                </button>
                <button
                  type="button"
                  disabled={!denseResearch}
                  onClick={() => setDeepResearchMode('hard')}
                  className={cn(
                    'rounded-full border px-3 py-1 text-[10px] font-semibold transition-colors',
                    deepResearchMode === 'hard'
                      ? 'border-red-300 bg-red-500/15 text-red-700'
                      : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700',
                    !denseResearch && 'pointer-events-none'
                  )}
                >
                  Hard (Multi-Provider)
                </button>
              </div>

              {/* Hard mode info box */}
              {deepResearchMode === 'hard' && (
                <div className="rounded-lg border border-red-200/50 bg-red-50/50 p-2.5">
                  <div className="flex items-start gap-2">
                    <Info className="h-3.5 w-3.5 text-red-500 mt-0.5 flex-shrink-0" />
                    <p className="text-[10px] text-red-700/80 leading-relaxed">
                      Claude orquestra multiplos agentes de pesquisa (Gemini, Perplexity, OpenAI)
                      em paralelo, combinando resultados com RAG local e global.
                    </p>
                  </div>
                </div>
              )}

              {/* Hard Mode Sources */}
              {deepResearchMode === 'hard' && (
                <div className="space-y-2 rounded-lg border border-red-200/50 bg-red-500/5 p-3">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs font-medium text-red-800">
                      Fontes da Pesquisa
                    </Label>
                    <div className="flex gap-1.5">
                      <button
                        type="button"
                        onClick={() => setAllHardResearchProviders(true)}
                        className="text-[10px] text-slate-500 hover:text-slate-700 underline"
                      >
                        Todas
                      </button>
                      <button
                        type="button"
                        onClick={() => setAllHardResearchProviders(false)}
                        className="text-[10px] text-slate-500 hover:text-slate-700 underline"
                      >
                        Nenhuma
                      </button>
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    {[
                      { id: 'gemini', label: 'Gemini Deep Research', desc: 'Google - busca web profunda', icon: '\u2726' },
                      { id: 'perplexity', label: 'Perplexity Sonar', desc: 'Web + Academic search', icon: '\u229B' },
                      { id: 'openai', label: 'ChatGPT Deep Research', desc: 'OpenAI - analise profunda', icon: '\u25C9' },
                      { id: 'rag_global', label: 'RAG Global', desc: 'Legislacao, jurisprudencia, sumulas', icon: '\u2696' },
                      { id: 'rag_local', label: 'RAG Local', desc: 'Documentos do caso/processo', icon: '\u25A4' },
                    ].map((source) => (
                      <label
                        key={source.id}
                        className={cn(
                          'flex items-center gap-2.5 rounded-md border px-2.5 py-1.5 cursor-pointer transition-colors',
                          hardResearchProviders[source.id] !== false
                            ? 'border-red-300/50 bg-red-500/10 text-slate-800'
                            : 'border-slate-200 bg-white text-slate-400'
                        )}
                      >
                        <input
                          type="checkbox"
                          checked={hardResearchProviders[source.id] !== false}
                          onChange={() => toggleHardResearchProvider(source.id)}
                          className="h-3.5 w-3.5 rounded border-slate-300 text-red-600 focus:ring-red-500"
                        />
                        <span className="text-sm">{source.icon}</span>
                        <div className="flex-1 min-w-0">
                          <span className="text-xs font-medium">{source.label}</span>
                          <span className="text-[10px] text-muted-foreground ml-1.5">{source.desc}</span>
                        </div>
                      </label>
                    ))}
                  </div>

                  <p className="text-[10px] text-red-600/60 mt-1">
                    Mais fontes = pesquisa mais completa, porem mais lenta e custosa
                  </p>
                </div>
              )}

              {/* Standard Mode - Provider Selector */}
              {deepResearchMode === 'standard' && (
                <div className={cn('space-y-2', !denseResearch && 'opacity-50')}>
                  <div className="flex items-center gap-2">
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Label className="text-sm font-medium cursor-help">
                            Provider
                          </Label>
                        </TooltipTrigger>
                        <TooltipContent side="right" className="max-w-xs text-xs">
                          Escolhe qual provedor executa o Deep Research. Auto usa o melhor disponivel;
                          Perplexity usa Sonar Deep Research; Google usa o agente Deep Research do Gemini.
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {[
                      { id: 'auto', label: 'Auto' },
                      { id: 'perplexity', label: 'Perplexity' },
                      { id: 'google', label: 'Google' },
                      { id: 'openai', label: 'OpenAI' },
                    ].map((provider) => (
                      <button
                        key={provider.id}
                        type="button"
                        disabled={!denseResearch}
                        onClick={() => setDeepResearchProvider(provider.id as 'auto' | 'google' | 'perplexity' | 'openai')}
                        className={cn(
                          'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                          deepResearchProvider === provider.id
                            ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                            : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700',
                          !denseResearch && 'pointer-events-none'
                        )}
                      >
                        {provider.label}
                      </button>
                    ))}
                  </div>

                  {/* Perplexity model selector */}
                  {deepResearchProvider === 'perplexity' && (
                    <div className={cn('space-y-1', !denseResearch && 'pointer-events-none')}>
                      <Label className="text-xs font-medium text-muted-foreground">
                        Modelo (Perplexity Deep Research)
                      </Label>
                      <div className="flex flex-wrap gap-1">
                        <button
                          type="button"
                          disabled={!denseResearch}
                          onClick={() => setDeepResearchModel('sonar-deep-research')}
                          className={cn(
                            'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                            deepResearchModel === 'sonar-deep-research'
                              ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                              : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700',
                            !denseResearch && 'pointer-events-none'
                          )}
                          title="sonar-deep-research"
                        >
                          Sonar Deep Research
                        </button>
                      </div>
                      <span className="text-[10px] text-muted-foreground">
                        Este backend usa apenas{' '}
                        <span className="font-mono">sonar-deep-research</span>.
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* Effort Level */}
              <div className="space-y-2">
                <Label className="text-xs font-semibold uppercase text-slate-500">
                  Effort Level
                </Label>
                <div className="flex flex-wrap gap-1">
                  {(['low', 'medium', 'high'] as const).map((level) => (
                    <button
                      key={level}
                      type="button"
                      onClick={() => setDeepResearchEffort(level)}
                      className={cn(
                        'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                        deepResearchEffort === level
                          ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                          : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                      )}
                    >
                      {level === 'low' ? 'Low' : level === 'medium' ? 'Medium' : 'High'}
                    </button>
                  ))}
                </div>
              </div>

              {/* Deep Research Params (Perplexity-specific) */}
              {enableDeepResearchParams && (
                <div className="space-y-3 rounded-2xl border border-slate-200 bg-white/70 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex flex-col gap-0.5">
                      <Label className="text-sm font-medium">Perplexity Deep Research</Label>
                      <span className="text-xs text-muted-foreground">
                        Pesquisa multi-etapas e raciocinio profundo
                      </span>
                    </div>
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-[9px] font-semibold text-slate-600">
                      DR
                    </span>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-xs font-semibold uppercase text-slate-500">
                      Search focus
                    </Label>
                    <div className="flex flex-wrap gap-1">
                      <button
                        type="button"
                        onClick={() => setDeepResearchSearchFocus('')}
                        className={cn(
                          'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                          deepResearchSearchFocus === ''
                            ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                            : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                        )}
                      >
                        Auto
                      </button>
                      {(['web', 'academic', 'sec'] as const).map((mode) => (
                        <button
                          key={mode}
                          type="button"
                          onClick={() => setDeepResearchSearchFocus(mode)}
                          className={cn(
                            'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                            deepResearchSearchFocus === mode
                              ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                              : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                          )}
                        >
                          {mode === 'web' ? 'Web' : mode === 'academic' ? 'Academico' : 'SEC'}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-1">
                    <Label className="text-[10px] font-semibold uppercase text-slate-500">
                      Search domain filter
                    </Label>
                    <Input
                      value={deepResearchDomainFilter}
                      onChange={(e) => setDeepResearchDomainFilter(e.target.value)}
                      placeholder="ex: stf.jus.br, -pinterest.com"
                      className="h-8 text-xs"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <Label className="text-[10px] font-semibold uppercase text-slate-500">
                        Published after
                      </Label>
                      <Input
                        type="date"
                        value={deepResearchSearchAfterDate}
                        onChange={(e) => setDeepResearchSearchAfterDate(e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[10px] font-semibold uppercase text-slate-500">
                        Published before
                      </Label>
                      <Input
                        type="date"
                        value={deepResearchSearchBeforeDate}
                        onChange={(e) => setDeepResearchSearchBeforeDate(e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <Label className="text-[10px] font-semibold uppercase text-slate-500">
                        Last updated after
                      </Label>
                      <Input
                        type="date"
                        value={deepResearchLastUpdatedAfter}
                        onChange={(e) => setDeepResearchLastUpdatedAfter(e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[10px] font-semibold uppercase text-slate-500">
                        Last updated before
                      </Label>
                      <Input
                        type="date"
                        value={deepResearchLastUpdatedBefore}
                        onChange={(e) => setDeepResearchLastUpdatedBefore(e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-2">
                    <div className="space-y-1">
                      <Label className="text-[10px] font-semibold uppercase text-slate-500">
                        Country
                      </Label>
                      <Input
                        value={deepResearchCountry}
                        onChange={(e) => setDeepResearchCountry(e.target.value)}
                        placeholder="BR"
                        className="h-8 text-xs"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[10px] font-semibold uppercase text-slate-500">
                        Latitude
                      </Label>
                      <Input
                        type="number"
                        step="0.0001"
                        value={deepResearchLatitude}
                        onChange={(e) => setDeepResearchLatitude(e.target.value)}
                        placeholder="-23.5505"
                        className="h-8 text-xs"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-[10px] font-semibold uppercase text-slate-500">
                        Longitude
                      </Label>
                      <Input
                        type="number"
                        step="0.0001"
                        value={deepResearchLongitude}
                        onChange={(e) => setDeepResearchLongitude(e.target.value)}
                        placeholder="-46.6333"
                        className="h-8 text-xs"
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* Activate Button */}
              <Button
                className={cn(
                  'w-full mt-2',
                  denseResearch
                    ? 'bg-emerald-600 hover:bg-emerald-700'
                    : 'bg-slate-400'
                )}
                size="sm"
                disabled={!denseResearch}
                onClick={() => setOpen(false)}
              >
                <Brain className="h-3.5 w-3.5 mr-1.5" />
                {denseResearch ? 'Deep Research Ativado' : 'Ativar Deep Research'}
              </Button>
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
