'use client';

import React from 'react';
import { PageHero } from '@/components/vorbium/page-hero';
import { Footer } from '@/components/vorbium/footer';
import { VorbiumNav } from '@/components/vorbium/vorbium-nav';
import { FeatureSection } from '@/components/vorbium/feature-section';
import { Brain, Search, PenTool, MessageSquare, Zap, Layers, CheckCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Link from 'next/link';

export default function PlatformPage() {
    const mainRef = React.useRef<HTMLElement>(null);

    const features = [
        {
            title: "Assistente IA",
            description: "Seu copiloto jurídico para análise e redação.",
            icon: Brain
        },
        {
            title: "Pesquisa Avançada",
            description: "Encontre precedentes e doutrina com contexto.",
            icon: Search
        },
        {
            title: "Editor Inteligente",
            description: "Crie documentos complexos com autofill inteligente.",
            icon: PenTool
        },
        {
            title: "Auditoria Automática",
            description: "Verifique consistência e erros antes de enviar.",
            icon: CheckCircle
        }
    ];

    const integrations = [
        {
            title: "Integração API",
            description: "Conecte-se aos seus sistemas existentes (ERP, CRM).",
            icon: Zap
        },
        {
            title: "Workflows Customizáveis",
            description: "Crie fluxos de trabalho que se adaptam ao seu time.",
            icon: Layers
        }
    ];

    return (
        <main
            ref={mainRef}
            className="relative h-[100dvh] overflow-y-auto bg-slate-50 dark:bg-[#0a0a0c] text-slate-900 dark:text-white selection:bg-indigo-500/30 snap-y snap-proximity scroll-smooth overscroll-y-contain"
        >
            <VorbiumNav scrollRef={mainRef} />

            <PageHero
                badge="Plataforma Integrada"
                title="Tudo o que você precisa, em um só lugar."
                description="A Plataforma VORBIUM unifica pesquisa, redação, revisão e colaboração em um ambiente seguro e potencializado por IA."
                primaryCtaText="Conhecer a Plataforma"
                primaryCtaLink="/demo"
            />

            <FeatureSection
                title="Módulos da Plataforma"
                features={features}
                className="bg-white dark:bg-white/5 border-y border-slate-200 dark:border-white/5"
            />

            <FeatureSection
                title="Integração e Extensibilidade"
                features={integrations}
                className="bg-slate-50 dark:bg-transparent"
            />

            <section className="py-24 relative snap-start text-center">
                <div className="container mx-auto px-6">
                    <h2 className="text-3xl md:text-4xl font-bold mb-8 text-slate-900 dark:text-white">Potencialize sua prática jurídica.</h2>
                    <Link href="/demo">
                        <Button size="lg" className="h-14 px-12 rounded-full text-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-[0_0_40px_-10px_rgba(79,70,229,0.5)] transition-all hover:scale-105">
                            Agendar Demo
                        </Button>
                    </Link>
                </div>
            </section>

            <Footer />
        </main>
    );
}
