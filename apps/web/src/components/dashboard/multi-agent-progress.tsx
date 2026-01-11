import { useEffect, useState } from 'react';
import { CheckCircle2, Circle, Loader2, Brain, Search, PenTool, FileCheck } from 'lucide-react';
import { cn } from '@/lib/utils';

type AgentStep = 'strategist' | 'researcher' | 'drafter' | 'reviewer' | 'completed';

interface MultiAgentProgressProps {
    status: AgentStep;
}

export function MultiAgentProgress({ status }: MultiAgentProgressProps) {
    const steps = [
        {
            id: 'strategist',
            label: 'Estrategista',
            description: 'Definindo tese e estrutura',
            icon: Brain,
        },
        {
            id: 'researcher',
            label: 'Pesquisador',
            description: 'Buscando jurisprudência e leis',
            icon: Search,
        },
        {
            id: 'drafter',
            label: 'Redator',
            description: 'Escrevendo a minuta',
            icon: PenTool,
        },
        {
            id: 'reviewer',
            label: 'Revisor',
            description: 'Verificando consistência e estilo',
            icon: FileCheck,
        },
    ];

    const getStepStatus = (stepId: string) => {
        const stepOrder = ['strategist', 'researcher', 'drafter', 'reviewer', 'completed'];
        const currentIndex = stepOrder.indexOf(status);
        const stepIndex = stepOrder.indexOf(stepId);

        if (stepIndex < currentIndex) return 'completed';
        if (stepIndex === currentIndex) return 'active';
        return 'pending';
    };

    return (
        <div className="w-full rounded-2xl border border-white/70 bg-white/90 p-6 shadow-soft">
            <h3 className="mb-6 font-display text-lg text-foreground">Progresso Multi-Agente</h3>
            <div className="relative flex flex-col gap-8 md:flex-row md:justify-between">
                {/* Connecting Line (Desktop) */}
                <div className="absolute left-4 top-4 h-[calc(100%-2rem)] w-0.5 bg-outline/30 md:left-0 md:top-6 md:h-0.5 md:w-full" />

                {steps.map((step) => {
                    const stepStatus = getStepStatus(step.id);
                    const Icon = step.icon;

                    return (
                        <div key={step.id} className="relative z-10 flex items-center gap-4 md:flex-col md:text-center">
                            <div
                                className={cn(
                                    'flex h-12 w-12 items-center justify-center rounded-full border-2 transition-all duration-500',
                                    stepStatus === 'completed'
                                        ? 'border-green-500 bg-green-50 text-green-600'
                                        : stepStatus === 'active'
                                            ? 'border-indigo-500 bg-indigo-50 text-indigo-600 shadow-[0_0_15px_rgba(99,102,241,0.3)]'
                                            : 'border-outline/30 bg-white text-muted-foreground'
                                )}
                            >
                                {stepStatus === 'completed' ? (
                                    <CheckCircle2 className="h-6 w-6" />
                                ) : stepStatus === 'active' ? (
                                    <Icon className="h-6 w-6 animate-pulse" />
                                ) : (
                                    <Icon className="h-6 w-6" />
                                )}
                            </div>
                            <div>
                                <p
                                    className={cn(
                                        'font-semibold transition-colors',
                                        stepStatus === 'active' ? 'text-indigo-600' : 'text-foreground'
                                    )}
                                >
                                    {step.label}
                                </p>
                                <p className="text-xs text-muted-foreground">{step.description}</p>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
