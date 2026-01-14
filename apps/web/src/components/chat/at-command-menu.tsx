'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { Search, FileText, BookOpen, Scale, Link as LinkIcon, Mic, ArrowLeft, Loader2, Bot } from 'lucide-react';
import { Command, CommandEmpty, CommandGroup, CommandItem, CommandList } from '@/components/ui/command';
import { apiClient } from '@/lib/api-client';

interface AtCommandMenuProps {
    onSelect: (value: string, label: string) => void;
    onClose: () => void;
    position?: { top: number; left: number };
}

interface ContextOption {
    id: string;
    label: string;
    icon: any;
    description: string;
    hasSubmenu?: boolean;
}

const CONTEXT_OPTIONS: ContextOption[] = [
    { id: 'models', label: 'Modelos de IA', icon: Bot, description: 'Mencionar um modelo específico', hasSubmenu: true },
    { id: 'files', label: 'Arquivos', icon: FileText, description: 'Buscar PDFs e DOCX', hasSubmenu: true },
    { id: 'library', label: 'Biblioteca', icon: BookOpen, description: 'Buscar modelos e peças', hasSubmenu: true },
    { id: 'juris', label: 'Jurisprudência', icon: Scale, description: 'Buscar jurisprudência' },
    { id: 'link', label: 'Link', icon: LinkIcon, description: 'Adicionar URL da web' },
    { id: 'audio', label: 'Áudio', icon: Mic, description: 'Gravar ou enviar áudio' },
];

const AI_MODELS = [
    { id: 'gpt-5.2', name: 'GPT-5.2', description: 'OpenAI - Raciocínio avançado' },
    { id: 'gpt-5', name: 'GPT-5o', description: 'OpenAI - Rápido e versátil' },
    { id: 'claude-sonnet-4-5@20250929', name: 'Claude 4.5 Sonnet', description: 'Anthropic - Escrita excepcional' },
    { id: 'claude-opus-4-5@20251101', name: 'Claude 4.5 Opus', description: 'Anthropic - Análise profunda' },
    { id: 'gemini-3-pro', name: 'Gemini 1.5 Pro', description: 'Google - Contexto longo' },
    { id: 'gemini-3-flash', name: 'Gemini 1.5 Flash', description: 'Google - Muito rápido' },
    { id: 'grok-4', name: 'Grok 4', description: 'xAI - Raciocínio' },
    { id: 'grok-4-fast', name: 'Grok 4 Fast', description: 'xAI - Baixa latência' },
    { id: 'grok-4.1-fast', name: 'Grok 4.1 Fast', description: 'xAI - Baixa latência' },
    { id: 'llama-4', name: 'Llama 4', description: 'Meta - OpenRouter' },
];

export function AtCommandMenu({ onSelect, onClose, position }: AtCommandMenuProps) {
    const [search, setSearch] = useState('');
    const [activeCategory, setActiveCategory] = useState<string | null>(null);
    const [items, setItems] = useState<any[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const menuRef = useRef<HTMLDivElement>(null);

    const fetchItems = useCallback(async (query: string) => {
        setIsLoading(true);
        try {
            if (activeCategory === 'models') {
                // Local filtering for models
                const filtered = AI_MODELS.filter(m =>
                    m.name.toLowerCase().includes(query.toLowerCase()) ||
                    m.description.toLowerCase().includes(query.toLowerCase())
                );
                setItems(filtered);
            } else if (activeCategory === 'files') {
                const res = await apiClient.getDocuments(0, 10, query);
                setItems(res.documents);
            } else if (activeCategory === 'library') {
                const res = await apiClient.getLibraryItems(0, 10, query);
                setItems(res.items);
            }
        } catch (error) {
            console.error(error);
        } finally {
            setIsLoading(false);
        }
    }, [activeCategory]);

    // Debounce search for submenus
    useEffect(() => {
        if (!activeCategory) return;

        const timer = setTimeout(() => {
            fetchItems(search);
        }, 300);

        return () => clearTimeout(timer);
    }, [search, activeCategory, fetchItems]);

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
                onClose();
            }
        };

        const handleEscape = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                if (activeCategory) {
                    setActiveCategory(null);
                    setSearch('');
                } else {
                    onClose();
                }
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        document.addEventListener('keydown', handleEscape);

        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
            document.removeEventListener('keydown', handleEscape);
        };
    }, [onClose, activeCategory]);

    const handleSelectCategory = (option: ContextOption) => {
        if (option.hasSubmenu) {
            setActiveCategory(option.id);
            setSearch('');
            setItems([]);
            fetchItems('');
        } else {
            onSelect(option.id, option.label);
            onClose();
        }
    };

    const handleSelectItem = (item: any) => {
        // Formato: @[Nome](id:type)
        if (activeCategory === 'models') {
            // For models: @Claude or @GPT-5.2
            const format = `@${item.name}`;
            onSelect(format, item.name);
        } else {
            const format = `@[${item.name}](${item.id}:${activeCategory === 'files' ? 'doc' : 'lib'})`;
            onSelect(format, item.name);
        }
        onClose();
    };

    return (
        <div
            ref={menuRef}
            className="fixed z-50 w-[320px] animate-in fade-in slide-in-from-bottom-2"
            style={{
                top: position?.top ? `${position.top}px` : 'auto',
                left: position?.left ? `${position.left}px` : 'auto',
                bottom: !position?.top ? '120px' : 'auto',
            }}
        >
            <Command className="rounded-lg border border-border bg-background shadow-lg overflow-hidden">
                <div className="flex items-center border-b border-border px-3 bg-muted/30">
                    {activeCategory && (
                        <button
                            onClick={() => { setActiveCategory(null); setSearch(''); }}
                            className="mr-2 p-1 hover:bg-background rounded-md transition-colors"
                        >
                            <ArrowLeft className="h-4 w-4 text-muted-foreground" />
                        </button>
                    )}
                    {!activeCategory && <Search className="mr-2 h-4 w-4 shrink-0 opacity-50" />}

                    <input
                        className="flex h-10 w-full rounded-md bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50"
                        placeholder={activeCategory ? `Buscar em ${activeCategory === 'files' ? 'Arquivos' : 'Biblioteca'}...` : "Adicionar contexto..."}
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        autoFocus
                    />
                </div>

                <CommandList className="max-h-[300px] overflow-y-auto">
                    {/* Main Menu */}
                    {!activeCategory && (
                        <CommandGroup heading="Fontes de Contexto">
                            {CONTEXT_OPTIONS.filter(opt =>
                                opt.label.toLowerCase().includes(search.toLowerCase()) ||
                                opt.description.toLowerCase().includes(search.toLowerCase())
                            ).map((option) => (
                                <CommandItem
                                    key={option.id}
                                    value={option.id}
                                    onSelect={() => handleSelectCategory(option)}
                                    className="flex items-center gap-3 px-4 py-3 cursor-pointer aria-selected:bg-accent"
                                >
                                    <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary/10 text-primary flex-shrink-0">
                                        <option.icon className="h-4 w-4" />
                                    </div>
                                    <div className="flex flex-col">
                                        <span className="font-medium text-sm text-foreground">{option.label}</span>
                                        <span className="text-xs text-muted-foreground">{option.description}</span>
                                    </div>
                                </CommandItem>
                            ))}
                        </CommandGroup>
                    )}

                    {/* Submenu Results */}
                    {activeCategory && (
                        <div className="p-1">
                            {isLoading ? (
                                <div className="flex items-center justify-center py-8 text-muted-foreground">
                                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                                    Carregando...
                                </div>
                            ) : items.length === 0 ? (
                                <CommandEmpty className="py-6 text-center text-sm text-muted-foreground">
                                    Nenhum item encontrado.
                                </CommandEmpty>
                            ) : (
                                <CommandGroup heading="Resultados">
                                    {items.map((item) => (
                                        <CommandItem
                                            key={item.id}
                                            value={item.id}
                                            onSelect={() => handleSelectItem(item)}
                                            className="flex items-center gap-3 px-4 py-2 cursor-pointer aria-selected:bg-accent"
                                        >
                                            <div className="flex flex-col truncate">
                                                <span className="font-medium text-sm text-foreground truncate">{item.name}</span>
                                                <span className="text-xs text-muted-foreground truncate">
                                                    {new Date(item.created_at || Date.now()).toLocaleDateString()}
                                                </span>
                                            </div>
                                        </CommandItem>
                                    ))}
                                </CommandGroup>
                            )}
                        </div>
                    )}
                </CommandList>
            </Command>
        </div>
    );
}
