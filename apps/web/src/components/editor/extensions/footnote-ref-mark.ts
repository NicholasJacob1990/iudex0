'use client';
/**
 * Footnote Reference Mark (TipTap)
 *
 * Purpose: render numeric citations like [1] as superscript-style footnote markers
 * in the canvas editor, without changing the underlying Markdown source.
 *
 * We use a simple HTML form:
 *   <span data-footnote-ref="1">1</span>
 */

import { Mark, mergeAttributes } from '@tiptap/core';

export interface FootnoteRefMarkOptions {
  HTMLAttributes: Record<string, any>;
}

export const FootnoteRefMark = Mark.create<FootnoteRefMarkOptions>({
  name: 'footnoteRef',

  addOptions() {
    return {
      HTMLAttributes: {},
    };
  },

  addAttributes() {
    return {
      number: {
        default: null,
        parseHTML: (element) => element.getAttribute('data-footnote-ref'),
        renderHTML: (attributes) => {
          if (!attributes.number) return {};
          return { 'data-footnote-ref': String(attributes.number) };
        },
      },
    };
  },

  parseHTML() {
    return [{ tag: 'span[data-footnote-ref]' }];
  },

  renderHTML({ HTMLAttributes }) {
    const n = HTMLAttributes['data-footnote-ref'] || '';
    return [
      'span',
      mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
        class:
          'iudex-footnote-ref align-super text-[10px] leading-none font-semibold text-muted-foreground px-0.5',
        title: n ? `Nota de rodapé ${n}` : 'Nota de rodapé',
      }),
      0,
    ];
  },
});

export default FootnoteRefMark;

