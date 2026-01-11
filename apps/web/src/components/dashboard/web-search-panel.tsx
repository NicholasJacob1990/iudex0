import { useEffect, useState } from 'react';
import { Input } from '@/components/ui/input';
import { Search, Clock } from 'lucide-react';
import apiClient from '@/lib/api-client';

export function WebSearchPanel() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<{ id: string; title?: string; url?: string; snippet?: string }[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    handleSearch('repercussão geral');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch = async (value?: string) => {
    const term = value ?? query;
    if (!term.trim()) return;
    setIsLoading(true);
    try {
      const data = await apiClient.searchWeb(term);
      setResults(data.items || []);
    } catch (error) {
      setResults([]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <section className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase text-muted-foreground">Pesquisa Web</p>
          <h2 className="font-display text-xl text-foreground">
            Busque informações relevantes na internet
          </h2>
        </div>
      </div>

      <div className="relative mt-4">
        <Search className="absolute left-4 top-3 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Pesquise na web..."
          className="h-12 rounded-2xl border-transparent bg-sand pl-11"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
        />
        <button
          type="button"
          className="absolute right-2 top-2 h-8 rounded-full bg-primary px-4 text-xs font-semibold text-primary-foreground"
          onClick={() => handleSearch()}
          disabled={isLoading}
        >
          Buscar
        </button>
      </div>

      <div className="mt-5 space-y-2">
        {isLoading ? (
          <p className="text-center text-sm text-muted-foreground py-4">Buscando na web...</p>
        ) : results.length ? (
          results.map((item) => (
            <div
              key={item.id}
              className="flex flex-col gap-1 rounded-2xl border border-outline/40 bg-white/80 px-4 py-2 text-sm"
            >
              <div className="flex items-center gap-2 text-muted-foreground">
                <Clock className="h-4 w-4" />
                <span className="font-semibold text-foreground">{item.title || item.url}</span>
              </div>
              {item.snippet && <p className="text-xs text-muted-foreground">{item.snippet}</p>}
            </div>
          ))
        ) : (
          <p className="text-center text-sm text-muted-foreground py-4">Nenhum resultado encontrado.</p>
        )}
      </div>
    </section>
  );
}
