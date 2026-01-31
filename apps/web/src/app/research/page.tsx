'use client';

import React from 'react';
import { PageHero } from '@/components/vorbium/page-hero';
import { Footer } from '@/components/vorbium/footer';
import { VorbiumNav } from '@/components/vorbium/vorbium-nav';
import { FeatureSection } from '@/components/vorbium/feature-section';
import { Globe, BookOpen, AlertCircle, FileText, Scale, Database, History, Eye, ListFilter, CheckCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { AnimatedContainer, StaggerContainer } from '@/components/ui/animated-container';
import { MotionDiv, fadeUp } from '@/components/ui/motion';

export default function ResearchPage() {
    const mainRef = React.useRef<HTMLElement>(null);

    const capabilities = [
        {
            title: "Pesquisa multi-jurisdição",
            description: "Com filtros claros e abrangentes.",
            icon: Globe
        },
        {
            title: "Comparação normativa",
            description: "Por tema e período.",
            icon: Scale
        },
        {
            title: "Identificação de conflitos",
            description: "Encontre exceções e divergências.",
            icon: AlertCircle
        },
        {
            title: "Síntese estruturada",
            description: "Com fundamentação sólida.",
            icon: FileText
        },
        {
            title: "Exportação auditável",
            description: "Em memorando versionado e citável.",
            icon: History
        }
    ];

    const typesOfOutput = [
        {
            title: "Memorando de pesquisa",
            description: "Análise aprofundada de um tema específico.",
            icon: FileText
        },
        {
            title: "Quadro comparativo regulatório",
            description: "Visualização lado a lado de normas.",
            icon: ListFilter
        },
        {
            title: "Resumo executivo",
            description: "Para tomada de decisão rápida.",
            icon: Eye
        },
        {
            title: "Insumo para Workflows",
            description: "Dados estruturados para alimentar automações.",
            icon: Database
        }
    ];

    return (
        <main
            ref={mainRef}
            className="relative h-[100dvh] overflow-y-auto bg-slate-50 dark:bg-[#0a0a0c] text-slate-900 dark:text-white selection:bg-indigo-500/30 snap-y snap-proximity scroll-smooth overscroll-y-contain"
        >
            <VorbiumNav scrollRef={mainRef} />

            <PageHero
                badge="Pesquisa jurídica profunda e governada"
                title="Pesquisa jurídica com profundidade, contexto e rastreabilidade."
                description="A VORBIUM Research combina legislação, jurisprudência, regulamentos e documentos internos para produzir insights jurídicos confiáveis, com fontes claras e escopo definido."
                primaryCtaText="Explorar Research"
                primaryCtaLink="/demo"
            />

            {/* Seção: O problema real */}
            <section className="py-24 relative snap-start">
                <AnimatedContainer className="container mx-auto px-6 max-w-4xl text-center">
                    <h2 className="text-3xl md:text-5xl font-bold mb-8 text-slate-900 dark:text-white">O problema real da pesquisa jurídica</h2>
                    <p className="text-xl text-slate-600 dark:text-gray-400 mb-8 leading-relaxed">
                        Pesquisar direito não é só localizar informação. É interpretar, comparar, contextualizar e justificar.
                    </p>
                    <p className="text-xl text-slate-600 dark:text-gray-400 leading-relaxed">
                        A VORBIUM Research foi projetada para decisões críticas: onde tempo importa, mas confiabilidade importa mais.
                    </p>
                </AnimatedContainer>
            </section>

            {/* App Screenshot: Research Results Mockup */}
            <section className="py-24 relative snap-start">
                <AnimatedContainer className="container mx-auto px-6">
                    <div className="text-center mb-12">
                        <h2 className="text-3xl md:text-4xl font-bold mb-4 text-slate-900 dark:text-white">Interface da Pesquisa</h2>
                        <p className="text-lg text-slate-600 dark:text-gray-400">Resultados estruturados com fontes, contexto e rastreabilidade</p>
                    </div>
                    <div className="relative max-w-5xl mx-auto rounded-2xl overflow-hidden border border-slate-200 dark:border-white/10 shadow-2xl">
                        {/* Browser chrome */}
                        <div className="h-10 bg-slate-100 dark:bg-slate-800 flex items-center px-4 gap-2 border-b border-slate-200 dark:border-white/5">
                            <div className="h-3 w-3 rounded-full bg-red-400/60" />
                            <div className="h-3 w-3 rounded-full bg-yellow-400/60" />
                            <div className="h-3 w-3 rounded-full bg-green-400/60" />
                            <span className="ml-4 text-xs text-slate-500 dark:text-slate-400">app.iudex.ai/research</span>
                        </div>
                        {/* Content area - simulated research interface */}
                        <div className="bg-slate-50 dark:bg-[#0a0a0c] p-6 min-h-[420px]">
                            <div className="grid lg:grid-cols-3 gap-6">
                                {/* Left: Search + Filters */}
                                <div className="lg:col-span-1 space-y-4">
                                    <div className="px-3 py-2 rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 flex items-center gap-2">
                                        <Globe className="h-4 w-4 text-slate-400" />
                                        <div className="h-3 bg-slate-200 dark:bg-white/10 rounded flex-1" />
                                    </div>
                                    <div className="space-y-2">
                                        <div className="text-xs uppercase tracking-wider text-slate-400 dark:text-gray-500 font-semibold">Filtros</div>
                                        {["Jurisdição: Federal", "Área: Civil", "Período: 2020-2026"].map((filter, i) => (
                                            <div key={i} className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 text-xs text-slate-600 dark:text-gray-400">
                                                <CheckCircle className="h-3 w-3 text-emerald-500" />
                                                {filter}
                                            </div>
                                        ))}
                                    </div>
                                    <div className="space-y-2">
                                        <div className="text-xs uppercase tracking-wider text-slate-400 dark:text-gray-500 font-semibold">Fontes</div>
                                        {["Legislação", "Jurisprudência", "Doutrina"].map((source, i) => (
                                            <div key={i} className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 text-xs text-slate-600 dark:text-gray-400">
                                                <BookOpen className="h-3 w-3 text-indigo-500" />
                                                {source}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                                {/* Right: Results */}
                                <div className="lg:col-span-2 space-y-4">
                                    <div className="flex items-center justify-between text-sm text-slate-500 dark:text-gray-500">
                                        <span>12 resultados encontrados</span>
                                        <span className="text-xs text-indigo-600 dark:text-indigo-400">Ordenar por relevância</span>
                                    </div>
                                    {[
                                        { title: "Art. 422 — Código Civil", tag: "Legislação", confidence: "Alta" },
                                        { title: "REsp 1.234.567/SP — STJ", tag: "Jurisprudência", confidence: "Alta" },
                                        { title: "Parecer n. 45/2024 — PGE", tag: "Doutrina", confidence: "Média" },
                                    ].map((result, i) => (
                                        <div key={i} className="p-4 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5">
                                            <div className="flex items-start justify-between mb-2">
                                                <h4 className="font-semibold text-sm text-slate-900 dark:text-white">{result.title}</h4>
                                                <span className={`text-xs px-2 py-0.5 rounded-full ${result.confidence === 'Alta' ? 'bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400' : 'bg-yellow-100 dark:bg-yellow-500/10 text-yellow-700 dark:text-yellow-400'}`}>
                                                    {result.confidence}
                                                </span>
                                            </div>
                                            <div className="flex items-center gap-2 mb-2">
                                                <span className="text-xs px-2 py-0.5 rounded bg-indigo-100 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">{result.tag}</span>
                                            </div>
                                            <div className="space-y-1.5">
                                                <div className="h-2.5 bg-slate-100 dark:bg-white/5 rounded w-full" />
                                                <div className="h-2.5 bg-slate-100 dark:bg-white/5 rounded w-4/5" />
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                </AnimatedContainer>
            </section>

            {/* Seção: O que você consegue fazer */}
            <FeatureSection
                title="O que você consegue fazer"
                features={capabilities}
                className="bg-white dark:bg-white/5 border-y border-slate-200 dark:border-white/5"
            />

            {/* Seção: Como a Research funciona */}
            <section className="py-24 relative snap-start">
                <AnimatedContainer className="container mx-auto px-6">
                    <div className="mb-16">
                        <div className="flex items-center gap-2 text-indigo-600 dark:text-indigo-300/80 mb-6 uppercase tracking-[0.3em] text-xs font-semibold">
                            <span className="h-px w-10 bg-indigo-600/40 dark:bg-indigo-400/40" />
                            <span>Processo</span>
                        </div>
                        <h2 className="text-4xl font-bold mb-6 text-slate-900 dark:text-white">Como a Research funciona</h2>
                    </div>

                    <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8">
                        {[
                            { step: "1", title: "Escopo explícito", desc: "Jurisdição, área, recorte temporal, hipóteses." },
                            { step: "2", title: "Fontes autorizadas", desc: "Bases públicas, privadas e memória institucional." },
                            { step: "3", title: "Orquestração multiagente", desc: "Coleta, análise, verificação e síntese." },
                            { step: "4", title: "Saída estruturada", desc: "Argumentos, riscos, divergências e citações." },
                        ].map((item, i) => (
                            <div key={i} className="relative p-8 rounded-2xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 shadow-sm dark:shadow-none">
                                <span className="absolute top-6 right-6 text-4xl font-bold text-slate-100 dark:text-white/5 font-display">{item.step}</span>
                                <h3 className="text-xl font-bold mb-3 text-slate-900 dark:text-white">{item.title}</h3>
                                <p className="text-slate-600 dark:text-gray-400">{item.desc}</p>
                            </div>
                        ))}
                    </div>
                </AnimatedContainer>
            </section>

            {/* Seção: Tipos de saída */}
            <FeatureSection
                title="Tipos de saída"
                features={typesOfOutput}
                className="bg-white dark:bg-white/5 border-y border-slate-200 dark:border-white/5"
            />

            {/* Seção: Governança da pesquisa */}
            <section className="py-24 relative snap-start">
                <AnimatedContainer className="container mx-auto px-6 text-center">
                    <h2 className="text-3xl font-bold mb-12 text-slate-900 dark:text-white">Governança da pesquisa</h2>
                    <div className="flex flex-wrap justify-center gap-4 md:gap-8 text-slate-600 dark:text-gray-300">
                        {["Fontes identificadas e citáveis", "Histórico de versões", "Critérios de escopo registrados", "Reaproveitamento institucional"].map((item, i) => (
                            <div key={i} className="flex items-center gap-2 px-4 py-2 rounded-full border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5">
                                <CheckCircle className="h-4 w-4 text-emerald-500 dark:text-emerald-400" />
                                <span className="text-sm font-medium">{item}</span>
                            </div>
                        ))}
                    </div>
                </AnimatedContainer>
            </section>


            {/* CTA Final */}
            <section className="py-24 relative snap-start text-center">
                <AnimatedContainer className="container mx-auto px-6">
                    <h2 className="text-3xl md:text-4xl font-bold mb-8 text-slate-900 dark:text-white">Pesquisar é reunir material. Decidir exige interpretação confiável.</h2>
                    <Link href="/demo">
                        <Button size="lg" className="h-14 px-12 rounded-full text-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-[0_0_40px_-10px_rgba(79,70,229,0.5)] transition-all hover:scale-105">
                            Começar Research
                        </Button>
                    </Link>
                </AnimatedContainer>
            </section>

            <Footer />
        </main>
    );
}
