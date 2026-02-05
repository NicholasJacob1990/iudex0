'use client';

import { useState, useEffect, useMemo } from 'react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chat-store';
import { useContextStore } from '@/stores/context-store';
import { useAuthStore } from '@/stores/auth-store';
import { ISO_3166_ALPHA2 } from '@/data/iso-3166-alpha2';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Checkbox } from '@/components/ui/checkbox';
import { Switch } from '@/components/ui/switch';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Input } from '@/components/ui/input';
import {
  Globe,
  Paperclip,
  Scale,
  ScrollText,
  Building2,
  BookOpen,
  FileText,
  Lock,
  Plug,
  ChevronDown,
  FolderOpen,
  Database,
  Search,
  X,
  Check,
} from 'lucide-react';
import apiClient from '@/lib/api-client';

// Source category types
type CorpusSourceId = 'legislacao' | 'jurisprudencia' | 'pecas_modelo' | 'doutrina' | 'sei';
type TabId = 'sources' | 'jurisdictions' | 'private' | 'connectors';
type GlobalJurisdictionId = string;
type RegionalSourceId = string;

interface CorpusSource {
  id: CorpusSourceId;
  label: string;
  icon: React.ReactNode;
  enabled: boolean;
}

interface AttachmentItem {
  id: string;
  name: string;
  tokens?: number;
  enabled: boolean;
}

interface PrivateCorpusProject {
  id: string;
  name: string;
  enabled: boolean;
  scope?: string | null;
}

interface OrgTeam {
  id: string;
  name: string;
  description?: string | null;
}

interface McpConnector {
  label: string;
  url: string;
  enabled: boolean;
}

interface RegionalSourceItem {
  id: RegionalSourceId;
  label: string;
  jurisdiction: string;
  collections: string[];
  domains: string[];
  description?: string | null;
  status?: string | null;
  sync?: string | null;
}

const SOURCE_ICONS: Record<string, React.ReactNode> = {
  legislacao: <ScrollText className="h-3.5 w-3.5" />,
  jurisprudencia: <Scale className="h-3.5 w-3.5" />,
  bnp: <Building2 className="h-3.5 w-3.5" />,
  pecas_modelo: <FileText className="h-3.5 w-3.5" />,
  doutrina: <BookOpen className="h-3.5 w-3.5" />,
  sei: <Database className="h-3.5 w-3.5" />,
  web: <Globe className="h-3.5 w-3.5" />,
  attachments: <Paperclip className="h-3.5 w-3.5" />,
  private: <Lock className="h-3.5 w-3.5" />,
  mcp: <Plug className="h-3.5 w-3.5" />,
};

const TAB_CONFIG: Array<{ id: TabId; label: string; icon: React.ReactNode }> = [
  { id: 'sources', label: 'Fontes', icon: <Database className="h-3.5 w-3.5" /> },
  { id: 'jurisdictions', label: 'Jurisdições', icon: <Globe className="h-3.5 w-3.5" /> },
  { id: 'private', label: 'Privado', icon: <Lock className="h-3.5 w-3.5" /> },
  { id: 'connectors', label: 'Conectores', icon: <Plug className="h-3.5 w-3.5" /> },
];

const DEFAULT_CORPUS_SOURCES: CorpusSource[] = [
  { id: 'legislacao', label: 'Legislação', icon: SOURCE_ICONS.legislacao, enabled: true },
  { id: 'jurisprudencia', label: 'Jurisprudência', icon: SOURCE_ICONS.jurisprudencia, enabled: true },
  { id: 'pecas_modelo', label: 'Peças Modelo', icon: SOURCE_ICONS.pecas_modelo, enabled: false },
  { id: 'doutrina', label: 'Doutrina', icon: SOURCE_ICONS.doutrina, enabled: false },
  { id: 'sei', label: 'SEI', icon: SOURCE_ICONS.sei, enabled: false },
];

const CORPUS_SOURCE_TO_RAG: Record<CorpusSourceId, string> = {
  legislacao: 'lei',
  jurisprudencia: 'juris',
  pecas_modelo: 'pecas_modelo',
  doutrina: 'doutrina',
  sei: 'sei',
};

const toFlagEmoji = (regionCode: string): string => {
  const code = String(regionCode || '').trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(code)) return '🏳️';
  const points = code.split('').map((c) => 127397 + c.charCodeAt(0));
  return String.fromCodePoint(...points);
};

const toRegionalFlagEmoji = (jurisdictionCode: string): string => {
  const code = String(jurisdictionCode || '').trim().toUpperCase();
  if (code === 'INT') return '🌍';
  if (code === 'UK') return toFlagEmoji('GB');
  return toFlagEmoji(code);
};

// Build jurisdictions list (safe across browsers)
const buildJurisdictions = (): Array<{ id: GlobalJurisdictionId; label: string; flag: string }> => {
  const items: Array<{ id: GlobalJurisdictionId; label: string; flag: string }> = [];

  // Special jurisdictions
  items.push({ id: 'INT', label: 'Internacional', flag: '🌍' });
  items.push({ id: 'EU', label: 'União Europeia', flag: '🇪🇺' });

  const displayNames = (() => {
    try {
      return new Intl.DisplayNames(['pt-BR'], { type: 'region' });
    } catch {
      return null;
    }
  })();

  const getLabel = (alpha2: string): string => {
    const normalized = String(alpha2 || '').trim().toUpperCase();
    return displayNames?.of(normalized) || normalized;
  };

  const pushRegion = (alpha2: string) => {
    const normalized = String(alpha2 || '').trim().toUpperCase();
    if (!/^[A-Z]{2}$/.test(normalized)) return;
    const id = normalized === 'GB' ? 'UK' : normalized;
    const flag = normalized === 'GB' ? toFlagEmoji('GB') : toFlagEmoji(normalized);
    items.push({ id, label: getLabel(normalized), flag });
  };

  // NOTE: Do not use Intl.supportedValuesOf('region') here.
  // Some environments implement supportedValuesOf but throw RangeError for 'region'.
  for (const code of ISO_3166_ALPHA2) pushRegion(code);

  // Dedupe and sort
  const seen = new Set<string>();
  const unique = items.filter((i) => {
    const key = String(i.id || '').trim().toUpperCase();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  unique.sort((a, b) => a.label.localeCompare(b.label, 'pt-BR'));
  return unique;
};

const ragSourceToCorpusId = (rag: string): CorpusSourceId | null => {
  const normalized = String(rag || '').trim().toLowerCase();
  const entry = Object.entries(CORPUS_SOURCE_TO_RAG).find(([, v]) => v === normalized);
  return (entry?.[0] as CorpusSourceId) || null;
};

export function SourcesBadge() {
  const [open, setOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<TabId>('sources');
  const { user } = useAuthStore();
  const [jurisdictionQuery, setJurisdictionQuery] = useState('');
  const [regionalSourceQuery, setRegionalSourceQuery] = useState('');

  // Chat store state
  const {
    webSearch,
    setWebSearch,
    mcpToolCalling,
    setMcpToolCalling,
    mcpUseAllServers,
    setMcpUseAllServers,
    mcpServerLabels,
    setMcpServerLabels,
    ragScope,
    setRagScope,
    ragSources,
    setRagSources,
    ragSelectedGroups,
    setRagSelectedGroups,
    toggleRagSelectedGroup,
    clearRagSelectedGroups,
    ragAllowGroups,
    setRagAllowGroups,
    ragGlobalJurisdictions,
    setRagGlobalJurisdictions,
    toggleRagGlobalJurisdiction,
    clearRagGlobalJurisdictions,
    ragGlobalSourceIds,
    setRagGlobalSourceIds,
    toggleRagGlobalSourceId,
    clearRagGlobalSourceIds,
  } = useChatStore();

  // Context store state
  const { items: contextItems } = useContextStore();

  // Local state
  const [corpusSources, setCorpusSources] = useState<CorpusSource[]>(() => {
    const selected = new Set((ragSources || []).map((s) => ragSourceToCorpusId(s)).filter(Boolean) as CorpusSourceId[]);
    return DEFAULT_CORPUS_SOURCES.map((src) => ({ ...src, enabled: selected.has(src.id) }));
  });
  const [privateProjects, setPrivateProjects] = useState<PrivateCorpusProject[]>([]);
  const [myTeams, setMyTeams] = useState<OrgTeam[]>([]);
  const [teamsLoading, setTeamsLoading] = useState(false);
  const [mcpServers, setMcpServers] = useState<McpConnector[]>([]);
  const [mcpLoading, setMcpLoading] = useState(false);
  const [regionalSources, setRegionalSources] = useState<RegionalSourceItem[]>([]);
  const [regionalSourcesLoading, setRegionalSourcesLoading] = useState(false);
  const [privateProjectsLoading, setPrivateProjectsLoading] = useState(false);
  const [privateProjectsLoaded, setPrivateProjectsLoaded] = useState(false);

  // Attachment items
  const attachmentItems: AttachmentItem[] = useMemo(() => {
    return contextItems
      .filter((item) => item.type === 'file' || item.type === 'audio')
      .map((item) => ({
        id: item.id,
        name: item.name,
        tokens: undefined,
        enabled: true,
      }));
  }, [contextItems]);

  // Load MCP servers
  useEffect(() => {
    if (!open || !mcpToolCalling) return;
    if (mcpServers.length > 0) return;

    setMcpLoading(true);
    apiClient
      .getMcpServers()
      .then((res) => {
        const list = Array.isArray(res?.servers) ? res.servers : [];
        const servers = list
          .map((s: any) => ({
            label: String(s?.label || '').trim(),
            url: String(s?.url || '').trim(),
            enabled: mcpUseAllServers || mcpServerLabels.includes(String(s?.label || '').trim()),
          }))
          .filter((s: McpConnector) => s.label && s.url);
        setMcpServers(servers);
      })
      .catch(() => setMcpServers([]))
      .finally(() => setMcpLoading(false));
  }, [open, mcpToolCalling, mcpUseAllServers, mcpServerLabels, mcpServers.length]);

  // Load Regional Sources
  useEffect(() => {
    if (!open) return;
    if (regionalSources.length > 0) return;
    setRegionalSourcesLoading(true);
    (async () => {
      try {
        const anyClient = apiClient as any;
        const payload =
          typeof anyClient?.getCorpusRegionalSources === 'function'
            ? await anyClient.getCorpusRegionalSources()
            : await (async () => {
              const res = await anyClient.fetchWithAuth('/corpus/sources/regional', { method: 'GET' });
              if (!res.ok) throw new Error(`HTTP ${res.status}`);
              return await res.json();
            })();

        const list = Array.isArray((payload as any)?.sources) ? (payload as any).sources : [];
        const items = list
          .map((s: any) => ({
            id: String(s?.id || '').trim(),
            label: String(s?.label || '').trim(),
            jurisdiction: String(s?.jurisdiction || '').trim().toUpperCase(),
            collections: Array.isArray(s?.collections)
              ? s.collections.map((c: any) => String(c || '').trim()).filter(Boolean)
              : [],
            domains: Array.isArray(s?.domains)
              ? s.domains.map((d: any) => String(d || '').trim()).filter(Boolean)
              : [],
            description: s?.description ?? null,
            status: s?.status ?? null,
            sync: s?.sync ?? null,
          }))
          .filter((s: RegionalSourceItem) => s.id && s.label && s.jurisdiction);
        setRegionalSources(items);
      } catch {
        setRegionalSources([]);
      } finally {
        setRegionalSourcesLoading(false);
      }
    })();
  }, [open, regionalSources.length]);

  // Load org teams (try even without organization_id — API returns empty if none)
  useEffect(() => {
    if (!open) return;
    if (myTeams.length > 0) return;

    setTeamsLoading(true);
    apiClient
      .getMyOrgTeams()
      .then((res) => {
        const teams = Array.isArray(res) ? res : [];
        const normalized = teams
          .map((t: any) => ({
            id: String(t?.id || '').trim(),
            name: String(t?.name || '').trim(),
            description: t?.description ?? null,
          }))
          .filter((t: OrgTeam) => t.id && t.name);
        setMyTeams(normalized);
      })
      .catch(() => setMyTeams([]))
      .finally(() => setTeamsLoading(false));
  }, [open, myTeams.length]);

  // Load private corpus projects
  useEffect(() => {
    if (!open) return;
    if (privateProjectsLoaded) return;
    setPrivateProjectsLoading(true);
    apiClient
      .getCorpusProjects({ is_knowledge_base: true, per_page: 100 })
      .then((res: any) => {
        const items = Array.isArray(res?.items) ? res.items : [];
        const normalized = items
          .map((p: any) => ({
            id: String(p?.id || '').trim(),
            name: String(p?.name || '').trim(),
            enabled: false,
            scope: p?.scope ?? null,
          }))
          .filter((p: PrivateCorpusProject) => p.id && p.name);
        setPrivateProjects(normalized);
      })
      .catch(() => setPrivateProjects([]))
      .finally(() => {
        setPrivateProjectsLoading(false);
        setPrivateProjectsLoaded(true);
      });
  }, [open, privateProjectsLoaded]);

  // Calculate active counts
  const activeSourcesCount = useMemo(() => {
    let count = 0;
    if (webSearch) count++;
    count += attachmentItems.filter((a) => a.enabled).length;
    count += corpusSources.filter((c) => c.enabled).length;
    count += privateProjects.filter((p) => p.enabled).length;
    if (mcpToolCalling) {
      count += mcpUseAllServers
        ? mcpServers.length
        : mcpServers.filter((m) => m.enabled).length;
    }
    return count;
  }, [webSearch, attachmentItems, corpusSources, privateProjects, mcpToolCalling, mcpUseAllServers, mcpServers]);

  const selectedJurisdictionsCount = (ragGlobalJurisdictions || []).length;
  const organizationKbProjects = useMemo(
    () => privateProjects.filter((p) => String(p.scope || '').toLowerCase() === 'organization'),
    [privateProjects]
  );
  const selectablePrivateProjects = useMemo(
    () => privateProjects.filter((p) => String(p.scope || '').toLowerCase() !== 'organization'),
    [privateProjects]
  );

  const privateCount = selectablePrivateProjects.filter((p) => p.enabled).length + (ragAllowGroups ? 1 : 0);
  const connectorsCount = mcpToolCalling ? (mcpUseAllServers ? mcpServers.length : mcpServers.filter((m) => m.enabled).length) : 0;

  // Active icons for badge
  const activeIcons = useMemo(() => {
    const icons: React.ReactNode[] = [];
    if (webSearch) icons.push(SOURCE_ICONS.web);
    if (attachmentItems.some((a) => a.enabled)) icons.push(SOURCE_ICONS.attachments);
    if (corpusSources.some((c) => c.id === 'legislacao' && c.enabled)) icons.push(SOURCE_ICONS.legislacao);
    if (corpusSources.some((c) => c.id === 'jurisprudencia' && c.enabled)) icons.push(SOURCE_ICONS.jurisprudencia);
    if (selectablePrivateProjects.some((p) => p.enabled) || ragAllowGroups) icons.push(SOURCE_ICONS.private);
    if (mcpToolCalling) icons.push(SOURCE_ICONS.mcp);
    return icons.slice(0, 5);
  }, [webSearch, attachmentItems, corpusSources, selectablePrivateProjects, ragAllowGroups, mcpToolCalling]);

  // Sync corpus from store
  useEffect(() => {
    const selected = new Set((ragSources || []).map((s) => ragSourceToCorpusId(s)).filter(Boolean) as CorpusSourceId[]);
    setCorpusSources((prev) => prev.map((src) => ({ ...src, enabled: selected.has(src.id) })));
  }, [ragSources]);

  // Toggle functions
  const toggleCorpusSource = (id: CorpusSourceId) => {
    setCorpusSources((prev) => {
      const next = prev.map((s) => (s.id === id ? { ...s, enabled: !s.enabled } : s));
      const enabledRag = next.filter((s) => s.enabled).map((s) => CORPUS_SOURCE_TO_RAG[s.id]);
      setRagSources(enabledRag);
      return next;
    });
  };

  const toggleMcpServer = (label: string) => {
    const currentLabels = new Set(mcpServerLabels);
    if (currentLabels.has(label)) {
      currentLabels.delete(label);
    } else {
      currentLabels.add(label);
    }
    setMcpServerLabels(Array.from(currentLabels));
    setMcpUseAllServers(false);
    setMcpServers((prev) =>
      prev.map((s) => (s.label === label ? { ...s, enabled: !s.enabled } : s))
    );
  };

  const togglePrivateProject = (id: string) => {
    setPrivateProjects((prev) =>
      prev.map((p) => (p.id === id ? { ...p, enabled: !p.enabled } : p))
    );
  };

  const hasAnySources = activeSourcesCount > 0;
  const isAllTeamsSelected = ragAllowGroups && (ragSelectedGroups || []).length === 0;
  const isAllJurisdictionsSelected = (ragGlobalJurisdictions || []).length === 0;

  const globalJurisdictions = useMemo(() => buildJurisdictions(), []);
  const filteredJurisdictions = useMemo(() => {
    const q = (jurisdictionQuery || '').trim().toLowerCase();
    if (!q) return globalJurisdictions;
    return globalJurisdictions.filter(
      (j) => j.label.toLowerCase().includes(q) || String(j.id).toLowerCase().includes(q)
    );
  }, [jurisdictionQuery, globalJurisdictions]);

  const filteredRegionalSources = useMemo(() => {
    const q = (regionalSourceQuery || '').trim().toLowerCase();
    const selectedJurisdictions = new Set((ragGlobalJurisdictions || []).map((j) => String(j || '').trim().toUpperCase()).filter(Boolean));
    const restrictByJurisdiction = selectedJurisdictions.size > 0;

    const base = (regionalSources || []).filter((s) => {
      if (restrictByJurisdiction && !selectedJurisdictions.has(String(s.jurisdiction || '').toUpperCase())) return false;
      if (!q) return true;
      const hay = [s.label, s.id, s.jurisdiction, ...(s.domains || [])].filter(Boolean).join(' ').toLowerCase();
      return hay.includes(q);
    });

    return base.sort((a, b) => {
      const j = String(a.jurisdiction || '').localeCompare(String(b.jurisdiction || ''), 'pt-BR');
      if (j !== 0) return j;
      return String(a.label || '').localeCompare(String(b.label || ''), 'pt-BR');
    });
  }, [regionalSourceQuery, ragGlobalJurisdictions, regionalSources]);

  const toggleRegionalSource = (src: RegionalSourceItem) => {
    toggleRagGlobalSourceId(src.id);
    const currentJurisdictions = (ragGlobalJurisdictions || []).map((j) => String(j || '').trim().toUpperCase()).filter(Boolean);
    if (currentJurisdictions.length > 0) {
      const j = String(src.jurisdiction || '').trim().toUpperCase();
      if (j && !currentJurisdictions.includes(j)) {
        setRagGlobalJurisdictions([...currentJurisdictions, j]);
      }
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            'flex items-center gap-1.5 h-7 px-2.5 rounded-full text-xs font-medium transition-all',
            'border hover:shadow-sm',
            hasAnySources
              ? 'border-emerald-200 bg-emerald-50/80 text-emerald-700 hover:bg-emerald-100/80'
              : 'border-slate-200 bg-white text-slate-500 hover:bg-slate-50 hover:text-slate-700'
          )}
        >
          <div className="flex items-center -space-x-0.5">
            {activeIcons.length > 0 ? (
              activeIcons.map((icon, i) => (
                <span
                  key={i}
                  className={cn(
                    'flex items-center justify-center w-4 h-4 rounded-full',
                    hasAnySources ? 'text-emerald-600' : 'text-slate-400'
                  )}
                >
                  {icon}
                </span>
              ))
            ) : (
              <Database className="h-3 w-3 text-slate-400" />
            )}
          </div>
          <span className="hidden sm:inline">
            Fontes{process.env.NODE_ENV !== 'production' ? ' v2' : ''}{' '}
            {activeSourcesCount > 0 && <span className="font-semibold">{activeSourcesCount}</span>}
          </span>
          <span className="sm:hidden font-semibold">
            {activeSourcesCount || '0'}
            {process.env.NODE_ENV !== 'production' ? ' v2' : ''}
          </span>
          <ChevronDown className="h-3 w-3 opacity-60" />
        </button>
      </PopoverTrigger>

      <PopoverContent
        className="w-[92vw] max-w-[520px] p-0 overflow-hidden"
        align="start"
        sideOffset={8}
        side="bottom"
        collisionPadding={12}
      >
        {/* Tabs */}
        <div className="flex border-b border-slate-100 bg-slate-50/50 overflow-x-auto">
          {TAB_CONFIG.map((tab) => {
            const count = tab.id === 'sources' ? activeSourcesCount
              : tab.id === 'jurisdictions' ? selectedJurisdictionsCount
              : tab.id === 'private' ? privateCount
              : connectorsCount;

            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  'flex-1 min-w-[110px] flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-medium transition-all border-b-2',
                  activeTab === tab.id
                    ? 'border-emerald-500 text-emerald-700 bg-white'
                    : 'border-transparent text-slate-500 hover:text-slate-700 hover:bg-slate-100/50'
                )}
              >
                {tab.icon}
                <span>{tab.label}</span>
                {count > 0 && (
                  <span className={cn(
                    'ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-semibold',
                    activeTab === tab.id ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-600'
                  )}>
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        <ScrollArea type="always" className="h-[70vh] max-h-[520px]">
          <div className="p-4">
            {/* SOURCES TAB */}
            {activeTab === 'sources' && (
              <div className="space-y-4">
                {/* Web Search */}
                <div className="flex items-center justify-between p-3 rounded-lg border border-slate-200 bg-slate-50/50">
                  <div className="flex items-center gap-2">
                    <Globe className="h-4 w-4 text-blue-500" />
                    <div>
                      <p className="text-sm font-medium text-slate-700">Busca Web</p>
                      <p className="text-[10px] text-slate-500">Enriquece respostas com dados da web</p>
                    </div>
                  </div>
                  <Switch checked={webSearch} onCheckedChange={setWebSearch} />
                </div>

                {/* Attachments */}
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-xs font-semibold text-slate-600 uppercase tracking-wide">
                    <Paperclip className="h-3.5 w-3.5" />
                    <span>Anexos do Caso</span>
                    {attachmentItems.length > 0 && (
                      <span className="ml-auto text-[10px] text-slate-400">{attachmentItems.length} arquivo(s)</span>
                    )}
                  </div>
                  {attachmentItems.length > 0 ? (
                    <div className="grid grid-cols-2 gap-2">
                      {attachmentItems.map((item) => (
                        <label key={item.id} className="flex items-center gap-2 p-2 rounded-md border border-slate-200 hover:border-emerald-300 cursor-pointer transition-colors">
                          <Checkbox checked={item.enabled} className="h-3.5 w-3.5" />
                          <span className="text-xs text-slate-600 truncate">{item.name}</span>
                        </label>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-slate-400 italic">Nenhum arquivo anexado</p>
                  )}
                </div>

                {/* Corpus Global */}
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-xs font-semibold text-slate-600 uppercase tracking-wide">
                    <Building2 className="h-3.5 w-3.5" />
                    <span>Corpus Global</span>
                  </div>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button
                        type="button"
                        className="w-full flex items-center justify-between gap-2 p-3 rounded-lg border border-slate-200 hover:border-slate-300 bg-white transition-colors"
                      >
                        <span className="flex items-center gap-2 text-sm text-slate-700">
                          <Building2 className="h-4 w-4 text-slate-500" />
                          Selecionar fontes do Global
                        </span>
                        <span className="text-xs text-slate-500">
                          {corpusSources.filter((s) => s.enabled).length} selecionada(s)
                        </span>
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start" className="w-[320px] p-2">
                      <div className="space-y-1">
                        {corpusSources.map((source) => (
                          <label
                            key={source.id}
                            className={cn(
                              'flex items-center gap-2 p-2 rounded-md cursor-pointer transition-colors',
                              source.enabled ? 'bg-emerald-50 text-emerald-800' : 'hover:bg-slate-50 text-slate-700'
                            )}
                          >
                            <Checkbox
                              checked={source.enabled}
                              onCheckedChange={() => toggleCorpusSource(source.id)}
                              className="h-3.5 w-3.5"
                            />
                            <span className="flex items-center gap-2 text-sm">
                              {source.icon}
                              {source.label}
                            </span>
                          </label>
                        ))}
                      </div>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>

                {/* RAG Scope */}
                <div className="space-y-2">
                  <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Escopo de Busca</p>
                  <div className="flex gap-2">
                    {[
                      { value: 'case_only', label: 'Apenas Caso' },
                      { value: 'case_and_global', label: 'Caso + Global' },
                      { value: 'global_only', label: 'Apenas Global' },
                    ].map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => setRagScope(option.value as typeof ragScope)}
                        className={cn(
                          'flex-1 px-3 py-2 rounded-lg text-xs font-medium transition-all border',
                          ragScope === option.value
                            ? 'bg-emerald-500 text-white border-emerald-500'
                            : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300'
                        )}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* JURISDICTIONS TAB */}
            {activeTab === 'jurisdictions' && (
              <div className="space-y-4">
                {/* Search */}
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                  <Input
                    value={jurisdictionQuery}
                    onChange={(e) => setJurisdictionQuery(e.target.value)}
                    placeholder="Buscar país ou região..."
                    className="pl-9 h-9"
                  />
                  {jurisdictionQuery && (
                    <button
                      type="button"
                      onClick={() => setJurisdictionQuery('')}
                      className="absolute right-3 top-1/2 -translate-y-1/2"
                    >
                      <X className="h-4 w-4 text-slate-400 hover:text-slate-600" />
                    </button>
                  )}
                </div>

                {/* All jurisdictions toggle */}
                <div className="flex items-center justify-between p-3 rounded-lg border border-slate-200 bg-slate-50/50">
                  <div className="flex items-center gap-2">
                    <Globe className="h-4 w-4 text-slate-500" />
                    <span className="text-sm font-medium text-slate-700">Todas as Jurisdições</span>
                  </div>
                  <Checkbox
                    checked={isAllJurisdictionsSelected}
                    onCheckedChange={(checked) => {
                      if (checked) {
                        clearRagGlobalJurisdictions();
                      } else {
                        setRagGlobalJurisdictions(['BR']);
                      }
                    }}
                    className="h-4 w-4"
                  />
                </div>

                {/* Selected jurisdictions chips */}
                {!isAllJurisdictionsSelected && (ragGlobalJurisdictions || []).length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {(ragGlobalJurisdictions || []).map((jId) => {
                      const j = globalJurisdictions.find((x) => x.id === jId);
                      if (!j) return null;
                      return (
                        <span
                          key={jId}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-emerald-100 text-emerald-700 text-xs"
                        >
                          <span>{j.flag}</span>
                          <span>{j.label}</span>
                          <button
                            type="button"
                            onClick={() => toggleRagGlobalJurisdiction(jId)}
                            className="ml-0.5 hover:text-emerald-900"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </span>
                      );
                    })}
                    <button
                      type="button"
                      onClick={() => clearRagGlobalJurisdictions()}
                      className="text-xs text-slate-500 hover:text-slate-700 underline"
                    >
                      Limpar
                    </button>
                  </div>
                )}

                {/* Jurisdiction grid */}
                <div className="rounded-lg border border-slate-200 bg-white">
                  <div className="px-3 py-2 border-b border-slate-100 text-[11px] text-slate-500 flex items-center justify-between">
                    <span>Países / regiões</span>
                    <span className="text-[10px] text-slate-400">role para ver mais</span>
                  </div>
                  <div className="max-h-[240px] overflow-y-auto p-2">
                    <div className="grid grid-cols-3 gap-1.5">
                  {filteredJurisdictions.map((j) => {
                    const isSelected = isAllJurisdictionsSelected || (ragGlobalJurisdictions || []).includes(j.id);
                    return (
                      <button
                        key={j.id}
                        type="button"
                        onClick={() => {
                          if (isAllJurisdictionsSelected) {
                            setRagGlobalJurisdictions([j.id]);
                          } else {
                            toggleRagGlobalJurisdiction(j.id);
                          }
                        }}
                        className={cn(
                          'flex items-center gap-1.5 px-2 py-1.5 rounded-md text-xs transition-all text-left',
                          isSelected && !isAllJurisdictionsSelected
                            ? 'bg-emerald-100 text-emerald-700 font-medium'
                            : 'hover:bg-slate-100 text-slate-600'
                        )}
                      >
                        <span className="text-sm">{j.flag}</span>
                        <span className="truncate">{j.label}</span>
                        {isSelected && !isAllJurisdictionsSelected && (
                          <Check className="h-3 w-3 ml-auto text-emerald-600" />
                        )}
                      </button>
                    );
                  })}
                    </div>
                  </div>
                </div>

                {/* Regional Sources */}
                {!isAllJurisdictionsSelected && (
                  <div className="space-y-2 pt-2 border-t border-slate-100">
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Fontes Regionais</p>
                      <button
                        type="button"
                        onClick={() => clearRagGlobalSourceIds()}
                        className="text-[10px] text-slate-500 hover:text-slate-700 underline"
                      >
                        Resetar
                      </button>
                    </div>
                    <Input
                      value={regionalSourceQuery}
                      onChange={(e) => setRegionalSourceQuery(e.target.value)}
                      placeholder="Filtrar fontes..."
                      className="h-8 text-xs"
                    />
                    {regionalSourcesLoading ? (
                      <p className="text-xs text-slate-400">Carregando...</p>
                    ) : filteredRegionalSources.length === 0 ? (
                      <p className="text-xs text-slate-400">Nenhuma fonte regional encontrada</p>
                    ) : (
                      <div className="max-h-[240px] overflow-y-auto space-y-1">
                        {filteredRegionalSources.map((src) => {
                          const isSelected = (ragGlobalSourceIds || []).includes(src.id);
                          return (
                            <label
                              key={src.id}
                              className={cn(
                                'flex items-start gap-2 p-2 rounded-md cursor-pointer transition-all',
                                isSelected ? 'bg-emerald-50 border border-emerald-200' : 'hover:bg-slate-50 border border-transparent'
                              )}
                            >
                              <Checkbox
                                checked={isSelected}
                                onCheckedChange={() => toggleRegionalSource(src)}
                                className="h-3.5 w-3.5 mt-0.5"
                              />
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-1">
                                  <span className="text-sm">{toRegionalFlagEmoji(src.jurisdiction)}</span>
                                  <span className="text-xs font-medium text-slate-700">{src.label}</span>
                                  <span className="text-[10px] text-slate-400">({src.jurisdiction})</span>
                                </div>
                                {src.description && (
                                  <p className="text-[10px] text-slate-500 truncate">{src.description}</p>
                                )}
                              </div>
                            </label>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* PRIVATE TAB */}
            {activeTab === 'private' && (
              <div className="space-y-4">
                {!user ? (
                  <div className="text-center py-8">
                    <Lock className="h-8 w-8 text-slate-300 mx-auto mb-2" />
                    <p className="text-sm text-slate-500">Faça login para acessar o Corpus Privado</p>
                  </div>
                ) : (
                  <>
                    {/* Organization base */}
                    <div className="p-3 rounded-lg border border-slate-200 bg-slate-50/50">
                      <div className="flex items-center gap-2">
                        <Building2 className="h-4 w-4 text-slate-500" />
                        <div className="flex-1">
                          <p className="text-sm font-medium text-slate-700">Organização (Base)</p>
                          <p className="text-[10px] text-slate-500">Sempre incluído nas buscas</p>
                        </div>
                        <Check className="h-4 w-4 text-emerald-500" />
                      </div>
                      {organizationKbProjects.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {organizationKbProjects.slice(0, 6).map((p) => (
                            <span
                              key={p.id}
                              className="inline-flex items-center gap-1 rounded-full bg-slate-200/70 px-2 py-0.5 text-[10px] text-slate-700"
                            >
                              KB: {p.name}
                            </span>
                          ))}
                          {organizationKbProjects.length > 6 && (
                            <span className="text-[10px] text-slate-500">+{organizationKbProjects.length - 6}…</span>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Departments toggle */}
                    <div className="flex items-center justify-between p-3 rounded-lg border border-slate-200">
                      <div className="flex items-center gap-2">
                        <FolderOpen className="h-4 w-4 text-slate-500" />
                        <div>
                          <p className="text-sm font-medium text-slate-700">Departamentos</p>
                          <p className="text-[10px] text-slate-500">Incluir corpus por departamento</p>
                        </div>
                      </div>
                      <Switch
                        checked={ragAllowGroups}
                        onCheckedChange={(checked) => {
                          setRagAllowGroups(Boolean(checked));
                          if (!checked) clearRagSelectedGroups();
                        }}
                      />
                    </div>

                    {/* Teams list */}
                    {ragAllowGroups && (
                      <div className="space-y-2">
                        {teamsLoading ? (
                          <p className="text-xs text-slate-400">Carregando departamentos...</p>
                        ) : myTeams.length > 0 ? (
                          <>
                            <label className="flex items-center gap-2 p-2 rounded-md hover:bg-slate-50 cursor-pointer">
                              <Checkbox
                                checked={isAllTeamsSelected}
                                onCheckedChange={(checked) => {
                                  if (checked) clearRagSelectedGroups();
                                  else setRagSelectedGroups(myTeams.map((t) => t.id));
                                }}
                                className="h-3.5 w-3.5"
                              />
                              <span className="text-xs text-slate-600 font-medium">Todos os departamentos</span>
                            </label>
                            <div className={cn('space-y-1 pl-4', isAllTeamsSelected && 'opacity-50')}>
                              {myTeams.map((team) => (
                                <label
                                  key={team.id}
                                  className={cn(
                                    'flex items-center gap-2 p-2 rounded-md cursor-pointer transition-all',
                                    isAllTeamsSelected ? 'pointer-events-none' : 'hover:bg-slate-50'
                                  )}
                                >
                                  <Checkbox
                                    checked={isAllTeamsSelected || (ragSelectedGroups || []).includes(team.id)}
                                    onCheckedChange={() => toggleRagSelectedGroup(team.id)}
                                    className="h-3.5 w-3.5"
                                  />
                                  <span className="text-xs text-slate-600">{team.name}</span>
                                </label>
                              ))}
                            </div>
                          </>
                        ) : (
                          <p className="text-xs text-slate-400 italic">Você não está em nenhum departamento</p>
                        )}
                      </div>
                    )}

                    {/* Private projects */}
                    <div className="space-y-2 pt-2 border-t border-slate-100">
                      <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">
                        Knowledge Bases
                      </p>
                      {privateProjectsLoading ? (
                        <p className="text-xs text-slate-400">Carregando projetos...</p>
                      ) : selectablePrivateProjects.length > 0 ? (
                        <div className="grid grid-cols-2 gap-2">
                          {selectablePrivateProjects.map((project) => (
                            <label
                              key={project.id}
                              className={cn(
                                'flex items-center gap-2 p-2.5 rounded-lg border cursor-pointer transition-all',
                                project.enabled
                                  ? 'border-emerald-300 bg-emerald-50/50'
                                  : 'border-slate-200 hover:border-slate-300'
                              )}
                            >
                              <Checkbox
                                checked={project.enabled}
                                onCheckedChange={() => togglePrivateProject(project.id)}
                                className="h-3.5 w-3.5"
                              />
                              <span className={cn(
                                'text-xs truncate',
                                project.enabled ? 'text-emerald-700 font-medium' : 'text-slate-600'
                              )}>
                                {project.name}
                              </span>
                            </label>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-slate-400 italic">Nenhum projeto configurado</p>
                      )}
                    </div>
                  </>
                )}
              </div>
            )}

            {/* CONNECTORS TAB */}
            {activeTab === 'connectors' && (
              <div className="space-y-4">
                {/* MCP Toggle */}
                <div className="flex items-center justify-between p-3 rounded-lg border border-slate-200 bg-slate-50/50">
                  <div className="flex items-center gap-2">
                    <Plug className="h-4 w-4 text-purple-500" />
                    <div>
                      <p className="text-sm font-medium text-slate-700">Conectores MCP</p>
                      <p className="text-[10px] text-slate-500">Habilitar tool calling via MCP</p>
                    </div>
                  </div>
                  <Switch checked={mcpToolCalling} onCheckedChange={setMcpToolCalling} />
                </div>

                {mcpToolCalling && (
                  <>
                    {/* Use all toggle */}
                    <label className="flex items-center gap-2 p-2 rounded-md hover:bg-slate-50 cursor-pointer">
                      <Checkbox
                        checked={mcpUseAllServers}
                        onCheckedChange={(checked) => setMcpUseAllServers(Boolean(checked))}
                        className="h-3.5 w-3.5"
                      />
                      <span className="text-xs text-slate-600 font-medium">Usar todos os servidores</span>
                    </label>

                    {/* Server list */}
                    {!mcpUseAllServers && (
                      <div className="space-y-2">
                        {mcpLoading ? (
                          <p className="text-xs text-slate-400">Carregando servidores...</p>
                        ) : mcpServers.length > 0 ? (
                          <div className="grid grid-cols-2 gap-2">
                            {mcpServers.map((server) => (
                              <label
                                key={server.label}
                                className={cn(
                                  'flex items-center gap-2 p-2.5 rounded-lg border cursor-pointer transition-all',
                                  server.enabled
                                    ? 'border-purple-300 bg-purple-50/50'
                                    : 'border-slate-200 hover:border-slate-300'
                                )}
                              >
                                <Checkbox
                                  checked={server.enabled}
                                  onCheckedChange={() => toggleMcpServer(server.label)}
                                  className="h-3.5 w-3.5"
                                />
                                <span className={cn(
                                  'text-xs truncate',
                                  server.enabled ? 'text-purple-700 font-medium' : 'text-slate-600'
                                )}>
                                  {server.label}
                                </span>
                              </label>
                            ))}
                          </div>
                        ) : (
                          <div className="text-center py-6">
                            <Plug className="h-8 w-8 text-slate-300 mx-auto mb-2" />
                            <p className="text-xs text-slate-400">Nenhum servidor MCP disponível</p>
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}

                {!mcpToolCalling && (
                  <div className="text-center py-6">
                    <Plug className="h-8 w-8 text-slate-300 mx-auto mb-2" />
                    <p className="text-xs text-slate-400">Ative os conectores MCP para expandir funcionalidades</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </ScrollArea>

        {/* Footer */}
        <div className="border-t border-slate-100 px-4 py-2.5 bg-slate-50/50 flex items-center justify-between">
          <p className="text-xs text-slate-500">
            {activeSourcesCount} fonte{activeSourcesCount !== 1 ? 's' : ''} ativa{activeSourcesCount !== 1 ? 's' : ''}
          </p>
          <div className="flex items-center gap-2">
            {process.env.NODE_ENV !== 'production' && (
              <span className="text-[10px] text-slate-400">UI v2</span>
            )}
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="px-3 py-1 text-xs font-medium text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50 rounded-md transition-colors"
            >
              Aplicar
            </button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

export default SourcesBadge;
