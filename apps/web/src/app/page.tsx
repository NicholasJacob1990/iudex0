'use client';

import React from 'react';
import { HeroSection } from '@/components/vorbium/hero-section';
import { Footer } from '@/components/vorbium/footer';
import { VorbiumNav } from '@/components/vorbium/vorbium-nav';
import { FeatureSection } from '@/components/vorbium/feature-section';
import { Scale, Users, FileText, CheckCircle, Shield, BrainCircuit, Gavel, Search, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Link from 'next/link';

export default function HomePage() {
  const mainRef = React.useRef<HTMLElement>(null);

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
      <VorbiumNav scrollRef={mainRef} />

      <HeroSection />

      {/* Seção: Por que a VORBIUM existe */}
      <section className="py-32 relative snap-start">
        <div className="container mx-auto px-6 max-w-4xl text-center">
          <h2 className="text-3xl md:text-5xl font-bold mb-8 text-slate-900 dark:text-white">Por que a VORBIUM existe</h2>
          <p className="text-xl text-slate-600 dark:text-gray-400 mb-8 leading-relaxed">
            O trabalho jurídico moderno exige mais do que respostas rápidas. Exige interpretação correta, decisão consistente e execução confiável.
          </p>
          <p className="text-xl text-slate-600 dark:text-gray-400 leading-relaxed">
            A VORBIUM organiza conhecimento jurídico e o transforma em processos auditáveis, operados por agentes especializados dentro de regras claras.
          </p>
        </div>
      </section>

      {/* Seção: O que você obtém */}
      <FeatureSection
        title="O que você obtém em uma plataforma única"
        features={benefits}
        className="bg-white dark:bg-white/5 border-y border-slate-200 dark:border-white/5"
      />

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

      {/* CTA Final */}
      <section className="py-32 relative snap-start text-center">
        <div className="container mx-auto px-6">
          <h2 className="text-4xl font-bold mb-6 text-slate-900 dark:text-white">A VORBIUM não “ajuda” o jurídico.</h2>
          <h3 className="text-3xl font-bold mb-12 text-indigo-600 dark:text-indigo-500">Ela opera o jurídico com governança.</h3>
          <Link href="/demo">
            <Button size="lg" className="h-14 px-12 rounded-full text-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-[0_0_40px_-10px_rgba(79,70,229,0.5)] transition-all hover:scale-105">
              Solicitar demonstração
            </Button>
          </Link>
        </div>
      </section>

      <Footer />
    </main>
  );
}
