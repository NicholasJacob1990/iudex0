"""
RAG Local Module - Índice Efêmero para Processos (v2.0)

Este módulo permite criar índices temporários para análise de processos específicos.
Ideal para SEI, PJe, ePROC e outros sistemas processuais com múltiplos documentos.

Uso:
    from rag_local import LocalProcessIndex
    
    index = LocalProcessIndex(processo_id="SEI-12345/2024", ttl_hours=4)
    index.index_pasta("./autos_processo/")
    results = index.search("laudo pericial", top_k=5)
"""

import os
import re
import hashlib
import logging
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Iterable, Tuple
from dataclasses import dataclass, field

# Third-party imports
try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    try:
        from sentence_transformers import CrossEncoder
    except Exception:
        CrossEncoder = None
    from rank_bm25 import BM25Okapi
except ImportError as e:
    print(f"❌ RAG Local - Dependências faltando: {e}")
    raise

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

from colorama import Fore, Style, init
init(autoreset=True)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RAGLocal")

from app.core.config import settings

# =============================================================================
# METADATA SCHEMA
# =============================================================================

@dataclass
class ProcessDocMetadata:
    """Metadados para documentos dentro de um processo"""
    # Identificação do processo
    processo_id: str       # Número SEI ou CNJ
    sistema: str           # SEI, PJe, eproc, SAPIENS
    
    # Identificação do documento
    doc_id: str            # ID interno do documento
    tipo_doc: str          # peticao, despacho, laudo, ata, oficio
    data_doc: str          # Data do documento
    
    # Localização
    pagina: int = 0        # Página do PDF
    volume: int = 1        # Volume
    
    # Conteúdo
    resumo_auto: str = ""  # Resumo gerado
    
    # v2.1: Alinhados com SEIMetadata para permitir joins leves
    orgao: str = ""        # PGFN, AGU, etc.
    unidade: str = ""      # Unidade organizacional
    tenant_id: str = "default"  # Multi-tenancy
    origem: str = "local"  # "local" | "global" - diferencia RAG Local vs Global
    file_path: str = ""    # Caminho absoluto do arquivo original

# =============================================================================
# LOCAL PROCESS INDEX
# =============================================================================

class LocalProcessIndex:
    """
    Índice efêmero para documentos de um processo específico.
    
    Cria um índice temporário (in-memory) para navegar nos autos de um caso,
    encontrar documentos e gerar citações auditáveis.
    """
    
    # Configurações de embedding
    EMBEDDING_MODEL = settings.EMBEDDING_MODEL or "intfloat/multilingual-e5-large"
    CHUNK_SIZE = 1500
    CHUNK_OVERLAP = 200
    
    def __init__(
        self, 
        processo_id: str, 
        sistema: str = "SEI",
        ttl_hours: int = 4,
        tenant_id: str = "default"
    ):
        """
        Inicializa índice efêmero para um processo.
        
        Args:
            processo_id: Número do processo (SEI, CNJ, etc.)
            sistema: Sistema de origem (SEI, PJe, eproc)
            ttl_hours: Tempo de vida do índice (horas)
            tenant_id: Tenant ID para isolamento (RBAC)
        """
        self.processo_id = processo_id
        self.sistema = sistema
        self.tenant_id = tenant_id
        self.created_at = datetime.now()
        self.expiry = self.created_at + timedelta(hours=ttl_hours)
        
        # ChromaDB in-memory
        self.client = chromadb.Client()
        self.collection_name = f"proc_{re.sub(r'[^a-zA-Z0-9]', '_', processo_id)}"
        self.collection = self.client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        
        # Embedding model
        logger.info(f"🔄 Carregando modelo de embeddings...")
        self.embedding_model = SentenceTransformer(self.EMBEDDING_MODEL)
        
        # BM25 index (lazy)
        self._documents = []
        self._metadatas = []
        self._chunk_ids: List[str] = []
        self._doc_chunk_indices: Dict[str, List[int]] = {}
        self._bm25 = None

        # Optional reranker (lazy)
        self._reranker = None
        self._reranker_name = None

        # Optional ephemeral graph (lazy)
        self._graph = None
        self._graph_extractor = None
        self._graph_tmp_dir = None
        self._graph_enabled = False
        self._argument_enabled = False
        
        logger.info(f"📁 Índice criado para processo: {processo_id} ({sistema})")
        logger.info(f"   Expira em: {self.expiry.strftime('%Y-%m-%d %H:%M')}")
    
    def is_expired(self) -> bool:
        """Verifica se o índice expirou"""
        return datetime.now() > self.expiry
    
    def _chunk_text(self, text: str, page_start: int = 0) -> List[Dict]:
        """Divide texto em chunks com metadados de página estimada"""
        chunks = []
        words = text.split()
        
        # Estimar ~300 palavras por página
        words_per_page = 300
        
        for i in range(0, len(words), self.CHUNK_SIZE - self.CHUNK_OVERLAP):
            chunk_words = words[i:i + self.CHUNK_SIZE]
            chunk_text = " ".join(chunk_words)
            
            # Estimar página
            word_position = i
            estimated_page = page_start + (word_position // words_per_page)
            
            chunks.append({
                "text": chunk_text,
                "page": estimated_page,
                "word_start": i,
                "word_end": i + len(chunk_words)
            })
        
        return chunks
    
    def _read_pdf_with_pages(self, file_path: str) -> List[Dict]:
        """Lê PDF mantendo informação de página"""
        if not PdfReader:
            raise ImportError("PyPDF2 não instalado")
        
        reader = PdfReader(file_path)
        pages = []
        
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages.append({
                    "text": text,
                    "page": i + 1
                })
        
        return pages
    
    def _detect_doc_type(self, text: str, filename: str) -> str:
        """Detecta tipo de documento a partir do conteúdo e nome"""
        filename_upper = filename.upper()
        text_peek = text[:1000].upper()
        
        patterns = {
            "peticao_inicial": ["PETIÇÃO INICIAL", "EXCELENTÍSSIMO", "AUTOR:"],
            "contestacao": ["CONTESTAÇÃO", "CONTESTANDO", "RÉU:"],
            "recurso": ["APELAÇÃO", "RECURSO", "AGRAVO", "RECORRE"],
            "sentenca": ["SENTENÇA", "JULGO", "DISPOSITIVO"],
            "acordao": ["ACÓRDÃO", "ACORDAM", "VOTO"],
            "despacho": ["DESPACHO", "INTIME-SE", "CITE-SE", "JUNTE-SE"],
            "laudo": ["LAUDO", "PERÍCIA", "PERITO"],
            "ata": ["ATA DE AUDIÊNCIA", "AUDIÊNCIA"],
            "oficio": ["OFÍCIO", "COMUNICAMOS"],
            "parecer": ["PARECER", "OPINAMOS"],
            "decisao": ["DECISÃO", "DEFIRO", "INDEFIRO"],
        }
        
        for tipo, keywords in patterns.items():
            for kw in keywords:
                if kw in filename_upper or kw in text_peek:
                    return tipo
        
        return "documento"
    
    def _extract_doc_id(self, filename: str, text: str) -> str:
        """Extrai ID do documento (SEI, Evento, etc.)"""
        # Padrão SEI: "12345678"
        sei_match = re.search(r'(\d{7,10})', filename)
        if sei_match:
            return sei_match.group(1)
        
        # Padrão PJe/eproc: "Evento 15"
        evento_match = re.search(r'[Ee]vento\s*(\d+)', filename) or re.search(r'[Ee]vento\s*(\d+)', text[:500])
        if evento_match:
            return f"Evento {evento_match.group(1)}"
        
        # Fallback: nome do arquivo sem extensão
        return Path(filename).stem
    
    def _extract_date(self, text: str) -> str:
        """Extrai data do documento"""
        # Padrão brasileiro: dd/mm/yyyy ou dd-mm-yyyy
        date_match = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', text[:2000])
        if date_match:
            return f"{date_match.group(3)}-{date_match.group(2).zfill(2)}-{date_match.group(1).zfill(2)}"
        return datetime.now().strftime("%Y-%m-%d")
    
    def index_documento(
        self, 
        file_path: str, 
        doc_id: Optional[str] = None,
        tipo_doc: Optional[str] = None
    ) -> int:
        """
        Indexa um documento do processo.
        
        Args:
            file_path: Caminho para o arquivo (PDF, TXT, etc.)
            doc_id: ID do documento (auto-detectado se não fornecido)
            tipo_doc: Tipo do documento (auto-detectado se não fornecido)
            
        Returns:
            Número de chunks indexados
        """
        filename = Path(file_path).name
        ext = Path(file_path).suffix.lower()
        
        # Ler conteúdo
        if ext == '.pdf':
            pages = self._read_pdf_with_pages(file_path)
            full_text = "\n".join([p["text"] for p in pages])
        elif ext in ['.txt', '.md']:
            with open(file_path, 'r', encoding='utf-8') as f:
                full_text = f.read()
            pages = [{"text": full_text, "page": 1}]
        else:
            logger.warning(f"Extensão não suportada: {ext}")
            return 0
        
        if not full_text.strip() or len(full_text) < 50:
            logger.warning(f"Documento vazio ou muito curto: {filename}")
            return 0
        
        # Auto-detectar metadados
        doc_id = doc_id or self._extract_doc_id(filename, full_text)
        tipo_doc = tipo_doc or self._detect_doc_type(full_text, filename)
        data_doc = self._extract_date(full_text)
        
        # Indexar por página
        total_chunks = 0
        chunk_index = 0
        for page_data in pages:
            chunks = self._chunk_text(page_data["text"], page_start=page_data["page"])
            
            for chunk in chunks:
                # Criar ID único
                chunk_id = hashlib.md5(f"{self.processo_id}_{doc_id}_{chunk['page']}_{chunk['word_start']}".encode()).hexdigest()
                source_hash = hashlib.sha256(chunk["text"].encode("utf-8")).hexdigest()
                
                # Embedding
                embedding = self.embedding_model.encode(chunk["text"]).tolist()
                
                # Metadata
                metadata = {
                    "processo_id": self.processo_id,
                    "sistema": self.sistema,
                    "tenant_id": self.tenant_id,
                    "doc_id": doc_id,
                    "tipo_doc": tipo_doc,
                    "data_doc": data_doc,
                    "pagina": chunk["page"],
                    "chunk_index": chunk_index,
                    "chunk_id": chunk_id,
                    "source_hash": source_hash,
                    "filename": filename,
                    "file_path": str(file_path)
                }
                
                # Add to collection
                self.collection.add(
                    ids=[chunk_id],
                    embeddings=[embedding],
                    documents=[chunk["text"]],
                    metadatas=[metadata]
                )
                
                # Store for BM25
                global_idx = len(self._documents)
                self._documents.append(chunk["text"])
                self._metadatas.append(metadata)
                self._chunk_ids.append(chunk_id)
                self._doc_chunk_indices.setdefault(str(doc_id), []).append(global_idx)

                self._graph_ingest_chunk(chunk["text"], metadata)
                
                total_chunks += 1
                chunk_index += 1
        
        # Invalidate BM25 cache
        self._bm25 = None
        
        logger.info(f"   ✅ {filename}: {total_chunks} chunks ({tipo_doc})")
        return total_chunks

    def index_text(
        self,
        text: str,
        filename: str = "documento.txt",
        doc_id: Optional[str] = None,
        tipo_doc: Optional[str] = None,
        source_path: Optional[str] = None,
    ) -> int:
        """Indexa texto já extraído (ex.: OCR, DOCX, ZIP)."""
        full_text = (text or "").strip()
        if not full_text or len(full_text) < 50:
            logger.warning(f"Texto vazio ou muito curto: {filename}")
            return 0

        doc_id = doc_id or self._extract_doc_id(filename, full_text)
        tipo_doc = tipo_doc or self._detect_doc_type(full_text, filename)
        data_doc = self._extract_date(full_text)
        page_start = 1
        chunks = self._chunk_text(full_text, page_start=page_start)

        total_chunks = 0
        chunk_index = 0
        for chunk in chunks:
            chunk_id = hashlib.md5(
                f"{self.processo_id}_{doc_id}_{chunk['page']}_{chunk['word_start']}".encode()
            ).hexdigest()
            source_hash = hashlib.sha256(chunk["text"].encode("utf-8")).hexdigest()
            embedding = self.embedding_model.encode(chunk["text"]).tolist()
            metadata = {
                "processo_id": self.processo_id,
                "sistema": self.sistema,
                "tenant_id": self.tenant_id,
                "doc_id": doc_id,
                "tipo_doc": tipo_doc,
                "data_doc": data_doc,
                "pagina": chunk["page"],
                "chunk_index": chunk_index,
                "chunk_id": chunk_id,
                "source_hash": source_hash,
                "filename": filename,
                "file_path": source_path or filename,
            }
            self.collection.add(
                ids=[chunk_id],
                embeddings=[embedding],
                documents=[chunk["text"]],
                metadatas=[metadata],
            )
            global_idx = len(self._documents)
            self._documents.append(chunk["text"])
            self._metadatas.append(metadata)
            self._chunk_ids.append(chunk_id)
            self._doc_chunk_indices.setdefault(str(doc_id), []).append(global_idx)
            self._graph_ingest_chunk(chunk["text"], metadata)
            total_chunks += 1
            chunk_index += 1

        self._bm25 = None
        logger.info(f"   ✅ {filename}: {total_chunks} chunks ({tipo_doc}) [texto]")
        return total_chunks
    
    def index_pasta(self, pasta_path: str) -> int:
        """
        Indexa todos os documentos de uma pasta.
        
        Args:
            pasta_path: Caminho para a pasta com os autos
            
        Returns:
            Total de chunks indexados
        """
        pasta = Path(pasta_path)
        if not pasta.exists():
            raise FileNotFoundError(f"Pasta não encontrada: {pasta_path}")
        
        print(f"\n{Fore.CYAN}📁 Indexando processo: {self.processo_id}")
        print(f"   Pasta: {pasta_path}{Style.RESET_ALL}\n")
        
        # Encontrar arquivos
        extensions = ['.pdf', '.txt', '.md']
        files = []
        for ext in extensions:
            files.extend(pasta.glob(f"**/*{ext}"))
        
        files = sorted(files)
        print(f"   Arquivos encontrados: {len(files)}\n")
        
        total = 0
        for file_path in files:
            try:
                count = self.index_documento(str(file_path))
                total += count
            except Exception as e:
                logger.error(f"Erro ao indexar {file_path}: {e}")
        
        print(f"\n{Fore.GREEN}✅ Total indexado: {total} chunks{Style.RESET_ALL}")
        return total
    
    def _build_bm25(self):
        """Constrói índice BM25 (lazy)"""
        if self._bm25 is None and self._documents:
            tokenized = [doc.lower().split() for doc in self._documents]
            self._bm25 = BM25Okapi(tokenized)

    def _get_reranker(self, model_name: Optional[str] = None):
        if CrossEncoder is None:
            return None
        model_name = model_name or os.getenv("RAG_LOCAL_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
        if self._reranker is not None and self._reranker_name == model_name:
            return self._reranker
        try:
            self._reranker = CrossEncoder(model_name)
            self._reranker_name = model_name
            logger.info(f"🔁 [RAG Local] Reranker carregado: {model_name}")
            return self._reranker
        except Exception as exc:
            logger.warning(f"⚠️ [RAG Local] Falha ao carregar reranker ({model_name}): {exc}")
            self._reranker = None
            self._reranker_name = None
            return None

    def _ensure_graph(self, *, enabled: bool) -> None:
        if not enabled:
            return
        if self._graph is not None and self._graph_extractor is not None:
            return
        try:
            from app.services.rag_graph import LegalKnowledgeGraph, LegalEntityExtractor
        except Exception as exc:
            logger.warning(f"⚠️ [RAG Local] GraphRAG indisponível: {exc}")
            return
        try:
            if self._graph_tmp_dir is None:
                self._graph_tmp_dir = tempfile.mkdtemp(prefix="iudex_rag_local_graph_")
            persist_path = os.path.join(self._graph_tmp_dir, "graph.json")
            self._graph = LegalKnowledgeGraph(persist_path=persist_path)
            self._graph_extractor = LegalEntityExtractor(self._graph)
        except Exception as exc:
            logger.warning(f"⚠️ [RAG Local] Falha ao inicializar GraphRAG: {exc}")
            self._graph = None
            self._graph_extractor = None

    def enable_graph(self, *, graph_rag_enabled: bool, argument_graph_enabled: bool) -> None:
        self._graph_enabled = bool(graph_rag_enabled)
        self._argument_enabled = bool(argument_graph_enabled)
        self._ensure_graph(enabled=self._graph_enabled or self._argument_enabled)

    def _graph_ingest_chunk(self, text: str, metadata: Dict[str, Any]) -> None:
        if not (self._graph_enabled or self._argument_enabled):
            return
        if not self._graph_extractor or not self._graph:
            return
        try:
            self._graph_extractor.extract_from_text(text or "")
        except Exception:
            return
        try:
            from app.services.argument_pack import ARGUMENT_PACK
        except Exception:
            return
        if not self._argument_enabled:
            return
        try:
            ARGUMENT_PACK.ingest_chunk(self._graph, text=text or "", metadata=metadata or {})
        except Exception:
            return

    def _score_gate_local(
        self,
        results: List[Dict[str, Any]],
        *,
        min_best_semantic: float,
        min_avg_top3_semantic: float,
    ) -> bool:
        if not results:
            return False
        scores = [float(r.get("raw_semantic_sim") or 0.0) for r in results]
        best = max(scores) if scores else 0.0
        top3 = scores[:3]
        avg_top3 = sum(top3) / len(top3) if top3 else 0.0
        return best >= min_best_semantic and avg_top3 >= min_avg_top3_semantic

    def _compress_local_results(
        self,
        results: List[Dict[str, Any]],
        *,
        query: str,
        max_chars_per_chunk: int,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        if not results:
            return results, {"compressed": 0, "skipped": 0}
        tokens = [t.lower() for t in re.split(r"\W+", query or "") if len(t) >= 4]
        keywords = [t for t in tokens if t not in {"para", "com", "sem", "sobre", "entre", "contra", "qual", "como", "que", "uma", "uns", "umas", "dos", "das", "por", "onde", "quando", "porque", "pois", "em", "no", "na", "de", "do", "da", "e", "ou"}]
        sentence_split = re.compile(r"(?<=[\.\?!;])\s+")

        compressed_count = 0
        skipped = 0
        for item in results:
            text = (item.get("text") or "").strip()
            if not text:
                skipped += 1
                continue
            if len(text) <= max_chars_per_chunk:
                continue
            sentences = sentence_split.split(text)
            selected: List[str] = []
            for sentence in sentences:
                s = sentence.strip()
                if not s:
                    continue
                lower = s.lower()
                if any(k in lower for k in keywords):
                    selected.append(s)
                if sum(len(x) for x in selected) >= max_chars_per_chunk:
                    break
            if not selected:
                selected = sentences[:2]
            compressed = " ".join(selected).strip()[:max_chars_per_chunk]
            if compressed and compressed != text:
                item["full_text"] = text
                item["text"] = compressed
                compressed_count += 1
        return results, {"compressed": compressed_count, "skipped": skipped}

    def _expand_neighbors(
        self,
        results: List[Dict[str, Any]],
        *,
        window: int,
        max_extra: int,
    ) -> List[Dict[str, Any]]:
        if not results or window <= 0 or max_extra <= 0:
            return results
        extras: List[Dict[str, Any]] = []
        seen: set[str] = set()

        def _chunk_key(meta: Dict[str, Any]) -> str:
            return str(meta.get("chunk_id") or meta.get("source_hash") or "")

        for item in results:
            meta = item.get("metadata") or {}
            key = _chunk_key(meta)
            if key:
                seen.add(key)

        for item in results:
            meta = item.get("metadata") or {}
            doc_id = meta.get("doc_id")
            chunk_index = meta.get("chunk_index")
            if doc_id is None or chunk_index is None:
                continue
            try:
                chunk_index_int = int(chunk_index)
            except Exception:
                continue
            indices = self._doc_chunk_indices.get(str(doc_id)) or []
            if not indices:
                continue
            # Add +/- window neighbors
            for offset in range(-window, window + 1):
                if offset == 0:
                    continue
                target_idx = chunk_index_int + offset
                if target_idx < 0:
                    continue
                # find matching chunk in this doc
                for global_idx in indices:
                    md = self._metadatas[global_idx] if global_idx < len(self._metadatas) else {}
                    if not isinstance(md, dict):
                        continue
                    if md.get("chunk_index") != target_idx:
                        continue
                    neighbor_key = _chunk_key(md)
                    if neighbor_key and neighbor_key in seen:
                        break
                    neighbor = dict(item)
                    neighbor_meta = dict(md)
                    neighbor_meta["neighbor_of"] = meta.get("chunk_id") or meta.get("source_hash") or ""
                    neighbor["metadata"] = neighbor_meta
                    neighbor["text"] = self._documents[global_idx]
                    neighbor["final_score"] = float(neighbor.get("final_score") or 0.0) - 0.001
                    neighbor["citacao"] = self.format_citation({"metadata": neighbor_meta})
                    if neighbor_key:
                        seen.add(neighbor_key)
                    extras.append(neighbor)
                    break
                if len(extras) >= max_extra:
                    break
            if len(extras) >= max_extra:
                break
        return results + extras if extras else results

    def _rrf_merge(
        self,
        *,
        query: str,
        semantic_results: Dict[str, Dict[str, Any]],
        bm25_results: Dict[str, Dict[str, Any]],
        top_k: int,
        rrf_k: int,
        bm25_weight: float,
        semantic_weight: float,
    ) -> List[Dict[str, Any]]:
        all_ids = set(semantic_results.keys()) | set(bm25_results.keys())

        def rrf_score(rank: int, k: int) -> float:
            return 1.0 / (k + rank)

        merged: List[Dict[str, Any]] = []
        for cid in all_ids:
            sem = semantic_results.get(cid) or {}
            bm = bm25_results.get(cid) or {}
            sem_rank = sem.get("rank")
            bm_rank = bm.get("rank")
            sem_rrf = rrf_score(int(sem_rank), rrf_k) * semantic_weight if sem_rank else 0.0
            bm_rrf = rrf_score(int(bm_rank), rrf_k) * bm25_weight if bm_rank else 0.0
            text = sem.get("text") or bm.get("text") or ""
            metadata = sem.get("metadata") or bm.get("metadata") or {}
            merged.append(
                {
                    "text": text,
                    "metadata": metadata,
                    "semantic_score": sem_rrf,
                    "bm25_score": bm_rrf,
                    "final_score": sem_rrf + bm_rrf,
                    "raw_semantic_sim": sem.get("raw_semantic_sim"),
                    "raw_bm25": bm.get("raw_bm25"),
                }
            )
        merged.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
        for r in merged:
            r["citacao"] = self.format_citation(r)
        return merged[:top_k]

    def _single_search(
        self,
        query: str,
        *,
        top_k: int,
        tipo_doc: Optional[str],
        bm25_weight: float,
        semantic_weight: float,
        rrf_k: int,
    ) -> List[Dict[str, Any]]:
        if self.is_expired():
            logger.warning("⚠️ Índice expirado!")

        query_embedding = self.embedding_model.encode(query).tolist()
        where_filter: Optional[dict] = {}
        if tipo_doc:
            where_filter["tipo_doc"] = tipo_doc
        if self.tenant_id and self.tenant_id != "default":
            where_filter["tenant_id"] = self.tenant_id
        if not where_filter:
            where_filter = None

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=max(2, int(top_k) * 2),
            where=where_filter,
            include=["documents", "metadatas", "distances", "ids"],
        )

        semantic_rank_map: Dict[str, Dict[str, Any]] = {}
        docs = (results.get("documents") or [[]])[0] or []
        metas = (results.get("metadatas") or [[]])[0] or []
        dists = (results.get("distances") or [[]])[0] or []
        ids = (results.get("ids") or [[]])[0] or []
        for rank, (doc, meta, dist, cid) in enumerate(zip(docs, metas, dists, ids), start=1):
            semantic_rank_map[str(cid)] = {
                "rank": rank,
                "text": doc,
                "metadata": meta if isinstance(meta, dict) else {},
                "raw_semantic_sim": float(1.0 - float(dist)),
            }

        self._build_bm25()
        bm25_rank_map: Dict[str, Dict[str, Any]] = {}
        if self._bm25 and self._documents:
            scores = self._bm25.get_scores(query.lower().split())
            scored_docs = [(i, float(score)) for i, score in enumerate(scores)]
            scored_docs.sort(key=lambda x: x[1], reverse=True)
            for rank, (idx, score) in enumerate(scored_docs[: max(2, int(top_k) * 2)], start=1):
                if idx >= len(self._documents) or idx >= len(self._chunk_ids):
                    continue
                cid = self._chunk_ids[idx]
                bm25_rank_map[str(cid)] = {
                    "rank": rank,
                    "text": self._documents[idx],
                    "metadata": self._metadatas[idx] if isinstance(self._metadatas[idx], dict) else {},
                    "raw_bm25": score,
                }

        return self._rrf_merge(
            query=query,
            semantic_results=semantic_rank_map,
            bm25_results=bm25_rank_map,
            top_k=top_k,
            rrf_k=max(1, int(rrf_k)),
            bm25_weight=float(bm25_weight),
            semantic_weight=float(semantic_weight),
        )

    def multi_query_search(
        self,
        queries: List[str],
        *,
        top_k: int,
        per_query_top_k: Optional[int] = None,
        tipo_doc: Optional[str] = None,
        rrf_k: int = 60,
        bm25_weight: float = 0.3,
        semantic_weight: float = 0.7,
    ) -> List[Dict[str, Any]]:
        if not queries:
            return []
        per_query_top_k = int(per_query_top_k or max(top_k, 8))
        rrf_k = max(1, int(rrf_k))
        per_query_results: List[List[Dict[str, Any]]] = []
        for q in queries:
            try:
                per_query_results.append(
                    self._single_search(
                        q,
                        top_k=per_query_top_k,
                        tipo_doc=tipo_doc,
                        bm25_weight=bm25_weight,
                        semantic_weight=semantic_weight,
                        rrf_k=rrf_k,
                    )
                )
            except Exception as exc:
                logger.warning(f"⚠️ [RAG Local] Multi-query falhou para '{q[:80]}': {exc}")
                per_query_results.append([])

        def rrf_score(rank: int, k: int) -> float:
            return 1.0 / (k + rank)

        merged: Dict[str, Dict[str, Any]] = {}
        rank_scores: Dict[str, float] = {}
        for result_list in per_query_results:
            for rank, item in enumerate(result_list, start=1):
                meta = item.get("metadata") or {}
                cid = str(meta.get("chunk_id") or meta.get("source_hash") or hashlib.md5((item.get("text") or "").encode("utf-8")).hexdigest())
                rank_scores[cid] = rank_scores.get(cid, 0.0) + rrf_score(rank, rrf_k)
                if cid not in merged:
                    merged[cid] = dict(item)
                else:
                    if float(item.get("final_score") or 0.0) > float(merged[cid].get("final_score") or 0.0):
                        merged[cid] = dict(item)

        all_results: List[Dict[str, Any]] = []
        for cid, item in merged.items():
            item["multi_score"] = rank_scores.get(cid, 0.0)
            item["final_score"] = item["multi_score"]
            all_results.append(item)
        all_results.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
        for r in all_results:
            r["citacao"] = self.format_citation(r)
        return all_results[:top_k]

    def search_advanced(
        self,
        query: str,
        *,
        top_k: int = 5,
        tipo_doc: Optional[str] = None,
        bm25_weight: float = 0.3,
        semantic_weight: float = 0.7,
        rrf_k: int = 60,
        multi_query: bool = False,
        queries: Optional[List[str]] = None,
        multi_query_max: int = 3,
        compression_enabled: bool = False,
        compression_max_chars: int = 900,
        neighbor_expand: bool = False,
        neighbor_window: int = 1,
        neighbor_max_extra: int = 12,
        corrective_rag: bool = False,
        corrective_min_best_semantic: float = 0.25,
        corrective_min_avg_semantic: float = 0.20,
        rerank: Optional[bool] = None,
        rerank_top_k: int = 20,
        rerank_max_chars: int = 1800,
        rerank_model: Optional[str] = None,
        graph_rag_enabled: bool = False,
        graph_hops: int = 2,
        argument_graph_enabled: bool = False,
    ) -> Tuple[List[Dict[str, Any]], str]:
        top_k = max(1, int(top_k))
        base_query = (query or "").strip()
        if not base_query:
            return [], ""

        results: List[Dict[str, Any]] = []
        used_queries: List[str] = []
        if queries:
            used_queries = [str(q).strip() for q in queries if str(q).strip()]
        elif multi_query and multi_query_max > 1:
            # Heurística simples: query original + sem '?'
            used_queries = [base_query]
            alt = base_query.replace("?", "").strip()
            if alt and alt.lower() != base_query.lower():
                used_queries.append(alt)
            used_queries = used_queries[: max(1, int(multi_query_max))]

        if used_queries and len(used_queries) > 1:
            results = self.multi_query_search(
                used_queries,
                top_k=top_k,
                tipo_doc=tipo_doc,
                rrf_k=rrf_k,
                bm25_weight=bm25_weight,
                semantic_weight=semantic_weight,
            )
        else:
            results = self._single_search(
                base_query,
                top_k=top_k,
                tipo_doc=tipo_doc,
                bm25_weight=bm25_weight,
                semantic_weight=semantic_weight,
                rrf_k=rrf_k,
            )

        low_evidence = False
        if corrective_rag:
            low_evidence = not self._score_gate_local(
                results,
                min_best_semantic=corrective_min_best_semantic,
                min_avg_top3_semantic=corrective_min_avg_semantic,
            )
            if low_evidence:
                # Retry: increase top_k and boost BM25 a bit
                retry_top_k = min(max(top_k * 2, 8), 40)
                results = self._single_search(
                    base_query,
                    top_k=retry_top_k,
                    tipo_doc=tipo_doc,
                    bm25_weight=min(0.6, bm25_weight + 0.2),
                    semantic_weight=max(0.2, semantic_weight - 0.2),
                    rrf_k=rrf_k,
                )

        if neighbor_expand and results:
            results = self._expand_neighbors(
                results,
                window=int(neighbor_window or 1),
                max_extra=int(neighbor_max_extra or 12),
            )

        if compression_enabled and results:
            results, _ = self._compress_local_results(
                results,
                query=base_query,
                max_chars_per_chunk=max(120, int(compression_max_chars or 900)),
            )

        if rerank is None:
            rerank = os.getenv("RAG_LOCAL_RERANK_ENABLED", "false").lower() in ("1", "true", "yes", "on")
        if rerank and results:
            reranker = self._get_reranker(rerank_model)
            if reranker:
                slice_size = min(int(rerank_top_k or 20), len(results))
                rerank_inputs = [[base_query, (r.get("text") or "")[: int(rerank_max_chars or 1800)]] for r in results[:slice_size]]
                try:
                    scores = reranker.predict(rerank_inputs)
                    for item, score in zip(results[:slice_size], scores):
                        item["rerank_score"] = float(score)
                    results[:slice_size] = sorted(
                        results[:slice_size],
                        key=lambda x: x.get("rerank_score", x.get("final_score", 0.0)),
                        reverse=True,
                    )
                except Exception as exc:
                    logger.warning(f"⚠️ [RAG Local] Rerank falhou: {exc}")

        graph_context = ""
        if graph_rag_enabled:
            self._ensure_graph(enabled=True)
            if self._graph:
                try:
                    ctx, _ = self._graph.query_context_from_text(base_query, hops=max(1, min(int(graph_hops or 2), 5)))
                    graph_context = ctx or ""
                except Exception:
                    graph_context = ""
                if results and not graph_context:
                    try:
                        graph_context = self._graph.enrich_context(results, hops=max(1, min(int(graph_hops or 2), 5))) or ""
                    except Exception:
                        graph_context = ""
                if argument_graph_enabled and self._graph:
                    try:
                        from app.services.argument_pack import ARGUMENT_PACK
                        arg_ctx = ARGUMENT_PACK.build_debate_context_from_query(
                            self._graph,
                            base_query,
                            hops=max(1, min(int(graph_hops or 2), 5)),
                        )
                        if arg_ctx:
                            graph_context = f"{graph_context}\n\n{arg_ctx}".strip()
                    except Exception:
                        pass
        return results[:top_k], graph_context
    
    def search(
        self, 
        query: str, 
        top_k: int = 5,
        tipo_doc: Optional[str] = None
    ) -> List[Dict]:
        """
        Busca híbrida (semântica + BM25) nos autos do processo.
        
        Args:
            query: Termo de busca
            top_k: Número de resultados
            tipo_doc: Filtrar por tipo de documento
            
        Returns:
            Lista de resultados com texto, metadata e citação
        """
        results = self._single_search(
            query,
            top_k=int(top_k),
            tipo_doc=tipo_doc,
            bm25_weight=0.3,
            semantic_weight=0.7,
            rrf_k=60,
        )
        return results[:top_k]
    
    def format_citation(self, result: Dict) -> str:
        """
        Formata citação auditável para o resultado.
        
        Args:
            result: Resultado da busca
            
        Returns:
            String de citação Ex: "[LAUDO - Doc. 12345, p. 3]"
        """
        meta = result.get("metadata", {})
        tipo = meta.get("tipo_doc", "DOC").upper()
        doc_id = meta.get("doc_id", "?")
        pagina = meta.get("pagina", "?")
        
        if self.sistema == "SEI":
            return f"[{tipo} - Doc. SEI nº {doc_id}, p. {pagina}]"
        elif self.sistema in ["PJe", "eproc"]:
            return f"[{tipo} - {doc_id}, p. {pagina}]"
        else:
            return f"[{tipo} - {doc_id}, p. {pagina}]"
    
    def get_stats(self) -> Dict:
        """Retorna estatísticas do índice"""
        return {
            "processo_id": self.processo_id,
            "sistema": self.sistema,
            "total_chunks": self.collection.count(),
            "total_documents": len(set(m.get("doc_id", "") for m in self._metadatas)),
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expiry.isoformat(),
            "is_expired": self.is_expired()
        }
    
    def cronologia(self) -> List[Dict]:
        """
        Gera cronologia dos documentos do processo.
        
        Returns:
            Lista de documentos ordenados por data
        """
        # Agrupar por doc_id
        docs = {}
        for meta in self._metadatas:
            doc_id = meta.get("doc_id", "")
            if doc_id not in docs:
                docs[doc_id] = {
                    "doc_id": doc_id,
                    "tipo_doc": meta.get("tipo_doc", ""),
                    "data_doc": meta.get("data_doc", ""),
                    "filename": meta.get("filename", ""),
                    "paginas": set()
                }
            docs[doc_id]["paginas"].add(meta.get("pagina", 0))
        
        # Converter e ordenar
        cronologia = []
        for doc in docs.values():
            doc["paginas"] = sorted(doc["paginas"])
            doc["total_paginas"] = len(doc["paginas"])
            cronologia.append(doc)
        
        cronologia.sort(key=lambda x: x.get("data_doc", ""))
        return cronologia
    
    def cleanup(self):
        """Libera recursos do índice"""
        try:
            self.client.delete_collection(self.collection_name)
            logger.info(f"🗑️ Índice {self.processo_id} removido.")
        except Exception as e:
            logger.warning(f"Erro ao limpar índice: {e}")


# =============================================================================
# CLI PARA TESTES
# =============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="RAG Local - Índice de Processos")
    parser.add_argument("--processo", required=True, help="Número do processo")
    parser.add_argument("--pasta", required=True, help="Pasta com os autos")
    parser.add_argument("--sistema", default="SEI", choices=["SEI", "PJe", "eproc", "SAPIENS"])
    parser.add_argument("--busca", help="Termo para buscar (teste)")
    
    args = parser.parse_args()
    
    # Criar índice
    index = LocalProcessIndex(
        processo_id=args.processo,
        sistema=args.sistema
    )
    
    # Indexar pasta
    index.index_pasta(args.pasta)
    
    # Mostrar cronologia
    print(f"\n{Fore.CYAN}📋 Cronologia do Processo:{Style.RESET_ALL}")
    for doc in index.cronologia():
        print(f"   {doc['data_doc']} | {doc['tipo_doc'].upper():15} | {doc['doc_id']}")
    
    # Buscar (se solicitado)
    if args.busca:
        print(f"\n{Fore.CYAN}🔍 Buscando: '{args.busca}'{Style.RESET_ALL}")
        results = index.search(args.busca, top_k=3)
        for r in results:
            print(f"\n   {r['citacao']} (score: {r['final_score']:.2f})")
            print(f"   \"{r['text'][:200]}...\"")
    
    # Stats
    print(f"\n{Fore.GREEN}📊 Estatísticas:{Style.RESET_ALL}")
    stats = index.get_stats()
    for k, v in stats.items():
        print(f"   {k}: {v}")


if __name__ == "__main__":
    main()
