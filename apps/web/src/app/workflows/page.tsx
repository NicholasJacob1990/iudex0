'use client';

import React from 'react';
import { PageHero } from '@/components/vorbium/page-hero';
import { Footer } from '@/components/vorbium/footer';
import { VorbiumNav } from '@/components/vorbium/vorbium-nav';
import { FeatureSection } from '@/components/vorbium/feature-section';
import { Workflow, FileSearch, ShieldCheck, Activity, RotateCw, GitBranch, FileInput, PlayCircle, Eye } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Link from 'next/link';

export default function WorkflowsPage() {
    const mainRef = React.useRef<HTMLElement>(null);

    const automations = [
        {
            title: "Due diligence",
            description: "Extração, classificação e sumarização de riscos.",
            icon: FileSearch
        },
        {
            title: "Contratos",
            description: "Revisão de cláusulas, alertas e geração de minutas.",
            icon: FileInput
        },
        {
            title: "Compliance",
            description: "Monitoramento e controles recorrentes.",
            icon: ShieldCheck
        },
        {
            title: "Contencioso",
            description: "Preparação de peças, cronologias e checklists.",
            icon: Activity
        },
        {
            title: "Rotinas internas",
            description: "Triagem, roteamento e padronização.",
            icon: RotateCw
        }
    ];

    return (
        <main
            ref={mainRef}
            className="relative h-[100dvh] overflow-y-auto bg-slate-50 dark:bg-[#0a0a0c] text-slate-900 dark:text-white selection:bg-indigo-500/30 snap-y snap-proximity scroll-smooth overscroll-y-contain"
        >
            <VorbiumNav scrollRef={mainRef} />

            <PageHero
                badge="Automação baseada em lógica jurídica executável"
                title="Transforme raciocínio jurídico em execução automatizada."
                description="Workflows da VORBIUM transformam regras e padrões jurídicos em fluxos executáveis, com agentes especializados, logs completos e supervisão humana por criticidade."
                primaryCtaText="Ver exemplos de Workflows"
                primaryCtaLink="/demo"
            />

            {/* Seção: Por que Workflows */}
            <section className="py-24 relative snap-start">
                <div className="container mx-auto px-6 max-w-4xl text-center">
                    <h2 className="text-3xl md:text-5xl font-bold mb-8 text-slate-900 dark:text-white">Por que Workflows?</h2>
                    <p className="text-xl text-slate-600 dark:text-gray-400 mb-8 leading-relaxed">
                        Boa parte do trabalho jurídico é repetitivo, condicionado a regras e passível de padronização.
                        A VORBIUM permite automatizar sem perder controle: com governança, exceções e aprovação humana quando necessário.
                    </p>
                </div>
            </section>

            {/* Seção: O que você pode automatizar */}
            <FeatureSection
                title="O que você pode automatizar"
                features={automations}
                className="bg-white dark:bg-white/5 border-y border-slate-200 dark:border-white/5"
            />

            {/* Seção: Como um Workflow funciona */}
            <section className="py-24 relative snap-start">
                <div className="container mx-auto px-6">
                    <div className="mb-16">
                        <div className="flex items-center gap-2 text-indigo-600 dark:text-indigo-300/80 mb-6 uppercase tracking-[0.3em] text-xs font-semibold">
                            <span className="h-px w-10 bg-indigo-600/40 dark:bg-indigo-400/40" />
                            <span>Lógica de execução</span>
                        </div>
                        <h2 className="text-4xl font-bold mb-6 text-slate-900 dark:text-white">Como um Workflow funciona</h2>
                    </div>

                    <div className="relative">
                        {/* Connecting Line (Desktop) */}
                        <div className="hidden lg:block absolute top-12 left-12 right-12 h-0.5 bg-gradient-to-r from-indigo-500/0 via-indigo-200 dark:via-indigo-500/30 to-indigo-500/0 border-t border-dashed border-slate-300 dark:border-white/20"></div>

                        <div className="grid lg:grid-cols-5 gap-6">
                            {[
                                { title: "Gatilho", desc: "Evento, documento, prazo ou requisição.", icon: PlayCircle },
                                { title: "Interpretação", desc: "Agentes analisam regras e contexto.", icon: BrainCircuit },
                                { title: "Decisão", desc: "Caminhos e exceções condicionais.", icon: GitBranch },
                                { title: "Execução", desc: "Produção de artefatos, tarefas e integrações.", icon: Activity },
                                { title: "Supervisão", desc: "Aprovação humana obrigatória quando configurada.", icon: Eye },
                            ].map((item, i) => (
                                <div key={i} className="relative z-10 flex flex-col items-center text-center group">
                                    <div className="h-24 w-24 rounded-full bg-white dark:bg-[#131418] border border-slate-200 dark:border-white/10 flex items-center justify-center mb-6 shadow-lg group-hover:border-indigo-500/50 transition-colors">
                                        <item.icon className="h-8 w-8 text-slate-400 dark:text-gray-400 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors" />
                                    </div>
                                    <h4 className="text-lg font-bold mb-2 text-slate-900 dark:text-white">{item.title}</h4>
                                    <p className="text-sm text-slate-600 dark:text-gray-500">{item.desc}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </section>

            {/* Seção: Logs e auditoria */}
            <section className="py-24 relative snap-start">
                <div className="container mx-auto px-6">
                    <div className="grid lg:grid-cols-2 gap-16 items-center">
                        <div>
                            <h2 className="text-3xl font-bold mb-6 text-slate-900 dark:text-white">Logs e auditoria</h2>
                            <p className="text-lg text-slate-600 dark:text-gray-400 mb-8">Cada execução registra:</p>
                            <ul className="space-y-4">
                                {[
                                    "Agente(s) e etapas executadas",
                                    "Decisões e critérios",
                                    "Fontes e evidências",
                                    "Ações disparadas",
                                    "Aprovações e revisões humanas",
                                    "Versão do workflow e do artefato gerado"
                                ].map((item, i) => (
                                    <li key={i} className="flex items-center gap-3 text-slate-700 dark:text-gray-300">
                                        <span className="h-1.5 w-1.5 rounded-full bg-indigo-500" />
                                        <span>{item}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                        <div className="rounded-xl bg-slate-950 dark:bg-white/5 border border-slate-800 dark:border-white/10 p-8 shadow-2xl">
                            <div className="font-mono text-xs text-slate-400 dark:text-gray-500 space-y-2">
                                <p>{`{`}</p>
                                <p className="pl-4">{`"execution_id": "wf_8923_khx",`}</p>
                                <p className="pl-4">{`"timestamp": "2026-01-31T10:45:00Z",`}</p>
                                <p className="pl-4">{`"trigger": "contract_upload",`}</p>
                                <p className="pl-4">{`"steps": [`}</p>
                                <p className="pl-8">{`{ "agent": "classifier", "status": "success", "confidence": 0.98 },`}</p>
                                <p className="pl-8">{`{ "agent": "risk_analyzer", "status": "flagged", "reason": "clause_4.2" }`}</p>
                                <p className="pl-4">{`],`}</p>
                                <p className="pl-4 text-emerald-400">{`"human_review": "required"`}</p>
                                <p>{`}`}</p>
                            </div>
                        </div>
                    </div>
                </div>
            </section>


            {/* CTA Final */}
            <section className="py-24 relative snap-start text-center">
                <div className="container mx-auto px-6">
                    <h2 className="text-3xl md:text-4xl font-bold mb-8 text-slate-900 dark:text-white">Automatizar tarefas é eficiência. Automatizar com controle é maturidade jurídica.</h2>
                    <Link href="/demo">
                        <Button size="lg" className="h-14 px-12 rounded-full text-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-[0_0_40px_-10px_rgba(79,70,229,0.5)] transition-all hover:scale-105">
                            Ver exemplos de Workflows
                        </Button>
                    </Link>
                </div>
            </section>

            <Footer />
        </main>
    );
}

// Helper icon for this file since BrainCircuit was used but not imported in the list above
function BrainCircuit(props: any) {
    return (
        <svg
            {...props}
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            <path d="M12 4.5a2.5 2.5 0 0 0-4.96-.46 2.5 2.5 0 0 0-1.98 3 2.5 2.5 0 0 0-1.32 3 2.5 2.5 0 0 0-.02 3 2.5 2.5 0 0 0 2.77 3 2.5 2.5 0 0 0 1.97 3 2.5 2.5 0 0 0 4.96-.46 2.5 2.5 0 0 0 1.98-3 2.5 2.5 0 0 0 1.32-3 2.5 2.5 0 0 0-.02-3 2.5 2.5 0 0 0-2.77-3 2.5 2.5 0 0 0-1.97-3 2.5 2.5 0 0 0-1.32-3 2.5 2.5 0 0 0-.02-3 2.5 2.5 0 0 0 2.77-3 2.5 2.5 0 0 0 1.97-3 2.5 2.5 0 0 0-3.54 0" />
        </svg>
    )
}
