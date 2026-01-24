'use client';

import { useMemo } from 'react';
import { Badge } from '@/components/ui/badge';
import {
    Activity,
    AlertTriangle,
    Bot,
    CheckCircle2,
    Compass,
    FileText,
    Search,
    ShieldAlert,
    ShieldCheck,
    Sparkles,
} from 'lucide-react';

interface TimelineItem {
    type: string;
    label: string;
    meta?: string;
    tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'info';
}

export interface TimelineGroup {
    title: string;
    events: Array<{
        type: string;
        agent?: string;
        data?: any;
    }>;
}

const iconForType = (type: string) => {
    if (type.startsWith('rag_')) return Compass;
    if (type.startsWith('research')) return Search;
    if (type.startsWith('agent') || type === 'section_completed' || type === 'section_stage') return Bot;
    if (type === 'divergence_detected') return AlertTriangle;
    if (type === 'audit_result') return ShieldCheck;
    if (type === 'documentgate_result') return ShieldAlert;
    if (type === 'workflow_end') return CheckCircle2;
    if (type === 'outline_generated') return FileText;
    return Activity;
};

const buildLabel = (event: { type: string; agent?: string; data?: any }): TimelineItem => {
    const data = event.data || {};
    const stageLabel = (stageRaw?: string) => {
        const stage = String(stageRaw || '').toLowerCase();
        switch (stage) {
            case 'draft':
                return 'Rascunho';
            case 'critique':
                return 'Critica';
            case 'revise':
                return 'Revisao';
            case 'merge':
                return 'Consolidacao';
            default:
                return stageRaw || '';
        }
    };
    switch (event.type) {
        case 'outline_generated':
            return { type: event.type, label: 'Outline gerado', tone: 'info' };
        case 'workflow_start':
            return { type: event.type, label: 'Workflow iniciado', tone: 'info' };
        case 'planner_decision':
            return { type: event.type, label: 'Planner decidiu pesquisa', tone: 'info' };
        case 'research_start':
            return { type: event.type, label: `Pesquisa ${data.researchmode || '-'} iniciou`, tone: 'info' };
        case 'research_done':
            return {
                type: event.type,
                label: `Pesquisa ${data.researchmode || '-'} concluida`,
                meta: data.sources_count ? `${data.sources_count} fontes` : undefined,
                tone: 'success',
            };
        case 'deepresearch_step':
            return { type: event.type, label: 'Deep Research step', tone: 'neutral' };
        case 'section_start':
            return { type: event.type, label: 'Secao iniciou', tone: 'info' };
        case 'section_context_start':
            return { type: event.type, label: 'Contexto em preparo', tone: 'neutral' };
        case 'section_context_ready':
            return { type: event.type, label: 'Contexto pronto', tone: 'success' };
        case 'section_stage': {
            const label = stageLabel(data.stage);
            return {
                type: event.type,
                label: label ? `Etapa: ${label}` : 'Etapa da secao',
                tone: 'info',
            };
        }
        case 'rag_routing':
            return {
                type: event.type,
                label: `RAG: ${data.strategy || 'routing'}`,
                meta: data.topk ? `topk ${data.topk}` : undefined,
                tone: 'info',
            };
        case 'rag_gate':
            return {
                type: event.type,
                label: `CRAG gate ${data.gatepassed ? 'passou' : 'falhou'}`,
                tone: data.gatepassed ? 'success' : 'warning',
            };
        case 'agent_start':
            return { type: event.type, label: `Agente ${event.agent || ''} iniciou`, tone: 'info' };
        case 'agent_output':
            return { type: event.type, label: `Agente ${event.agent || ''} rascunho`, tone: 'neutral' };
        case 'agent_end':
            return { type: event.type, label: `Agente ${event.agent || ''} finalizado`, tone: 'success' };
        case 'section_completed':
            return { type: event.type, label: 'Secao concluida', tone: 'success' };
        case 'section_error':
            return { type: event.type, label: 'Erro na secao', tone: 'danger' };
        case 'divergence_detected':
            return { type: event.type, label: 'Divergencia detectada', tone: 'warning' };
        case 'audit_result':
            return { type: event.type, label: 'Auditoria concluida', tone: 'success' };
        case 'stylecheck_result':
            return { type: event.type, label: 'Style check concluido', tone: 'info' };
        case 'documentgate_result':
            return { type: event.type, label: 'Document gate concluido', tone: 'info' };
        case 'hil_required':
            return { type: event.type, label: 'HIL requerido', tone: 'warning' };
        case 'hil_response':
            return { type: event.type, label: 'HIL respondido', tone: 'success' };
        case 'workflow_end':
            return { type: event.type, label: 'Workflow finalizado', tone: 'success' };
        default:
            return { type: event.type, label: event.type || 'Evento', tone: 'neutral' };
    }
};

const toneClass = (tone?: TimelineItem['tone']) => {
    switch (tone) {
        case 'success':
            return 'text-emerald-600';
        case 'warning':
            return 'text-amber-600';
        case 'danger':
            return 'text-rose-600';
        case 'info':
            return 'text-blue-600';
        default:
            return 'text-muted-foreground';
    }
};

export function ProcessTimeline({ groups }: { groups: TimelineGroup[] }) {
    const normalizedGroups = useMemo(() => {
        return (groups || []).map((group) => {
            const items = (group.events || [])
                .map((ev) => buildLabel(ev))
                .slice(-12);
            return { title: group.title, items };
        });
    }, [groups]);

    if (!normalizedGroups.length) {
        return (
            <div className="rounded-2xl border border-outline/20 bg-white p-4">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Sparkles className="h-4 w-4" />
                    Aguardando eventos do pipeline.
                </div>
            </div>
        );
    }

    return (
        <div className="rounded-2xl border border-outline/20 bg-white p-4">
            <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold uppercase text-muted-foreground">Timeline</h3>
                <Badge variant="outline" className="text-[10px]">Ao vivo</Badge>
            </div>
            <div className="mt-3 space-y-4">
                {normalizedGroups.map((group) => (
                    <div key={group.title} className="space-y-2">
                        <div className="text-[11px] font-semibold text-foreground/80">{group.title}</div>
                        <div className="space-y-1">
                            {group.items.map((item, idx) => {
                                const Icon = iconForType(item.type);
                                return (
                                    <div key={`${item.type}-${idx}`} className="flex items-center gap-2 text-[11px]">
                                        <Icon className={`h-3.5 w-3.5 ${toneClass(item.tone)}`} />
                                        <span className="text-foreground/80">{item.label}</span>
                                        {item.meta && <span className="text-muted-foreground">{item.meta}</span>}
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
