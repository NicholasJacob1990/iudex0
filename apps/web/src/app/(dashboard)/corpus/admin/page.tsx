'use client';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { AnimatedContainer } from '@/components/ui/animated-container';
import { BarChart3, Users, Activity, Shield } from 'lucide-react';
import { useAuthStore } from '@/stores/auth-store';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { CorpusAdminOverviewPanel } from './corpus-admin-overview';
import { CorpusAdminUsersPanel } from './corpus-admin-users';
import { CorpusAdminActivityPanel } from './corpus-admin-activity';

export default function CorpusAdminPage() {
  const { user } = useAuthStore();
  const router = useRouter();

  // Redirecionar se nao for admin
  useEffect(() => {
    if (user && user.role !== 'ADMIN') {
      router.push('/corpus');
    }
  }, [user, router]);

  if (!user || user.role !== 'ADMIN') {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center space-y-2">
          <Shield className="h-12 w-12 text-muted-foreground mx-auto" />
          <p className="text-lg font-medium text-foreground">Acesso Restrito</p>
          <p className="text-sm text-muted-foreground">
            Esta pagina e exclusiva para administradores.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <AnimatedContainer>
        <div className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft">
          <div className="flex items-center gap-3 mb-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-red-50">
              <Shield className="h-5 w-5 text-red-600" />
            </div>
            <div>
              <p className="text-xs font-semibold uppercase text-muted-foreground">
                Administracao
              </p>
              <h1 className="font-display text-3xl text-foreground">
                Painel Administrativo do Corpus
              </h1>
            </div>
          </div>
          <p className="text-sm text-muted-foreground mt-2">
            Visibilidade completa sobre todos os documentos, usuarios e atividades do Corpus
            na organizacao. Gerencie propriedade, monitore ingestao e acompanhe o uso.
          </p>
        </div>
      </AnimatedContainer>

      {/* Tabs */}
      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList className="grid w-full grid-cols-3 rounded-xl bg-muted/80 p-1">
          <TabsTrigger
            value="overview"
            className="rounded-lg gap-2 data-[state=active]:bg-white data-[state=active]:shadow-sm"
          >
            <BarChart3 className="h-4 w-4" />
            <span className="hidden sm:inline">Visao Geral</span>
            <span className="sm:hidden">Geral</span>
          </TabsTrigger>
          <TabsTrigger
            value="users"
            className="rounded-lg gap-2 data-[state=active]:bg-white data-[state=active]:shadow-sm"
          >
            <Users className="h-4 w-4" />
            <span className="hidden sm:inline">Usuarios</span>
            <span className="sm:hidden">Usuarios</span>
          </TabsTrigger>
          <TabsTrigger
            value="activity"
            className="rounded-lg gap-2 data-[state=active]:bg-white data-[state=active]:shadow-sm"
          >
            <Activity className="h-4 w-4" />
            <span className="hidden sm:inline">Atividade</span>
            <span className="sm:hidden">Atividade</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <CorpusAdminOverviewPanel />
        </TabsContent>

        <TabsContent value="users">
          <CorpusAdminUsersPanel />
        </TabsContent>

        <TabsContent value="activity">
          <CorpusAdminActivityPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}
