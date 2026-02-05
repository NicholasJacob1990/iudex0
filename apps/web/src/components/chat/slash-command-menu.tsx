'use client';

import { useState, useEffect, useRef } from 'react';
import { Search, FileText, ChevronRight, Star, HelpCircle } from 'lucide-react';
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command';
import { PREDEFINED_PROMPTS, type PredefinedPrompt } from '@/data/prompts';
import type { CustomPrompt } from '@/components/dashboard/prompt-customization';
import { cn } from '@/lib/utils';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

import { Sparkles, Columns2, Box, Bot, Layers, Settings2 } from 'lucide-react';

type AnyPrompt = PredefinedPrompt | CustomPrompt;

export interface SystemCommand {
    id: string;
    category: 'Comandos do Sistema';
    name: string;
    description: string;
    action: string; // Identifier for the action
    icon?: any;
    tooltip?: string;
}

const SYSTEM_COMMANDS: SystemCommand[] = [
    {
        id: 'cmd-gpt',
        category: 'Comandos do Sistema',
        name: 'Mudar para GPT-5.2',
        description: 'Alterna o modelo ativo para GPT-5.2',
        action: 'set-model:gpt-5.2',
        icon: Bot
    },
    {
        id: 'cmd-claude',
        category: 'Comandos do Sistema',
        name: 'Mudar para Claude 3.5 Sonnet',
        description: 'Alterna o modelo ativo para Claude 3.5 Sonnet',
        action: 'set-model:claude-3-5-sonnet-20240620',
        icon: Bot
    },
    {
        id: 'cmd-gemini',
        category: 'Comandos do Sistema',
        name: 'Mudar para Gemini Pro',
        description: 'Alterna o modelo ativo para Gemini 1.5 Pro',
        action: 'set-model:gemini-1.5-pro-latest',
        icon: Bot
    },
    {
        id: 'cmd-multi',
        category: 'Comandos do Sistema',
        name: 'Ativar Modo Multi-Modelo',
        description: 'Ativa chat paralelo com 3 modelos',
        action: 'set-mode:multi-model',
        icon: Columns2
    },
    {
        id: 'cmd-standard',
        category: 'Comandos do Sistema',
        name: 'Ativar Modo Padrão',
        description: 'Volta para chat com um único modelo',
        action: 'set-mode:standard',
        icon: Box
    },
    {
        id: 'cmd-canvas-edit',
        category: 'Comandos do Sistema',
        name: 'Editar documento (Canvas)',
        description: 'Insere /canvas <instrução>',
        action: 'insert-text:/canvas ',
        icon: FileText,
        tooltip: 'Aplica a instrução ao documento inteiro.'
    },
    {
        id: 'cmd-canvas-append',
        category: 'Comandos do Sistema',
        name: 'Adicionar ao documento',
        description: 'Insere /canvas append <conteúdo>',
        action: 'insert-text:/canvas append ',
        icon: FileText,
        tooltip: 'Pede para anexar conteúdo ao final do documento.'
    },
    {
        id: 'cmd-canvas-replace',
        category: 'Comandos do Sistema',
        name: 'Substituir documento',
        description: 'Insere /canvas replace <instrução>',
        action: 'insert-text:/canvas replace ',
        icon: FileText,
        tooltip: 'Pede para reescrever o documento inteiro.'
    },
    {
        id: 'cmd-templates-on',
        category: 'Comandos do Sistema',
        name: 'Ativar modelos de peça (RAG)',
        description: 'Insere /templates on',
        action: 'insert-text:/templates on',
        icon: Layers,
        tooltip: 'Habilita o RAG de pecas_modelo para esta conversa.'
    },
    {
        id: 'cmd-templates-off',
        category: 'Comandos do Sistema',
        name: 'Desativar modelos de peça',
        description: 'Insere /templates off',
        action: 'insert-text:/templates off',
        icon: Box,
        tooltip: 'Desliga o uso de modelos de peça no chat.'
    },
    {
        id: 'cmd-template-id',
        category: 'Comandos do Sistema',
        name: 'Definir Template ID',
        description: 'Insere /template_id <id>',
        action: 'insert-text:/template_id ',
        icon: Settings2,
        tooltip: 'Molde da biblioteca com marcadores (minuta/CONTENT). Aceita @[Nome](id:lib).'
    },
    {
        id: 'cmd-template-doc',
        category: 'Comandos do Sistema',
        name: 'Definir Documento base (RAG)',
        description: 'Insere /template_doc <id>',
        action: 'insert-text:/template_doc ',
        icon: Settings2,
        tooltip: 'Usa um documento real como referência (não aplica marcadores). Aceita @[Nome](id:doc).'
    },
    {
        id: 'cmd-template-filters',
        category: 'Comandos do Sistema',
        name: 'Filtrar modelos do RAG',
        description: 'Insere /template_filters tipo= area= rito= clause=off',
        action: 'insert-text:/template_filters tipo= area= rito= clause=off',
        icon: Settings2,
        tooltip: 'Restringe modelos por tipo, área e rito. clause=on usa só clause bank.'
    },
    {
        id: 'cmd-template-clear',
        category: 'Comandos do Sistema',
        name: 'Limpar configs de template',
        description: 'Insere /template_clear',
        action: 'insert-text:/template_clear',
        icon: Box,
        tooltip: 'Remove template_id, template_doc e filtros do chat.'
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

    const handleSelect = (prompt: AnyPrompt | SystemCommand) => {
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
                                                    item.icon ? <item.icon className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />
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
                                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                    <span className="line-clamp-1">{item.description}</span>
                                                    {item.tooltip && (
                                                        <TooltipProvider>
                                                            <Tooltip>
                                                                <TooltipTrigger asChild>
                                                                    <button
                                                                        type="button"
                                                                        className="text-muted-foreground hover:text-foreground"
                                                                        onClick={(event) => event.stopPropagation()}
                                                                        onMouseDown={(event) => event.stopPropagation()}
                                                                    >
                                                                        <HelpCircle className="h-3.5 w-3.5" />
                                                                    </button>
                                                                </TooltipTrigger>
                                                                <TooltipContent side="right" className="max-w-xs text-xs">
                                                                    {item.tooltip}
                                                                </TooltipContent>
                                                            </Tooltip>
                                                        </TooltipProvider>
                                                    )}
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
