# Análise: parseMarkdownToHtmlSync e GFM Pipe Tables

> Análise completa sobre o comportamento de `markdown-parser.ts` com tabelas GFM.
> Data: 2026-02-11

## Resumo Executivo

A função `parseMarkdownToHtmlSync()` em `apps/web/src/lib/markdown-parser.ts` está **corretamente implementada** e **segura** para usar com tabelas GFM. Não há interferência do `breaks: true` com tabelas, e HTML bruto é propriamente escapado.

## Questões Investigadas

### 1. O `breaks: true` interfere com a detecção de blocos de tabela GFM?

**Resposta: NÃO**

O parser `marked` v17.0.1 trata tabelas como blocos (block-level) reconhecendo o padrão `| ... |` de forma independente. A opção `breaks: true` afeta apenas conteúdo inline (converte `\n` em `<br>`), após as tabelas já terem sido identificadas como blocos.

**Teste realizado:**
```typescript
const markdown = `| Header 1 | Header 2 |
|----------|----------|
| Cell 1   | Cell 2   |
| Cell 3   | Cell 4   |`;

// WITH breaks: true (current)
const html = marked.parse(markdown, { async: false });
// ✓ Renders correctly as <table> with proper structure
```

**Resultado:** Identêntico com ou sem `breaks: true`.

### 2. O renderer `html()` que escapa HTML causa problemas?

**Resposta: NÃO para segurança, SIM para UX se LLM usar HTML tables**

O código atual:
```javascript
html(token: any) {
    return escapeHtml(token?.text || '');
}
```

Isso significa que qualquer HTML bruto é convertido:
- `<table>` → `&lt;table&gt;` (segurança ✓)
- Mas aparece como **texto literal**, não como tabela visual

**Teste realizado:**
```javascript
const markdown = '<table><tr><td>A</td><td>B</td></tr></table>';
const html = parseMarkdownToHtmlSync(markdown);
// Result: &lt;table&gt;&lt;tr&gt;...&lt;/table&gt;
// ✓ Secure, but appears as text, not a visual table
```

## Comportamentos Observados

### Pipe Tables (Markdown Nativo) ✓

**Funciona corretamente:**
```markdown
| Column A | Column B |
|----------|----------|
| Value 1  | Value 2  |
```

Renderiza como HTML `<table>` visual funcional.

**Casos especiais:**
- Tabelas com múltiplas linhas: ✓ Corretas
- Separação com parágrafo: Requer `\n\n` (double newline) para separar
- Caracteres especiais nas células: ✓ Escape automático

### HTML Tables (Geradas pelo LLM)

**Comportamento atual:**
```markdown
<table><tr><td>Data</td></tr></table>
```

Renderiza como: `&lt;table&gt;&lt;tr&gt;&lt;td&gt;Data&lt;/td&gt;&lt;/tr&gt;&lt;/table&gt;`

**Problema:** Aparece como texto literal, não como tabela visual.

**Solução recomendada:** Treinar/configurar LLM para **gerar pipe tables** em vez de HTML.

## Configuração Atual

```typescript
// apps/web/src/lib/markdown-parser.ts
marked.setOptions({
    mangle: false,        // ✓ Desativa name mangling
    headerIds: false,     // ✓ Headers sem IDs
    gfm: true,           // ✓ GitHub Flavored Markdown
    breaks: true,        // ✓ Newlines → <br> (seguro para tabelas)
});
```

**Avaliação:** **Adequada e segura**

## Recomendações

### 1. Use Pipe Tables para LLM Output
- **Recomendado:** LLM gera markdown pipe tables
- **Evitar:** LLM gera HTML `<table>` bruto (será escapado)

### 2. Adicionar Validação se Necessário
Se quiser detectar/alertar quando LLM gera HTML tables:

```typescript
function hasHtmlTables(markdown: string): boolean {
    return /<table/i.test(markdown);
}
```

### 3. Consideração de Sanitização Adicional
O código já usa **DOMPurify** (`sanitizeHtml()`), que é uma camada de segurança extra além do escaping no renderer. Isso é **ótimo para defesa em profundidade**.

### 4. Testar Edge Cases
Verificado:
- ✓ CRLF line endings (Windows)
- ✓ Empty tables
- ✓ Special characters in cells
- ✓ Mixed markdown + tables
- ✓ HTML escaping (security)

## Conclusão

| Aspecto | Status | Nota |
|---------|--------|------|
| `breaks: true` com tabelas | ✓ Seguro | Sem interferência |
| Pipe tables GFM | ✓ Funciona | Renderiza corretamente |
| HTML tables escapadas | ✓ Seguro | Aparecem como texto (por design) |
| Sanitização | ✓ Dupla camada | HTML escape + DOMPurify |
| **Recomendação** | **Manter atual** | Funciona bem se LLM usar pipe tables |

## Arquivos Relacionados

- `apps/web/src/lib/markdown-parser.ts` — Implementação principal
- `scripts/test-markdown-tables.js` — Script de verificação manual
- `apps/web/src/lib/__tests__/markdown-parser-tables.test.ts` — Suite de testes (Jest)

## Próximos Passos (se necessário)

1. **Se LLM usar HTML tables:** Adicionar prompt engineering para forçar pipe tables
2. **Se quiser detectar:** Usar `hasHtmlTables()` e alertar usuário
3. **Se quiser converter:** Considerar biblioteca como `html-to-markdown` para converter HTML → Markdown
