'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Plus, Trash2, TestTube, Loader2, Server, CheckCircle2, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api-client';

interface MCPServer {
  label: string;
  url: string;
  allowed_tools?: string[];
  auth?: { type: string; token?: string; value?: string; token_env?: string };
}

interface TestResult {
  status: string;
  tools_count?: number;
}

export function MCPServersConfig() {
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({});

  // Form state
  const [newLabel, setNewLabel] = useState('');
  const [newUrl, setNewUrl] = useState('');
  const [newAuthType, setNewAuthType] = useState<string>('none');
  const [newToken, setNewToken] = useState('');

  const loadServers = useCallback(async () => {
    try {
      const res = await apiClient.getUserMcpServers();
      setServers(res.servers || []);
    } catch {
      toast.error('Erro ao carregar servidores MCP');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadServers();
  }, [loadServers]);

  async function addServer() {
    if (!newLabel.trim() || !newUrl.trim()) {
      toast.error('Label e URL são obrigatórios');
      return;
    }
    setAdding(true);
    try {
      await apiClient.addUserMcpServer({
        label: newLabel.trim(),
        url: newUrl.trim(),
        auth_type: newAuthType !== 'none' ? newAuthType : null,
        auth_token: newToken || null,
      });
      toast.success('Servidor adicionado');
      setNewLabel('');
      setNewUrl('');
      setNewAuthType('none');
      setNewToken('');
      await loadServers();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Erro ao adicionar servidor';
      toast.error(message);
    } finally {
      setAdding(false);
    }
  }

  async function removeServer(label: string) {
    try {
      await apiClient.removeUserMcpServer(label);
      toast.success('Servidor removido');
      setServers((prev) => prev.filter((s) => s.label !== label));
    } catch {
      toast.error('Erro ao remover servidor');
    }
  }

  async function testServer(label: string) {
    setTesting(label);
    try {
      const res = await apiClient.testUserMcpServer(label);
      setTestResults((prev) => ({ ...prev, [label]: res }));
      if (res.status === 'ok') {
        toast.success(`Conectado! ${res.tools_count} tools encontradas`);
      } else {
        toast.error(`Falha: ${res.message}`);
      }
    } catch {
      toast.error('Erro ao testar servidor');
    } finally {
      setTesting(null);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-8 justify-center text-slate-400">
        <Loader2 className="h-4 w-4 animate-spin" /> Carregando...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-1">
          Servidores MCP Personalizados
        </h3>
        <p className="text-xs text-slate-500 mb-4">
          Adicione servidores MCP externos para expandir as ferramentas disponíveis no chat e workflows.
          Máximo de 10 servidores.
        </p>
      </div>

      {/* Existing servers */}
      {servers.length > 0 && (
        <div className="space-y-2">
          {servers.map((s) => (
            <div
              key={s.label}
              className="flex items-center gap-3 p-3 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900"
            >
              <Server className="h-4 w-4 text-slate-400 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-700 dark:text-slate-300">{s.label}</p>
                <p className="text-xs text-slate-400 truncate">{s.url}</p>
              </div>
              {testResults[s.label] && (
                <span className="text-xs">
                  {testResults[s.label].status === 'ok' ? (
                    <span className="flex items-center gap-1 text-emerald-600">
                      <CheckCircle2 className="h-3 w-3" /> {testResults[s.label].tools_count} tools
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-red-500">
                      <XCircle className="h-3 w-3" /> Falha
                    </span>
                  )}
                </span>
              )}
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => testServer(s.label)}
                disabled={testing === s.label}
              >
                {testing === s.label ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <TestTube className="h-3.5 w-3.5" />
                )}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-red-500 hover:text-red-600"
                onClick={() => removeServer(s.label)}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          ))}
        </div>
      )}

      {/* Add new server form */}
      <div className="space-y-3 p-4 rounded-lg border border-dashed border-slate-300 dark:border-slate-600">
        <div className="grid grid-cols-2 gap-3">
          <Input
            placeholder="Label (ex: brave-search)"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            className="h-8 text-sm"
          />
          <Input
            placeholder="URL do servidor MCP"
            value={newUrl}
            onChange={(e) => setNewUrl(e.target.value)}
            className="h-8 text-sm"
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <select
            value={newAuthType}
            onChange={(e) => setNewAuthType(e.target.value)}
            className="h-8 text-sm rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-2"
          >
            <option value="none">Sem autenticação</option>
            <option value="bearer">Bearer Token</option>
            <option value="header">Header customizado</option>
          </select>
          {newAuthType !== 'none' && (
            <Input
              placeholder="Token"
              type="password"
              value={newToken}
              onChange={(e) => setNewToken(e.target.value)}
              className="h-8 text-sm"
            />
          )}
        </div>
        <Button size="sm" onClick={addServer} disabled={adding} className="gap-1.5">
          {adding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
          Adicionar Servidor
        </Button>
      </div>
    </div>
  );
}
