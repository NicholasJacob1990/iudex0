import { webQueries } from '@/data/mock';
import { Input } from '@/components/ui/input';
import { Search, Clock } from 'lucide-react';

export function WebSearchPanel() {
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
        />
      </div>

      <div className="mt-5 space-y-2">
        {webQueries.map((query) => (
          <div
            key={query.id}
            className="flex items-center justify-between rounded-2xl border border-outline/40 bg-white/80 px-4 py-2 text-sm"
          >
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-muted-foreground" />
              <span>{query.query}</span>
            </div>
            <span className="text-xs text-muted-foreground">{query.date}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

