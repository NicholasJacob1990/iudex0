'use client';

import { motion } from 'framer-motion';
import Link from 'next/link';
import { ArrowRight, CheckCircle2, Zap, Shield, FileText, BrainCircuit, Scale, Building2, GraduationCap, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { GravityBackground } from '@/components/ui/gravity-background';
import { useState, useEffect } from 'react';

export default function HomePage() {
  const [typingText, setTypingText] = useState('');
  const fullText = "Excelentíssimo Senhor Doutor Juiz de Direito da 1ª Vara Cível da Comarca de São Paulo...";

  useEffect(() => {
    let index = 0;
    const interval = setInterval(() => {
      setTypingText(fullText.slice(0, index));
      index++;
      if (index > fullText.length) {
        index = 0;
      }
    }, 50);
    return () => clearInterval(interval);
  }, []);

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1
      }
    }
  };

  const itemVariants = {
    hidden: { y: 20, opacity: 0 },
    visible: {
      y: 0,
      opacity: 1
    }
  };

  return (
    <div className="min-h-screen bg-[#0F1115] text-white overflow-hidden font-sans selection:bg-indigo-500/30 relative">
      <GravityBackground />

      {/* Navbar */}
      <nav className="fixed top-0 w-full z-50 border-b border-white/5 bg-[#0F1115]/80 backdrop-blur-xl">
        <div className="container mx-auto px-6 h-20 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
              <span className="font-bold text-white">I</span>
            </div>
            <span className="text-xl font-bold tracking-tight">Iudex</span>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/login">
              <Button variant="ghost" className="text-gray-200 hover:text-white hover:bg-white/5">
                Entrar
              </Button>
            </Link>
            <Link href="/register">
              <Button className="bg-indigo-600 hover:bg-indigo-700 text-white rounded-full px-6">
                Começar Agora
              </Button>
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative pt-32 pb-20 lg:pt-48 lg:pb-32 overflow-hidden">
        <div className="container mx-auto px-6 relative z-10">
          <motion.div
            initial="hidden"
            animate="visible"
            variants={containerVariants}
            className="max-w-4xl mx-auto text-center"
          >
            <motion.div variants={itemVariants} className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-sm font-medium mb-8 backdrop-blur-sm">
              <Zap className="w-4 h-4" />
              <span>Potencializado por IA Avançada</span>
            </motion.div>

            <motion.h1 variants={itemVariants} className="text-5xl lg:text-7xl font-bold tracking-tight mb-8 bg-clip-text text-transparent bg-gradient-to-b from-white to-white/60 drop-shadow-2xl">
              O Futuro da <br />
              <span className="text-indigo-400">Advocacia Inteligente</span>
            </motion.h1>

            <motion.p variants={itemVariants} className="text-xl text-gray-300 mb-12 max-w-2xl mx-auto leading-relaxed backdrop-blur-sm p-4 rounded-xl bg-black/20">
              Gere peças jurídicas complexas em segundos, analise processos com precisão e aumente a produtividade do seu escritório com nossa IA especializada.
            </motion.p>

            <motion.div variants={itemVariants} className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link href="/register">
                <Button size="lg" className="h-14 px-8 text-lg bg-indigo-600 hover:bg-indigo-700 text-white rounded-full shadow-lg shadow-indigo-500/25 w-full sm:w-auto transition-all hover:scale-105">
                  Criar Conta Grátis
                  <ArrowRight className="ml-2 w-5 h-5" />
                </Button>
              </Link>
              <Link href="/login">
                <Button size="lg" variant="outline" className="h-14 px-8 text-lg border-white/10 bg-white/5 hover:bg-white/10 text-white rounded-full w-full sm:w-auto backdrop-blur-md">
                  Ver Demonstração
                </Button>
              </Link>
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* Trusted By */}
      <section className="py-10 border-y border-white/5 bg-black/20 backdrop-blur-sm">
        <div className="container mx-auto px-6">
          <p className="text-center text-sm text-gray-400 mb-8 uppercase tracking-widest">Confiado por escritórios inovadores</p>
          <div className="flex flex-wrap justify-center gap-12 opacity-70 grayscale hover:grayscale-0 transition-all duration-500">
            {['Machado Meyer', 'Pinheiro Neto', 'Mattos Filho', 'Demarest', 'TozziniFreire'].map((firm) => (
              <div key={firm} className="text-xl font-serif font-bold text-white/60 hover:text-white transition-colors cursor-default">
                {firm}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Interactive Demo Section */}
      <section className="py-24 relative">
        <div className="container mx-auto px-6">
          <div className="grid lg:grid-cols-2 gap-16 items-center">
            <motion.div
              initial={{ opacity: 0, x: -50 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
            >
              <h2 className="text-3xl lg:text-4xl font-bold mb-6">
                Escreva na velocidade do <span className="text-indigo-400">pensamento</span>
              </h2>
              <p className="text-gray-300 text-lg mb-8 leading-relaxed">
                Nossa IA não apenas completa frases, ela entende o contexto jurídico, cita jurisprudência atualizada e formata suas petições automaticamente.
              </p>
              <ul className="space-y-4">
                {[
                  "Jurisprudência atualizada em tempo real",
                  "Formatação automática ABNT e Forense",
                  "Sugestões de teses jurídicas vencedoras"
                ].map((item, i) => (
                  <li key={i} className="flex items-center gap-3 text-gray-200">
                    <div className="h-6 w-6 rounded-full bg-indigo-500/20 flex items-center justify-center">
                      <Check className="w-3 h-3 text-indigo-400" />
                    </div>
                    {item}
                  </li>
                ))}
              </ul>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              className="relative rounded-xl bg-[#1A1D24] border border-white/10 p-6 shadow-2xl"
            >
              <div className="flex items-center gap-2 mb-4 border-b border-white/5 pb-4">
                <div className="h-3 w-3 rounded-full bg-red-500" />
                <div className="h-3 w-3 rounded-full bg-yellow-500" />
                <div className="h-3 w-3 rounded-full bg-green-500" />
                <div className="ml-auto text-xs text-gray-500">peticao_inicial.docx</div>
              </div>
              <div className="font-mono text-sm text-gray-300 leading-relaxed h-48">
                {typingText}
                <span className="animate-pulse inline-block w-2 h-4 bg-indigo-500 ml-1 align-middle"></span>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* Features Grid */}
      <section className="py-24 bg-white/5 border-y border-white/5 backdrop-blur-sm">
        <div className="container mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-3xl lg:text-4xl font-bold mb-4">Recursos Poderosos</h2>
            <p className="text-gray-300">Tudo que você precisa para advogar melhor</p>
          </div>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                icon: FileText,
                title: "Geração de Documentos",
                desc: "Crie petições, contratos e pareceres personalizados em segundos com nossa IA treinada em legislação brasileira."
              },
              {
                icon: BrainCircuit,
                title: "Análise Inteligente",
                desc: "Analise processos e documentos complexos automaticamente, extraindo insights cruciais e jurisprudência relevante."
              },
              {
                icon: Shield,
                title: "Segurança Jurídica",
                desc: "Todos os documentos passam por rigorosa verificação de conformidade e atualização legislativa em tempo real."
              }
            ].map((feature, idx) => (
              <motion.div
                key={idx}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.2 }}
                viewport={{ once: true }}
                className="p-8 rounded-2xl bg-[#0F1115]/50 border border-white/10 hover:border-indigo-500/50 transition-all hover:-translate-y-1 group backdrop-blur-md"
              >
                <div className="h-12 w-12 rounded-lg bg-indigo-500/10 flex items-center justify-center text-indigo-400 mb-6 group-hover:scale-110 transition-transform">
                  <feature.icon className="w-6 h-6" />
                </div>
                <h3 className="text-xl font-bold mb-4 text-white">{feature.title}</h3>
                <p className="text-gray-300 leading-relaxed">
                  {feature.desc}
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Use Cases */}
      <section className="py-24 relative">
        <div className="container mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-3xl lg:text-4xl font-bold mb-4">Para quem é o Iudex?</h2>
            <p className="text-gray-300">A ferramenta essencial para todos os operadores do direito</p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[
              {
                icon: Scale,
                title: "Advogados Autônomos",
                desc: "Aumente sua capacidade de produção sem aumentar custos fixos. Tenha um estagiário sênior 24/7."
              },
              {
                icon: Building2,
                title: "Escritórios de Advocacia",
                desc: "Padronize a qualidade das peças, reduza o tempo de revisão e escale sua operação com eficiência."
              },
              {
                icon: Shield,
                title: "Ministério Público",
                desc: "Agilize a análise de inquéritos e a elaboração de denúncias e pareceres com base em vasta jurisprudência."
              },
              {
                icon: Scale,
                title: "Magistratura",
                desc: "Otimize a minutagem de sentenças e decisões, permitindo maior foco na análise do mérito e celeridade processual."
              },
              {
                icon: Shield,
                title: "Defensoria Pública",
                desc: "Atenda mais assistidos com qualidade, automatizando peças repetitivas e focando na estratégia de defesa."
              },
              {
                icon: GraduationCap,
                title: "Estudantes e Acadêmicos",
                desc: "Aprenda com modelos de excelência e entenda a estrutura de peças jurídicas complexas na prática."
              }
            ].map((useCase, idx) => (
              <motion.div
                key={idx}
                whileHover={{ scale: 1.02 }}
                className="p-6 rounded-xl border border-white/10 bg-gradient-to-b from-white/5 to-transparent hover:from-indigo-500/10 transition-all"
              >
                <useCase.icon className="w-10 h-10 text-indigo-400 mb-4" />
                <h3 className="text-xl font-bold mb-2 text-white">{useCase.title}</h3>
                <p className="text-gray-300 text-sm leading-relaxed">{useCase.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section className="py-24 bg-white/5 border-y border-white/5 backdrop-blur-sm">
        <div className="container mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-3xl lg:text-4xl font-bold mb-4">Planos Flexíveis</h2>
            <p className="text-gray-300">Escolha o melhor para sua necessidade</p>
          </div>
          <div className="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
            {[
              {
                name: "Starter",
                price: "R$ 97",
                period: "/mês",
                features: ["10 documentos/mês", "Análise básica", "Suporte por email"],
                highlight: false
              },
              {
                name: "Pro",
                price: "R$ 197",
                period: "/mês",
                features: ["Documentos ilimitados", "Análise avançada", "Prioridade no suporte", "Acesso a API"],
                highlight: true
              },
              {
                name: "Enterprise",
                price: "Sob Consulta",
                period: "",
                features: ["SLA garantido", "Treinamento dedicado", "Integração customizada", "Gestor de conta"],
                highlight: false
              }
            ].map((plan, idx) => (
              <motion.div
                key={idx}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.1 }}
                viewport={{ once: true }}
                className={`relative p-8 rounded-2xl border ${plan.highlight ? 'border-indigo-500 bg-indigo-500/10' : 'border-white/10 bg-[#0F1115]'} flex flex-col`}
              >
                {plan.highlight && (
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2 px-4 py-1 rounded-full bg-indigo-500 text-white text-xs font-bold uppercase tracking-wider">
                    Mais Popular
                  </div>
                )}
                <h3 className="text-xl font-bold mb-2">{plan.name}</h3>
                <div className="mb-6">
                  <span className="text-4xl font-bold">{plan.price}</span>
                  <span className="text-gray-300 text-sm">{plan.period}</span>
                </div>
                <ul className="space-y-4 mb-8 flex-1">
                  {plan.features.map((feature, i) => (
                    <li key={i} className="flex items-center gap-3 text-sm text-gray-200">
                      <Check className={`w-4 h-4 ${plan.highlight ? 'text-indigo-400' : 'text-gray-400'}`} />
                      {feature}
                    </li>
                  ))}
                </ul>
                <Button className={`w-full ${plan.highlight ? 'bg-indigo-600 hover:bg-indigo-700' : 'bg-white/10 hover:bg-white/20'} text-white`}>
                  Escolher Plano
                </Button>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-32 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-indigo-900/20 to-[#0F1115]" />
        <div className="container mx-auto px-6 relative z-10 text-center">
          <h2 className="text-4xl lg:text-5xl font-bold mb-8">Pronto para revolucionar sua advocacia?</h2>
          <p className="text-xl text-gray-300 mb-12 max-w-2xl mx-auto">
            Junte-se a milhares de advogados que já estão usando o Iudex para trabalhar de forma mais inteligente.
          </p>
          <Link href="/register">
            <Button size="lg" className="h-16 px-10 text-xl bg-white text-indigo-900 hover:bg-gray-100 rounded-full shadow-2xl shadow-white/10">
              Começar Gratuitamente
            </Button>
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 border-t border-white/5 bg-[#0F1115] relative z-10">
        <div className="container mx-auto px-6">
          <div className="grid md:grid-cols-4 gap-12 mb-12">
            <div className="col-span-2">
              <div className="flex items-center gap-2 mb-6">
                <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
                  <span className="font-bold text-white">I</span>
                </div>
                <span className="text-xl font-bold tracking-tight">Iudex</span>
              </div>
              <p className="text-gray-400 max-w-sm">
                A plataforma de inteligência artificial definitiva para o mercado jurídico brasileiro.
              </p>
            </div>
            <div>
              <h4 className="font-bold mb-6">Produto</h4>
              <ul className="space-y-4 text-gray-400">
                <li><a href="#" className="hover:text-indigo-400 transition-colors">Funcionalidades</a></li>
                <li><a href="#" className="hover:text-indigo-400 transition-colors">Preços</a></li>
                <li><a href="#" className="hover:text-indigo-400 transition-colors">Casos de Uso</a></li>
              </ul>
            </div>
            <div>
              <h4 className="font-bold mb-6">Empresa</h4>
              <ul className="space-y-4 text-gray-400">
                <li><a href="#" className="hover:text-indigo-400 transition-colors">Sobre</a></li>
                <li><a href="#" className="hover:text-indigo-400 transition-colors">Blog</a></li>
                <li><a href="#" className="hover:text-indigo-400 transition-colors">Contato</a></li>
              </ul>
            </div>
          </div>
          <div className="pt-8 border-t border-white/5 text-center text-gray-500 text-sm">
            <p>&copy; 2024 Iudex. Todos os direitos reservados.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
