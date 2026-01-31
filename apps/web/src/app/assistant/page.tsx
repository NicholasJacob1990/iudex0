'use client';

import React from 'react';
import { PageHero } from '@/components/vorbium/page-hero';
import { Footer } from '@/components/vorbium/footer';
import { VorbiumNav } from '@/components/vorbium/vorbium-nav';
import { FeatureSection } from '@/components/vorbium/feature-section';
import { MessageSquare, FileText, AlertTriangle, PenTool, CheckCircle, Search, Eye } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Link from 'next/link';

export default function AssistantPage() {
    const mainRef = React.useRef<HTMLElement>(null);

    const capabilities = [
        {
            title: "Interpretação complexa",
            description: "Interpreta documentos e situações jurídicas complexas.",
            icon: FileText
        },
        {
            title: "Análise profunda",
            description: "Analisa contratos, políticas, regulamentos e peças.",
            icon: Search
        },
        {
            title: "Gestão de riscos",
            description: "Identifica riscos, lacunas e inconsistências.",
            icon: AlertTriangle
        },
        {
            title: "Redação jurídica",
            description: "Redige memorandos, pareceres, minutas e cláusulas.",
            icon: PenTool
        },
        {
            title: "Explicabilidade",
            description: "Explica o raciocínio e evidencia fontes e premissas.",
            icon: Eye
        }
    ];

    const modes = [
        {
            title: "Análise jurídica",
            description: "Interpretação completa com fundamentos.",
            icon: Search
        },
        {
            title: "Redação",
            description: "Minuta estruturada com consistência e padrão institucional.",
            icon: PenTool
        },
        {
            title: "Revisão crítica",
            description: "Riscos, pontos frágeis, inconsistências e sugestões.",
            icon: AlertTriangle
        },
        {
            title: "Decisão orientada",
            description: "Alternativas, impactos e recomendações condicionais.",
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
                badge="Interface de raciocínio jurídico"
                title="Faça perguntas jurídicas. Receba decisões estruturadas."
                description="O Assistente da VORBIUM interpreta documentos, normas e precedentes para produzir análises jurídicas fundamentadas, sempre com rastreabilidade e contexto."
                primaryCtaText="Ver demonstração do Assistente"
                primaryCtaLink="/demo"
            />

            {/* Seção: O que o Assistente é */}
            <section className="py-24 relative snap-start">
                <div className="container mx-auto px-6 max-w-4xl text-center">
                    <h2 className="text-3xl md:text-5xl font-bold mb-8 text-slate-900 dark:text-white">O que o Assistente é</h2>
                    <p className="text-xl text-slate-600 dark:text-gray-400 mb-8 leading-relaxed">
                        O Assistente da VORBIUM não é um chat genérico. Ele é uma interface de raciocínio jurídico conectada a agentes especializados, fontes autorizadas e regras institucionais.
                    </p>
                    <p className="text-xl text-slate-600 dark:text-gray-400 leading-relaxed">
                        Cada saída é um artefato jurídico, pronto para revisão, versionamento e auditoria.
                    </p>
                </div>
            </section>
            {/* Seção: O que ele faz */}
            <FeatureSection
                title="O que ele faz"
                features={capabilities}
                className="bg-white/5"
            />

            {/* Seção: O que ele não faz */}
            <section className="py-24 relative snap-start">
                <div className="container mx-auto px-6">
                    <div className="mb-16 max-w-3xl">
                        <div className="flex items-center gap-2 text-indigo-300/80 mb-6 uppercase tracking-[0.3em] text-xs font-semibold">
                            <span className="h-px w-10 bg-indigo-400/40" />
                            <span>Limites</span>
                        </div>
                        <h2 className="text-4xl lg:text-5xl font-bold mb-6 leading-tight text-white">O que ele não faz</h2>
                    </div>
                    <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
                        {[
                            "Não responde fora do escopo",
                            "Não “inventa” fundamentos",
                            "Não omite fontes quando exigidas",
                            "Não executa ações críticas sem supervisão"
                        ].map((item, i) => (
                            <div key={i} className="p-6 rounded-xl border border-red-500/20 bg-red-500/5 flex items-center gap-4">
                                <div className="h-2 w-2 rounded-full bg-red-500 flex-shrink-0" />
                                <span className="text-gray-300 font-medium">{item}</span>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Seção: Modos de uso */}
            <FeatureSection
                title="Modos de uso"
                description="Adaptável para diferentes fluxos de trabalho do time jurídico."
                features={modes}
                className="bg-white/5"
            />

            {/* Seção: Transparência e controle */}
            <section className="py-24 relative snap-start">
                <div className="container mx-auto px-6">
                    <div className="grid lg:grid-cols-2 gap-16 items-center">
                        <div>
                            <h2 className="text-3xl md:text-5xl font-bold mb-6">Transparência e controle</h2>
                            <p className="text-lg text-gray-400 mb-8">Cada resultado apresenta, quando aplicável:</p>
                            <ul className="space-y-4">
                                {[
                                    "Fontes utilizadas e trechos relevantes",
                                    "Agentes envolvidos e papéis desempenhados",
                                    "Nível de confiança e limitações",
                                    "Registro de revisão e aprovação humana"
                                ].map((item, i) => (
                                    <li key={i} className="flex items-center gap-3 text-gray-300">
                                        <CheckCircle className="h-5 w-5 text-indigo-500" />
                                        <span>{item}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                        {/* Visual placeholder for transparency ui */}
                        <div className="relative rounded-2xl border border-white/10 bg-[#0F1115] p-6 shadow-2xl">
                            <div className="flex items-center justify-between mb-4 border-b border-white/5 pb-4">
                                <span className="text-xs uppercase tracking-wider text-gray-500">Audit Log</span>
                                <span className="text-xs text-indigo-400">Verified</span>
                            </div>
                            <div className="space-y-3 font-mono text-sm">
                                <div className="flex gap-4">
                                    <span className="text-gray-600 w-16">10:42:01</span>
                                    <span className="text-indigo-300">Agent <span className="text-indigo-200">Researcher</span> accessed Civil Code Art. 422</span>
                                </div>
                                <div className="flex gap-4">
                                    <span className="text-gray-600 w-16">10:42:05</span>
                                    <span className="text-indigo-300">Agent <span className="text-indigo-200">Analyst</span> identified risk: "High"</span>
                                </div>
                                <div className="flex gap-4">
                                    <span className="text-gray-600 w-16">10:42:15</span>
                                    <span className="text-emerald-300">Human Approval required for final clause</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* CTA Final */}
            <section className="py-24 relative snap-start text-center">
                <div className="container mx-auto px-6">
                    <h2 className="text-3xl md:text-4xl font-bold mb-8">Perguntar é fácil. Decidir com segurança é o diferencial.</h2>
                    <Link href="/demo">
                        <Button size="lg" className="h-14 px-12 rounded-full text-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-[0_0_40px_-10px_rgba(79,70,229,0.5)] transition-all hover:scale-105">
                            Ver demonstração do Assistente
                        </Button>
                    </Link>
                </div>
            </section>

            <Footer />
        </main>
    );
}
