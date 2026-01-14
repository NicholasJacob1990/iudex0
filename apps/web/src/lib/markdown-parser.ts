
import { marked } from 'marked';
import createDOMPurify from 'dompurify';

// ---------------------------------------------------------------------------
// Segurança básica: impede HTML bruto e URLs perigosas (ex.: javascript:)
// Observação: isso NÃO substitui um sanitizer completo (ex.: DOMPurify),
// mas já elimina os vetores mais óbvios sem adicionar dependências.
// ---------------------------------------------------------------------------

function escapeHtml(raw: string): string {
    return (raw || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function isSafeUrl(href: string): boolean {
    const v = (href || '').trim().toLowerCase();
    if (!v) return false;
    // bloqueia esquemas perigosos
    if (v.startsWith('javascript:')) return false;
    if (v.startsWith('data:')) return false;
    if (v.startsWith('vbscript:')) return false;
    return true;
}

let configured = false;
function configureMarkedOnce() {
    if (configured) return;
    configured = true;

    // Desabilitar mangle e ids automáticos para saída mais previsível
    marked.setOptions({
        mangle: false,
        headerIds: false,
        gfm: true,
        breaks: true,
    } as any);

    // Override do renderer para bloquear HTML bruto e higienizar links/imagens
    marked.use({
        renderer: {
            // HTML inline no markdown: renderiza como texto escapado (não executa)
            html(token: any) {
                return escapeHtml(token?.text || '');
            },
            link(href: string | null, title: string | null, text: string) {
                const safeHref = href && isSafeUrl(href) ? href : '#';
                const safeTitle = title ? escapeHtml(title) : '';
                return `<a href="${escapeHtml(safeHref)}"${safeTitle ? ` title="${safeTitle}"` : ''} target="_blank" rel="noreferrer noopener">${text}</a>`;
            },
            image(href: string | null, title: string | null, text: string) {
                // imagens podem vazar requests; mantém apenas se URL for segura (http/https)
                const safeHref = href && isSafeUrl(href) && href.startsWith('http') ? href : '';
                if (!safeHref) return '';
                const safeTitle = title ? escapeHtml(title) : '';
                const alt = escapeHtml(text || '');
                return `<img src="${escapeHtml(safeHref)}" alt="${alt}"${safeTitle ? ` title="${safeTitle}"` : ''} />`;
            },
        } as any,
    });
}

// ---------------------------------------------------------------------------
// Sanitização completa: DOMPurify (client-side).
// Importante: `markdown-parser.ts` é usado por componentes "use client".
// Mesmo assim, evitamos acessar `window` fora de runtime do browser.
// ---------------------------------------------------------------------------

let domPurifyInstance: ReturnType<typeof createDOMPurify> | null = null;
function getDomPurify() {
    if (domPurifyInstance) return domPurifyInstance;
    if (typeof window === 'undefined') return null;
    domPurifyInstance = createDOMPurify(window);
    return domPurifyInstance;
}

function sanitizeHtml(html: string): string {
    const dp = getDomPurify();
    if (!dp) return html;

    // Perfil HTML padrão + permitir atributos úteis para links externos
    return dp.sanitize(html, {
        USE_PROFILES: { html: true },
        ADD_ATTR: ['target', 'rel'],
    }) as string;
}

/**
 * Converts Markdown string to HTML for use in TipTap editor.
 * Ensures basic formatting (headers, bold, lists) is preserved.
 */
export async function parseMarkdownToHtml(markdown: string): Promise<string> {
    if (!markdown) return '';

    configureMarkedOnce();
    // Configure marked for safe/standard output if needed
    // For now default async parsing
    const html = await marked.parse(markdown, { async: true });
    return sanitizeHtml(html);
}

/**
 * Sync version if needed (marked 11+ is async by default but can be sync)
 */
export function parseMarkdownToHtmlSync(markdown: string): string {
    if (!markdown) return '';
    configureMarkedOnce();
    const html = marked.parse(markdown, { async: false }) as string;
    return sanitizeHtml(html);
}
