'use client';

import React, { useCallback, useEffect, useState } from 'react';
import {
  Cloud,
  Building2,
  HardDrive,
  Briefcase,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
  Link2,
  Unlink,
  RefreshCw,
  FolderOpen,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api-client';
import { DMSFileBrowser } from './dms-file-browser';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

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
  root_folder_id: string | null;
  sync_enabled: boolean;
  last_sync_at: string | null;
  connection_status: string | null;
  provider_metadata: Record<string, unknown> | null;
  created_at: string;
}

interface Props {
  targetCorpusProjectId?: string;
  onImportComplete?: (documentIds: string[]) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const PROVIDER_ICONS: Record<string, React.ReactNode> = {
  google_drive: <Cloud className="h-6 w-6 text-blue-500" />,
  sharepoint: <Building2 className="h-6 w-6 text-teal-600" />,
  onedrive: <HardDrive className="h-6 w-6 text-blue-600" />,
  imanage: <Briefcase className="h-6 w-6 text-amber-600" />,
};

const STATUS_CONFIG: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
  connected: {
    icon: <CheckCircle2 className="h-4 w-4 text-green-500" />,
    label: 'Conectado',
    color: 'bg-green-100 text-green-800',
  },
  expired: {
    icon: <AlertCircle className="h-4 w-4 text-amber-500" />,
    label: 'Token expirado',
    color: 'bg-amber-100 text-amber-800',
  },
  error: {
    icon: <XCircle className="h-4 w-4 text-red-500" />,
    label: 'Erro',
    color: 'bg-red-100 text-red-800',
  },
  disconnected: {
    icon: <XCircle className="h-4 w-4 text-slate-400" />,
    label: 'Desconectado',
    color: 'bg-slate-100 text-slate-600',
  },
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function DMSConnectionPanel({ targetCorpusProjectId, onImportComplete }: Props) {
  const [providers, setProviders] = useState<DMSProvider[]>([]);
  const [integrations, setIntegrations] = useState<DMSIntegration[]>([]);
  const [loading, setLoading] = useState(true);
  const [connectingProvider, setConnectingProvider] = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState<string | null>(null);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [browseIntegration, setBrowseIntegration] = useState<DMSIntegration | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [providersRes, integrationsRes] = await Promise.all([
        apiClient.getDMSProviders(),
        apiClient.getDMSIntegrations(),
      ]);
      setProviders(providersRes.providers || []);
      setIntegrations(integrationsRes.integrations || []);
    } catch {
      toast.error('Erro ao carregar integrações DMS.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const getIntegrationForProvider = (providerId: string): DMSIntegration | undefined => {
    return integrations.find((i) => i.provider === providerId);
  };

  const handleConnect = async (providerId: string) => {
    setConnectingProvider(providerId);
    try {
      const redirectUrl = `${window.location.origin}/api/dms/callback`;
      const res = await apiClient.startDMSConnect(providerId, '', redirectUrl);
      // Redirect to OAuth flow
      window.location.href = res.auth_url;
    } catch {
      toast.error('Erro ao iniciar conexão com o DMS.');
      setConnectingProvider(null);
    }
  };

  const handleDisconnect = async (integrationId: string) => {
    setDisconnecting(integrationId);
    try {
      await apiClient.disconnectDMS(integrationId);
      toast.success('Integração desconectada com sucesso.');
      await fetchData();
    } catch {
      toast.error('Erro ao desconectar integração.');
    } finally {
      setDisconnecting(null);
    }
  };

  const handleSync = async (integrationId: string) => {
    setSyncing(integrationId);
    try {
      await apiClient.triggerDMSSync(integrationId);
      toast.success('Sincronização iniciada.');
      await fetchData();
    } catch {
      toast.error('Erro ao sincronizar.');
    } finally {
      setSyncing(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">Integrações DMS</h3>
          <Button variant="ghost" size="sm" onClick={fetchData}>
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {providers.map((provider) => {
            const integration = getIntegrationForProvider(provider.id);
            const isConnected = !!integration;
            const status = integration?.connection_status || 'disconnected';
            const statusConfig = STATUS_CONFIG[status] || STATUS_CONFIG.disconnected;

            return (
              <Card key={provider.id} className={isConnected ? 'border-primary/30' : ''}>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      {PROVIDER_ICONS[provider.id] || <Cloud className="h-6 w-6" />}
                      <div>
                        <CardTitle className="text-base">{provider.name}</CardTitle>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {provider.description}
                        </p>
                      </div>
                    </div>
                    <Badge variant="secondary" className={statusConfig.color}>
                      {statusConfig.icon}
                      <span className="ml-1">{statusConfig.label}</span>
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent>
                  {isConnected ? (
                    <div className="space-y-3">
                      <div className="text-xs text-muted-foreground">
                        <span className="font-medium">{integration.display_name}</span>
                        {integration.last_sync_at && (
                          <span className="ml-2">
                            Sincronizado em{' '}
                            {new Date(integration.last_sync_at).toLocaleDateString('pt-BR')}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setBrowseIntegration(integration)}
                        >
                          <FolderOpen className="mr-1 h-3 w-3" />
                          Navegar Arquivos
                        </Button>
                        {provider.supports_sync && (
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={syncing === integration.id}
                            onClick={() => handleSync(integration.id)}
                          >
                            {syncing === integration.id ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              <RefreshCw className="h-3 w-3" />
                            )}
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive hover:text-destructive"
                          disabled={disconnecting === integration.id}
                          onClick={() => handleDisconnect(integration.id)}
                        >
                          {disconnecting === integration.id ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <Unlink className="h-3 w-3" />
                          )}
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <Button
                      className="w-full"
                      variant="outline"
                      disabled={connectingProvider === provider.id}
                      onClick={() => handleConnect(provider.id)}
                    >
                      {connectingProvider === provider.id ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Conectando...
                        </>
                      ) : (
                        <>
                          <Link2 className="mr-2 h-4 w-4" />
                          Conectar {provider.name}
                        </>
                      )}
                    </Button>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>

      {/* File Browser Dialog */}
      <Dialog open={!!browseIntegration} onOpenChange={() => setBrowseIntegration(null)}>
        <DialogContent className="max-w-3xl h-[600px] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {browseIntegration &&
                (PROVIDER_ICONS[browseIntegration.provider] || <Cloud className="h-5 w-5" />)}
              {browseIntegration?.display_name || 'Navegar Arquivos'}
            </DialogTitle>
          </DialogHeader>
          <div className="flex-1 min-h-0">
            {browseIntegration && (
              <DMSFileBrowser
                integrationId={browseIntegration.id}
                targetCorpusProjectId={targetCorpusProjectId}
                onImportComplete={(ids) => {
                  onImportComplete?.(ids);
                  setBrowseIntegration(null);
                }}
              />
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
