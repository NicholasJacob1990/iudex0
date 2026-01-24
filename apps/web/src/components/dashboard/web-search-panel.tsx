import { useEffect, useMemo, useState } from 'react';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Search, Clock, ExternalLink, SlidersHorizontal } from 'lucide-react';
import apiClient from '@/lib/api-client';

type WebSearchItem = {
  id: string;
  title?: string;
  url?: string;
  snippet?: string;
  date?: string | null;
  last_updated?: string | null;
  images?: unknown;
  source?: string;
  query?: string;
};

export function WebSearchPanel() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<WebSearchItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [limit, setLimit] = useState(10);
  const [multiQuery, setMultiQuery] = useState(true);
  const [useCache, setUseCache] = useState(true);
  const [country, setCountry] = useState('BR');
  const [domainFilter, setDomainFilter] = useState('');
  const [languageFilter, setLanguageFilter] = useState('pt');
  const [recencyFilter, setRecencyFilter] = useState<'day' | 'week' | 'month' | 'year' | ''>('');
  const [searchMode, setSearchMode] = useState<'web' | 'academic' | 'sec'>('web');
  const [searchAfterDate, setSearchAfterDate] = useState('');
  const [searchBeforeDate, setSearchBeforeDate] = useState('');
  const [lastUpdatedAfter, setLastUpdatedAfter] = useState('');
  const [lastUpdatedBefore, setLastUpdatedBefore] = useState('');
  const [maxTokens, setMaxTokens] = useState<string>('');
  const [maxTokensPerPage, setMaxTokensPerPage] = useState<string>('');
  const [returnImages, setReturnImages] = useState(false);
  const [returnSnippets, setReturnSnippets] = useState(true);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [meta, setMeta] = useState<{ total: number; source?: string; cached?: boolean; queries?: string[] }>({
    total: 0,
  });

  const parsedDomainFilter = useMemo(() => {
    return domainFilter
      .split(/[,\n]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }, [domainFilter]);

  const parsedLanguageFilter = useMemo(() => {
    return languageFilter
      .split(/[,\n]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }, [languageFilter]);

  useEffect(() => {
    handleSearch('repercussão geral');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch = async (value?: string) => {
    const term = value ?? query;
    if (!term.trim()) return;
    setIsLoading(true);
    try {
      const parsedMaxTokens = Number(maxTokens);
      const parsedMaxTokensPerPage = Number(maxTokensPerPage);
      const data = await apiClient.searchWeb(term, {
        limit,
        multi_query: multiQuery,
        use_cache: useCache,
        country: country.trim() || undefined,
        domain_filter: parsedDomainFilter.length ? parsedDomainFilter : undefined,
        language_filter: parsedLanguageFilter.length ? parsedLanguageFilter : undefined,
        recency_filter: recencyFilter || undefined,
        search_mode: searchMode,
        search_after_date: searchAfterDate.trim() || undefined,
        search_before_date: searchBeforeDate.trim() || undefined,
        last_updated_after: lastUpdatedAfter.trim() || undefined,
        last_updated_before: lastUpdatedBefore.trim() || undefined,
        max_tokens: Number.isFinite(parsedMaxTokens) ? parsedMaxTokens : undefined,
        max_tokens_per_page: Number.isFinite(parsedMaxTokensPerPage) ? parsedMaxTokensPerPage : undefined,
        return_images: returnImages,
        return_snippets: returnSnippets,
      });
      setResults(data.items || []);
      setMeta({
        total: typeof data.total === 'number' ? data.total : (data.items?.length || 0),
        source: data.source,
        cached: data.cached,
        queries: data.queries,
      });
    } catch (error) {
      setResults([]);
      setMeta({ total: 0 });
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

      <div className="mt-4 flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-600">
        <div className="flex items-center gap-2">
          <span className="font-semibold">Multi‑query</span>
          <Switch checked={multiQuery} onCheckedChange={setMultiQuery} />
        </div>
        <div className="flex items-center gap-2">
          <span className="font-semibold">Cache</span>
          <Switch checked={useCache} onCheckedChange={setUseCache} />
        </div>
        <div className="flex items-center gap-2">
          <span className="font-semibold">País</span>
          <Input
            className="h-8 w-20 rounded-xl bg-white text-xs"
            value={country}
            onChange={(e) => setCountry(e.target.value)}
            placeholder="BR"
          />
        </div>
        <div className="flex items-center gap-2">
          <span className="font-semibold">Recência</span>
          <Select value={recencyFilter} onValueChange={(v) => setRecencyFilter(v as any)}>
            <SelectTrigger className="h-8 w-[130px] rounded-xl bg-white text-xs">
              <SelectValue placeholder="(tudo)" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">(tudo)</SelectItem>
              <SelectItem value="day">dia</SelectItem>
              <SelectItem value="week">semana</SelectItem>
              <SelectItem value="month">mês</SelectItem>
              <SelectItem value="year">ano</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-semibold">Escopo</span>
          <Select value={searchMode} onValueChange={(v) => setSearchMode(v as any)}>
            <SelectTrigger className="h-8 w-[130px] rounded-xl bg-white text-xs">
              <SelectValue placeholder="web" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="web">web</SelectItem>
              <SelectItem value="academic">acadêmico</SelectItem>
              <SelectItem value="sec">SEC</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <button
          type="button"
          className="ml-auto inline-flex items-center gap-1 rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-100"
          onClick={() => setShowAdvanced((v) => !v)}
        >
          <SlidersHorizontal className="h-4 w-4" />
          Filtros
        </button>
      </div>

      {showAdvanced && (
        <div className="mt-3 grid grid-cols-1 gap-3 rounded-2xl border border-slate-200 bg-white/60 p-4 text-xs md:grid-cols-2">
          <div>
            <p className="mb-1 font-semibold text-slate-700">Domínios (allow/deny list)</p>
            <Input
              className="h-9 rounded-xl bg-white text-xs"
              value={domainFilter}
              onChange={(e) => setDomainFilter(e.target.value)}
              placeholder="stf.jus.br, stj.jus.br ou -reddit.com"
            />
          </div>
          <div>
            <p className="mb-1 font-semibold text-slate-700">Idiomas (ISO 639‑1)</p>
            <Input
              className="h-9 rounded-xl bg-white text-xs"
              value={languageFilter}
              onChange={(e) => setLanguageFilter(e.target.value)}
              placeholder="pt, en"
            />
          </div>
          <div>
            <p className="mb-1 font-semibold text-slate-700">Publicado após (m/d/yyyy)</p>
            <Input
              className="h-9 rounded-xl bg-white text-xs"
              value={searchAfterDate}
              onChange={(e) => setSearchAfterDate(e.target.value)}
              placeholder="1/1/2024"
            />
          </div>
          <div>
            <p className="mb-1 font-semibold text-slate-700">Publicado antes (m/d/yyyy)</p>
            <Input
              className="h-9 rounded-xl bg-white text-xs"
              value={searchBeforeDate}
              onChange={(e) => setSearchBeforeDate(e.target.value)}
              placeholder="12/31/2024"
            />
          </div>
          <div>
            <p className="mb-1 font-semibold text-slate-700">Atualizado após (m/d/yyyy)</p>
            <Input
              className="h-9 rounded-xl bg-white text-xs"
              value={lastUpdatedAfter}
              onChange={(e) => setLastUpdatedAfter(e.target.value)}
              placeholder="7/1/2025"
            />
          </div>
          <div>
            <p className="mb-1 font-semibold text-slate-700">Atualizado antes (m/d/yyyy)</p>
            <Input
              className="h-9 rounded-xl bg-white text-xs"
              value={lastUpdatedBefore}
              onChange={(e) => setLastUpdatedBefore(e.target.value)}
              placeholder="12/30/2025"
            />
          </div>
          <div>
            <p className="mb-1 font-semibold text-slate-700">Max tokens (total)</p>
            <Input
              className="h-9 rounded-xl bg-white text-xs"
              value={maxTokens}
              onChange={(e) => setMaxTokens(e.target.value)}
              placeholder="25000"
              inputMode="numeric"
            />
          </div>
          <div>
            <p className="mb-1 font-semibold text-slate-700">Tokens por página</p>
            <Input
              className="h-9 rounded-xl bg-white text-xs"
              value={maxTokensPerPage}
              onChange={(e) => setMaxTokensPerPage(e.target.value)}
              placeholder="2048"
              inputMode="numeric"
            />
          </div>
          <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
            <div>
              <p className="font-semibold text-slate-700">Imagens</p>
              <p className="text-[10px] text-slate-500">return_images</p>
            </div>
            <Switch checked={returnImages} onCheckedChange={setReturnImages} />
          </div>
          <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
            <div>
              <p className="font-semibold text-slate-700">Snippets</p>
              <p className="text-[10px] text-slate-500">return_snippets</p>
            </div>
            <Switch checked={returnSnippets} onCheckedChange={setReturnSnippets} />
          </div>
          <div>
            <p className="mb-1 font-semibold text-slate-700">Limite de resultados</p>
            <Input
              className="h-9 rounded-xl bg-white text-xs"
              value={String(limit)}
              onChange={(e) => setLimit(Math.max(1, Math.min(20, Number(e.target.value) || 10)))}
              placeholder="10"
              inputMode="numeric"
            />
          </div>
        </div>
      )}

      {(meta.source || typeof meta.cached === 'boolean') && (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {meta.source && <span>Fonte: <span className="font-semibold text-slate-700">{meta.source}</span></span>}
          {typeof meta.cached === 'boolean' && <span>Cache: <span className="font-semibold text-slate-700">{meta.cached ? 'sim' : 'não'}</span></span>}
          <span>Total: <span className="font-semibold text-slate-700">{meta.total}</span></span>
          {Array.isArray(meta.queries) && meta.queries.length > 0 && (
            <span className="truncate">Queries: <span className="font-semibold text-slate-700">{meta.queries.slice(0, 4).join(' • ')}</span></span>
          )}
        </div>
      )}

      <div className="mt-5 space-y-2">
        {isLoading ? (
          <p className="text-center text-sm text-muted-foreground py-4">Buscando na web...</p>
        ) : results.length ? (
          results.map((item) => (
            <div
              key={item.id}
              className="flex flex-col gap-1 rounded-2xl border border-outline/40 bg-white/80 px-4 py-2 text-sm"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2 text-muted-foreground">
                <Clock className="h-4 w-4" />
                <a
                  href={item.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="font-semibold text-foreground hover:underline"
                >
                  {item.title || item.url}
                </a>
              </div>
                {item.url && (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="mt-0.5 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-slate-700"
                    title="Abrir fonte"
                  >
                    <ExternalLink className="h-4 w-4" />
                  </a>
                )}
              </div>
              {item.query && multiQuery && (
                <p className="text-[10px] text-muted-foreground">Query: {item.query}</p>
              )}
              {item.snippet && <p className="text-xs text-muted-foreground">{item.snippet}</p>}
              <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-muted-foreground">
                {item.source && <span className="rounded-full bg-slate-100 px-2 py-1">{item.source}</span>}
                {item.date && <span className="rounded-full bg-slate-100 px-2 py-1">Publicado: {item.date}</span>}
                {item.last_updated && <span className="rounded-full bg-slate-100 px-2 py-1">Atualizado: {item.last_updated}</span>}
              </div>
              {(() => {
                const raw = item.images;
                const urls = Array.isArray(raw)
                  ? raw
                    .map((img: any) => {
                      if (!img) return '';
                      if (typeof img === 'string') return img;
                      if (typeof img.url === 'string') return img.url;
                      if (typeof img.src === 'string') return img.src;
                      return '';
                    })
                    .filter((u: string) => !!u)
                  : [];
                if (!urls.length) return null;
                return (
                  <div className="mt-2 grid grid-cols-3 gap-2">
                    {urls.slice(0, 3).map((u: string) => (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        key={u}
                        src={u}
                        alt=""
                        loading="lazy"
                        className="h-20 w-full rounded-xl object-cover"
                      />
                    ))}
                  </div>
                );
              })()}
            </div>
          ))
        ) : (
          <p className="text-center text-sm text-muted-foreground py-4">Nenhum resultado encontrado.</p>
        )}
      </div>
    </section>
  );
}
