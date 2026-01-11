'use client';

import { Button } from '@/components/ui/button';
import {
    PenLine,
    MessageSquare,
    Columns,
    Maximize2,
    ChevronDown
} from 'lucide-react';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';

export type LayoutPreset = 'escrever' | 'debater' | 'padrao' | 'canvas';

interface LayoutPresetSelectorProps {
    currentPreset: LayoutPreset;
    onPresetChange: (preset: LayoutPreset) => void;
    className?: string;
}

const presets: { id: LayoutPreset; label: string; icon: typeof PenLine; description: string; proportions: string }[] = [
    {
        id: 'escrever',
        label: 'Escrever',
        icon: PenLine,
        description: 'Foco no documento (80% canvas)',
        proportions: '20/80'
    },
    {
        id: 'debater',
        label: 'Debater',
        icon: MessageSquare,
        description: 'Conversa e edição (50/50)',
        proportions: '50/50'
    },
    {
        id: 'padrao',
        label: 'Padrão',
        icon: Columns,
        description: 'Layout balanceado (35/65)',
        proportions: '35/65'
    },
    {
        id: 'canvas',
        label: 'Canvas',
        icon: Maximize2,
        description: 'Canvas expandido (chat mínimo visível)',
        proportions: '15/85'
    },
];

export function LayoutPresetSelector({
    currentPreset,
    onPresetChange,
    className,
}: LayoutPresetSelectorProps) {
    const current = presets.find(p => p.id === currentPreset) || presets[2];
    const CurrentIcon = current.icon;

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button
                    variant="ghost"
                    size="sm"
                    className={cn(
                        "h-8 gap-1.5 text-xs font-normal",
                        className
                    )}
                >
                    <CurrentIcon className="h-3.5 w-3.5" />
                    {current.label}
                    <span className="text-[10px] text-muted-foreground">({current.proportions})</span>
                    <ChevronDown className="h-3 w-3 opacity-50" />
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-[200px]">
                <DropdownMenuLabel className="text-xs">Layout do Canvas</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {presets.map((preset) => {
                    const Icon = preset.icon;
                    return (
                        <DropdownMenuItem
                            key={preset.id}
                            onClick={() => onPresetChange(preset.id)}
                            className={cn(
                                "flex flex-col items-start gap-1 cursor-pointer",
                                currentPreset === preset.id && "bg-primary/10"
                            )}
                        >
                            <div className="flex items-center gap-2">
                                <Icon className="h-4 w-4" />
                                <span className="font-medium">{preset.label}</span>
                                <span className="text-[10px] text-muted-foreground ml-auto">
                                    {preset.proportions}
                                </span>
                            </div>
                            <span className="text-[10px] text-muted-foreground pl-6">
                                {preset.description}
                            </span>
                        </DropdownMenuItem>
                    );
                })}
            </DropdownMenuContent>
        </DropdownMenu>
    );
}

// Helper function to get proportions from preset
export function getLayoutProportions(preset: LayoutPreset): {
    outline: number;
    chat: number;
    canvas: number;
    showOutline: boolean;
    showChat: boolean;
} {
    switch (preset) {
        case 'escrever':
            return { outline: 0, chat: 20, canvas: 80, showOutline: false, showChat: true };
        case 'debater':
            return { outline: 15, chat: 42, canvas: 43, showOutline: true, showChat: true };
        case 'padrao':
            return { outline: 15, chat: 30, canvas: 55, showOutline: true, showChat: true };
        case 'canvas':
            return { outline: 0, chat: 0, canvas: 100, showOutline: false, showChat: false };
        default:
            return { outline: 15, chat: 30, canvas: 55, showOutline: true, showChat: true };
    }
}

export default LayoutPresetSelector;
