'use client';
/**
 * Suggestion Highlight Extension for TipTap
 * 
 * Used for diff-based AI edits:
 * - Insertions: Green background
 * - Deletions: Red strikethrough
 * - Pending: Yellow background (awaiting accept/reject)
 */

import { Mark, mergeAttributes } from '@tiptap/core';

export interface SuggestionHighlightOptions {
    HTMLAttributes: Record<string, any>;
}

declare module '@tiptap/core' {
    interface Commands<ReturnType> {
        suggestionHighlight: {
            setSuggestion: (attributes: { type: 'insertion' | 'deletion' | 'pending'; suggestionId?: string }) => ReturnType;
            unsetSuggestion: () => ReturnType;
        };
    }
}

const typeConfig = {
    insertion: {
        bgColor: 'bg-green-100',
        textColor: 'text-green-800',
        decoration: '',
        icon: '+',
    },
    deletion: {
        bgColor: 'bg-red-100',
        textColor: 'text-red-800 line-through',
        decoration: 'line-through',
        icon: '-',
    },
    pending: {
        bgColor: 'bg-yellow-100',
        textColor: 'text-yellow-800',
        decoration: '',
        icon: '?',
    },
};

export const SuggestionHighlight = Mark.create<SuggestionHighlightOptions>({
    name: 'suggestionHighlight',

    addOptions() {
        return {
            HTMLAttributes: {},
        };
    },

    addAttributes() {
        return {
            type: {
                default: 'pending',
                parseHTML: (element) => element.getAttribute('data-suggestion-type'),
                renderHTML: (attributes) => ({
                    'data-suggestion-type': attributes.type,
                }),
            },
            suggestionId: {
                default: null,
                parseHTML: (element) => element.getAttribute('data-suggestion-id'),
                renderHTML: (attributes) => {
                    if (!attributes.suggestionId) return {};
                    return { 'data-suggestion-id': attributes.suggestionId };
                },
            },
        };
    },

    parseHTML() {
        return [
            {
                tag: 'span[data-suggestion-type]',
            },
        ];
    },

    renderHTML({ HTMLAttributes }) {
        const type = HTMLAttributes['data-suggestion-type'] || 'pending';
        const config = typeConfig[type as keyof typeof typeConfig] || typeConfig.pending;

        return [
            'span',
            mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
                class: `suggestion-highlight px-0.5 rounded ${config.bgColor} ${config.textColor} ${config.decoration}`,
            }),
            0,
        ];
    },

    addCommands() {
        return {
            setSuggestion:
                (attributes) =>
                    ({ commands }) => {
                        return commands.setMark(this.name, attributes);
                    },
            unsetSuggestion:
                () =>
                    ({ commands }) => {
                        return commands.unsetMark(this.name);
                    },
        };
    },
});

export default SuggestionHighlight;
