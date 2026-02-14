/**
 * Test suite: parseMarkdownToHtmlSync with GFM tables
 *
 * These tests verify that:
 * 1. GFM pipe tables parse correctly despite breaks: true
 * 2. HTML tables are properly escaped for security
 * 3. Mixed markdown + tables work as expected
 *
 * Key Finding: marked v17.0.1 with breaks: true does NOT interfere with table parsing.
 * Tables are recognized as block-level elements before breaks are applied to inline content.
 */

import { parseMarkdownToHtmlSync } from '../markdown-parser';

describe('parseMarkdownToHtmlSync — GFM Tables', () => {
  describe('Pipe Table Parsing', () => {
    it('should parse simple pipe tables correctly', () => {
      const markdown = `| Col1 | Col2 |
|------|------|
| A    | B    |`;

      const html = parseMarkdownToHtmlSync(markdown);

      expect(html).toContain('<table>');
      expect(html).toContain('<thead>');
      expect(html).toContain('<tbody>');
      expect(html).toContain('Col1');
      expect(html).toContain('Col2');
      expect(html).toContain('<td>A</td>');
      expect(html).toContain('<td>B</td>');
    });

    it('should parse multi-row tables', () => {
      const markdown = `| Name | Age |
|------|-----|
| John | 25  |
| Jane | 30  |`;

      const html = parseMarkdownToHtmlSync(markdown);

      expect(html).toContain('<table>');
      expect(html).toContain('John');
      expect(html).toContain('Jane');
      expect(html).toContain('25');
      expect(html).toContain('30');
    });

    it('should handle tables with double-newline separation from following paragraph', () => {
      const markdown = `| Col1 | Col2 |
|------|------|
| A    | B    |

Paragraph text here`;

      const html = parseMarkdownToHtmlSync(markdown);

      expect(html).toContain('<table>');
      expect(html).toContain('<p>');
      expect(html).toContain('Paragraph text here');
    });

    it('should NOT be broken by breaks: true setting (key test)', () => {
      // markdown-parser.ts uses breaks: true
      // This test ensures it doesn't interfere with table block recognition
      const markdown = `| Header 1 | Header 2 |
|----------|----------|
| Cell 1   | Cell 2   |
| Cell 3   | Cell 4   |`;

      const html = parseMarkdownToHtmlSync(markdown);

      // If breaks: true broke table parsing, we'd see <br> tags within cells
      expect(html).toContain('<table>');
      expect(html).not.toContain('<br>');
      // Count that we have proper structure (2 header cells, 4 data cells)
      const thCount = (html.match(/<th>/g) || []).length;
      const tdCount = (html.match(/<td>/g) || []).length;
      expect(thCount).toBeGreaterThanOrEqual(2);
      expect(tdCount).toBeGreaterThanOrEqual(4);
    });
  });

  describe('HTML Table Security', () => {
    it('should escape raw HTML <table> tags', () => {
      const markdown = '<table><tr><td>A</td><td>B</td></tr></table>';

      const html = parseMarkdownToHtmlSync(markdown);

      // HTML renderer's escapeHtml() should convert < and > to entities
      expect(html).toContain('&lt;table&gt;');
      expect(html).toContain('&lt;/table&gt;');
      expect(html).not.toMatch(/<table[^&]/); // Not an unescaped table tag
    });

    it('should escape HTML tables with attributes', () => {
      const markdown = '<table border="1"><tr><td>Data</td></tr></table>';

      const html = parseMarkdownToHtmlSync(markdown);

      expect(html).toContain('&lt;table');
      expect(html).toContain('border');
      expect(html).toContain('&quot;');
    });

    it('IMPORTANT: HTML tables will appear as text, not visual tables', () => {
      // This documents the current behavior:
      // If an LLM generates <table> HTML, it gets escaped and appears as literal text
      // Solution: Train LLM to generate pipe tables instead
      const markdown = '<table><tr><td>Data</td></tr></table>';
      const html = parseMarkdownToHtmlSync(markdown);

      // Visual table will NOT render; user sees escaped HTML
      expect(html).toMatch(/&lt;table/);
      expect(html).not.toMatch(/<table>/);
    });
  });

  describe('Edge Cases', () => {
    it('should handle empty tables (header only)', () => {
      const markdown = `| Col1 | Col2 |
|------|------|`;

      const html = parseMarkdownToHtmlSync(markdown);

      expect(html).toContain('<table>');
      expect(html).toContain('<thead>');
      // Empty tbody is acceptable
    });

    it('should handle tables with special characters in cell content', () => {
      const markdown = `| Description | Value |
|-------------|-------|
| < Less than | 5     |
| > Greater   | 10    |`;

      const html = parseMarkdownToHtmlSync(markdown);

      expect(html).toContain('<table>');
      expect(html).toContain('Less than');
      expect(html).toContain('Greater');
    });

    it('should handle mixed markdown and pipe tables', () => {
      const markdown = `# Header

Some introductory text.

| Key | Value |
|-----|-------|
| Foo | 100   |

Concluding paragraph.`;

      const html = parseMarkdownToHtmlSync(markdown);

      expect(html).toContain('<h1>');
      expect(html).toContain('introductory text');
      expect(html).toContain('<table>');
      expect(html).toContain('Concluding paragraph');
    });

    it('should handle CRLF line endings (Windows)', () => {
      // marked normalizes line endings internally
      const markdown = '| Col1 | Col2 |\r\n|------|------|\r\n| A    | B    |';

      const html = parseMarkdownToHtmlSync(markdown);

      expect(html).toContain('<table>');
      expect(html).toContain('A');
      expect(html).toContain('B');
    });
  });
});
