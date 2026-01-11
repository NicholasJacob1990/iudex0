'use client';

import { useCanvasStore } from '@/stores/canvas-store';
import { FileText, History, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';

interface DocumentVersionBadgeProps {
    documentName?: string;
    className?: string;
}

export function DocumentVersionBadge({
    documentName = 'Documento',
    className,
}: DocumentVersionBadgeProps) {
    const { contentHistory, historyIndex, pendingSuggestions } = useCanvasStore();

    const versionNumber = historyIndex + 1;
    const totalVersions = contentHistory.length;
    const hasPendingSuggestions = pendingSuggestions.length > 0;
    const lastAction = contentHistory[historyIndex]?.label || 'Versão inicial';
    const lastTimestamp = contentHistory[historyIndex]?.timestamp;

    const formatTime = (ts: number) => {
        const date = new Date(ts);
        return date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    };

    return (
        <TooltipProvider>
            <Tooltip>
                <TooltipTrigger asChild>
                    <div
                        className={cn(
                            'inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors',
                            hasPendingSuggestions
                                ? 'border-orange-200 bg-orange-50 text-orange-700'
                                : 'border-outline/30 bg-muted/50 text-muted-foreground hover:bg-muted',
                            className
                        )}
                    >
                        <FileText className="h-3.5 w-3.5" />
                        <span className="truncate max-w-[120px]">{documentName}</span>
                        <span className="text-[10px] opacity-70">|</span>
                        <div className="flex items-center gap-1">
                            <History className="h-3 w-3" />
                            <span>v{versionNumber}/{totalVersions || 1}</span>
                        </div>
                        {hasPendingSuggestions && (
                            <>
                                <span className="text-[10px] opacity-70">|</span>
                                <div className="flex items-center gap-1 text-orange-600">
                                    <AlertCircle className="h-3 w-3" />
                                    <span>{pendingSuggestions.length} pendente{pendingSuggestions.length > 1 ? 's' : ''}</span>
                                </div>
                            </>
                        )}
                    </div>
                </TooltipTrigger>
                <TooltipContent className="max-w-[250px]">
                    <div className="space-y-1 text-xs">
                        <p className="font-medium">Documento Ativo</p>
                        <p><strong>Nome:</strong> {documentName}</p>
                        <p><strong>Versão:</strong> {versionNumber} de {totalVersions || 1}</p>
                        {lastAction && <p><strong>Última ação:</strong> {lastAction}</p>}
                        {lastTimestamp && <p><strong>Horário:</strong> {formatTime(lastTimestamp)}</p>}
                        {hasPendingSuggestions && (
                            <p className="text-orange-600 mt-2">
                                ⚠️ {pendingSuggestions.length} sugestão(ões) aguardando aprovação
                            </p>
                        )}
                    </div>
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}

export default DocumentVersionBadge;
