'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuthStore } from '@/stores';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { toast } from 'sonner';
import { MotionDiv, scaleIn, smoothTransition } from '@/components/ui/motion';
import { PaintBackground } from '@/components/ui/paint-background';

export default function RegisterPage() {
  const router = useRouter();
  const { register, isLoading } = useAuthStore();

  // Form State
  const [step, setStep] = useState<'profile' | 'details'>('profile');
  const [profileType, setProfileType] = useState<'individual' | 'institutional'>('individual');

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  // Individual Details
  const [cpf, setCpf] = useState('');
  const [oab, setOab] = useState('');
  const [oabState, setOabState] = useState('');
  const [phone, setPhone] = useState('');

  // Institutional Details
  const [orgName, setOrgName] = useState('');
  const [teamSize, setTeamSize] = useState('');
  const [industry, setIndustry] = useState('');
  const [role, setRole] = useState('');
  const [cnpj, setCnpj] = useState('');
  const [department, setDepartment] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!name || !email || !password || !confirmPassword) {
      toast.error('Por favor, preencha todos os campos obrigatórios');
      return;
    }

    if (profileType === 'institutional') {
      if (!orgName || !teamSize || !industry || !role) {
        toast.error('Por favor, preencha todos os detalhes da organização');
        return;
      }
    }

    if (password !== confirmPassword) {
      toast.error('As senhas não coincidem');
      return;
    }

    if (password.length < 8) {
      toast.error('A senha deve ter no mínimo 8 caracteres');
      return;
    }

    try {
      // Register with profile data
      await register({
        name,
        email,
        password,
        account_type: profileType === 'individual' ? 'INDIVIDUAL' : 'INSTITUTIONAL',
        // Institutional data
        institution_name: profileType === 'institutional' ? orgName : undefined,
        team_size: profileType === 'institutional' ? teamSize : undefined,
        position: profileType === 'institutional' ? role : undefined,
        cnpj: profileType === 'institutional' ? cnpj : undefined,
        department: profileType === 'institutional' ? department : undefined,
        // Individual data
        cpf: profileType === 'individual' ? cpf : undefined,
        oab: profileType === 'individual' ? oab : undefined,
        oab_state: profileType === 'individual' ? oabState : undefined,
        phone: phone || undefined,
      });
      toast.success('Conta criada com sucesso! Bem-vindo ao Iudex.');
      router.push('/generator'); // Redirect directly to generator for immediate value
    } catch (error) {
      // Erro já tratado pelo interceptor
      console.error(error);
      toast.error('Erro ao criar conta. Tente novamente.');
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-gradient-to-br from-primary/10 via-background to-secondary/10 p-4 font-sans overflow-hidden">
      {/* Paint worklet background */}
      <PaintBackground worklet="grid-pulse" color="#8b5cf6" seed={67} />

      {/* Animated gradient mesh background */}
      <div className="pointer-events-none absolute inset-0 z-[1]">
        <div className="absolute -top-32 -left-32 h-96 w-96 rounded-full bg-indigo-500/15 blur-3xl animate-drift" />
        <div className="absolute -bottom-32 -right-32 h-96 w-96 rounded-full bg-purple-500/15 blur-3xl animate-float" />
      </div>

      <MotionDiv
        variants={scaleIn}
        initial="hidden"
        animate="visible"
        transition={smoothTransition}
        className="w-full max-w-md relative z-10"
      >
      <Card className="w-full max-w-md backdrop-blur-xl bg-white/80 dark:bg-white/5 dark:border-white/10">
        <CardHeader className="space-y-1 text-center">
          <CardTitle className="text-3xl font-bold">
            {step === 'profile' ? 'Escolha seu Perfil' : 'Criar Conta'}
          </CardTitle>
          <CardDescription>
            {step === 'profile'
              ? 'Personalize sua experiência no Iudex'
              : 'Preencha seus dados para começar'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {step === 'profile' ? (
            <div className="grid gap-4">
              <button
                onClick={() => { setProfileType('individual'); setStep('details'); }}
                className="group relative flex items-center gap-4 rounded-xl border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-white/5 p-4 transition-all hover:border-indigo-500/50 hover:bg-indigo-500/10"
              >
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-indigo-500/20 text-indigo-400 group-hover:scale-110 transition-transform">
                  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></svg>
                </div>
                <div className="text-left">
                  <h3 className="font-semibold text-slate-900 dark:text-white">Individual</h3>
                  <p className="text-sm text-slate-500 dark:text-gray-400">Para advogados autônomos, consultores e estudantes.</p>
                </div>
              </button>

              <button
                onClick={() => { setProfileType('institutional'); setStep('details'); }}
                className="group relative flex items-center gap-4 rounded-xl border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-white/5 p-4 transition-all hover:border-purple-500/50 hover:bg-purple-500/10"
              >
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-purple-500/20 text-purple-400 group-hover:scale-110 transition-transform">
                  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 21h18" /><path d="M5 21V7l8-4 8 4v14" /><path d="M17 21v-8H7v8" /><path d="M9 9h1" /><path d="M9 13h1" /><path d="M9 17h1" /><path d="M14 9h1" /><path d="M14 13h1" /><path d="M14 17h1" /></svg>
                </div>
                <div className="text-left">
                  <h3 className="font-semibold text-slate-900 dark:text-white">Institucional</h3>
                  <p className="text-sm text-slate-500 dark:text-gray-400">Para escritórios de advocacia e departamentos jurídicos.</p>
                </div>
              </button>

              <div className="text-center text-sm mt-4">
                <span className="text-muted-foreground">Já tem uma conta? </span>
                <Link href="/login" className="text-primary hover:underline">
                  Faça login
                </Link>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="flex items-center gap-2 mb-4 text-sm text-muted-foreground">
                <button type="button" onClick={() => setStep('profile')} className="hover:text-foreground transition-colors">
                  ← Voltar
                </button>
                <span className="text-slate-300 dark:text-gray-600">|</span>
                <span className="text-primary capitalize">{profileType === 'individual' ? 'Individual' : 'Institucional'}</span>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700 dark:text-slate-200">Nome Completo</label>
                <Input
                  className="text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-all duration-300"
                  placeholder="Seu nome"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={isLoading}
                  required
                />
              </div>

              {profileType === 'individual' && (
                <>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <label className="text-sm font-medium text-slate-700 dark:text-slate-200">CPF</label>
                      <Input
                        className="text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-all duration-300"
                        placeholder="000.000.000-00"
                        value={cpf}
                        onChange={(e) => setCpf(e.target.value)}
                        disabled={isLoading}
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-medium text-slate-700 dark:text-slate-200">Telefone</label>
                      <Input
                        className="text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-all duration-300"
                        placeholder="(00) 00000-0000"
                        value={phone}
                        onChange={(e) => setPhone(e.target.value)}
                        disabled={isLoading}
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <label className="text-sm font-medium text-slate-700 dark:text-slate-200">OAB</label>
                      <Input
                        className="text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-all duration-300"
                        placeholder="000000"
                        value={oab}
                        onChange={(e) => setOab(e.target.value)}
                        disabled={isLoading}
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-medium text-slate-700 dark:text-slate-200">UF OAB</label>
                      <Input
                        className="text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-all duration-300"
                        placeholder="SP"
                        value={oabState}
                        onChange={(e) => setOabState(e.target.value)}
                        disabled={isLoading}
                        maxLength={2}
                      />
                    </div>
                  </div>
                </>
              )}

              {profileType === 'institutional' && (
                <>
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-slate-700 dark:text-slate-200">Nome da Organização</label>
                    <Input
                      className="text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-all duration-300"
                      placeholder="Nome do Escritório ou Empresa"
                      value={orgName}
                      onChange={(e) => setOrgName(e.target.value)}
                      disabled={isLoading}
                      required
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <label className="text-sm font-medium text-slate-700 dark:text-slate-200">CNPJ</label>
                      <Input
                        className="text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-all duration-300"
                        placeholder="00.000.000/0000-00"
                        value={cnpj}
                        onChange={(e) => setCnpj(e.target.value)}
                        disabled={isLoading}
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-medium text-slate-700 dark:text-slate-200">Departamento</label>
                      <Input
                        className="text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-all duration-300"
                        placeholder="Jurídico"
                        value={department}
                        onChange={(e) => setDepartment(e.target.value)}
                        disabled={isLoading}
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <label className="text-sm font-medium text-slate-700 dark:text-slate-200">Setor de Atuação</label>
                      <select
                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                        value={industry}
                        onChange={(e) => setIndustry(e.target.value)}
                        disabled={isLoading}
                        required
                      >
                        <option value="" className="bg-background">Selecione...</option>
                        <option value="law_firm" className="bg-background">Escritório de Advocacia</option>
                        <option value="corporate_legal" className="bg-background">Jurídico Interno</option>
                        <option value="government" className="bg-background">Setor Público</option>
                        <option value="other" className="bg-background">Outro</option>
                      </select>
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-medium text-slate-700 dark:text-slate-200">Tamanho da Equipe</label>
                      <select
                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                        value={teamSize}
                        onChange={(e) => setTeamSize(e.target.value)}
                        disabled={isLoading}
                        required
                      >
                        <option value="" className="bg-background">Selecione...</option>
                        <option value="1-5" className="bg-background">1-5 pessoas</option>
                        <option value="6-20" className="bg-background">6-20 pessoas</option>
                        <option value="21-50" className="bg-background">21-50 pessoas</option>
                        <option value="50+" className="bg-background">50+ pessoas</option>
                      </select>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-slate-700 dark:text-slate-200">Seu Cargo</label>
                    <Input
                      className="text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-all duration-300"
                      placeholder="Ex: Sócio, Advogado Sênior, Diretor..."
                      value={role}
                      onChange={(e) => setRole(e.target.value)}
                      disabled={isLoading}
                      required
                    />
                  </div>
                </>
              )}

              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700 dark:text-slate-200">Email Profissional</label>
                <Input
                  className="text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-all duration-300"
                  type="email"
                  placeholder="seu@email.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={isLoading}
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-700 dark:text-slate-200">Senha</label>
                  <Input
                    className="text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-all duration-300"
                    type="password"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    disabled={isLoading}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-700 dark:text-slate-200">Confirmar</label>
                  <Input
                    className="text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-all duration-300"
                    type="password"
                    placeholder="••••••••"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    disabled={isLoading}
                    required
                  />
                </div>
              </div>

              <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading ? 'Criando conta...' : 'Finalizar Cadastro'}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
      </MotionDiv>
    </div>
  );
}

