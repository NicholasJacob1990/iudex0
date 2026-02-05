'use client';

import React from 'react';
import { PageHero } from '@/components/vorbium/page-hero';
import { Footer } from '@/components/vorbium/footer';
import { VorbiumNav } from '@/components/vorbium/vorbium-nav';
import { FeatureSection } from '@/components/vorbium/feature-section';
import { Users, MessageSquare, History, Share2, GitBranch, Lock, CheckCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Link from 'next/link';

export default function CollaborationPage() {
    const mainRef = React.useRef<HTMLElement>(null);

    const features = [
        {
            title: "Edição em tempo real",
            description: "Trabalhe simultaneamente no mesmo documento.",
            icon: Users
        },
        {
            title: "Comentários contextuais",
            description: "Discuta pontos específicos sem sair do fluxo.",
            icon: MessageSquare
        },
        {
            title: "Histórico de versões",
            description: "Controle total de alterações e quem fez o quê.",
            icon: History
        },
        {
            title: "Compartilhamento seguro",
            description: "Permissões granulares por usuário ou equipe.",
            icon: Share2
        }
    ];

    const workflowSteps = [
        {
            title: "Rascunho colaborativo",
            description: "Múltiplos autores, uma única fonte de verdade.",
            icon: Users
        },
        {
            title: "Revisão e Aprovação",
            description: "Fluxos de aprovação integrados ao documento.",
            icon: CheckCircle
        },
        {
            title: "Controle de Alterações",
            description: "Compare versões e aceite/rejeite mudanças.",
            icon: GitBranch
        },
        {
            title: "Entrega Segura",
            description: "Links de visualização ou exportação protegida.",
            icon: Lock
        }
    ];

    return (
        <main
            ref={mainRef}
            className="relative h-[100dvh] overflow-y-auto bg-slate-50 dark:bg-[#0a0a0c] text-slate-900 dark:text-white selection:bg-indigo-500/30 snap-y snap-proximity scroll-smooth overscroll-y-contain"
        >
            <VorbiumNav scrollRef={mainRef} />

            <PageHero
                badge="Colaboração sem atrito"
                title="Construa documentos jurídicos em equipe."
                description="A VORBIUM Collaboration permite que equipes jurídicas trabalhem juntas em tempo real, com controle de versão, comentários e fluxos de aprovação integrados."
                primaryCtaText="Experimentar Collaboration"
                primaryCtaLink="/demo"
                worklet="nebula-flow"
                workletColor="#06b6d4"
                workletSeed={83}
            />

            <FeatureSection
                title="Recursos de Colaboração"
                features={features}
                className="bg-white dark:bg-white/5 border-y border-slate-200 dark:border-white/5"
            />

            <section className="py-24 relative snap-start">
                <div className="container mx-auto px-6">
                    <div className="mb-16 text-center">
                        <h2 className="text-3xl md:text-4xl font-bold mb-4 text-slate-900 dark:text-white">Fluxo de Trabalho Unificado</h2>
                        <p className="text-xl text-slate-600 dark:text-gray-400 max-w-2xl mx-auto">
                            Do rascunho à assinatura, mantenha todos na mesma página.
                        </p>
                    </div>

                    <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8">
                        {workflowSteps.map((item, i) => (
                            <div key={i} className="relative p-8 rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 shadow-sm dark:shadow-none hover:border-indigo-500/30 transition-colors">
                                <item.icon className="h-10 w-10 text-indigo-600 dark:text-indigo-400 mb-6" />
                                <h3 className="text-xl font-bold mb-3 text-slate-900 dark:text-white">{item.title}</h3>
                                <p className="text-slate-600 dark:text-gray-400 leading-relaxed">{item.description}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            <section className="py-24 relative snap-start text-center">
                <div className="container mx-auto px-6">
                    <h2 className="text-3xl md:text-4xl font-bold mb-8 text-slate-900 dark:text-white">Pare de enviar anexos por e-mail.</h2>
                    <Link href="/demo">
                        <Button size="lg" className="h-14 px-12 rounded-full text-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-[0_0_40px_-10px_rgba(79,70,229,0.5)] transition-all hover:scale-105">
                            Começar Agora
                        </Button>
                    </Link>
                </div>
            </section>

            <Footer />
        </main>
    );
}
