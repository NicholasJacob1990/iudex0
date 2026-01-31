'use client';

import { useState, KeyboardEvent, useEffect } from 'react';
import { useGraphStore } from '@/stores/graph-store';
import { useLexicalSearch } from '@/lib/use-graph';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import {
    Search,
    X,
    Scale,
    User,
    Trash2,
    Info,
    Loader2,
    Network,
    CheckCircle2,
} from 'lucide-react';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';

export function GraphLexicalSearch() {
    const {
        filters,
        addLexicalTerm,
        removeLexicalTerm,
        addLexicalAuthor,
        removeLexicalAuthor,
        addLexicalDevice,
        removeLexicalDevice,
        setLexicalMatchMode,
        clearLexicalFilters,
        setLexicalSearchMode,
    } = useGraphStore();

    const [termInput, setTermInput] = useState('');
    const [deviceInput, setDeviceInput] = useState('');
    const [authorInput, setAuthorInput] = useState('');
    const [showResults, setShowResults] = useState(false);

    // Call API for lexical search in Neo4j graph
    const lexicalSearchQuery = useLexicalSearch({
        terms: filters.lexicalTerms,
        devices: filters.lexicalDevices,
        authors: filters.lexicalAuthors,
        matchMode: filters.lexicalMatchMode,
        limit: 50,
    });

    const handleKeyDown = (
        e: KeyboardEvent<HTMLInputElement>,
        type: 'term' | 'device' | 'author'
    ) => {
        if (e.key === 'Enter' && e.currentTarget.value.trim()) {
            e.preventDefault();
            const value = e.currentTarget.value.trim();

            switch (type) {
                case 'term':
                    addLexicalTerm(value);
                    setTermInput('');
                    break;
                case 'device':
                    addLexicalDevice(value);
                    setDeviceInput('');
                    break;
                case 'author':
                    addLexicalAuthor(value);
                    setAuthorInput('');
                    break;
            }
            setShowResults(true);
        }
    };

    const totalFilters =
        filters.lexicalTerms.length +
        filters.lexicalAuthors.length +
        filters.lexicalDevices.length;

    // Auto-show results when filters change
    useEffect(() => {
        if (totalFilters > 0) {
            setShowResults(true);
        }
    }, [totalFilters]);

    const resultCount = lexicalSearchQuery.data?.length || 0;

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="p-4 border-b">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <h3 className="text-sm font-semibold">Pesquisa no Grafo</h3>
                        <TooltipProvider>
                            <Tooltip>
                                <TooltipTrigger>
                                    <Info className="h-3.5 w-3.5 text-muted-foreground" />
                                </TooltipTrigger>
                                <TooltipContent className="max-w-xs">
                                    <p className="text-xs">
                                        Busca entidades no grafo Neo4j por termos, dispositivos legais ou autores.
                                        Digite e pressione Enter para buscar.
                                    </p>
                                </TooltipContent>
                            </Tooltip>
                        </TooltipProvider>
                    </div>
                    {totalFilters > 0 && (
                        <div className="flex items-center gap-2">
                            {lexicalSearchQuery.isLoading && (
                                <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                            )}
                            <Badge variant="secondary" className="text-xs">
                                {resultCount} resultado{resultCount !== 1 ? 's' : ''}
                            </Badge>
                        </div>
                    )}
                </div>
            </div>

            {/* Filters */}
            <div className="flex-1 overflow-auto p-4 space-y-5">
                {/* Search Mode */}
                <div className="space-y-3">
                    <Label className="text-xs font-medium">Modo de Pesquisa</Label>
                    <div className="flex gap-2">
                        <Button
                            variant={filters.lexicalSearchMode === 'entities' ? 'default' : 'outline'}
                            size="sm"
                            className={cn(
                                "flex-1 text-xs h-8",
                                filters.lexicalSearchMode === 'entities' && "bg-slate-900 hover:bg-slate-800"
                            )}
                            onClick={() => setLexicalSearchMode('entities')}
                        >
                            Entidades (Neo4j)
                        </Button>
                        <Button
                            variant={filters.lexicalSearchMode === 'content' ? 'default' : 'outline'}
                            size="sm"
                            className={cn(
                                "flex-1 text-xs h-8",
                                filters.lexicalSearchMode === 'content' && "bg-slate-900 hover:bg-slate-800"
                            )}
                            onClick={() => setLexicalSearchMode('content')}
                        >
                            Conteudo (BM25)
                        </Button>
                    </div>
                    <p className="text-[10px] text-muted-foreground leading-snug">
                        Entidades: busca nomes/citacoes no grafo. Conteudo: busca trechos e deriva entidades.
                    </p>
                </div>

                {/* Terms/Phrases */}
                <div className="space-y-2">
                    <Label className="text-xs font-medium flex items-center gap-2">
                        <Search className="h-3.5 w-3.5 text-muted-foreground" />
                        Termos e Frases
                    </Label>
                    <Input
                        placeholder="Digite e pressione Enter..."
                        className="h-9 text-sm"
                        value={termInput}
                        onChange={(e) => setTermInput(e.target.value)}
                        onKeyDown={(e) => handleKeyDown(e, 'term')}
                    />
                    {filters.lexicalTerms.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mt-2">
                            {filters.lexicalTerms.map((term) => (
                                <Badge
                                    key={term}
                                    variant="secondary"
                                    className="text-xs pr-1 bg-blue-50 text-blue-700 hover:bg-blue-100"
                                >
                                    {term}
                                    <button
                                        onClick={() => removeLexicalTerm(term)}
                                        className="ml-1.5 hover:text-destructive"
                                    >
                                        <X className="h-3 w-3" />
                                    </button>
                                </Badge>
                            ))}
                        </div>
                    )}
                </div>

                {/* Legal Devices */}
                <div className="space-y-2">
                    <Label className="text-xs font-medium flex items-center gap-2">
                        <Scale className="h-3.5 w-3.5 text-emerald-600" />
                        Dispositivos Legais
                    </Label>
                    <Input
                        placeholder="Ex: Art. 5º CF, Lei 8.666, Súmula 331..."
                        className="h-9 text-sm"
                        value={deviceInput}
                        onChange={(e) => setDeviceInput(e.target.value)}
                        onKeyDown={(e) => handleKeyDown(e, 'device')}
                    />
                    {filters.lexicalDevices.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mt-2">
                            {filters.lexicalDevices.map((device) => (
                                <Badge
                                    key={device}
                                    variant="secondary"
                                    className="text-xs pr-1 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                                >
                                    <Scale className="h-3 w-3 mr-1" />
                                    {device}
                                    <button
                                        onClick={() => removeLexicalDevice(device)}
                                        className="ml-1.5 hover:text-destructive"
                                    >
                                        <X className="h-3 w-3" />
                                    </button>
                                </Badge>
                            ))}
                        </div>
                    )}
                </div>

                {/* Authors/Tribunals */}
                <div className="space-y-2">
                    <Label className="text-xs font-medium flex items-center gap-2">
                        <User className="h-3.5 w-3.5 text-violet-600" />
                        Autores / Tribunais
                    </Label>
                    <Input
                        placeholder="Ex: STF, Min. Barroso, Nelson Nery..."
                        className="h-9 text-sm"
                        value={authorInput}
                        onChange={(e) => setAuthorInput(e.target.value)}
                        onKeyDown={(e) => handleKeyDown(e, 'author')}
                    />
                    {filters.lexicalAuthors.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mt-2">
                            {filters.lexicalAuthors.map((author) => (
                                <Badge
                                    key={author}
                                    variant="secondary"
                                    className="text-xs pr-1 bg-violet-50 text-violet-700 hover:bg-violet-100"
                                >
                                    <User className="h-3 w-3 mr-1" />
                                    {author}
                                    <button
                                        onClick={() => removeLexicalAuthor(author)}
                                        className="ml-1.5 hover:text-destructive"
                                    >
                                        <X className="h-3 w-3" />
                                    </button>
                                </Badge>
                            ))}
                        </div>
                    )}
                </div>

                {/* Match Mode */}
                <div className="space-y-3 pt-2 border-t">
                    <Label className="text-xs font-medium">Modo de Correspondência</Label>
                    <div className="flex gap-2">
                        <Button
                            variant={filters.lexicalMatchMode === 'any' ? 'default' : 'outline'}
                            size="sm"
                            className={cn(
                                "flex-1 text-xs h-8",
                                filters.lexicalMatchMode === 'any' && "bg-blue-600 hover:bg-blue-700"
                            )}
                            onClick={() => setLexicalMatchMode('any')}
                        >
                            Qualquer (OU)
                        </Button>
                        <Button
                            variant={filters.lexicalMatchMode === 'all' ? 'default' : 'outline'}
                            size="sm"
                            className={cn(
                                "flex-1 text-xs h-8",
                                filters.lexicalMatchMode === 'all' && "bg-blue-600 hover:bg-blue-700"
                            )}
                            onClick={() => setLexicalMatchMode('all')}
                        >
                            Todos (E)
                        </Button>
                    </div>
                </div>

                {/* Search Results */}
                {showResults && totalFilters > 0 && (
                    <div className="space-y-3 pt-2 border-t">
                        <div className="flex items-center justify-between">
                            <Label className="text-xs font-medium flex items-center gap-2">
                                <Network className="h-3.5 w-3.5 text-blue-600" />
                                Entidades Encontradas
                            </Label>
                            <Button
                                variant="ghost"
                                size="sm"
                                className="h-6 text-xs"
                                onClick={() => setShowResults(false)}
                            >
                                Ocultar
                            </Button>
                        </div>

                        {lexicalSearchQuery.isLoading ? (
                            <div className="flex items-center justify-center py-4">
                                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                            </div>
                        ) : lexicalSearchQuery.error ? (
                            <p className="text-xs text-destructive text-center py-4">
                                Erro ao buscar entidades
                            </p>
                        ) : resultCount === 0 ? (
                            <p className="text-xs text-muted-foreground text-center py-4">
                                Nenhuma entidade encontrada
                            </p>
                        ) : (
                            <ScrollArea className="h-[200px]">
                                <div className="space-y-1">
                                    {lexicalSearchQuery.data?.map((entity) => (
                                        <div
                                            key={entity.id}
                                            className="flex items-center justify-between p-2 rounded-lg hover:bg-muted/50 text-xs"
                                        >
                                            <div className="flex items-center gap-2 min-w-0">
                                                <div
                                                    className={cn(
                                                        "w-2 h-2 rounded-full flex-shrink-0",
                                                        entity.group === 'legislacao' && "bg-blue-500",
                                                        entity.group === 'jurisprudencia' && "bg-violet-500",
                                                        entity.group === 'doutrina' && "bg-emerald-500",
                                                        !['legislacao', 'jurisprudencia', 'doutrina'].includes(entity.group) && "bg-gray-400"
                                                    )}
                                                />
                                                <span className="truncate">{entity.name}</span>
                                            </div>
                                            <div className="flex items-center gap-1 flex-shrink-0">
                                                <Badge variant="outline" className="text-[10px] px-1">
                                                    {entity.type}
                                                </Badge>
                                                {entity.mention_count > 0 && (
                                                    <Badge variant="secondary" className="text-[10px] px-1">
                                                        {entity.mention_count}x
                                                    </Badge>
                                                )}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </ScrollArea>
                        )}
                    </div>
                )}
            </div>

            {/* Footer */}
            {totalFilters > 0 && (
                <div className="p-4 border-t">
                    <Button
                        variant="outline"
                        size="sm"
                        className="w-full text-xs"
                        onClick={() => {
                            clearLexicalFilters();
                            setShowResults(false);
                        }}
                    >
                        <Trash2 className="h-3.5 w-3.5 mr-2" />
                        Limpar todos os filtros
                    </Button>
                </div>
            )}
        </div>
    );
}
