'use client';

import { useState, useEffect } from 'react';
import { useAuthStore } from '@/stores';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { MCPServersConfig } from '@/components/settings/mcp-servers-config';
import { DMSIntegrations } from '@/components/settings/dms-integrations';
import { apiClient } from '@/lib/api-client';
import { Scale, Eye, EyeOff, CheckCircle, CloudCog } from 'lucide-react';

export default function SettingsPage() {
  const { user } = useAuthStore();

  // PJe credentials state
  const [pjeCpf, setPjeCpf] = useState('');
  const [pjeSenha, setPjeSenha] = useState('');
  const [pjeSenhaSet, setPjeSenhaSet] = useState(false);
  const [showPjeSenha, setShowPjeSenha] = useState(false);
  const [pjeSaving, setPjeSaving] = useState(false);
  const [pjeSaved, setPjeSaved] = useState(false);

  useEffect(() => {
    apiClient.getPreferences().then((data: any) => {
      const creds = data?.preferences?.pje_credentials || {};
      if (creds.cpf) setPjeCpf(creds.cpf);
      if (creds.senha_set) setPjeSenhaSet(true);
    }).catch(() => {});
  }, []);

  const savePjeCredentials = async () => {
    setPjeSaving(true);
    try {
      await apiClient.updatePreferences({
        pje_credentials: { cpf: pjeCpf, senha: pjeSenha || undefined },
      });
      setPjeSaved(true);
      if (pjeSenha) setPjeSenhaSet(true);
      setPjeSenha('');
      setTimeout(() => setPjeSaved(false), 3000);
    } catch {
      // silently handle
    } finally {
      setPjeSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Configurações</h1>
        <p className="text-muted-foreground">
          Gerencie suas preferências e configurações
        </p>
      </div>

      {/* Profile */}
      <Card>
        <CardHeader>
          <CardTitle>Perfil</CardTitle>
          <CardDescription>
            Informações da sua conta
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Nome</Label>
            <Input id="name" defaultValue={user?.name} />
          </div>

          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" defaultValue={user?.email} />
          </div>

          <Button>Salvar Alterações</Button>
        </CardContent>
      </Card>

      {/* Password */}
      <Card>
        <CardHeader>
          <CardTitle>Senha</CardTitle>
          <CardDescription>
            Altere sua senha
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="currentPassword">Senha Atual</Label>
            <Input id="currentPassword" type="password" />
          </div>

          <div className="space-y-2">
            <Label htmlFor="newPassword">Nova Senha</Label>
            <Input id="newPassword" type="password" />
          </div>

          <div className="space-y-2">
            <Label htmlFor="confirmPassword">Confirmar Nova Senha</Label>
            <Input id="confirmPassword" type="password" />
          </div>

          <Button>Atualizar Senha</Button>
        </CardContent>
      </Card>

      {/* Preferences */}
      <Card>
        <CardHeader>
          <CardTitle>Preferências</CardTitle>
          <CardDescription>
            Configure suas preferências de geração de documentos
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="style">Estilo de Escrita</Label>
            <select id="style" className="w-full rounded-md border p-2">
              <option>Formal</option>
              <option>Técnico</option>
              <option>Objetivo</option>
            </select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="language">Linguagem</Label>
            <select id="language" className="w-full rounded-md border p-2">
              <option>Português (Brasil)</option>
              <option>Português (Portugal)</option>
            </select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="institution">Instituição</Label>
            <Input id="institution" placeholder="Nome da instituição" />
          </div>

          <div className="space-y-2">
            <Label htmlFor="role">Cargo/Função</Label>
            <Input id="role" placeholder="Ex: Advogado, Juiz, Promotor" />
          </div>

          <Button>Salvar Preferências</Button>
        </CardContent>
      </Card>

      {/* PJe Credentials */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Scale className="h-5 w-5 text-blue-600" />
            Credenciais PJe
          </CardTitle>
          <CardDescription>
            Configure suas credenciais do PJe (MNI) para consulta de processos nos workflows.
            As credenciais ficam armazenadas de forma segura no seu perfil.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="pje-cpf">CPF</Label>
            <Input
              id="pje-cpf"
              placeholder="000.000.000-00"
              value={pjeCpf}
              onChange={(e) => setPjeCpf(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="pje-senha">Senha MNI</Label>
            <div className="relative">
              <Input
                id="pje-senha"
                type={showPjeSenha ? 'text' : 'password'}
                placeholder={pjeSenhaSet ? '••••••• (já configurada)' : 'Sua senha do PJe'}
                value={pjeSenha}
                onChange={(e) => setPjeSenha(e.target.value)}
              />
              <button
                type="button"
                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                onClick={() => setShowPjeSenha(!showPjeSenha)}
              >
                {showPjeSenha ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            <p className="text-xs text-muted-foreground">
              Utilizada para autenticação no Modelo Nacional de Interoperabilidade (MNI) do PJe.
            </p>
          </div>
          <Button onClick={savePjeCredentials} disabled={pjeSaving || !pjeCpf}>
            {pjeSaved ? (
              <><CheckCircle className="mr-2 h-4 w-4" /> Salvo</>
            ) : pjeSaving ? 'Salvando...' : 'Salvar Credenciais PJe'}
          </Button>
        </CardContent>
      </Card>

      {/* DMS Integrations */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CloudCog className="h-5 w-5 text-indigo-600" />
            Integrações DMS
          </CardTitle>
          <CardDescription>
            Conecte serviços de armazenamento externo (Google Drive, SharePoint, OneDrive) para
            importar e sincronizar documentos diretamente no Corpus.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <DMSIntegrations />
        </CardContent>
      </Card>

      {/* MCP Servers */}
      <Card>
        <CardHeader>
          <CardTitle>Servidores MCP</CardTitle>
          <CardDescription>
            Gerencie servidores MCP personalizados para expandir as ferramentas de IA
          </CardDescription>
        </CardHeader>
        <CardContent>
          <MCPServersConfig />
        </CardContent>
      </Card>
    </div>
  );
}

