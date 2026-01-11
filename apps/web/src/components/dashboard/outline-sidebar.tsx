'use client';

import { useMemo } from 'react';
import { cn } from '@/lib/utils';
import { useCanvasStore } from '@/stores/canvas-store';
import {
    FileText,
    CheckCircle2,
    Clock,
    AlertCircle,
    ChevronRight,
    ChevronDown,
    Loader2
} from 'lucide-react';
import { Button } from '@/components/ui/button';

export type SectionStatus = 'pending' | 'generating' | 'done' | 'review' | 'error';

export interface OutlineSection {
    id: string;
    title: string;
    status: SectionStatus;
    level?: number; // 1 = h1, 2 = h2, etc.
}

interface OutlineSidebarProps {
    sections?: OutlineSection[];
    onSectionClick?: (sectionId: string) => void;
    collapsed?: boolean;
    onToggleCollapse?: () => void;
}

const statusConfig: Record<SectionStatus, { icon: typeof CheckCircle2; color: string; label: string }> = {
    pending: { icon: Clock, color: 'text-muted-foreground', label: 'Pendente' },
    generating: { icon: Loader2, color: 'text-blue-500 animate-spin', label: 'Gerando...' },
    done: { icon: CheckCircle2, color: 'text-green-500', label: 'Pronto' },
    review: { icon: AlertCircle, color: 'text-yellow-500', label: 'Precisa revisão' },
    error: { icon: AlertCircle, color: 'text-red-500', label: 'Erro' },
};

export function OutlineSidebar({
    sections = [],
    onSectionClick,
    collapsed = false,
    onToggleCollapse,
}: OutlineSidebarProps) {
    const { content } = useCanvasStore();

    // Auto-generate outline from content if sections not provided
    const displaySections = useMemo(() => {
        if (sections.length > 0) return sections;

        // Parse headings from content (simple regex approach)
        if (!content) return [];

        const headingRegex = /^(#{1,6})\s+(.+)$/gm;
        const parsed: OutlineSection[] = [];
        let match;
        let index = 0;

        while ((match = headingRegex.exec(content)) !== null) {
            parsed.push({
                id: `section-${index++}`,
                title: match[2].replace(/\*\*/g, '').slice(0, 50),
                status: 'done',
                level: match[1].length,
            });
        }

        return parsed;
    }, [content, sections]);

    if (collapsed) {
        return (
            <div className="flex flex-col items-center py-4 px-1 border-r border-outline/30 bg-muted/20">
                <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 mb-4"
                    onClick={onToggleCollapse}
                    title="Expandir outline"
                >
                    <ChevronRight className="h-4 w-4" />
                </Button>
                <FileText className="h-4 w-4 text-muted-foreground" />
                <span className="text-xs text-muted-foreground mt-2 writing-mode-vertical">
                    {displaySections.length} seções
                </span>
            </div>
        );
    }

    return (
        <div className="flex flex-col h-full border-r border-outline/30 bg-muted/10 w-full">
            {/* Header */}
            <div className="flex items-center justify-between px-3 py-2 border-b border-outline/20">
                <div className="flex items-center gap-2">
                    <FileText className="h-4 w-4 text-primary" />
                    <span className="text-xs font-semibold text-foreground uppercase tracking-wide">
                        Sumário
                    </span>
                </div>
                {onToggleCollapse && (
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6"
                        onClick={onToggleCollapse}
                    >
                        <ChevronDown className="h-3 w-3" />
                    </Button>
                )}
            </div>

            {/* Sections List */}
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
                {displaySections.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                        <FileText className="h-8 w-8 opacity-30 mb-2" />
                        <span className="text-xs text-center">
                            Nenhuma seção ainda.
                            <br />
                            Gere um documento.
                        </span>
                    </div>
                ) : (
                    displaySections.map((section) => {
                        const StatusIcon = statusConfig[section.status].icon;
                        const indent = (section.level || 1) - 1;

                        return (
                            <button
                                key={section.id}
                                onClick={() => onSectionClick?.(section.id)}
                                className={cn(
                                    'w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left text-xs transition-colors',
                                    'hover:bg-muted/50 focus:outline-none focus:ring-1 focus:ring-primary/50',
                                    section.status === 'generating' && 'bg-blue-50/50',
                                    section.status === 'review' && 'bg-yellow-50/50',
                                    section.status === 'error' && 'bg-red-50/50',
                                )}
                                style={{ paddingLeft: `${8 + indent * 12}px` }}
                                title={statusConfig[section.status].label}
                            >
                                <StatusIcon className={cn('h-3 w-3 flex-shrink-0', statusConfig[section.status].color)} />
                                <span className="truncate flex-1 text-foreground/90">
                                    {section.title}
                                </span>
                            </button>
                        );
                    })
                )}
            </div>

            {/* Footer Stats */}
            {displaySections.length > 0 && (
                <div className="px-3 py-2 border-t border-outline/20 bg-muted/20">
                    <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                        <span>{displaySections.filter(s => s.status === 'done').length}/{displaySections.length} prontas</span>
                        <span>{displaySections.filter(s => s.status === 'review').length} p/ revisar</span>
                    </div>
                </div>
            )}
        </div>
    );
}

export default OutlineSidebar;
