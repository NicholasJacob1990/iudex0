'use client';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { AnimatedContainer } from '@/components/ui/animated-container';
import { Button } from '@/components/ui/button';
import { Globe, Building2, Clock, Shield, Table2 } from 'lucide-react';
import { useAuthStore } from '@/stores/auth-store';
import Link from 'next/link';
import { CorpusStats } from './components/corpus-stats';
import { CorpusGlobalTab } from './components/corpus-global-tab';
import { CorpusPrivateTab } from './components/corpus-private-tab';
import { CorpusLocalTab } from './components/corpus-local-tab';

export default function CorpusPage() {
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'ADMIN';

  return (
    <div className="space-y-8">
      {/* Header */}
      <AnimatedContainer>
        <div className="rounded-3xl border border-white/70 bg-white/95 p-6 shadow-soft">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs font-semibold uppercase text-muted-foreground">Corpus</p>
              <h1 className="font-display text-3xl text-foreground">
                Base de conhecimento juridico unificada.
              </h1>
              <p className="text-sm text-muted-foreground">
                Gerencie legislacao, jurisprudencia, doutrina e documentos privados que alimentam a IA.
                Inspirado no conceito de <em>corpus juris</em>.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Link href="/corpus/review">
                <Button variant="outline" size="sm" className="gap-2 rounded-full">
                  <Table2 className="h-4 w-4" />
                  <span className="hidden sm:inline">Review Tables</span>
                </Button>
              </Link>
              {isAdmin && (
                <Link href="/corpus/admin">
                  <Button variant="outline" size="sm" className="gap-2 rounded-full">
                    <Shield className="h-4 w-4" />
                    <span className="hidden sm:inline">Painel Admin</span>
                  </Button>
                </Link>
              )}
            </div>
          </div>
        </div>
      </AnimatedContainer>

      {/* Stats Overview */}
      <CorpusStats />

      {/* Tabs */}
      <Tabs defaultValue="global" className="space-y-6">
        <TabsList className="grid w-full grid-cols-3 rounded-xl bg-muted/80 p-1">
          <TabsTrigger value="global" className="rounded-lg gap-2 data-[state=active]:bg-white data-[state=active]:shadow-sm">
            <Globe className="h-4 w-4" />
            <span className="hidden sm:inline">Corpus Global</span>
            <span className="sm:hidden">Global</span>
          </TabsTrigger>
          <TabsTrigger value="private" className="rounded-lg gap-2 data-[state=active]:bg-white data-[state=active]:shadow-sm">
            <Building2 className="h-4 w-4" />
            <span className="hidden sm:inline">Corpus Privado</span>
            <span className="sm:hidden">Privado</span>
          </TabsTrigger>
          <TabsTrigger value="local" className="rounded-lg gap-2 data-[state=active]:bg-white data-[state=active]:shadow-sm">
            <Clock className="h-4 w-4" />
            <span className="hidden sm:inline">Corpus Local</span>
            <span className="sm:hidden">Local</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="global">
          <CorpusGlobalTab />
        </TabsContent>

        <TabsContent value="private">
          <CorpusPrivateTab />
        </TabsContent>

        <TabsContent value="local">
          <CorpusLocalTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
