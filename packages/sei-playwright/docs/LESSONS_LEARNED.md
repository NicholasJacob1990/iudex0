# Lessons Learned - sei-playwright

## 2026-01-24 — Seletores CSS vs Estrutura Real do DOM

### Problema
Login não funcionava no SEI MG - campos de senha e órgão não eram preenchidos.

### Causa Raiz
1. **Campos duplicados com seletores ambíguos**: O SEI MG tem dois inputs de senha:
   - Um oculto (`display: none`) com `name="pwdSenha"`
   - Um visível com `id="pwdSenha"` e `class="masked"`

   O seletor `input[name="pwdSenha"]` capturava o campo **oculto**.

2. **SelectOption por valor vs label**: `page.selectOption(sel, "CODEMGE")` não funcionava
   porque "CODEMGE" é o texto visível, não o atributo `value` (que era "86").

### Solução
```typescript
// Antes (errado)
senha: '#pwdSenha, input[name="pwdSenha"]'
await page.selectOption(selector, orgaoValue);

// Depois (correto)
senha: 'input#pwdSenha.masked, input#pwdSenha:not([type="password"]), ...'
await page.selectOption(selector, { label: orgaoValue });
```

### Prevenção
- **Sempre investigar a estrutura real do DOM** antes de definir seletores
- **Usar snapshot de acessibilidade** (`page.accessibility.snapshot()`) para entender elementos
- **Testar seletores em ambiente real** antes de assumir que funcionam
- **Para selects**: Verificar se o valor passado é `value` ou `label` da option

### Arquivos Relacionados
- `src/browser/selectors.ts`
- `src/browser/client.ts`
