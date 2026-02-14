import { useState, useCallback } from 'react';
import {
  Input,
  Button,
  Card,
  CardHeader,
  Text,
  Badge,
  Spinner,
} from '@fluentui/react-components';
import { SearchRegular } from '@fluentui/react-icons';
import { searchCorpus, type CorpusResult } from '@/api/client';

export function CorpusSearch() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<CorpusResult[]>([]);
  const [total, setTotal] = useState(0);
  const [isSearching, setIsSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = useCallback(async () => {
    const trimmed = query.trim();
    if (!trimmed) return;

    setIsSearching(true);
    setError(null);
    setHasSearched(true);

    try {
      const response = await searchCorpus(trimmed, 10);
      setResults(response.results);
      setTotal(response.total);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Erro ao pesquisar';
      setError(message);
      setResults([]);
      setTotal(0);
    } finally {
      setIsSearching(false);
    }
  }, [query]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        handleSearch();
      }
    },
    [handleSearch]
  );

  return (
    <div className="space-y-4">
      {/* Search Input */}
      <div className="flex gap-2">
        <Input
          className="flex-1"
          placeholder="Pesquisar jurisprudencia, legislacao, doutrina..."
          value={query}
          onChange={(_e, data) => setQuery(data.value)}
          onKeyDown={handleKeyDown}
          contentBefore={<SearchRegular />}
        />
        <Button
          appearance="primary"
          onClick={handleSearch}
          disabled={isSearching || !query.trim()}
        >
          Pesquisar
        </Button>
      </div>

      {/* Loading */}
      {isSearching && (
        <div className="flex justify-center py-4">
          <Spinner size="small" label="Pesquisando..." />
        </div>
      )}

      {/* Error */}
      {error && (
        <Card size="small">
          <Text className="text-status-error">{error}</Text>
        </Card>
      )}

      {/* Results */}
      {!isSearching && hasSearched && (
        <>
          <Text size={200} className="text-text-secondary">
            {total} resultado{total !== 1 ? 's' : ''} encontrado{total !== 1 ? 's' : ''}
          </Text>

          {results.length === 0 && !error ? (
            <div className="py-4 text-center">
              <Text className="text-text-secondary">
                Nenhum resultado encontrado para &quot;{query}&quot;.
              </Text>
            </div>
          ) : (
            <div className="space-y-3">
              {results.map((result) => (
                <Card key={result.id} size="small" className="hover:shadow-sm">
                  <CardHeader
                    header={
                      <div className="flex items-center gap-2">
                        <Text weight="semibold">{result.title}</Text>
                        {result.source && (
                          <Badge appearance="outline" size="small">
                            {result.source}
                          </Badge>
                        )}
                        <Badge appearance="tint" color="brand" size="small">
                          {(result.score * 100).toFixed(0)}%
                        </Badge>
                      </div>
                    }
                    description={
                      <Text
                        size={200}
                        className="line-clamp-3 text-text-secondary"
                      >
                        {result.content}
                      </Text>
                    }
                  />
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
