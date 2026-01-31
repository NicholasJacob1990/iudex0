'use client';

import React from 'react';
import { PageHero } from '@/components/vorbium/page-hero';
import { Footer } from '@/components/vorbium/footer';
import { VorbiumNav } from '@/components/vorbium/vorbium-nav';
import { FeatureSection } from '@/components/vorbium/feature-section';
import { Building2, Scale, Gavel, Globe, CheckCircle, TrendingUp, Clock, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Link from 'next/link';

export default function CustomersPage() {
    const mainRef = React.useRef<HTMLElement>(null);

    const sectors = [
        {
            title: "Escritórios de Advocacia",
            description: "Aumente a eficiência e a qualidade das entregas.",
            icon: Scale
        },
        {
            title: "Departamentos Jurídicos",
            description: "Gerencie demandas internas com mais agilidade.",
            icon: Building2
        },
        {
            title: "Tribunais e Órgãos Públicos",
            description: "Modernize a análise e processamento de casos.",
            icon: Gavel
        },
        {
            title: "Consultorias Globais",
            description: "Pesquisa e compliance em múltiplas jurisdições.",
            icon: Globe
        }
    ];

    const results = [
        {
            title: "Redução de Tempo",
            description: "70% menos tempo gasto em pesquisa e redação preliminar.",
            icon: Clock
        },
        {
            title: "Aumento de Capacidade",
            description: "Equipes focam em estratégia, não em braçal.",
            icon: TrendingUp
        },
        {
            title: "Mitigação de Riscos",
            description: "Auditoria automática reduz erros humanos.",
            icon: ShieldCheck
        },
        {
            title: "Padronização",
            description: "Consistência em todos os documentos produzidos.",
            icon: CheckCircle
        }
    ];

    return (
        <main
            ref={mainRef}
            className="relative h-[100dvh] overflow-y-auto bg-slate-50 dark:bg-[#0a0a0c] text-slate-900 dark:text-white selection:bg-indigo-500/30 snap-y snap-proximity scroll-smooth overscroll-y-contain"
        >
            <VorbiumNav scrollRef={mainRef} />

            <PageHero
                badge="Nossos Clientes"
                title="Quem confia na VORBIUM."
                description="Líderes jurídicos que transformaram suas operações com inteligência artificial governada e segura."
                primaryCtaText="Ver Casos de Sucesso"
                primaryCtaLink="/demo"
            />

            <FeatureSection
                title="Setores Atendidos"
                features={sectors}
                className="bg-white dark:bg-white/5 border-y border-slate-200 dark:border-white/5"
            />

            <section className="py-24 relative snap-start">
                <div className="container mx-auto px-6 text-center">
                    <div className="mb-16">
                        <h2 className="text-3xl md:text-4xl font-bold mb-4 text-slate-900 dark:text-white">Resultados Reais</h2>
                        <p className="text-xl text-slate-600 dark:text-gray-400 max-w-2xl mx-auto">
                            O impacto da VORBIUM na operação dos nossos parceiros.
                        </p>
                    </div>

                    <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8">
                        {results.map((item, i) => (
                            <div key={i} className="flex flex-col items-center p-6 rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5">
                                <item.icon className="h-12 w-12 text-indigo-600 dark:text-indigo-400 mb-4" />
                                <h3 className="text-lg font-bold mb-2 text-slate-900 dark:text-white">{item.title}</h3>
                                <p className="text-sm text-slate-600 dark:text-gray-400">{item.description}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            <section className="py-24 relative snap-start text-center">
                <div className="container mx-auto px-6">
                    <h2 className="text-3xl md:text-4xl font-bold mb-8 text-slate-900 dark:text-white">Junte-se à inovação jurídica.</h2>
                    <Link href="/demo">
                        <Button size="lg" className="h-14 px-12 rounded-full text-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-[0_0_40px_-10px_rgba(79,70,229,0.5)] transition-all hover:scale-105">
                            Falar com Vendas
                        </Button>
                    </Link>
                </div>
            </section>

            <Footer />
        </main>
    );
}
