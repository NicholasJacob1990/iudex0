'use client';

import {
    Upload,
    Search,
    FileText,
    Gavel,
    Sparkles,
    FolderOpen,
    History,
    ArrowRight,
    PlusCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface ContextOption {
    id: string;
    label: string;
    description: string;
    icon: React.ElementType;
    color: string;
    gradient: string;
}

const contextOptions: ContextOption[] = [
    {
        id: 'new',
        label: 'Nova Minuta',
        description: 'Criar do zero com IA',
        icon: PlusCircle,
        color: 'text-indigo-400',
        gradient: 'from-indigo-500/20 to-indigo-600/5',
    },
    {
        id: 'analyze',
        label: 'Analisar Processo',
        description: 'Extrair dados de PDF',
        icon: Search,
        color: 'text-blue-400',
        gradient: 'from-blue-500/20 to-blue-600/5',
    },
    {
        id: 'juris',
        label: 'Jurisprudência',
        description: 'Pesquisa inteligente',
        icon: Gavel,
        color: 'text-amber-400',
        gradient: 'from-amber-500/20 to-amber-600/5',
    },
];

export function ContextDashboard() {
    return (
        <div className="flex h-full flex-col p-6">
            <div className="mb-8">
                <div className="mb-6 flex items-center justify-between">
                    <div>
                        <h3 className="font-display text-xl font-bold text-foreground flex items-center gap-2">
                            <Sparkles className="h-5 w-5 text-yellow-500" />
                            Ações Rápidas
                        </h3>
                        <p className="text-xs text-muted-foreground">
                            Selecione uma ferramenta para iniciar
                        </p>
                    </div>
                </div>

                <div className="grid gap-3">
                    {contextOptions.map((option) => {
                        const Icon = option.icon;
                        return (
                            <button
                                key={option.id}
                                className="group relative overflow-hidden rounded-xl border border-white/5 bg-card/30 p-1 transition-all hover:border-primary/30 hover:bg-card/50"
                            >
                                <div className="relative flex items-center gap-4 rounded-lg p-3">
                                    <div className={cn("flex h-10 w-10 items-center justify-center rounded-lg bg-white/5 shadow-inner ring-1 ring-white/5 transition-transform group-hover:scale-105", option.color)}>
                                        <Icon className="h-5 w-5" />
                                    </div>
                                    <div className="flex-1 text-left">
                                        <p className="font-medium text-sm text-foreground group-hover:text-primary transition-colors">{option.label}</p>
                                        <p className="text-[10px] text-muted-foreground">{option.description}</p>
                                    </div>
                                    <ArrowRight className="h-4 w-4 text-muted-foreground/50 opacity-0 transition-all group-hover:translate-x-1 group-hover:opacity-100" />
                                </div>
                            </button>
                        );
                    })}
                </div>
            </div>

            <div className="mt-auto">
                <div className="rounded-xl border border-white/10 bg-white/5 p-4 backdrop-blur-md">
                    <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                            <History className="h-3.5 w-3.5" />
                            <span>Recentes</span>
                        </div>
                        <Button variant="ghost" size="sm" className="h-5 text-[10px] hover:text-primary px-2">Ver tudo</Button>
                    </div>
                    <div className="space-y-2">
                        {[1, 2, 3].map((i) => (
                            <div key={i} className="flex items-center gap-3 rounded-lg p-2 hover:bg-white/5 cursor-pointer transition-colors group">
                                <div className="flex h-6 w-6 items-center justify-center rounded bg-indigo-500/20 text-indigo-400">
                                    <FileText className="h-3 w-3" />
                                </div>
                                <div className="flex-1 overflow-hidden">
                                    <p className="text-xs text-foreground truncate group-hover:text-indigo-300 transition-colors">Agravo de Instrumento - Caso Silva</p>
                                    <p className="text-[10px] text-muted-foreground">Há 2 horas • Rascunho</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}
