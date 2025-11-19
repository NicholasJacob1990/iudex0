import { modelsBoard } from '@/data/mock';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { FileCheck } from 'lucide-react';

export function ModelsBoard() {
  return (
    <section className="rounded-3xl border border-white/70 bg-white/90 p-5 shadow-soft">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="font-display text-xl text-foreground">Modelos</h2>
          <p className="text-sm text-muted-foreground">Arraste e solte o modelo a ser seguido.</p>
        </div>
        <div className="flex items-center gap-3 text-xs font-semibold uppercase">
          <Toggle label="Limpeza automática" active />
          <Toggle label="Modo rigoroso" active />
        </div>
      </div>

      <div className="mt-4 grid gap-3">
        {modelsBoard.map((model) => (
          <div
            key={model.id}
            className={cn(
              'flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-outline/40 px-4 py-3',
              model.selected ? 'bg-primary/5' : 'bg-sand/60'
            )}
          >
            <div>
              <p className="font-semibold text-foreground">{model.title}</p>
              <p className="text-xs text-muted-foreground">{model.tokens} tokens</p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="rounded-full border-primary text-primary">
                Expandir
              </Button>
              <Button variant="ghost" size="sm" className="rounded-full border border-outline/50">
                Salvar
              </Button>
              <Button size="sm" className="rounded-full bg-primary text-primary-foreground">
                Seguir
              </Button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function Toggle({ label, active }: { label: string; active?: boolean }) {
  return (
    <span
      className={cn(
        'flex items-center gap-2 rounded-full px-3 py-1',
        active ? 'bg-primary/10 text-primary' : 'bg-sand text-muted-foreground'
      )}
    >
      <FileCheck className="h-3.5 w-3.5" />
      {label}
    </span>
  );
}

