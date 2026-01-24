# LESSONS_LEARNED.md — Lições Aprendidas

> Documente aqui erros, bugs sutis e soluções encontradas.
> Este arquivo serve como base de conhecimento para evitar repetir erros.

---

## Template de Entrada

```markdown
## [DATA] — Título Curto do Problema

### Problema
- Descrição do erro/comportamento inesperado

### Causa Raiz
- O que estava causando o problema

### Solução
- Como foi resolvido

### Prevenção
- Como evitar no futuro

### Arquivos Relacionados
- `caminho/arquivo.ts`
```

---

## 2026-01-20 — TipTap SSR Warning

### Problema
- Console alertava sobre SSR/hidratação no editor TipTap

### Causa Raiz
- `immediatelyRender` não estava definido no useEditor

### Solução
- Definir `immediatelyRender: false` no useEditor

### Prevenção
- Sempre configurar immediatelyRender em editores TipTap com Next.js

### Arquivos Relacionados
- `apps/web/src/components/editor/document-editor.tsx`

---

## 2026-01-20 — Next Image Sizes Warning

### Problema
- Logos com next/image em modo fill avisavam sobre ausência de sizes

### Causa Raiz
- Propriedade `sizes` obrigatória quando usando `fill`

### Solução
- Adicionar `sizes="16px"` (ou valor apropriado) nas imagens

### Prevenção
- Sempre definir sizes ao usar fill em next/image

### Arquivos Relacionados
- `apps/web/src/components/chat/model-selector.tsx`

---

## 2026-01-20 — Gemini Streaming Thoughts

### Problema
- Painel "Processo de raciocínio" não recebia streaming no Gemini Flash

### Causa Raiz
- `thinking_mode` precisava ser "high" para streaming de thoughts

### Solução
- Forçar `thinking_mode=high` para modelos Flash com reasoning_level médio/alto

### Prevenção
- Verificar configuração de thinking_mode ao integrar novos modelos

### Arquivos Relacionados
- `apps/api/app/api/endpoints/chats.py`
- `apps/api/app/services/chat_service.py`

---

## 2026-01-24 — TTL Cleanup Nunca Funcionou (Campo Errado)

### Problema
- TTL cleanup do RAG nunca deletava documentos antigos
- OpenSearch e Qdrant acumulavam dados indefinidamente

### Causa Raiz
- `ttl_cleanup.py` buscava campos `ingested_at`, `created_at`, `timestamp`
- OpenSearch e Qdrant usam `uploaded_at` como campo de timestamp na ingestão
- Query com `should` + `minimum_should_match: 1` retornava 0 resultados sempre

### Solução
- Alterar queries para usar `uploaded_at`:
  - OpenSearch: `{"range": {"uploaded_at": {"lt": cutoff_iso}}}`
  - Qdrant: `timestamp_fields = ["uploaded_at"]`

### Prevenção
- Ao criar jobs de cleanup/manutenção, verificar os campos reais gravados na ingestão
- Criar testes que validem os nomes dos campos usados nas queries
- Manter convenção única de timestamp (`uploaded_at`) em todo o sistema RAG

### Arquivos Relacionados
- `apps/api/app/services/rag/utils/ttl_cleanup.py` (cleanup)
- `apps/api/app/services/rag/storage/opensearch_service.py` (ingestão OS)
- `apps/api/app/services/rag/storage/qdrant_service.py` (ingestão Qdrant)

---

<!-- Novas entradas acima desta linha -->
