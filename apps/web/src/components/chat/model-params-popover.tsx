'use client';

import React, { useMemo } from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { SlidersHorizontal } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useChatStore } from '@/stores/chat-store';
import { getModelConfig, type ModelId } from '@/config/models';

const recencyOptions: { value: '' | 'day' | 'week' | 'month' | 'year'; label: string }[] = [
  { value: '', label: 'Sem filtro' },
  { value: 'day', label: '24h' },
  { value: 'week', label: '7d' },
  { value: 'month', label: '30d' },
  { value: 'year', label: '1 ano' },
];

export const ModelParamsPopover = React.memo(function ModelParamsPopover() {
  const {
    chatMode,
    selectedModels,
    selectedModel,
    webSearch,
    searchMode,
    denseResearch,
    deepResearchProvider,
    reasoningLevel,
    setReasoningLevel,
    thinkingBudget,
    setThinkingBudget,
    verbosity,
    setVerbosity,
    modelOverrides,
    setModelOverride,
    perplexitySearchMode,
    setPerplexitySearchMode,
    perplexitySearchType,
    setPerplexitySearchType,
    perplexitySearchContextSize,
    setPerplexitySearchContextSize,
    perplexitySearchClassifier,
    setPerplexitySearchClassifier,
    perplexityDisableSearch,
    setPerplexityDisableSearch,
    perplexityStreamMode,
    setPerplexityStreamMode,
    perplexitySearchDomainFilter,
    setPerplexitySearchDomainFilter,
    perplexitySearchLanguageFilter,
    setPerplexitySearchLanguageFilter,
    perplexitySearchRecencyFilter,
    setPerplexitySearchRecencyFilter,
    perplexitySearchAfterDate,
    setPerplexitySearchAfterDate,
    perplexitySearchBeforeDate,
    setPerplexitySearchBeforeDate,
    perplexityLastUpdatedAfter,
    setPerplexityLastUpdatedAfter,
    perplexityLastUpdatedBefore,
    setPerplexityLastUpdatedBefore,
    perplexitySearchMaxResults,
    setPerplexitySearchMaxResults,
    perplexitySearchMaxTokens,
    setPerplexitySearchMaxTokens,
    perplexitySearchMaxTokensPerPage,
    setPerplexitySearchMaxTokensPerPage,
    perplexitySearchCountry,
    setPerplexitySearchCountry,
    perplexitySearchRegion,
    setPerplexitySearchRegion,
    perplexitySearchCity,
    setPerplexitySearchCity,
    perplexitySearchLatitude,
    setPerplexitySearchLatitude,
    perplexitySearchLongitude,
    setPerplexitySearchLongitude,
    perplexityReturnImages,
    setPerplexityReturnImages,
    perplexityReturnVideos,
    setPerplexityReturnVideos,
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
  } = useChatStore();

  const activeModelIds = useMemo(() => {
    const base =
      chatMode === 'multi-model'
        ? selectedModels
        : selectedModels.length > 0
          ? [selectedModels[0]]
          : selectedModel
            ? [selectedModel]
            : [];
    return Array.from(new Set(base.filter(Boolean)));
  }, [chatMode, selectedModels, selectedModel]);

  const showPerModelOverrides = chatMode === 'multi-model' && activeModelIds.length > 0;
  const primaryModelId =
    selectedModels.length === 1 ? String(selectedModels[0] || '').toLowerCase() : '';
  const isPerplexitySonarSelected = ['sonar', 'sonar-pro', 'sonar-reasoning-pro'].includes(
    primaryModelId
  );
  const isSonarProSelected = primaryModelId === 'sonar-pro';
  const isPerplexityDeepSelected = primaryModelId === 'sonar-deep-research';
  const isAnyPerplexitySelected =
    isPerplexitySonarSelected || isPerplexityDeepSelected || primaryModelId.includes('sonar');
  const isSharedSearchMode = webSearch && (searchMode === 'shared' || searchMode === 'perplexity');
  const enableDeepResearchParams =
    isPerplexityDeepSelected || (denseResearch && deepResearchProvider === 'perplexity');
  const showPerplexitySonarParams = webSearch && isPerplexitySonarSelected && !isSharedSearchMode;
  const showPerplexitySearchApiParams =
    webSearch && isSharedSearchMode && isAnyPerplexitySelected && !isPerplexityDeepSelected;
  const showSearchFocusInSearchApi = showPerplexitySearchApiParams && !showPerplexitySonarParams;
  const hasModelParamOptions =
    showPerplexitySonarParams || showPerplexitySearchApiParams || enableDeepResearchParams;
  const isClaudeSelected = primaryModelId.startsWith('claude');
  const claudeBudgetRange = primaryModelId.includes('sonnet') ? '0-31999' : '0-63999';
  const claudeBudgetFlavor = primaryModelId.includes('sonnet') ? 'Claude Sonnet' : 'Claude Opus';
  const claudeBudgetHint = `${claudeBudgetRange} (${claudeBudgetFlavor})`;
  const isGpt52Selected = primaryModelId.startsWith('gpt-5.2');
  const isGeminiProSelected = primaryModelId === 'gemini-3-pro';
  const isGeminiFlashSelected =
    primaryModelId.includes('flash') && primaryModelId.startsWith('gemini');
  const hasSingleModel = selectedModels.length === 1;
  const showThinkingParams =
    hasSingleModel && !isPerplexitySonarSelected && !isPerplexityDeepSelected;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          title="Parâmetros por modelo"
          className={cn(
            'h-7 w-7 rounded-full transition-colors',
            hasModelParamOptions
              ? 'text-emerald-600 bg-emerald-500/10'
              : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'
          )}
        >
          <SlidersHorizontal className="h-3.5 w-3.5" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-[380px] max-h-[70vh] overflow-y-auto p-4 pr-3 space-y-4 overscroll-contain"
        align="start"
        sideOffset={8}
        collisionPadding={12}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-col gap-0.5">
            <Label className="text-sm font-medium">Parâmetros por modelo</Label>
            <span className="text-xs text-muted-foreground">
              Ajustes de raciocínio e parâmetros avançados
            </span>
          </div>
          <span className="rounded-full bg-slate-100 px-2 py-1 text-[9px] font-semibold text-slate-600">
            ADV
          </span>
        </div>

        <div className="space-y-3 rounded-2xl border border-slate-200 bg-white/70 p-3">
          <div className="flex items-start justify-between gap-3">
            <div className="flex flex-col gap-0.5">
              <Label className="text-sm font-medium">Parâmetros de raciocínio</Label>
              <span className="text-xs text-muted-foreground">
                Variam conforme o modelo selecionado
              </span>
            </div>
            <span className="rounded-full bg-slate-100 px-2 py-1 text-[9px] font-semibold text-slate-600">
              THINK
            </span>
          </div>

          {!hasSingleModel && (
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-600">
              No modo Comparar modelos, use overrides por modelo abaixo.
            </div>
          )}

          {showPerModelOverrides && (
            <div className="space-y-2">
              {activeModelIds.map((modelId) => {
                const cfg = getModelConfig(modelId as ModelId);
                const override = modelOverrides?.[modelId] || {};
                const lower = String(modelId || '').toLowerCase();
                const isClaude = lower.startsWith('claude');
                const isGpt52 = lower.startsWith('gpt-5.2');
                const isGpt5 = lower.startsWith('gpt-5') && !isGpt52;
                const isGeminiPro = lower === 'gemini-3-pro';
                const isGeminiFlash = lower === 'gemini-3-flash';
                const overrideReasoning = override.reasoningLevel;

                const thinkingOptions = isGpt52
                  ? (['none', 'low', 'medium', 'high', 'xhigh'] as const)
                  : isGpt5
                    ? (['minimal', 'low', 'medium', 'high'] as const)
                    : isGeminiPro
                      ? (['low', 'high'] as const)
                      : isGeminiFlash
                        ? (['minimal', 'low', 'medium', 'high'] as const)
                        : null;

                const budgetHint = lower.includes('sonnet') ? '0-31999' : '0-63999';

                return (
                  <div key={modelId} className="rounded-md border p-2 text-[11px] space-y-2">
                    <div className="font-semibold">{cfg?.label || modelId}</div>

                    {thinkingOptions && (
                      <div className="space-y-2">
                        <Label className="text-[10px] font-semibold uppercase text-slate-500">
                          {isGeminiPro || isGeminiFlash
                            ? 'Thinking level'
                            : 'Reasoning effort'}
                        </Label>
                        <div className="flex flex-wrap gap-1">
                          <button
                            type="button"
                            onClick={() => setModelOverride(modelId, { reasoningLevel: undefined })}
                            className={cn(
                              'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                              !overrideReasoning
                                ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                            )}
                          >
                            Auto
                          </button>
                          {thinkingOptions.map((level) => (
                            <button
                              key={level}
                              type="button"
                              onClick={() => setModelOverride(modelId, { reasoningLevel: level })}
                              className={cn(
                                'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                                overrideReasoning === level
                                  ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                                  : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                              )}
                            >
                              {String(level).toUpperCase()}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {isClaude && (
                      <div className="space-y-2">
                        <Label className="text-[10px] font-semibold uppercase text-slate-500">
                          Thinking budget (Claude)
                        </Label>
                        <Input
                          value={override.thinkingBudget ?? ''}
                          onChange={(e) =>
                            setModelOverride(modelId, { thinkingBudget: e.target.value })
                          }
                          placeholder={`Auto (${budgetHint})`}
                          inputMode="numeric"
                          className="h-8 text-xs"
                        />
                      </div>
                    )}

                    <div className="space-y-2">
                      <Label className="text-[10px] font-semibold uppercase text-slate-500">
                        Verbosidade
                      </Label>
                      <div className="flex gap-1 rounded-lg bg-slate-100 p-1">
                        {(['auto', 'low', 'medium', 'high'] as const).map((level) => (
                          <button
                            key={level}
                            onClick={() =>
                              setModelOverride(modelId, {
                                verbosity: level === 'auto' ? undefined : level,
                              })
                            }
                            className={cn(
                              'flex-1 px-2 py-1 text-[10px] font-medium rounded-md transition-all',
                              (level === 'auto'
                                ? !override.verbosity
                                : override.verbosity === level)
                                ? 'bg-emerald-600/15 text-emerald-700 shadow-sm'
                                : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                            )}
                          >
                            {level === 'auto'
                              ? 'Auto'
                              : level === 'low'
                                ? 'Baixa'
                                : level === 'medium'
                                  ? 'Media'
                                  : 'Alta'}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })}
              <span className="text-[10px] text-muted-foreground">
                Overrides so se aplicam no modo Comparar modelos.
              </span>
            </div>
          )}

          {showThinkingParams && isClaudeSelected && (
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase text-slate-500">
                Thinking budget (Claude 4.5)
              </Label>
              <Input
                value={thinkingBudget}
                onChange={(e) => setThinkingBudget(e.target.value)}
                placeholder="Auto"
                inputMode="numeric"
                className="h-8 text-xs"
              />
              <span className="text-[10px] text-muted-foreground">
                Define budget_tokens para ativar thinking. Deve ser menor que max_tokens.
              </span>
              <span className="text-[10px] text-muted-foreground">
                Intervalo: {claudeBudgetHint}
              </span>
            </div>
          )}

          {showThinkingParams && isGpt52Selected && (
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase text-slate-500">
                Reasoning level (GPT‑5.2)
              </Label>
              <div className="flex flex-wrap gap-1">
                {(['none', 'low', 'medium', 'high', 'xhigh'] as const).map((level) => (
                  <button
                    key={level}
                    type="button"
                    onClick={() => setReasoningLevel(level)}
                    className={cn(
                      'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                      reasoningLevel === level
                        ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                        : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                    )}
                  >
                    {level === 'none' ? 'None' : level.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
          )}

          {showThinkingParams && isGeminiProSelected && (
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase text-slate-500">
                Thinking level (Gemini 3 Pro)
              </Label>
              <div className="flex flex-wrap gap-1">
                {(['low', 'high'] as const).map((level) => (
                  <button
                    key={level}
                    type="button"
                    onClick={() => setReasoningLevel(level)}
                    className={cn(
                      'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                      reasoningLevel === level
                        ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                        : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                    )}
                  >
                    {level === 'low' ? 'Low' : 'High'}
                  </button>
                ))}
              </div>
            </div>
          )}

          {showThinkingParams && isGeminiFlashSelected && (
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase text-slate-500">
                Thinking level (Gemini 3 Flash)
              </Label>
              <div className="flex flex-wrap gap-1">
                {(['minimal', 'low', 'medium', 'high'] as const).map((level) => (
                  <button
                    key={level}
                    type="button"
                    onClick={() => setReasoningLevel(level)}
                    className={cn(
                      'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                      reasoningLevel === level
                        ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                        : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                    )}
                  >
                    {level === 'minimal' ? 'Minimal' : level === 'low' ? 'Low' : level === 'medium' ? 'Medium' : 'High'}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {!hasModelParamOptions && (
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-600">
            Para opções específicas do Perplexity: ative Web Search, selecione um modelo Sonar (chat)
            ou habilite Deep Research (Perplexity).
          </div>
        )}

        {showPerplexitySonarParams && (
          <div className="space-y-3 rounded-2xl border border-slate-200 bg-white/70 p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="flex flex-col gap-0.5">
                <Label className="text-sm font-medium">Perplexity Sonar (Chat)</Label>
                <span className="text-xs text-muted-foreground">
                  Chat web-grounded com fontes
                </span>
              </div>
              <span className="rounded-full bg-slate-100 px-2 py-1 text-[9px] font-semibold text-slate-600">
                SONAR
              </span>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase text-slate-500">
                Search focus
              </Label>
              <div className="flex flex-wrap gap-1">
                {(['web', 'academic', 'sec'] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setPerplexitySearchMode(mode)}
                    className={cn(
                      'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                      perplexitySearchMode === mode
                        ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                        : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                    )}
                  >
                    {mode === 'web' ? 'Web' : mode === 'academic' ? 'Acadêmico' : 'SEC'}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase text-slate-500">
                Search context size
              </Label>
              <div className="flex flex-wrap gap-1">
                {(['low', 'medium', 'high'] as const).map((size) => (
                  <button
                    key={size}
                    type="button"
                    onClick={() => setPerplexitySearchContextSize(size)}
                    className={cn(
                      'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                      perplexitySearchContextSize === size
                        ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                        : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                    )}
                  >
                    {size === 'low' ? 'Low' : size === 'medium' ? 'Medium' : 'High'}
                  </button>
                ))}
              </div>
            </div>

            {isSonarProSelected && (
              <div className="space-y-2">
                <Label className="text-xs font-semibold uppercase text-slate-500">
                  Search type (Sonar Pro)
                </Label>
                <div className="flex flex-wrap gap-1">
                  {(['fast', 'pro', 'auto'] as const).map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => setPerplexitySearchType(mode)}
                      className={cn(
                        'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                        perplexitySearchType === mode
                          ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                          : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                      )}
                    >
                      {mode === 'fast' ? 'Fast' : mode === 'pro' ? 'Pro' : 'Auto'}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="grid gap-2">
              <div className="space-y-1">
                <Label className="text-[10px] font-semibold uppercase text-slate-500">
                  Search domain filter
                </Label>
                <Input
                  value={perplexitySearchDomainFilter}
                  onChange={(e) => setPerplexitySearchDomainFilter(e.target.value)}
                  placeholder="ex: stf.jus.br, -pinterest.com"
                  className="h-8 text-xs"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-[10px] font-semibold uppercase text-slate-500">
                  Language filter
                </Label>
                <Input
                  value={perplexitySearchLanguageFilter}
                  onChange={(e) => setPerplexitySearchLanguageFilter(e.target.value)}
                  placeholder="ex: pt,en"
                  className="h-8 text-xs"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase text-slate-500">
                Recency filter
              </Label>
              <div className="flex flex-wrap gap-1">
                {recencyOptions.map((opt) => (
                  <button
                    key={opt.value || 'all'}
                    type="button"
                    onClick={() => setPerplexitySearchRecencyFilter(opt.value)}
                    className={cn(
                      'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                      perplexitySearchRecencyFilter === opt.value
                        ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                        : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                    )}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid gap-2">
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <Label className="text-[10px] font-semibold uppercase text-slate-500">
                    Published after
                  </Label>
                  <Input
                    type="date"
                    value={perplexitySearchAfterDate}
                    onChange={(e) => setPerplexitySearchAfterDate(e.target.value)}
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-[10px] font-semibold uppercase text-slate-500">
                    Published before
                  </Label>
                  <Input
                    type="date"
                    value={perplexitySearchBeforeDate}
                    onChange={(e) => setPerplexitySearchBeforeDate(e.target.value)}
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
                    value={perplexityLastUpdatedAfter}
                    onChange={(e) => setPerplexityLastUpdatedAfter(e.target.value)}
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-[10px] font-semibold uppercase text-slate-500">
                    Last updated before
                  </Label>
                  <Input
                    type="date"
                    value={perplexityLastUpdatedBefore}
                    onChange={(e) => setPerplexityLastUpdatedBefore(e.target.value)}
                    className="h-8 text-xs"
                  />
                </div>
              </div>
            </div>

            <div className="grid gap-2">
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <Label className="text-[10px] font-semibold uppercase text-slate-500">
                    Max results
                  </Label>
                  <Input
                    type="number"
                    min={1}
                    max={20}
                    value={perplexitySearchMaxResults}
                    onChange={(e) => setPerplexitySearchMaxResults(e.target.value)}
                    placeholder="1-20"
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-[10px] font-semibold uppercase text-slate-500">
                    Max tokens/page
                  </Label>
                  <Input
                    type="number"
                    min={1}
                    max={1_000_000}
                    value={perplexitySearchMaxTokensPerPage}
                    onChange={(e) => setPerplexitySearchMaxTokensPerPage(e.target.value)}
                    placeholder="2048"
                    className="h-8 text-xs"
                  />
                </div>
              </div>
              <div className="space-y-1">
                <Label className="text-[10px] font-semibold uppercase text-slate-500">
                  Max tokens (total)
                </Label>
                <Input
                  type="number"
                  min={1}
                  max={1_000_000}
                  value={perplexitySearchMaxTokens}
                  onChange={(e) => setPerplexitySearchMaxTokens(e.target.value)}
                  placeholder="25000"
                  className="h-8 text-xs"
                />
              </div>
            </div>

            <div className="grid gap-2">
              <div className="grid grid-cols-3 gap-2">
                <div className="space-y-1">
                  <Label className="text-[10px] font-semibold uppercase text-slate-500">
                    Country
                  </Label>
                  <Input
                    value={perplexitySearchCountry}
                    onChange={(e) => setPerplexitySearchCountry(e.target.value)}
                    placeholder="BR"
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-[10px] font-semibold uppercase text-slate-500">
                    Region
                  </Label>
                  <Input
                    value={perplexitySearchRegion}
                    onChange={(e) => setPerplexitySearchRegion(e.target.value)}
                    placeholder="SP"
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-[10px] font-semibold uppercase text-slate-500">
                    City
                  </Label>
                  <Input
                    value={perplexitySearchCity}
                    onChange={(e) => setPerplexitySearchCity(e.target.value)}
                    placeholder="São Paulo"
                    className="h-8 text-xs"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <Label className="text-[10px] font-semibold uppercase text-slate-500">
                    Latitude
                  </Label>
                  <Input
                    type="number"
                    step="0.0001"
                    value={perplexitySearchLatitude}
                    onChange={(e) => setPerplexitySearchLatitude(e.target.value)}
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
                    value={perplexitySearchLongitude}
                    onChange={(e) => setPerplexitySearchLongitude(e.target.value)}
                    placeholder="-46.6333"
                    className="h-8 text-xs"
                  />
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-2">
              <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                <div>
                  <p className="text-[11px] font-semibold text-slate-700">Return images</p>
                  <p className="text-[10px] text-slate-500">Incluir imagens na busca</p>
                </div>
                <Switch
                  checked={perplexityReturnImages}
                  onCheckedChange={setPerplexityReturnImages}
                />
              </div>
              <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                <div>
                  <p className="text-[11px] font-semibold text-slate-700">Return videos</p>
                  <p className="text-[10px] text-slate-500">
                    Incluir videos nos resultados
                  </p>
                </div>
                <Switch
                  checked={perplexityReturnVideos}
                  onCheckedChange={setPerplexityReturnVideos}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-2">
              {isSonarProSelected && (
                <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                  <div>
                    <p className="text-[11px] font-semibold text-slate-700">
                      Classificador automático
                    </p>
                    <p className="text-[10px] text-slate-500">
                      Habilita roteamento Fast/Pro
                    </p>
                  </div>
                  <Switch
                    checked={perplexitySearchClassifier}
                    onCheckedChange={setPerplexitySearchClassifier}
                  />
                </div>
              )}
              <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                <div>
                  <p className="text-[11px] font-semibold text-slate-700">
                    Desativar busca
                  </p>
                  <p className="text-[10px] text-slate-500">Resposta sem pesquisa web</p>
                </div>
                <Switch
                  checked={perplexityDisableSearch}
                  onCheckedChange={setPerplexityDisableSearch}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase text-slate-500">
                Stream mode
              </Label>
              <div className="flex flex-wrap gap-1">
                {(['full', 'concise'] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setPerplexityStreamMode(mode)}
                    className={cn(
                      'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                      perplexityStreamMode === mode
                        ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                        : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                    )}
                  >
                    {mode === 'full' ? 'Full' : 'Concise'}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {showPerplexitySearchApiParams && (
          <div className="space-y-3 rounded-2xl border border-slate-200 bg-white/70 p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="flex flex-col gap-0.5">
                <Label className="text-sm font-medium">
                  Perplexity Search API (Compartilhada)
                </Label>
                <span className="text-xs text-muted-foreground">
                  Filtros da busca compartilhada
                </span>
              </div>
              <span className="rounded-full bg-slate-100 px-2 py-1 text-[9px] font-semibold text-slate-600">
                API
              </span>
            </div>

            {showSearchFocusInSearchApi && (
              <div className="space-y-2">
                <Label className="text-xs font-semibold uppercase text-slate-500">
                  Search focus
                </Label>
                <div className="flex flex-wrap gap-1">
                  {(['web', 'academic', 'sec'] as const).map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => setPerplexitySearchMode(mode)}
                      className={cn(
                        'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                        perplexitySearchMode === mode
                          ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                          : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                      )}
                    >
                      {mode === 'web' ? 'Web' : mode === 'academic' ? 'Acadêmico' : 'SEC'}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="grid gap-2">
              <div className="space-y-1">
                <Label className="text-[10px] font-semibold uppercase text-slate-500">
                  Search domain filter
                </Label>
                <Input
                  value={perplexitySearchDomainFilter}
                  onChange={(e) => setPerplexitySearchDomainFilter(e.target.value)}
                  placeholder="ex: stf.jus.br, -pinterest.com"
                  className="h-8 text-xs"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-[10px] font-semibold uppercase text-slate-500">
                  Language filter
                </Label>
                <Input
                  value={perplexitySearchLanguageFilter}
                  onChange={(e) => setPerplexitySearchLanguageFilter(e.target.value)}
                  placeholder="ex: pt,en"
                  className="h-8 text-xs"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase text-slate-500">
                Recency filter
              </Label>
              <div className="flex flex-wrap gap-1">
                {recencyOptions.map((opt) => (
                  <button
                    key={opt.value || 'all'}
                    type="button"
                    onClick={() => setPerplexitySearchRecencyFilter(opt.value)}
                    className={cn(
                      'rounded-full border px-2 py-1 text-[10px] font-semibold transition-colors',
                      perplexitySearchRecencyFilter === opt.value
                        ? 'border-emerald-200 bg-emerald-500/15 text-emerald-700'
                        : 'border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                    )}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid gap-2">
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <Label className="text-[10px] font-semibold uppercase text-slate-500">
                    Published after
                  </Label>
                  <Input
                    type="date"
                    value={perplexitySearchAfterDate}
                    onChange={(e) => setPerplexitySearchAfterDate(e.target.value)}
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-[10px] font-semibold uppercase text-slate-500">
                    Published before
                  </Label>
                  <Input
                    type="date"
                    value={perplexitySearchBeforeDate}
                    onChange={(e) => setPerplexitySearchBeforeDate(e.target.value)}
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
                    value={perplexityLastUpdatedAfter}
                    onChange={(e) => setPerplexityLastUpdatedAfter(e.target.value)}
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-[10px] font-semibold uppercase text-slate-500">
                    Last updated before
                  </Label>
                  <Input
                    type="date"
                    value={perplexityLastUpdatedBefore}
                    onChange={(e) => setPerplexityLastUpdatedBefore(e.target.value)}
                    className="h-8 text-xs"
                  />
                </div>
              </div>
            </div>

            <div className="grid gap-2">
              <div className="grid grid-cols-3 gap-2">
                <div className="space-y-1">
                  <Label className="text-[10px] font-semibold uppercase text-slate-500">
                    Country
                  </Label>
                  <Input
                    value={perplexitySearchCountry}
                    onChange={(e) => setPerplexitySearchCountry(e.target.value)}
                    placeholder="BR"
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-[10px] font-semibold uppercase text-slate-500">
                    Region
                  </Label>
                  <Input
                    value={perplexitySearchRegion}
                    onChange={(e) => setPerplexitySearchRegion(e.target.value)}
                    placeholder="SP"
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-[10px] font-semibold uppercase text-slate-500">
                    City
                  </Label>
                  <Input
                    value={perplexitySearchCity}
                    onChange={(e) => setPerplexitySearchCity(e.target.value)}
                    placeholder="São Paulo"
                    className="h-8 text-xs"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <Label className="text-[10px] font-semibold uppercase text-slate-500">
                    Latitude
                  </Label>
                  <Input
                    type="number"
                    step="0.0001"
                    value={perplexitySearchLatitude}
                    onChange={(e) => setPerplexitySearchLatitude(e.target.value)}
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
                    value={perplexitySearchLongitude}
                    onChange={(e) => setPerplexitySearchLongitude(e.target.value)}
                    placeholder="-46.6333"
                    className="h-8 text-xs"
                  />
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-2">
              <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                <div>
                  <p className="text-[11px] font-semibold text-slate-700">
                    Return images
                  </p>
                  <p className="text-[10px] text-slate-500">Incluir imagens na busca</p>
                </div>
                <Switch
                  checked={perplexityReturnImages}
                  onCheckedChange={setPerplexityReturnImages}
                />
              </div>
              <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                <div>
                  <p className="text-[11px] font-semibold text-slate-700">Return videos</p>
                  <p className="text-[10px] text-slate-500">
                    Incluir videos nos resultados
                  </p>
                </div>
                <Switch
                  checked={perplexityReturnVideos}
                  onCheckedChange={setPerplexityReturnVideos}
                />
              </div>
            </div>
          </div>
        )}

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
                Reasoning effort
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
                    {mode === 'web' ? 'Web' : mode === 'academic' ? 'Acadêmico' : 'SEC'}
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
      </PopoverContent>
    </Popover>
  );
});
