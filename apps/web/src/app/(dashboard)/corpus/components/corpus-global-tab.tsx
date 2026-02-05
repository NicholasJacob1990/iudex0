'use client';

import { Scale, Gavel, BookOpen, FileSignature, ExternalLink } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { useCorpusCollections } from '../hooks/use-corpus';
import { useState } from 'react';

const collectionIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  lei: Scale,
  jurisprudencia: Gavel,
  doutrina: BookOpen,
  pecas_modelo: FileSignature,
};

const collectionColors: Record<string, { bg: string; text: string; badge: string }> = {
  lei: { bg: 'bg-indigo-50', text: 'text-indigo-600', badge: 'bg-indigo-100 text-indigo-700' },
  jurisprudencia: { bg: 'bg-purple-50', text: 'text-purple-600', badge: 'bg-purple-100 text-purple-700' },
  doutrina: { bg: 'bg-emerald-50', text: 'text-emerald-600', badge: 'bg-emerald-100 text-emerald-700' },
  pecas_modelo: { bg: 'bg-amber-50', text: 'text-amber-600', badge: 'bg-amber-100 text-amber-700' },
};

export function CorpusGlobalTab() {
  const { data: collections, isLoading } = useCorpusCollections();
  const [searchQuery, setSearchQuery] = useState('');

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-full rounded-xl" />
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-48 rounded-2xl" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-white/70 bg-white/95 p-4 shadow-soft">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium text-foreground">Base de conhecimento publica</p>
            <p className="text-xs text-muted-foreground">
              Legislacao, jurisprudencia e doutrina indexadas pela plataforma. Somente leitura.
            </p>
          </div>
          <Input
            placeholder="Buscar no corpus global..."
            className="max-w-xs rounded-xl"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {collections?.filter((collection) =>
          !searchQuery.trim() ||
          collection.display_name.toLowerCase().includes(searchQuery.trim().toLowerCase()) ||
          collection.name.toLowerCase().includes(searchQuery.trim().toLowerCase())
        ).map((collection) => {
          const Icon = collectionIcons[collection.name] ?? BookOpen;
          const colors = collectionColors[collection.name] ?? collectionColors.doutrina;

          return (
            <Card
              key={collection.name}
              className="group rounded-2xl border-white/70 bg-white/95 shadow-soft transition-all hover:shadow-md"
            >
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${colors.bg}`}>
                      <Icon className={`h-5 w-5 ${colors.text}`} />
                    </div>
                    <div>
                      <CardTitle className="text-base">{collection.display_name}</CardTitle>
                      <p className="text-xs text-muted-foreground">{collection.description}</p>
                    </div>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge className={`rounded-full text-[10px] ${colors.badge} border-0`}>
                      {collection.document_count.toLocaleString('pt-BR')} documentos
                    </Badge>
                  </div>
                  <Badge variant="outline" className="rounded-full text-[10px]">
                    {collection.status}
                  </Badge>
                </div>

                <div className="rounded-xl bg-muted/50 p-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                    Exemplo de busca
                  </p>
                  <p className="text-xs text-muted-foreground italic">
                    {collection.name === 'lei' && '"Art. 5o da Constituicao Federal — direitos fundamentais"'}
                    {collection.name === 'juris' && '"Sumula 331 TST — terceirizacao licita"'}
                    {collection.name === 'doutrina' && '"Responsabilidade civil objetiva — risco da atividade"'}
                    {collection.name === 'pecas_modelo' && '"Peticao inicial — acao de cobranca"'}
                  </p>
                </div>

                <Button
                  variant="outline"
                  size="sm"
                  className="w-full rounded-full gap-2 text-xs"
                >
                  <ExternalLink className="h-3 w-3" />
                  Explorar colecao
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
