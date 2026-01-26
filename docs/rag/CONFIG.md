# Referencia de Configuracao RAG - Iudex

Este documento detalha todos os parametros de configuracao do RAG Pipeline, organizados por categoria.

## Carregamento de Configuracao

A configuracao eh carregada automaticamente de variaveis de ambiente:

```python
from app.services.rag.config import get_rag_config

config = get_rag_config()
```

Para resetar (util em testes):

```python
from app.services.rag.config import reset_rag_config

reset_rag_config()
```

---

## Feature Flags

Controlam a ativacao/desativacao de componentes do pipeline.

| Parametro | Env Var | Padrao | Descricao |
|-----------|---------|--------|-----------|
| `enable_crag` | `RAG_ENABLE_CRAG` | `true` | Ativa o CRAG quality gate para validacao de relevancia |
| `enable_hyde` | `RAG_ENABLE_HYDE` | `true` | Ativa HyDE (Hypothetical Document Embedding) para query expansion |
| `enable_multiquery` | `RAG_ENABLE_MULTIQUERY` | `true` | Ativa geracao de multiplas queries alternativas |
| `enable_rerank` | `RAG_ENABLE_RERANK` | `true` | Ativa reordenacao por cross-encoder neural |
| `enable_compression` | `RAG_ENABLE_COMPRESSION` | `true` | Ativa compressao de contexto para caber no token budget |
| `enable_graph_enrich` | `RAG_ENABLE_GRAPH_ENRICH` | `true` | Ativa enriquecimento via knowledge graph |
| `enable_tracing` | `RAG_ENABLE_TRACING` | `true` | Ativa tracing/logging detalhado do pipeline |
| `enable_chunk_expansion` | `RAG_ENABLE_CHUNK_EXPANSION` | `true` | Ativa recuperacao de chunks adjacentes |
| `enable_lexical_first_gating` | `RAG_ENABLE_LEXICAL_FIRST` | `true` | Permite pular busca vetorial se lexical for suficiente |

### Exemplo de Uso

```bash
# Desabilitar CRAG em desenvolvimento
export RAG_ENABLE_CRAG=false

# Desabilitar graph enrichment se Neo4j nao disponivel
export RAG_ENABLE_GRAPH_ENRICH=false
```

---

## CRAG (Corrective RAG)

Configuracoes do gate de qualidade que valida os documentos recuperados.

| Parametro | Env Var | Padrao | Range | Descricao |
|-----------|---------|--------|-------|-----------|
| `crag_min_best_score` | `RAG_CRAG_MIN_BEST_SCORE` | `0.5` | 0.0-1.0 | Score minimo do melhor documento para aceitar |
| `crag_min_avg_score` | `RAG_CRAG_MIN_AVG_SCORE` | `0.35` | 0.0-1.0 | Score medio minimo dos top-N documentos |
| `crag_max_retries` | `RAG_CRAG_MAX_RETRIES` | `2` | 0-5 | Numero maximo de tentativas com query expandida |

### Decisoes do CRAG

- **ACCEPT:** `best_score >= crag_min_best_score` E `avg_score >= crag_min_avg_score`
- **RETRY:** Scores abaixo dos thresholds, tentativas < max_retries
- **REJECT:** Scores baixos apos todas as tentativas

### Exemplo

```bash
# Ser mais rigoroso com qualidade
export RAG_CRAG_MIN_BEST_SCORE=0.6
export RAG_CRAG_MIN_AVG_SCORE=0.45

# Permitir mais retries
export RAG_CRAG_MAX_RETRIES=3
```

---

## Query Expansion

Configuracoes de HyDE e multi-query para melhorar recall.

| Parametro | Env Var | Padrao | Descricao |
|-----------|---------|--------|-----------|
| `hyde_model` | `RAG_HYDE_MODEL` | `gemini-2.0-flash` | Modelo LLM para gerar documento hipotetico |
| `hyde_max_tokens` | `RAG_HYDE_MAX_TOKENS` | `300` | Tokens maximos do documento hipotetico |
| `multiquery_max` | `RAG_MULTIQUERY_MAX` | `3` | Numero maximo de queries alternativas |
| `multiquery_model` | `RAG_MULTIQUERY_MODEL` | `gemini-2.0-flash` | Modelo LLM para gerar queries alternativas |

### Exemplo

```bash
# Usar modelo mais capaz para HyDE
export RAG_HYDE_MODEL=gpt-4o

# Gerar mais queries alternativas
export RAG_MULTIQUERY_MAX=5
```

---

## Reranking

Configuracoes do cross-encoder para reordenacao de precisao.

| Parametro | Env Var | Padrao | Descricao |
|-----------|---------|--------|-----------|
| `rerank_model` | `RAG_RERANK_MODEL` | `cross-encoder/ms-marco-multilingual-MiniLM-L6-H384-v1` | Modelo cross-encoder principal |
| `rerank_model_fallback` | `RAG_RERANK_MODEL_FALLBACK` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Modelo fallback se principal falhar |
| `rerank_batch_size` | `RAG_RERANK_BATCH_SIZE` | `32` | Tamanho do batch para inferencia |
| `rerank_use_fp16` | `RAG_RERANK_USE_FP16` | `true` | Usar FP16 para GPU (mais rapido) |
| `rerank_cache_model` | `RAG_RERANK_CACHE_MODEL` | `true` | Manter modelo em memoria |
| `rerank_top_k` | `RAG_RERANK_TOP_K` | `10` | Numero de documentos a retornar apos rerank |
| `rerank_max_chars` | `RAG_RERANK_MAX_CHARS` | `1800` | Caracteres maximos por documento no rerank |

### Exemplo

```bash
# Aumentar batch para GPU potente
export RAG_RERANK_BATCH_SIZE=64

# Retornar mais documentos
export RAG_RERANK_TOP_K=15
```

---

## Compression

Configuracoes de compressao de contexto para otimizar token budget.

| Parametro | Env Var | Padrao | Range | Descricao |
|-----------|---------|--------|-------|-----------|
| `compression_max_chars` | `RAG_COMPRESSION_MAX_CHARS` | `900` | 100-5000 | Caracteres maximos por chunk comprimido |
| `compression_min_chars` | `RAG_COMPRESSION_MIN_CHARS` | `100` | 50-500 | Caracteres minimos para preservar |
| `compression_token_budget` | `RAG_COMPRESSION_TOKEN_BUDGET` | `4000` | 1000-16000 | Budget total de tokens para contexto |
| `compression_preserve_full_text` | `RAG_COMPRESSION_PRESERVE_FULL` | `true` | - | Preservar texto original em metadata |

### Exemplo

```bash
# Aumentar budget para modelos com contexto grande
export RAG_COMPRESSION_TOKEN_BUDGET=8000

# Chunks maiores
export RAG_COMPRESSION_MAX_CHARS=1500
```

---

## Chunk Expansion

Configuracoes para recuperacao de chunks adjacentes.

| Parametro | Env Var | Padrao | Range | Descricao |
|-----------|---------|--------|-------|-----------|
| `chunk_expansion_window` | `RAG_CHUNK_EXPANSION_WINDOW` | `1` | 0-3 | Chunks antes e depois a recuperar |
| `chunk_expansion_max_extra` | `RAG_CHUNK_EXPANSION_MAX_EXTRA` | `12` | 0-50 | Maximo de chunks extras total |
| `chunk_expansion_merge_adjacent` | `RAG_CHUNK_EXPANSION_MERGE` | `true` | - | Unir chunks consecutivos |

### Exemplo

```bash
# Mais contexto ao redor
export RAG_CHUNK_EXPANSION_WINDOW=2
export RAG_CHUNK_EXPANSION_MAX_EXTRA=20
```

---

## Graph Enrichment

Configuracoes do knowledge graph juridico.

| Parametro | Env Var | Padrao | Range | Descricao |
|-----------|---------|--------|-------|-----------|
| `graph_hops` | `RAG_GRAPH_HOPS` | `2` | 1-4 | Niveis de relacionamento a explorar |
| `graph_max_nodes` | `RAG_GRAPH_MAX_NODES` | `50` | 10-200 | Maximo de nos a retornar |

---

## Graph Backend (NetworkX / Neo4j)

Configuracoes para selecionar o backend do grafo e conectar ao Neo4j.

| Parametro | Env Var | Padrao | Descricao |
|-----------|---------|--------|-----------|
| `graph_backend` | `RAG_GRAPH_BACKEND` | `networkx` | Backend do grafo: `networkx` (local) ou `neo4j` |
| `neo4j_uri` | `NEO4J_URI` | `bolt://localhost:7687` | URI de conexao (ex.: `bolt://...`, `neo4j+s://...`) |
| `neo4j_user` | `NEO4J_USER` (ou `NEO4J_USERNAME`) | `neo4j` | Usuario do banco |
| `neo4j_password` | `NEO4J_PASSWORD` | `password` | Senha do banco |
| `neo4j_database` | `NEO4J_DATABASE` | `iudex` | Nome do database |
| `neo4j_max_connection_pool_size` | `NEO4J_MAX_POOL_SIZE` | `50` | Pool maximo de conexoes |
| `neo4j_connection_timeout` | `NEO4J_CONNECTION_TIMEOUT` | `30` | Timeout de conexao (s) |

### Modo Hibrido (labels por tipo)

O modo hibrido mantém `(:Entity)` e adiciona labels por tipo (ex.: `(:Entity:Lei)`), usando whitelist para seguranca.

| Parametro | Env Var | Padrao | Descricao |
|-----------|---------|--------|-----------|
| `graph_hybrid_mode` | `RAG_GRAPH_HYBRID_MODE` | `false` | Ativa labels por tipo (Lei, Artigo, Sumula, ...) |
| `graph_hybrid_auto_schema` | `RAG_GRAPH_HYBRID_AUTO_SCHEMA` | `true` | Cria indices/constraints (best-effort) ao conectar |
| `graph_hybrid_migrate_on_startup` | `RAG_GRAPH_HYBRID_MIGRATE_ON_STARTUP` | `false` | Migra labels existentes no startup (opcional) |

### Graph Embedding Training

| Parametro | Env Var | Padrao | Descricao |
|-----------|---------|--------|-----------|
| `graph_embedding_method` | `GRAPH_EMBEDDING_METHOD` | `rotate` | Algoritmo: transe, rotate, complex, distmult |
| `graph_embedding_dim` | `GRAPH_EMBEDDING_DIM` | `128` | Dimensoes do embedding |
| `graph_embedding_epochs` | `GRAPH_EMBEDDING_EPOCHS` | `200` | Epocas de treinamento |
| `graph_embedding_batch_size` | `GRAPH_EMBEDDING_BATCH_SIZE` | `512` | Batch size |
| `graph_embedding_lr` | `GRAPH_EMBEDDING_LR` | `0.001` | Learning rate |
| `graph_embedding_negative_samples` | `GRAPH_EMBEDDING_NEG_SAMPLES` | `10` | Amostras negativas |
| `graph_embedding_negative_strategy` | `GRAPH_EMBEDDING_NEG_STRATEGY` | `self_adv` | Estrategia: uniform, self_adv, bernoulli |
| `graph_embedding_patience` | `GRAPH_EMBEDDING_PATIENCE` | `20` | Early stopping patience |
| `graph_embedding_checkpoint_dir` | `GRAPH_EMBEDDING_CHECKPOINT_DIR` | `data/embeddings/checkpoints` | Diretorio de checkpoints |
| `graph_embedding_retrain_hours` | `GRAPH_EMBEDDING_RETRAIN_HOURS` | `24` | Intervalo para retreino automatico |
| `graph_embedding_min_new_triples` | `GRAPH_EMBEDDING_MIN_NEW_TRIPLES` | `100` | Minimo de triplas novas para retreino |

---

## Storage - OpenSearch

Configuracoes do OpenSearch para busca lexical.

| Parametro | Env Var | Padrao | Descricao |
|-----------|---------|--------|-----------|
| `opensearch_url` | `OPENSEARCH_URL` | `https://localhost:9200` | URL do cluster OpenSearch |
| `opensearch_user` | `OPENSEARCH_USER` | `admin` | Usuario de autenticacao |
| `opensearch_password` | `OPENSEARCH_PASS` ou `OPENSEARCH_INITIAL_ADMIN_PASSWORD` | `admin` | Senha de autenticacao |
| `opensearch_verify_certs` | `OPENSEARCH_VERIFY_CERTS` | `false` | Verificar certificados SSL |

### Indices

| Parametro | Env Var | Padrao | Descricao |
|-----------|---------|--------|-----------|
| `opensearch_index_lei` | `OPENSEARCH_INDEX_LEI` | `rag-lei` | Indice de legislacao |
| `opensearch_index_juris` | `OPENSEARCH_INDEX_JURIS` | `rag-juris` | Indice de jurisprudencia |
| `opensearch_index_pecas` | `OPENSEARCH_INDEX_PECAS` | `rag-pecas_modelo` | Indice de pecas modelo |
| `opensearch_index_sei` | `OPENSEARCH_INDEX_SEI` | `rag-sei` | Indice de documentos internos |
| `opensearch_index_local` | `OPENSEARCH_INDEX_LOCAL` | `rag-local` | Indice de documentos locais |

### Exemplo

```bash
export OPENSEARCH_URL=https://opensearch.production.internal:9200
export OPENSEARCH_USER=rag_service
export OPENSEARCH_PASS=secure_password_here
export OPENSEARCH_VERIFY_CERTS=true
```

---

## Storage - Qdrant

Configuracoes do Qdrant para busca vetorial.

| Parametro | Env Var | Padrao | Descricao |
|-----------|---------|--------|-----------|
| `qdrant_url` | `QDRANT_URL` | `http://localhost:6333` | URL do servidor Qdrant |
| `qdrant_api_key` | `QDRANT_API_KEY` | `""` | API key (se necessario) |

### Collections

| Parametro | Env Var | Padrao | Descricao |
|-----------|---------|--------|-----------|
| `qdrant_collection_lei` | `QDRANT_COLLECTION_LEI` | `lei` | Collection de legislacao |
| `qdrant_collection_juris` | `QDRANT_COLLECTION_JURIS` | `juris` | Collection de jurisprudencia |
| `qdrant_collection_pecas` | `QDRANT_COLLECTION_PECAS` | `pecas_modelo` | Collection de pecas modelo |
| `qdrant_collection_sei` | `QDRANT_COLLECTION_SEI` | `sei` | Collection de documentos internos |
| `qdrant_collection_local` | `QDRANT_COLLECTION_LOCAL` | `local_chunks` | Collection de documentos locais |

### Exemplo

```bash
export QDRANT_URL=http://qdrant.production.internal:6333
export QDRANT_API_KEY=your_api_key_here
```

---

## Embeddings

Configuracoes do modelo de embeddings.

| Parametro | Env Var | Padrao | Descricao |
|-----------|---------|--------|-----------|
| `embedding_model` | `EMBEDDING_MODEL` | `text-embedding-3-large` | Modelo de embedding |
| `embedding_dimensions` | `EMBEDDING_DIMENSIONS` | `3072` | Dimensoes do vetor |
| `embedding_cache_ttl_seconds` | `EMBEDDING_CACHE_TTL` | `3600` | TTL do cache (1 hora) |
| `embedding_batch_size` | `EMBEDDING_BATCH_SIZE` | `100` | Tamanho do batch para embeddings |

### Modelos Suportados

- `text-embedding-3-large` (OpenAI, 3072 dims) - Padrao
- `text-embedding-3-small` (OpenAI, 1536 dims)
- `text-embedding-ada-002` (OpenAI, 1536 dims)

### Exemplo

```bash
# Usar modelo menor para reduzir custos
export EMBEDDING_MODEL=text-embedding-3-small
export EMBEDDING_DIMENSIONS=1536
```

---

## TTL Settings

Configuracoes de limpeza automatica de documentos locais.

| Parametro | Env Var | Padrao | Descricao |
|-----------|---------|--------|-----------|
| `local_ttl_days` | `LOCAL_TTL_DAYS` | `7` | Dias ate expiracao de docs locais |
| `ttl_cleanup_interval_hours` | `TTL_CLEANUP_INTERVAL_HOURS` | `6` | Intervalo de execucao da limpeza |

### Exemplo

```bash
# Manter documentos locais por 30 dias
export LOCAL_TTL_DAYS=30
```

---

## Tracing

Configuracoes de observabilidade e auditoria.

| Parametro | Env Var | Padrao | Descricao |
|-----------|---------|--------|-----------|
| `trace_log_path` | `RAG_TRACE_LOG_PATH` | `logs/rag_trace.jsonl` | Caminho do arquivo de trace |
| `trace_persist_db` | `RAG_TRACE_PERSIST_DB` | `false` | Salvar traces no banco de dados |
| `trace_export_otel` | `RAG_TRACE_EXPORT_OTEL` | `false` | Exportar para OpenTelemetry |
| `trace_export_langsmith` | `RAG_TRACE_EXPORT_LANGSMITH` | `false` | Exportar para LangSmith |

### Exemplo

```bash
# Habilitar exportacao para OpenTelemetry
export RAG_TRACE_EXPORT_OTEL=true
```

---

## RRF Fusion

Configuracoes do algoritmo de fusao Reciprocal Rank Fusion.

| Parametro | Env Var | Padrao | Range | Descricao |
|-----------|---------|--------|-------|-----------|
| `rrf_k` | `RAG_RRF_K` | `60` | 1-100 | Constante RRF (controla peso da posicao) |
| `lexical_weight` | `RAG_LEXICAL_WEIGHT` | `0.5` | 0.0-1.0 | Peso da busca lexical na fusao |
| `vector_weight` | `RAG_VECTOR_WEIGHT` | `0.5` | 0.0-1.0 | Peso da busca vetorial na fusao |

### Exemplo

```bash
# Priorizar busca lexical
export RAG_LEXICAL_WEIGHT=0.7
export RAG_VECTOR_WEIGHT=0.3
```

---

## Search Defaults

Configuracoes padrao de busca.

| Parametro | Env Var | Padrao | Range | Descricao |
|-----------|---------|--------|-------|-----------|
| `default_fetch_k` | `RAG_DEFAULT_FETCH_K` | `50` | 10-500 | Candidatos a buscar inicialmente |
| `default_top_k` | `RAG_DEFAULT_TOP_K` | `10` | 1-100 | Resultados finais a retornar |

### Exemplo

```bash
# Buscar mais candidatos para melhor recall
export RAG_DEFAULT_FETCH_K=100
export RAG_DEFAULT_TOP_K=20
```

---

## Lexical-First Gating

Configuracoes da otimizacao que pula busca vetorial quando lexical eh suficiente.

| Parametro | Env Var | Padrao | Range | Descricao |
|-----------|---------|--------|-------|-----------|
| `lexical_strong_threshold` | `RAG_LEXICAL_STRONG_THRESHOLD` | `0.7` | 0.5-1.0 | Score minimo para considerar lexical suficiente |
| `lexical_citation_patterns` | - | Lista de regex | - | Padroes que indicam query de citacao |

### Padroes de Citacao (Builtin)

```python
[
    r"art\.?\s*\d+",                          # Art. 5
    r"§\s*\d+",                               # § 1
    r"inciso\s+[IVXLCDM]+",                   # Inciso IV
    r"lei\s+n?\.?\s*\d+",                     # Lei 8.666
    r"súmula\s+n?\.?\s*\d+",                  # Sumula 123
    r"stf|stj|tst|trf|tjsp",                  # Tribunais
    r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}",  # Numero CNJ
]
```

---

## Configuracao Completa de Exemplo

```bash
# .env.production

# Feature Flags
RAG_ENABLE_CRAG=true
RAG_ENABLE_HYDE=true
RAG_ENABLE_MULTIQUERY=true
RAG_ENABLE_RERANK=true
RAG_ENABLE_COMPRESSION=true
RAG_ENABLE_GRAPH_ENRICH=true
RAG_ENABLE_TRACING=true

# CRAG
RAG_CRAG_MIN_BEST_SCORE=0.5
RAG_CRAG_MIN_AVG_SCORE=0.35
RAG_CRAG_MAX_RETRIES=2

# Query Expansion
RAG_HYDE_MODEL=gemini-2.0-flash
RAG_MULTIQUERY_MAX=3

# Reranking
RAG_RERANK_TOP_K=10
RAG_RERANK_BATCH_SIZE=32

# Compression
RAG_COMPRESSION_TOKEN_BUDGET=4000

# OpenSearch
OPENSEARCH_URL=https://opensearch.internal:9200
OPENSEARCH_USER=rag_service
OPENSEARCH_PASS=secure_password

# Qdrant
QDRANT_URL=http://qdrant.internal:6333

# Embeddings
EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_DIMENSIONS=3072

# RRF
RAG_LEXICAL_WEIGHT=0.5
RAG_VECTOR_WEIGHT=0.5

# Search
RAG_DEFAULT_FETCH_K=50
RAG_DEFAULT_TOP_K=10
```

---

## Metodos Utilitarios da Config

```python
config = get_rag_config()

# Obter todos os indices OpenSearch
indices = config.get_opensearch_indices()
# ['rag-lei', 'rag-juris', 'rag-pecas_modelo', 'rag-sei', 'rag-local']

# Obter apenas indices globais (sem local)
global_indices = config.get_global_indices()
# ['rag-lei', 'rag-juris', 'rag-pecas_modelo', 'rag-sei']

# Obter collections Qdrant
collections = config.get_qdrant_collections()
# ['lei', 'juris', 'pecas_modelo', 'sei', 'local_chunks']

# Obter config de treinamento de graph embeddings
training_config = config.get_embedding_training_config()
```
