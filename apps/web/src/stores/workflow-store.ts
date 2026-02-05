'use client';

import { create } from 'zustand';
import type { Node, Edge } from '@xyflow/react';

// ── Node data types ──────────────────────────────────────────────
export interface WorkflowNodeData {
  label: string;
  description?: string;
  // prompt node
  prompt?: string;
  model?: string;
  // rag_search node
  sources?: string[];
  limit?: number;
  // selection node
  options?: string[];
  collects?: string;
  // condition node
  condition_field?: string;
  branches?: Record<string, string>;
  // human_review node
  instructions?: string;
  // tool_call node
  tool_name?: string;
  arguments?: Record<string, any>;
  // file_upload node
  accepts?: string;
  // user_input node
  input_type?: 'text' | 'file' | 'both' | 'selection';
  optional?: boolean;
  default_text?: string;
  default_template?: string;
  placeholder?: string;
  // review_table node
  columns?: Array<{ id: string; name: string; description: string }>;
  prompt_prefix?: string;
  // output node
  sections?: Array<{ label: string; variable_ref: string; order: number }>;
  show_all?: boolean;
  // knowledge sources (for prompt node)
  knowledge_sources?: Array<{ type: string; id?: string; db_type?: string; label?: string; sources?: string[]; limit?: number }>;
  [key: string]: any;
}

export type WorkflowNode = Node<WorkflowNodeData>;
export type WorkflowEdge = Edge;

// ── Run event ────────────────────────────────────────────────────
export interface RunEvent {
  type: string;
  data: Record<string, any>;
  timestamp: number;
}

// ── Store ────────────────────────────────────────────────────────
interface WorkflowState {
  // Metadata
  id: string | null;
  name: string;
  description: string;
  tags: string[];
  isSaving: boolean;
  isDirty: boolean;

  // React Flow
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  selectedNodeId: string | null;

  // History (undo/redo)
  undoStack: { nodes: WorkflowNode[]; edges: WorkflowEdge[] }[];
  redoStack: { nodes: WorkflowNode[]; edges: WorkflowEdge[] }[];

  // Clipboard
  clipboardNodes: WorkflowNode[];
  clipboardEdges: WorkflowEdge[];

  // Execution
  isRunning: boolean;
  runId: string | null;
  runEvents: RunEvent[];
  runStatus: string | null;
  hilPending: boolean;
  hilNodeId: string | null;
  hilInstructions: string | null;

  // Actions – metadata
  setMetadata: (data: { id?: string; name?: string; description?: string; tags?: string[] }) => void;
  setDirty: (v: boolean) => void;
  setSaving: (v: boolean) => void;

  // Actions – graph
  setNodes: (nodes: WorkflowNode[]) => void;
  setEdges: (edges: WorkflowEdge[]) => void;
  addNode: (node: WorkflowNode) => void;
  updateNodeData: (nodeId: string, data: Partial<WorkflowNodeData>) => void;
  removeNode: (nodeId: string) => void;
  selectNode: (nodeId: string | null) => void;

  // Actions – history
  pushHistory: () => void;
  undo: () => void;
  redo: () => void;

  // Actions – clipboard & bulk
  copySelected: () => void;
  paste: () => void;
  removeSelectedNodes: () => void;

  // Actions – execution
  startRun: (runId: string) => void;
  addRunEvent: (event: RunEvent) => void;
  setRunStatus: (status: string) => void;
  setHIL: (nodeId: string, instructions: string) => void;
  clearHIL: () => void;
  resetRun: () => void;

  // Reset
  resetAll: () => void;
}

const initialState = {
  id: null as string | null,
  name: '',
  description: '',
  tags: [] as string[],
  isSaving: false,
  isDirty: false,
  nodes: [] as WorkflowNode[],
  edges: [] as WorkflowEdge[],
  selectedNodeId: null as string | null,
  undoStack: [] as { nodes: WorkflowNode[]; edges: WorkflowEdge[] }[],
  redoStack: [] as { nodes: WorkflowNode[]; edges: WorkflowEdge[] }[],
  clipboardNodes: [] as WorkflowNode[],
  clipboardEdges: [] as WorkflowEdge[],
  isRunning: false,
  runId: null as string | null,
  runEvents: [] as RunEvent[],
  runStatus: null as string | null,
  hilPending: false,
  hilNodeId: null as string | null,
  hilInstructions: null as string | null,
};

export const useWorkflowStore = create<WorkflowState>((set, get) => ({
  ...initialState,

  // Metadata
  setMetadata: (data) =>
    set((s) => ({
      ...data,
      isDirty: true,
    })),
  setDirty: (v) => set({ isDirty: v }),
  setSaving: (v) => set({ isSaving: v }),

  // Graph
  setNodes: (nodes) => set({ nodes, isDirty: true }),
  setEdges: (edges) => set({ edges, isDirty: true }),
  addNode: (node) => {
    get().pushHistory();
    set((s) => ({ nodes: [...s.nodes, node], isDirty: true }));
  },
  updateNodeData: (nodeId, data) => {
    get().pushHistory();
    set((s) => ({
      nodes: s.nodes.map((n) =>
        n.id === nodeId ? { ...n, data: { ...n.data, ...data } } : n
      ),
      isDirty: true,
    }));
  },
  removeNode: (nodeId) => {
    get().pushHistory();
    set((s) => ({
      nodes: s.nodes.filter((n) => n.id !== nodeId),
      edges: s.edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
      selectedNodeId: s.selectedNodeId === nodeId ? null : s.selectedNodeId,
      isDirty: true,
    }));
  },
  selectNode: (nodeId) => set({ selectedNodeId: nodeId }),

  // History
  pushHistory: () =>
    set((s) => ({
      undoStack: [...s.undoStack.slice(-49), { nodes: s.nodes, edges: s.edges }],
      redoStack: [],
    })),
  undo: () => {
    const { undoStack, nodes, edges } = get();
    if (undoStack.length === 0) return;
    const prev = undoStack[undoStack.length - 1];
    set((s) => ({
      undoStack: s.undoStack.slice(0, -1),
      redoStack: [...s.redoStack, { nodes, edges }],
      nodes: prev.nodes,
      edges: prev.edges,
      isDirty: true,
    }));
  },
  redo: () => {
    const { redoStack, nodes, edges } = get();
    if (redoStack.length === 0) return;
    const next = redoStack[redoStack.length - 1];
    set((s) => ({
      redoStack: s.redoStack.slice(0, -1),
      undoStack: [...s.undoStack, { nodes, edges }],
      nodes: next.nodes,
      edges: next.edges,
      isDirty: true,
    }));
  },

  // Clipboard & bulk
  copySelected: () => {
    const { nodes, edges } = get();
    const selected = nodes.filter((n) => n.selected);
    const selectedIds = new Set(selected.map((n) => n.id));
    const connectedEdges = edges.filter(
      (e) => selectedIds.has(e.source) && selectedIds.has(e.target)
    );
    set({ clipboardNodes: selected, clipboardEdges: connectedEdges });
  },
  paste: () => {
    const { clipboardNodes, clipboardEdges } = get();
    if (clipboardNodes.length === 0) return;
    get().pushHistory();
    const idMap = new Map<string, string>();
    const ts = Date.now();
    clipboardNodes.forEach((n, i) => {
      idMap.set(n.id, `${n.type}_${ts}_${i}_${Math.random().toString(36).slice(2, 8)}`);
    });
    const newNodes = clipboardNodes.map((n) => ({
      ...n,
      id: idMap.get(n.id)!,
      position: { x: n.position.x + 60, y: n.position.y + 60 },
      selected: false,
    }));
    const newEdges = clipboardEdges.map((e) => ({
      ...e,
      id: `e_${idMap.get(e.source)}_${idMap.get(e.target)}`,
      source: idMap.get(e.source)!,
      target: idMap.get(e.target)!,
    }));
    set((s) => ({
      nodes: [...s.nodes, ...newNodes],
      edges: [...s.edges, ...newEdges],
      isDirty: true,
    }));
  },
  removeSelectedNodes: () => {
    const { nodes } = get();
    const selected = nodes.filter((n) => n.selected);
    if (selected.length === 0) return;
    get().pushHistory();
    const selectedIds = new Set(selected.map((n) => n.id));
    set((s) => ({
      nodes: s.nodes.filter((n) => !selectedIds.has(n.id)),
      edges: s.edges.filter((e) => !selectedIds.has(e.source) && !selectedIds.has(e.target)),
      selectedNodeId: s.selectedNodeId && selectedIds.has(s.selectedNodeId) ? null : s.selectedNodeId,
      isDirty: true,
    }));
  },

  // Execution
  startRun: (runId) =>
    set({ isRunning: true, runId, runEvents: [], runStatus: 'running', hilPending: false }),
  addRunEvent: (event) =>
    set((s) => ({ runEvents: [...s.runEvents, event] })),
  setRunStatus: (status) => set({ runStatus: status, isRunning: status === 'running' }),
  setHIL: (nodeId, instructions) =>
    set({ hilPending: true, hilNodeId: nodeId, hilInstructions: instructions }),
  clearHIL: () => set({ hilPending: false, hilNodeId: null, hilInstructions: null }),
  resetRun: () =>
    set({ isRunning: false, runId: null, runEvents: [], runStatus: null, hilPending: false, hilNodeId: null, hilInstructions: null }),

  // Reset all
  resetAll: () => set(initialState),
}));
