'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  Cloud,
  Building2,
  HardDrive,
  Trash2,
  Loader2,
  CheckCircle2,
  ExternalLink,
  RefreshCw,
  AlertCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api-client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DMSProvider {
  id: string;
  name: string;
  description: string;
  icon: string;
  supports_sync: boolean;
}

interface DMSIntegration {
  id: string;
  provider: string;
  display_name: string;
  root_folder_id?: string | null;
  sync_enabled: boolean;
  last_sync_at?: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Icon helper
// ---------------------------------------------------------------------------

function ProviderIcon({ provider, className }: { provider: string; className?: string }) {
  switch (provider) {
    case 'google_drive':
      return <Cloud className={className} />;
    case 'sharepoint':
      return <Building2 className={className} />;
    case 'onedrive':
      return <HardDrive className={className} />;
    default:
      return <Cloud className={className} />;
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function DMSIntegrations() {
  const [providers, setProviders] = useState<DMSProvider[]>([]);
  const [integrations, setIntegrations] = useState<DMSIntegration[]>([]);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [disconnectTarget, setDisconnectTarget] = useState<DMSIntegration | null>(null);
  const [disconnecting, setDisconnecting] = useState(false);
  const [syncing, setSyncing] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [provRes, intRes] = await Promise.all([
        apiClient.getDMSProviders(),
        apiClient.getDMSIntegrations(),
      ]);
      setProviders(provRes.providers || []);
      setIntegrations(intRes.integrations || []);
    } catch {
      toast.error('Erro ao carregar integrações DMS');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Listen for OAuth popup callback
  useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (event.data?.type === 'dms-oauth-callback' && event.data?.success) {
        loadData();
        toast.success('Integração conectada com sucesso!');
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [loadData]);

  async function connectProvider(providerId: string) {
    setConnecting(providerId);
    try {
      const res = await apiClient.startDMSConnect(providerId);
      // Open OAuth URL in a popup
      const w = 600;
      const h = 700;
      const left = window.screenX + (window.innerWidth - w) / 2;
      const top = window.screenY + (window.innerHeight - h) / 2;
      window.open(
        res.auth_url,
        'dms-oauth',
        `width=${w},height=${h},left=${left},top=${top},popup=yes`
      );
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Erro ao iniciar conexão';
      toast.error(message);
    } finally {
      setConnecting(null);
    }
  }

  async function disconnectIntegration() {
    if (!disconnectTarget) return;
    setDisconnecting(true);
    try {
      await apiClient.disconnectDMS(disconnectTarget.id);
      toast.success('Integração desconectada');
      setDisconnectTarget(null);
      await loadData();
    } catch {
      toast.error('Erro ao desconectar integração');
    } finally {
      setDisconnecting(false);
    }
  }

  async function triggerSync(integrationId: string) {
    setSyncing(integrationId);
    try {
      const res = await apiClient.triggerDMSSync(integrationId);
      toast.success(res.message || 'Sincronização iniciada');
    } catch {
      toast.error('Erro ao sincronizar');
    } finally {
      setSyncing(null);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const connectedProviderIds = new Set(integrations.map((i) => i.provider));

  return (
    <div className="space-y-6">
      {/* Connected integrations */}
      {integrations.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-sm font-medium text-muted-foreground">Conectados</h4>
          {integrations.map((integration) => (
            <div
              key={integration.id}
              className="flex items-center justify-between rounded-lg border p-4"
            >
              <div className="flex items-center gap-3">
                <ProviderIcon
                  provider={integration.provider}
                  className="h-5 w-5 text-green-600"
                />
                <div>
                  <p className="font-medium">{integration.display_name}</p>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <CheckCircle2 className="h-3 w-3 text-green-500" />
                    Conectado
                    {integration.last_sync_at && (
                      <>
                        {' '}
                        &middot; Sincronizado em{' '}
                        {new Date(integration.last_sync_at).toLocaleDateString('pt-BR')}
                      </>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {integration.sync_enabled && (
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={syncing === integration.id}
                    onClick={() => triggerSync(integration.id)}
                  >
                    {syncing === integration.id ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <RefreshCw className="h-4 w-4" />
                    )}
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive hover:text-destructive"
                  onClick={() => setDisconnectTarget(integration)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Available providers */}
      <div className="space-y-3">
        <h4 className="text-sm font-medium text-muted-foreground">
          {integrations.length > 0 ? 'Adicionar Integração' : 'Provedores Disponíveis'}
        </h4>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {providers.map((provider) => {
            const isConnected = connectedProviderIds.has(provider.id);
            return (
              <div
                key={provider.id}
                className="flex flex-col justify-between rounded-lg border p-4"
              >
                <div className="mb-3">
                  <div className="flex items-center gap-2 mb-1">
                    <ProviderIcon provider={provider.id} className="h-5 w-5" />
                    <span className="font-medium">{provider.name}</span>
                    {isConnected && (
                      <Badge variant="secondary" className="text-xs">
                        Conectado
                      </Badge>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">{provider.description}</p>
                </div>
                <Button
                  variant={isConnected ? 'outline' : 'default'}
                  size="sm"
                  className="w-full"
                  disabled={connecting === provider.id}
                  onClick={() => connectProvider(provider.id)}
                >
                  {connecting === provider.id ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Conectando...
                    </>
                  ) : (
                    <>
                      <ExternalLink className="mr-2 h-4 w-4" />
                      {isConnected ? 'Reconectar' : 'Conectar'}
                    </>
                  )}
                </Button>
              </div>
            );
          })}
        </div>

        {providers.length === 0 && (
          <div className="flex items-center gap-2 rounded-lg border border-dashed p-6 text-muted-foreground">
            <AlertCircle className="h-5 w-5" />
            <p className="text-sm">
              Nenhum provedor DMS disponível. Verifique as configurações do servidor.
            </p>
          </div>
        )}
      </div>

      {/* Disconnect confirmation dialog */}
      <Dialog open={!!disconnectTarget} onOpenChange={() => setDisconnectTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Desconectar Integração</DialogTitle>
            <DialogDescription>
              Tem certeza que deseja desconectar{' '}
              <strong>{disconnectTarget?.display_name}</strong>? Os documentos já importados
              não serão afetados, mas a sincronização será interrompida.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDisconnectTarget(null)}>
              Cancelar
            </Button>
            <Button
              variant="destructive"
              disabled={disconnecting}
              onClick={disconnectIntegration}
            >
              {disconnecting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Desconectando...
                </>
              ) : (
                'Desconectar'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
