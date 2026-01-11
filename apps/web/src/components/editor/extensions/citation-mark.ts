'use client';
/**
 * Citation Mark Extension for TipTap
 * 
 * Renders inline citation badges with status:
 * - 🟢 valid: Citation verified in RAG/jurisprudence database
 * - 🟡 suspicious: Citation found but may be incorrect
 * - 🔴 hallucination: Citation not found, likely AI hallucination
 */

import { Mark, mergeAttributes } from '@tiptap/core';

export interface CitationMarkOptions {
    HTMLAttributes: Record<string, any>;
}

declare module '@tiptap/core' {
    interface Commands<ReturnType> {
        citationMark: {
            setCitation: (attributes: { status: string; message?: string; citationId?: string }) => ReturnType;
            unsetCitation: () => ReturnType;
        };
    }
}

const statusConfig = {
    valid: {
        badge: '🟢',
        bgColor: 'bg-green-100',
        textColor: 'text-green-700',
        borderColor: 'border-green-300',
    },
    suspicious: {
        badge: '🟡',
        bgColor: 'bg-yellow-100',
        textColor: 'text-yellow-700',
        borderColor: 'border-yellow-300',
    },
    hallucination: {
        badge: '🔴',
        bgColor: 'bg-red-100',
        textColor: 'text-red-700',
        borderColor: 'border-red-300',
    },
    warning: {
        badge: '⚠️',
        bgColor: 'bg-orange-100',
        textColor: 'text-orange-700',
        borderColor: 'border-orange-300',
    },
};

export const CitationMark = Mark.create<CitationMarkOptions>({
    name: 'citationMark',

    addOptions() {
        return {
            HTMLAttributes: {},
        };
    },

    addAttributes() {
        return {
            status: {
                default: 'valid',
                parseHTML: (element) => element.getAttribute('data-citation-status'),
                renderHTML: (attributes) => ({
                    'data-citation-status': attributes.status,
                }),
            },
            message: {
                default: null,
                parseHTML: (element) => element.getAttribute('data-citation-message'),
                renderHTML: (attributes) => {
                    if (!attributes.message) return {};
                    return { 'data-citation-message': attributes.message };
                },
            },
            citationId: {
                default: null,
                parseHTML: (element) => element.getAttribute('data-citation-id'),
                renderHTML: (attributes) => {
                    if (!attributes.citationId) return {};
                    return { 'data-citation-id': attributes.citationId };
                },
            },
        };
    },

    parseHTML() {
        return [
            {
                tag: 'span[data-citation-status]',
            },
        ];
    },

    renderHTML({ HTMLAttributes }) {
        const status = HTMLAttributes['data-citation-status'] || 'valid';
        const config = statusConfig[status as keyof typeof statusConfig] || statusConfig.valid;

        return [
            'span',
            mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
                class: `citation-mark inline-flex items-center gap-0.5 px-1 py-0.5 rounded border cursor-pointer transition-all hover:shadow-sm ${config.bgColor} ${config.textColor} ${config.borderColor}`,
                title: HTMLAttributes['data-citation-message'] || `Citação ${status}`,
            }),
            ['span', { class: 'citation-badge text-xs' }, config.badge],
            ['span', { class: 'citation-text' }, 0], // 0 = render content
        ];
    },

    addCommands() {
        return {
            setCitation:
                (attributes) =>
                    ({ commands }) => {
                        return commands.setMark(this.name, attributes);
                    },
            unsetCitation:
                () =>
                    ({ commands }) => {
                        return commands.unsetMark(this.name);
                    },
        };
    },
});

export default CitationMark;
