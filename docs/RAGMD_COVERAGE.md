# Cobertura do `rag.md` no Iudex (RAG/CogRAG)

Este documento mapeia cada seção do `rag.md` para o que existe hoje no código.

**Legenda**
- `OK`: implementado (ou equivalente) e em produção no fluxo.
- `PARCIAL`: existe, mas falta parte importante / não é padrão / depende de configuração.
- `N/A`: seção do livro é conceitual, tutorial de infra (Docker), exemplo com outra stack (Streamlit/Chroma/CrewAI) ou “exercícios”.

## Capítulo 1 — Padrões de RAG

- `1.1 Quando usar RAG` (`rag.md:118`): `N/A` (decisão arquitetural; o código já suporta “RAG vs não-RAG” via roteamento/flags).
- `1.2 Arquitetura do RAG` (`rag.md:156`): `N/A` (conceitual; equivalente aparece na arquitetura do pipeline).
- `1.3 Um RAG Simples` (`rag.md:265`): `OK` — pipeline clássico com estágios explícitos. `apps/api/app/services/rag/pipeline/rag_pipeline.py:1`.
- `1.4 RAG com Memória` (`rag.md:293`): `OK` — Redis+TTL e uso no contexto do RAG. `apps/api/app/services/ai/rag_memory_store.py:12`, `apps/api/app/services/rag/pipeline_adapter.py:482`.
- `1.5 Agent RAG / Autônomo` (`rag.md:325`): `OK` — roteamento com schema + orquestração multi-passos. `apps/api/app/services/ai/rag_router.py:36`, `apps/api/app/services/rag/core/agentic_orchestrator.py:52`.
- `1.6 CRAG (Corrective RAG)` (`rag.md:362`): `OK` — gate de qualidade + retries/estratégias. `apps/api/app/services/rag/core/crag_gate.py:372`, `apps/api/app/services/rag/pipeline/rag_pipeline.py:2234`.
- `1.7 Adaptive RAG` (`rag.md:406`): `OK` — gating lexical-first + preflight antes de HyDE/MultiQuery. `apps/api/app/services/rag/pipeline/rag_pipeline.py:1195`.
- `1.8 GraphRAG` (`rag.md:445`): `OK` — Neo4j-first, paths como evidência e contexto de grafo. `apps/api/app/services/rag/core/neo4j_mvp.py:1`, `apps/api/app/services/rag/config.py:74`.
- `1.9 Hybrid RAG` (`rag.md:483`): `OK` — lexical+vector+grafo com merge por RRF. `apps/api/app/services/rag/pipeline/rag_pipeline.py:739`.
- `1.10 RRF (RAG-Fusion)` (`rag.md:527`): `OK` — merge multi-fonte via RRF. `apps/api/app/services/rag/pipeline/rag_pipeline.py:982`.
- `1.11 HyDE` (`rag.md:555`): `OK` — HyDE só para vetor (evita “poluir” lexical) + budget/skip. `apps/api/app/services/rag/pipeline/rag_pipeline.py:1255`, `apps/api/app/services/rag/pipeline/rag_pipeline.py:2423`.

**Aprimoramentos além do livro (Cap. 1)**
- Verificação determinística de citações/refs (além do CRAG): `apps/api/app/services/rag/core/cograg/nodes/verifier.py:406`.
- Batch embeddings + concorrência controlada no vetor (reduz p95 sem perder recall): `apps/api/app/services/rag/core/embeddings.py:1`.

## Capítulo 2 — RAG Clássico (Indexing + Online)

- `2.1 Corpus` (`rag.md:659`): `OK` — ingestão multi-fonte (documentos, web etc) + metadados/tenancy (no app). Ex.: `apps/api/app/services/rag/utils/ingest.py:1`.
- `2.2 Fluxo do RAG` (`rag.md:679`): `OK` — pipeline em estágios (retrieval → augmented → generation). `apps/api/app/services/rag/pipeline/rag_pipeline.py:1`.
- `2.3 Fase do Indexador` (`rag.md:719`): `OK` — utilitários/serviços de ingestão e indexação (Qdrant/OpenSearch/Neo4j).
- `2.4 Lendo e convertendo` (`rag.md:772`): `OK` — extração/chunking utilitária. `apps/api/app/services/rag/utils/ingest.py:58`.
- `2.5 Chunking` (`rag.md:915`): `OK` — chunking com overlap + semantic chunker disponível. `apps/api/app/services/rag/utils/ingest.py:23`, `apps/api/app/services/rag/utils/semantic_chunker.py:136`.
- `2.6 Embeddings` (`rag.md:981`): `OK` — `text-embedding-3-large` + cache/batch. `apps/api/app/services/rag/core/embeddings.py:1`.
- `2.7 Vector DB` (`rag.md:1082`): `OK` — Qdrant (e opcionalmente Neo4j vector index). `apps/api/app/services/rag/storage/qdrant_service.py:1`, `apps/api/app/services/rag/core/neo4j_mvp.py:99`.
- `2.8 Classe de Encoder` (`rag.md:1115`): `OK` — `EmbeddingsService` cumpre o papel. `apps/api/app/services/rag/core/embeddings.py:177`.
- `2.9 Recuperando conhecimento` (`rag.md:1301`): `OK` — lexical (OpenSearch) + vetor (Qdrant) + grafo (Neo4j). `apps/api/app/services/rag/pipeline/rag_pipeline.py:739`.
- `2.10 Aumento de informação (Augmented)` (`rag.md:1447`): `OK` — template central com política “use apenas evidências” + anti-injection, aplicado no pipeline. `apps/api/app/services/rag/pipeline_adapter.py:169`, `apps/api/app/services/rag_context_legacy.py:97`.
- `2.11 Gerando a resposta` (`rag.md:1529`): `OK` — geração no fluxo do app (LLM + política + citações/verificação quando habilitado).
- `2.12 Rodando com Streamlit` (`rag.md:1580`): `N/A` — o Iudex usa UI própria.
- `2.13 Exercícios` (`rag.md:1646`): `N/A`.

## Capítulo 3 — Memória (Redis)

- `3.1 Redis como memória + TTL` (`rag.md:1737`): `OK` — TTL padrão 24h. `apps/api/app/services/ai/rag_memory_store.py:9`.
- `3.2/3.3 Docker/Instalação` (`rag.md:1772`, `rag.md:1837`): `N/A` (infra).
- `3.4 Criando a memória` (`rag.md:1900`): `OK` — armazenamento por `conversation_id`. `apps/api/app/services/ai/rag_memory_store.py:14`.
- `3.5 Adicionando memória ao RAG` (`rag.md:2071`): `OK` — carregamento no adapter + persistência best-effort no chat. `apps/api/app/services/rag/pipeline_adapter.py:482`, `apps/api/app/services/chat_service.py:1306`.
- `3.6 Exercícios` (`rag.md:2257`): `N/A`.

## Capítulo 4 — Agentic RAG

- `4.1 AgenticRAG (roteamento)` (`rag.md:2336`): `OK` — roteador com schema e heurísticas. `apps/api/app/services/ai/rag_router.py:36`, `apps/api/app/services/ai/agentic_rag.py:62`.
- `4.2 Registro de datasets + locale` (`rag.md:2380`): `OK` — `DatasetRegistry` + `locale` e prompt “JSON-only”. `apps/api/app/services/ai/agentic_rag.py:16`.
- `4.3 Agente abstrato` (`rag.md:2433`): `PARCIAL` — não há uma ABC idêntica ao exemplo do livro; o papel é coberto por orquestração/roteadores do app.
- `4.4 Agente com API da LLM` (`rag.md:2500`): `OK` — chamadas LLM com contrato JSON (quando aplicável) e fallback heurístico. `apps/api/app/services/ai/rag_router.py:185`.
- `4.5 CrewAI` (`rag.md:2654`): `N/A` (não é necessário para o design atual).
- `4.6 Executando Agentic RAG` (`rag.md:2849`): `OK` — integrado ao fluxo do app (roteamento/flags).
- `4.7 Exercícios` (`rag.md:2938`): `N/A`.

## Capítulo 5 — GraphRAG (Neo4j)

- `5.1 Do vetor ao grafo` (`rag.md:3001`): `OK` — busca por relações (paths) + evidência estruturada. `apps/api/app/services/rag/core/neo4j_mvp.py:1`.
- `5.2 Definição de grafo` (`rag.md:3016`): `N/A` (conceitual).
- `5.3 De textos para grafos` (`rag.md:3080`): `OK` — extração determinística (regex) + ingest de relações, com schema explícito. `apps/api/app/services/rag/core/neo4j_mvp.py:180`.
- `5.4 Neo4j` (`rag.md:3160`): `OK` — Neo4j como grafo principal (inclusive “paths como evidência”). `apps/api/app/services/rag/core/neo4j_mvp.py:1013`.
- `5.5 Docker Neo4j` (`rag.md:3187`): `N/A` (infra).
- `5.6 Cypher` (`rag.md:3291`): `OK` — queries via `_execute_read`/`find_paths`. `apps/api/app/services/rag/core/neo4j_mvp.py:1013`.

**Aprimoramentos além do livro (Cap. 5)**
- Evidência em grafo como 1ª classe + “MindMap-Explain” (artefato de raciocínio): `apps/api/app/services/rag/core/cograg/nodes/mindmap_explain.py:103`.
- Verificador também valida `[path:...]` e inclui `<KG_PATHS>` no prompt: `apps/api/app/services/rag/core/cograg/nodes/verifier.py:206`.

## Principais gaps (se o objetivo for “cobrir 100%”)

- `PARCIAL`: “agente abstrato” no formato didático do livro (Cap. 4.3) — hoje o app usa roteadores/orquestradores ao invés de uma ABC única.
- `N/A`: exemplos específicos de Streamlit/Chroma/CrewAI e tutoriais de Docker/instalação.
