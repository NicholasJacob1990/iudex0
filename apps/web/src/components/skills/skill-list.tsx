'use client';

import { RefreshCcw, Wrench } from 'lucide-react';
import type { SkillLibraryItem } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface SkillListProps {
  items: SkillLibraryItem[];
  loading: boolean;
  onRefresh: () => Promise<void>;
}

const getTagValue = (tags: string[], prefix: string): string | null => {
  const match = tags.find((tag) => tag.startsWith(prefix));
  if (!match) return null;
  return match.replace(prefix, '').trim() || null;
};

export function SkillList({ items, loading, onRefresh }: SkillListProps) {
  return (
    <Card className="border-white/70 bg-white/95 shadow-soft">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">Skills publicadas</CardTitle>
        <Button variant="outline" size="sm" onClick={() => void onRefresh()} disabled={loading}>
          <RefreshCcw className="mr-2 h-3.5 w-3.5" />
          Atualizar
        </Button>
      </CardHeader>
      <CardContent>
        {loading ? (
          <p className="text-sm text-muted-foreground">Carregando skills...</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhuma skill publicada ainda.</p>
        ) : (
          <div className="space-y-3">
            {items.map((item) => {
              const tags = Array.isArray(item.tags) ? item.tags : [];
              const version = getTagValue(tags, 'skill_version:') || '1';
              const state = getTagValue(tags, 'state:') || 'active';
              const visibility = getTagValue(tags, 'visibility:') || 'personal';
              return (
                <div key={item.id} className="rounded-lg border border-slate-200 bg-white p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold">{item.name}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {item.updated_at ? new Date(item.updated_at).toLocaleString('pt-BR') : 'sem data'}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      <Badge variant="secondary">v{version}</Badge>
                      <Badge variant={state === 'active' ? 'default' : 'secondary'}>{state}</Badge>
                      <Badge variant="outline">{visibility}</Badge>
                    </div>
                  </div>
                  <div className="mt-2 flex items-center gap-1 text-[11px] text-muted-foreground">
                    <Wrench className="h-3 w-3" />
                    {tags.filter((tag) => tag !== 'skill').join(' • ') || 'sem metadados adicionais'}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
