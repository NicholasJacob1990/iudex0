'use client';

import React from 'react';
import { PageHero } from '@/components/vorbium/page-hero';
import { Footer } from '@/components/vorbium/footer';
import { VorbiumNav } from '@/components/vorbium/vorbium-nav';
import { FeatureSection } from '@/components/vorbium/feature-section';
import { Shield, Lock, FileKey, Server, EyeOff, Key, CheckCircle, BadgeCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { AnimatedContainer, StaggerContainer } from '@/components/ui/animated-container';
import { MotionDiv, fadeUp } from '@/components/ui/motion';

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
                worklet="grid-pulse"
                workletColor="#10b981"
                workletSeed={91}
            />

            <FeatureSection
                title="Pilares de Segurança"
                features={features}
                className="bg-white dark:bg-white/5 border-y border-slate-200 dark:border-white/5"
            />

            {/* Certification Badges Section */}
            <section className="py-24 relative snap-start bg-slate-900 dark:bg-[#050507] text-white overflow-hidden">
                <div className="container mx-auto px-6">
                    <AnimatedContainer className="text-center mb-16">
                        <div className="flex items-center justify-center gap-2 text-emerald-400 mb-6 uppercase tracking-[0.3em] text-xs font-semibold">
                            <span className="h-px w-10 bg-emerald-400/40" />
                            <span>Compliance</span>
                            <span className="h-px w-10 bg-emerald-400/40" />
                        </div>
                        <h2 className="text-3xl md:text-4xl font-bold mb-4">Certificações e Conformidade</h2>
                        <p className="text-xl text-gray-400 max-w-2xl mx-auto">
                            Padrões internacionais de segurança aplicados a toda a plataforma.
                        </p>
                    </AnimatedContainer>
                    <StaggerContainer className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 max-w-5xl mx-auto">
                        {[
                            { name: "SOC 2 Type II", description: "Auditoria independente de controles de segurança, disponibilidade e confidencialidade.", color: "from-emerald-500 to-green-600" },
                            { name: "ISO 27001", description: "Sistema de gestão de segurança da informação certificado internacionalmente.", color: "from-blue-500 to-cyan-600" },
                            { name: "LGPD", description: "Conformidade total com a Lei Geral de Proteção de Dados brasileira.", color: "from-indigo-500 to-orange-600" },
                            { name: "GDPR", description: "Atendimento ao Regulamento Geral de Proteção de Dados europeu.", color: "from-purple-500 to-indigo-600" },
                        ].map((cert, i) => (
                            <MotionDiv key={i} variants={fadeUp}>
                                <div className="p-6 rounded-2xl border border-white/10 bg-white/5 backdrop-blur-sm hover:bg-white/10 transition-all duration-300 h-full text-center">
                                    <div className={`h-16 w-16 rounded-2xl bg-gradient-to-br ${cert.color} flex items-center justify-center mb-5 mx-auto`}>
                                        <BadgeCheck className="h-8 w-8 text-white" />
                                    </div>
                                    <h3 className="text-xl font-bold mb-2">{cert.name}</h3>
                                    <p className="text-sm text-gray-400 leading-relaxed">{cert.description}</p>
                                </div>
                            </MotionDiv>
                        ))}
                    </StaggerContainer>
                </div>
            </section>

            {/* Data Protection Details */}
            <section className="py-24 relative snap-start">
                <AnimatedContainer className="container mx-auto px-6">
                    <div className="max-w-4xl mx-auto">
                        <div className="text-center mb-16">
                            <h2 className="text-3xl md:text-4xl font-bold mb-4 text-slate-900 dark:text-white">Proteção em cada camada</h2>
                        </div>
                        <StaggerContainer className="grid md:grid-cols-3 gap-8">
                            {[
                                { title: "Dados em trânsito", description: "TLS 1.3 para todas as comunicações. Nenhum dado trafega sem criptografia.", icon: Lock },
                                { title: "Dados em repouso", description: "AES-256 para armazenamento. Chaves gerenciadas com rotação automática.", icon: Key },
                                { title: "Isolamento de dados", description: "Cada cliente em ambiente isolado. Sem compartilhamento de contexto entre contas.", icon: Shield },
                            ].map((item, i) => (
                                <MotionDiv key={i} variants={fadeUp}>
                                    <div className="p-6 rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 h-full">
                                        <item.icon className="h-10 w-10 text-indigo-600 dark:text-indigo-400 mb-4" />
                                        <h3 className="text-lg font-bold mb-2 text-slate-900 dark:text-white">{item.title}</h3>
                                        <p className="text-sm text-slate-600 dark:text-gray-400 leading-relaxed">{item.description}</p>
                                    </div>
                                </MotionDiv>
                            ))}
                        </StaggerContainer>
                    </div>
                </AnimatedContainer>
            </section>

            <section className="py-24 relative snap-start text-center">
                <AnimatedContainer className="container mx-auto px-6">
                    <h2 className="text-3xl md:text-4xl font-bold mb-8 text-slate-900 dark:text-white">Confiança é a nossa base.</h2>
                    <Link href="/demo">
                        <Button size="lg" className="h-14 px-12 rounded-full text-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-[0_0_40px_-10px_rgba(79,70,229,0.5)] transition-all hover:scale-105">
                            Falar com Segurança
                        </Button>
                    </Link>
                </AnimatedContainer>
            </section>

            <Footer />
        </main>
    );
}
