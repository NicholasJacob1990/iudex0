'use client';

import { useEffect, useMemo, useState } from 'react';

import { apiClient } from '@/lib/api-client';

type RiskProfile = 'precision' | 'balanced' | 'recall';

type RiskSignal = {
  scenario: string;
  title: string;
  score: number;
  entities: Array<{ entity_id: string; name?: string | null; entity_type?: string | null; role?: string | null }>;
  supporting_docs?: { count: number; doc_ids_sample?: string[]; chunk_previews_sample?: string[] };
  explain?: string;
  focus?: { source_id: string; target_id: string } | null;
};

type RiskScanResponse = {
  success: boolean;
  signals: RiskSignal[];
  report_id?: string | null;
  execution_time_ms?: number;
  error?: string | null;
};

type ReportListItem = {
  id: string;
  created_at: string;
  expires_at: string;
  status: string;
  signal_count: number;
  params: any;
};

type AuditEdgeResponse = {
  success: boolean;
  source_id: string;
  target_id: string;
  edge_matches: Array<{ rel_type: string; props: any }>;
  co_mentions: Array<{ doc_id: string; preview: string }>;
  notes?: string | null;
  error?: string | null;
};

type AuditChainResponse = {
  success: boolean;
  source_id: string;
  target_id: string;
  paths: Array<{
    nodes?: Array<{ entity_id: string; name?: string; type?: string }>;
    relationships?: string[];
    length?: number;
    evidence?: Array<{ hop: number; rel_type: string; co_mentions?: number; preview?: string }>;
  }>;
  execution_time_ms?: number;
  error?: string | null;
};

async function postJSON<T>(path: string, body: any): Promise<T> {
  return (await apiClient.fetchWithAuth(path, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  }).then((r) => r.json())) as T;
}

async function getJSON<T>(path: string): Promise<T> {
  return (await apiClient.fetchWithAuth(path, {
    method: 'GET',
  }).then((r) => r.json())) as T;
}

export default function GraphRiskPageClient() {
  const [profile, setProfile] = useState<RiskProfile>('balanced');
  const [includeGlobal, setIncludeGlobal] = useState(true);
  const [includeCandidates, setIncludeCandidates] = useState<boolean>(() => profile === 'recall');
  const [limit, setLimit] = useState<number>(30);
  const [minSharedDocs, setMinSharedDocs] = useState<number>(2);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [signals, setSignals] = useState<RiskSignal[]>([]);
  const [reportId, setReportId] = useState<string | null>(null);

  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [selectedAudit, setSelectedAudit] = useState<AuditEdgeResponse | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [selectedChainAudit, setSelectedChainAudit] = useState<AuditChainResponse | null>(null);
  const [chainLoading, setChainLoading] = useState(false);
  const [auditTab, setAuditTab] = useState<'edge' | 'chain'>('edge');

  useEffect(() => {
    void (async () => {
      try {
        const data = await getJSON<ReportListItem[]>('/graph/risk/reports?limit=30');
        setReports(Array.isArray(data) ? data : []);
      } catch {
        // ignore
      }
    })();
  }, []);

  useEffect(() => {
    // Keep a sensible default for includeCandidates when profile changes.
    setIncludeCandidates(profile === 'recall');
  }, [profile]);

  const header = useMemo(() => {
    return `Risco & Auditoria (GraphRAG)`;
  }, []);

  const runScan = async () => {
    setLoading(true);
    setError(null);
    setSelectedAudit(null);
    setSelectedChainAudit(null);
    try {
      const resp = await postJSON<RiskScanResponse>('/graph/risk/scan', {
        profile,
        include_global: includeGlobal,
        include_candidates: includeCandidates,
        limit,
        min_shared_docs: minSharedDocs,
        persist: true,
      });
      if (!resp?.success) {
        setError(resp?.error || 'Falha ao executar scan.');
        setSignals([]);
        setReportId(null);
      } else {
        setSignals(resp.signals || []);
        setReportId(resp.report_id || null);
        // Refresh list
        try {
          const data = await getJSON<ReportListItem[]>('/graph/risk/reports?limit=30');
          setReports(Array.isArray(data) ? data : []);
        } catch {
          // ignore
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erro desconhecido');
      setSignals([]);
      setReportId(null);
    } finally {
      setLoading(false);
    }
  };

  const auditSignal = async (sig: RiskSignal) => {
    const focus = sig.focus;
    if (!focus) return;
    setAuditLoading(true);
    setSelectedAudit(null);
    setAuditTab('edge');
    try {
      const resp = await postJSON<AuditEdgeResponse>('/graph/risk/audit/edge', {
        source_id: focus.source_id,
        target_id: focus.target_id,
        include_candidates: includeCandidates,
        include_global: includeGlobal,
        limit_docs: 8,
      });
      setSelectedAudit(resp);
    } catch (e) {
      setSelectedAudit({
        success: false,
        source_id: focus.source_id,
        target_id: focus.target_id,
        edge_matches: [],
        co_mentions: [],
        error: e instanceof Error ? e.message : 'Erro desconhecido',
      });
    } finally {
      setAuditLoading(false);
    }
  };

  const auditChainSignal = async (sig: RiskSignal) => {
    const focus = sig.focus;
    if (!focus) return;
    setChainLoading(true);
    setSelectedChainAudit(null);
    setAuditTab('chain');
    try {
      const resp = await postJSON<AuditChainResponse>('/graph/risk/audit/chain', {
        source_id: focus.source_id,
        target_id: focus.target_id,
        max_hops: 4,
        include_candidates: includeCandidates,
        include_global: includeGlobal,
        limit: 5,
      });
      setSelectedChainAudit(resp);
    } catch (e) {
      setSelectedChainAudit({
        success: false,
        source_id: focus.source_id,
        target_id: focus.target_id,
        paths: [],
        error: e instanceof Error ? e.message : 'Erro desconhecido',
      });
    } finally {
      setChainLoading(false);
    }
  };

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">{header}</h1>
          <p className="text-sm text-muted-foreground">
            Scan determinístico com evidências (co-menções + arestas existentes). Use o chat da página de grafos para exploração; use esta tela para triagem e auditoria.
          </p>
        </div>
        <a className="text-sm underline" href="/graph">
          Voltar ao grafo
        </a>
      </div>

      <div className="rounded-lg border bg-white p-4 space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          <label className="space-y-1">
            <div className="text-xs text-muted-foreground">Perfil</div>
            <select
              className="h-9 w-full rounded border px-2 text-sm"
              value={profile}
              onChange={(e) => setProfile(e.target.value as RiskProfile)}
              disabled={loading}
            >
              <option value="precision">precision</option>
              <option value="balanced">balanced</option>
              <option value="recall">recall</option>
            </select>
          </label>

          <label className="space-y-1">
            <div className="text-xs text-muted-foreground">Limite</div>
            <input
              className="h-9 w-full rounded border px-2 text-sm"
              type="number"
              min={1}
              max={200}
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              disabled={loading}
            />
          </label>

          <label className="space-y-1">
            <div className="text-xs text-muted-foreground">min_shared_docs</div>
            <input
              className="h-9 w-full rounded border px-2 text-sm"
              type="number"
              min={1}
              max={20}
              value={minSharedDocs}
              onChange={(e) => setMinSharedDocs(Number(e.target.value))}
              disabled={loading}
            />
          </label>

          <label className="flex items-center gap-2 pt-6">
            <input
              type="checkbox"
              checked={includeCandidates}
              onChange={(e) => setIncludeCandidates(e.target.checked)}
              disabled={loading}
            />
            <span className="text-sm">include candidates</span>
          </label>

          <label className="flex items-center gap-2 pt-6">
            <input
              type="checkbox"
              checked={includeGlobal}
              onChange={(e) => setIncludeGlobal(e.target.checked)}
              disabled={loading}
            />
            <span className="text-sm">include global</span>
          </label>
        </div>

        <div className="flex items-center justify-between gap-3">
          <button
            className="h-9 rounded bg-slate-900 text-white px-3 text-sm disabled:opacity-60"
            onClick={() => void runScan()}
            disabled={loading}
          >
            {loading ? 'Executando...' : 'Executar scan'}
          </button>
          <div className="text-xs text-muted-foreground">
            {reportId ? `Report: ${reportId}` : 'Report: (nenhum)'}
          </div>
        </div>

        {error && <div className="text-sm text-red-600">{error}</div>}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 rounded-lg border bg-white">
          <div className="border-b px-4 py-3 flex items-center justify-between">
            <div className="text-sm font-semibold">Sinais</div>
            <div className="text-xs text-muted-foreground">{signals.length} itens</div>
          </div>

          <div className="overflow-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs text-slate-600">
                <tr>
                  <th className="text-left px-3 py-2">scenario</th>
                  <th className="text-left px-3 py-2">score</th>
                  <th className="text-left px-3 py-2">entities</th>
                  <th className="text-left px-3 py-2">docs</th>
                  <th className="text-left px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {signals.map((s, idx) => {
                  const ents = (s.entities || []).slice(0, 3).map((e) => e.name || e.entity_id).join(' · ');
                  const docs = s.supporting_docs?.count ?? 0;
                  return (
                    <tr key={`${s.scenario}-${idx}`} className="border-t">
                      <td className="px-3 py-2">
                        <div className="font-medium">{s.scenario}</div>
                        <div className="text-xs text-muted-foreground">{s.title}</div>
                      </td>
                      <td className="px-3 py-2 tabular-nums">{Number(s.score || 0).toFixed(2)}</td>
                      <td className="px-3 py-2">{ents || '-'}</td>
                      <td className="px-3 py-2 tabular-nums">{docs}</td>
                      <td className="px-3 py-2">
                        {s.focus ? (
                          <div className="flex gap-1">
                            <button
                              className="h-8 rounded border px-2 text-xs hover:bg-slate-50 disabled:opacity-60"
                              onClick={() => void auditSignal(s)}
                              disabled={auditLoading || chainLoading}
                            >
                              Aresta
                            </button>
                            <button
                              className="h-8 rounded border border-blue-200 bg-blue-50 px-2 text-xs text-blue-700 hover:bg-blue-100 disabled:opacity-60"
                              onClick={() => void auditChainSignal(s)}
                              disabled={auditLoading || chainLoading}
                            >
                              Cadeia
                            </button>
                          </div>
                        ) : (
                          <span className="text-xs text-muted-foreground">-</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {signals.length === 0 && (
                  <tr>
                    <td className="px-3 py-6 text-sm text-muted-foreground" colSpan={5}>
                      Nenhum sinal ainda. Rode um scan.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded-lg border bg-white">
          <div className="border-b px-4 py-3 flex items-center justify-between">
            <div className="text-sm font-semibold">Auditoria</div>
            <div className="text-xs text-muted-foreground">
              {auditLoading || chainLoading ? 'carregando...' : ''}
            </div>
          </div>

          {/* Tabs: Aresta / Cadeia */}
          <div className="border-b flex">
            <button
              className={`flex-1 px-3 py-2 text-xs font-medium transition-colors ${
                auditTab === 'edge'
                  ? 'border-b-2 border-slate-900 text-slate-900'
                  : 'text-muted-foreground hover:text-slate-700'
              }`}
              onClick={() => setAuditTab('edge')}
            >
              Aresta
            </button>
            <button
              className={`flex-1 px-3 py-2 text-xs font-medium transition-colors ${
                auditTab === 'chain'
                  ? 'border-b-2 border-blue-600 text-blue-700'
                  : 'text-muted-foreground hover:text-slate-700'
              }`}
              onClick={() => setAuditTab('chain')}
            >
              Cadeia
            </button>
          </div>

          <div className="p-4 space-y-3">
            {/* === Edge Audit Tab === */}
            {auditTab === 'edge' && (
              <>
                {!selectedAudit && (
                  <div className="text-sm text-muted-foreground">
                    Selecione um sinal e clique em Aresta.
                  </div>
                )}

                {selectedAudit && !selectedAudit.success && (
                  <div className="text-sm text-red-600">
                    {selectedAudit.error || 'Falha na auditoria.'}
                  </div>
                )}

                {selectedAudit && selectedAudit.success && (
                  <>
                    {selectedAudit.notes && (
                      <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
                        {selectedAudit.notes}
                      </div>
                    )}

                    <div className="space-y-1">
                      <div className="text-xs text-muted-foreground">Arestas</div>
                      <div className="text-sm">
                        {selectedAudit.edge_matches.length === 0 ? (
                          <span className="text-muted-foreground">Nenhuma aresta direta encontrada.</span>
                        ) : (
                          <ul className="list-disc pl-5 space-y-1 text-xs">
                            {selectedAudit.edge_matches.slice(0, 8).map((e, i) => (
                              <li key={`${e.rel_type}-${i}`}>
                                <span className="font-semibold">{e.rel_type}</span>
                                {e.props?.evidence ? <span className="text-muted-foreground"> · ev: {String(e.props.evidence).slice(0, 120)}</span> : null}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    </div>

                    <div className="space-y-1">
                      <div className="text-xs text-muted-foreground">Co-menções (chunks)</div>
                      {selectedAudit.co_mentions.length === 0 ? (
                        <div className="text-sm text-muted-foreground">Nenhuma co-menção encontrada.</div>
                      ) : (
                        <ul className="space-y-2">
                          {selectedAudit.co_mentions.slice(0, 5).map((c, i) => (
                            <li key={`${c.doc_id}-${i}`} className="text-xs border rounded p-2">
                              <div className="text-[10px] text-muted-foreground">doc: {c.doc_id}</div>
                              <div className="mt-1">{c.preview}</div>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </>
                )}
              </>
            )}

            {/* === Chain Audit Tab === */}
            {auditTab === 'chain' && (
              <>
                {!selectedChainAudit && !chainLoading && (
                  <div className="text-sm text-muted-foreground">
                    Selecione um sinal e clique em Cadeia para rastrear caminhos multi-hop com evidências.
                  </div>
                )}

                {chainLoading && (
                  <div className="text-sm text-muted-foreground animate-pulse">
                    Rastreando cadeias...
                  </div>
                )}

                {selectedChainAudit && !selectedChainAudit.success && (
                  <div className="text-sm text-red-600">
                    {selectedChainAudit.error || 'Falha na auditoria de cadeia.'}
                  </div>
                )}

                {selectedChainAudit && selectedChainAudit.success && (
                  <>
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>
                        {selectedChainAudit.paths.length} caminho{selectedChainAudit.paths.length !== 1 ? 's' : ''} encontrado{selectedChainAudit.paths.length !== 1 ? 's' : ''}
                      </span>
                      {selectedChainAudit.execution_time_ms != null && (
                        <span>{selectedChainAudit.execution_time_ms}ms</span>
                      )}
                    </div>

                    {selectedChainAudit.paths.length === 0 && (
                      <div className="text-sm text-muted-foreground">
                        Nenhum caminho encontrado entre as entidades.
                      </div>
                    )}

                    {selectedChainAudit.paths.map((path, pathIdx) => (
                      <div key={pathIdx} className="border rounded p-3 space-y-2">
                        <div className="flex items-center justify-between">
                          <div className="text-xs font-semibold">
                            Caminho {pathIdx + 1}
                            {path.length != null && (
                              <span className="font-normal text-muted-foreground ml-1">
                                ({path.length} hop{path.length !== 1 ? 's' : ''})
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Node chain visualization */}
                        {path.nodes && path.nodes.length > 0 && (
                          <div className="flex flex-wrap items-center gap-1">
                            {path.nodes.map((node, nodeIdx) => (
                              <span key={node.entity_id} className="contents">
                                <span
                                  className={`inline-block rounded px-1.5 py-0.5 text-[11px] ${
                                    nodeIdx === 0
                                      ? 'bg-green-100 text-green-800 border border-green-300'
                                      : nodeIdx === path.nodes!.length - 1
                                        ? 'bg-red-100 text-red-800 border border-red-300'
                                        : 'bg-slate-100 text-slate-700 border border-slate-300'
                                  }`}
                                >
                                  {node.name || node.entity_id}
                                  {node.type && (
                                    <span className="text-[9px] text-muted-foreground ml-1">
                                      [{node.type}]
                                    </span>
                                  )}
                                </span>
                                {nodeIdx < path.nodes!.length - 1 && (
                                  <span className="text-[10px] text-blue-500 font-medium mx-0.5">
                                    {path.relationships?.[nodeIdx] || '->'}
                                  </span>
                                )}
                              </span>
                            ))}
                          </div>
                        )}

                        {/* Evidence per hop */}
                        {path.evidence && path.evidence.length > 0 && (
                          <div className="space-y-1 mt-1">
                            <div className="text-[10px] text-muted-foreground font-medium">Evidências por hop:</div>
                            {path.evidence.map((ev, evIdx) => (
                              <div key={evIdx} className="text-xs border-l-2 border-blue-200 pl-2 py-1">
                                <span className="font-medium">Hop {ev.hop}:</span>{' '}
                                <span className="text-muted-foreground">{ev.rel_type}</span>
                                {ev.co_mentions != null && (
                                  <span className="text-blue-600 ml-1">({ev.co_mentions} co-menções)</span>
                                )}
                                {ev.preview && (
                                  <div className="text-[11px] text-muted-foreground mt-0.5 line-clamp-2">
                                    {ev.preview}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </>
                )}
              </>
            )}

            <div className="pt-2 border-t">
              <div className="text-xs text-muted-foreground">Relatórios recentes</div>
              <ul className="mt-2 space-y-1 text-xs">
                {reports.slice(0, 8).map((r) => (
                  <li key={r.id} className="flex items-center justify-between gap-2">
                    <span className="truncate">{r.id}</span>
                    <span className="text-muted-foreground tabular-nums">{r.signal_count}</span>
                  </li>
                ))}
                {reports.length === 0 && <li className="text-muted-foreground">Sem histórico.</li>}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

