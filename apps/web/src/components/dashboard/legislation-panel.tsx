import { legislationSaved } from '@/data/mock';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Search, Bookmark } from 'lucide-react';

export function LegislationPanel() {
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
          Ver legislações salvas ({legislationSaved.length})
        </Button>
      </div>

      <div className="mt-4 flex flex-col gap-3">
        <div className="relative">
          <Search className="absolute left-4 top-3 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Ex: proteção de dados, contraditório..."
            className="h-12 rounded-2xl border-transparent bg-sand pl-11"
          />
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {legislationSaved.map((law) => (
            <div
              key={law.id}
              className="flex items-center justify-between rounded-2xl border border-outline/40 bg-white/80 px-4 py-3"
            >
              <div>
                <p className="font-semibold text-foreground">{law.title}</p>
                <p className="text-xs text-muted-foreground">{law.status}</p>
              </div>
              <Button variant="ghost" size="icon" className="rounded-full">
                <Bookmark className="h-4 w-4" />
              </Button>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

