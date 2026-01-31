'use client';

import { useState, useEffect, useCallback } from 'react';
import { useGraphStore } from '@/stores/graph-store';
import { apiClient } from '@/lib/api-client';
import { useAddFromRAG } from '@/lib/use-graph';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import {
    Search,
    FileText,
    Folder,
    BookOpen,
    Scale,
    Gavel,
    Loader2,
    X,
    Network,
    Plus,
} from 'lucide-react';

interface DocumentItem {
    id: string;
    title: string;
    filename?: string;
    status?: string;
    created_at?: string;
}

interface CaseItem {
    id: string;
    title: string;
    number?: string;
    status?: string;
}

interface LibraryItem {
    id: string;
    name: string;
    type: string;
    description?: string;
}

export function GraphMaterialSelector() {
    const {
        filters,
        addDocument,
        removeDocument,
        addCase,
        removeCase,
        toggleFilterByMaterials,
    } = useGraphStore();

    const [activeTab, setActiveTab] = useState('documents');
    const [searchQuery, setSearchQuery] = useState('');

    // Data states
    const [documents, setDocuments] = useState<DocumentItem[]>([]);
    const [cases, setCases] = useState<CaseItem[]>([]);
    const [libraryItems, setLibraryItems] = useState<LibraryItem[]>([]);

    // Loading states
    const [loadingDocs, setLoadingDocs] = useState(false);
    const [loadingCases, setLoadingCases] = useState(false);
    const [loadingLibrary, setLoadingLibrary] = useState(false);

    // Load documents
    const loadDocuments = useCallback(async () => {
        setLoadingDocs(true);
        try {
            const response = await apiClient.getDocuments(0, 50, searchQuery || undefined);
            setDocuments(response.documents || []);
        } catch (error) {
            console.error('Failed to load documents:', error);
        } finally {
            setLoadingDocs(false);
        }
    }, [searchQuery]);

    // Load cases
    const loadCases = useCallback(async () => {
        setLoadingCases(true);
        try {
            const response = await apiClient.getCases(0, 50);
            setCases(response.cases || []);
        } catch (error) {
            console.error('Failed to load cases:', error);
        } finally {
            setLoadingCases(false);
        }
    }, []);

    // Load library items
    const loadLibraryItems = useCallback(async () => {
        setLoadingLibrary(true);
        try {
            const response = await apiClient.getLibraryItems(0, 50, searchQuery || undefined);
            setLibraryItems(response.items || []);
        } catch (error) {
            console.error('Failed to load library:', error);
        } finally {
            setLoadingLibrary(false);
        }
    }, [searchQuery]);

    // Load data on tab change
    useEffect(() => {
        if (activeTab === 'documents') {
            loadDocuments();
        } else if (activeTab === 'cases') {
            loadCases();
        } else if (activeTab === 'library') {
            loadLibraryItems();
        }
    }, [activeTab, loadDocuments, loadCases, loadLibraryItems]);

    // Reload on search
    useEffect(() => {
        const timeout = setTimeout(() => {
            if (activeTab === 'documents') loadDocuments();
            else if (activeTab === 'library') loadLibraryItems();
        }, 300);
        return () => clearTimeout(timeout);
    }, [searchQuery, activeTab, loadDocuments, loadLibraryItems]);

    const totalSelected = filters.selectedDocuments.length + filters.selectedCases.length;

    const handleDocumentToggle = (docId: string) => {
        if (filters.selectedDocuments.includes(docId)) {
            removeDocument(docId);
        } else {
            addDocument(docId);
        }
    };

    const handleCaseToggle = (caseId: string) => {
        if (filters.selectedCases.includes(caseId)) {
            removeCase(caseId);
        } else {
            addCase(caseId);
        }
    };

    // Mutation to add entities from selected documents/cases to graph
    const addFromRAGMutation = useAddFromRAG();

    const handleAddToGraph = async () => {
        if (totalSelected === 0) return;

        try {
            const result = await addFromRAGMutation.mutateAsync({
                documentIds: filters.selectedDocuments,
                caseIds: filters.selectedCases,
                extractSemantic: true,
            });

            toast.success(
                `Adicionado ao grafo: ${result.entities_added} novas entidades, ${result.relationships_created} relações`,
                {
                    description: `Processados ${result.documents_processed} documentos, ${result.chunks_processed} trechos`
                }
            );
        } catch (error) {
            toast.error('Erro ao adicionar ao grafo', {
                description: error instanceof Error ? error.message : 'Tente novamente'
            });
        }
    };

    return (
        <div className="flex flex-col h-full">
            {/* Header with filter toggle */}
            <div className="p-4 border-b space-y-3">
                <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold">Materiais</h3>
                    {totalSelected > 0 && (
                        <Badge variant="secondary" className="text-xs">
                            {totalSelected} selecionado{totalSelected > 1 ? 's' : ''}
                        </Badge>
                    )}
                </div>

                <div className="flex items-center justify-between">
                    <Label htmlFor="filter-by-materials" className="text-xs text-muted-foreground">
                        Filtrar grafo por materiais
                    </Label>
                    <Switch
                        id="filter-by-materials"
                        checked={filters.filterByMaterials}
                        onCheckedChange={toggleFilterByMaterials}
                        disabled={totalSelected === 0}
                    />
                </div>

                {/* Search */}
                <div className="relative">
                    <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                        placeholder="Buscar..."
                        className="pl-9 h-9 text-sm"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                    />
                </div>
            </div>

            {/* Tabs */}
            <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col">
                <TabsList className="mx-4 mt-2 grid w-auto grid-cols-3">
                    <TabsTrigger value="documents" className="text-xs">
                        <FileText className="h-3.5 w-3.5 mr-1" />
                        Docs
                    </TabsTrigger>
                    <TabsTrigger value="cases" className="text-xs">
                        <Folder className="h-3.5 w-3.5 mr-1" />
                        Casos
                    </TabsTrigger>
                    <TabsTrigger value="library" className="text-xs">
                        <BookOpen className="h-3.5 w-3.5 mr-1" />
                        Biblioteca
                    </TabsTrigger>
                </TabsList>

                {/* Documents Tab */}
                <TabsContent value="documents" className="flex-1 mt-0">
                    <ScrollArea className="h-[300px]">
                        <div className="p-4 space-y-2">
                            {loadingDocs ? (
                                <div className="flex items-center justify-center py-8">
                                    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                                </div>
                            ) : documents.length === 0 ? (
                                <p className="text-sm text-muted-foreground text-center py-8">
                                    Nenhum documento encontrado
                                </p>
                            ) : (
                                documents.map((doc) => (
                                    <div
                                        key={doc.id}
                                        className="flex items-start gap-3 p-2 rounded-lg hover:bg-muted/50 cursor-pointer"
                                        onClick={() => handleDocumentToggle(doc.id)}
                                    >
                                        <Checkbox
                                            checked={filters.selectedDocuments.includes(doc.id)}
                                            onCheckedChange={() => handleDocumentToggle(doc.id)}
                                            onClick={(e) => e.stopPropagation()}
                                        />
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm font-medium truncate">
                                                {doc.title || doc.filename || 'Sem título'}
                                            </p>
                                            {doc.status && (
                                                <Badge variant="outline" className="text-[10px] mt-1">
                                                    {doc.status}
                                                </Badge>
                                            )}
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    </ScrollArea>
                </TabsContent>

                {/* Cases Tab */}
                <TabsContent value="cases" className="flex-1 mt-0">
                    <ScrollArea className="h-[300px]">
                        <div className="p-4 space-y-2">
                            {loadingCases ? (
                                <div className="flex items-center justify-center py-8">
                                    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                                </div>
                            ) : cases.length === 0 ? (
                                <p className="text-sm text-muted-foreground text-center py-8">
                                    Nenhum caso encontrado
                                </p>
                            ) : (
                                cases.map((caseItem) => (
                                    <div
                                        key={caseItem.id}
                                        className="flex items-start gap-3 p-2 rounded-lg hover:bg-muted/50 cursor-pointer"
                                        onClick={() => handleCaseToggle(caseItem.id)}
                                    >
                                        <Checkbox
                                            checked={filters.selectedCases.includes(caseItem.id)}
                                            onCheckedChange={() => handleCaseToggle(caseItem.id)}
                                            onClick={(e) => e.stopPropagation()}
                                        />
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm font-medium truncate">
                                                {caseItem.title || 'Caso sem título'}
                                            </p>
                                            {caseItem.number && (
                                                <p className="text-xs text-muted-foreground truncate">
                                                    {caseItem.number}
                                                </p>
                                            )}
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    </ScrollArea>
                </TabsContent>

                {/* Library Tab */}
                <TabsContent value="library" className="flex-1 mt-0">
                    <ScrollArea className="h-[300px]">
                        <div className="p-4 space-y-2">
                            {loadingLibrary ? (
                                <div className="flex items-center justify-center py-8">
                                    <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                                </div>
                            ) : libraryItems.length === 0 ? (
                                <p className="text-sm text-muted-foreground text-center py-8">
                                    Nenhum item de biblioteca encontrado
                                </p>
                            ) : (
                                libraryItems.map((item) => (
                                    <div
                                        key={item.id}
                                        className="flex items-start gap-3 p-2 rounded-lg hover:bg-muted/50 cursor-pointer"
                                        onClick={() => handleDocumentToggle(item.id)}
                                    >
                                        <Checkbox
                                            checked={filters.selectedDocuments.includes(item.id)}
                                            onCheckedChange={() => handleDocumentToggle(item.id)}
                                            onClick={(e) => e.stopPropagation()}
                                        />
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2">
                                                {item.type === 'JURISPRUDENCE' && (
                                                    <Gavel className="h-3.5 w-3.5 text-emerald-500" />
                                                )}
                                                {item.type === 'LEGISLATION' && (
                                                    <Scale className="h-3.5 w-3.5 text-blue-500" />
                                                )}
                                                {item.type === 'MODEL' && (
                                                    <BookOpen className="h-3.5 w-3.5 text-violet-500" />
                                                )}
                                                <p className="text-sm font-medium truncate">
                                                    {item.name}
                                                </p>
                                            </div>
                                            {item.description && (
                                                <p className="text-xs text-muted-foreground truncate mt-0.5">
                                                    {item.description}
                                                </p>
                                            )}
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    </ScrollArea>
                </TabsContent>
            </Tabs>

            {/* Selected items summary */}
            {totalSelected > 0 && (
                <div className="p-4 border-t space-y-3">
                    <p className="text-xs text-muted-foreground">Selecionados:</p>
                    <div className="flex flex-wrap gap-1">
                        {filters.selectedDocuments.slice(0, 5).map((id) => (
                            <Badge
                                key={id}
                                variant="secondary"
                                className="text-[10px] pr-1"
                            >
                                <FileText className="h-3 w-3 mr-1" />
                                {id.slice(0, 8)}...
                                <button
                                    onClick={() => removeDocument(id)}
                                    className="ml-1 hover:text-destructive"
                                >
                                    <X className="h-3 w-3" />
                                </button>
                            </Badge>
                        ))}
                        {filters.selectedCases.slice(0, 5).map((id) => (
                            <Badge
                                key={id}
                                variant="secondary"
                                className="text-[10px] pr-1"
                            >
                                <Folder className="h-3 w-3 mr-1" />
                                {id.slice(0, 8)}...
                                <button
                                    onClick={() => removeCase(id)}
                                    className="ml-1 hover:text-destructive"
                                >
                                    <X className="h-3 w-3" />
                                </button>
                            </Badge>
                        ))}
                        {totalSelected > 10 && (
                            <Badge variant="outline" className="text-[10px]">
                                +{totalSelected - 10} mais
                            </Badge>
                        )}
                    </div>

                    {/* Add to Graph button */}
                    <Button
                        variant="default"
                        size="sm"
                        className="w-full text-xs bg-blue-600 hover:bg-blue-700"
                        onClick={handleAddToGraph}
                        disabled={addFromRAGMutation.isPending}
                    >
                        {addFromRAGMutation.isPending ? (
                            <>
                                <Loader2 className="h-3.5 w-3.5 mr-2 animate-spin" />
                                Extraindo entidades...
                            </>
                        ) : (
                            <>
                                <Network className="h-3.5 w-3.5 mr-2" />
                                Adicionar ao Grafo
                            </>
                        )}
                    </Button>
                </div>
            )}
        </div>
    );
}
