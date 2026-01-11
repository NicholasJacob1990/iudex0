'use client';

import { useState, useEffect, useRef } from 'react';
import { Search, FileText, ChevronRight, Star } from 'lucide-react';
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command';
import { PREDEFINED_PROMPTS, type PredefinedPrompt } from '@/data/prompts';
import type { CustomPrompt } from '@/components/dashboard/prompt-customization';
import { cn } from '@/lib/utils';

import { Zap, Scale, Box } from 'lucide-react';

type AnyPrompt = PredefinedPrompt | CustomPrompt;

export interface SystemCommand {
    id: string;
    category: 'Comandos do Sistema';
    name: string;
    description: string;
    action: string; // Identifier for the action
    icon?: any;
}

const SYSTEM_COMMANDS: SystemCommand[] = [
    {
        id: 'cmd-gpt',
        category: 'Comandos do Sistema',
        name: 'Mudar para GPT-5.2',
        description: 'Alterna o modelo ativo para GPT-5.2',
        action: 'set-model:gpt-5.2',
        icon: Zap
    },
    {
        id: 'cmd-claude',
        category: 'Comandos do Sistema',
        name: 'Mudar para Claude 3.5 Sonnet',
        description: 'Alterna o modelo ativo para Claude 3.5 Sonnet',
        action: 'set-model:claude-3-5-sonnet-20240620',
        icon: Zap
    },
    {
        id: 'cmd-gemini',
        category: 'Comandos do Sistema',
        name: 'Mudar para Gemini Pro',
        description: 'Alterna o modelo ativo para Gemini 1.5 Pro',
        action: 'set-model:gemini-1.5-pro-latest',
        icon: Zap
    },
    {
        id: 'cmd-multi',
        category: 'Comandos do Sistema',
        name: 'Ativar Modo Multi-Modelo',
        description: 'Ativa chat paralelo com 3 modelos',
        action: 'set-mode:multi-model',
        icon: Scale
    },
    {
        id: 'cmd-standard',
        category: 'Comandos do Sistema',
        name: 'Ativar Modo Padrão',
        description: 'Volta para chat com um único modelo',
        action: 'set-mode:standard',
        icon: Box
    }
];


interface SlashCommandMenuProps {
    onSelect: (item: AnyPrompt | SystemCommand) => void;
    onClose: () => void;
    position?: { top: number; left: number };
    prompts?: AnyPrompt[];
}

export function SlashCommandMenu({ onSelect, onClose, position }: SlashCommandMenuProps) {
    const [search, setSearch] = useState('');
    const [customPrompts, setCustomPrompts] = useState<CustomPrompt[]>([]);
    const menuRef = useRef<HTMLDivElement>(null);

    // Load custom prompts from localStorage
    useEffect(() => {
        const stored = localStorage.getItem('iudex_custom_prompts');
        if (stored) {
            try {
                setCustomPrompts(JSON.parse(stored));
            } catch (e) {
                console.error('Failed to load custom prompts:', e);
            }
        }
    }, []);

    // Merge predefined, custom prompts AND system commands
    const allItems: (AnyPrompt | SystemCommand)[] = [...SYSTEM_COMMANDS, ...PREDEFINED_PROMPTS, ...customPrompts];

    // Group items by category
    const groupedItems = allItems.reduce((acc, item) => {
        if (!acc[item.category]) {
            acc[item.category] = [];
        }
        acc[item.category].push(item);
        return acc;
    }, {} as Record<string, (AnyPrompt | SystemCommand)[]>);

    // Close on click outside
    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
                onClose();
            }
        };

        const handleEscape = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                onClose();
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        document.addEventListener('keydown', handleEscape);

        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
            document.removeEventListener('keydown', handleEscape);
        };
    }, [onClose]);

    const handleSelect = (prompt: PredefinedPrompt) => {
        onSelect(prompt);
        onClose();
    };

    return (
        <div
            ref={menuRef}
            className="fixed z-50 w-[500px] animate-in fade-in slide-in-from-bottom-2"
            style={{
                top: position?.top ? `${position.top}px` : 'auto',
                left: position?.left ? `${position.left}px` : 'auto',
                bottom: !position?.top ? '120px' : 'auto',
            }}
        >
            <Command className="rounded-lg border border-border bg-background shadow-lg">
                <div className="flex items-center border-b border-border px-3">
                    <Search className="mr-2 h-4 w-4 shrink-0 opacity-50" />
                    <input
                        className="flex h-10 w-full rounded-md bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50"
                        placeholder="Buscar prompts..."
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        autoFocus
                    />
                </div>

                <CommandList className="max-h-[400px] overflow-y-auto">
                    <CommandEmpty className="py-6 text-center text-sm text-muted-foreground">
                        Nenhum prompt encontrado.
                    </CommandEmpty>

                    {Object.entries(groupedItems).map(([category, items]) => {
                        const filteredItems = search
                            ? items.filter(
                                (p: any) =>
                                    p.name.toLowerCase().includes(search.toLowerCase()) ||
                                    p.description.toLowerCase().includes(search.toLowerCase())
                            )
                            : items;

                        if (filteredItems.length === 0) return null;

                        return (
                            <CommandGroup key={category} heading={category}>
                                {filteredItems.map((item: any) => (
                                    <CommandItem
                                        key={item.id}
                                        value={item.id}
                                        onSelect={() => handleSelect(item)}
                                        className="flex items-center justify-between px-4 py-3 cursor-pointer"
                                    >
                                        <div className="flex items-start gap-3 flex-1 overflow-hidden">
                                            <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-md bg-primary/10 text-primary flex-shrink-0">
                                                {item.category === 'Comandos do Sistema' ? (
                                                    item.icon ? <item.icon className="h-4 w-4" /> : <Zap className="h-4 w-4" />
                                                ) : ('isCustom' in item && item.isCustom) ? (
                                                    <Star className="h-4 w-4 fill-current" />
                                                ) : (
                                                    <FileText className="h-4 w-4" />
                                                )}
                                            </div>
                                            <div className="flex-1 overflow-hidden">
                                                <div className="flex items-center gap-2">
                                                    <span className="font-medium text-sm text-foreground">{item.name}</span>
                                                    {('isCustom' in item && item.isCustom) && (
                                                        <span className="rounded-md bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-600">
                                                            Personalizado
                                                        </span>
                                                    )}
                                                    {item.category === 'Comandos do Sistema' && (
                                                        <span className="rounded-md bg-indigo-500/10 px-1.5 py-0.5 text-[10px] font-medium text-indigo-600">
                                                            Comando
                                                        </span>
                                                    )}
                                                </div>
                                                <div className="text-xs text-muted-foreground line-clamp-1">
                                                    {item.description}
                                                </div>
                                            </div>
                                        </div>
                                        <ChevronRight className="h-4 w-4 text-muted-foreground flex-shrink-0 ml-2" />
                                    </CommandItem>
                                ))}
                            </CommandGroup>
                        );
                    })}
                </CommandList>

                <div className="border-t border-border bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
                    <div className="flex items-center justify-between">
                        <span>Use as setas ↑↓ para navegar</span>
                        <span>
                            <kbd className="rounded bg-background px-1.5 py-0.5 text-[10px] font-medium">Enter</kbd> para
                            selecionar
                        </span>
                    </div>
                </div>
            </Command>
        </div>
    );
}
