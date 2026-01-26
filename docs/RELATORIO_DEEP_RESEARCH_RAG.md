# Relatório: Integração de Deep Research APIs com RAG e Vector Search (2025-2026)

> Gerado em: 2026-01-24

## Sumário Executivo

Este relatório analisa os padrões de integração entre APIs de Deep Research (Google Gemini, Perplexity, OpenAI) e sistemas RAG com vector databases externos, com recomendações específicas para o projeto Iudex.

---

## 1. Padrões de Integração por Provider

### 1.1 Google Gemini + RAG Externo

#### Arquitetura Disponível

O Google oferece **três abordagens distintas** para integração RAG:

1. **Gemini File Search Tool (Nov 2025)**
   - Sistema RAG totalmente gerenciado integrado à Gemini API
   - Elimina necessidade de Pinecone/ChromaDB externos para casos simples
   - Gera citações automaticamente vinculando respostas aos documentos fonte
   - [Fonte: DataCamp Tutorial](https://www.datacamp.com/tutorial/google-file-search-tool)

2. **Vertex AI RAG Engine**
   - Suporta **integração nativa** com vector databases externos:
     - **Pinecone**: Configuração via Secret Manager para API key, mapeamento 1:1 entre RAG corpus e Pinecone index
     - **Weaviate**: Suporte a hybrid search (dense + sparse), mapeamento 1:1 corpus/collection
   - Parâmetros configuráveis: `SIMILARITY_TOP_K`, `VECTOR_DISTANCE_THRESHOLD`
   - **Limitação**: Não é possível mudar tipo de vector database após criação
   - [Fonte: Google Cloud Docs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/vector-db-choices)

3. **Grounding com Custom Search API**
   - Permite conectar **qualquer serviço de busca** como fonte de grounding
   - Suporta até 10 fontes de grounding por request
   - Combinável com Google Search
   - Requer resposta JSON com campos `snippet` e `uri`
   - [Fonte: Google Cloud Docs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/grounding/grounding-with-your-search-api)

4. **Gemini Deep Research via Interactions API (Dez 2025)**
   - Disponível via `agent="deep-research-pro-preview-12-2025"`
   - Suporta File Upload e File Search Tool para documentos próprios
   - Background execution mode com polling assíncrono
   - **Limitação atual**: Não suporta custom Function Calling ou MCP servers
   - [Fonte: Google Developers Blog](https://blog.google/innovation-and-ai/technology/developers-tools/deep-research-agent-gemini-api/)

#### Padrão Recomendado para Iudex

```
Query → RAG Pipeline (Qdrant/OpenSearch) → Context Injection → Gemini Deep Research
                                                               ↓
                                          Grounding com Custom Search API
                                          (apontando para API própria do Iudex)
```

---

### 1.2 Perplexity Sonar + RAG

#### Características do sonar-deep-research

- **Modelo de pesquisa multi-step** que busca, lê e avalia centenas de fontes automaticamente
- Retorna citações numeradas com URLs e metadados por padrão
- Suporta grandes context windows para multi-document synthesis
- [Fonte: Perplexity Docs](https://docs.perplexity.ai/getting-started/models/models/sonar-deep-research)

#### Limitações com Dados Privados

**Crítico**: O Perplexity Sonar **não oferece integração nativa** com vector databases externos ou documentos privados via API. As opções são:

1. **Context Injection**: Enviar documentos resumidos no prompt (limitado por tokens)
2. **Spaces (UI)**: Feature disponível apenas na interface web, não via API
3. **Hybrid Pattern**: Combinar busca web do Perplexity com RAG interno

#### Padrão Híbrido Recomendado

```
                    ┌─────────────────────────────────────┐
                    │           Query Original            │
                    └───────────────┬─────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            ↓                       ↓                       ↓
    ┌───────────────┐       ┌───────────────┐       ┌───────────────┐
    │ Perplexity    │       │ RAG Pipeline  │       │  Knowledge    │
    │ (Web Search)  │       │ (Internal KB) │       │    Graph      │
    └───────┬───────┘       └───────┬───────┘       └───────┬───────┘
            │                       │                       │
            └───────────────────────┼───────────────────────┘
                                    ↓
                    ┌─────────────────────────────────────┐
                    │   Reciprocal Rank Fusion (RRF)      │
                    │   + Cross-encoder Reranking         │
                    └───────────────┬─────────────────────┘
                                    ↓
                    ┌─────────────────────────────────────┐
                    │        LLM Final Response           │
                    └─────────────────────────────────────┘
```

[Fonte: Vespa.ai Case Study](https://vespa.ai/perplexity/)

---

### 1.3 OpenAI + RAG

#### Responses API vs Assistants API

**Importante**: A Assistants API está **deprecated** e será desligada em **26 de agosto de 2026**. A migração para Responses API é obrigatória.

| Aspecto | Assistants API | Responses API |
|---------|---------------|---------------|
| Status | Deprecated | Recomendada |
| Estado | Stateful (threads) | Stateless por padrão |
| File Search | Sim | Sim + metadata filtering |
| Vector Store | Built-in da OpenAI | Built-in da OpenAI |
| Pricing | Re-processa todo o thread | File Search separado |

[Fonte: OpenAI Developer Blog](https://developers.openai.com/blog/responses-api/)

#### Integração com Vector DBs Externos

A OpenAI **não oferece integração nativa** com Pinecone/Qdrant no file_search. O padrão é:

1. Usar OpenAI Embeddings (`text-embedding-3-large`)
2. Armazenar em Pinecone/Qdrant
3. Construir pipeline RAG próprio
4. Injetar contexto no prompt

**Pinecone + OpenAI**:
- Pinecone oferece MCP (Model Context Protocol) para AI assistants
- Permite upsert, query e manage de índices via agents
- [Fonte: Pinecone Docs](https://docs.pinecone.io/integrations/openai)

---

## 2. Arquiteturas Híbridas: Deep Research + RAG

### 2.1 Quando Usar Cada Abordagem

| Cenário | Abordagem Recomendada |
|---------|----------------------|
| Informação pública/atual | Deep Research (web) |
| Legislação específica (ex: Art. 5º CF) | RAG interno (lexical-first) |
| Jurisprudência recente | Híbrido (RAG + web search) |
| Documentos do cliente | RAG interno apenas |
| Pesquisa exploratória | Deep Research + RAG fusion |

### 2.2 Fusion Ranking: RRF

O **Reciprocal Rank Fusion (RRF)** é o método padrão para combinar resultados de múltiplas fontes:

```python
def rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)

# Combinação de fontes:
final_score = (
    lexical_weight * rrf_score(lexical_rank) +
    vector_weight * rrf_score(vector_rank) +
    web_weight * rrf_score(web_rank)
)
```

**Benefícios**:
- Não requer calibração de scores entre fontes
- Robusto para scales incompatíveis
- k ≈ 60 funciona bem na maioria dos casos
- [Fonte: MongoDB RRF Guide](https://www.mongodb.com/resources/basics/reciprocal-rank-fusion)

### 2.3 Hierarquia de Fusion (HF-RAG)

Padrão avançado de 2025:

1. **Within-source fusion**: RRF dentro de cada fonte (lexical, vector, web)
2. **Score standardization**: Z-score para normalizar escalas
3. **Cross-source fusion**: RRF final entre fontes normalizadas

[Fonte: Arxiv RAG Survey](https://arxiv.org/html/2506.00054v1)

---

## 3. Análise do RAG Atual do Iudex

### 3.1 Pontos Fortes Existentes

Baseado na análise de `/apps/api/app/services/rag/`:

1. **Pipeline Bem Estruturado**:
   - 10 estágios claramente definidos
   - CRAG Gate com retry logic
   - Lexical-first gating para citações jurídicas
   - RRF já implementado

2. **Storage Dual**:
   - OpenSearch (lexical/BM25)
   - Qdrant (vector/semantic)
   - Hybrid search nativo

3. **Features Avançadas**:
   - HyDE (Hypothetical Document Embeddings)
   - Multi-query expansion
   - Cross-encoder reranking
   - Knowledge Graph enrichment (NetworkX + Neo4j)
   - Context compression

4. **Deep Research Service**:
   - Suporta Google Gemini e Perplexity
   - Streaming via SSE
   - Caching de resultados
   - Fallback entre providers

### 3.2 Gaps Identificados

1. **Sem fusion web + interno**: Deep Research e RAG operam separadamente
2. **Sem grounding customizado**: Gemini não recebe contexto do RAG interno
3. **Perplexity sem contexto privado**: Não injeta documentos no prompt
4. **Sem reranking cross-source**: RRF apenas entre lexical/vector

---

## 4. Recomendações para o Iudex

### 4.1 Arquitetura Proposta: Unified Hybrid Research

```
                         ┌──────────────────────────────────────┐
                         │            Query Router              │
                         │   (Classifica tipo de pesquisa)      │
                         └───────────────┬──────────────────────┘
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        │                                │                                │
        ↓                                ↓                                ↓
┌───────────────────┐          ┌───────────────────┐          ┌───────────────────┐
│   RAG Pipeline    │          │   Deep Research   │          │  Knowledge Graph  │
│                   │          │                   │          │                   │
│ • Lexical (OS)    │          │ • Gemini/Pplx    │          │ • Neo4j           │
│ • Vector (Qdrant) │          │ • Web grounding   │          │ • Entity linking  │
│ • CRAG gate       │          │ • Streaming       │          │ • Multi-hop       │
└─────────┬─────────┘          └─────────┬─────────┘          └─────────┬─────────┘
          │                              │                              │
          └──────────────────────────────┼──────────────────────────────┘
                                         ↓
                         ┌──────────────────────────────────────┐
                         │        Unified Fusion Layer          │
                         │                                      │
                         │  1. Normalize sources (z-score)      │
                         │  2. RRF across all sources           │
                         │  3. Cross-encoder rerank top-N       │
                         │  4. Dedup by chunk_uid               │
                         └───────────────┬──────────────────────┘
                                         ↓
                         ┌──────────────────────────────────────┐
                         │         Context Assembly             │
                         │                                      │
                         │  • Token budget management           │
                         │  • Citation formatting               │
                         │  • Source attribution                │
                         └───────────────┬──────────────────────┘
                                         ↓
                         ┌──────────────────────────────────────┐
                         │          LLM Generation              │
                         └──────────────────────────────────────┘
```

### 4.2 Implementação por Provider

#### Google Gemini

```python
# 1. Configurar Custom Search API Endpoint
# Em apps/api/app/api/endpoints/grounding_search.py

@router.post("/grounding-search")
async def grounding_search(query: str, top_k: int = 10):
    """Endpoint para Gemini Grounding."""
    pipeline = RAGPipeline()
    results = await pipeline.search(query, top_k=top_k)

    # Formato requerido pelo Gemini
    return [
        {"snippet": r["text"][:500], "uri": r.get("source_url", "")}
        for r in results.results
    ]

# 2. Configurar no Gemini
grounding_config = {
    "grounding_with_external_search": {
        "endpoint": "https://api.iudex.com/grounding-search",
        "api_key_secret_name": "projects/xxx/secrets/iudex-grounding-key"
    }
}
```

#### Perplexity

```python
# Injetar contexto do RAG no prompt
async def hybrid_perplexity_research(query: str):
    # 1. Buscar contexto interno
    rag_results = await rag_pipeline.search(query, top_k=5)

    # 2. Construir prompt com contexto
    context = "\n".join([
        f"[Documento {i+1}]: {r['text'][:400]}"
        for i, r in enumerate(rag_results.results)
    ])

    enhanced_prompt = f"""
    Contexto interno da base jurídica:
    {context}

    Pergunta do usuário: {query}

    Pesquise informações adicionais na web e combine com o contexto fornecido.
    """

    # 3. Chamar Perplexity
    return await deep_research_service.run_research_task(
        enhanced_prompt,
        config={"provider": "perplexity"}
    )
```

#### OpenAI (Responses API)

```python
# Usar vector store interno + Responses API
async def openai_rag_response(query: str):
    # 1. Buscar no Qdrant
    embeddings = await get_embeddings_service().embed(query)
    qdrant_results = await qdrant.search(embeddings, top_k=10)

    # 2. Formatar contexto
    context = format_rag_context(qdrant_results)

    # 3. Chamar Responses API
    response = await openai.responses.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": f"Use este contexto: {context}"},
            {"role": "user", "content": query}
        ],
        tools=[{"type": "file_search"}]  # Para docs adicionais
    )
```

### 4.3 Modificações no RAGConfig

```python
# Em apps/api/app/services/rag/config.py

@dataclass
class RAGConfig:
    # ... existing fields ...

    # === Deep Research Integration ===
    enable_deep_research_fusion: bool = True
    deep_research_weight_in_rrf: float = 0.3
    deep_research_max_sources: int = 5

    # Grounding API
    grounding_api_endpoint: str = ""
    grounding_api_key_secret: str = ""

    # Hybrid mode
    hybrid_research_mode: str = "parallel"  # "parallel" | "sequential" | "conditional"
    web_search_for_recent_threshold_days: int = 30
```

### 4.4 Custos e Latência Comparativos

| Operação | Latência Típica | Custo Estimado |
|----------|----------------|----------------|
| RAG Pipeline (Iudex) | 500-1500ms | ~$0.002/query |
| Perplexity sonar-deep-research | 15-45s | ~$0.05/query |
| Gemini Deep Research | 30-120s | ~$0.10/query |
| Gemini grounding (search) | 1-3s | ~$0.01/query |

**Recomendação**: Usar Deep Research apenas para queries complexas que exigem pesquisa web extensiva. Para a maioria das consultas jurídicas, o RAG interno é suficiente e muito mais rápido/barato.

---

## 5. Próximos Passos Sugeridos

### Fase 1: Fusion Layer (2-3 dias)
1. Criar `UnifiedFusionService` que combina resultados de múltiplas fontes
2. Implementar z-score normalization entre fontes
3. Adicionar cross-source RRF

### Fase 2: Grounding API (1-2 dias)
1. Criar endpoint `/api/grounding-search` para Gemini
2. Configurar Vertex AI com custom grounding
3. Testar com Deep Research agent

### Fase 3: Perplexity Hybrid (1 dia)
1. Modificar `deep_research_service.py` para injetar contexto RAG
2. Implementar summarization do contexto antes de enviar

### Fase 4: Query Router (2 dias)
1. Classificador ML para decidir entre RAG-only, Deep Research, ou Híbrido
2. Considerar: tipo de query, idade da informação necessária, complexidade

---

## Fontes Consultadas

- [Google RAG Engine API Docs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/rag-api)
- [Google File Search Tool Tutorial](https://www.datacamp.com/tutorial/google-file-search-tool)
- [Gemini Deep Research Agent](https://blog.google/innovation-and-ai/technology/developers-tools/deep-research-agent-gemini-api/)
- [Vertex AI Grounding Overview](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/grounding/overview)
- [Perplexity Sonar Deep Research](https://docs.perplexity.ai/getting-started/models/models/sonar-deep-research)
- [Perplexity Architecture 2025](https://vespa.ai/perplexity/)
- [OpenAI Responses API](https://developers.openai.com/blog/responses-api/)
- [OpenAI Vector Stores Reference](https://platform.openai.com/docs/api-reference/vector-stores)
- [Pinecone + OpenAI Integration](https://docs.pinecone.io/integrations/openai)
- [RAG-Fusion Paper](https://arxiv.org/abs/2402.03367)
- [Reciprocal Rank Fusion Guide](https://www.mongodb.com/resources/basics/reciprocal-rank-fusion)
- [RAG Survey 2025](https://arxiv.org/html/2506.00054v1)
- [Hybrid RAG Systems](https://medium.com/@adnanmasood/hybrid-retrieval-augmented-generation-systems-for-knowledge-intensive-tasks-10347cbe83ab)
