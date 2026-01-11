import { useEffect, useState } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Search, Bookmark } from 'lucide-react';
import apiClient from '@/lib/api-client';

export function LegislationPanel() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    handleSearch('licitação');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch = async (value?: string) => {
    const term = value ?? query;
    if (!term.trim()) return;
    setIsLoading(true);
    try {
      const data = await apiClient.searchLegislation(term);
      setResults(data.items || []);
    } catch (error) {
      setResults([]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <section className="rounded-3xl border border-white/70 bg-white/90 p-5 shadow-soft">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase text-muted-foreground">Legislação</p>
          <h2 className="font-display text-xl text-foreground">
            Pesquise e gerencie legislação oficial
          </h2>
        </div>
        <Button variant="outline" className="rounded-full">
          Ver legislações salvas
        </Button>
      </div>

      <div className="mt-4 flex flex-col gap-3">
        <div className="relative">
          <Search className="absolute left-4 top-3 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Ex: proteção de dados, contraditório..."
            className="h-12 rounded-2xl border-transparent bg-sand pl-11"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          />
          <Button
            className="absolute right-2 top-2 h-8 rounded-full bg-primary text-primary-foreground"
            onClick={() => handleSearch()}
            disabled={isLoading}
          >
            Buscar
          </Button>
        </div>
        {isLoading ? (
          <p className="text-sm text-muted-foreground py-6 text-center">Buscando legislação...</p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {results.map((law) => (
              <div
                key={law.id}
                className="flex items-center justify-between rounded-2xl border border-outline/40 bg-white/80 px-4 py-3"
              >
                <div>
                  <p className="font-semibold text-foreground">{law.title}</p>
                  <p className="text-xs text-muted-foreground">{law.status || law.excerpt}</p>
                </div>
                <Button variant="ghost" size="icon" className="rounded-full">
                  <Bookmark className="h-4 w-4" />
                </Button>
              </div>
            ))}
            {results.length === 0 && (
              <p className="text-sm text-muted-foreground py-6 text-center">Nenhum resultado.</p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
