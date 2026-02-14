# Melhorias Opcionais: Markdown Parser

> Sugestões para melhorias futuras no `markdown-parser.ts` baseadas na análise de 2026-02-11.

## Contexto

A análise atual mostra que o parser está funcionando corretamente, mas existem algumas melhorias opcionais que podem ser consideradas dependendo dos requisitos.

## Opção 1: Detectar e Alertar sobre HTML Tables

**Caso de uso:** Se você quer que os usuários saibam quando o LLM gerou HTML tables (que serão escapadas).

### Implementação

```typescript
// Add to markdown-parser.ts

export function containsHtmlTables(markdown: string): boolean {
    return /<table\b/i.test(markdown);
}

export function parseMarkdownToHtmlSync(markdown: string): string {
    if (!markdown) return '';

    configureMarkedOnce();

    // Warn if HTML tables detected
    if (containsHtmlTables(markdown)) {
        console.warn(
            'WARNING: Markdown contains HTML <table> tags. ' +
            'These will be escaped and appear as text. ' +
            'Consider using pipe tables instead: | Col1 | Col2 |'
        );
    }

    const html = marked.parse(markdown, { async: false }) as string;
    return sanitizeHtml(html);
}
```

### Uso no Frontend

```typescript
import { parseMarkdownToHtmlSync, containsHtmlTables } from '@/lib/markdown-parser';
import { toast } from 'sonner';

function renderMarkdown(markdown: string) {
    if (containsHtmlTables(markdown)) {
        toast.warning('Document contains HTML tables - they may not render properly. Consider regenerating with pipe tables.');
    }
    return parseMarkdownToHtmlSync(markdown);
}
```

## Opção 2: Converter HTML Tables para Pipe Tables

**Caso de uso:** Se você quer suportar automaticamente HTML tables geradas por LLM.

### Instalação

```bash
npm install html-table-parser turndown
```

### Implementação

```typescript
import TurndownService from 'turndown';

const turndownService = new TurndownService({
    headingStyle: 'atx',
    codeBlockStyle: 'fenced',
});

export function normalizeHtmlTables(markdown: string): string {
    // Only process if HTML tables detected
    if (!/<table\b/i.test(markdown)) {
        return markdown;
    }

    // Replace HTML tables with Turndown-converted markdown
    return markdown.replace(/<table[\s\S]*?<\/table>/gi, (htmlTable) => {
        try {
            const markdownTable = turndownService.turndown(htmlTable);
            return markdownTable;
        } catch (err) {
            console.warn('Failed to convert HTML table, keeping original:', err);
            return htmlTable;
        }
    });
}

export function parseMarkdownToHtmlSync(markdown: string): string {
    if (!markdown) return '';

    configureMarkedOnce();

    // Normalize HTML tables to pipe tables
    const normalizedMarkdown = normalizeHtmlTables(markdown);

    const html = marked.parse(normalizedMarkdown, { async: false }) as string;
    return sanitizeHtml(html);
}
```

**Avaliação:** Adiciona complexidade; usar apenas se necessário.

## Opção 3: Suporte a Table de Customização

**Caso de uso:** Se você quiser renderizar tabelas com estilos customizados (ex: zebra striping).

### Implementação

```typescript
marked.use({
    renderer: {
        table(token: any) {
            // Override default table rendering
            let body = token.rows
                .map((row: any) => {
                    const cells = row
                        .map((cell: any) => `<td>${(this as any).parseInline(cell.tokens)}</td>`)
                        .join('');
                    return `<tr>${cells}</tr>`;
                })
                .join('');

            return `<table class="markdown-table zebra">\n${body}\n</table>`;
        },
    } as any,
});
```

### CSS Correspondente

```css
.markdown-table.zebra tbody tr:nth-child(odd) {
    background-color: rgba(0, 0, 0, 0.02);
}

.markdown-table.zebra tbody tr:hover {
    background-color: rgba(0, 0, 0, 0.05);
}

.markdown-table.zebra th {
    background-color: rgba(0, 0, 0, 0.08);
    font-weight: 600;
}
```

## Opção 4: Validar Estrutura de Tabelas

**Caso de uso:** Garantir que tabelas GFM estão bem formadas.

```typescript
export function validateGfmTable(markdown: string): {
    isValid: boolean;
    errors: string[];
} {
    const errors: string[] = [];

    // Simple check: pipe table deve ter pelo menos header + separator + 1 row
    const lines = markdown.split('\n');
    const pipeLines = lines.filter(line => line.includes('|'));

    if (pipeLines.length < 2) {
        errors.push('Table must have at least header and separator rows');
    }

    if (pipeLines.length >= 2) {
        const headerLine = pipeLines[0];
        const separatorLine = pipeLines[1];

        const headerCols = (headerLine.match(/\|/g) || []).length;
        const separatorCols = (separatorLine.match(/\|/g) || []).length;

        if (headerCols !== separatorCols) {
            errors.push('Header and separator rows must have same number of columns');
        }

        if (!/^\|?[\s-|]+\|?$/.test(separatorLine)) {
            errors.push('Separator row must contain only dashes and pipes');
        }
    }

    return {
        isValid: errors.length === 0,
        errors,
    };
}
```

## Comparação das Opções

| Opção | Complexidade | Benefício | Recomendação |
|-------|--------------|-----------|--------------|
| 1. Detectar HTML tables | Baixa | Alertar usuário | ✓ Fácil de adicionar |
| 2. Converter HTML → Markdown | Alta | Suporte automático | ✗ Adiciona dependências |
| 3. Customizar estilos | Média | Melhor UX visual | ✓ Se for relevante |
| 4. Validar estrutura | Média | Garantir qualidade | ✗ Só se necessário |

## Recomendação

**Manter o código atual** a menos que você encontre problemas específicos com:
1. Usuários gerando HTML tables
2. Tabelas com estilos inadequados
3. Erros de validação de tabelas

Neste caso, adicionar **Opção 1 (Detecção)** é a mais simples e não impactante.

## Testes para Validar Melhorias

Se implementar qualquer opção acima, executar:

```bash
node scripts/test-markdown-tables.js
```

Para garantir que as mudanças não quebram o comportamento existente.
