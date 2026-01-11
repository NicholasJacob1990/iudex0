import { create } from 'zustand';

const looksLikeHtml = (content: string) => {
    return /<(p|h1|h2|h3|h4|h5|h6|div|ul|ol|li|table|thead|tbody|tr|td|th|blockquote|strong|em|span)(\s|>)/i.test(
        content
    );
};

const escapeHtml = (value: string) => {
    return value
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
};

const findRangeInHtml = (content: string, original: string) => {
    const map: number[] = [];
    const plainChars: string[] = [];
    let inTag = false;

    for (let i = 0; i < content.length; i += 1) {
        const ch = content[i];
        if (ch === '<') {
            inTag = true;
            continue;
        }
        if (inTag) {
            if (ch === '>') inTag = false;
            continue;
        }
        plainChars.push(ch);
        map.push(i);
    }

    const plain = plainChars.join('');
    const idx = plain.indexOf(original);
    if (idx === -1) return null;

    const start = map[idx];
    const end = map[idx + original.length - 1] + 1;
    return { start, end };
};

const findRangeInText = (content: string, original: string) => {
    const idx = content.indexOf(original);
    if (idx === -1) return null;
    return { start: idx, end: idx + original.length };
};

export type CanvasState = 'hidden' | 'normal' | 'expanded';
export type CanvasTab = 'editor' | 'process' | 'audit';
export type SectionStatus = 'pending' | 'generating' | 'done' | 'review' | 'error';
export type CitationStatus = 'valid' | 'suspicious' | 'hallucination' | 'warning';

interface HistoryEntry {
    content: string;
    label: string;
    timestamp: number;
}

interface OutlineSection {
    id: string;
    title: string;
    status: SectionStatus;
    level?: number;
}

interface PendingSuggestion {
    id: string;
    from: number;
    to: number;
    original: string;
    replacement: string;
    label: string;
    agent?: string;
}

interface CitationAudit {
    citation: string;
    status: CitationStatus;
    message?: string;
    position?: { from: number; to: number };
}

interface CanvasStore {
    state: CanvasState;
    activeTab: CanvasTab;
    content: string;
    metadata: any;
    costInfo: any;
    // Context-aware chat: selected text from canvas
    selectedText: string;
    pendingAction: 'improve' | 'shorten' | null;
    // Granular undo history
    contentHistory: HistoryEntry[];
    historyIndex: number;
    // Outline navigation
    outline: OutlineSection[];
    outlineCollapsed: boolean;
    // Suggestion mode (diff-based edits)
    pendingSuggestions: PendingSuggestion[];
    highlightedText: string | null;
    // Citation audit badges
    citationAudit: CitationAudit[];

    setState: (state: CanvasState) => void;
    setActiveTab: (tab: CanvasTab) => void;
    setContent: (content: string) => void;
    setMetadata: (metadata: any, costInfo: any) => void;
    showCanvas: () => void;
    hideCanvas: () => void;
    toggleExpanded: () => void;
    // Context-aware chat actions
    setSelectedText: (text: string, action?: 'improve' | 'shorten' | null) => void;
    clearSelectedText: () => void;
    // Granular undo actions
    pushHistory: (content: string, label: string) => void;
    undo: () => void;
    redo: () => void;
    canUndo: () => boolean;
    canRedo: () => boolean;
    // Outline actions
    setOutline: (sections: OutlineSection[]) => void;
    updateSectionStatus: (sectionId: string, status: SectionStatus) => void;
    toggleOutline: () => void;
    // Suggestion actions
    proposeSuggestion: (suggestion: Omit<PendingSuggestion, 'id'>) => void;
    acceptSuggestion: (id: string) => void;
    rejectSuggestion: (id: string) => void;
    clearSuggestions: () => void;
    applyTextReplacement: (original: string, replacement: string, label?: string) => { success: boolean; reason?: string };
    setHighlightedText: (text: string | null) => void;
    // Citation audit actions
    setCitationAudit: (citations: CitationAudit[]) => void;
    clearCitationAudit: () => void;
}

export const useCanvasStore = create<CanvasStore>((set, get) => ({
    state: 'hidden',
    activeTab: 'editor',
    content: '',
    metadata: null,
    costInfo: null,
    selectedText: '',
    pendingAction: null,
    contentHistory: [],
    historyIndex: -1,
    outline: [],
    outlineCollapsed: false,
    pendingSuggestions: [],
    highlightedText: null,
    citationAudit: [],

    setState: (state) => set({ state }),
    setActiveTab: (tab) => set({ activeTab: tab }),
    setContent: (content) => set({ content, state: content ? 'normal' : 'hidden' }),
    setMetadata: (metadata, costInfo) => set({ metadata, costInfo }),
    showCanvas: () => set({ state: 'normal' }),
    hideCanvas: () => set({ state: 'hidden' }),
    toggleExpanded: () => set((store) => ({
        state: store.state === 'expanded' ? 'normal' : 'expanded'
    })),
    setSelectedText: (text, action = null) => set({ selectedText: text, pendingAction: action }),
    clearSelectedText: () => set({ selectedText: '', pendingAction: null }),

    // Push a new history entry (called when AI makes changes)
    pushHistory: (content, label) => set((store) => {
        const newHistory = store.historyIndex >= 0
            ? store.contentHistory.slice(0, store.historyIndex + 1)
            : [];
        newHistory.push({ content, label, timestamp: Date.now() });
        if (newHistory.length > 50) newHistory.shift();
        return {
            contentHistory: newHistory,
            historyIndex: newHistory.length - 1,
            content
        };
    }),

    undo: () => set((store) => {
        if (store.historyIndex <= 0) return store;
        const newIndex = store.historyIndex - 1;
        return {
            historyIndex: newIndex,
            content: store.contentHistory[newIndex].content
        };
    }),

    redo: () => set((store) => {
        if (store.historyIndex >= store.contentHistory.length - 1) return store;
        const newIndex = store.historyIndex + 1;
        return {
            historyIndex: newIndex,
            content: store.contentHistory[newIndex].content
        };
    }),

    canUndo: () => get().historyIndex > 0,
    canRedo: () => get().historyIndex < get().contentHistory.length - 1,

    // Outline actions
    setOutline: (sections) => set({ outline: sections }),
    updateSectionStatus: (sectionId, status) => set((store) => ({
        outline: store.outline.map(s =>
            s.id === sectionId ? { ...s, status } : s
        )
    })),
    toggleOutline: () => set((store) => ({ outlineCollapsed: !store.outlineCollapsed })),

    // Suggestion actions
    proposeSuggestion: (suggestion) => set((store) => ({
        pendingSuggestions: [
            ...store.pendingSuggestions,
            { ...suggestion, id: `suggestion-${Date.now()}` }
        ]
    })),
    acceptSuggestion: (id) => set((store) => {
        const suggestion = store.pendingSuggestions.find(s => s.id === id);
        if (!suggestion) return store;
        // Apply the replacement to content
        const newContent = store.content.slice(0, suggestion.from) +
            suggestion.replacement +
            store.content.slice(suggestion.to);
        return {
            content: newContent,
            pendingSuggestions: store.pendingSuggestions.filter(s => s.id !== id)
        };
    }),
    rejectSuggestion: (id) => set((store) => ({
        pendingSuggestions: store.pendingSuggestions.filter(s => s.id !== id)
    })),
    clearSuggestions: () => set({ pendingSuggestions: [] }),
    applyTextReplacement: (original, replacement, label = 'Sugestão aplicada') => {
        const content = get().content || '';
        if (!content.trim() || !original?.trim() || !replacement?.trim()) {
            return { success: false, reason: 'missing' };
        }

        const isHtml = looksLikeHtml(content);
        const range = isHtml ? findRangeInHtml(content, original) : findRangeInText(content, original);
        if (!range) {
            return { success: false, reason: 'not_found' };
        }

        const safeReplacement = isHtml
            ? escapeHtml(replacement).replace(/\n/g, '<br/>')
            : replacement;
        const newContent = content.slice(0, range.start) + safeReplacement + content.slice(range.end);
        get().pushHistory(newContent, label);
        return { success: true };
    },
    setHighlightedText: (text) => set({ highlightedText: text }),

    // Citation audit actions
    setCitationAudit: (citations) => set({ citationAudit: citations }),
    clearCitationAudit: () => set({ citationAudit: [] }),
}));
