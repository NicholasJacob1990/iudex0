'use client';

import { useEffect, useState } from 'react';
import { useAuthStore, useOrgStore } from '@/stores';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { Building2, UserPlus, Users, Shield, Trash2 } from 'lucide-react';

const ROLE_LABELS: Record<string, string> = {
  admin: 'Administrador',
  advogado: 'Advogado',
  estagiario: 'Estagiário',
};

export default function OrganizationPage() {
  const { user } = useAuthStore();
  const {
    organization,
    members,
    teams,
    isLoading,
    fetchOrganization,
    fetchMembers,
    fetchTeams,
    createOrganization,
    inviteMember,
    updateMemberRole,
    removeMember,
    createTeam,
  } = useOrgStore();

  const [orgName, setOrgName] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('advogado');
  const [teamName, setTeamName] = useState('');

  useEffect(() => {
    if (user?.organization_id) {
      fetchOrganization();
      fetchMembers();
      fetchTeams();
    }
  }, [user?.organization_id, fetchOrganization, fetchMembers, fetchTeams]);

  const handleCreateOrg = async () => {
    if (!orgName.trim()) return;
    try {
      await createOrganization({ name: orgName });
      toast.success('Organização criada com sucesso!');
      setOrgName('');
      // Refresh profile to get updated organization_id
      window.location.reload();
    } catch {
      toast.error('Erro ao criar organização');
    }
  };

  const handleInvite = async () => {
    if (!inviteEmail.trim()) return;
    try {
      await inviteMember(inviteEmail, inviteRole);
      toast.success(`Convite enviado para ${inviteEmail}`);
      setInviteEmail('');
    } catch {
      toast.error('Erro ao convidar membro');
    }
  };

  const handleCreateTeam = async () => {
    if (!teamName.trim()) return;
    try {
      await createTeam({ name: teamName });
      toast.success(`Equipe "${teamName}" criada`);
      setTeamName('');
    } catch {
      toast.error('Erro ao criar equipe');
    }
  };

  // No org — show creation form
  if (!user?.organization_id) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold">Organização</h1>
          <p className="text-muted-foreground">
            Crie uma organização para compartilhar casos e documentos com sua equipe
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Building2 className="h-5 w-5" />
              Criar Organização
            </CardTitle>
            <CardDescription>
              Ao criar uma organização, você será o administrador e poderá convidar membros.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="org-name">Nome do Escritório</Label>
              <Input
                id="org-name"
                placeholder="Ex: Silva & Associados"
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
              />
            </div>
            <Button onClick={handleCreateOrg} disabled={isLoading || !orgName.trim()}>
              {isLoading ? 'Criando...' : 'Criar Organização'}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Organização</h1>
        <p className="text-muted-foreground">
          Gerencie sua organização, membros e equipes
        </p>
      </div>

      {/* Org Info */}
      {organization && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Building2 className="h-5 w-5" />
              {organization.name}
            </CardTitle>
            <CardDescription>
              Plano {organization.plan} · {organization.member_count} membro(s) de {organization.max_members}
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {/* Members */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5" />
            Membros ({members.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="divide-y divide-border rounded-lg border">
            {members.map((member) => (
              <div key={member.user_id} className="flex items-center justify-between p-3">
                <div>
                  <p className="text-sm font-medium">{member.user_name}</p>
                  <p className="text-xs text-muted-foreground">{member.user_email}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium">
                    <Shield className="h-3 w-3" />
                    {ROLE_LABELS[member.role] || member.role}
                  </span>
                  {member.user_id !== user?.id && (
                    <select
                      className="h-8 rounded border bg-background px-2 text-xs"
                      value={member.role}
                      onChange={(e) => updateMemberRole(member.user_id, e.target.value)}
                    >
                      <option value="admin">Administrador</option>
                      <option value="advogado">Advogado</option>
                      <option value="estagiario">Estagiário</option>
                    </select>
                  )}
                  {member.user_id !== user?.id && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        if (confirm(`Remover ${member.user_name}?`)) {
                          removeMember(member.user_id);
                        }
                      }}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Invite */}
          <div className="flex items-end gap-3 pt-4">
            <div className="flex-1 space-y-2">
              <Label>Convidar membro</Label>
              <Input
                placeholder="email@escritorio.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
              />
            </div>
            <select
              className="h-10 rounded border bg-background px-3 text-sm"
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value)}
            >
              <option value="advogado">Advogado</option>
              <option value="estagiario">Estagiário</option>
              <option value="admin">Admin</option>
            </select>
            <Button onClick={handleInvite} disabled={!inviteEmail.trim()}>
              <UserPlus className="mr-2 h-4 w-4" />
              Convidar
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Teams */}
      <Card>
        <CardHeader>
          <CardTitle>Equipes ({teams.length})</CardTitle>
          <CardDescription>Organize membros em equipes de trabalho</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {teams.length > 0 && (
            <div className="divide-y divide-border rounded-lg border">
              {teams.map((team) => (
                <div key={team.id} className="flex items-center justify-between p-3">
                  <div>
                    <p className="text-sm font-medium">{team.name}</p>
                    {team.description && (
                      <p className="text-xs text-muted-foreground">{team.description}</p>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">{team.member_count} membro(s)</span>
                </div>
              ))}
            </div>
          )}

          <div className="flex items-end gap-3">
            <div className="flex-1 space-y-2">
              <Label>Nova equipe</Label>
              <Input
                placeholder="Ex: Contencioso Cível"
                value={teamName}
                onChange={(e) => setTeamName(e.target.value)}
              />
            </div>
            <Button onClick={handleCreateTeam} disabled={!teamName.trim()}>
              Criar Equipe
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
