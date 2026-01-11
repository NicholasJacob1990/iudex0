"""
RAG Module for Legal Document Generation (v1.0)

This module provides hybrid retrieval (BM25 + embeddings) for legal documents
with 4 collections: lei (legislation), juris (jurisprudence), sei (internal), pecas_modelo (templates).

Requires: pip install chromadb sentence-transformers rank_bm25
"""

import os
import json
import hashlib
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

# Third-party imports
try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer, CrossEncoder
    from rank_bm25 import BM25Okapi
except ImportError as e:
    print(f"❌ RAG Module - Dependências faltando: {e}")
    print("Instale: pip install chromadb sentence-transformers rank_bm25")
    raise

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RAGModule")

# =============================================================================
# METADATA SCHEMAS
# =============================================================================

@dataclass
class LegislacaoMetadata:
    """Metadados para legislação consolidada"""
    tipo: str  # lei, decreto, resolução, portaria
    numero: str  # "8.666"
    ano: int
    jurisdicao: str  # BR, SP, RJ
    artigo: Optional[str] = None  # "art. 37, §6º"
    vigencia: str = "vigente"  # vigente, revogado, parcialmente_revogado
    data_atualizacao: Optional[str] = None
    
@dataclass
class JurisprudenciaMetadata:
    """Metadados para jurisprudência"""
    tribunal: str  # STF, STJ, TJSP, TRF1
    orgao: str  # Pleno, 1ª Turma, 2ª Seção
    tipo_decisao: str  # acordao, sumula, decisao_monocratica
    numero: str  # "REsp 1.234.567"
    relator: Optional[str] = None
    data_julgamento: Optional[str] = None
    tema: Optional[str] = None  # Tema 1.199, Repercussão Geral
    assuntos: List[str] = field(default_factory=list)  # Tags de assunto
    
@dataclass
class SEIMetadata:
    """Metadados para documentos internos (SEI)"""
    processo_sei: str  # Número do processo
    tipo_documento: str  # parecer, nota_tecnica, oficio, despacho
    orgao: str  # PGFN, AGU, Procuradoria de SP
    unidade: str  # Unidade organizacional
    data_criacao: str
    sigilo: str = "publico"  # publico, restrito, sigiloso
    tenant_id: str = "default"  # Para multi-tenancy
    responsavel_id: Optional[str] = None
    allowed_users: List[str] = field(default_factory=list)
    
@dataclass
class PecaModeloMetadata:
    """Metadados para modelos de peças jurídicas"""
    tipo_peca: str  # peticao_inicial, contestacao, recurso, parecer, contrato
    area: str  # civil, tributario, administrativo, trabalhista
    rito: str  # ordinario, sumario, sumarissimo, especial
    tribunal_destino: Optional[str] = None
    tese: Optional[str] = None  # Descrição da tese/argumento
    resultado: Optional[str] = None  # procedente, improcedente, acordo
    data_criacao: str = ""
    versao: str = "v1"
    aprovado: bool = True

@dataclass
class ClauseMetadata:
    """Metadados para blocos de cláusulas jurídicas (v2.0)"""
    # Identificação do bloco
    tipo_bloco: str  # preliminar, merito, pedido, fundamentacao
    subtipo: str  # ilegitimidade_passiva, prescricao, tutela_urgencia
    
    # Origem
    tipo_peca: str  # peticao_inicial, contestacao
    area: str  # civil, tributario
    tribunal: str  # TJRJ, STJ
    
    # Qualidade/Governança
    status: str = "aprovado" # rascunho, aprovado, arquivado
    aprovador: Optional[str] = None
    data_aprovacao: Optional[str] = None
    sucesso: bool = False # Se a tese foi acolhida
    
    # Versionamento
    versao: str = "v1"
    data_uso: Optional[str] = None
    
# =============================================================================
# RAG MANAGER
# =============================================================================

class RAGManager:
    """
    Gerenciador de RAG Híbrido para documentos jurídicos.
    
    Suporta 4 coleções:
    - lei: Legislação consolidada (artigos, leis, decretos)
    - juris: Jurisprudência (ementas, votos, súmulas)
    - sei: Documentos internos (pareceres, notas técnicas)
    - pecas_modelo: Modelos de peças jurídicas (blocos reutilizáveis)
    """
    
    COLLECTIONS = ["lei", "juris", "sei", "pecas_modelo"]
    DEFAULT_EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
    
    def __init__(
        self,
        persist_directory: str = "./chroma_db",
        embedding_model: str = None
    ):
        self.persist_directory = persist_directory
        
        # Initialize ChromaDB
        logger.info(f"🗄️ Inicializando ChromaDB em: {persist_directory}")
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Initialize embedding model
        model_name = embedding_model or self.DEFAULT_EMBEDDING_MODEL
        logger.info(f"🧠 Carregando modelo de embeddings: {model_name}")
        self.embedding_model = SentenceTransformer(model_name)
        
        # Create or get collections
        self.collections = {}
        for name in self.COLLECTIONS:
            self.collections[name] = self.client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"   ✅ Coleção '{name}': {self.collections[name].count()} documentos")
        
        # BM25 indices (built on-demand)
        self._bm25_indices = {}
        self._bm25_docs = {}
        self._reranker = None
        self._reranker_name = None

    def _get_reranker(self, model_name: Optional[str] = None):
        if model_name is None:
            model_name = os.getenv("RAG_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

        if self._reranker and self._reranker_name == model_name:
            return self._reranker

        try:
            self._reranker = CrossEncoder(model_name)
            self._reranker_name = model_name
            logger.info(f"🔁 Reranker carregado: {model_name}")
            return self._reranker
        except Exception as e:
            logger.warning(f"⚠️ Falha ao carregar reranker ({model_name}): {e}")
            self._reranker = None
            self._reranker_name = None
            return None
    
    # =========================================================================
    # INDEXING
    # =========================================================================
    
    def _generate_id(self, text: str, metadata: dict) -> str:
        """Gera ID único baseado no conteúdo"""
        content = text + json.dumps(metadata, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()
    
    def _chunk_text(
        self, 
        text: str, 
        chunk_size: int = 1000, 
        overlap: int = 100,
        structure_aware: bool = True
    ) -> List[str]:
        """
        Divide texto em chunks.
        Se structure_aware=True, tenta respeitar estrutura (artigos, parágrafos).
        """
        if structure_aware:
            # Tentar dividir por estrutura jurídica
            import re
            # Padrões comuns em textos jurídicos
            patterns = [
                r'\n(?=Art\.\s*\d+)',  # Início de artigo
                r'\n(?=§\s*\d+)',      # Início de parágrafo
                r'\n(?=\d+\.\s+[A-Z])', # Numeração de seção
                r'\n\n',               # Parágrafo duplo
            ]
            
            chunks = []
            current_chunk = ""
            
            # Dividir por linhas e reagrupar
            lines = text.split('\n')
            for line in lines:
                if len(current_chunk) + len(line) > chunk_size:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = line
                else:
                    current_chunk += '\n' + line
            
            if current_chunk:
                chunks.append(current_chunk.strip())
            
            return [c for c in chunks if len(c) > 50]  # Filtrar chunks muito pequenos
        
        else:
            # Chunking simples por tamanho
            chunks = []
            for i in range(0, len(text), chunk_size - overlap):
                chunk = text[i:i + chunk_size]
                if len(chunk) > 50:
                    chunks.append(chunk)
            return chunks
    
    def add_legislacao(
        self,
        text: str,
        metadata: LegislacaoMetadata,
        chunk: bool = True
    ) -> int:
        """Adiciona legislação ao índice"""
        meta_dict = {
            "tipo": metadata.tipo,
            "numero": metadata.numero,
            "ano": metadata.ano,
            "jurisdicao": metadata.jurisdicao,
            "artigo": metadata.artigo or "",
            "vigencia": metadata.vigencia,
            "data_atualizacao": metadata.data_atualizacao or "",
            "source_type": "lei"
        }
        
        if chunk:
            chunks = self._chunk_text(text, structure_aware=True)
        else:
            chunks = [text]
        
        ids = []
        embeddings = []
        documents = []
        metadatas = []
        
        for i, c in enumerate(chunks):
            doc_id = self._generate_id(c, meta_dict)
            ids.append(doc_id)
            embeddings.append(self.embedding_model.encode(c).tolist())
            documents.append(c)
            chunk_meta = {**meta_dict, "chunk_index": i}
            metadatas.append(chunk_meta)
        
        self.collections["lei"].add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        
        # Invalidate BM25 cache
        self._bm25_indices.pop("lei", None)
        
        logger.info(f"✅ Adicionados {len(chunks)} chunks de legislação ({metadata.tipo} {metadata.numero}/{metadata.ano})")
        return len(chunks)
    
    def add_jurisprudencia(
        self,
        text: str,
        metadata: JurisprudenciaMetadata,
        chunk: bool = True
    ) -> int:
        """Adiciona jurisprudência ao índice"""
        meta_dict = {
            "tribunal": metadata.tribunal,
            "orgao": metadata.orgao,
            "tipo_decisao": metadata.tipo_decisao,
            "numero": metadata.numero,
            "relator": metadata.relator or "",
            "data_julgamento": metadata.data_julgamento or "",
            "tema": metadata.tema or "",
            "assuntos": ",".join(metadata.assuntos),
            "source_type": "juris"
        }
        
        if chunk:
            chunks = self._chunk_text(text, structure_aware=True)
        else:
            chunks = [text]
        
        ids = []
        embeddings = []
        documents = []
        metadatas = []
        
        for i, c in enumerate(chunks):
            doc_id = self._generate_id(c, meta_dict)
            ids.append(doc_id)
            embeddings.append(self.embedding_model.encode(c).tolist())
            documents.append(c)
            chunk_meta = {**meta_dict, "chunk_index": i}
            metadatas.append(chunk_meta)
        
        self.collections["juris"].add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        
        self._bm25_indices.pop("juris", None)
        
        logger.info(f"✅ Adicionados {len(chunks)} chunks de jurisprudência ({metadata.tribunal} {metadata.numero})")
        return len(chunks)
    
    def add_sei(
        self,
        text: str,
        metadata: SEIMetadata,
        chunk: bool = True
    ) -> int:
        """Adiciona documento SEI ao índice (com controle de acesso)"""
        meta_dict = {
            "processo_sei": metadata.processo_sei,
            "tipo_documento": metadata.tipo_documento,
            "orgao": metadata.orgao,
            "unidade": metadata.unidade,
            "data_criacao": metadata.data_criacao,
            "sigilo": metadata.sigilo,
            "tenant_id": metadata.tenant_id,
            "responsavel_id": metadata.responsavel_id or "",
            "allowed_users": ",".join(metadata.allowed_users),
            "source_type": "sei"
        }
        
        if chunk:
            chunks = self._chunk_text(text, structure_aware=True)
        else:
            chunks = [text]
        
        ids = []
        embeddings = []
        documents = []
        metadatas = []
        
        for i, c in enumerate(chunks):
            doc_id = self._generate_id(c, meta_dict)
            ids.append(doc_id)
            embeddings.append(self.embedding_model.encode(c).tolist())
            documents.append(c)
            chunk_meta = {**meta_dict, "chunk_index": i}
            metadatas.append(chunk_meta)
        
        self.collections["sei"].add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        
        self._bm25_indices.pop("sei", None)
        
        logger.info(f"✅ Adicionados {len(chunks)} chunks SEI ({metadata.processo_sei})")
        return len(chunks)
    
    def add_peca_modelo(
        self,
        text: str,
        metadata: PecaModeloMetadata,
        chunk: bool = True
    ) -> int:
        """Adiciona modelo de peça ao índice"""
        meta_dict = {
            "tipo_peca": metadata.tipo_peca,
            "area": metadata.area,
            "rito": metadata.rito,
            "tribunal_destino": metadata.tribunal_destino or "",
            "tese": metadata.tese or "",
            "resultado": metadata.resultado or "",
            "data_criacao": metadata.data_criacao or datetime.now().isoformat(),
            "versao": metadata.versao,
            "aprovado": str(metadata.aprovado),
            "source_type": "pecas_modelo"
        }
        
        if chunk:
            chunks = self._chunk_text(text, chunk_size=800, structure_aware=True)
        else:
            chunks = [text]
        
        ids = []
        embeddings = []
        documents = []
        metadatas = []
        
        for i, c in enumerate(chunks):
            doc_id = self._generate_id(c, meta_dict)
            ids.append(doc_id)
            embeddings.append(self.embedding_model.encode(c).tolist())
            documents.append(c)
            chunk_meta = {**meta_dict, "chunk_index": i}
            metadatas.append(chunk_meta)
        
        self.collections["pecas_modelo"].add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        
        self._bm25_indices.pop("pecas_modelo", None)
        
        logger.info(f"✅ Adicionados {len(chunks)} chunks de modelo ({metadata.tipo_peca} - {metadata.area})")
        return len(chunks)
    
    # =========================================================================
    # RETRIEVAL
    # =========================================================================
    
    def _build_bm25_index(self, collection_name: str):
        """Constrói índice BM25 para uma coleção"""
        if collection_name in self._bm25_indices:
            return
        
        collection = self.collections[collection_name]
        if collection.count() == 0:
            return
        
        # Get all documents
        results = collection.get(include=["documents"])
        docs = results["documents"]
        
        # Tokenize (simples, pode melhorar com NLTK/spaCy)
        tokenized = [doc.lower().split() for doc in docs]
        
        self._bm25_indices[collection_name] = BM25Okapi(tokenized)
        self._bm25_docs[collection_name] = docs
        
        logger.info(f"🔍 Índice BM25 construído para '{collection_name}' ({len(docs)} docs)")
    
    def _bm25_search(
        self, 
        query: str, 
        collection_name: str, 
        top_k: int = 20
    ) -> List[tuple]:
        """Busca BM25 (lexical) em uma coleção"""
        self._build_bm25_index(collection_name)
        
        if collection_name not in self._bm25_indices:
            return []
        
        bm25 = self._bm25_indices[collection_name]
        docs = self._bm25_docs[collection_name]
        
        tokenized_query = query.lower().split()
        scores = bm25.get_scores(tokenized_query)
        
        # Get top_k indices
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        
        return [(docs[i], scores[i]) for i in top_indices if scores[i] > 0]
    
    def _semantic_search(
        self,
        query: str,
        collection_name: str,
        top_k: int = 20,
        where_filter: Optional[dict] = None
    ) -> List[dict]:
        """Busca semântica (embeddings) em uma coleção"""
        collection = self.collections[collection_name]
        
        if collection.count() == 0:
            return []
        
        query_embedding = self.embedding_model.encode(query).tolist()
        
        kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"]
        }
        
        if where_filter:
            kwargs["where"] = where_filter
        
        results = collection.query(**kwargs)
        
        # Format results
        formatted = []
        for i in range(len(results["documents"][0])):
            formatted.append({
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
                "score": 1 - results["distances"][0][i]  # Convert distance to similarity
            })
        
        return formatted
    
    def hybrid_search(
        self,
        query: str,
        sources: List[str] = None,
        top_k: int = 10,
        bm25_weight: float = 0.3,
        semantic_weight: float = 0.7,
        rrf_k: int = 60,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        tenant_id: str = "default",
        tipo_peca_filter: Optional[str] = None,  # v1.1: Filter pecas_modelo by type
        use_rerank: Optional[bool] = None,
        rerank_top_k: int = 20,
        rerank_max_chars: int = 1800,
        rerank_model: Optional[str] = None
    ) -> List[dict]:
        """
        Busca híbrida (BM25 + Semântica) com RRF (Reciprocal Rank Fusion).
        
        Args:
            query: Texto da busca
            sources: Lista de coleções a buscar (default: todas)
            top_k: Número de resultados finais
            bm25_weight: Peso do BM25 na fusão
            semantic_weight: Peso semântico na fusão
            filters: Filtros de metadados (ex: {"tribunal": "STJ"})
            user_id: ID do usuário para RBAC (SEI)
            tenant_id: Tenant para multi-tenancy (SEI)
            tipo_peca_filter: v1.1: Filtrar pecas_modelo por tipo (peticao_inicial, contestacao, etc.)
        
        Returns:
            Lista de resultados ordenados por relevância
        """
        sources = sources or self.COLLECTIONS
        if use_rerank is None:
            use_rerank = os.getenv("RAG_RERANK_ENABLED", "true").lower() == "true"
        
        all_results = []
        rrf_k = max(1, int(rrf_k))
        
        for source in sources:
            if source not in self.COLLECTIONS:
                logger.warning(f"⚠️ Coleção '{source}' não existe, ignorando...")
                continue
            
            # Build where filter for ChromaDB
            where_filter = None
            if filters:
                # Check if filters is a "routed" filter (keys are collection names)
                if source in filters and isinstance(filters[source], dict):
                    where_filter = filters[source].copy()
                # Or if it contains other collection keys, assume it's a routed filter structure
                # and this source doesn't have a specific filter (unless it's a global filter request)
                elif any(k in self.COLLECTIONS for k in filters.keys()):
                    # If the filter dict has keys like 'pecas_modelo', 'lei', etc.
                    # and the current source isn't one of them, we probably shouldn't apply the sibling filters.
                    # We only apply if there's a filter specifically for THIS source or generic keys.
                    # For safety in this "routed" mode, we start empty if no match.
                    where_filter = None
                else:
                     # Classic mode: apply all filters globally (e.g. tenant_id)
                    where_filter = filters.copy()
            
            # RBAC for SEI
            if source == "sei":
                sei_filter = {"tenant_id": tenant_id}
                if user_id:
                    # Only allow if user is in allowed_users or is responsavel
                    # ChromaDB has limited filter support, so we'll filter post-hoc
                    pass
                if where_filter:
                    where_filter.update(sei_filter)
                else:
                    where_filter = sei_filter
            
            # v1.1: Filter pecas_modelo by tipo_peca
            if source == "pecas_modelo" and tipo_peca_filter:
                peca_filter = {"tipo_peca": tipo_peca_filter}
                if where_filter:
                    where_filter.update(peca_filter)
                else:
                    where_filter = peca_filter
            
            # BM25 Search
            bm25_results = self._bm25_search(query, source, top_k=top_k * 2)
            
            # Semantic Search
            semantic_results = self._semantic_search(
                query, source, top_k=top_k * 2, where_filter=where_filter
            )
            
            # Create score dict for RRF
            doc_scores = {}
            
            # Rank-based scores (RRF)
            bm25_ranked = sorted(bm25_results, key=lambda x: x[1], reverse=True)
            semantic_ranked = sorted(semantic_results, key=lambda x: x["score"], reverse=True)

            bm25_rank_map = {}
            for rank, (doc, _) in enumerate(bm25_ranked, start=1):
                doc_id = hashlib.md5(doc.encode()).hexdigest()
                bm25_rank_map[doc_id] = (rank, doc)

            semantic_rank_map = {}
            for rank, result in enumerate(semantic_ranked, start=1):
                doc_id = hashlib.md5(result["text"].encode()).hexdigest()
                semantic_rank_map[doc_id] = (rank, result)
            
            all_doc_ids = set(bm25_rank_map.keys()) | set(semantic_rank_map.keys())

            def rrf_score(rank: int, k: int) -> float:
                return 1.0 / (k + rank)

            for doc_id in all_doc_ids:
                bm25_rank, bm25_doc = bm25_rank_map.get(doc_id, (None, None))
                semantic_rank, semantic_result = semantic_rank_map.get(doc_id, (None, None))

                bm25_rrf = rrf_score(bm25_rank, rrf_k) * bm25_weight if bm25_rank else 0.0
                semantic_rrf = rrf_score(semantic_rank, rrf_k) * semantic_weight if semantic_rank else 0.0
                text = semantic_result["text"] if semantic_result else bm25_doc
                metadata = semantic_result["metadata"] if semantic_result else {}

                doc_scores[doc_id] = {
                    "text": text,
                    "bm25_score": bm25_rrf,
                    "semantic_score": semantic_rrf,
                    "source": source,
                    "metadata": metadata
                }
            
            # Compute final score (RRF)
            for doc_id, data in doc_scores.items():
                data["final_score"] = data["bm25_score"] + data["semantic_score"]
                all_results.append(data)
        
        # Post-hoc RBAC filtering for SEI
        if user_id and "sei" in sources:
            filtered_results = []
            for r in all_results:
                if r["source"] == "sei":
                    allowed = r["metadata"].get("allowed_users", "")
                    responsavel = r["metadata"].get("responsavel_id", "")
                    sigilo = r["metadata"].get("sigilo", "publico")
                    
                    # Public documents are always allowed
                    if sigilo == "publico":
                        filtered_results.append(r)
                    # Restricted/sigiloso need explicit permission
                    elif user_id in allowed.split(",") or user_id == responsavel:
                        filtered_results.append(r)
                    # Skip if not authorized
                else:
                    filtered_results.append(r)
            all_results = filtered_results

        # Sort by final score and rerank (optional)
        all_results.sort(key=lambda x: x["final_score"], reverse=True)

        if use_rerank and all_results:
            reranker = self._get_reranker(rerank_model)
            if reranker:
                slice_size = min(rerank_top_k, len(all_results))
                rerank_inputs = []
                for item in all_results[:slice_size]:
                    text = item.get("text", "")
                    rerank_inputs.append([query, text[:rerank_max_chars]])
                try:
                    scores = reranker.predict(rerank_inputs)
                    for item, score in zip(all_results[:slice_size], scores):
                        item["rerank_score"] = float(score)
                    all_results[:slice_size] = sorted(
                        all_results[:slice_size],
                        key=lambda x: x.get("rerank_score", x["final_score"]),
                        reverse=True
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Rerank falhou, mantendo score original: {e}")
        
        return all_results[:top_k]
    
    def hyde_search(
        self,
        query: str,
        sources: List[str] = None,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        tenant_id: str = "default",
        tipo_peca_filter: Optional[str] = None,
        verbose: bool = False
    ) -> List[dict]:
        """
        Executa a etapa de recuperação do HyDE (Hypothetical Document Embeddings).
        
        Assume que 'query' já é um documento hipotético ou uma query enriquecida/expandida.
        Prioriza fortemente a busca semântica (Embeddings) sobre keywords exatas (BM25),
        pois o documento hipotético tende a alinhar vetorialmente com os reais.
        """
        if verbose:
            logger.info(f"🔮 HyDE Search: '{query[:50]}...'")
            
        return self.hybrid_search(
            query=query,
            sources=sources,
            top_k=top_k,
            bm25_weight=0.1,      # Peso residual para capturar termos técnicos
            semantic_weight=0.9,  # Foco principal na similaridade vetorial
            filters=filters,
            user_id=user_id,      # Importante para RBAC no SEI
            tenant_id=tenant_id,
            tipo_peca_filter=tipo_peca_filter
        )
    
    def search_for_section(
        self,
        section_title: str,
        case_facts: str,
        sources: List[str] = None,
        top_k: int = 8,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        tenant_id: str = "default"
    ) -> List[dict]:
        """
        Busca especializada para geração de seção de documento jurídico.
        
        Combina o título da seção com os fatos do caso para gerar query otimizada.
        """
        # Build optimized query
        query = f"{section_title}. Contexto: {case_facts[:500]}"
        
        return self.hybrid_search(
            query=query,
            sources=sources,
            top_k=top_k,
            filters=filters,
            user_id=user_id,
            tenant_id=tenant_id
        )
    
    def format_sources_for_prompt(self, results: List[dict], max_chars: int = 8000) -> str:
        """
        Formata resultados do RAG para injeção no prompt do LLM.
        """
        if not results:
            return ""
        
        output = "## Fontes Recuperadas (RAG)\n\n"
        total_chars = len(output)
        
        for i, r in enumerate(results):
            source_type = r.get("source", "?")
            metadata = r.get("metadata", {})
            text = r.get("text", "")
            score = r.get("final_score", 0)
            
            # Format metadata label
            if source_type == "lei":
                label = f"📜 {metadata.get('tipo', '')} {metadata.get('numero', '')}/{metadata.get('ano', '')} - {metadata.get('artigo', '')}"
            elif source_type == "juris":
                label = f"⚖️ {metadata.get('tribunal', '')} - {metadata.get('numero', '')} ({metadata.get('tema', '')})"
            elif source_type == "sei":
                label = f"📁 SEI {metadata.get('processo_sei', '')} - {metadata.get('tipo_documento', '')}"
            elif source_type == "pecas_modelo":
                label = f"📝 Modelo: {metadata.get('tipo_peca', '')} - {metadata.get('area', '')}"
                if metadata.get("source_type") == "clause_bank":
                    label += f" [Bloco: {metadata.get('tipo_bloco', '?')}/{metadata.get('subtipo', '?')}]"
            else:
                label = f"📄 {source_type}"
            
            entry = f"### [{i+1}] {label} (score: {score:.2f})\n{text[:1500]}...\n\n"
            
            if total_chars + len(entry) > max_chars:
                output += f"\n*... {len(results) - i} fontes adicionais omitidas (limite de caracteres)*\n"
                break
            
            output += entry
            total_chars += len(entry)
        
        return output
    
    # =========================================================================
    # UTILITY
    # =========================================================================
    
    def get_stats(self) -> dict:
        """Retorna estatísticas das coleções"""
        stats = {}
        for name, collection in self.collections.items():
            stats[name] = collection.count()
        return stats
    
    def clear_collection(self, collection_name: str):
        """Limpa uma coleção"""
        if collection_name in self.collections:
            self.client.delete_collection(collection_name)
            self.collections[collection_name] = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            self._bm25_indices.pop(collection_name, None)
            logger.info(f"🗑️ Coleção '{collection_name}' limpa")


# =============================================================================
# GRAPH RAG INTEGRATION (v5.1)
# =============================================================================

_knowledge_graph = None


def get_knowledge_graph():
    """
    Get or create the singleton Knowledge Graph instance.
    
    Returns LegalKnowledgeGraph or None if module unavailable.
    """
    global _knowledge_graph
    if _knowledge_graph is None:
        try:
            from app.services.rag_graph import LegalKnowledgeGraph
            _knowledge_graph = LegalKnowledgeGraph()
            logger.info(f"📊 GraphRAG: Loaded knowledge graph")
        except ImportError as e:
            logger.warning(f"⚠️ GraphRAG: Module not available: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ GraphRAG: Failed to load: {e}")
            return None
    return _knowledge_graph


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def create_rag_manager(persist_dir: str = None) -> RAGManager:
    """Factory function para criar RAGManager com configuração padrão"""
    persist_dir = persist_dir or os.path.join(os.path.dirname(__file__), "chroma_db")
    return RAGManager(persist_directory=persist_dir)


# =============================================================================
# CLI / TESTING
# =============================================================================

if __name__ == "__main__":
    print("🧪 Testando RAG Module...")
    
    # Initialize
    rag = RAGManager(persist_directory="./test_chroma_db")
    
    # Add sample legislation
    rag.add_legislacao(
        text="""Art. 37. A administração pública direta e indireta de qualquer dos Poderes da União, 
        dos Estados, do Distrito Federal e dos Municípios obedecerá aos princípios de legalidade, 
        impessoalidade, moralidade, publicidade e eficiência.""",
        metadata=LegislacaoMetadata(
            tipo="constituicao",
            numero="1988",
            ano=1988,
            jurisdicao="BR",
            artigo="art. 37, caput",
            vigencia="vigente"
        )
    )
    
    # Add sample jurisprudence
    rag.add_jurisprudencia(
        text="""EMENTA: RESPONSABILIDADE CIVIL DO ESTADO. OMISSÃO. A responsabilidade civil do Estado 
        por omissão é subjetiva, exigindo-se a prova da culpa, salvo quando a omissão criar risco 
        específico de dano.""",
        metadata=JurisprudenciaMetadata(
            tribunal="STF",
            orgao="Pleno",
            tipo_decisao="acordao",
            numero="RE 123.456",
            relator="Min. Fulano",
            assuntos=["responsabilidade civil", "omissão estatal"]
        )
    )
    
    # Test search
    print("\n🔍 Testando busca híbrida...")
    results = rag.hybrid_search(
        query="responsabilidade civil do estado por omissão",
        sources=["lei", "juris"],
        top_k=5
    )
    
    print(f"\n📊 Resultados encontrados: {len(results)}")
    for r in results:
        print(f"  - [{r['source']}] Score: {r['final_score']:.2f}")
        print(f"    {r['text'][:100]}...")
    
    # Print formatted for prompt
    print("\n📄 Formatado para prompt:")
    print(rag.format_sources_for_prompt(results))
    
    # Stats
    print(f"\n📈 Estatísticas: {rag.get_stats()}")
    
    print("\n✅ Teste concluído!")
