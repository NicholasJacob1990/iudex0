'use client';

import React from 'react';
import { HeroSection } from '@/components/vorbium/hero-section';
import { Footer } from '@/components/vorbium/footer';
import { VorbiumNav } from '@/components/vorbium/vorbium-nav';
import { FeatureSection } from '@/components/vorbium/feature-section';
import { Users, FileText, CheckCircle, Shield, BrainCircuit, Gavel, Search, AlertCircle } from 'lucide-react';
import { MediaShowcase } from '@/components/vorbium/media-showcase';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { useScrollProgress } from '@/hooks/use-scroll-progress';
import { useScrollAnimationFallback } from '@/hooks/use-scroll-animation';
import { MotionDiv, scaleIn, fadeUp } from '@/components/ui/motion';
import { AnimatedContainer, StaggerContainer } from '@/components/ui/animated-container';

export default function HomePage() {
  const mainRef = React.useRef<HTMLElement>(null);
  const progress = useScrollProgress(mainRef);
  useScrollAnimationFallback();

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
      <MediaShowcase
        title="Veja o Iudex em ação"
        subtitle="Uma demonstração completa da plataforma jurídica com IA multi-agente"
        media={[{ type: 'video', label: 'Demo completa — 3:42 min' }]}
      />

      {/* Seção: Por que a VORBIUM existe */}
      <AnimatedContainer as="section" className="py-32 relative snap-start" variants={scaleIn}>
        <div className="container mx-auto px-6 max-w-4xl text-center">
          <h2 className="text-3xl md:text-5xl font-bold heading-section mb-8 text-slate-900 dark:text-white">Por que a VORBIUM existe</h2>
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
            <h2 className="text-4xl lg:text-5xl font-bold heading-section mb-6">Todos os modelos de IA.<br />Uma so plataforma juridica.</h2>
            <p className="text-xl text-gray-400 max-w-3xl mx-auto">
              GPT, Claude, Gemini, Perplexity, DeepSeek, Llama e Mistral — orquestrados automaticamente para cada tarefa juridica.
              Modelos diferentes tem forcas diferentes. O Iudex escolhe o melhor para cada etapa do seu trabalho.
            </p>
          </AnimatedContainer>
          <StaggerContainer className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-5 max-w-5xl mx-auto">
            {[
              {
                name: "GPT-4o",
                provider: "OpenAI",
                strength: "Raciocinio juridico complexo",
                icon: (
                  <svg viewBox="0 0 16 16" className="h-7 w-7" fill="currentColor">
                    <path d="M14.949 6.547a3.94 3.94 0 0 0-.348-3.273 4.11 4.11 0 0 0-4.4-1.934A4.1 4.1 0 0 0 8.423.2 4.15 4.15 0 0 0 6.305.086a4.1 4.1 0 0 0-1.891.948 4.04 4.04 0 0 0-1.158 1.753 4.1 4.1 0 0 0-1.563.679A4 4 0 0 0 .554 4.72a3.99 3.99 0 0 0 .502 4.731 3.94 3.94 0 0 0 .346 3.274 4.11 4.11 0 0 0 4.402 1.933c.382.425.852.764 1.377.995.526.231 1.095.35 1.67.346 1.78.002 3.358-1.132 3.901-2.804a4.1 4.1 0 0 0 1.563-.68 4 4 0 0 0 1.14-1.253 3.99 3.99 0 0 0-.506-4.716m-6.097 8.406a3.05 3.05 0 0 1-1.945-.694l.096-.054 3.23-1.838a.53.53 0 0 0 .265-.455v-4.49l1.366.778q.02.011.025.035v3.722c-.003 1.653-1.361 2.992-3.037 2.996m-6.53-2.75a2.95 2.95 0 0 1-.36-2.01l.095.057L5.29 12.09a.53.53 0 0 0 .527 0l3.949-2.246v1.555a.05.05 0 0 1-.022.041L6.473 13.3c-1.454.826-3.311.335-4.15-1.098m-.85-6.94A3.02 3.02 0 0 1 3.07 3.949v3.785a.51.51 0 0 0 .262.451l3.93 2.237-1.366.779a.05.05 0 0 1-.048 0L2.585 9.342a2.98 2.98 0 0 1-1.113-4.094zm11.216 2.571L8.747 5.576l1.362-.776a.05.05 0 0 1 .048 0l3.265 1.86a3 3 0 0 1 1.173 1.207 2.96 2.96 0 0 1-.27 3.2 3.05 3.05 0 0 1-1.36.997V8.279a.52.52 0 0 0-.276-.445m1.36-2.015-.097-.057-3.226-1.855a.53.53 0 0 0-.53 0L6.249 6.153V4.598a.04.04 0 0 1 .019-.04L9.533 2.7a3.07 3.07 0 0 1 3.257.139c.474.325.843.778 1.066 1.303.223.526.289 1.103.191 1.664zM5.503 8.575 4.139 7.8a.05.05 0 0 1-.026-.037V4.049c0-.57.166-1.127.476-1.607s.752-.864 1.275-1.105a3.08 3.08 0 0 1 3.234.41l-.096.054-3.23 1.838a.53.53 0 0 0-.265.455zm.742-1.577 1.758-1 1.762 1v2l-1.755 1-1.762-1z"/>
                  </svg>
                ),
                bgColor: "bg-[#10a37f]",
              },
              {
                name: "Claude",
                provider: "Anthropic",
                strength: "Analise contextual profunda",
                icon: (
                  <svg viewBox="0 0 16 16" className="h-7 w-7" fill="currentColor">
                    <path d="m3.127 10.604 3.135-1.76.053-.153-.053-.085H6.11l-.525-.032-1.791-.048-1.554-.065-1.505-.08-.38-.081L0 7.832l.036-.234.32-.214.455.04 1.009.069 1.513.105 1.097.064 1.626.17h.259l.036-.105-.089-.065-.068-.064-1.566-1.062-1.695-1.121-.887-.646-.48-.327-.243-.306-.104-.67.435-.48.585.04.15.04.593.456 1.267.981 1.654 1.218.242.202.097-.068.012-.049-.109-.181-.9-1.626-.96-1.655-.428-.686-.113-.411a2 2 0 0 1-.068-.484l.496-.674L4.446 0l.662.089.279.242.411.94.666 1.48 1.033 2.014.302.597.162.553.06.17h.105v-.097l.085-1.134.157-1.392.154-1.792.052-.504.25-.605.497-.327.387.186.319.456-.045.294-.19 1.23-.37 1.93-.243 1.29h.142l.161-.16.654-.868 1.097-1.372.484-.545.565-.601.363-.287h.686l.505.751-.226.775-.707.895-.585.759-.839 1.13-.524.904.048.072.125-.012 1.897-.403 1.024-.186 1.223-.21.553.258.06.263-.218.536-1.307.323-1.533.307-2.284.54-.028.02.032.04 1.029.098.44.024h1.077l2.005.15.525.346.315.424-.053.323-.807.411-3.631-.863-.872-.218h-.12v.073l.726.71 1.331 1.202 1.667 1.55.084.383-.214.302-.226-.032-1.464-1.101-.565-.497-1.28-1.077h-.084v.113l.295.432 1.557 2.34.08.718-.112.234-.404.141-.444-.08-.911-1.28-.94-1.44-.759-1.291-.093.053-.448 4.821-.21.246-.484.186-.403-.307-.214-.496.214-.98.258-1.28.21-1.016.19-1.263.112-.42-.008-.028-.092.012-.953 1.307-1.448 1.957-1.146 1.227-.274.109-.477-.247.045-.44.266-.39 1.586-2.018.956-1.25.617-.723-.004-.105h-.036l-4.212 2.736-.75.096-.324-.302.04-.496.154-.162 1.267-.871z"/>
                  </svg>
                ),
                bgColor: "bg-[#d97757]",
              },
              {
                name: "Gemini",
                provider: "Google",
                strength: "Redacao e sintese juridica",
                icon: (
                  <svg viewBox="0 0 24 24" className="h-7 w-7" fill="currentColor">
                    <path d="M11.04 19.32Q12 21.51 12 24q0-2.49.93-4.68.96-2.19 2.58-3.81t3.81-2.55Q21.51 12 24 12q-2.49 0-4.68-.93a12.3 12.3 0 0 1-3.81-2.58 12.3 12.3 0 0 1-2.58-3.81Q12 2.49 12 0q0 2.49-.96 4.68-.93 2.19-2.55 3.81a12.3 12.3 0 0 1-3.81 2.58Q2.49 12 0 12q2.49 0 4.68.96 2.19.93 3.81 2.55t2.55 3.81"/>
                  </svg>
                ),
                bgColor: "bg-[#8E75B2]",
              },
              {
                name: "Perplexity",
                provider: "Perplexity AI",
                strength: "Pesquisa com fontes verificadas",
                icon: (
                  <svg viewBox="0 0 16 16" className="h-7 w-7" fill="currentColor">
                    <path fillRule="evenodd" d="M8 .188a.5.5 0 0 1 .503.5V4.03l3.022-2.92.059-.048a.51.51 0 0 1 .49-.054.5.5 0 0 1 .306.46v3.247h1.117l.1.01a.5.5 0 0 1 .403.49v5.558a.5.5 0 0 1-.503.5H12.38v3.258a.5.5 0 0 1-.312.462.51.51 0 0 1-.55-.11l-3.016-3.018v3.448c0 .275-.225.5-.503.5a.5.5 0 0 1-.503-.5v-3.448l-3.018 3.019a.51.51 0 0 1-.548.11.5.5 0 0 1-.312-.463v-3.258H2.503a.5.5 0 0 1-.503-.5V5.215l.01-.1c.047-.229.25-.4.493-.4H3.62V1.469l.006-.074a.5.5 0 0 1 .302-.387.51.51 0 0 1 .547.102l3.023 2.92V.687c0-.276.225-.5.503-.5M4.626 9.333v3.984l2.87-2.872v-4.01zm3.877 1.113 2.871 2.871V9.333l-2.87-2.897zm3.733-1.668a.5.5 0 0 1 .145.35v1.145h.612V5.715H9.201zm-9.23 1.495h.613V9.13c0-.131.052-.257.145-.35l3.033-3.064h-3.79zm1.62-5.558H6.76L4.626 2.652zm4.613 0h2.134V2.652z"/>
                  </svg>
                ),
                bgColor: "bg-[#20808d]",
              },
              {
                name: "DeepSeek",
                provider: "DeepSeek",
                strength: "Reasoning avancado e logica",
                icon: (
                  <svg viewBox="0 0 377 278" className="h-7 w-7" fill="currentColor">
                    <path d="M373.15,23.32c-4-1.95-5.72,1.77-8.06,3.66-.79.62-1.47,1.43-2.14,2.14-5.85,6.26-12.67,10.36-21.57,9.86-13.04-.71-24.16,3.38-33.99,13.37-2.09-12.31-9.04-19.66-19.6-24.38-5.54-2.45-11.13-4.9-14.99-10.23-2.71-3.78-3.44-8-4.81-12.16-.85-2.51-1.72-5.09-4.6-5.52-3.13-.5-4.36,2.14-5.58,4.34-4.93,8.99-6.82,18.92-6.65,28.97.43,22.58,9.97,40.56,28.89,53.37,2.16,1.46,2.71,2.95,2.03,5.09-1.29,4.4-2.82,8.68-4.19,13.09-.85,2.82-2.14,3.44-5.15,2.2-10.39-4.34-19.37-10.76-27.29-18.55-13.46-13.02-25.63-27.41-40.81-38.67-3.57-2.64-7.12-5.09-10.81-7.41-15.49-15.07,2.03-27.45,6.08-28.9,4.25-1.52,1.47-6.79-12.23-6.73-13.69.06-26.24,4.65-42.21,10.76-2.34.93-4.79,1.61-7.32,2.14-14.5-2.73-29.55-3.35-45.29-1.58-29.62,3.32-53.28,17.34-70.68,41.28C1.29,88.2-3.63,120.88,2.39,155c6.33,35.91,24.64,65.68,52.8,88.94,29.18,24.1,62.8,35.91,101.15,33.65,23.29-1.33,49.23-4.46,78.48-29.24,7.38,3.66,15.12,5.12,27.97,6.23,9.89.93,19.41-.5,26.79-2.02,11.55-2.45,10.75-13.15,6.58-15.13-33.87-15.78-26.44-9.36-33.2-14.54,17.21-20.41,43.15-41.59,53.3-110.19.79-5.46.11-8.87,0-13.3-.06-2.67.54-3.72,3.61-4.03,8.48-.96,16.72-3.29,24.28-7.47,21.94-12,30.78-31.69,32.87-55.33.31-3.6-.06-7.35-3.86-9.24Z"/>
                  </svg>
                ),
                bgColor: "bg-[#4D6BFE]",
              },
              {
                name: "Llama",
                provider: "Meta",
                strength: "Modelos open-source poderosos",
                icon: (
                  <svg viewBox="0 0 24 24" className="h-7 w-7" fill="currentColor">
                    <path d="M6.915 4.03c-1.968 0-3.683 1.28-4.871 3.113C.704 9.208 0 11.883 0 14.449c0 .706.07 1.369.21 1.973a6.624 6.624 0 0 0 .265.86 5.297 5.297 0 0 0 .371.761c.696 1.159 1.818 1.927 3.593 1.927 1.497 0 2.633-.671 3.965-2.444.76-1.012 1.144-1.626 2.663-4.32l.756-1.339.186-.325c.061.1.121.196.183.3l2.152 3.595c.724 1.21 1.665 2.556 2.47 3.314 1.046.987 1.992 1.22 3.06 1.22 1.075 0 1.876-.355 2.455-.843a3.743 3.743 0 0 0 .81-.973c.542-.939.861-2.127.861-3.745 0-2.72-.681-5.357-2.084-7.45-1.282-1.912-2.957-2.93-4.716-2.93-1.047 0-2.088.467-3.053 1.308-.652.57-1.257 1.29-1.82 2.05-.69-.875-1.335-1.547-1.958-2.056-1.182-.966-2.315-1.303-3.454-1.303zm10.16 2.053c1.147 0 2.188.758 2.992 1.999 1.132 1.748 1.647 4.195 1.647 6.4 0 1.548-.368 2.9-1.839 2.9-.58 0-1.027-.23-1.664-1.004-.496-.601-1.343-1.878-2.832-4.358l-.617-1.028a44.908 44.908 0 0 0-1.255-1.98c.07-.109.141-.224.211-.327 1.12-1.667 2.118-2.602 3.358-2.602zm-10.201.553c1.265 0 2.058.791 2.675 1.446.307.327.737.871 1.234 1.579l-1.02 1.566c-.757 1.163-1.882 3.017-2.837 4.338-1.191 1.649-1.81 1.817-2.486 1.817-.524 0-1.038-.237-1.383-.794-.263-.426-.464-1.13-.464-2.046 0-2.221.63-4.535 1.66-6.088.454-.687.964-1.226 1.533-1.533a2.264 2.264 0 0 1 1.088-.285z"/>
                  </svg>
                ),
                bgColor: "bg-[#0467DF]",
              },
              {
                name: "Mistral",
                provider: "Mistral AI",
                strength: "Eficiencia e velocidade",
                icon: (
                  <svg viewBox="0 0 24 24" className="h-7 w-7">
                    <rect x="0" y="0" width="5" height="5" fill="#FCDB04"/>
                    <rect x="19" y="0" width="5" height="5" fill="#FCDB04"/>
                    <rect x="0" y="6.3" width="5" height="5" fill="#FCB404"/>
                    <rect x="6.3" y="6.3" width="5" height="5" fill="#FCB404"/>
                    <rect x="13" y="6.3" width="5" height="5" fill="#FCB404"/>
                    <rect x="19" y="6.3" width="5" height="5" fill="#FCB404"/>
                    <rect x="0" y="12.7" width="5" height="5" fill="#FC8304"/>
                    <rect x="6.3" y="12.7" width="11.7" height="5" fill="#FC8304"/>
                    <rect x="19" y="12.7" width="5" height="5" fill="#FC8304"/>
                    <rect x="0" y="19" width="5" height="5" fill="#FC4C04"/>
                    <rect x="6.3" y="19" width="5" height="5" fill="#FC4C04"/>
                    <rect x="13" y="19" width="5" height="5" fill="#FC4C04"/>
                    <rect x="19" y="19" width="5" height="5" fill="#FC4C04"/>
                  </svg>
                ),
                bgColor: "bg-[#131313]",
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
        variant="steps"
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
            <h2 className="text-4xl font-bold heading-section mb-6 text-slate-900 dark:text-white">A VORBIUM não &ldquo;ajuda&rdquo; o jurídico.</h2>
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
