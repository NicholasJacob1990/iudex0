"use client";

import { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { InteractiveNvlWrapper } from '@neo4j-nvl/react';
import type { Node, Relationship, HitTargets } from '@neo4j-nvl/base';
import type { NVL } from '@neo4j-nvl/base';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
    Search,
    ZoomIn,
    ZoomOut,
    Maximize2,
    RefreshCw,
    Scale,
    BookOpen,
    Gavel,
    GraduationCap,
    X,
    ChevronRight,
    Link2,
    FileText,
    Info,
    Route,
    Users,
    Loader2,
    ArrowRight,
    Target,
    Move,
} from 'lucide-react';
import { toast } from 'sonner';
import {
    useGraphStore,
    GraphNode,
    GraphLink,
    GROUP_COLORS,
    selectFilteredNodes,
    selectFilteredLinks,
} from '@/stores/graph-store';
import {
    useGraphData,
    useGraphStats,
    useGraphEntity,
    useGraphRemissoes,
    useSemanticNeighbors,
    useGraphPath,
    usePrefetchEntity,
    usePrefetchNeighbors,
} from '@/lib/use-graph';

// =============================================================================
// NVL THEME COLORS
// =============================================================================

const NVL_COLORS = {
    legislacao: '#3b82f6',      // blue-500
    jurisprudencia: '#8b5cf6',  // violet-500
    doutrina: '#10b981',        // emerald-500
    outros: '#6b7280',          // gray-500
    selected: '#f59e0b',        // amber-500
    pathSource: '#22c55e',      // green-500
    pathTarget: '#ef4444',      // red-500
    pathNode: '#f59e0b',        // amber-500
};

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

function getNodeColor(group: string, isSelected: boolean = false): string {
    if (isSelected) return NVL_COLORS.selected;
    return NVL_COLORS[group as keyof typeof NVL_COLORS] || NVL_COLORS.outros;
}

function transformToNvlNodes(
    nodes: GraphNode[],
    selectedId: string | null,
    pathSource: string | null,
    pathTarget: string | null,
    pathNodeIds: string[]
): Node[] {
    return nodes.map((node) => {
        let color = getNodeColor(node.group);
        let size = Math.max(20, (node.size || 1) * 8);

        // Path mode highlighting
        if (pathSource === node.id) {
            color = NVL_COLORS.pathSource;
            size = 35;
        } else if (pathTarget === node.id) {
            color = NVL_COLORS.pathTarget;
            size = 35;
        } else if (pathNodeIds.includes(node.id)) {
            color = NVL_COLORS.pathNode;
            size = 30;
        }

        // Selected highlighting
        if (selectedId === node.id) {
            size = 35;
        }

        return {
            id: node.id,
            color,
            size,
            caption: node.label,
            captionAlign: 'bottom' as const,
            selected: selectedId === node.id,
            pinned: false,
        };
    });
}

function transformToNvlRels(links: GraphLink[]): Relationship[] {
    return links.map((link, idx) => ({
        id: `rel-${idx}-${typeof link.source === 'string' ? link.source : link.source}`,
        from: typeof link.source === 'string' ? link.source : String(link.source),
        to: typeof link.target === 'string' ? link.target : String(link.target),
        caption: link.label || '',
        color: '#d1d5db',
        width: Math.max(1, (link.weight || 1) * 0.8),
    }));
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export default function GraphPage() {
    const nvlRef = useRef<NVL>(null);
    const containerRef = useRef<HTMLDivElement>(null);

    const {
        graphData,
        selectedNode,
        filters,
        setGraphData,
        setSelectedNode,
        setSelectedEntity,
        setRemissoes,
        setStats,
        setLoading,
        setLoadingDetail,
        toggleGroup,
        clearSelection,
        setFilters,
    } = useGraphStore();

    const [pathSource, setPathSource] = useState<string | null>(null);
    const [pathTarget, setPathTarget] = useState<string | null>(null);
    const [showPathMode, setShowPathMode] = useState(false);
    const [activeTab, setActiveTab] = useState<string>('info');

    // Get filtered data from store
    const filteredNodes = useGraphStore(selectFilteredNodes);
    const filteredLinks = useGraphStore(selectFilteredLinks);

    // Prefetch functions
    const prefetchEntity = usePrefetchEntity();
    const prefetchNeighbors = usePrefetchNeighbors();

    // ==========================================================================
    // REACT QUERY HOOKS
    // ==========================================================================

    const graphDataQuery = useGraphData({
        types: filters.entityTypes.join(','),
        groups: [
            filters.showLegislacao && 'legislacao',
            filters.showJurisprudencia && 'jurisprudencia',
            filters.showDoutrina && 'doutrina',
        ].filter(Boolean).join(','),
        maxNodes: filters.maxNodes,
        includeRelationships: filters.showRelationships,
    });

    const statsQuery = useGraphStats();
    const entityQuery = useGraphEntity(selectedNode?.id ?? null);
    const remissoesQuery = useGraphRemissoes(selectedNode?.id ?? null);
    const neighborsQuery = useSemanticNeighbors(
        selectedNode?.id ?? null,
        30,
        activeTab === 'neighbors' && !!selectedNode
    );

    const pathQuery = useGraphPath(
        pathSource,
        pathTarget,
        4,
        showPathMode && !!pathSource && !!pathTarget
    );

    // ==========================================================================
    // SYNC REACT QUERY TO STORE
    // ==========================================================================

    useEffect(() => {
        if (graphDataQuery.data) {
            setGraphData(graphDataQuery.data);
        }
    }, [graphDataQuery.data, setGraphData]);

    useEffect(() => {
        if (statsQuery.data) {
            setStats(statsQuery.data);
        }
    }, [statsQuery.data, setStats]);

    useEffect(() => {
        if (entityQuery.data) {
            setSelectedEntity(entityQuery.data);
        }
    }, [entityQuery.data, setSelectedEntity]);

    useEffect(() => {
        if (remissoesQuery.data) {
            setRemissoes(remissoesQuery.data);
        }
    }, [remissoesQuery.data, setRemissoes]);

    useEffect(() => {
        setLoading(graphDataQuery.isLoading);
    }, [graphDataQuery.isLoading, setLoading]);

    useEffect(() => {
        setLoadingDetail(entityQuery.isLoading || remissoesQuery.isLoading);
    }, [entityQuery.isLoading, remissoesQuery.isLoading, setLoadingDetail]);

    // ==========================================================================
    // NVL DATA
    // ==========================================================================

    const pathNodeIds = useMemo(() => {
        if (!pathQuery.data?.found || !pathQuery.data.paths?.[0]) return [];
        return pathQuery.data.paths[0].path_ids || [];
    }, [pathQuery.data]);

    const nvlNodes = useMemo(() =>
        transformToNvlNodes(
            filteredNodes,
            selectedNode?.id ?? null,
            pathSource,
            pathTarget,
            pathNodeIds
        ),
        [filteredNodes, selectedNode?.id, pathSource, pathTarget, pathNodeIds]
    );

    const nvlRels = useMemo(() =>
        transformToNvlRels(filteredLinks),
        [filteredLinks]
    );

    // ==========================================================================
    // HANDLERS
    // ==========================================================================

    const handleNodeClick = useCallback((node: Node, hitTargets: HitTargets, evt: MouseEvent) => {
        if (showPathMode) {
            if (!pathSource) {
                setPathSource(node.id);
                toast.info(`Origem: ${node.caption}. Clique em outro no para destino.`);
            } else if (!pathTarget && node.id !== pathSource) {
                setPathTarget(node.id);
                toast.info(`Destino: ${node.caption}. Buscando caminho...`);
            }
            return;
        }

        const graphNode = filteredNodes.find(n => n.id === node.id);
        if (graphNode) {
            setSelectedNode(graphNode);
            setActiveTab('info');

            // Zoom to node
            if (nvlRef.current) {
                nvlRef.current.fit([node.id]);
            }
        }
    }, [showPathMode, pathSource, pathTarget, filteredNodes, setSelectedNode]);

    const handleNodeHover = useCallback((nodeId: string | null) => {
        if (nodeId) {
            prefetchEntity(nodeId);
        }
    }, [prefetchEntity]);

    const handleZoomIn = () => {
        if (nvlRef.current) {
            const currentZoom = nvlRef.current.getScale();
            nvlRef.current.setZoom(currentZoom * 1.5);
        }
    };

    const handleZoomOut = () => {
        if (nvlRef.current) {
            const currentZoom = nvlRef.current.getScale();
            nvlRef.current.setZoom(currentZoom / 1.5);
        }
    };

    const handleFitView = () => {
        if (nvlRef.current) {
            nvlRef.current.fit(nvlNodes.map(n => n.id));
        }
    };

    const handleRefresh = () => {
        graphDataQuery.refetch();
        statsQuery.refetch();
    };

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        graphDataQuery.refetch();
    };

    const togglePathMode = () => {
        if (showPathMode) {
            setShowPathMode(false);
            setPathSource(null);
            setPathTarget(null);
        } else {
            setShowPathMode(true);
            clearSelection();
            toast.info('Modo caminho ativado. Clique em dois nos para encontrar o caminho.');
        }
    };

    const clearPath = () => {
        setPathSource(null);
        setPathTarget(null);
    };

    const navigateToNode = useCallback((nodeId: string) => {
        const graphNode = filteredNodes.find(n => n.id === nodeId);
        if (graphNode) {
            setSelectedNode(graphNode);
            if (nvlRef.current) {
                nvlRef.current.fit([nodeId]);
            }
        }
    }, [filteredNodes, setSelectedNode]);

    // ==========================================================================
    // PATH VISUALIZATION
    // ==========================================================================

    const pathVisualization = useMemo(() => {
        if (!pathQuery.data?.found || !pathQuery.data.paths?.[0]) return null;
        const path = pathQuery.data.paths[0];
        return {
            nodes: path.nodes || [],
            edges: path.edges || [],
            pathNames: path.path,
            relationships: path.relationships,
            length: path.length,
        };
    }, [pathQuery.data]);

    // ==========================================================================
    // RENDER
    // ==========================================================================

    return (
        <div className="h-[calc(100vh-4rem)] flex flex-col">
            {/* Header */}
            <div className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 p-4">
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-bold tracking-tight">Grafo de Conhecimento Juridico</h1>
                        <p className="text-muted-foreground text-sm">
                            Explore relacoes semanticas entre legislacao, jurisprudencia e doutrina
                        </p>
                    </div>

                    <div className="flex items-center gap-4">
                        {/* Path Mode Toggle */}
                        <Button
                            variant={showPathMode ? "default" : "outline"}
                            size="sm"
                            onClick={togglePathMode}
                            className="gap-2"
                        >
                            <Route className="h-4 w-4" />
                            {showPathMode ? 'Sair do modo caminho' : 'Encontrar caminho'}
                        </Button>

                        {/* Search */}
                        <form onSubmit={handleSearch} className="relative">
                            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                            <Input
                                placeholder="Buscar entidade..."
                                className="pl-9 w-64"
                                value={filters.searchQuery}
                                onChange={(e) => setFilters({ searchQuery: e.target.value })}
                            />
                        </form>

                        {/* Refresh */}
                        <Button
                            variant="outline"
                            size="icon"
                            onClick={handleRefresh}
                            disabled={graphDataQuery.isLoading}
                        >
                            <RefreshCw className={`h-4 w-4 ${graphDataQuery.isLoading ? 'animate-spin' : ''}`} />
                        </Button>
                    </div>
                </div>

                {/* Filter Checkboxes */}
                <div className="flex items-center gap-6 mt-4">
                    <div className="flex items-center gap-2">
                        <Checkbox
                            id="legislacao"
                            checked={filters.showLegislacao}
                            onCheckedChange={() => toggleGroup('legislacao')}
                        />
                        <Label htmlFor="legislacao" className="flex items-center gap-2 cursor-pointer">
                            <BookOpen className="h-4 w-4" style={{ color: NVL_COLORS.legislacao }} />
                            Legislacao
                        </Label>
                    </div>

                    <div className="flex items-center gap-2">
                        <Checkbox
                            id="jurisprudencia"
                            checked={filters.showJurisprudencia}
                            onCheckedChange={() => toggleGroup('jurisprudencia')}
                        />
                        <Label htmlFor="jurisprudencia" className="flex items-center gap-2 cursor-pointer">
                            <Gavel className="h-4 w-4" style={{ color: NVL_COLORS.jurisprudencia }} />
                            Jurisprudencia
                        </Label>
                    </div>

                    <div className="flex items-center gap-2">
                        <Checkbox
                            id="doutrina"
                            checked={filters.showDoutrina}
                            onCheckedChange={() => toggleGroup('doutrina')}
                        />
                        <Label htmlFor="doutrina" className="flex items-center gap-2 cursor-pointer">
                            <GraduationCap className="h-4 w-4" style={{ color: NVL_COLORS.doutrina }} />
                            Doutrina
                        </Label>
                    </div>

                    <div className="flex-1" />

                    {/* Stats */}
                    {statsQuery.data && (
                        <div className="flex items-center gap-4 text-sm text-muted-foreground">
                            <span>{statsQuery.data.total_entities} entidades</span>
                            <span>{statsQuery.data.total_documents} documentos</span>
                            <span>{statsQuery.data.relationships_count} relacoes</span>
                        </div>
                    )}
                </div>

                {/* Path Mode Indicator */}
                {showPathMode && (
                    <div className="mt-4 p-3 bg-muted rounded-lg flex items-center justify-between">
                        <div className="flex items-center gap-4 text-sm">
                            <span className="font-medium">Modo Caminho:</span>
                            <div className="flex items-center gap-2">
                                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: NVL_COLORS.pathSource }} />
                                <span>Origem: {pathSource ? graphData?.nodes.find(n => n.id === pathSource)?.label || pathSource : 'Selecione...'}</span>
                            </div>
                            <ArrowRight className="h-4 w-4" />
                            <div className="flex items-center gap-2">
                                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: NVL_COLORS.pathTarget }} />
                                <span>Destino: {pathTarget ? graphData?.nodes.find(n => n.id === pathTarget)?.label || pathTarget : 'Selecione...'}</span>
                            </div>
                            {pathQuery.isLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                        </div>
                        <Button variant="ghost" size="sm" onClick={clearPath}>
                            Limpar
                        </Button>
                    </div>
                )}
            </div>

            {/* Main Content */}
            <div className="flex-1 flex overflow-hidden">
                {/* Graph Container */}
                <div className="flex-1 relative bg-slate-50 dark:bg-slate-900" ref={containerRef}>
                    {graphDataQuery.isLoading && !graphData ? (
                        <div className="absolute inset-0 flex items-center justify-center">
                            <div className="text-center">
                                <RefreshCw className="h-8 w-8 animate-spin mx-auto text-muted-foreground" />
                                <p className="mt-2 text-sm text-muted-foreground">Carregando grafo...</p>
                            </div>
                        </div>
                    ) : graphDataQuery.error ? (
                        <div className="absolute inset-0 flex items-center justify-center">
                            <div className="text-center">
                                <p className="text-destructive">{(graphDataQuery.error as Error).message}</p>
                                <Button variant="outline" className="mt-4" onClick={handleRefresh}>
                                    Tentar novamente
                                </Button>
                            </div>
                        </div>
                    ) : nvlNodes.length > 0 ? (
                        <InteractiveNvlWrapper
                            ref={nvlRef}
                            nodes={nvlNodes}
                            rels={nvlRels}
                            nvlOptions={{
                                initialZoom: 1,
                                minZoom: 0.1,
                                maxZoom: 10,
                                layout: 'forceDirected',
                                renderer: 'canvas',
                                allowDynamicMinZoom: true,
                                disableWebGL: false,
                            }}
                            mouseEventCallbacks={{
                                onNodeClick: handleNodeClick,
                                onHover: (element, hitTargets, evt) => {
                                    if (hitTargets.nodes.length > 0) {
                                        const hoveredNode = hitTargets.nodes[0];
                                        handleNodeHover(hoveredNode.data.id ?? null);
                                    } else {
                                        handleNodeHover(null);
                                    }
                                },
                            }}
                            nvlCallbacks={{
                                onLayoutDone: () => {
                                    console.log('NVL layout complete');
                                },
                            }}
                            style={{ width: '100%', height: '100%' }}
                        />
                    ) : (
                        <div className="absolute inset-0 flex items-center justify-center">
                            <div className="text-center text-muted-foreground">
                                <Scale className="h-12 w-12 mx-auto mb-4 opacity-50" />
                                <p>Nenhuma entidade encontrada</p>
                                <p className="text-sm">Ajuste os filtros ou faca uma busca</p>
                            </div>
                        </div>
                    )}

                    {/* Zoom Controls */}
                    <div className="absolute bottom-4 right-4 flex flex-col gap-2">
                        <Button variant="secondary" size="icon" onClick={handleZoomIn} title="Zoom in">
                            <ZoomIn className="h-4 w-4" />
                        </Button>
                        <Button variant="secondary" size="icon" onClick={handleZoomOut} title="Zoom out">
                            <ZoomOut className="h-4 w-4" />
                        </Button>
                        <Button variant="secondary" size="icon" onClick={handleFitView} title="Fit to view">
                            <Maximize2 className="h-4 w-4" />
                        </Button>
                    </div>

                    {/* Legend */}
                    <div className="absolute bottom-4 left-4 bg-background/95 backdrop-blur rounded-lg border p-3 shadow-lg">
                        <p className="text-xs font-medium mb-2">Legenda</p>
                        <div className="flex flex-col gap-1.5">
                            <div className="flex items-center gap-2 text-xs">
                                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: NVL_COLORS.legislacao }} />
                                <span>Legislacao</span>
                            </div>
                            <div className="flex items-center gap-2 text-xs">
                                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: NVL_COLORS.jurisprudencia }} />
                                <span>Jurisprudencia</span>
                            </div>
                            <div className="flex items-center gap-2 text-xs">
                                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: NVL_COLORS.doutrina }} />
                                <span>Doutrina</span>
                            </div>
                        </div>
                        {showPathMode && (
                            <>
                                <div className="border-t my-2" />
                                <div className="flex flex-col gap-1.5">
                                    <div className="flex items-center gap-2 text-xs">
                                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: NVL_COLORS.pathSource }} />
                                        <span>Origem</span>
                                    </div>
                                    <div className="flex items-center gap-2 text-xs">
                                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: NVL_COLORS.pathTarget }} />
                                        <span>Destino</span>
                                    </div>
                                    <div className="flex items-center gap-2 text-xs">
                                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: NVL_COLORS.pathNode }} />
                                        <span>Caminho</span>
                                    </div>
                                </div>
                            </>
                        )}
                        <div className="border-t mt-2 pt-2">
                            <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                                <Move className="h-3 w-3" />
                                <span>Arraste para mover</span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Detail Panel */}
                {(selectedNode || (showPathMode && pathQuery.data?.found)) && (
                    <div className="w-96 border-l bg-background overflow-hidden flex flex-col">
                        <div className="p-4 border-b flex items-center justify-between">
                            <h2 className="font-semibold truncate">
                                {showPathMode && pathQuery.data?.found
                                    ? 'Caminho Encontrado'
                                    : selectedNode?.label}
                            </h2>
                            <Button variant="ghost" size="icon" onClick={() => {
                                clearSelection();
                                if (showPathMode) clearPath();
                            }}>
                                <X className="h-4 w-4" />
                            </Button>
                        </div>

                        <ScrollArea className="flex-1">
                            <div className="p-4 space-y-4">
                                {/* Path Visualization */}
                                {showPathMode && pathQuery.data?.found && pathVisualization && (
                                    <Card>
                                        <CardHeader className="pb-2">
                                            <CardTitle className="text-sm flex items-center gap-2">
                                                <Route className="h-4 w-4" />
                                                Caminho ({pathVisualization.length} passos)
                                            </CardTitle>
                                        </CardHeader>
                                        <CardContent>
                                            <div className="space-y-2">
                                                {pathVisualization.pathNames.map((name, idx) => (
                                                    <div key={idx}>
                                                        {idx > 0 && (
                                                            <div className="flex items-center gap-2 py-1">
                                                                <div className="flex-1 h-px bg-border" />
                                                                <Badge variant="outline" className="text-[10px] px-1.5">
                                                                    {pathVisualization.relationships[idx - 1]}
                                                                </Badge>
                                                                <div className="flex-1 h-px bg-border" />
                                                            </div>
                                                        )}
                                                        <div
                                                            className={`p-2 rounded-lg text-sm cursor-pointer hover:opacity-80 transition-opacity ${
                                                                idx === 0 ? 'bg-green-100 dark:bg-green-900/30 border border-green-300' :
                                                                idx === pathVisualization.pathNames.length - 1 ? 'bg-red-100 dark:bg-red-900/30 border border-red-300' :
                                                                'bg-amber-100 dark:bg-amber-900/30 border border-amber-300'
                                                            }`}
                                                            onClick={() => {
                                                                const nodeId = pathVisualization.nodes?.[idx]?.entity_id;
                                                                if (nodeId) navigateToNode(nodeId);
                                                            }}
                                                        >
                                                            {name}
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        </CardContent>
                                    </Card>
                                )}

                                {/* Entity Detail Tabs */}
                                {selectedNode && !showPathMode && (
                                    <Tabs value={activeTab} onValueChange={setActiveTab}>
                                        <TabsList className="grid w-full grid-cols-3">
                                            <TabsTrigger value="info">Info</TabsTrigger>
                                            <TabsTrigger value="remissoes">Remissoes</TabsTrigger>
                                            <TabsTrigger value="neighbors">
                                                Vizinhos
                                                {neighborsQuery.isLoading && (
                                                    <Loader2 className="h-3 w-3 ml-1 animate-spin" />
                                                )}
                                            </TabsTrigger>
                                        </TabsList>

                                        {/* Info Tab */}
                                        <TabsContent value="info" className="mt-4 space-y-4">
                                            {entityQuery.isLoading ? (
                                                <div className="space-y-2">
                                                    <Skeleton className="h-24 w-full" />
                                                    <Skeleton className="h-32 w-full" />
                                                </div>
                                            ) : entityQuery.data ? (
                                                <>
                                                    <Card>
                                                        <CardHeader className="pb-2">
                                                            <CardTitle className="text-sm flex items-center gap-2">
                                                                <Info className="h-4 w-4" />
                                                                Informacoes
                                                            </CardTitle>
                                                        </CardHeader>
                                                        <CardContent className="space-y-2 text-sm">
                                                            <div className="flex justify-between">
                                                                <span className="text-muted-foreground">Tipo</span>
                                                                <Badge variant="secondary">{entityQuery.data.type}</Badge>
                                                            </div>
                                                            <div className="flex justify-between">
                                                                <span className="text-muted-foreground">Grupo</span>
                                                                <Badge
                                                                    style={{
                                                                        backgroundColor: NVL_COLORS[selectedNode.group as keyof typeof NVL_COLORS] || NVL_COLORS.outros,
                                                                        color: 'white'
                                                                    }}
                                                                >
                                                                    {selectedNode.group}
                                                                </Badge>
                                                            </div>
                                                            {entityQuery.data.normalized && (
                                                                <div className="flex justify-between">
                                                                    <span className="text-muted-foreground">Normalizado</span>
                                                                    <span className="font-mono text-xs">{entityQuery.data.normalized}</span>
                                                                </div>
                                                            )}
                                                        </CardContent>
                                                    </Card>

                                                    {/* Chunks/Sources */}
                                                    {entityQuery.data.chunks && entityQuery.data.chunks.length > 0 && (
                                                        <Card>
                                                            <CardHeader className="pb-2">
                                                                <CardTitle className="text-sm flex items-center gap-2">
                                                                    <FileText className="h-4 w-4" />
                                                                    Fontes ({entityQuery.data.chunks.length})
                                                                </CardTitle>
                                                            </CardHeader>
                                                            <CardContent>
                                                                <div className="space-y-3">
                                                                    {entityQuery.data.chunks.slice(0, 5).map((chunk) => (
                                                                        <div key={chunk.chunk_uid} className="text-sm border-l-2 border-muted pl-3">
                                                                            <p className="font-medium text-xs text-muted-foreground mb-1">
                                                                                {chunk.doc_title || chunk.source_type}
                                                                            </p>
                                                                            <p className="text-xs line-clamp-3">
                                                                                {chunk.text}
                                                                            </p>
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            </CardContent>
                                                        </Card>
                                                    )}

                                                    {/* Direct Neighbors */}
                                                    {entityQuery.data.neighbors && entityQuery.data.neighbors.length > 0 && (
                                                        <Card>
                                                            <CardHeader className="pb-2">
                                                                <CardTitle className="text-sm">
                                                                    Conexoes diretas ({entityQuery.data.neighbors.length})
                                                                </CardTitle>
                                                            </CardHeader>
                                                            <CardContent>
                                                                <div className="flex flex-wrap gap-1">
                                                                    {entityQuery.data.neighbors.slice(0, 20).map((n) => (
                                                                        <Badge
                                                                            key={n.id}
                                                                            variant="outline"
                                                                            className="text-xs cursor-pointer hover:bg-muted"
                                                                            onClick={() => navigateToNode(n.id)}
                                                                        >
                                                                            {n.name}
                                                                        </Badge>
                                                                    ))}
                                                                </div>
                                                            </CardContent>
                                                        </Card>
                                                    )}
                                                </>
                                            ) : null}
                                        </TabsContent>

                                        {/* Remissoes Tab */}
                                        <TabsContent value="remissoes" className="mt-4">
                                            {remissoesQuery.isLoading ? (
                                                <Skeleton className="h-48 w-full" />
                                            ) : remissoesQuery.data && remissoesQuery.data.length > 0 ? (
                                                <Card>
                                                    <CardHeader className="pb-2">
                                                        <CardTitle className="text-sm flex items-center gap-2">
                                                            <Link2 className="h-4 w-4" />
                                                            Remissoes ({remissoesQuery.data.length})
                                                        </CardTitle>
                                                        <CardDescription className="text-xs">
                                                            Dispositivos semanticamente relacionados
                                                        </CardDescription>
                                                    </CardHeader>
                                                    <CardContent>
                                                        <div className="space-y-1">
                                                            {remissoesQuery.data.slice(0, 15).map((r) => (
                                                                <div
                                                                    key={r.id}
                                                                    className="flex items-center justify-between p-2 rounded-lg hover:bg-muted cursor-pointer transition-colors"
                                                                    onClick={() => navigateToNode(r.id)}
                                                                >
                                                                    <div className="flex items-center gap-2">
                                                                        <div
                                                                            className="w-2 h-2 rounded-full"
                                                                            style={{ backgroundColor: NVL_COLORS[r.group as keyof typeof NVL_COLORS] || NVL_COLORS.outros }}
                                                                        />
                                                                        <span className="text-sm">{r.name}</span>
                                                                    </div>
                                                                    <div className="flex items-center gap-1">
                                                                        <Badge variant="outline" className="text-xs">
                                                                            {r.co_occurrences}x
                                                                        </Badge>
                                                                        <ChevronRight className="h-3 w-3 text-muted-foreground" />
                                                                    </div>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </CardContent>
                                                </Card>
                                            ) : (
                                                <div className="text-center py-8 text-muted-foreground text-sm">
                                                    Nenhuma remissao encontrada
                                                </div>
                                            )}
                                        </TabsContent>

                                        {/* Semantic Neighbors Tab */}
                                        <TabsContent value="neighbors" className="mt-4">
                                            {neighborsQuery.isLoading ? (
                                                <div className="space-y-2">
                                                    <Skeleton className="h-16 w-full" />
                                                    <Skeleton className="h-16 w-full" />
                                                    <Skeleton className="h-16 w-full" />
                                                </div>
                                            ) : neighborsQuery.data?.neighbors && neighborsQuery.data.neighbors.length > 0 ? (
                                                <Card>
                                                    <CardHeader className="pb-2">
                                                        <CardTitle className="text-sm flex items-center gap-2">
                                                            <Users className="h-4 w-4" />
                                                            Vizinhos Semanticos ({neighborsQuery.data.total})
                                                        </CardTitle>
                                                        <CardDescription className="text-xs">
                                                            Entidades relacionadas por contexto
                                                        </CardDescription>
                                                    </CardHeader>
                                                    <CardContent>
                                                        <div className="space-y-2">
                                                            {neighborsQuery.data.neighbors.slice(0, 15).map((neighbor) => (
                                                                <div
                                                                    key={neighbor.id}
                                                                    className="p-2 rounded-lg hover:bg-muted cursor-pointer border transition-colors"
                                                                    onClick={() => navigateToNode(neighbor.id)}
                                                                    onMouseEnter={() => prefetchNeighbors(neighbor.id)}
                                                                >
                                                                    <div className="flex items-center justify-between mb-1">
                                                                        <div className="flex items-center gap-2">
                                                                            <div
                                                                                className="w-2 h-2 rounded-full"
                                                                                style={{ backgroundColor: NVL_COLORS[neighbor.group as keyof typeof NVL_COLORS] || NVL_COLORS.outros }}
                                                                            />
                                                                            <span className="text-sm font-medium">{neighbor.name}</span>
                                                                        </div>
                                                                        <Badge variant="secondary" className="text-xs">
                                                                            {neighbor.strength}x
                                                                        </Badge>
                                                                    </div>
                                                                    <div className="flex items-center gap-2 mb-1">
                                                                        <Badge variant="outline" className="text-[10px]">
                                                                            {neighbor.relation.label}
                                                                        </Badge>
                                                                        <span className="text-[10px] text-muted-foreground">
                                                                            {neighbor.type}
                                                                        </span>
                                                                    </div>
                                                                    {neighbor.sample_contexts?.[0] && (
                                                                        <p className="text-xs text-muted-foreground line-clamp-2">
                                                                            {neighbor.sample_contexts[0]}
                                                                        </p>
                                                                    )}
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </CardContent>
                                                </Card>
                                            ) : (
                                                <div className="text-center py-8 text-muted-foreground text-sm">
                                                    Nenhum vizinho semantico encontrado
                                                </div>
                                            )}
                                        </TabsContent>
                                    </Tabs>
                                )}
                            </div>
                        </ScrollArea>
                    </div>
                )}
            </div>
        </div>
    );
}
