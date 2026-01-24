# Documentacao da API RAG - Iudex

Esta documentacao descreve os endpoints da API RAG para busca, ingestao e gerenciamento de documentos.

## Base URL

```
/api/rag
```

## Autenticacao

Todos os endpoints requerem autenticacao via JWT Bearer token:

```http
Authorization: Bearer <token>
```

---

## Endpoints

### POST /rag/search

Executa busca semantica hibrida (lexical + vetorial) com processamento completo do pipeline RAG.

#### Request

```json
{
  "query": "Art. 37 da CF responsabilidade civil do Estado",
  "tenant_id": "tenant-123",
  "case_id": "case-456",
  "group_ids": ["group-a", "group-b"],
  "user_id": "user-789",
  "use_hyde": true,
  "use_multiquery": true,
  "use_crag": true,
  "use_rerank": true,
  "force_vector": false,
  "top_k": 10,
  "fetch_k": 50,
  "include_trace": false
}
```

#### Parametros

| Campo | Tipo | Obrigatorio | Descricao |
|-------|------|-------------|-----------|
| `query` | string | Sim | Query de busca (1-10000 caracteres) |
| `tenant_id` | string | Sim | Identificador do tenant |
| `case_id` | string | Nao | ID do caso para filtrar documentos locais |
| `group_ids` | string[] | Nao | IDs de grupos para acesso a documentos compartilhados |
| `user_id` | string | Nao | ID do usuario (usa usuario autenticado se omitido) |
| `use_hyde` | boolean | Nao | Ativar HyDE query expansion (usa config padrao se omitido) |
| `use_multiquery` | boolean | Nao | Ativar multi-query expansion |
| `use_crag` | boolean | Nao | Ativar CRAG quality gate |
| `use_rerank` | boolean | Nao | Ativar reranking por cross-encoder |
| `force_vector` | boolean | Nao | Forcar busca vetorial mesmo se lexical for suficiente |
| `top_k` | integer | Nao | Numero de resultados (1-100, padrao: 10) |
| `fetch_k` | integer | Nao | Candidatos a buscar (1-500, padrao: 50) |
| `include_trace` | boolean | Nao | Incluir trace de execucao na resposta |

#### Response

```json
{
  "results": [
    {
      "chunk_id": "chunk-abc-123",
      "text": "Art. 37. A administracao publica direta e indireta de qualquer dos Poderes da Uniao...",
      "score": 0.892,
      "metadata": {
        "source": "constituicao_federal",
        "title": "Art. 37 CF",
        "page": 15,
        "dataset": "lei"
      },
      "source": "lei",
      "highlight": "A administracao <em>publica</em> direta e indireta..."
    }
  ],
  "mode": "hybrid",
  "trace": {
    "request_id": "req-xyz-789",
    "started_at": "2024-01-15T10:30:00.000Z",
    "completed_at": "2024-01-15T10:30:01.234Z",
    "duration_ms": 1234.5,
    "stages": [
      {
        "stage": "lexical_search",
        "duration_ms": 45.2,
        "input_count": 1,
        "output_count": 50
      }
    ],
    "lexical_score": 0.85,
    "vector_score": 0.72,
    "rerank_applied": true,
    "hyde_applied": true,
    "multiquery_applied": false,
    "crag_passed": true
  },
  "metadata": {
    "total_candidates": 100,
    "filtered_count": 10,
    "query_expansion_count": 2,
    "cache_hit": false
  }
}
```

#### Modos de Busca

| Mode | Descricao |
|------|-----------|
| `lexical_only` | Apenas busca lexical foi usada (lexical-first gating ativado) |
| `hybrid` | Busca lexical + vetorial combinadas via RRF |
| `vector_only` | Apenas busca vetorial (raro, geralmente fallback) |

#### Codigos de Resposta

| Codigo | Descricao |
|--------|-----------|
| 200 | Sucesso |
| 400 | Request invalido (query vazia, parametros fora do range) |
| 401 | Nao autenticado |
| 500 | Erro interno (falha no pipeline) |
| 503 | Servico RAG indisponivel |

---

### POST /rag/ingest/local

Ingere documentos locais associados a um caso especifico.

#### Request

```json
{
  "tenant_id": "tenant-123",
  "case_id": "case-456",
  "documents": [
    {
      "text": "Conteudo do documento anexado ao caso...",
      "metadata": {
        "filename": "contrato.pdf",
        "page": 1,
        "source_type": "attachment"
      },
      "doc_id": "doc-optional-id"
    }
  ],
  "chunk_size": 512,
  "chunk_overlap": 50
}
```

#### Parametros

| Campo | Tipo | Obrigatorio | Descricao |
|-------|------|-------------|-----------|
| `tenant_id` | string | Sim | Identificador do tenant |
| `case_id` | string | Sim | ID do caso para associacao |
| `documents` | array | Sim | Lista de documentos (1-1000) |
| `documents[].text` | string | Sim | Conteudo do documento |
| `documents[].metadata` | object | Nao | Metadados adicionais |
| `documents[].doc_id` | string | Nao | ID do documento (auto-gerado se omitido) |
| `chunk_size` | integer | Nao | Tamanho do chunk em tokens (100-2000, padrao: 512) |
| `chunk_overlap` | integer | Nao | Sobreposicao entre chunks (0-500, padrao: 50) |

#### Response

```json
{
  "indexed_count": 5,
  "chunk_uids": [
    "chunk-abc-001",
    "chunk-abc-002",
    "chunk-abc-003",
    "chunk-abc-004",
    "chunk-abc-005"
  ],
  "skipped_count": 0,
  "errors": []
}
```

#### Codigos de Resposta

| Codigo | Descricao |
|--------|-----------|
| 200 | Sucesso (pode ter erros parciais) |
| 400 | Request invalido |
| 401 | Nao autenticado |
| 500 | Erro de ingestao |

---

### POST /rag/ingest/global

Ingere documentos em datasets globais (legislacao, jurisprudencia, etc).

**Requer permissoes elevadas** (admin ou `rag:ingest:global`).

#### Request

```json
{
  "dataset": "lei",
  "documents": [
    {
      "text": "Lei 8.666/93 - Art. 1o Esta Lei estabelece normas gerais...",
      "metadata": {
        "numero": "8666",
        "ano": 1993,
        "tipo": "lei_federal",
        "ementa": "Normas para licitacoes e contratos"
      }
    }
  ],
  "chunk_size": 512,
  "chunk_overlap": 50,
  "deduplicate": true
}
```

#### Parametros

| Campo | Tipo | Obrigatorio | Descricao |
|-------|------|-------------|-----------|
| `dataset` | enum | Sim | Dataset alvo: `lei`, `juris`, `pecas`, `sei` |
| `documents` | array | Sim | Lista de documentos (1-5000) |
| `chunk_size` | integer | Nao | Tamanho do chunk (100-2000, padrao: 512) |
| `chunk_overlap` | integer | Nao | Sobreposicao (0-500, padrao: 50) |
| `deduplicate` | boolean | Nao | Pular documentos duplicados (padrao: true) |

#### Datasets Disponiveis

| Dataset | Descricao | Indices |
|---------|-----------|---------|
| `lei` | Legislacao (leis, decretos, resolucoes) | `rag-lei`, `lei` |
| `juris` | Jurisprudencia (acordaos, decisoes) | `rag-juris`, `juris` |
| `pecas` | Pecas processuais modelo | `rag-pecas_modelo`, `pecas_modelo` |
| `sei` | Documentos internos (pareceres, notas) | `rag-sei`, `sei` |

#### Response

```json
{
  "indexed_count": 150,
  "chunk_uids": ["chunk-001", "chunk-002", "..."],
  "skipped_count": 5,
  "errors": [
    {
      "doc_index": "12",
      "doc_id": "lei-xyz",
      "error": "Document text is empty"
    }
  ]
}
```

#### Codigos de Resposta

| Codigo | Descricao |
|--------|-----------|
| 200 | Sucesso |
| 400 | Request invalido |
| 401 | Nao autenticado |
| 403 | Permissao negada (requer admin) |
| 500 | Erro de ingestao |

---

### DELETE /rag/local/{case_id}

Remove todos os chunks locais associados a um caso.

#### Parametros de URL

| Parametro | Tipo | Descricao |
|-----------|------|-----------|
| `case_id` | string | ID do caso |

#### Query Parameters

| Parametro | Tipo | Obrigatorio | Descricao |
|-----------|------|-------------|-----------|
| `tenant_id` | string | Sim | Tenant ID para verificacao |

#### Request

```http
DELETE /api/rag/local/case-456?tenant_id=tenant-123
Authorization: Bearer <token>
```

#### Response

```json
{
  "deleted_count": 25,
  "case_id": "case-456"
}
```

#### Codigos de Resposta

| Codigo | Descricao |
|--------|-----------|
| 200 | Sucesso (mesmo se nenhum documento deletado) |
| 400 | Parametros invalidos |
| 401 | Nao autenticado |
| 500 | Erro na delecao |

---

### GET /rag/stats

Retorna estatisticas do pipeline RAG.

#### Request

```http
GET /api/rag/stats
Authorization: Bearer <token>
```

#### Response

```json
{
  "cache_stats": {
    "enabled": true,
    "hits": 1523,
    "misses": 4821,
    "size": 150,
    "ttl_seconds": 30
  },
  "trace_stats": {
    "enabled": true,
    "total_traces": 15420,
    "avg_duration_ms": 856.3
  },
  "collections": {
    "lei": 125000,
    "juris": 450000,
    "pecas_modelo": 5000,
    "sei": 12000,
    "local_chunks": 35000
  },
  "last_updated": "2024-01-15T10:30:00.000Z"
}
```

---

## Schemas

### SearchResultItem

```typescript
interface SearchResultItem {
  chunk_id: string;      // ID unico do chunk
  text: string;          // Conteudo do chunk
  score: number;         // Score de relevancia (0-1)
  metadata: object;      // Metadados do documento
  source?: string;       // Collection/dataset de origem
  highlight?: string;    // Snippet com highlight
}
```

### TraceInfo

```typescript
interface TraceInfo {
  request_id: string;
  started_at: string;      // ISO timestamp
  completed_at: string;    // ISO timestamp
  duration_ms: number;
  stages: StageTrace[];
  lexical_score?: number;
  vector_score?: number;
  rerank_applied: boolean;
  hyde_applied: boolean;
  multiquery_applied: boolean;
  crag_passed?: boolean;
}
```

### StageTrace

```typescript
interface StageTrace {
  stage: string;           // Nome do estagio
  duration_ms: number;
  input_count: number;
  output_count: number;
  data?: object;           // Dados especificos do estagio
  error?: string;
  skipped: boolean;
  skip_reason?: string;
}
```

### DocumentInput

```typescript
interface DocumentInput {
  text: string;            // Conteudo (obrigatorio)
  metadata?: object;       // Metadados opcionais
  doc_id?: string;         // ID opcional (auto-gerado)
}
```

---

## Exemplos de Uso

### Python (requests)

```python
import requests

BASE_URL = "https://api.iudex.com/api"
TOKEN = "your_jwt_token"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# Busca simples
response = requests.post(
    f"{BASE_URL}/rag/search",
    headers=headers,
    json={
        "query": "Art. 5 da Constituicao Federal direitos fundamentais",
        "tenant_id": "my-tenant",
        "top_k": 5
    }
)
results = response.json()

for item in results["results"]:
    print(f"Score: {item['score']:.3f} - {item['text'][:100]}...")
```

### JavaScript (fetch)

```javascript
const BASE_URL = "https://api.iudex.com/api";
const TOKEN = "your_jwt_token";

// Busca com opcoes avancadas
const response = await fetch(`${BASE_URL}/rag/search`, {
  method: "POST",
  headers: {
    "Authorization": `Bearer ${TOKEN}`,
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    query: "responsabilidade civil objetiva do Estado",
    tenant_id: "my-tenant",
    case_id: "case-123",
    use_hyde: true,
    use_rerank: true,
    include_trace: true,
    top_k: 10
  })
});

const data = await response.json();

console.log(`Mode: ${data.mode}`);
console.log(`Duration: ${data.trace?.duration_ms}ms`);
console.log(`Results: ${data.results.length}`);
```

### cURL

```bash
# Busca
curl -X POST "https://api.iudex.com/api/rag/search" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Lei 8.666 licitacao dispensa",
    "tenant_id": "tenant-123",
    "top_k": 5
  }'

# Ingestao local
curl -X POST "https://api.iudex.com/api/rag/ingest/local" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "tenant-123",
    "case_id": "case-456",
    "documents": [
      {
        "text": "Contrato de prestacao de servicos...",
        "metadata": {"filename": "contrato.pdf"}
      }
    ]
  }'

# Estatisticas
curl -X GET "https://api.iudex.com/api/rag/stats" \
  -H "Authorization: Bearer $TOKEN"

# Deletar chunks de um caso
curl -X DELETE "https://api.iudex.com/api/rag/local/case-456?tenant_id=tenant-123" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Codigos de Erro

### Erros de Validacao (400)

```json
{
  "detail": [
    {
      "loc": ["body", "query"],
      "msg": "ensure this value has at least 1 characters",
      "type": "value_error.any_str.min_length"
    }
  ]
}
```

### Erro de Autenticacao (401)

```json
{
  "detail": "Could not validate credentials"
}
```

### Erro de Permissao (403)

```json
{
  "detail": "Global ingestion requires elevated permissions"
}
```

### Erro Interno (500)

```json
{
  "detail": "Search failed: Connection to OpenSearch timed out"
}
```

### Servico Indisponivel (503)

```json
{
  "detail": "RAG service unavailable. Check server configuration."
}
```

---

## Rate Limiting

Os endpoints de RAG possuem rate limiting por tenant:

| Endpoint | Limite |
|----------|--------|
| `/rag/search` | 100 req/min |
| `/rag/ingest/local` | 20 req/min |
| `/rag/ingest/global` | 10 req/min |
| `/rag/stats` | 60 req/min |

Headers de rate limit na resposta:

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1705315860
```

---

## Webhooks (Futuro)

Endpoints de webhook para notificacoes assincronas de ingestao estao planejados:

- `POST /rag/webhooks/ingest-complete`
- `POST /rag/webhooks/index-ready`

---

## Changelog

### v1.0.0 (2024-01)

- Release inicial da API RAG
- Endpoints de busca, ingestao e stats
- Suporte a busca hibrida (lexical + vetorial)
- CRAG quality gate
- Multi-tenant isolation
