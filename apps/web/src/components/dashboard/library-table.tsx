import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Eye, Share2, Trash2, FolderInput, Search, Filter, ArrowUpDown } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { useLibraryStore } from '@/stores';
import { formatDateTime } from '@/lib/utils';
import { toast } from 'sonner';
import { ShareDialog } from './share-dialog';

type SortField = 'name' | 'updated_at';
type SortOrder = 'asc' | 'desc';

export function LibraryTable() {
  const { items, isLoading, fetchItems, deleteItem } = useLibraryStore();
  const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<string>('all');
  const [sortField, setSortField] = useState<SortField>('updated_at');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');

  useEffect(() => {
    fetchItems().catch(() => {
      // erros tratados no interceptor
    });
  }, [fetchItems]);

  const handleDelete = async (id: string) => {
    if (!confirm('Deseja excluir este item da biblioteca?')) return;
    await deleteItem(id);
    setSelectedItems((prev) => {
      const newSet = new Set(prev);
      newSet.delete(id);
      return newSet;
    });
  };

  const handleBulkDelete = async () => {
    if (selectedItems.size === 0) return;
    if (!confirm(`Deseja excluir ${selectedItems.size} item(ns)?`)) return;

    for (const id of selectedItems) {
      await deleteItem(id);
    }
    setSelectedItems(new Set());
    toast.success(`${selectedItems.size} item(ns) excluído(s)`);
  };

  const toggleSelectAll = () => {
    if (selectedItems.size === filteredItems.length) {
      setSelectedItems(new Set());
    } else {
      setSelectedItems(new Set(filteredItems.map((item) => item.id)));
    }
  };

  const toggleSelectItem = (id: string) => {
    const newSet = new Set(selectedItems);
    if (newSet.has(id)) {
      newSet.delete(id);
    } else {
      newSet.add(id);
    }
    setSelectedItems(newSet);
  };

  const handleItemAction = (action: string, itemName: string, itemId?: string) => {
    if (action === 'Compartilhar' && itemId) {
      setShareItem({ id: itemId, name: itemName });
      setShareDialogOpen(true);
    } else {
      toast.info(`${action}: ${itemName}`);
    }
  };

  const [shareDialogOpen, setShareDialogOpen] = useState(false);
  const [shareItem, setShareItem] = useState<{ id: string; name: string } | null>(null);

  // Filter and sort
  const filteredItems = items
    .filter((item) => {
      const matchesSearch = item.name.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesType = filterType === 'all' || item.type === filterType;
      return matchesSearch && matchesType;
    })
    .sort((a, b) => {
      const aValue = a[sortField];
      const bValue = b[sortField];
      const comparison = aValue < bValue ? -1 : aValue > bValue ? 1 : 0;
      return sortOrder === 'asc' ? comparison : -comparison;
    });

  const uniqueTypes = Array.from(new Set(items.map((item) => item.type)));

  return (
    <section className="rounded-3xl border border-white/70 bg-white/90 p-5 shadow-soft">
      {/* Header */}
      <div className="flex flex-col gap-4 mb-4">
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="font-display text-xl text-foreground">Biblioteca</h2>
            <p className="text-sm text-muted-foreground">
              Gerencie e ative seus conteúdos com praticidade.
            </p>
          </div>
          <div className="flex gap-2">
            {selectedItems.size > 0 && (
              <Button
                variant="outline"
                size="sm"
                className="rounded-full gap-2 text-xs text-destructive"
                onClick={handleBulkDelete}
              >
                <Trash2 className="h-3 w-3" />
                Excluir ({selectedItems.size})
              </Button>
            )}
          </div>
        </div>

        {/* Search and Filters */}
        <div className="flex flex-wrap gap-2">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Buscar por nome..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-9 pl-9 rounded-full text-xs"
            />
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="rounded-full gap-2 text-xs">
                <Filter className="h-3 w-3" />
                {filterType === 'all' ? 'Todos os tipos' : filterType}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuItem onClick={() => setFilterType('all')}>
                Todos os tipos
              </DropdownMenuItem>
              {uniqueTypes.map((type) => (
                <DropdownMenuItem key={type} onClick={() => setFilterType(type)}>
                  {type}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="rounded-full gap-2 text-xs">
                <ArrowUpDown className="h-3 w-3" />
                Ordenar
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuItem onClick={() => { setSortField('name'); setSortOrder('asc'); }}>
                Nome (A-Z)
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => { setSortField('name'); setSortOrder('desc'); }}>
                Nome (Z-A)
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => { setSortField('updated_at'); setSortOrder('desc'); }}>
                Mais recentes
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => { setSortField('updated_at'); setSortOrder('asc'); }}>
                Mais antigos
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        {isLoading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Carregando biblioteca...</p>
        ) : filteredItems.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            {searchQuery || filterType !== 'all' ? 'Nenhum item encontrado.' : 'Nenhum item na biblioteca ainda.'}
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground border-b border-outline/20">
                <th className="pb-3 w-8">
                  <Checkbox
                    checked={selectedItems.size === filteredItems.length && filteredItems.length > 0}
                    onCheckedChange={toggleSelectAll}
                  />
                </th>
                <th className="pb-3">Nome</th>
                <th className="pb-3">Tipo</th>
                <th className="pb-3">Tags</th>
                <th className="pb-3">Atualizado</th>
                <th className="pb-3 text-right">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline/20">
              {filteredItems.map((item) => (
                <tr key={item.id} className="text-foreground hover:bg-sand/30 transition-colors">
                  <td className="py-3">
                    <Checkbox
                      checked={selectedItems.has(item.id)}
                      onCheckedChange={() => toggleSelectItem(item.id)}
                    />
                  </td>
                  <td className="py-3 font-medium">{item.name}</td>
                  <td className="py-3">
                    <span className="chip bg-lavender/70 text-foreground text-xs">{item.type}</span>
                  </td>
                  <td className="py-3 text-xs text-muted-foreground">
                    {item.tags?.length ? item.tags.join(', ') : '—'}
                  </td>
                  <td className="py-3 text-muted-foreground text-xs">{formatDateTime(item.updated_at)}</td>
                  <td className="py-3 text-right">
                    <div className="flex justify-end gap-1">
                      <IconButton
                        icon={<Eye className="h-4 w-4" />}
                        label="Visualizar"
                        onClick={() => handleItemAction('Visualizar', item.name)}
                      />
                      <IconButton
                        icon={<FolderInput className="h-4 w-4" />}
                        label="Carregar"
                        onClick={() => handleItemAction('Carregar na aba', item.name)}
                      />
                      <IconButton
                        icon={<Share2 className="h-4 w-4" />}
                        label="Compartilhar"
                        onClick={() => handleItemAction('Compartilhar', item.name, item.id)}
                      />
                      <IconButton
                        icon={<Trash2 className="h-4 w-4" />}
                        label="Excluir"
                        onClick={() => handleDelete(item.id)}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <ShareDialog
        open={shareDialogOpen}
        onOpenChange={setShareDialogOpen}
        itemName={shareItem?.name || ''}
        itemType="item"
      />
    </section>
  );
}

function IconButton({ icon, label, onClick }: { icon: React.ReactNode; label: string; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-full border border-outline/50 p-2 text-muted-foreground transition hover:text-primary hover:border-primary"
      aria-label={label}
      title={label}
    >
      {icon}
    </button>
  );
}
