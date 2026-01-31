'use client';

import { useRouter } from 'next/navigation';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { User, Building2 } from 'lucide-react';
import { MotionDiv, scaleIn, fadeUp, smoothTransition } from '@/components/ui/motion';
import { StaggerContainer } from '@/components/ui/animated-container';

export default function RegisterTypePage() {
  const router = useRouter();

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100 p-4 overflow-hidden">
      {/* Animated gradient mesh background */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -top-32 -left-32 h-96 w-96 rounded-full bg-indigo-500/20 blur-3xl animate-drift" />
        <div className="absolute -bottom-32 -right-32 h-96 w-96 rounded-full bg-purple-500/20 blur-3xl animate-float" />
      </div>

      <div className="w-full max-w-4xl relative z-10">
        <MotionDiv variants={fadeUp} initial="hidden" animate="visible" transition={smoothTransition} className="mb-8 text-center">
          <h1 className="font-display text-4xl font-bold">Bem-vindo ao Iudex</h1>
          <p className="mt-2 text-lg text-muted-foreground">
            Escolha o tipo de conta que melhor se adequa a você
          </p>
        </MotionDiv>

        <StaggerContainer className="grid gap-6 md:grid-cols-2">
          {/* Individual */}
          <MotionDiv variants={fadeUp}>
          <Card className="group cursor-pointer overflow-hidden border-2 border-border transition-all hover:border-primary hover:shadow-lg backdrop-blur-xl bg-white/80">
            <button
              onClick={() => router.push('/register/individual')}
              className="w-full p-8 text-left"
            >
              <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-primary transition-all group-hover:bg-primary group-hover:text-white">
                <User className="h-8 w-8" />
              </div>
              
              <h2 className="mb-2 font-display text-2xl font-bold">Conta Individual</h2>
              <p className="mb-4 text-muted-foreground">
                Para advogados e profissionais autônomos
              </p>
              
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>Cadastro com CPF e OAB</span>
                </li>
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>Assinatura pessoal em documentos</span>
                </li>
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>Biblioteca individual</span>
                </li>
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>Geração ilimitada de documentos</span>
                </li>
              </ul>

              <div className="mt-6">
                <Button className="w-full">
                  Criar Conta Individual
                </Button>
              </div>
            </button>
          </Card>
          </MotionDiv>

          {/* Institutional */}
          <MotionDiv variants={fadeUp}>
          <Card className="group cursor-pointer overflow-hidden border-2 border-border transition-all hover:border-primary hover:shadow-lg backdrop-blur-xl bg-white/80">
            <button
              onClick={() => router.push('/register/institutional')}
              className="w-full p-8 text-left"
            >
              <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-primary transition-all group-hover:bg-primary group-hover:text-white">
                <Building2 className="h-8 w-8" />
              </div>
              
              <h2 className="mb-2 font-display text-2xl font-bold">Conta Institucional</h2>
              <p className="mb-4 text-muted-foreground">
                Para escritórios, empresas e instituições
              </p>
              
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>Cadastro com CNPJ</span>
                </li>
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>Assinatura institucional com logotipo</span>
                </li>
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>Múltiplos usuários (em breve)</span>
                </li>
                <li className="flex items-start">
                  <span className="mr-2">•</span>
                  <span>Biblioteca compartilhada</span>
                </li>
              </ul>

              <div className="mt-6">
                <Button className="w-full">
                  Criar Conta Institucional
                </Button>
              </div>
            </button>
          </Card>
          </MotionDiv>
        </StaggerContainer>

        <p className="mt-8 text-center text-sm text-muted-foreground">
          Já tem uma conta?{' '}
          <a href="/login" className="font-medium text-primary hover:underline">
            Faça login
          </a>
        </p>
      </div>
    </div>
  );
}





