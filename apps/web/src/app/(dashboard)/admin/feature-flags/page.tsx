'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2, Shield, SlidersHorizontal, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api-client';
import { useAuthStore } from '@/stores/auth-store';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';

type SnapshotPayload = {
  global_enabled: boolean;
  auto_detect_sdk: boolean;
  sdk_available: boolean;
  canary_percent: number;
  analytics_sample_rate: number;
  executor_enabled: Record<string, boolean>;
  limits: {
    max_tool_calls_per_request: number;
    max_delegated_tokens_per_request: number;
  };
};

type FlagsResponsePayload = {
  snapshot: SnapshotPayload;
  runtime_overrides: Record<string, string>;
};

const BOOL_FLAG_ROWS = [
  { key: 'IUDEX_AGENTIC_GLOBAL_ENABLED', label: 'Kill Switch Global', fromSnapshot: 'global_enabled' as const },
  { key: 'IUDEX_AGENTIC_AUTO_DETECT_SDK', label: 'Auto Detect SDK', fromSnapshot: 'auto_detect_sdk' as const },
  { key: 'IUDEX_AGENTIC_EXECUTOR_CLAUDE_AGENT_ENABLED', label: 'Executor Claude Agent', executorKey: 'claude_agent' },
  { key: 'IUDEX_AGENTIC_EXECUTOR_OPENAI_AGENT_ENABLED', label: 'Executor OpenAI Agent', executorKey: 'openai_agent' },
  { key: 'IUDEX_AGENTIC_EXECUTOR_GOOGLE_AGENT_ENABLED', label: 'Executor Google Agent', executorKey: 'google_agent' },
  { key: 'IUDEX_AGENTIC_EXECUTOR_LANGGRAPH_ENABLED', label: 'Executor LangGraph', executorKey: 'langgraph' },
  { key: 'IUDEX_AGENTIC_EXECUTOR_PARALLEL_ENABLED', label: 'Executor Parallel', executorKey: 'parallel' },
  { key: 'IUDEX_AGENTIC_QUICK_BRIDGE_ENABLED', label: 'Quick Agent Bridge' },
];

const NUMERIC_FLAG_ROWS = [
  {
    key: 'IUDEX_AGENTIC_CANARY_PERCENT',
    label: 'Canary Percent',
    fromSnapshot: (s: SnapshotPayload) => String(s.canary_percent),
    placeholder: '0-100',
  },
  {
    key: 'IUDEX_AGENTIC_ANALYTICS_SAMPLE_RATE',
    label: 'Analytics Sample Rate',
    fromSnapshot: (s: SnapshotPayload) => String(s.analytics_sample_rate),
    placeholder: '0.0-1.0',
  },
  {
    key: 'IUDEX_AGENTIC_MAX_TOOL_CALLS',
    label: 'Max Tool Calls',
    fromSnapshot: (s: SnapshotPayload) => String(s.limits.max_tool_calls_per_request),
    placeholder: '1-200',
  },
  {
    key: 'IUDEX_AGENTIC_MAX_DELEGATED_TOKENS',
    label: 'Max Delegated Tokens',
    fromSnapshot: (s: SnapshotPayload) => String(s.limits.max_delegated_tokens_per_request),
    placeholder: '1000-2000000',
  },
];

const parseBool = (value: string | undefined): boolean | null => {
  if (!value) return null;
  const normalized = value.trim().toLowerCase();
  if (['1', 'true', 'yes', 'on'].includes(normalized)) return true;
  if (['0', 'false', 'no', 'off'].includes(normalized)) return false;
  return null;
};

export default function AdminFeatureFlagsPage() {
  const { user } = useAuthStore();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [data, setData] = useState<FlagsResponsePayload | null>(null);
  const [numericDrafts, setNumericDrafts] = useState<Record<string, string>>({});

  const isAdmin = String(user?.role || '').toUpperCase() === 'ADMIN';

  const hydrateNumericDrafts = useCallback((snapshot: SnapshotPayload, runtimeOverrides: Record<string, string>) => {
    const drafts: Record<string, string> = {};
    for (const row of NUMERIC_FLAG_ROWS) {
      drafts[row.key] = runtimeOverrides[row.key] ?? row.fromSnapshot(snapshot);
    }
    setNumericDrafts(drafts);
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiClient.getAgenticFeatureFlags();
      setData(response);
      hydrateNumericDrafts(response.snapshot, response.runtime_overrides || {});
    } catch (error: any) {
      if (error?.response?.status === 403) {
        toast.error('Acesso restrito a administradores.');
      } else {
        toast.error('Falha ao carregar feature flags.');
      }
    } finally {
      setLoading(false);
    }
  }, [hydrateNumericDrafts]);

  useEffect(() => {
    if (user && !isAdmin) {
      router.push('/dashboard');
    }
  }, [isAdmin, router, user]);

  useEffect(() => {
    if (!isAdmin) return;
    void loadData();
  }, [isAdmin, loadData]);

  const runtimeOverrides = data?.runtime_overrides;

  const boolRows = useMemo(() => {
    if (!data) return [];
    return BOOL_FLAG_ROWS.map((row) => {
      const override = runtimeOverrides?.[row.key];
      const overrideBool = parseBool(override);
      let base = false;
      if (row.fromSnapshot) {
        base = data.snapshot[row.fromSnapshot];
      } else if (row.executorKey) {
        base = !!data.snapshot.executor_enabled?.[row.executorKey];
      }

      return {
        ...row,
        effective: overrideBool ?? base,
        hasOverride: override !== undefined,
        overrideValue: override,
      };
    });
  }, [data, runtimeOverrides]);

  const applyOverride = async (key: string, value: string | number | boolean) => {
    setSavingKey(key);
    try {
      const response = await apiClient.updateAgenticFeatureFlags({ [key]: value });
      setData({
        snapshot: response.snapshot,
        runtime_overrides: response.runtime_overrides || {},
      });
      hydrateNumericDrafts(response.snapshot, response.runtime_overrides || {});
      toast.success(`Override aplicado: ${key}`);
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || `Falha ao atualizar ${key}.`);
    } finally {
      setSavingKey(null);
    }
  };

  const removeOverride = async (key: string) => {
    setSavingKey(key);
    try {
      const response = await apiClient.removeAgenticFeatureFlagOverride(key);
      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          runtime_overrides: response.runtime_overrides || {},
        };
      });
      toast.success(`Override removido: ${key}`);
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || `Falha ao remover override de ${key}.`);
    } finally {
      setSavingKey(null);
    }
  };

  if (!user || !isAdmin) {
    return (
      <div className="flex min-h-[360px] items-center justify-center">
        <div className="space-y-2 text-center">
          <Shield className="mx-auto h-10 w-10 text-muted-foreground" />
          <p className="text-lg font-medium">Acesso restrito</p>
          <p className="text-sm text-muted-foreground">Esta pagina e exclusiva para administradores.</p>
        </div>
      </div>
    );
  }

  if (loading || !data) {
    return (
      <div className="flex min-h-[360px] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <div className="flex items-center gap-3">
        <div className="rounded-lg bg-indigo-100 p-2">
          <SlidersHorizontal className="h-6 w-6 text-indigo-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold">Agentic Feature Flags</h1>
          <p className="text-sm text-muted-foreground">
            Governanca de rollout para execucao agentic e quick bridge.
          </p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">SDK Disponivel</CardTitle>
          </CardHeader>
          <CardContent>
            <Badge variant={data.snapshot.sdk_available ? 'default' : 'secondary'}>
              {data.snapshot.sdk_available ? 'Disponivel' : 'Indisponivel'}
            </Badge>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Canary Percent</CardTitle>
          </CardHeader>
          <CardContent className="text-lg font-semibold">{data.snapshot.canary_percent}%</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Runtime Overrides</CardTitle>
          </CardHeader>
          <CardContent className="text-lg font-semibold">{Object.keys(runtimeOverrides || {}).length}</CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Flags Booleanas</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {boolRows.map((row) => (
            <div key={row.key} className="rounded-lg border p-3">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold">{row.label}</p>
                  <p className="text-xs text-muted-foreground font-mono">{row.key}</p>
                  {row.hasOverride ? (
                    <Badge variant="secondary" className="mt-1 text-[10px]">
                      override={row.overrideValue}
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="mt-1 text-[10px]">
                      sem override
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Switch
                    checked={row.effective}
                    onCheckedChange={(checked) => {
                      void applyOverride(row.key, checked);
                    }}
                    disabled={savingKey === row.key}
                  />
                  <Button
                    variant="ghost"
                    size="icon"
                    disabled={!row.hasOverride || savingKey === row.key}
                    onClick={() => {
                      void removeOverride(row.key);
                    }}
                    title="Remover override"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Flags Numericas</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {NUMERIC_FLAG_ROWS.map((row) => {
            const hasOverride = runtimeOverrides?.[row.key] !== undefined;
            return (
              <div key={row.key} className="rounded-lg border p-3">
                <div className="mb-2">
                  <p className="text-sm font-semibold">{row.label}</p>
                  <p className="text-xs font-mono text-muted-foreground">{row.key}</p>
                </div>
                <div className="flex items-center gap-2">
                  <div className="flex-1 space-y-1">
                    <Label htmlFor={row.key} className="text-xs">
                      Valor
                    </Label>
                    <Input
                      id={row.key}
                      value={numericDrafts[row.key] ?? ''}
                      onChange={(event) => {
                        const value = event.target.value;
                        setNumericDrafts((prev) => ({ ...prev, [row.key]: value }));
                      }}
                      placeholder={row.placeholder}
                    />
                  </div>
                  <Button
                    className="mt-5"
                    disabled={!numericDrafts[row.key]?.trim() || savingKey === row.key}
                    onClick={() => {
                      void applyOverride(row.key, numericDrafts[row.key]);
                    }}
                  >
                    Aplicar
                  </Button>
                  <Button
                    className="mt-5"
                    variant="outline"
                    disabled={!hasOverride || savingKey === row.key}
                    onClick={() => {
                      void removeOverride(row.key);
                    }}
                  >
                    Remover
                  </Button>
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}
