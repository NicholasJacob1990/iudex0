# Plano: Integração Cognitive RAG no Pipeline RAG do Iudex

> **Status:** Implementado (MVP) — em evolução
> **Data:** 2026-01-29
> **Referências:**
> - Paper CogGRAG (2503.06567v2) — Decomposição top-down + retrieval estruturado + verificação dual-LLM
> - Paper MindMap (2308.09729v5) — KG prompting com graph-of-thoughts
> - Paper Cog-RAG (2511.13201, AAAI 2026) — Dual-hypergraph cognitivo (temas + entidades)
> - Cognitive RAG patterns — Query rewriting, evidence refinement, memory integration, hallucination filtering
> - Repo cy623/RAG — Implementação oficial CogGRAG (referência acadêmica, **não usar direto em prod**)

---

## Contexto

O pipeline RAG do Iudex já possui 10 stages (Query Enhancement → Parallel Search → RRF Fusion → CRAG Gate → Rerank → Expand → Compress → Graph Enrich → Trace), com per-DB timeouts, result cache, metrics, circuit breaker, e budget tracking.

Este plano unifica **três abordagens complementares**:

| Abordagem | Paper | Contribuição principal |
|-----------|-------|----------------------|
| **CogGRAG** | 2503.06567v2 | Decomposição em mind map + retrieval por sub-questão + verificação dual-LLM |
| **Cog-RAG** | 2511.13201 (AAAI 2026) | Dual-hypergraph: temas globais (top-down) + entidades de alta ordem (bottom-up). +35% vs GraphRAG em domínio denso |
| **Cognitive RAG** | Posts/LinkedIn | 5 módulos cognitivos: query rewriting, evidence refinement, memory integration, reasoning with feedback, hallucination filtering |

**Objetivo**: Integrar um pipeline Cognitive RAG completo como modo alternativo de processamento, ativado por feature flag, sem quebrar o pipeline existente.

---

## Decisão Arquitetural Principal: LangGraph como Orquestrador

### Por que LangGraph (não cy623/RAG direto)

| Critério | cy623/RAG (CogGRAG) | LangGraph |
|----------|---------------------|-----------|
| **Propósito** | Framework KGQA acadêmico, mind-map cognitivo | Orquestrador genérico de agentes com grafo de estados |
| **Flexibilidade** | Baixa: mind-map + verification hard-coded | Alta: nós/edges condicionais definidos sob medida |
| **Integração** | Precisa adaptar para Neo4j/Qdrant/OpenSearch | Nativa: conectores para Neo4j, Qdrant, OpenSearch, Claude, GPT |
| **Multi-agente** | Básico: reasoning + verification | Avançado: N agentes, sub-grafos, retry, backtracking |
| **Estado/memória** | Implícito no mind-map | Explícito: state centralizado, checkpointing, replay |
| **Debugging** | Logs manuais | LangSmith Studio: trace, visualização, profiling |
| **Maturidade** | Código de paper (2025), sem versionamento | Produção: mantido pela LangChain Inc., releases estáveis |

**Abordagem híbrida**: Pegar as **ideias** do CogGRAG (mind-map, dual-phase retrieval, self-verification) e implementar como **StateGraph LangGraph** com nós tipados, edges condicionais e state centralizado.

### Infraestrutura LangGraph existente no Iudex

O Iudex já possui:
- `app/services/ai/langgraph/workflow.py` — `LangGraphWorkflow` wrapper com SSE streaming
- `app/services/ai/langgraph/subgraphs/parallel_research.py` — `ResearchState` com fan-out para rag_local/rag_global/web/juris + deduplicação + merge
- `app/services/ai/langgraph/improvements/checkpoint_manager.py` — Checkpointing
- `app/services/ai/langgraph/improvements/context_manager.py` — Compactação de contexto
- `app/services/ai/langgraph/improvements/parallel_nodes.py` — Execução paralela de nós

O `CognitiveRAGGraph` será um **novo StateGraph** no mesmo padrão, reutilizando `ResearchState`, SSE streaming e checkpoint.

### CognitiveRAGState (state centralizado)

```python
class CognitiveRAGState(TypedDict):
    # Input
    query: str
    tenant_id: Optional[str]
    case_id: Optional[str]
    scope: str

    # Phase 1: Decomposition
    mind_map: Optional[Dict[str, Any]]      # CognitiveTree serializado
    temas: List[str]                         # Temas macro/sub identificados
    sub_questions: List[Dict[str, Any]]      # Sub-questões com state Continue/End

    # Phase 1: Retrieval
    graph_nodes: List[Dict[str, Any]]        # Nós Neo4j recuperados (local + global)
    text_chunks: List[Dict[str, Any]]        # Chunks Qdrant/OpenSearch
    evidence_map: Dict[str, Any]             # Evidência por sub-questão

    # Phase 2.5: Refinement
    conflicts: List[Dict[str, Any]]          # Conflitos jurídicos detectados
    refined_evidence: Dict[str, Any]         # Evidência refinada
    similar_consultation: Optional[Dict]     # Consulta anterior similar (memória)

    # Phase 3: Reasoning + Verification
    sub_answers: List[Dict[str, Any]]        # Respostas por sub-questão com citações
    verification_status: str                 # "approved" | "rejected" | "abstain"
    verification_issues: List[str]           # Problemas encontrados pelo Verifier
    rethink_count: int                       # Tentativas de re-think
    max_rethink: int                         # Máximo permitido (default: 2)

    # Phase 3: Integration
    integrated_response: Optional[str]       # Parecer final estruturado
    citations_used: List[str]                # Citações [tipo:id] usadas
    abstain_info: Optional[Dict]             # Se abstain: lacunas identificadas

    # Metadata
    job_id: Optional[str]
    metrics: Dict[str, Any]
```

### Grafo de nós e edges

```
                    ┌──────────────┐
                    │   planner    │  Decompõe query em mind-map
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │theme_activator│  Ativa nós (:Tema) no Neo4j (top-down)
                    └──────┬───────┘
                           │
              ┌────────────▼────────────┐
              │    dual_retriever       │  Fan-out: Neo4j local + global + Qdrant + OpenSearch
              │  (parallel subgraph)    │
              └────────────┬────────────┘
                           │
                    ┌──────▼───────┐
                    │evidence_refiner│  Avalia relevância, detecta conflitos
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │memory_check  │  Busca consulta similar anterior
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │   reasoner   │  Responde sub-questões com CoT + citações
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
              ┌─────│   verifier   │─────┐
              │     └──────────────┘     │
              │                          │
         REPROVADO                   APROVADO
         + requer busca              │
              │                      │
              ▼                      │
     ┌────────────────┐              │
     │ query_rewriter │              │
     └───────┬────────┘              │
             │                       │
             ▼                       │
     dual_retriever ◄────────────────┘
     (retry com query                │
      reformulada)              APROVADO
                                     │
                              ┌──────▼───────┐
                              │  integrator  │  Consolida parecer final
                              └──────┬───────┘
                                     │
                              ┌──────▼───────┐
                              │memory_store  │  Persiste no Neo4j
                              └──────┬───────┘
                                     │
                                    END
```

---

## Phase 1: Core — Data Structures + LangGraph StateGraph + Nós Planner/Retriever

### 1.1 `apps/api/app/services/rag/core/cograg/__init__.py` (NOVO)

- Exports dos módulos do pacote

### 1.2 `apps/api/app/services/rag/core/cograg/mindmap.py` (NOVO)

- **Data structures puras** (sem I/O):
  - `NodeState(Enum)`: `CONTINUE` | `END`
  - `MindMapNode`: `node_id, question, level, state, parent_id, children, answer, evidence, verified`
  - `CognitiveTree`: `root_question, conditions, nodes, max_depth=3, max_children=4`
    - Métodos: `root()`, `leaves()`, `nodes_by_level(n)`, `max_level()`, `to_dict()`

### 1.3 `apps/api/app/services/ai/langgraph/subgraphs/cognitive_rag.py` (NOVO)

**O StateGraph principal** — orquestra todo o fluxo cognitivo:

```python
from langgraph.graph import StateGraph, END

class CognitiveRAGState(TypedDict):
    query: str
    tenant_id: Optional[str]
    case_id: Optional[str]
    scope: str
    mind_map: Optional[Dict[str, Any]]
    temas: List[str]
    sub_questions: List[Dict[str, Any]]
    graph_nodes: List[Dict[str, Any]]
    text_chunks: List[Dict[str, Any]]
    evidence_map: Dict[str, Any]
    conflicts: List[Dict[str, Any]]
    refined_evidence: Dict[str, Any]
    similar_consultation: Optional[Dict]
    sub_answers: List[Dict[str, Any]]
    verification_status: str
    verification_issues: List[str]
    rethink_count: int
    max_rethink: int
    integrated_response: Optional[str]
    citations_used: List[str]
    abstain_info: Optional[Dict]
    job_id: Optional[str]
    metrics: Dict[str, Any]

def build_cognitive_rag_graph() -> StateGraph:
    graph = StateGraph(CognitiveRAGState)

    # Nós
    graph.add_node("planner", planner_node)
    graph.add_node("theme_activator", theme_activator_node)
    graph.add_node("dual_retriever", dual_retriever_node)
    graph.add_node("evidence_refiner", evidence_refiner_node)
    graph.add_node("memory_check", memory_check_node)
    graph.add_node("reasoner", reasoner_node)
    graph.add_node("verifier", verifier_node)
    graph.add_node("query_rewriter", query_rewriter_node)
    graph.add_node("integrator", integrator_node)
    graph.add_node("memory_store", memory_store_node)

    # Edges lineares
    graph.set_entry_point("planner")
    graph.add_edge("planner", "theme_activator")
    graph.add_edge("theme_activator", "dual_retriever")
    graph.add_edge("dual_retriever", "evidence_refiner")
    graph.add_edge("evidence_refiner", "memory_check")
    graph.add_edge("memory_check", "reasoner")
    graph.add_edge("reasoner", "verifier")

    # Edge condicional: verifier → (reasoner | query_rewriter | integrator)
    graph.add_conditional_edges(
        "verifier",
        lambda s: (
            "query_rewriter" if s["verification_status"] == "rejected"
                and s.get("requires_new_search") and s["rethink_count"] < s["max_rethink"]
            else "reasoner" if s["verification_status"] == "rejected"
                and s["rethink_count"] < s["max_rethink"]
            else "integrator"
        )
    )
    graph.add_edge("query_rewriter", "dual_retriever")  # Loop de volta
    graph.add_edge("integrator", "memory_store")
    graph.add_edge("memory_store", END)

    return graph.compile()
```

### 1.4 `apps/api/app/services/rag/core/cograg/nodes/planner.py` (NOVO)

- **Nó Planner** — decompõe query em mind-map (lógica do CogGRAG):
  - `planner_node(state) → dict` — Gera mind-map hierárquico via LLM
  - `_is_complex_query(query) → bool` — heurística: múltiplas entidades legais, conjunções, comprimento > 20 chars. Queries de citação pura (Art. X) retornam fallback
  - `_extract_conditions(query) → str` — prompt LLM para extrair contexto
  - `_generate_subquestions(parent, conditions) → List[MindMapNode]` — BFS level-by-level
- **Prompts em português jurídico** (EXTRACT_CONDITIONS_PROMPT, DECOMPOSE_PROMPT)
- Usa Gemini Flash (consistente com hyde_model/multiquery_model existentes)

### 1.5 `apps/api/app/services/rag/core/cograg/nodes/retriever.py` (NOVO)

- **Nó Dual Retriever** — retrieval estruturado por sub-questão (lógica dual-phase do CogGRAG):
  - `dual_retriever_node(state) → dict` — fan-out paralelo por sub-questão
  - `_extract_keys(question) → List[RetrievalKey]` — usa `LegalEntityExtractor` (regex, zero LLM)
  - `_local_retrieval(keys)` — Neo4j entity/triple lookup (bottom-up)
  - `_global_retrieval(keys)` — Neo4j subgraph traversal multi-hop
  - Chunk retrieval via OpenSearch BM25 + Qdrant semantic
  - Filtro cosine similarity ≥ 0.7
  - Deduplicação cross-subquestion por `chunk_uid`
- **Nó Theme Activator** — ativa nós `(:Tema)` no Neo4j (top-down, Cog-RAG pattern):
  - `theme_activator_node(state) → dict` — busca temas macro/sub no grafo

---

## Phase 2: Integração no Pipeline RAG

### 2.1 `apps/api/app/services/rag/config.py` (MODIFICAR)

Adicionar ao `RAGConfig`:

```python
# CogGRAG Core
enable_cograg: bool = False
cograg_max_depth: int = 3
cograg_max_children: int = 4
cograg_decomposer_model: str = "gemini-2.0-flash"
cograg_similarity_threshold: float = 0.7
cograg_complexity_threshold: float = 0.5

# Cognitive RAG Enhancements (Phase 2.5)
cograg_theme_retrieval_enabled: bool = False
cograg_evidence_refinement_enabled: bool = False
cograg_memory_enabled: bool = False
cograg_abstain_mode: bool = True

# Verification (Phase 3)
cograg_verification_enabled: bool = False
cograg_verification_model: str = "gemini-2.0-flash"
cograg_max_rethink_attempts: int = 1
cograg_hallucination_loop: bool = False
```

E correspondentes no `from_env()` com env vars `RAG_ENABLE_COGRAG`, `RAG_COGRAG_*`.

### 2.2 `apps/api/app/services/rag/pipeline/rag_pipeline.py` (MODIFICAR)

**Novos stages** no enum `PipelineStage`:

- `COGRAG_DECOMPOSE`, `COGRAG_STRUCTURED_RETRIEVAL`, `COGRAG_EVIDENCE_REFINE`, `COGRAG_VERIFICATION`

**Import try/except** (padrão existente):

```python
try:
    from app.services.rag.core.cograg import CognitiveDecomposer, DecomposerConfig, StructuredRetriever
except ImportError:
    CognitiveDecomposer = None
```

**Branching no `search()`** (após `_ensure_components`, antes de Stage 1):

```python
use_cograg = self._base_config.enable_cograg and self._cograg_decomposer is not None

if use_cograg:
    cograg_result = await self._cograg_pipeline(query, trace, indices, collections, ...)
    if not cograg_result["fallback"]:
        merged_results = cograg_result["results"]
        # Pula direto para Stage 5 (CRAG Gate) com os resultados CogGRAG
    else:
        # Query simples → pipeline normal
else:
    # Pipeline normal inalterado (Stages 1-4)
```

**Novo método `_cograg_pipeline()`**:

1. Stage COGRAG_DECOMPOSE: `decomposer.decompose(query)` → `CognitiveTree`
2. Fallback se ≤1 folha (query simples)
3. Stage COGRAG_STRUCTURED_RETRIEVAL: `retriever.retrieve_for_tree(tree, ...)` → evidence_map
4. Merge + deduplicação cross-subquestion
5. Return results para Stage 5+ do pipeline normal

**Lazy init em `_ensure_components()`**: `self._cograg_decomposer`, `self._cograg_retriever`

---

## Phase 2.5: Enriquecimentos Cognitive RAG

> Baseado no paper Cog-RAG (2511.13201) e padrões Cognitive RAG.
> Cada item tem feature flag independente.

### 2.5.1 Schema Neo4j expandido — Nós de Tema (Cog-RAG dual-level)

**Arquivo:** `apps/api/app/services/rag/core/neo4j_mvp.py` (MODIFICAR) + migration Cypher

O paper Cog-RAG (AAAI 2026) demonstra que representação dual-level (temas macro + entidades micro) supera GraphRAG em 35% em domínios densos. Adicionar ao grafo Neo4j:

```cypher
// Novos labels
(:Tema {nome, nivel: "macro"|"sub", descricao, tenant_id})
(:Consulta {id, pergunta_usuario, data, resposta_final, tenant_id})
(:SubPergunta {texto, resposta, citacoes, node_id})
(:Correcao {texto, usuario_id, data, tipo: "factual"|"juridico"|"formatacao"})

// Novos relationships
(:Processo)-[:TRATA_DE {relevancia: float}]->(:Tema)
(:Tema)-[:SUBTEMA_DE]->(:Tema)
(:Jurisprudencia)-[:SOBRE_TEMA]->(:Tema)
(:Dispositivo)-[:RELACIONADO_A]->(:Tema)
(:Consulta)-[:DECOMPOSTA_EM]->(:SubPergunta)
(:SubPergunta)-[:USA_NO]->(:Processo|:Dispositivo|:Jurisprudencia)
(:Consulta)-[:CORRIGIDA_POR]->(:Correcao)

// Índices
CREATE INDEX tema_nome IF NOT EXISTS FOR (t:Tema) ON (t.nome);
CREATE INDEX consulta_tenant IF NOT EXISTS FOR (c:Consulta) ON (c.tenant_id);
```

**Extração de temas na ingestão**: Ao indexar documentos, LLM extrai temas macro/sub e cria nós `(:Tema)`. O `StructuredRetriever` primeiro ativa temas (top-down), depois desce para entidades (bottom-up), conforme o fluxo cognitivo do Cog-RAG.

### 2.5.2 Evidence Refinement — Avaliação pré-merge

**Arquivo:** `apps/api/app/services/rag/core/cograg/evidence_refiner.py` (NOVO)

Antes de aceitar top-K chunks, avaliar relevância, consistência e conflito:

```python
class EvidenceRefiner:
    """Avalia e refina evidências antes do merge (Cognitive RAG pattern)."""

    async def refine(
        self,
        query: str,
        evidence_map: Dict[str, SubQuestionEvidence],
        tree: CognitiveTree,
    ) -> Dict[str, SubQuestionEvidence]:
        """
        Para cada sub-questão:
        1. Avaliar relevância de cada chunk (score threshold)
        2. Detectar conflitos entre chunks (posições jurídicas divergentes)
        3. Marcar conflitos para o Reasoner tratar explicitamente
        4. Descartar chunks irrelevantes (< threshold)
        """
        ...

    def _detect_conflicts(
        self, chunks: List[Dict]
    ) -> List[Dict[str, Any]]:
        """Identifica chunks com posições jurídicas conflitantes."""
        ...
```

### 2.5.3 Memory Integration — Memória de consultas

**Arquivo:** `apps/api/app/services/rag/core/cograg/memory.py` (NOVO)

Consultas anteriores e suas sub-respostas viram nós no grafo. Permite cache semântico e aprendizado:

```python
class CognitiveMemory:
    """Memória de consultas para reuso e aprendizado (Cognitive RAG pattern)."""

    async def find_similar_consultation(
        self, query: str, tenant_id: str, threshold: float = 0.85
    ) -> Optional[Dict]:
        """Busca consulta anterior semanticamente similar."""
        ...

    async def store_consultation(
        self, query: str, tree: CognitiveTree,
        verification_results: Dict, tenant_id: str
    ) -> str:
        """Persiste consulta como nós (:Consulta) → (:SubPergunta) no Neo4j."""
        ...

    async def apply_correction(
        self, consulta_id: str, correcao: str, usuario_id: str
    ) -> None:
        """Human-in-the-loop: advogado corrige → nó (:Correcao) penaliza caminhos."""
        ...
```

### 2.5.4 Abstain Mode — "Não sei" explícito

Quando confiança é baixa, o sistema responde "Não encontrei evidência suficiente" e indica o que falta, em vez de alucinar. Integrado no Reasoner (Phase 3):

```python
# No reasoner, após gerar resposta:
if confidence < self._config.abstain_threshold:
    return AbstainResult(
        message="Não encontrei evidência suficiente para responder.",
        missing=["contrato de trabalho", "CCT aplicável"],
        partial_answer=answer,  # resposta parcial se houver
    )
```

---

## Phase 3: Verificação Dual-LLM + Hallucination Filtering

### 3.1 `apps/api/app/services/rag/core/cograg/reasoner.py` (NOVO)

- `ReasonerConfig`: `response_model, verifier_model, max_rethink_attempts=1, verification_temperature=0.1, abstain_threshold=0.3`
- `VerificationResult`: `node_id, question, answer, is_consistent, confidence, issues, rethink_count, citations_used`
- `AbstainResult`: `message, missing, partial_answer`
- `BottomUpReasoner`:
  - `reason_and_verify(tree, evidence_map, budget_tracker?) → Dict[node_id, VerificationResult]`
    1. Folhas → `_generate_answer(node, evidence)` via LLM_res
    2. Subir pela árvore: combinar respostas dos filhos
    3. Para cada nó: `_verify_answer(node, answer, evidence)` via LLM_ver
    4. Se inconsistente: `_rethink(node, previous, evidence)` (max N tentativas)
    5. Se confiança baixa: `AbstainResult` com indicação do que falta

**Prompts dos agentes (anti-alucinação jurídica):**

**Reasoner:**
```
REGRAS OBRIGATÓRIAS DE CITAÇÃO:
1. Toda afirmação jurídica DEVE citar: [tipo:id] ex: [processo:0001234-56.2024.5.02.0000], [lei:CLT-art468]
2. Se não houver evidência suficiente: "Não encontrei evidência suficiente. Necessário: [o que falta]."
3. NÃO invente números de processo, artigos ou teses
4. Se entendimentos conflitantes: cite ambos com [id] e indique "entendimento não pacificado"
5. Raciocínio passo-a-passo (CoT) explícito

Responda em JSON:
{
  "resposta": "texto com citações inline [tipo:id]",
  "citacoes_usadas": ["tipo:id"],
  "grau_confianca": "alto|medio|baixo",
  "lacunas": "o que falta para resposta definitiva"
}
```

**Verifier (checklist obrigatório):**
```
CHECKLIST:
1. Toda afirmação importante tem citação [tipo:id]?
2. As citações existem no contexto fornecido? (não inventadas)
3. A resposta admite incerteza quando evidência é fraca?
4. Há viés de confirmação? (Reasoner ignorou evidência contrária?)
5. A lógica jurídica está correta? (competência, instância, matéria)

AÇÃO:
- APROVADO: {"status": "aprovado", "resposta_final": <mesma>}
- REPROVADO: {"status": "reprovar", "motivo": "...", "requer_nova_busca": true/false}
```

### 3.2 Hallucination Filtering Loop (Cognitive RAG pattern)

Quando `cograg_hallucination_loop=True`, o Verifier pode solicitar **nova busca** (query rewriting) se detectar que a evidência é insuficiente para a claim feita:

```python
# No _cograg_pipeline, loop de verificação:
for attempt in range(max_rethink + 1):
    verification = await reasoner.verify(node, answer, evidence)
    if verification.is_consistent:
        break
    if verification.requer_nova_busca and attempt < max_rethink:
        # Query rewriting: reformular busca com sugestão do Verifier
        new_evidence = await retriever.retrieve_for_node(
            node, query=verification.sugestao_busca, ...
        )
        evidence = merge(evidence, new_evidence)
        answer = await reasoner.generate_answer(node, evidence)
```

### 3.3 Final Integrator

**Arquivo:** `apps/api/app/services/rag/core/cograg/integrator.py` (NOVO)

Consolida sub-respostas verificadas em parecer final estruturado:

```python
class FinalIntegrator:
    """Consolida sub-respostas em parecer jurídico estruturado."""

    async def integrate(
        self,
        tree: CognitiveTree,
        verification_results: Dict[str, VerificationResult],
        original_query: str,
    ) -> IntegratedResponse:
        """
        Gera parecer final em seções:
        - Fundamento Legal (com citações [tipo:id])
        - Jurisprudência Aplicável
        - Análise
        - Conclusão
        - Limitações (se houve lacunas/abstain)
        """
        ...
```

### 3.4 Integração em `rag_pipeline.py`

- Após COGRAG_STRUCTURED_RETRIEVAL:
  - Stage COGRAG_EVIDENCE_REFINE (se `cograg_evidence_refinement_enabled`)
  - Stage COGRAG_VERIFICATION (se `cograg_verification_enabled`)
  - Enricha resultados com `_cograg_verified`, `_cograg_confidence`, `_cograg_citations`
  - Chunks verificados recebem boost no score
  - Se abstain: resultado inclui `abstain_info` com lacunas identificadas

---

## Phase 4: Frontend + SSE Events

### 4.1 `apps/api/app/services/ai/shared/sse_protocol.py` (MODIFICAR)

Novos eventos:

- `COGRAG_DECOMPOSE_START` / `COGRAG_DECOMPOSE_NODE` / `COGRAG_DECOMPOSE_COMPLETE`
- `COGRAG_RETRIEVAL_START` / `COGRAG_RETRIEVAL_NODE` / `COGRAG_RETRIEVAL_COMPLETE`
- `COGRAG_REFINE_START` / `COGRAG_REFINE_COMPLETE`
- `COGRAG_VERIFY_START` / `COGRAG_VERIFY_NODE` / `COGRAG_VERIFY_COMPLETE`
- `COGRAG_ABSTAIN` — sistema indica que não tem evidência suficiente

### 4.2 `apps/web/src/components/chat/cograg-tree-viewer.tsx` (NOVO)

- Componente React para visualizar árvore de decomposição em tempo real
- Nodes coloridos por estado (decomposing/verified/pending/failed/abstain)
- Badge com contagem de evidências por folha
- Indicador de conflitos detectados
- Seção "Limitações" quando abstain mode ativado

### 4.3 `apps/web/src/stores/chat-store.ts` (MODIFICAR)

- Adicionar: `cogragTree: CogRAGNode[] | null`, `cogragStatus: "idle"|"decomposing"|"retrieving"|"refining"|"verifying"|"complete"|"abstain"`

---

## Phase 5: Testes

### Novos arquivos de teste:

1. `apps/api/tests/test_cograg_mindmap.py` — Node/Tree creation, leaves, levels, serialização, max_depth
2. `apps/api/tests/test_cograg_decomposer.py` — Query simples não decompõe, query complexa decompõe, budget respeitado, complexity detection
3. `apps/api/tests/test_cograg_retrieval.py` — Key extraction com entidades legais, retrieve paralelo, similarity filtering, deduplicação
4. `apps/api/tests/test_cograg_evidence_refiner.py` — Conflito detection, relevância filtering, chunks descartados
5. `apps/api/tests/test_cograg_reasoner.py` — Citação obrigatória, abstain mode, verificação dual-LLM, rethink loop, hallucination filtering
6. `apps/api/tests/test_cograg_memory.py` — Store/retrieve consulta, correção human-in-the-loop, penalização de caminhos
7. `apps/api/tests/test_cograg_integration.py` — Pipeline completo com CogGRAG enabled, disabled inalterado, fallback query simples, verificação, abstain

---

## Arquivos Críticos

| Arquivo | Ação | Phase |
|---------|------|-------|
| `app/services/rag/core/cograg/__init__.py` | NOVO | 1 |
| `app/services/rag/core/cograg/mindmap.py` | NOVO — data structures puras | 1 |
| `app/services/ai/langgraph/subgraphs/cognitive_rag.py` | NOVO — **StateGraph principal** | 1 |
| `app/services/rag/core/cograg/nodes/planner.py` | NOVO — nó Planner (decomposição) | 1 |
| `app/services/rag/core/cograg/nodes/retriever.py` | NOVO — nós Dual Retriever + Theme Activator | 1 |
| `app/services/rag/config.py` | MODIFICAR | 2 |
| `app/services/rag/pipeline/rag_pipeline.py` | MODIFICAR — branching para LangGraph | 2 |
| `app/services/rag/core/cograg/nodes/refiner.py` | NOVO — nó Evidence Refiner | 2.5 |
| `app/services/rag/core/cograg/nodes/memory.py` | NOVO — nós Memory Check + Store | 2.5 |
| `app/services/rag/core/neo4j_mvp.py` | MODIFICAR — schema (:Tema), (:Consulta) | 2.5 |
| `app/services/rag/core/cograg/nodes/reasoner.py` | NOVO — nó Reasoner (CoT + citações) | 3 |
| `app/services/rag/core/cograg/nodes/verifier.py` | NOVO — nó Verifier (checklist 5 itens) | 3 |
| `app/services/rag/core/cograg/nodes/query_rewriter.py` | NOVO — nó Query Rewriter (hallucination loop) | 3 |
| `app/services/rag/core/cograg/nodes/integrator.py` | NOVO — nó Integrator (parecer final) | 3 |
| `app/services/ai/shared/sse_protocol.py` | MODIFICAR | 4 |
| `apps/web/src/components/chat/cograg-tree-viewer.tsx` | NOVO | 4 |
| `apps/web/src/stores/chat-store.ts` | MODIFICAR | 4 |
| `tests/test_cograg_*.py` (7 arquivos) | NOVO | 5 |

---

## Schema Neo4j Completo (referência)

### Labels existentes (manter)
```
(:Document), (:Chunk), (:Entity), (:Fact), (:Claim), (:Evidence)
```

### Labels novos (Phase 2.5)
```
(:Tema {nome, nivel: "macro"|"sub", descricao, tenant_id})
(:Consulta {id, pergunta_usuario, data, resposta_final, tenant_id})
(:SubPergunta {texto, resposta, citacoes[], node_id})
(:Correcao {texto, usuario_id, data, tipo: "factual"|"juridico"|"formatacao"})
```

### Relationships novos
```
(:Processo)-[:TRATA_DE {relevancia}]->(:Tema)
(:Tema)-[:SUBTEMA_DE]->(:Tema)
(:Jurisprudencia)-[:SOBRE_TEMA]->(:Tema)
(:Dispositivo)-[:RELACIONADO_A]->(:Tema)
(:Consulta)-[:DECOMPOSTA_EM]->(:SubPergunta)
(:SubPergunta)-[:USA_NO]->(:Processo|:Dispositivo|:Jurisprudencia)
(:Consulta)-[:CORRIGIDA_POR]->(:Correcao)
```

---

## Mecanismos Anti-Alucinação

| Mecanismo | Phase | Implementação |
|-----------|-------|---------------|
| **Citação obrigatória** | 3 | Reasoner/Verifier forçam `[tipo:id]` em cada claim |
| **Validação de ID** | 3 | Verifier checa se IDs existem no contexto (não na memória do LLM) |
| **Abstain explícito** | 2.5/3 | Se confiança baixa → "não sei" + indica docs faltantes |
| **Evidence refinement** | 2.5 | Avalia relevância/conflito antes de usar chunks |
| **Conflito explícito** | 2.5/3 | Entendimentos divergentes citados com ambos os lados |
| **Hallucination loop** | 3 | Verifier solicita nova busca se evidência insuficiente |
| **Human-in-the-loop** | 2.5 | Advogado corrige → nó (:Correcao) → penaliza caminhos ruins |
| **Memória de erros** | 2.5 | Correções viram edges no grafo, re-treinam retriever implicitamente |
| **Sem inferência criativa** | 3 | Prompts proíbem "deduzir", "presumir", "por analogia" sem precedente |

---

## Fluxo Cognitivo Completo

```
1. Usuário pergunta
   ↓
2. Planner/Decomposer: gera sub-questões + identifica temas (Phase 1)
   ↓
3. Theme Activation: ativa nós (:Tema) no Neo4j — top-down (Phase 2.5)
   ↓
4. Structured Retrieval: por sub-questão — Neo4j + Qdrant + OpenSearch (Phase 1)
   ↓
5. Evidence Refinement: avalia relevância, detecta conflitos (Phase 2.5)
   ↓
6. Memory Check: busca consulta similar anterior (Phase 2.5)
   ↓
7. Reasoner: responde cada sub-questão com CoT + citações [tipo:id] (Phase 3)
   ↓
8. Verifier: checa citações, consistência, viés — checklist 5 itens (Phase 3)
   ├─ Se REPROVADO + requer busca → Query Rewriting → volta ao 4
   ├─ Se REPROVADO → Re-think → volta ao 7
   └─ Se APROVADO → continua
   ↓
9. Integrator: consolida em parecer (Fundamento / Jurisprudência / Análise / Conclusão / Limitações) (Phase 3)
   ↓
10. Memory Store: persiste consulta + sub-respostas no Neo4j (Phase 2.5)
   ↓
11. Resposta ao usuário (com árvore visual no frontend, Phase 4)
```

---

## Decisões Arquiteturais

1. **LangGraph como orquestrador** (não cy623/RAG direto): Pegar as ideias do CogGRAG (mind-map, dual-phase retrieval, self-verification) e implementar como StateGraph LangGraph. Motivo: controle total do fluxo, state centralizado com checkpointing, debugging via LangSmith, integração nativa com Neo4j/Qdrant/Claude/GPT, maturidade de produção
2. **Feature-flagged**: `enable_cograg=False` por default — zero impacto quando desligado
3. **Fallback automático**: Query simples (≤1 folha na decomposição) → pipeline normal
4. **Gemini Flash para decomposição**: Consistente com hyde_model/multiquery_model existentes, baixo custo
5. **LegalEntityExtractor (regex) para key extraction**: Zero LLM calls nessa etapa
6. **Incremental**: Phase 1-2 funcionam sem Phase 2.5/3. Cada feature tem seu flag independente
7. **Budget**: Decomposição ~2-3 LLM calls, refinement ~1, verificação ~2N, integration ~1. `max_llm_calls_per_request` elevado para ~20 via env var quando CogGRAG completo ativo
8. **Dual-level retrieval** (Cog-RAG): Temas macro (top-down) → Entidades micro (bottom-up). Requer extração de temas na ingestão (LLM call adicional por documento)
9. **Memória persistente**: Consultas/correções no Neo4j com multi-tenancy (tenant_id em todos os nós meta-cognitivos)
10. **Anti-alucinação como prioridade**: Abstain mode ativo por default. Prompts com proibições explícitas de inferência sem precedente
11. **Cada nó = arquivo separado**: `nodes/planner.py`, `nodes/retriever.py`, `nodes/reasoner.py`, etc. — facilita teste unitário, substituição e evolução independente
12. **State centralizado** (`CognitiveRAGState`): Todos os nós lêem/escrevem no mesmo TypedDict. Checkpoint automático entre nós para replay/debug

---

## Verificação

1. **Unit tests**: `pytest tests/test_cograg_*.py -v` (7 arquivos, Phase 5)
2. **Integration**: Pipeline com `enable_cograg=True` processa query multi-conceito e retorna resultados estruturados por sub-questão
3. **Fallback**: Pipeline com `enable_cograg=True` + query simples ("Art. 5 CF") → fallback para pipeline normal
4. **Feature flag off**: Pipeline com `enable_cograg=False` → comportamento 100% inalterado
5. **Budget**: Verificar que BudgetTracker bloqueia se CogGRAG exceder limites
6. **Anti-alucinação**: Query sem evidência suficiente → abstain com indicação de docs faltantes
7. **Conflito**: Query com jurisprudência divergente → ambos os lados citados
8. **Memória**: Segunda consulta similar → reutiliza sub-respostas (cache hit)
9. **Human-in-the-loop**: Correção de advogado → nó (:Correcao) criado → futura consulta penaliza caminho errado
