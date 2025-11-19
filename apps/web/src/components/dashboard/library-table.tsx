import { libraryItems } from '@/data/mock';
import { Button } from '@/components/ui/button';
import { Eye, Share2, Trash2 } from 'lucide-react';

export function LibraryTable() {
  return (
    <section className="rounded-3xl border border-white/70 bg-white/90 p-5 shadow-soft">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="font-display text-xl text-foreground">Biblioteca</h2>
          <p className="text-sm text-muted-foreground">
            Gerencie e ative seus conteúdos com praticidade.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" className="rounded-full">
            Nova Pasta
          </Button>
          <Button className="rounded-full bg-primary text-primary-foreground">Compartilhar</Button>
        </div>
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th className="pb-2">Nome</th>
              <th className="pb-2">Tipo</th>
              <th className="pb-2">Tokens</th>
              <th className="pb-2">Atualizado</th>
              <th className="pb-2 text-right">Ações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline/40">
            {libraryItems.map((item) => (
              <tr key={item.id} className="text-foreground">
                <td className="py-3">{item.name}</td>
                <td className="py-3">
                  <span className="chip bg-lavender/70 text-foreground">{item.type}</span>
                </td>
                <td className="py-3">{item.tokens}</td>
                <td className="py-3 text-muted-foreground">{item.updatedAt}</td>
                <td className="py-3 text-right">
                  <div className="flex justify-end gap-2">
                    <IconButton icon={<Eye className="h-4 w-4" />} label="Visualizar" />
                    <IconButton icon={<Share2 className="h-4 w-4" />} label="Compartilhar" />
                    <IconButton icon={<Trash2 className="h-4 w-4" />} label="Excluir" />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function IconButton({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <button
      type="button"
      className="rounded-full border border-outline/50 p-2 text-muted-foreground transition hover:text-primary"
      aria-label={label}
    >
      {icon}
    </button>
  );
}

