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

const normalizeHeading = (value: string) =>
    (value || '').replace(/\s+/g, ' ').trim().toLowerCase();

const deriveOutlineFromContent = (content: string): OutlineSection[] => {
    const raw = String(content || '');
    if (!raw.trim()) return [];

    const sections: OutlineSection[] = [];
    const looksHtml = looksLikeHtml(raw);

    if (looksHtml) {
        // Match headings and keep match.index as from-offset (same coordinate system as pendingSuggestions.from/to).
        const re = /<h([1-6])[^>]*>([\s\S]*?)<\/h\1>/gi;
        let m: RegExpExecArray | null = null;
        while ((m = re.exec(raw)) !== null) {
            const level = Number(m[1]) || 1;
            const inner = String(m[2] || '');
            const title = inner.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
            if (!title) continue;
            sections.push({
                id: `sec-${sections.length}-${m.index}`,
                title,
                status: 'done',
                level,
                from: m.index,
            });
        }
        return sections;
    }

    // Markdown headings
    const re = /(^|\n)(#{1,6})\s+([^\n]+)/g;
    let m: RegExpExecArray | null = null;
    while ((m = re.exec(raw)) !== null) {
        const hashes = m[2] || '#';
        const level = Math.min(6, Math.max(1, hashes.length));
        const title = String(m[3] || '').trim();
        if (!title) continue;
        // m.index points to the start of (^|\n), so move into the actual heading line.
        const from = m.index + (m[1] ? m[1].length : 0);
        sections.push({
            id: `sec-${sections.length}-${from}`,
            title,
            status: 'done',
            level,
            from,
        });
    }
    return sections;
};

const mergeOutline = (existing: OutlineSection[], derived: OutlineSection[]) => {
    if (!derived.length) return existing || [];
    const byKey = new Map<string, OutlineSection>();
    const titleCounts = new Map<string, number>();

    (existing || []).forEach((s) => {
        const normalized = normalizeHeading(s.title);
        const key = `${s.level ?? 1}:${normalized}`;
        byKey.set(key, s);
        titleCounts.set(normalized, (titleCounts.get(normalized) || 0) + 1);
    });

    const byTitle = new Map<string, OutlineSection>();
    (existing || []).forEach((s) => {
        const normalized = normalizeHeading(s.title);
        if (titleCounts.get(normalized) === 1) {
            byTitle.set(normalized, s);
        }
    });

    return derived.map((d) => {
        const normalized = normalizeHeading(d.title);
        const key = `${d.level ?? 1}:${normalized}`;
        const prev = byKey.get(key) || byTitle.get(normalized);
        if (!prev) return d;
        return {
            ...prev,
            title: d.title,
            level: d.level ?? prev.level,
            from: typeof d.from === 'number' ? d.from : prev.from,
        };
    });
};

export type CanvasState = 'hidden' | 'normal' | 'expanded';
export type CanvasTab = 'editor' | 'process' | 'audit' | 'quality';
export type SectionStatus = 'pending' | 'generating' | 'done' | 'review' | 'error';
export type CitationStatus = 'valid' | 'suspicious' | 'hallucination' | 'warning';
export type PendingAction = 'improve' | 'shorten' | 'rewrite' | 'formalize' | 'ground' | 'ementa' | 'verify' | null;

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
    // Offset no conteúdo (mesma base de índice usada por pendingSuggestions.from/to)
    from?: number;
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
    lastEditedAt: number | null;
    // Context-aware chat: selected text from canvas
    selectedText: string;
    selectionRange: { from: number; to: number } | null;
    selectionContext: { before: string; after: string } | null;
    pendingEdit: { original: string; replacement: string; range?: { from: number; to: number }; label?: string } | null;
    pendingAction: PendingAction;
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
    setSelectedText: (
        text: string,
        action?: 'improve' | 'shorten' | null,
        range?: { from: number; to: number } | null,
        context?: { before: string; after: string } | null
    ) => void;
    clearSelectedText: () => void;
    clearPendingEdit: () => void;
    // Granular undo actions
    pushHistory: (content: string, label: string) => void;
    undo: () => void;
    redo: () => void;
    canUndo: () => boolean;
    canRedo: () => boolean;
    // Outline actions
    syncOutlineFromTitles: (titles: Array<string | { title?: string; label?: string; name?: string; level?: number; status?: SectionStatus }>) => void;
    setOutline: (sections: OutlineSection[]) => void;
    updateSectionStatus: (sectionId: string, status: SectionStatus) => void;
    toggleOutline: () => void;
    // Suggestion actions
    proposeSuggestion: (suggestion: Omit<PendingSuggestion, 'id'>) => void;
    acceptSuggestion: (id: string) => void;
    rejectSuggestion: (id: string) => void;
    acceptAllSuggestions: () => { applied: number; skipped: number };
    rejectAllSuggestions: () => number;
    acceptSuggestionsByIds: (ids: string[]) => { applied: number; skipped: number };
    rejectSuggestionsByIds: (ids: string[]) => number;
    clearSuggestions: () => void;
    applyTextReplacement: (original: string, replacement: string, label?: string, rangeOverride?: { from: number; to: number } | null) => { success: boolean; reason?: string };
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
    lastEditedAt: null,
    selectedText: '',
    selectionRange: null,
    selectionContext: null,
    pendingEdit: null,
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
    setContent: (content) => set((store) => {
        const derived = deriveOutlineFromContent(content);
        const merged = mergeOutline(store.outline, derived);
        return {
            content,
            state: content ? 'normal' : 'hidden',
            lastEditedAt: Date.now(),
            outline: merged,
        };
    }),
    setMetadata: (metadata, costInfo) => set({ metadata, costInfo }),
    showCanvas: () => set({ state: 'normal' }),
    hideCanvas: () => set({ state: 'hidden' }),
    toggleExpanded: () => set((store) => ({
        state: store.state === 'expanded' ? 'normal' : 'expanded'
    })),
    setSelectedText: (text, action = null, range = null, context = null) => set({
        selectedText: text,
        pendingAction: action,
        selectionRange: range,
        selectionContext: context
    }),
    clearSelectedText: () => set({ selectedText: '', pendingAction: null, selectionRange: null, selectionContext: null }),
    clearPendingEdit: () => set({ pendingEdit: null }),

    // Push a new history entry (called when AI makes changes)
    pushHistory: (content, label) => set((store) => {
        const newHistory = store.historyIndex >= 0
            ? store.contentHistory.slice(0, store.historyIndex + 1)
            : [];
        newHistory.push({ content, label, timestamp: Date.now() });
        if (newHistory.length > 50) newHistory.shift();
        const derived = deriveOutlineFromContent(content);
        const merged = mergeOutline(store.outline, derived);
        return {
            contentHistory: newHistory,
            historyIndex: newHistory.length - 1,
            content,
            lastEditedAt: Date.now(),
            outline: merged,
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
    syncOutlineFromTitles: (titles) => set((store) => {
        const entries = Array.isArray(titles) ? titles : [];
        const baseSections = entries
            .map((entry, idx) => {
                const rawTitle = typeof entry === 'string'
                    ? entry
                    : entry?.title || entry?.label || entry?.name;
                const title = String(rawTitle || '').trim();
                if (!title) return null;
                const level = typeof entry === 'object' ? entry?.level : undefined;
                const status = (typeof entry === 'object' && entry?.status ? entry.status : 'done') as SectionStatus;
                return {
                    id: `outline-${idx}-${normalizeHeading(title)}`,
                    title,
                    status,
                    level,
                };
            })
            .filter(Boolean) as OutlineSection[];

        if (!baseSections.length) {
            return { outline: store.outline };
        }

        const withExisting = mergeOutline(store.outline, baseSections);
        const derived = deriveOutlineFromContent(store.content);
        const merged = mergeOutline(withExisting, derived);
        return { outline: merged };
    }),
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
    acceptAllSuggestions: () => {
        const store = get();
        const content = store.content || '';
        if (!store.pendingSuggestions.length || !content) return { applied: 0, skipped: 0 };

        // Apply from the end towards the beginning to keep ranges stable.
        const sorted = [...store.pendingSuggestions].sort((a, b) => b.from - a.from);

        const accepted: PendingSuggestion[] = [];
        let lastFrom = Number.POSITIVE_INFINITY;
        for (const s of sorted) {
            // Only accept non-overlapping ranges (conservative).
            if (s.to <= lastFrom) {
                accepted.push(s);
                lastFrom = s.from;
            }
        }

        let next = content;
        for (const s of accepted) {
            next = next.slice(0, s.from) + s.replacement + next.slice(s.to);
        }

        // Persist change as one history entry for clean undo.
        store.pushHistory(next, `Aplicar sugestões (${accepted.length})`);

        const acceptedIds = new Set(accepted.map(s => s.id));
        set((prev) => ({
            pendingSuggestions: prev.pendingSuggestions.filter(s => !acceptedIds.has(s.id)),
        }));

        return { applied: accepted.length, skipped: store.pendingSuggestions.length - accepted.length };
    },
    rejectAllSuggestions: () => {
        const count = get().pendingSuggestions.length;
        set({ pendingSuggestions: [] });
        return count;
    },
    acceptSuggestionsByIds: (ids) => {
        const store = get();
        const content = store.content || '';
        if (!ids?.length || !store.pendingSuggestions.length || !content) return { applied: 0, skipped: 0 };

        const setIds = new Set(ids);
        const picked = store.pendingSuggestions.filter((s) => setIds.has(s.id));
        if (!picked.length) return { applied: 0, skipped: 0 };

        const sorted = [...picked].sort((a, b) => b.from - a.from);

        const accepted: PendingSuggestion[] = [];
        let lastFrom = Number.POSITIVE_INFINITY;
        for (const s of sorted) {
            if (s.to <= lastFrom) {
                accepted.push(s);
                lastFrom = s.from;
            }
        }

        let next = content;
        for (const s of accepted) {
            next = next.slice(0, s.from) + s.replacement + next.slice(s.to);
        }

        store.pushHistory(next, `Aplicar sugestões (${accepted.length})`);

        const acceptedIds = new Set(accepted.map(s => s.id));
        set((prev) => ({
            pendingSuggestions: prev.pendingSuggestions.filter(s => !acceptedIds.has(s.id)),
        }));

        return { applied: accepted.length, skipped: picked.length - accepted.length };
    },
    rejectSuggestionsByIds: (ids) => {
        if (!ids?.length) return 0;
        const setIds = new Set(ids);
        const before = get().pendingSuggestions.length;
        set((prev) => ({
            pendingSuggestions: prev.pendingSuggestions.filter(s => !setIds.has(s.id)),
        }));
        const after = get().pendingSuggestions.length;
        return Math.max(0, before - after);
    },
    clearSuggestions: () => set({ pendingSuggestions: [] }),
    applyTextReplacement: (original, replacement, label = 'Sugestão aplicada', rangeOverride = null) => {
        const range = rangeOverride;
        if (range && range.from !== range.to) {
            set({ pendingEdit: { original, replacement, range, label } });
            return { success: true, reason: 'pending' };
        }

        const content = get().content || '';
        if (!content.trim() || !original?.trim() || !replacement?.trim()) {
            return { success: false, reason: 'missing' };
        }

        const isHtml = looksLikeHtml(content);
        const foundRange = isHtml ? findRangeInHtml(content, original) : findRangeInText(content, original);
        if (!foundRange) {
            return { success: false, reason: 'not_found' };
        }

        const safeReplacement = isHtml
            ? escapeHtml(replacement).replace(/\n/g, '<br/>')
            : replacement;
        const newContent = content.slice(0, foundRange.start) + safeReplacement + content.slice(foundRange.end);
        get().pushHistory(newContent, label);
        return { success: true };
    },
    setHighlightedText: (text) => set({ highlightedText: text }),

    // Citation audit actions
    setCitationAudit: (citations) => set({ citationAudit: citations }),
    clearCitationAudit: () => set({ citationAudit: [] }),
}));
