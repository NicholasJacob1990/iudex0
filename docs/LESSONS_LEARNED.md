# LESSONS_LEARNED.md — Lições Aprendidas

> Documente aqui erros, bugs sutis e soluções encontradas.
> Este arquivo serve como base de conhecimento para evitar repetir erros.

---

## 2026-01-27 — OpenAI Reasoning Models nao suportam temperature

### Problema
- Chamadas ao OpenAI `o4-mini-deep-research` falhavam com 400: "Unsupported parameter: 'temperature' is not supported with this model"

### Causa Raiz
- `deep_research_service.py` passava `temperature=0.2` hardcoded em todas as chamadas OpenAI
- Modelos reasoning (o1, o3, o4) nao aceitam temperature

### Solucao
- Detectar modelo reasoning por prefixo (`o1`, `o3`, `o4`)
- Omitir `temperature` para esses modelos em ambos os paths (sync e streaming)

### Prevencao
- Sempre verificar compatibilidade de parametros por familia de modelo
- OpenAI reasoning models: sem temperature, sem top_p, effort minimo "medium"

### Arquivos Relacionados
- `apps/api/app/services/ai/deep_research_service.py` (linhas ~487, ~950)
- `apps/api/app/services/ai/deep_research_hard_service.py` (effort "low" -> "medium" para OpenAI)

---

## 2026-01-29 — Falsos positivos de “Tema XXXX” por erro de ASR (Whisper)

### Problema
- Auditoria/Qualidade geravam alerts do tipo `missing_julgado` para “Tema 234”/“Tema 1933”, que não faziam sentido (ou eram variantes erradas do ASR).
- Em alguns casos, a extração de referências não reconhecia `Tema 1.234` (com separador) e produzia diferenças artificiais RAW vs formatado.

### Causa Raiz
- O texto RAW pode conter números “Tema” inconsistentes por erro de ASR (ex.: perda do dígito inicial `234` vs `1234`, ou erro em um dígito `1933` vs `1033`).
- A comparação de referências era sensível à pontuação (`1.234` vs `1234`) e/ou não filtrava variações típicas de ASR.

### Solução
- Normalização de “Tema” na extração de referências (ex.: `Tema 1.234` → `tema 1234`) para comparar por dígitos.
- Filtro conservador em `missing_julgados` para não levantar alertas quando há evidência interna no formatado:
  - `234` é tratado como variante de `1234` se `1234` já aparece.
  - Um `tema` 4-dígitos é ignorado como “missing” quando existe outro tema 4-dígitos muito próximo (Hamming ≤ 1) no formatado.
- Sanitização final do markdown para remover/normalizar variantes erradas quando a forma canônica já está no documento.
- Normalização opcional no texto RAW (ASR) + overrides configuráveis.

### Prevenção
- Preferir normalização por dígitos (não por string literal) ao comparar referências numéricas.
- Para confusões conhecidas, usar overrides via:
  - `VOMO_ASR_NORMALIZE_TEMAS` (default: `true`)
  - `VOMO_ASR_TEMA_OVERRIDES` (ex.: `"1933=1033,234=1234"`)

### Arquivos Relacionados
- `mlx_vomo.py`
- `auto_fix_apostilas.py`
- `apps/api/app/services/quality_service.py`

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

## 2026-01-26 — load_dotenv timing bug desabilitava diarização

### Problema
- Diarização de áudio (pyannote) nunca executava apesar de estar instalada
- `HF_TOKEN` sempre era `None` mesmo com valor no `.env`

### Causa Raiz
- Variável `HF_TOKEN` era lida no nível de módulo (linha 195): `HF_TOKEN = os.getenv("HUGGING_FACE_TOKEN")`
- `load_dotenv()` só era chamado depois, dentro do `__init__` de uma classe (linha 4137)
- Quando o módulo é importado, o código no nível de módulo executa primeiro → `HF_TOKEN = None`
- Quando `__init__` chama `load_dotenv()`, já é tarde — a variável global já foi definida

### Solução
- Mover `load_dotenv()` para o início do módulo, antes de qualquer `os.getenv()`

### Prevenção
- **Regra**: Sempre chamar `load_dotenv()` no início absoluto do módulo, antes de qualquer `os.getenv()`
- Se uma variável de ambiente é usada no nível de módulo, garantir que `.env` já foi carregado
- Ou usar lazy loading: `HF_TOKEN = None` no módulo e `HF_TOKEN = HF_TOKEN or os.getenv(...)` quando precisar

### Arquivos Relacionados
- `mlx_vomo.py`

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
