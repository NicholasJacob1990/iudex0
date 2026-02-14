/**
 * Painel de busca no corpus juridico.
 *
 * Reutiliza o endpoint /corpus/search do backend.
 * Adaptado do CorpusPanel do Word add-in para o contexto do Outlook.
 */

import { useState, useCallback } from 'react';
import {
  Input,
  Button,
  Spinner,
  Text,
} from '@fluentui/react-components';
import { SearchRegular } from '@fluentui/react-icons';
import { searchCorpus, type CorpusResult, type CorpusSearchResponse } from '@/api/client';
import { useEmailStore } from '@/stores/email-store';
import { ResultCard } from './ResultCard';

export function CorpusSearch() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<CorpusResult[]>([]);
  const [totalResults, setTotalResults] = useState(0);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const currentEmail = useEmailStore((s) => s.currentEmail);

  const handleSearch = useCallback(
    async (searchQuery?: string) => {
      const q = searchQuery || query;
      if (!q.trim()) return;

      setIsSearching(true);
      setError(null);

      try {
        const response: CorpusSearchResponse = await searchCorpus(q, 10);
        setResults(response.results);
        setTotalResults(response.total);
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : 'Erro na busca';
        setError(message);
      } finally {
        setIsSearching(false);
      }
    },
    [query]
  );

  const handleSearchFromEmail = useCallback(() => {
    if (!currentEmail) return;
    // Usa o assunto do e-mail como query
    const emailQuery = currentEmail.subject || '';
    if (emailQuery.trim()) {
      setQuery(emailQuery);
      handleSearch(emailQuery);
    }
  }, [currentEmail, handleSearch]);

  const handleCopy = useCallback(async (result: CorpusResult) => {
    const text = `${result.title}\n${result.content}\nFonte: ${result.source || 'N/A'}`;
    await navigator.clipboard.writeText(text);
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* Cabecalho de busca */}
      <div className="border-b border-gray-200 p-office-md">
        <Text size={400} weight="semibold" className="mb-2 block">
          Pesquisa no Corpus
        </Text>

        {/* Input de busca */}
        <div className="flex gap-2">
          <Input
            value={query}
            onChange={(_e, data) => setQuery(data.value)}
            onKeyDown={handleKeyDown}
            placeholder="Buscar precedentes, jurisprudencia..."
            contentBefore={<SearchRegular />}
            className="flex-1"
            size="small"
          />
          <Button
            appearance="primary"
            size="small"
            onClick={() => handleSearch()}
            disabled={isSearching || !query.trim()}
          >
            {isSearching ? '...' : 'Buscar'}
          </Button>
        </div>

        {/* Acao rapida: buscar a partir do e-mail */}
        {currentEmail && (
          <div className="mt-2">
            <button
              onClick={handleSearchFromEmail}
              className="text-office-xs text-brand hover:underline"
            >
              Buscar a partir do assunto do e-mail
            </button>
          </div>
        )}

        {/* Contagem de resultados */}
        {results.length > 0 && (
          <Text size={100} className="mt-2 block text-text-tertiary">
            {results.length} de {totalResults} resultados
          </Text>
        )}
      </div>

      {/* Lista de resultados */}
      <div className="flex-1 overflow-y-auto p-office-md">
        {/* Erro */}
        {error && (
          <div className="mb-3 rounded bg-red-50 p-2">
            <Text size={200} className="text-status-error">
              {error}
            </Text>
          </div>
        )}

        {/* Loading */}
        {isSearching && (
          <div className="flex items-center justify-center py-8">
            <Spinner size="medium" label="Buscando..." />
          </div>
        )}

        {/* Vazio */}
        {!isSearching && results.length === 0 && !error && (
          <div className="py-8 text-center">
            <Text size={200} className="text-text-tertiary">
              Busque por precedentes, jurisprudencia e documentos no corpus.
            </Text>
          </div>
        )}

        {/* Resultados */}
        <div className="space-y-3">
          {results.map((result) => (
            <ResultCard
              key={result.id}
              result={result}
              isExpanded={expandedId === result.id}
              onToggleExpand={() =>
                setExpandedId(expandedId === result.id ? null : result.id)
              }
              onCopy={() => handleCopy(result)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
