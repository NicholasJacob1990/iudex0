'use client';

import React from 'react';
import { PageHero } from '@/components/vorbium/page-hero';
import { Footer } from '@/components/vorbium/footer';
import { VorbiumNav } from '@/components/vorbium/vorbium-nav';
import { FeatureSection } from '@/components/vorbium/feature-section';
import { Building2, Scale, Gavel, Globe, CheckCircle, TrendingUp, Clock, ShieldCheck, Quote } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { AnimatedContainer, StaggerContainer } from '@/components/ui/animated-container';
import { MotionDiv, fadeUp } from '@/components/ui/motion';

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

            {/* Impact Metrics - Large Numbers */}
            <section className="py-24 relative snap-start bg-white dark:bg-white/5 border-y border-slate-200 dark:border-white/5">
                <AnimatedContainer className="container mx-auto px-6">
                    <div className="text-center mb-16">
                        <h2 className="text-3xl md:text-4xl font-bold mb-4 text-slate-900 dark:text-white">Impacto mensuravel</h2>
                        <p className="text-xl text-slate-600 dark:text-gray-400 max-w-2xl mx-auto">
                            Resultados reais na operacao dos nossos parceiros.
                        </p>
                    </div>
                    <StaggerContainer className="grid md:grid-cols-4 gap-8 max-w-5xl mx-auto text-center">
                        {[
                            { value: "70%", label: "Reducao de tempo em pesquisa juridica", color: "text-indigo-600 dark:text-indigo-400" },
                            { value: "3x", label: "Aumento de capacidade por profissional", color: "text-emerald-600 dark:text-emerald-400" },
                            { value: "95%", label: "Precisao na identificacao de precedentes", color: "text-amber-600 dark:text-amber-400" },
                            { value: "24/7", label: "Disponibilidade da plataforma", color: "text-purple-600 dark:text-purple-400" },
                        ].map((stat, i) => (
                            <MotionDiv key={i} variants={fadeUp}>
                                <div className="p-8 rounded-2xl border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-white/5">
                                    <div className={`text-6xl font-bold mb-3 ${stat.color}`}>{stat.value}</div>
                                    <div className="text-sm text-slate-600 dark:text-gray-400">{stat.label}</div>
                                </div>
                            </MotionDiv>
                        ))}
                    </StaggerContainer>
                </AnimatedContainer>
            </section>

            {/* Setores Section - Enhanced with icons and descriptions */}
            <section className="py-24 relative snap-start">
                <AnimatedContainer className="container mx-auto px-6">
                    <div className="text-center mb-16">
                        <div className="flex items-center justify-center gap-2 text-indigo-600 dark:text-indigo-400 mb-6 uppercase tracking-[0.3em] text-xs font-semibold">
                            <span className="h-px w-10 bg-indigo-400/40" />
                            <span>Setores</span>
                            <span className="h-px w-10 bg-indigo-400/40" />
                        </div>
                        <h2 className="text-3xl md:text-4xl font-bold mb-4 text-slate-900 dark:text-white">Quem usa o Iudex</h2>
                        <p className="text-xl text-slate-600 dark:text-gray-400 max-w-2xl mx-auto">
                            Da banca individual ao departamento juridico de multinacional.
                        </p>
                    </div>
                    <StaggerContainer className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 max-w-5xl mx-auto">
                        {sectors.map((sector, i) => (
                            <MotionDiv key={i} variants={fadeUp}>
                                <div className="p-6 rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 hover:border-indigo-500/50 transition-all duration-300 h-full">
                                    <div className="h-12 w-12 rounded-xl bg-indigo-100 dark:bg-indigo-500/10 flex items-center justify-center mb-4">
                                        <sector.icon className="h-6 w-6 text-indigo-600 dark:text-indigo-400" />
                                    </div>
                                    <h3 className="text-lg font-bold mb-2 text-slate-900 dark:text-white">{sector.title}</h3>
                                    <p className="text-sm text-slate-600 dark:text-gray-400">{sector.description}</p>
                                </div>
                            </MotionDiv>
                        ))}
                    </StaggerContainer>
                </AnimatedContainer>
            </section>

            {/* Testimonials Section */}
            <section className="py-24 relative snap-start bg-slate-900 dark:bg-[#050507] text-white overflow-hidden">
                <div className="container mx-auto px-6">
                    <AnimatedContainer className="text-center mb-16">
                        <h2 className="text-3xl md:text-4xl font-bold mb-4">O que nossos clientes dizem</h2>
                        <p className="text-xl text-gray-400 max-w-2xl mx-auto">
                            Profissionais que transformaram sua pratica com IA juridica governada.
                        </p>
                    </AnimatedContainer>
                    <StaggerContainer className="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
                        {[
                            {
                                quote: "O Iudex reduziu nosso tempo de pesquisa jurisprudencial de horas para minutos. A qualidade das fontes e citado e impressionante.",
                                author: "Dra. Marina Costa",
                                role: "Socia, Escritorio de Advocacia",
                                initials: "MC",
                            },
                            {
                                quote: "A orquestracao multi-agente e um diferencial real. Cada etapa do workflow tem um agente especializado, com rastreabilidade completa.",
                                author: "Dr. Ricardo Almeida",
                                role: "Diretor Juridico, Multinacional",
                                initials: "RA",
                            },
                            {
                                quote: "Ter acesso a GPT, Claude e Gemini em uma unica plataforma juridica, com governanca, e exatamente o que precisavamos.",
                                author: "Dra. Fernanda Lima",
                                role: "Coordenadora, Departamento Juridico",
                                initials: "FL",
                            },
                        ].map((testimonial, i) => (
                            <MotionDiv key={i} variants={fadeUp}>
                                <div className="p-8 rounded-2xl border border-white/10 bg-white/5 backdrop-blur-sm h-full flex flex-col">
                                    <Quote className="h-8 w-8 text-indigo-400/40 mb-4 flex-shrink-0" />
                                    <p className="text-gray-300 mb-6 flex-grow leading-relaxed">&ldquo;{testimonial.quote}&rdquo;</p>
                                    <div className="flex items-center gap-3">
                                        <div className="h-10 w-10 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
                                            <span className="text-white text-sm font-bold">{testimonial.initials}</span>
                                        </div>
                                        <div>
                                            <div className="text-sm font-semibold text-white">{testimonial.author}</div>
                                            <div className="text-xs text-gray-500">{testimonial.role}</div>
                                        </div>
                                    </div>
                                </div>
                            </MotionDiv>
                        ))}
                    </StaggerContainer>
                </div>
            </section>

            {/* CTA */}
            <section className="py-24 relative snap-start text-center">
                <AnimatedContainer className="container mx-auto px-6">
                    <h2 className="text-3xl md:text-4xl font-bold mb-8 text-slate-900 dark:text-white">Junte-se a inovacao juridica.</h2>
                    <Link href="/demo">
                        <Button size="lg" className="h-14 px-12 rounded-full text-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-[0_0_40px_-10px_rgba(79,70,229,0.5)] transition-all hover:scale-105">
                            Falar com Vendas
                        </Button>
                    </Link>
                </AnimatedContainer>
            </section>

            <Footer />
        </main>
    );
}
