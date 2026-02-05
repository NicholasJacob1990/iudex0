import { useCallback, useState } from 'react';
import { useCorpusStore } from '@/stores/corpus-store';
import { useChatStore } from '@/stores/chat-store';
import type { CorpusResult } from '@/api/client';
import { insertTextAtCursor, appendText } from '@/office/document-bridge';
import { ReferenceCard } from './ReferenceCard';

export function CorpusPanel() {
  const {
    query,
    isSearching,
    error,
    totalResults,
    minScore,
    sortBy,
    expandedResultId,
    selectedResults,
    searchHistory,
    setQuery,
    search,
    searchFromSelection,
    setMinScore,
    setSortBy,
    toggleExpanded,
    toggleSelected,
    clearSelection,
    clearResults,
    filteredResults,
    selectedResultsList,
  } = useCorpusStore();

  const [showHistory, setShowHistory] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  const results = filteredResults();

  const showFeedback = useCallback((msg: string) => {
    setFeedback(msg);
    setTimeout(() => setFeedback(null), 2500);
  }, []);

  // Insert reference as citation block
  const handleInsert = useCallback(
    async (result: CorpusResult) => {
      const citation = `\n[Ref.: ${result.title}]\n${result.content.slice(0, 500)}\n`;
      await insertTextAtCursor(citation);
      showFeedback('Referencia inserida');
    },
    [showFeedback]
  );

  // Insert as footnote-style at end of document
  const handleInsertAsFootnote = useCallback(
    async (result: CorpusResult) => {
      const footnote = `\n---\n[${result.title}] ${result.source || ''}\n${result.content.slice(0, 300)}\n`;
      await appendText(footnote);
      showFeedback('Nota de rodape inserida');
    },
    [showFeedback]
  );

  // Copy text to clipboard
  const handleCopy = useCallback(
    async (result: CorpusResult) => {
      const text = `${result.title}\n${result.content}\nFonte: ${result.source || 'N/A'}`;
      await navigator.clipboard.writeText(text);
      showFeedback('Copiado');
    },
    [showFeedback]
  );

  // Use as context in chat — switch to chat tab with this context
  const handleUseAsContext = useCallback(
    (result: CorpusResult) => {
      const context = `[Contexto do Corpus: ${result.title}]\n${result.content.slice(0, 1000)}`;
      // Store in chat store for next message context
      useChatStore.getState().setDocumentContext?.(context);
      showFeedback('Contexto adicionado ao chat');
    },
    [showFeedback]
  );

  // Batch: insert all selected references
  const handleBatchInsert = useCallback(async () => {
    const selected = selectedResultsList();
    if (selected.length === 0) return;

    const text = selected
      .map((r) => `[Ref.: ${r.title}]\n${r.content.slice(0, 300)}\n`)
      .join('\n---\n');

    await insertTextAtCursor('\n' + text);
    clearSelection();
    showFeedback(`${selected.length} referencias inseridas`);
  }, [selectedResultsList, clearSelection, showFeedback]);

  return (
    <div className="flex h-full flex-col">
      {/* Search header */}
      <div className="border-b border-gray-200 p-office-md">
        <div className="flex items-center justify-between">
          <h2 className="text-office-lg font-semibold">Corpus</h2>
          {searchHistory.length > 0 && (
            <button
              onClick={() => setShowHistory(!showHistory)}
              className="text-office-xs text-brand hover:underline"
            >
              {showHistory ? 'Fechar' : 'Historico'}
            </button>
          )}
        </div>

        {/* Search input */}
        <div className="mt-2 flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && search()}
            placeholder="Buscar precedentes, jurisprudencia..."
            className="office-input flex-1"
          />
          <button
            onClick={() => search()}
            disabled={isSearching || !query.trim()}
            className="office-btn-primary shrink-0 px-3"
          >
            {isSearching ? '...' : 'Buscar'}
          </button>
        </div>

        {/* Quick actions */}
        <div className="mt-2 flex items-center gap-3">
          <button
            onClick={searchFromSelection}
            className="text-office-xs text-brand hover:underline"
          >
            Buscar com selecao do Word
          </button>
          {results.length > 0 && (
            <>
              <span className="text-text-tertiary">|</span>
              <button
                onClick={() => setShowFilters(!showFilters)}
                className="text-office-xs text-text-secondary hover:text-brand"
              >
                Filtros
              </button>
              <button
                onClick={clearResults}
                className="text-office-xs text-text-secondary hover:text-brand"
              >
                Limpar
              </button>
            </>
          )}
        </div>

        {/* Search history dropdown */}
        {showHistory && (
          <div className="mt-2 space-y-1 rounded border border-gray-200 bg-white p-2">
            {searchHistory.map((h, i) => (
              <button
                key={i}
                onClick={() => {
                  setQuery(h.query);
                  search(h.query);
                  setShowHistory(false);
                }}
                className="flex w-full items-center justify-between rounded px-2 py-1 text-left text-office-xs hover:bg-surface-tertiary"
              >
                <span className="truncate text-text-primary">{h.query}</span>
                <span className="shrink-0 text-text-tertiary">
                  {h.resultCount} resultados
                </span>
              </button>
            ))}
          </div>
        )}

        {/* Filters */}
        {showFilters && results.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-3 rounded bg-surface-tertiary p-2">
            <div className="flex items-center gap-1.5">
              <label className="text-office-xs text-text-secondary">Score min:</label>
              <select
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                className="rounded border border-gray-300 px-1.5 py-0.5 text-office-xs"
              >
                <option value={0}>Todos</option>
                <option value={0.3}>30%+</option>
                <option value={0.5}>50%+</option>
                <option value={0.7}>70%+</option>
                <option value={0.9}>90%+</option>
              </select>
            </div>
            <div className="flex items-center gap-1.5">
              <label className="text-office-xs text-text-secondary">Ordenar:</label>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as 'relevance' | 'title')}
                className="rounded border border-gray-300 px-1.5 py-0.5 text-office-xs"
              >
                <option value="relevance">Relevancia</option>
                <option value="title">Titulo</option>
              </select>
            </div>
          </div>
        )}

        {/* Results count + batch actions */}
        {results.length > 0 && (
          <div className="mt-2 flex items-center justify-between">
            <p className="text-office-xs text-text-tertiary">
              {results.length} de {totalResults} resultados
              {minScore > 0 && ` (score >= ${(minScore * 100).toFixed(0)}%)`}
            </p>
            {selectedResults.size > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-office-xs text-brand">
                  {selectedResults.size} selecionados
                </span>
                <button
                  onClick={handleBatchInsert}
                  className="rounded bg-brand px-2 py-0.5 text-office-xs font-medium text-white hover:bg-brand/90"
                >
                  Inserir todos
                </button>
                <button
                  onClick={clearSelection}
                  className="text-office-xs text-text-tertiary hover:text-brand"
                >
                  Limpar
                </button>
              </div>
            )}
          </div>
        )}

        {/* Feedback */}
        {feedback && (
          <p className="mt-1 text-office-xs font-medium text-status-success">
            {feedback}
          </p>
        )}
      </div>

      {/* Results list */}
      <div className="flex-1 overflow-y-auto p-office-md">
        {error && (
          <p className="mb-3 rounded bg-red-50 p-2 text-office-sm text-status-error">
            {error}
          </p>
        )}

        {isSearching && (
          <div className="flex items-center justify-center py-8">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-brand border-t-transparent" />
          </div>
        )}

        {!isSearching && results.length === 0 && !error && (
          <div className="py-8 text-center">
            <p className="text-office-sm text-text-tertiary">
              Busque por precedentes, jurisprudencia e documentos no corpus.
            </p>
            <p className="mt-2 text-office-xs text-text-tertiary">
              Voce pode buscar por texto livre ou usar a selecao do Word como query.
            </p>
          </div>
        )}

        <div className="space-y-3">
          {results.map((result) => (
            <ReferenceCard
              key={result.id}
              result={result}
              isExpanded={expandedResultId === result.id}
              isSelected={selectedResults.has(result.id)}
              onToggleExpand={() => toggleExpanded(result.id)}
              onToggleSelect={() => toggleSelected(result.id)}
              onInsert={() => handleInsert(result)}
              onInsertAsFootnote={() => handleInsertAsFootnote(result)}
              onCopyText={() => handleCopy(result)}
              onUseAsContext={() => handleUseAsContext(result)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
