'use client';

import { useState } from 'react';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { AlertTriangle, Check, X, Diff, ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DiffConfirmDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    title?: string;
    description?: string;
    original: string;
    replacement: string;
    affectedSection?: string;
    changeStats?: {
        paragraphsChanged: number;
        totalParagraphs: number;
        wordsAdded: number;
        wordsRemoved: number;
    };
    onAccept: () => void;
    onReject: () => void;
    onAcceptPartial?: () => void; // Future: partial accept
}

export function DiffConfirmDialog({
    open,
    onOpenChange,
    title = 'Confirmar Alteração',
    description,
    original,
    replacement,
    affectedSection,
    changeStats,
    onAccept,
    onReject,
    onAcceptPartial,
}: DiffConfirmDialogProps) {
    const [showFullDiff, setShowFullDiff] = useState(false);

    // Calculate change percentage
    const changePercentage = changeStats
        ? Math.round((changeStats.paragraphsChanged / changeStats.totalParagraphs) * 100)
        : 0;
    const isLargeChange = changePercentage > 50;

    // Simple word diff for display
    const renderDiff = () => {
        const maxPreview = 300;
        const originalPreview = original.slice(0, maxPreview);
        const replacementPreview = replacement.slice(0, maxPreview);

        return (
            <div className="space-y-3">
                {/* Original (red) */}
                <div className="rounded-md border border-red-200 bg-red-50/50 p-3">
                    <div className="flex items-center gap-2 mb-2 text-xs font-medium text-red-700">
                        <span className="inline-flex h-5 w-5 items-center justify-center rounded bg-red-100 text-red-600">−</span>
                        Texto Original
                    </div>
                    <p className="text-sm text-red-900 line-through opacity-70">
                        {originalPreview}{original.length > maxPreview && '...'}
                    </p>
                </div>

                {/* Replacement (green) */}
                <div className="rounded-md border border-green-200 bg-green-50/50 p-3">
                    <div className="flex items-center gap-2 mb-2 text-xs font-medium text-green-700">
                        <span className="inline-flex h-5 w-5 items-center justify-center rounded bg-green-100 text-green-600">+</span>
                        Novo Texto
                    </div>
                    <p className="text-sm text-green-900">
                        {replacementPreview}{replacement.length > maxPreview && '...'}
                    </p>
                </div>
            </div>
        );
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[600px]">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        {isLargeChange && <AlertTriangle className="h-5 w-5 text-orange-500" />}
                        <Diff className="h-5 w-5 text-primary" />
                        {title}
                    </DialogTitle>
                    <DialogDescription>
                        {description || 'A IA propôs as seguintes alterações no documento. Revise antes de aplicar.'}
                    </DialogDescription>
                </DialogHeader>

                {/* Change Stats */}
                {changeStats && (
                    <div className="flex items-center gap-4 p-3 rounded-lg bg-muted/50 text-sm">
                        {affectedSection && (
                            <span className="text-muted-foreground">
                                📍 <strong className="text-foreground">{affectedSection}</strong>
                            </span>
                        )}
                        <span className="text-muted-foreground">
                            {changeStats.paragraphsChanged}/{changeStats.totalParagraphs} parágrafos alterados
                        </span>
                        {isLargeChange && (
                            <span className="inline-flex items-center gap-1 rounded-full bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-700">
                                <AlertTriangle className="h-3 w-3" />
                                {changePercentage}% do documento
                            </span>
                        )}
                    </div>
                )}

                {/* Large Change Warning */}
                {isLargeChange && (
                    <div className="flex items-start gap-3 p-3 rounded-lg border border-orange-200 bg-orange-50">
                        <AlertTriangle className="h-5 w-5 text-orange-500 flex-shrink-0 mt-0.5" />
                        <div className="text-sm">
                            <p className="font-medium text-orange-800">Alteração Significativa Detectada</p>
                            <p className="text-orange-700 mt-1">
                                Esta ação irá modificar mais de 50% do documento. Recomendamos revisar com atenção antes de aplicar.
                            </p>
                        </div>
                    </div>
                )}

                {/* Diff Preview */}
                <div className="max-h-[300px] overflow-y-auto">
                    {renderDiff()}
                </div>

                {/* Toggle full diff */}
                {(original.length > 300 || replacement.length > 300) && (
                    <Button
                        variant="ghost"
                        size="sm"
                        className="w-full"
                        onClick={() => setShowFullDiff(!showFullDiff)}
                    >
                        {showFullDiff ? (
                            <>
                                <ChevronUp className="h-4 w-4 mr-1" />
                                Mostrar menos
                            </>
                        ) : (
                            <>
                                <ChevronDown className="h-4 w-4 mr-1" />
                                Ver alteração completa
                            </>
                        )}
                    </Button>
                )}

                <DialogFooter className="gap-2 sm:gap-0">
                    <Button variant="outline" onClick={onReject}>
                        <X className="h-4 w-4 mr-1" />
                        Rejeitar
                    </Button>
                    {onAcceptPartial && (
                        <Button variant="secondary" onClick={onAcceptPartial}>
                            Aplicar Parcialmente
                        </Button>
                    )}
                    <Button
                        onClick={onAccept}
                        className={cn(
                            isLargeChange && 'bg-orange-600 hover:bg-orange-700'
                        )}
                    >
                        <Check className="h-4 w-4 mr-1" />
                        {isLargeChange ? 'Aplicar Mesmo Assim' : 'Aplicar'}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

export default DiffConfirmDialog;
