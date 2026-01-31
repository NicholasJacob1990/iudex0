'use client';

import React from 'react';
import { PageHero } from '@/components/vorbium/page-hero';
import { Footer } from '@/components/vorbium/footer';
import { VorbiumNav } from '@/components/vorbium/vorbium-nav';
import { FeatureSection } from '@/components/vorbium/feature-section';
import { Shield, Lock, FileKey, Server, EyeOff, Key, CheckCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Link from 'next/link';

export default function SecurityPage() {
    const mainRef = React.useRef<HTMLElement>(null);

    const features = [
        {
            title: "Criptografia de Ponta a Ponta",
            description: "Seus dados cifrados em trânsito e em repouso.",
            icon: Lock
        },
        {
            title: "Controle de Acesso (RBAC)",
            description: "Permissões granulares baseadas em função.",
            icon: Key
        },
        {
            title: "Privacidade de Dados",
            description: "Conformidade total com LGPD e GDPR.",
            icon: EyeOff
        },
        {
            title: "Infraestrutura Segura",
            description: "Hospedagem em ambiente certificado SOC2.",
            icon: Server
        }
    ];

    const certifications = [
        "SOC 2 Type II",
        "ISO 27001",
        "LGPD Compliant",
        "GDPR Compliant"
    ];

    return (
        <main
            ref={mainRef}
            className="relative h-[100dvh] overflow-y-auto bg-slate-50 dark:bg-[#0a0a0c] text-slate-900 dark:text-white selection:bg-indigo-500/30 snap-y snap-proximity scroll-smooth overscroll-y-contain"
        >
            <VorbiumNav scrollRef={mainRef} />

            <PageHero
                badge="Segurança e Compliance"
                title="Seus dados, protegidos."
                description="A VORBIUM adota os mais rigorosos padrões de segurança da informação para garantir a confidencialidade e integridade dos seus dados jurídicos."
                primaryCtaText="Ler Whitepaper de Segurança"
                primaryCtaLink="/demo"
            />

            <FeatureSection
                title="Pilares de Segurança"
                features={features}
                className="bg-white dark:bg-white/5 border-y border-slate-200 dark:border-white/5"
            />

            <section className="py-24 relative snap-start">
                <div className="container mx-auto px-6 text-center">
                    <h2 className="text-3xl font-bold mb-12 text-slate-900 dark:text-white">Certificações e Conformidade</h2>
                    <div className="flex flex-wrap justify-center gap-4 md:gap-8 text-slate-600 dark:text-gray-300">
                        {certifications.map((item, i) => (
                            <div key={i} className="flex items-center gap-3 px-6 py-4 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 hover:border-indigo-500/50 transition-colors">
                                <Shield className="h-6 w-6 text-emerald-500 dark:text-emerald-400" />
                                <span className="text-lg font-medium">{item}</span>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            <section className="py-24 relative snap-start text-center">
                <div className="container mx-auto px-6">
                    <h2 className="text-3xl md:text-4xl font-bold mb-8 text-slate-900 dark:text-white">Confiança é a nossa base.</h2>
                    <Link href="/demo">
                        <Button size="lg" className="h-14 px-12 rounded-full text-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-[0_0_40px_-10px_rgba(79,70,229,0.5)] transition-all hover:scale-105">
                            Falar com Segurança
                        </Button>
                    </Link>
                </div>
            </section>

            <Footer />
        </main>
    );
}
