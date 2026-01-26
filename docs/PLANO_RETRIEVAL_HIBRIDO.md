# Plano de Implementação: Retrieval Híbrido com Neo4j + ColPali

> **Data**: 2025-01-25
> **Atualizado**: 2025-01-25
> **Objetivo**: Implementar arquitetura de retrieval híbrida mantendo Qdrant + OpenSearch como candidate generators, adicionando Neo4j como camada de grafo para expansão multi-hop, e ColPali para documentos visuais.

---

## ⚡ STATUS ATUAL

### Fase 1 (MVP) - **90% IMPLEMENTADO**

| Componente | Status | Arquivo |
|------------|--------|---------|
| Neo4jMVP multi-hop | ✅ DONE | `neo4j_mvp.py` |
| Paths explicáveis (path_nodes/edges) | ✅ DONE | `neo4j_mvp.py` |
| Security trimming completo | ✅ DONE | `neo4j_mvp.py`, `graph.py` |
| GraphContext.paths | ✅ DONE | `rag_pipeline.py` |
| RAG_LEXICAL_BACKEND routing | ✅ DONE | `rag_pipeline.py` |
| RAG_VECTOR_BACKEND routing | ✅ DONE | `rag_pipeline.py` |
| Neo4j Fulltext Index | ✅ DONE | `neo4j_mvp.py` (flag: NEO4J_FULLTEXT_ENABLED) |
| Neo4j Vector Index schema | ✅ DONE | `neo4j_mvp.py` (flag: NEO4J_VECTOR_INDEX_ENABLED) |
| RAG_GRAPH_INGEST_ENGINE | ✅ DONE | `rag.py` (mvp/graph_rag/both) |
| **ColPali Service** | ✅ DONE | `colpali_service.py` (18 testes passando) |

### Fase 2 - **PREPARADO**

| Componente | Status |
|------------|--------|
| Neo4j Vector Search wiring | ⚡ Schema pronto, wiring pendente |
| Métricas de comparação | ❌ PENDENTE |
| Decisão de migração | ❌ PENDENTE |

---

## Visão Geral da Estratégia

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FASE 1 (MVP - PRIORIDADE)                         │
│  Desbloqueia chat + grafo explicável sem risco                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  • Manter Qdrant + OpenSearch como "candidate generator"                    │
│  • Neo4j MVP como "camada de grafo" para:                                   │
│    - Expansão multi-hop (1-2 hops)                                          │
│    - Paths explicáveis (nodes/relationships com IDs/props)                  │
│    - Visualização do grafo (mesma fonte)                                    │
│  • ColPali para documentos visuais (PDFs com tabelas/figuras)               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FASE 2 (SEM VIRAR REFÉM - QUANDO TIVER NÚMEROS)          │
├─────────────────────────────────────────────────────────────────────────────┤
│  • Implementar "retrieval router" por flag/métricas                         │
│  • Adicionar em paralelo:                                                   │
│    - Neo4j FULLTEXT para UI/lexical                                         │
│    - Neo4j VECTOR INDEX para seeds (usando embeddings prontos)              │
│  • Comparar com Qdrant/OpenSearch até dar paridade                          │
│  • Só então desliga o que não precisar                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## FASE 1: Neo4j como Camada de Grafo + ColPali

### 1.1 Arquitetura Alvo

```
                              ┌─────────────────┐
                              │   User Query    │
                              └────────┬────────┘
                                       │
                              ┌────────▼────────┐
                              │  Query Router   │
                              │ (classificação) │
                              └────────┬────────┘
                                       │
         ┌─────────────────────────────┼─────────────────────────────┐
         │                             │                             │
         ▼                             ▼                             ▼
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│   Text Query    │         │  Visual Query   │         │  Graph Query    │
│ (Qdrant+OpenS)  │         │   (ColPali)     │         │   (Neo4j)       │
└────────┬────────┘         └────────┬────────┘         └────────┬────────┘
         │                           │                           │
         │                           │                           │
         └───────────────────────────┼───────────────────────────┘
                                     │
                              ┌──────▼───────┐
                              │  RRF Fusion  │
                              │ + Reranking  │
                              └──────┬───────┘
                                     │
                              ┌──────▼───────┐
                              │   Neo4j      │
                              │  Multi-Hop   │
                              │  Expansion   │
                              └──────┬───────┘
                                     │
                              ┌──────▼───────┐
                              │  Explainable │
                              │    Paths     │
                              └──────┬───────┘
                                     │
                              ┌──────▼───────┐
                              │ LLM Response │
                              └──────────────┘
```

### 1.2 Tarefas de Implementação

#### Task 1.2.1: Neo4j Graph Expansion Service
**Arquivo**: `apps/api/app/services/rag/core/neo4j_graph_expansion.py`

```python
"""
Neo4j Graph Expansion Service
Expande resultados de retrieval usando grafos de conhecimento.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
from neo4j import AsyncDriver, AsyncGraphDatabase
import asyncio

@dataclass
class GraphPath:
    """Representa um caminho explicável no grafo."""
    nodes: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]
    score: float
    explanation: str

@dataclass
class ExpandedResult:
    """Resultado expandido com contexto de grafo."""
    original_chunk_uid: str
    original_score: float
    expanded_entities: List[Dict[str, Any]]
    paths: List[GraphPath]
    total_score: float

class Neo4jGraphExpansionService:
    """
    Serviço para expansão multi-hop usando Neo4j.

    Features:
    - Expansão 1-2 hops a partir de entidades mencionadas
    - Paths explicáveis com IDs e propriedades
    - Cache de resultados frequentes
    - Tenant isolation
    """

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        database: str = "iudex",
        max_hops: int = 2,
        max_expanded_nodes: int = 50
    ):
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.max_hops = max_hops
        self.max_expanded_nodes = max_expanded_nodes
        self._driver: Optional[AsyncDriver] = None

    async def connect(self):
        """Estabelece conexão assíncrona com Neo4j."""
        if not self._driver:
            self._driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password)
            )

    async def close(self):
        """Fecha conexão."""
        if self._driver:
            await self._driver.close()
            self._driver = None

    async def expand_from_entities(
        self,
        entity_ids: List[str],
        tenant_id: str,
        hops: int = 1,
        relationship_types: Optional[List[str]] = None
    ) -> List[ExpandedResult]:
        """
        Expande a partir de entidades encontradas no retrieval.

        Args:
            entity_ids: IDs das entidades seed (ex: "lei:12345", "artigo:5_cf88")
            tenant_id: ID do tenant para isolamento
            hops: Número de hops (1 ou 2)
            relationship_types: Tipos de relacionamento para seguir
                               (default: CITA, REGULAMENTA, INTERPRETA, PRECEDENTE)

        Returns:
            Lista de resultados expandidos com paths explicáveis
        """
        await self.connect()

        rel_types = relationship_types or ["CITA", "REGULAMENTA", "INTERPRETA", "PRECEDENTE", "REVOGA"]
        rel_pattern = "|".join(rel_types)

        # Query para 1-hop
        if hops == 1:
            query = f"""
            UNWIND $entity_ids AS eid
            MATCH (seed:Entity {{id: eid}})
            WHERE seed.tenant_id = $tenant_id OR seed.scope = 'global'
            OPTIONAL MATCH path = (seed)-[r:{rel_pattern}]-(related:Entity)
            WHERE related.tenant_id = $tenant_id OR related.scope = 'global'
            RETURN
                seed.id AS seed_id,
                seed AS seed_node,
                collect(DISTINCT {{
                    node: related,
                    relationship: type(r),
                    rel_props: properties(r),
                    direction: CASE WHEN startNode(r) = seed THEN 'outgoing' ELSE 'incoming' END
                }})[0..$max_nodes] AS expansions,
                [n IN nodes(path) | properties(n)] AS path_nodes,
                [r IN relationships(path) | {{type: type(r), props: properties(r)}}] AS path_rels
            """
        else:
            # Query para 2-hops
            query = f"""
            UNWIND $entity_ids AS eid
            MATCH (seed:Entity {{id: eid}})
            WHERE seed.tenant_id = $tenant_id OR seed.scope = 'global'
            OPTIONAL MATCH path = (seed)-[r1:{rel_pattern}]-(hop1:Entity)-[r2:{rel_pattern}]-(hop2:Entity)
            WHERE (hop1.tenant_id = $tenant_id OR hop1.scope = 'global')
              AND (hop2.tenant_id = $tenant_id OR hop2.scope = 'global')
              AND hop2 <> seed
            RETURN
                seed.id AS seed_id,
                seed AS seed_node,
                collect(DISTINCT {{
                    hop1_node: hop1,
                    hop1_rel: type(r1),
                    hop2_node: hop2,
                    hop2_rel: type(r2)
                }})[0..$max_nodes] AS expansions,
                [n IN nodes(path) | properties(n)] AS path_nodes,
                [r IN relationships(path) | {{type: type(r), props: properties(r)}}] AS path_rels
            """

        async with self._driver.session(database=self.database) as session:
            result = await session.run(
                query,
                entity_ids=entity_ids,
                tenant_id=tenant_id,
                max_nodes=self.max_expanded_nodes
            )
            records = await result.data()

        return self._parse_expansion_results(records, hops)

    async def get_explainable_paths(
        self,
        source_id: str,
        target_id: str,
        tenant_id: str,
        max_paths: int = 3
    ) -> List[GraphPath]:
        """
        Retorna caminhos explicáveis entre duas entidades.

        Útil para explicar por que uma lei se relaciona com outra.
        """
        await self.connect()

        query = """
        MATCH path = shortestPath((source:Entity {id: $source_id})-[*1..4]-(target:Entity {id: $target_id}))
        WHERE all(n IN nodes(path) WHERE n.tenant_id = $tenant_id OR n.scope = 'global')
        RETURN
            [n IN nodes(path) | {id: n.id, type: labels(n)[1], name: n.name, props: properties(n)}] AS nodes,
            [r IN relationships(path) | {type: type(r), props: properties(r)}] AS relationships
        LIMIT $max_paths
        """

        async with self._driver.session(database=self.database) as session:
            result = await session.run(
                query,
                source_id=source_id,
                target_id=target_id,
                tenant_id=tenant_id,
                max_paths=max_paths
            )
            records = await result.data()

        paths = []
        for record in records:
            explanation = self._generate_path_explanation(record["nodes"], record["relationships"])
            paths.append(GraphPath(
                nodes=record["nodes"],
                relationships=record["relationships"],
                score=1.0 / len(record["nodes"]),  # Paths mais curtos = maior score
                explanation=explanation
            ))

        return paths

    async def get_subgraph_for_visualization(
        self,
        entity_ids: List[str],
        tenant_id: str,
        depth: int = 2,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Retorna subgrafo para visualização no frontend.

        Returns:
            {
                "nodes": [...],
                "edges": [...],
                "metadata": {...}
            }
        """
        await self.connect()

        query = """
        UNWIND $entity_ids AS eid
        MATCH (seed:Entity {id: eid})
        WHERE seed.tenant_id = $tenant_id OR seed.scope = 'global'
        CALL apoc.path.subgraphAll(seed, {
            maxLevel: $depth,
            relationshipFilter: 'CITA|REGULAMENTA|INTERPRETA|PRECEDENTE|REVOGA',
            limit: $limit
        })
        YIELD nodes, relationships
        RETURN
            [n IN nodes | {
                id: n.id,
                label: labels(n)[1],
                name: coalesce(n.name, n.titulo, n.id),
                props: properties(n)
            }] AS nodes,
            [r IN relationships | {
                source: startNode(r).id,
                target: endNode(r).id,
                type: type(r),
                props: properties(r)
            }] AS edges
        """

        async with self._driver.session(database=self.database) as session:
            result = await session.run(
                query,
                entity_ids=entity_ids,
                tenant_id=tenant_id,
                depth=depth,
                limit=limit
            )
            record = await result.single()

        if not record:
            return {"nodes": [], "edges": [], "metadata": {"empty": True}}

        return {
            "nodes": record["nodes"],
            "edges": record["edges"],
            "metadata": {
                "seed_count": len(entity_ids),
                "depth": depth,
                "node_count": len(record["nodes"]),
                "edge_count": len(record["edges"])
            }
        }

    def _parse_expansion_results(self, records: List[Dict], hops: int) -> List[ExpandedResult]:
        """Parseia resultados da query de expansão."""
        results = []
        for record in records:
            if not record.get("seed_id"):
                continue

            expanded = ExpandedResult(
                original_chunk_uid=record["seed_id"],
                original_score=1.0,
                expanded_entities=[],
                paths=[],
                total_score=1.0
            )

            for exp in record.get("expansions", []):
                if hops == 1 and exp.get("node"):
                    expanded.expanded_entities.append({
                        "id": exp["node"].get("id"),
                        "name": exp["node"].get("name"),
                        "type": exp.get("relationship"),
                        "direction": exp.get("direction")
                    })
                elif hops == 2:
                    if exp.get("hop1_node"):
                        expanded.expanded_entities.append({
                            "id": exp["hop1_node"].get("id"),
                            "hop": 1
                        })
                    if exp.get("hop2_node"):
                        expanded.expanded_entities.append({
                            "id": exp["hop2_node"].get("id"),
                            "hop": 2
                        })

            # Criar paths explicáveis
            if record.get("path_nodes"):
                explanation = self._generate_path_explanation(
                    record["path_nodes"],
                    record.get("path_rels", [])
                )
                expanded.paths.append(GraphPath(
                    nodes=record["path_nodes"],
                    relationships=record.get("path_rels", []),
                    score=1.0,
                    explanation=explanation
                ))

            results.append(expanded)

        return results

    def _generate_path_explanation(
        self,
        nodes: List[Dict],
        relationships: List[Dict]
    ) -> str:
        """Gera explicação em linguagem natural do path."""
        if not nodes:
            return ""

        parts = []
        for i, node in enumerate(nodes):
            node_name = node.get("name") or node.get("titulo") or node.get("id", "?")
            parts.append(node_name)

            if i < len(relationships):
                rel = relationships[i]
                rel_type = rel.get("type", "relaciona com")
                rel_map = {
                    "CITA": "cita",
                    "REGULAMENTA": "regulamenta",
                    "INTERPRETA": "interpreta",
                    "REVOGA": "revoga",
                    "PRECEDENTE": "é precedente de"
                }
                parts.append(f" → {rel_map.get(rel_type, rel_type)} → ")

        return "".join(parts)
```

#### Task 1.2.2: ColPali Visual Retrieval Service
**Arquivo**: `apps/api/app/services/rag/core/colpali_service.py`

```python
"""
ColPali Visual Document Retrieval Service
Retrieval de documentos usando visão computacional (sem OCR).
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import asyncio
import torch
from PIL import Image
import io
import base64

@dataclass
class VisualRetrievalResult:
    """Resultado de retrieval visual."""
    doc_id: str
    page_num: int
    score: float
    image_base64: Optional[str] = None
    patch_highlights: Optional[List[Dict]] = None
    metadata: Optional[Dict] = None

class ColPaliService:
    """
    Serviço de retrieval visual usando ColPali/ColQwen2.5.

    Ideal para:
    - PDFs com tabelas complexas
    - Documentos com figuras/infográficos
    - Layouts não-standard que OCR falha

    Referências:
    - Paper: https://arxiv.org/abs/2407.01449
    - GitHub: https://github.com/illuin-tech/colpali
    - Models: https://huggingface.co/vidore
    """

    def __init__(
        self,
        model_name: str = "vidore/colqwen2.5-v1",
        device: str = "auto",
        embedding_dim: int = 128,
        batch_size: int = 4,
        cache_dir: Optional[str] = None
    ):
        """
        Args:
            model_name: Nome do modelo no HuggingFace
                       - vidore/colpali (original, PaliGemma)
                       - vidore/colqwen2.5-v1 (mais eficiente, Qwen2.5-VL)
                       - vidore/colsmol (menor, para CPU)
            device: "cuda", "cpu" ou "auto"
            embedding_dim: Dimensão dos embeddings (128 default)
            batch_size: Batch size para processamento
        """
        self.model_name = model_name
        self.device = self._resolve_device(device)
        self.embedding_dim = embedding_dim
        self.batch_size = batch_size
        self.cache_dir = cache_dir

        self._model = None
        self._processor = None
        self._loaded = False

    def _resolve_device(self, device: str) -> str:
        if device == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        return device

    async def load_model(self):
        """Carrega modelo de forma lazy."""
        if self._loaded:
            return

        # Importa só quando necessário (modelo grande)
        from colpali_engine.models import ColQwen2_5, ColQwen2_5_Processor

        self._model = ColQwen2_5.from_pretrained(
            self.model_name,
            torch_dtype=torch.bfloat16 if self.device == "cuda" else torch.float32,
            device_map=self.device,
            cache_dir=self.cache_dir
        ).eval()

        self._processor = ColQwen2_5_Processor.from_pretrained(self.model_name)
        self._loaded = True

    async def index_document_pages(
        self,
        pages: List[Tuple[str, int, Image.Image]],  # (doc_id, page_num, image)
        tenant_id: str
    ) -> List[Dict[str, Any]]:
        """
        Indexa páginas de documentos como imagens.

        Args:
            pages: Lista de (doc_id, page_num, PIL.Image)
            tenant_id: ID do tenant

        Returns:
            Lista de embeddings com metadados para armazenar
        """
        await self.load_model()

        results = []

        # Processa em batches
        for i in range(0, len(pages), self.batch_size):
            batch = pages[i:i + self.batch_size]
            images = [p[2] for p in batch]

            # Processa imagens
            with torch.no_grad():
                batch_images = self._processor.process_images(images).to(self.device)
                image_embeddings = self._model(**batch_images)

            # Cada página gera múltiplos vetores (late interaction)
            for j, (doc_id, page_num, _) in enumerate(batch):
                embeddings = image_embeddings[j].cpu().numpy().tolist()

                results.append({
                    "doc_id": doc_id,
                    "page_num": page_num,
                    "tenant_id": tenant_id,
                    "embeddings": embeddings,  # Multi-vector (patches)
                    "num_patches": len(embeddings),
                    "model": self.model_name
                })

        return results

    async def search(
        self,
        query: str,
        tenant_id: str,
        indexed_pages: List[Dict],  # Páginas pré-indexadas
        top_k: int = 5
    ) -> List[VisualRetrievalResult]:
        """
        Busca por query usando late interaction (ColBERT-style).

        Args:
            query: Query textual do usuário
            tenant_id: ID do tenant
            indexed_pages: Páginas com embeddings pré-computados
            top_k: Número de resultados

        Returns:
            Lista de resultados ranqueados por similaridade
        """
        await self.load_model()

        # Embed query
        with torch.no_grad():
            batch_queries = self._processor.process_queries([query]).to(self.device)
            query_embeddings = self._model(**batch_queries)[0]  # [num_tokens, dim]

        scores = []

        for page in indexed_pages:
            if page["tenant_id"] != tenant_id and page.get("scope") != "global":
                continue

            # Late interaction: MaxSim
            page_embeddings = torch.tensor(page["embeddings"]).to(self.device)

            # Para cada token da query, encontra o patch mais similar
            # score = sum(max(sim(query_token, page_patches)) for query_token in query)
            sim_matrix = torch.matmul(query_embeddings, page_embeddings.T)
            max_sim_per_token = sim_matrix.max(dim=1).values
            total_score = max_sim_per_token.sum().item()

            scores.append({
                "doc_id": page["doc_id"],
                "page_num": page["page_num"],
                "score": total_score,
                "metadata": page.get("metadata", {})
            })

        # Ordena por score
        scores.sort(key=lambda x: x["score"], reverse=True)

        results = []
        for item in scores[:top_k]:
            results.append(VisualRetrievalResult(
                doc_id=item["doc_id"],
                page_num=item["page_num"],
                score=item["score"],
                metadata=item["metadata"]
            ))

        return results

    async def search_with_highlights(
        self,
        query: str,
        page_image: Image.Image,
        page_embeddings: List[List[float]]
    ) -> Tuple[float, List[Dict]]:
        """
        Busca com highlight de patches relevantes.

        Útil para explicabilidade - mostra quais partes da página
        matcham com quais termos da query.

        Returns:
            (score, patches_highlights)
        """
        await self.load_model()

        with torch.no_grad():
            batch_queries = self._processor.process_queries([query]).to(self.device)
            query_embs = self._model(**batch_queries)[0]

        page_embs = torch.tensor(page_embeddings).to(self.device)

        # Calcula similaridade por token/patch
        sim_matrix = torch.matmul(query_embs, page_embs.T)

        # Encontra best patches para cada token
        query_tokens = query.split()
        highlights = []

        for i, token in enumerate(query_tokens):
            best_patch_idx = sim_matrix[i].argmax().item()
            best_sim = sim_matrix[i, best_patch_idx].item()

            # Calcula posição aproximada do patch na imagem
            # (depende da resolução do modelo, ~14x14 patches típico)
            patch_row = best_patch_idx // 14
            patch_col = best_patch_idx % 14

            highlights.append({
                "token": token,
                "patch_idx": best_patch_idx,
                "similarity": best_sim,
                "position": {"row": patch_row, "col": patch_col}
            })

        total_score = sim_matrix.max(dim=1).values.sum().item()
        return total_score, highlights


class ColPaliQdrantAdapter:
    """
    Adapter para armazenar embeddings ColPali no Qdrant.

    Como ColPali usa multi-vector (um vetor por patch), precisamos
    de uma estratégia especial de armazenamento.
    """

    def __init__(
        self,
        qdrant_url: str,
        collection_name: str = "visual_docs",
        colpali_service: Optional[ColPaliService] = None
    ):
        from qdrant_client import QdrantClient
        from qdrant_client.models import VectorParams, Distance

        self.client = QdrantClient(url=qdrant_url)
        self.collection_name = collection_name
        self.colpali = colpali_service or ColPaliService()

        # Cria collection se não existir
        # Usa multi-vector com late interaction
        self._ensure_collection()

    def _ensure_collection(self):
        """Garante que collection existe com config correta."""
        from qdrant_client.models import VectorParams, Distance

        collections = [c.name for c in self.client.get_collections().collections]

        if self.collection_name not in collections:
            # ColPali usa multi-vector, então criamos com config especial
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "patch_vectors": VectorParams(
                        size=128,
                        distance=Distance.COSINE,
                        multivector_config={
                            "comparator": "max_sim"  # Late interaction
                        }
                    )
                }
            )

    async def index_pdf(
        self,
        pdf_path: str,
        doc_id: str,
        tenant_id: str
    ) -> int:
        """
        Indexa PDF convertendo páginas em imagens.

        Returns:
            Número de páginas indexadas
        """
        import fitz  # PyMuPDF

        doc = fitz.open(pdf_path)
        pages = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            pages.append((doc_id, page_num, img))

        doc.close()

        # Indexa com ColPali
        indexed = await self.colpali.index_document_pages(pages, tenant_id)

        # Salva no Qdrant
        from qdrant_client.models import PointStruct

        points = []
        for i, item in enumerate(indexed):
            points.append(PointStruct(
                id=f"{doc_id}_{item['page_num']}",
                vector={"patch_vectors": item["embeddings"]},
                payload={
                    "doc_id": item["doc_id"],
                    "page_num": item["page_num"],
                    "tenant_id": tenant_id,
                    "num_patches": item["num_patches"]
                }
            ))

        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )

        return len(indexed)
```

#### Task 1.2.3: Retrieval Router (Feature Flags)
**Arquivo**: `apps/api/app/services/rag/core/retrieval_router.py`

```python
"""
Retrieval Router com Feature Flags
Roteamento inteligente entre diferentes backends de retrieval.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from enum import Enum
import asyncio
import time

class RetrievalBackend(Enum):
    """Backends de retrieval disponíveis."""
    QDRANT = "qdrant"
    OPENSEARCH = "opensearch"
    NEO4J_VECTOR = "neo4j_vector"
    NEO4J_FULLTEXT = "neo4j_fulltext"
    COLPALI = "colpali"
    HYBRID = "hybrid"

@dataclass
class RetrievalMetrics:
    """Métricas de um retrieval."""
    backend: RetrievalBackend
    latency_ms: float
    result_count: int
    avg_score: float
    timestamp: float = field(default_factory=time.time)

@dataclass
class RouterConfig:
    """Configuração do router."""
    # Feature flags
    enable_qdrant: bool = True
    enable_opensearch: bool = True
    enable_neo4j_vector: bool = False  # Fase 2
    enable_neo4j_fulltext: bool = False  # Fase 2
    enable_colpali: bool = True
    enable_graph_expansion: bool = True  # Neo4j multi-hop

    # Pesos para fusão
    qdrant_weight: float = 0.5
    opensearch_weight: float = 0.5
    neo4j_vector_weight: float = 0.0
    neo4j_fulltext_weight: float = 0.0
    colpali_weight: float = 0.3

    # Thresholds
    lexical_strong_threshold: float = 0.7
    skip_vector_if_lexical_strong: bool = True
    visual_query_threshold: float = 0.5  # Score para ativar ColPali

    # Métricas
    collect_metrics: bool = True
    metrics_window_size: int = 1000

class RetrievalRouter:
    """
    Router inteligente que decide quais backends usar.

    Fase 1: Qdrant + OpenSearch + ColPali + Neo4j (graph only)
    Fase 2: Adiciona Neo4j Vector + Fulltext em paralelo
    """

    def __init__(
        self,
        config: RouterConfig,
        qdrant_service: Any = None,
        opensearch_service: Any = None,
        neo4j_expansion: Any = None,
        colpali_service: Any = None,
        neo4j_hybrid: Any = None  # Fase 2
    ):
        self.config = config
        self.qdrant = qdrant_service
        self.opensearch = opensearch_service
        self.neo4j_expansion = neo4j_expansion
        self.colpali = colpali_service
        self.neo4j_hybrid = neo4j_hybrid

        self._metrics: List[RetrievalMetrics] = []

    async def route_and_retrieve(
        self,
        query: str,
        tenant_id: str,
        case_id: Optional[str] = None,
        top_k: int = 10,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Roteia query para backends apropriados e faz fusão.

        Returns:
            {
                "results": [...],
                "backends_used": [...],
                "metrics": {...},
                "graph_expansion": {...}  # Se habilitado
            }
        """
        # 1. Classifica tipo de query
        query_type = self._classify_query(query)

        # 2. Decide backends a usar
        backends = self._select_backends(query_type)

        # 3. Executa retrievals em paralelo
        tasks = []
        backend_names = []

        for backend in backends:
            if backend == RetrievalBackend.QDRANT and self.qdrant:
                tasks.append(self._retrieve_qdrant(query, tenant_id, case_id, top_k))
                backend_names.append("qdrant")
            elif backend == RetrievalBackend.OPENSEARCH and self.opensearch:
                tasks.append(self._retrieve_opensearch(query, tenant_id, case_id, top_k))
                backend_names.append("opensearch")
            elif backend == RetrievalBackend.COLPALI and self.colpali:
                tasks.append(self._retrieve_colpali(query, tenant_id, top_k))
                backend_names.append("colpali")
            elif backend == RetrievalBackend.NEO4J_VECTOR and self.neo4j_hybrid:
                tasks.append(self._retrieve_neo4j_vector(query, tenant_id, top_k))
                backend_names.append("neo4j_vector")
            elif backend == RetrievalBackend.NEO4J_FULLTEXT and self.neo4j_hybrid:
                tasks.append(self._retrieve_neo4j_fulltext(query, tenant_id, top_k))
                backend_names.append("neo4j_fulltext")

        # Executa em paralelo
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        # 4. Processa resultados e coleta métricas
        all_results = []
        metrics = {}

        for i, (name, results) in enumerate(zip(backend_names, results_list)):
            if isinstance(results, Exception):
                metrics[name] = {"error": str(results)}
                continue

            all_results.extend([
                {**r, "_source": name, "_weight": self._get_weight(name)}
                for r in results.get("results", [])
            ])
            metrics[name] = results.get("metrics", {})

        # 5. Fusão com RRF
        fused_results = self._rrf_fusion(all_results, top_k)

        # 6. Expansão de grafo (se habilitado)
        graph_expansion = None
        if self.config.enable_graph_expansion and self.neo4j_expansion:
            entity_ids = self._extract_entity_ids(fused_results)
            if entity_ids:
                graph_expansion = await self.neo4j_expansion.expand_from_entities(
                    entity_ids=entity_ids,
                    tenant_id=tenant_id,
                    hops=2
                )

        return {
            "results": fused_results,
            "backends_used": backend_names,
            "metrics": metrics,
            "graph_expansion": graph_expansion,
            "query_type": query_type
        }

    def _classify_query(self, query: str) -> str:
        """Classifica tipo de query."""
        query_lower = query.lower()

        # Padrões de citação legal
        legal_patterns = ["art.", "artigo", "lei nº", "lei n.", "súmula", "cf/88", "cpc", "cpp"]
        if any(p in query_lower for p in legal_patterns):
            return "legal_citation"

        # Queries visuais (tabelas, figuras)
        visual_patterns = ["tabela", "figura", "gráfico", "imagem", "diagrama", "fluxograma"]
        if any(p in query_lower for p in visual_patterns):
            return "visual"

        # Queries de relacionamento (bom para grafo)
        graph_patterns = ["relaciona", "cita", "revoga", "regulamenta", "precedente"]
        if any(p in query_lower for p in graph_patterns):
            return "graph_traversal"

        return "general"

    def _select_backends(self, query_type: str) -> List[RetrievalBackend]:
        """Seleciona backends baseado no tipo de query."""
        backends = []

        # Sempre usa os backends principais habilitados
        if self.config.enable_opensearch:
            backends.append(RetrievalBackend.OPENSEARCH)

        if self.config.enable_qdrant:
            backends.append(RetrievalBackend.QDRANT)

        # ColPali para queries visuais
        if query_type == "visual" and self.config.enable_colpali:
            backends.append(RetrievalBackend.COLPALI)

        # Neo4j backends (Fase 2)
        if self.config.enable_neo4j_fulltext:
            backends.append(RetrievalBackend.NEO4J_FULLTEXT)

        if self.config.enable_neo4j_vector:
            backends.append(RetrievalBackend.NEO4J_VECTOR)

        return backends

    def _get_weight(self, backend_name: str) -> float:
        """Retorna peso do backend para fusão."""
        weights = {
            "qdrant": self.config.qdrant_weight,
            "opensearch": self.config.opensearch_weight,
            "neo4j_vector": self.config.neo4j_vector_weight,
            "neo4j_fulltext": self.config.neo4j_fulltext_weight,
            "colpali": self.config.colpali_weight
        }
        return weights.get(backend_name, 0.5)

    def _rrf_fusion(
        self,
        results: List[Dict],
        top_k: int,
        k: int = 60
    ) -> List[Dict]:
        """Reciprocal Rank Fusion."""
        # Agrupa por chunk_uid
        scores = {}

        for r in results:
            uid = r.get("chunk_uid") or r.get("doc_id")
            if not uid:
                continue

            if uid not in scores:
                scores[uid] = {"item": r, "rrf_score": 0.0}

            # RRF: 1 / (k + rank)
            rank = results.index(r) + 1
            weight = r.get("_weight", 0.5)
            scores[uid]["rrf_score"] += weight * (1.0 / (k + rank))

        # Ordena por RRF score
        sorted_items = sorted(
            scores.values(),
            key=lambda x: x["rrf_score"],
            reverse=True
        )

        return [
            {**item["item"], "rrf_score": item["rrf_score"]}
            for item in sorted_items[:top_k]
        ]

    def _extract_entity_ids(self, results: List[Dict]) -> List[str]:
        """Extrai IDs de entidades mencionadas nos resultados."""
        entity_ids = []

        for r in results:
            # Tenta extrair de metadata
            meta = r.get("metadata", {})

            if "lei_id" in meta:
                entity_ids.append(f"lei:{meta['lei_id']}")
            if "artigo_id" in meta:
                entity_ids.append(f"artigo:{meta['artigo_id']}")
            if "sumula_id" in meta:
                entity_ids.append(f"sumula:{meta['sumula_id']}")

        return list(set(entity_ids))[:20]  # Limita a 20 seeds

    # Métodos de retrieval por backend (implementar com serviços existentes)
    async def _retrieve_qdrant(self, query, tenant_id, case_id, top_k):
        start = time.time()
        results = await self.qdrant.search(query, tenant_id, case_id, top_k)
        return {
            "results": results,
            "metrics": {"latency_ms": (time.time() - start) * 1000}
        }

    async def _retrieve_opensearch(self, query, tenant_id, case_id, top_k):
        start = time.time()
        results = await self.opensearch.search(query, tenant_id, case_id, top_k)
        return {
            "results": results,
            "metrics": {"latency_ms": (time.time() - start) * 1000}
        }

    async def _retrieve_colpali(self, query, tenant_id, top_k):
        start = time.time()
        results = await self.colpali.search(query, tenant_id, [], top_k)
        return {
            "results": [
                {"chunk_uid": f"{r.doc_id}_{r.page_num}", "score": r.score}
                for r in results
            ],
            "metrics": {"latency_ms": (time.time() - start) * 1000}
        }

    async def _retrieve_neo4j_vector(self, query, tenant_id, top_k):
        # Fase 2 - a implementar
        pass

    async def _retrieve_neo4j_fulltext(self, query, tenant_id, top_k):
        # Fase 2 - a implementar
        pass

    # Métodos para métricas e comparação
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Retorna resumo de métricas para decisão de migração."""
        if not self._metrics:
            return {}

        by_backend = {}
        for m in self._metrics[-self.config.metrics_window_size:]:
            name = m.backend.value
            if name not in by_backend:
                by_backend[name] = {
                    "count": 0,
                    "total_latency": 0,
                    "total_results": 0,
                    "total_score": 0
                }

            by_backend[name]["count"] += 1
            by_backend[name]["total_latency"] += m.latency_ms
            by_backend[name]["total_results"] += m.result_count
            by_backend[name]["total_score"] += m.avg_score

        summary = {}
        for name, data in by_backend.items():
            count = data["count"]
            summary[name] = {
                "queries": count,
                "avg_latency_ms": data["total_latency"] / count,
                "avg_results": data["total_results"] / count,
                "avg_score": data["total_score"] / count
            }

        return summary
```

---

### 1.3 Integração com Pipeline Existente

#### Task 1.3.1: Modificar RAG Pipeline
**Arquivo**: `apps/api/app/services/rag/pipeline/rag_pipeline.py`

```python
# Adicionar após estágio 9 (Graph Enrichment)

# === NOVO ESTÁGIO: Graph Expansion (Neo4j Multi-Hop) ===
async def _stage_graph_expansion(
    self,
    results: List[RetrievalResult],
    query: str,
    tenant_id: str,
    config: RAGConfig
) -> Tuple[List[RetrievalResult], Dict]:
    """
    Estágio de expansão de grafo usando Neo4j.

    - Extrai entidades mencionadas nos resultados
    - Expande 1-2 hops no grafo de conhecimento
    - Adiciona paths explicáveis
    """
    if not config.enable_graph_expansion:
        return results, {"skipped": True}

    from app.services.rag.core.neo4j_graph_expansion import Neo4jGraphExpansionService

    expansion_service = Neo4jGraphExpansionService(
        uri=config.neo4j_uri,
        user=config.neo4j_user,
        password=config.neo4j_password,
        database=config.neo4j_database,
        max_hops=config.graph_expansion_hops
    )

    try:
        # Extrai entity IDs dos resultados
        entity_ids = []
        for r in results[:10]:  # Top 10
            if r.metadata:
                if "lei_id" in r.metadata:
                    entity_ids.append(f"lei:{r.metadata['lei_id']}")
                if "artigo_id" in r.metadata:
                    entity_ids.append(f"artigo:{r.metadata['artigo_id']}")

        if not entity_ids:
            return results, {"no_entities": True}

        # Expande no grafo
        expansions = await expansion_service.expand_from_entities(
            entity_ids=list(set(entity_ids))[:20],
            tenant_id=tenant_id,
            hops=config.graph_expansion_hops
        )

        # Adiciona expansões aos resultados
        expansion_context = {
            "expansions": expansions,
            "paths": [exp.paths for exp in expansions if exp.paths],
            "related_entities": [
                ent for exp in expansions
                for ent in exp.expanded_entities
            ]
        }

        return results, expansion_context

    finally:
        await expansion_service.close()
```

---

## FASE 2: Neo4j Hybrid (Vector + Fulltext) em Paralelo

### 2.1 Quando Iniciar Fase 2

**Pré-requisitos:**
1. Fase 1 completa e estável em produção
2. Métricas coletadas por ≥2 semanas
3. Baseline de latência/recall documentado

**Critérios de comparação:**
```python
# Comparar antes de desligar Qdrant/OpenSearch:
{
    "latency_p50_ms": {"qdrant": X, "neo4j": Y},  # Neo4j deve ser ≤ 1.2x Qdrant
    "latency_p99_ms": {"qdrant": X, "neo4j": Y},  # Neo4j deve ser ≤ 1.5x Qdrant
    "recall@10": {"qdrant": X, "neo4j": Y},       # Neo4j deve ser ≥ 0.95x Qdrant
    "mrr": {"qdrant": X, "neo4j": Y}              # Neo4j deve ser ≥ 0.95x Qdrant
}
```

### 2.2 Implementação Neo4j Hybrid Service
**Arquivo**: `apps/api/app/services/rag/core/neo4j_hybrid_service.py`

```python
"""
Neo4j Hybrid Service - Vector + Fulltext
Para Fase 2: rodar em paralelo com Qdrant/OpenSearch.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from neo4j import AsyncDriver, AsyncGraphDatabase
import asyncio

@dataclass
class Neo4jHybridResult:
    """Resultado de busca híbrida Neo4j."""
    node_id: str
    text: str
    score: float
    source: str  # "vector" | "fulltext" | "hybrid"
    metadata: Dict[str, Any]

class Neo4jHybridService:
    """
    Serviço de busca híbrida usando índices nativos do Neo4j.

    Usa:
    - Vector Index (HNSW) para busca semântica
    - Fulltext Index (Lucene) para busca lexical
    - HybridRetriever para combinação

    Referência: https://neo4j.com/docs/neo4j-graphrag-python/current/
    """

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        database: str = "iudex",
        vector_index_name: str = "chunk_embeddings",
        fulltext_index_name: str = "chunk_text",
        embedding_dim: int = 3072
    ):
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.vector_index_name = vector_index_name
        self.fulltext_index_name = fulltext_index_name
        self.embedding_dim = embedding_dim
        self._driver: Optional[AsyncDriver] = None

    async def connect(self):
        if not self._driver:
            self._driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password)
            )

    async def setup_indexes(self):
        """
        Cria índices de vetor e fulltext no Neo4j.

        Executar uma vez na inicialização.
        """
        await self.connect()

        async with self._driver.session(database=self.database) as session:
            # Vector Index
            await session.run(f"""
                CREATE VECTOR INDEX {self.vector_index_name} IF NOT EXISTS
                FOR (c:Chunk)
                ON c.embedding
                OPTIONS {{
                    indexConfig: {{
                        `vector.dimensions`: {self.embedding_dim},
                        `vector.similarity_function`: 'cosine'
                    }}
                }}
            """)

            # Fulltext Index
            await session.run(f"""
                CREATE FULLTEXT INDEX {self.fulltext_index_name} IF NOT EXISTS
                FOR (c:Chunk)
                ON EACH [c.text]
                OPTIONS {{
                    indexConfig: {{
                        `fulltext.analyzer`: 'brazilian'
                    }}
                }}
            """)

    async def ingest_chunk(
        self,
        chunk_uid: str,
        text: str,
        embedding: List[float],
        tenant_id: str,
        metadata: Dict[str, Any]
    ):
        """Ingere chunk com embedding no Neo4j."""
        await self.connect()

        async with self._driver.session(database=self.database) as session:
            await session.run("""
                MERGE (c:Chunk {uid: $uid})
                SET c.text = $text,
                    c.embedding = $embedding,
                    c.tenant_id = $tenant_id,
                    c.scope = $scope,
                    c.source_type = $source_type,
                    c.updated_at = datetime()
                WITH c
                UNWIND keys($metadata) AS key
                SET c[key] = $metadata[key]
            """,
                uid=chunk_uid,
                text=text,
                embedding=embedding,
                tenant_id=tenant_id,
                scope=metadata.get("scope", "private"),
                source_type=metadata.get("source_type", "unknown"),
                metadata=metadata
            )

    async def vector_search(
        self,
        query_embedding: List[float],
        tenant_id: str,
        top_k: int = 10
    ) -> List[Neo4jHybridResult]:
        """Busca vetorial usando HNSW index."""
        await self.connect()

        async with self._driver.session(database=self.database) as session:
            result = await session.run(f"""
                CALL db.index.vector.queryNodes(
                    '{self.vector_index_name}',
                    $top_k,
                    $embedding
                )
                YIELD node, score
                WHERE node.tenant_id = $tenant_id OR node.scope = 'global'
                RETURN
                    node.uid AS uid,
                    node.text AS text,
                    score,
                    properties(node) AS metadata
                LIMIT $top_k
            """,
                embedding=query_embedding,
                tenant_id=tenant_id,
                top_k=top_k
            )

            records = await result.data()

        return [
            Neo4jHybridResult(
                node_id=r["uid"],
                text=r["text"],
                score=r["score"],
                source="vector",
                metadata=r["metadata"]
            )
            for r in records
        ]

    async def fulltext_search(
        self,
        query: str,
        tenant_id: str,
        top_k: int = 10
    ) -> List[Neo4jHybridResult]:
        """Busca fulltext usando Lucene index."""
        await self.connect()

        # Escape caracteres especiais do Lucene
        escaped_query = self._escape_lucene(query)

        async with self._driver.session(database=self.database) as session:
            result = await session.run(f"""
                CALL db.index.fulltext.queryNodes(
                    '{self.fulltext_index_name}',
                    $query
                )
                YIELD node, score
                WHERE node.tenant_id = $tenant_id OR node.scope = 'global'
                RETURN
                    node.uid AS uid,
                    node.text AS text,
                    score,
                    properties(node) AS metadata
                LIMIT $top_k
            """,
                query=escaped_query,
                tenant_id=tenant_id,
                top_k=top_k
            )

            records = await result.data()

        return [
            Neo4jHybridResult(
                node_id=r["uid"],
                text=r["text"],
                score=r["score"],
                source="fulltext",
                metadata=r["metadata"]
            )
            for r in records
        ]

    async def hybrid_search(
        self,
        query: str,
        query_embedding: List[float],
        tenant_id: str,
        top_k: int = 10,
        vector_weight: float = 0.5,
        fulltext_weight: float = 0.5
    ) -> List[Neo4jHybridResult]:
        """
        Busca híbrida combinando vector + fulltext.

        Usa RRF para fusão de scores.
        """
        # Executa buscas em paralelo
        vector_results, fulltext_results = await asyncio.gather(
            self.vector_search(query_embedding, tenant_id, top_k * 2),
            self.fulltext_search(query, tenant_id, top_k * 2)
        )

        # RRF Fusion
        scores = {}
        k = 60

        for i, r in enumerate(vector_results):
            if r.node_id not in scores:
                scores[r.node_id] = {"result": r, "rrf": 0}
            scores[r.node_id]["rrf"] += vector_weight * (1 / (k + i + 1))

        for i, r in enumerate(fulltext_results):
            if r.node_id not in scores:
                scores[r.node_id] = {"result": r, "rrf": 0}
            scores[r.node_id]["rrf"] += fulltext_weight * (1 / (k + i + 1))

        # Ordena e retorna top_k
        sorted_results = sorted(
            scores.values(),
            key=lambda x: x["rrf"],
            reverse=True
        )[:top_k]

        return [
            Neo4jHybridResult(
                node_id=item["result"].node_id,
                text=item["result"].text,
                score=item["rrf"],
                source="hybrid",
                metadata=item["result"].metadata
            )
            for item in sorted_results
        ]

    def _escape_lucene(self, query: str) -> str:
        """Escapa caracteres especiais do Lucene."""
        special_chars = r'+-&|!(){}[]^"~*?:\/'
        for char in special_chars:
            query = query.replace(char, f"\\{char}")
        return query
```

---

## Decisão: Manter Embeddings OpenAI

### Contexto
O Iudex já usa `text-embedding-3-large` (3072 dims) da OpenAI indexado no Qdrant.

### Decisão: **MANTER**

| Fase | Ação | Justificativa |
|------|------|---------------|
| **Fase 1** | Manter OpenAI no Qdrant | Zero risco, já funciona |
| **Fase 2** | Copiar mesmos embeddings para Neo4j | Evita re-indexação |
| **Futuro** | Avaliar embedding local se custo for problema | Só se necessário |

### Motivos para NÃO trocar agora

1. **Re-indexação cara**: Milhões de chunks já indexados
2. **Qualidade**: OpenAI ainda é estado da arte para português jurídico
3. **Cache**: Embeddings já cached, custo incremental baixo
4. **Risco**: Trocar modelo pode degradar recall

### ColPali é COMPLEMENTAR, não substituto

```
Texto puro        → OpenAI embeddings (Qdrant/Neo4j)
Documentos visuais → ColPali embeddings (índice separado)
```

ColPali gera embeddings de **imagens** (128 dims), não compete com embeddings de texto.

### Quando reconsiderar

- Custo de API OpenAI > $500/mês
- Latência de embedding > 500ms (improvável com cache)
- Requisito de rodar 100% offline
- Modelo local superar OpenAI em benchmark jurídico PT-BR

---

## Configuração de Environment Variables

**Adicionar ao `.env`:**

```bash
# === FASE 1: Graph Expansion ===
RAG_ENABLE_GRAPH_EXPANSION=true
RAG_GRAPH_EXPANSION_HOPS=2
RAG_GRAPH_MAX_EXPANDED_NODES=50

# === ColPali Visual Retrieval ===
RAG_ENABLE_COLPALI=true
COLPALI_MODEL=vidore/colqwen2.5-v1
COLPALI_DEVICE=auto
COLPALI_BATCH_SIZE=4

# === FASE 2: Neo4j Hybrid (Desabilitado inicialmente) ===
RAG_ENABLE_NEO4J_VECTOR=false
RAG_ENABLE_NEO4J_FULLTEXT=false
NEO4J_VECTOR_INDEX_NAME=chunk_embeddings
NEO4J_FULLTEXT_INDEX_NAME=chunk_text

# === Retrieval Router ===
RAG_ROUTER_QDRANT_WEIGHT=0.5
RAG_ROUTER_OPENSEARCH_WEIGHT=0.5
RAG_ROUTER_NEO4J_VECTOR_WEIGHT=0.0
RAG_ROUTER_NEO4J_FULLTEXT_WEIGHT=0.0
RAG_ROUTER_COLPALI_WEIGHT=0.3
RAG_ROUTER_COLLECT_METRICS=true
```

---

## Cronograma de Implementação

### Fase 1 (2-3 semanas)

| Semana | Tarefa | Entregável |
|--------|--------|------------|
| 1 | Neo4j Graph Expansion Service | `neo4j_graph_expansion.py` funcionando |
| 1 | Integrar com RAG Pipeline | Estágio 10.5 adicionado |
| 2 | ColPali Service | `colpali_service.py` funcionando |
| 2 | Retrieval Router básico | `retrieval_router.py` com flags |
| 3 | API endpoints | `/api/rag/graph/expand`, `/api/rag/graph/visualize` |
| 3 | Frontend grafo | Componente de visualização |

### Fase 2 (2-3 semanas, após métricas)

| Semana | Tarefa | Entregável |
|--------|--------|------------|
| 4 | Neo4j Hybrid Service | `neo4j_hybrid_service.py` |
| 4 | Migração de embeddings | Script de cópia Qdrant → Neo4j |
| 5 | Comparação A/B | Dashboard de métricas |
| 5-6 | Decisão de migração | Relatório com números |

---

## Métricas de Sucesso

### Fase 1
- [ ] Latência do pipeline ≤ 1.5s (p95)
- [ ] Paths explicáveis em ≥80% das queries com entidades
- [ ] ColPali melhora recall em queries visuais em ≥20%

### Fase 2
- [ ] Neo4j hybrid latência ≤ 1.2x Qdrant+OpenSearch
- [ ] Recall@10 ≥ 0.95x baseline
- [ ] Custo de infra reduzido em ≥30% (menos serviços)

---

## Referências

- [ColPali Paper](https://arxiv.org/abs/2407.01449)
- [ColPali GitHub](https://github.com/illuin-tech/colpali)
- [HuggingFace Vidore Models](https://huggingface.co/vidore)
- [Neo4j GraphRAG Python](https://github.com/neo4j/neo4j-graphrag-python)
- [Neo4j Vector Index Docs](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/)
- [Neo4j Fulltext Index Docs](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/full-text-indexes/)
- [Vespa ColPali Scaling](https://blog.vespa.ai/scaling-colpali-to-billions/)
