declare module 'react-force-graph-2d' {
    import { Component, RefObject } from 'react';

    export interface NodeObject {
        id?: string | number;
        x?: number;
        y?: number;
        vx?: number;
        vy?: number;
        fx?: number | null;
        fy?: number | null;
        [key: string]: unknown;
    }

    export interface LinkObject {
        source?: string | number | NodeObject;
        target?: string | number | NodeObject;
        [key: string]: unknown;
    }

    export interface GraphData {
        nodes: NodeObject[];
        links: LinkObject[];
    }

    export interface ForceGraph2DProps {
        // Data
        graphData?: GraphData;

        // Container layout
        width?: number;
        height?: number;
        backgroundColor?: string;

        // Node styling
        nodeRelSize?: number;
        nodeId?: string | ((node: NodeObject) => string);
        nodeLabel?: string | ((node: NodeObject) => string);
        nodeVal?: number | string | ((node: NodeObject) => number);
        nodeColor?: string | ((node: NodeObject) => string);
        nodeAutoColorBy?: string | ((node: NodeObject) => string | null);
        nodeCanvasObject?: (node: NodeObject, ctx: CanvasRenderingContext2D, globalScale: number) => void;
        nodeCanvasObjectMode?: string | ((node: NodeObject) => string);
        nodePointerAreaPaint?: (node: NodeObject, color: string, ctx: CanvasRenderingContext2D, globalScale: number) => void;

        // Link styling
        linkSource?: string | ((link: LinkObject) => string);
        linkTarget?: string | ((link: LinkObject) => string);
        linkLabel?: string | ((link: LinkObject) => string);
        linkVisibility?: boolean | string | ((link: LinkObject) => boolean);
        linkColor?: string | ((link: LinkObject) => string);
        linkAutoColorBy?: string | ((link: LinkObject) => string | null);
        linkWidth?: number | string | ((link: LinkObject) => number);
        linkCurvature?: number | string | ((link: LinkObject) => number);
        linkCanvasObject?: (link: LinkObject, ctx: CanvasRenderingContext2D, globalScale: number) => void;
        linkCanvasObjectMode?: string | ((link: LinkObject) => string);
        linkDirectionalArrowLength?: number | string | ((link: LinkObject) => number);
        linkDirectionalArrowColor?: string | ((link: LinkObject) => string);
        linkDirectionalArrowRelPos?: number | string | ((link: LinkObject) => number);
        linkDirectionalParticles?: number | string | ((link: LinkObject) => number);
        linkDirectionalParticleSpeed?: number | string | ((link: LinkObject) => number);
        linkDirectionalParticleWidth?: number | string | ((link: LinkObject) => number);
        linkDirectionalParticleColor?: string | ((link: LinkObject) => string);
        linkPointerAreaPaint?: (link: LinkObject, color: string, ctx: CanvasRenderingContext2D, globalScale: number) => void;

        // Interaction
        onNodeClick?: (node: NodeObject, event: MouseEvent) => void;
        onNodeRightClick?: (node: NodeObject, event: MouseEvent) => void;
        onNodeHover?: (node: NodeObject | null, previousNode: NodeObject | null) => void;
        onNodeDrag?: (node: NodeObject, translate: { x: number; y: number }) => void;
        onNodeDragEnd?: (node: NodeObject, translate: { x: number; y: number }) => void;
        onLinkClick?: (link: LinkObject, event: MouseEvent) => void;
        onLinkRightClick?: (link: LinkObject, event: MouseEvent) => void;
        onLinkHover?: (link: LinkObject | null, previousLink: LinkObject | null) => void;
        onBackgroundClick?: (event: MouseEvent) => void;
        onBackgroundRightClick?: (event: MouseEvent) => void;
        onZoom?: (transform: { k: number; x: number; y: number }) => void;
        onZoomEnd?: (transform: { k: number; x: number; y: number }) => void;

        // Controls
        enableNodeDrag?: boolean;
        enableZoomInteraction?: boolean;
        enablePanInteraction?: boolean;
        enablePointerInteraction?: boolean;

        // Force engine
        dagMode?: string;
        dagLevelDistance?: number;
        dagNodeFilter?: (node: NodeObject) => boolean;
        onDagError?: (loopNodeIds: (string | number)[]) => void;
        d3AlphaMin?: number;
        d3AlphaDecay?: number;
        d3VelocityDecay?: number;
        warmupTicks?: number;
        cooldownTicks?: number;
        cooldownTime?: number;
        onEngineStop?: () => void;
        onEngineTick?: () => void;

        // Misc
        autoPauseRedraw?: boolean;
        minZoom?: number;
        maxZoom?: number;

        // Ref methods (via ref)
        ref?: RefObject<ForceGraphMethods>;
    }

    export interface ForceGraphMethods {
        // Camera
        centerAt: (x?: number, y?: number, ms?: number) => void;
        zoom: (zoom?: number, ms?: number) => number;
        zoomToFit: (ms?: number, padding?: number, nodeFilter?: (node: NodeObject) => boolean) => void;
        cameraPosition: (position?: { x: number; y: number; z: number }, lookAt?: { x: number; y: number; z: number }, ms?: number) => { x: number; y: number; z: number };

        // Force engine
        pauseAnimation: () => void;
        resumeAnimation: () => void;
        d3Force: (name: string, force?: unknown) => unknown;
        d3ReheatSimulation: () => void;

        // Utility
        getGraphBbox: (nodeFilter?: (node: NodeObject) => boolean) => { x: [number, number]; y: [number, number] };
        screen2GraphCoords: (x: number, y: number) => { x: number; y: number };
        graph2ScreenCoords: (x: number, y: number) => { x: number; y: number };
    }

    export default class ForceGraph2D extends Component<ForceGraph2DProps> implements ForceGraphMethods {
        centerAt: ForceGraphMethods['centerAt'];
        zoom: ForceGraphMethods['zoom'];
        zoomToFit: ForceGraphMethods['zoomToFit'];
        cameraPosition: ForceGraphMethods['cameraPosition'];
        pauseAnimation: ForceGraphMethods['pauseAnimation'];
        resumeAnimation: ForceGraphMethods['resumeAnimation'];
        d3Force: ForceGraphMethods['d3Force'];
        d3ReheatSimulation: ForceGraphMethods['d3ReheatSimulation'];
        getGraphBbox: ForceGraphMethods['getGraphBbox'];
        screen2GraphCoords: ForceGraphMethods['screen2GraphCoords'];
        graph2ScreenCoords: ForceGraphMethods['graph2ScreenCoords'];
    }
}
