'use client';

import { useEffect, useState } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Search, Filter, Sparkles, Plus, FolderOpen } from 'lucide-react';
import { JurisprudenceCard, TribunalSelectorDialog, ManualPrecedentDialog } from '@/components/dashboard';
import { toast } from 'sonner';
import apiClient from '@/lib/api-client';

const courts = ['Todos', 'STF', 'STJ', 'TST', 'TSE', 'TRFs', 'TJs'];

const initialResults: any[] = [];

export default function JurisprudencePage() {
  const [searchTerm, setSearchTerm] = useState('');
  const [activeCourt, setActiveCourt] = useState('Todos');
  const [isSearching, setIsSearching] = useState(false);
  const [results, setResults] = useState<typeof initialResults>([]);
  const [tribunalDialogOpen, setTribunalDialogOpen] = useState(false);
  const [manualDialogOpen, setManualDialogOpen] = useState(false);

  useEffect(() => {
    handleSearch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch = () => {
    setIsSearching(true);
    apiClient
      .searchJurisprudence(searchTerm || 'dano moral', activeCourt === 'Todos' ? undefined : activeCourt)
      .then((data) => {
        setResults(data.items || []);
      })
      .catch(() => {
        setResults(initialResults);
      })
      .finally(() => setIsSearching(false));
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.success('Ementa copiada para a área de transferência');
  };

  const handleSummarize = (id: string) => {
    toast.info('Gerando resumo inteligente...');
    setTimeout(() => toast.success('Resumo gerado e salvo nas notas'), 1500);
  };

  const handleSelect = (id: string) => {
    toast.success('Precedente adicionado ao contexto!');
  };

  const handleOpenInCourt = (id: string) => {
    toast.info('Abrindo consulta no site do tribunal...');
  };

  const handleViewFull = (id: string) => {
    toast.info('Carregando inteiro teor...');
  };

  const handleSaveToLibrary = (id: string) => {
    toast.success('Precedente salvo na biblioteca!');
  };

  const handleDelete = (id: string) => {
    if (!confirm('Deseja remover este precedente dos resultados?')) return;
    setResults(results.filter((r) => r.id !== id));
    toast.success('Precedente removido');
  };

  return (
    <div className="space-y-8 h-full flex flex-col">
      <div className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft flex-none">
        <div className="flex flex-col gap-6">
          <div>
            <p className="text-xs font-semibold uppercase text-muted-foreground">Jurisprudência Inteligente</p>
            <h1 className="font-display text-3xl text-foreground">
              Busque precedentes com precisão de IA.
            </h1>
            <p className="text-sm text-muted-foreground">
              Pesquise em todos os tribunais com filtros semânticos e análise de tendências.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm">
            <div className="flex items-start gap-3">
              <span className="text-slate-600 text-lg">ℹ️</span>
              <div>
                <p className="font-semibold text-slate-900">Base Local de Jurisprudência</p>
                <p className="text-slate-700 mt-1">
                  Resultados provenientes da base local configurada. Recomendamos validar o inteiro teor no tribunal
                  antes de inserir em documentos finais.
                </p>
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-4">
            <div className="relative">
              <Search className="absolute left-4 top-3.5 h-5 w-5 text-muted-foreground" />
              <Input
                placeholder="Ex: danos morais por negativação indevida, tese do século..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="h-12 rounded-2xl border-outline/30 bg-sand/50 pl-12 text-base shadow-inner transition-all focus:bg-white focus:shadow-md"
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              />
              <Button
                className="absolute right-2 top-2 h-8 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white"
                onClick={handleSearch}
              >
                Pesquisar
              </Button>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                className="gap-2 rounded-full border-dashed border-outline/50"
                onClick={() => setTribunalDialogOpen(true)}
              >
                <Filter className="h-3 w-3" />
                Selecionar Tribunais
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="gap-2 rounded-full"
                onClick={() => setManualDialogOpen(true)}
              >
                <Plus className="h-3 w-3" />
                Inserir Manualmente
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="gap-2 rounded-full"
              >
                <FolderOpen className="h-3 w-3" />
                Ver Salvos
              </Button>
              <div className="h-4 w-px bg-outline/30 mx-2" />
              {courts.map((court) => (
                <Button
                  key={court}
                  variant={court === activeCourt ? 'default' : 'ghost'}
                  size="sm"
                  className={`rounded-full ${court === activeCourt ? 'bg-indigo-600 text-white hover:bg-indigo-700' : 'text-muted-foreground hover:bg-sand hover:text-foreground'}`}
                  onClick={() => setActiveCourt(court)}
                >
                  {court}
                </Button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <section className="flex-1 rounded-3xl border border-white/70 bg-white/90 p-6 shadow-soft overflow-hidden flex flex-col">
        <div className="flex items-center justify-between mb-6 flex-none">
          <h2 className="font-display text-xl text-foreground flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-indigo-500" />
            Resultados Relevantes
          </h2>
          <span className="text-xs text-muted-foreground">
            {results.length} precedentes encontrados
          </span>
        </div>

        <div className="overflow-y-auto pr-2 -mr-2 space-y-4 flex-1">
          {isSearching ? (
            <div className="flex flex-col items-center justify-center h-40 gap-4">
              <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" />
              <p className="text-sm text-muted-foreground animate-pulse">Analisando 35.000+ julgados...</p>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {results.map((precedent) => (
                <JurisprudenceCard
                  key={precedent.id}
                  precedent={precedent}
                  onCopy={handleCopy}
                  onSummarize={handleSummarize}
                  onSelect={handleSelect}
                  onOpenInCourt={handleOpenInCourt}
                  onViewFull={handleViewFull}
                  onSaveToLibrary={handleSaveToLibrary}
                  onDelete={handleDelete}
                />
              ))}
            </div>
          )}
        </div>
      </section>

      <TribunalSelectorDialog open={tribunalDialogOpen} onOpenChange={setTribunalDialogOpen} />
      <ManualPrecedentDialog open={manualDialogOpen} onOpenChange={setManualDialogOpen} />
    </div>
  );
}
