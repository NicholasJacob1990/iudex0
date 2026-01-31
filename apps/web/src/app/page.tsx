'use client';

import React from 'react';
import { HeroSection } from '@/components/vorbium/hero-section';
import { Footer } from '@/components/vorbium/footer';
import { VorbiumNav } from '@/components/vorbium/vorbium-nav';
import { FeatureSection } from '@/components/vorbium/feature-section';
import { Users, FileText, CheckCircle, Shield, BrainCircuit, Gavel, Search, AlertCircle, Play } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { useScrollProgress } from '@/hooks/use-scroll-progress';
import { MotionDiv, scaleIn, fadeUp } from '@/components/ui/motion';
import { AnimatedContainer, StaggerContainer } from '@/components/ui/animated-container';

export default function HomePage() {
  const mainRef = React.useRef<HTMLElement>(null);
  const progress = useScrollProgress(mainRef);

  const benefits = [
    {
      title: "Assistente jurídico",
      description: "Para perguntas, interpretação e redação.",
      icon: Users
    },
    {
      title: "Pesquisa jurídica profunda",
      description: "Com escopo e fontes claras.",
      icon: Search
    },
    {
      title: "Workflows executáveis",
      description: "Para automação de tarefas com controle.",
      icon: BrainCircuit
    },
    {
      title: "Colaboração segura",
      description: "Entre equipes e clientes.",
      icon: Users
    },
    {
      title: "Governança e auditoria",
      description: "Em cada decisão e execução.",
      icon: Shield
    }
  ];

  const howItWorks = [
    {
      title: "Entrada jurídica",
      description: "Documentos, perguntas, normas, eventos e contexto do caso.",
      icon: FileText
    },
    {
      title: "Interpretação agentiva",
      description: "Agentes analisam regras, precedentes, exceções e escopo.",
      icon: BrainCircuit
    },
    {
      title: "Decisão estruturada",
      description: "Conclusão jurídica com fundamentos e fontes.",
      icon: Gavel
    },
    {
      title: "Execução controlada",
      description: "Geração de artefatos, tarefas e fluxos com supervisão.",
      icon: CheckCircle
    }
  ];

  const operationalPrinciples = [
    {
      title: "Sem resposta sem fonte",
      description: "Toda afirmação é rastreável à sua origem.",
      icon: Search
    },
    {
      title: "Sem decisão fora do escopo",
      description: "Limites claros de atuação para evitar alucinações.",
      icon: AlertCircle
    },
    {
      title: "Sem automação sem logs",
      description: "Rastreabilidade completa de todas as ações.",
      icon: FileText
    },
    {
      title: "Sem 'caixa-preta'",
      description: "Toda conclusão é explicável.",
      icon: BrainCircuit
    }
  ];

  return (
    <main
      ref={mainRef}
      className="relative h-[100dvh] overflow-y-auto bg-slate-50 dark:bg-[#0a0a0c] text-slate-900 dark:text-white selection:bg-indigo-500/30 snap-y snap-proximity scroll-smooth overscroll-y-contain"
    >
      {/* Scroll progress bar */}
      <MotionDiv
        className="fixed top-0 left-0 right-0 h-[3px] bg-indigo-600 dark:bg-indigo-500 origin-left z-[100]"
        style={{ scaleX: progress }}
      />

      <VorbiumNav scrollRef={mainRef} />

      <HeroSection />

      {/* Video Demo Section */}
      <section className="py-24 relative snap-start">
        <AnimatedContainer className="container mx-auto px-6">
          <div className="text-center mb-12">
            <h2 className="text-3xl md:text-5xl font-bold mb-4 text-slate-900 dark:text-white">Veja o Iudex em ação</h2>
            <p className="text-xl text-slate-600 dark:text-gray-400">Uma demonstração completa da plataforma jurídica com IA multi-agente</p>
          </div>
          <div className="relative max-w-4xl mx-auto rounded-2xl overflow-hidden border border-slate-200 dark:border-white/10 shadow-2xl bg-slate-900 aspect-video group cursor-pointer">
            {/* Poster/thumbnail placeholder */}
            <div className="absolute inset-0 bg-gradient-to-br from-indigo-600/20 via-purple-600/10 to-slate-900 flex items-center justify-center">
              <div className="flex flex-col items-center gap-4">
                <div className="h-20 w-20 rounded-full bg-white/10 backdrop-blur-xl flex items-center justify-center border border-white/20 group-hover:scale-110 transition-transform duration-300">
                  <Play className="h-8 w-8 text-white ml-1" />
                </div>
                <span className="text-white/70 text-sm">3:42 min</span>
              </div>
            </div>
            {/* Decorative screenshot mockup lines */}
            <div className="absolute top-0 left-0 right-0 h-10 bg-slate-800/80 flex items-center px-4 gap-2">
              <div className="h-3 w-3 rounded-full bg-red-400/60" />
              <div className="h-3 w-3 rounded-full bg-yellow-400/60" />
              <div className="h-3 w-3 rounded-full bg-green-400/60" />
              <span className="ml-4 text-xs text-slate-400">Iudex — Plataforma Jurídica com IA</span>
            </div>
          </div>
        </AnimatedContainer>
      </section>

      {/* Seção: Por que a VORBIUM existe */}
      <AnimatedContainer as="section" className="py-32 relative snap-start" variants={scaleIn}>
        <div className="container mx-auto px-6 max-w-4xl text-center">
          <h2 className="text-3xl md:text-5xl font-bold mb-8 text-slate-900 dark:text-white">Por que a VORBIUM existe</h2>
          <p className="text-xl text-slate-600 dark:text-gray-400 mb-8 leading-relaxed">
            O trabalho jurídico moderno exige mais do que respostas rápidas. Exige interpretação correta, decisão consistente e execução confiável.
          </p>
          <p className="text-xl text-slate-600 dark:text-gray-400 leading-relaxed">
            A VORBIUM organiza conhecimento jurídico e o transforma em processos auditáveis, operados por agentes especializados dentro de regras claras.
          </p>
        </div>
      </AnimatedContainer>

      {/* Seção: O que você obtém */}
      <FeatureSection
        title="O que você obtém em uma plataforma única"
        features={benefits}
        className="bg-white dark:bg-white/5 border-y border-slate-200 dark:border-white/5"
      />

      {/* Multi-Provider AI Section */}
      <section className="py-24 relative snap-start bg-slate-900 dark:bg-[#050507] text-white overflow-hidden">
        <div className="container mx-auto px-6">
          <AnimatedContainer className="text-center mb-16">
            <div className="flex items-center justify-center gap-2 text-indigo-400 mb-6 uppercase tracking-[0.3em] text-xs font-semibold">
              <span className="h-px w-10 bg-indigo-400/40" />
              <span>Multi-Provider</span>
              <span className="h-px w-10 bg-indigo-400/40" />
            </div>
            <h2 className="text-4xl lg:text-5xl font-bold mb-6">Todos os modelos de IA.<br />Uma so plataforma juridica.</h2>
            <p className="text-xl text-gray-400 max-w-3xl mx-auto">
              GPT, Claude, Gemini, Perplexity e DeepSeek — orquestrados automaticamente para cada tarefa juridica.
              Modelos diferentes tem forcas diferentes. O Iudex escolhe o melhor para cada etapa do seu trabalho.
            </p>
          </AnimatedContainer>
          <StaggerContainer className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-5 max-w-6xl mx-auto">
            {[
              {
                name: "GPT-4o",
                provider: "OpenAI",
                strength: "Raciocinio juridico complexo",
                icon: (
                  <svg viewBox="0 0 24 24" className="h-7 w-7" fill="none">
                    <path d="M22.282 9.821a5.985 5.985 0 0 0-.516-4.91 6.046 6.046 0 0 0-6.51-2.9A6.065 6.065 0 0 0 4.981 4.18a5.998 5.998 0 0 0-3.998 2.9 6.046 6.046 0 0 0 .743 7.097 5.98 5.98 0 0 0 .51 4.911 6.051 6.051 0 0 0 6.515 2.9A5.985 5.985 0 0 0 13.26 24a6.056 6.056 0 0 0 5.772-4.206 5.99 5.99 0 0 0 3.997-2.9 6.056 6.056 0 0 0-.747-7.073zM13.26 22.43a4.476 4.476 0 0 1-2.876-1.04l.141-.081 4.779-2.758a.795.795 0 0 0 .392-.681v-6.737l2.02 1.168a.071.071 0 0 1 .038.052v5.583a4.504 4.504 0 0 1-4.494 4.494zM3.6 18.304a4.47 4.47 0 0 1-.535-3.014l.142.085 4.783 2.759a.77.77 0 0 0 .78 0l5.843-3.369v2.332a.08.08 0 0 1-.033.062L9.74 19.95a4.5 4.5 0 0 1-6.14-1.646zM2.34 7.896a4.485 4.485 0 0 1 2.366-1.973V11.6a.766.766 0 0 0 .388.676l5.815 3.355-2.02 1.168a.076.076 0 0 1-.071 0l-4.83-2.786A4.504 4.504 0 0 1 2.34 7.872zm16.597 3.855l-5.833-3.387L15.119 7.2a.076.076 0 0 1 .071 0l4.83 2.791a4.494 4.494 0 0 1-.676 8.105v-5.678a.79.79 0 0 0-.407-.667zm2.01-3.023l-.141-.085-4.774-2.782a.776.776 0 0 0-.785 0L9.409 9.23V6.897a.066.066 0 0 1 .028-.061l4.83-2.787a4.5 4.5 0 0 1 6.68 4.66zm-12.64 4.135l-2.02-1.164a.08.08 0 0 1-.038-.057V6.075a4.5 4.5 0 0 1 7.375-3.453l-.142.08L8.704 5.46a.795.795 0 0 0-.393.681zm1.097-2.365l2.602-1.5 2.607 1.5v2.999l-2.597 1.5-2.607-1.5z" fill="currentColor"/>
                  </svg>
                ),
                bgColor: "bg-[#10a37f]",
              },
              {
                name: "Claude",
                provider: "Anthropic",
                strength: "Analise contextual profunda",
                icon: (
                  <svg viewBox="0 0 24 24" className="h-7 w-7" fill="none">
                    <path d="M16.865 12.885l-4.166-8.57a.75.75 0 0 0-1.35 0l-4.166 8.57a.75.75 0 0 0 .675 1.082h8.332a.75.75 0 0 0 .675-1.082z" fill="currentColor"/>
                    <path d="M17.49 15.217H6.51a.75.75 0 0 0-.675 1.082l2.083 4.286a.75.75 0 0 0 .675.415h6.814a.75.75 0 0 0 .675-.415l2.083-4.286a.75.75 0 0 0-.675-1.082z" fill="currentColor" opacity="0.6"/>
                  </svg>
                ),
                bgColor: "bg-[#d97757]",
              },
              {
                name: "Gemini",
                provider: "Google",
                strength: "Redacao e sintese juridica",
                icon: (
                  <svg viewBox="0 0 24 24" className="h-7 w-7" fill="none">
                    <path d="M12 24A14.304 14.304 0 0 0 0 12 14.304 14.304 0 0 0 12 0a14.305 14.305 0 0 0 12 12 14.305 14.305 0 0 0-12 12z" fill="url(#gemini-grad)"/>
                    <defs>
                      <linearGradient id="gemini-grad" x1="0" y1="0" x2="24" y2="24">
                        <stop stopColor="#4285F4"/>
                        <stop offset="1" stopColor="#886FFF"/>
                      </linearGradient>
                    </defs>
                  </svg>
                ),
                bgColor: "bg-[#1a73e8]",
              },
              {
                name: "Perplexity",
                provider: "Perplexity AI",
                strength: "Pesquisa com fontes verificadas",
                icon: (
                  <svg viewBox="0 0 24 24" className="h-7 w-7" fill="none">
                    <path d="M12 2L4 7v10l8 5 8-5V7l-8-5z" stroke="currentColor" strokeWidth="1.5" fill="none"/>
                    <path d="M12 2v20M4 7l8 5 8-5M4 17l8-5 8 5" stroke="currentColor" strokeWidth="1.5"/>
                  </svg>
                ),
                bgColor: "bg-[#20808d]",
              },
              {
                name: "DeepSeek",
                provider: "DeepSeek",
                strength: "Reasoning avancado e logica",
                icon: (
                  <svg viewBox="0 0 24 24" className="h-7 w-7" fill="none">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.5"/>
                    <path d="M8 12a4 4 0 0 1 8 0" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                    <path d="M12 12v5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                    <circle cx="12" cy="8" r="1.5" fill="currentColor"/>
                  </svg>
                ),
                bgColor: "bg-[#4D6BFE]",
              },
            ].map((model) => (
              <MotionDiv key={model.name} variants={fadeUp} className="relative group">
                <div className="p-5 rounded-2xl border border-white/10 bg-white/5 backdrop-blur-sm hover:bg-white/10 transition-all duration-300 hover:-translate-y-1 h-full">
                  <div className={`h-12 w-12 rounded-xl ${model.bgColor} flex items-center justify-center mb-4 text-white shadow-lg`}>
                    {model.icon}
                  </div>
                  <h3 className="text-lg font-bold mb-0.5">{model.name}</h3>
                  <p className="text-xs text-gray-500 mb-2">{model.provider}</p>
                  <p className="text-sm text-gray-300 leading-relaxed">{model.strength}</p>
                </div>
              </MotionDiv>
            ))}
          </StaggerContainer>
          <AnimatedContainer className="text-center mt-14">
            <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-gray-500 text-sm">
              <span className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                Auto-routing inteligente
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-blue-400" />
                Selecao manual disponivel
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-purple-400" />
                Modelos atualizados automaticamente
              </span>
            </div>
          </AnimatedContainer>
        </div>
      </section>

      {/* Seção: Como o sistema funciona */}
      <FeatureSection
        title="Como o sistema funciona"
        features={howItWorks}
      />

      {/* Seção: Princípios operacionais */}
      <FeatureSection
        title="Princípios operacionais"
        features={operationalPrinciples}
        className="bg-white dark:bg-white/5 border-y border-slate-200 dark:border-white/5"
      />

      {/* CTA Final — Scale-up reveal on scroll */}
      <AnimatedContainer as="section" className="py-32 relative snap-start text-center" variants={scaleIn}>
        <div className="container mx-auto px-6 max-w-3xl">
          <div className="rounded-3xl border border-slate-200 dark:border-white/10 bg-white/50 dark:bg-white/5 backdrop-blur-xl px-8 py-16 md:px-16 shadow-xl dark:shadow-none">
            <h2 className="text-4xl font-bold mb-6 text-slate-900 dark:text-white">A VORBIUM não &ldquo;ajuda&rdquo; o jurídico.</h2>
            <h3 className="text-3xl font-bold mb-12 text-indigo-600 dark:text-indigo-500">Ela opera o jurídico com governança.</h3>
            <Link href="/demo">
              <Button size="lg" className="h-14 px-12 rounded-full text-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-[0_0_40px_-10px_rgba(79,70,229,0.5)] transition-all hover:scale-105">
                Solicitar demonstração
              </Button>
            </Link>
          </div>
        </div>
      </AnimatedContainer>

      <Footer />
    </main>
  );
}
