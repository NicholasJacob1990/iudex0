"""
Query Expansion Module: HyDE and Multi-Query RAG

This module provides advanced query expansion techniques for legal RAG:
- HyDE (Hypothetical Document Embeddings): Generate hypothetical answers for better semantic search
- Multi-Query: Generate query variants and merge results using RRF
- RRF (Reciprocal Rank Fusion): Merge and rank results from multiple sources

Optimized for Brazilian legal domain with Gemini as the default LLM.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import google.generativeai as genai

from app.services.rag.config import get_rag_config

# Import BudgetTracker (optional - graceful degradation if not available)
try:
    from app.services.rag.core.budget_tracker import BudgetTracker, estimate_tokens
except ImportError:
    BudgetTracker = None  # type: ignore
    estimate_tokens = None  # type: ignore

logger = logging.getLogger("rag.query_expansion")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class QueryExpansionConfig:
    """Configuration for query expansion features."""

    # HyDE settings
    hyde_enabled: bool = True
    hyde_model: str = "gemini-2.0-flash"
    hyde_max_tokens: int = 300
    hyde_temperature: float = 0.3
    hyde_semantic_weight: float = 0.7  # Higher weight on semantic for HyDE
    hyde_lexical_weight: float = 0.3

    # Multi-Query settings
    multi_query_enabled: bool = True
    multi_query_model: str = "gemini-2.0-flash"
    multi_query_count: int = 4  # Original + 3 variants
    multi_query_max_tokens: int = 300
    multi_query_temperature: float = 0.5

    # Cache settings
    cache_ttl_seconds: int = 3600  # 1 hour
    cache_max_items: int = 5000

    # RRF settings
    rrf_k: int = 60

    @classmethod
    def from_rag_config(cls) -> "QueryExpansionConfig":
        """Load configuration from RAGConfig."""
        cfg = get_rag_config()
        return cls(
            hyde_enabled=cfg.enable_hyde,
            hyde_model=cfg.hyde_model,
            hyde_max_tokens=cfg.hyde_max_tokens,
            hyde_semantic_weight=cfg.vector_weight,
            hyde_lexical_weight=cfg.lexical_weight,
            multi_query_enabled=cfg.enable_multiquery,
            multi_query_model=cfg.multiquery_model,
            multi_query_count=cfg.multiquery_max + 1,  # +1 for original query
            rrf_k=cfg.rrf_k,
            cache_ttl_seconds=cfg.embedding_cache_ttl_seconds,
        )


# ---------------------------------------------------------------------------
# Legal Domain Prompts (Portuguese)
# ---------------------------------------------------------------------------

HYDE_LEGAL_PROMPT = """Voce e um especialista juridico brasileiro. Dada a pergunta abaixo, escreva um documento hipotetico que responderia perfeitamente a essa pergunta.

O documento deve:
- Ser escrito em portugues juridico formal
- Conter terminologia juridica precisa (artigos de lei, jurisprudencia, doutrina)
- Ter entre 6-10 sentencas
- Ser factual e objetivo
- Nao usar listas ou citacoes formais
- Parecer um trecho de uma peca juridica, parecer ou acordao

Pergunta: {query}

Documento hipotetico:"""


HYDE_LEGAL_PROMPT_EXTENDED = """Voce e um especialista juridico brasileiro com ampla experiencia em direito constitucional, civil, penal, trabalhista, tributario e administrativo.

Dada a consulta juridica abaixo, redija um documento hipotetico que seria encontrado em uma base de dados juridica e que responderia de forma completa e precisa a essa consulta.

O documento deve:
1. Usar linguagem tecnico-juridica formal brasileira
2. Mencionar dispositivos legais relevantes (artigos, paragrafos, incisos)
3. Fazer referencia a jurisprudencia quando aplicavel (STF, STJ, TST, TRFs)
4. Citar doutrina ou principios juridicos pertinentes
5. Ter entre 150-250 palavras
6. Parecer um trecho autentico de:
   - Acordao ou decisao judicial
   - Parecer juridico
   - Peca processual
   - Doutrina especializada

Consulta: {query}

Documento hipotetico:"""


MULTI_QUERY_LEGAL_PROMPT = """Voce e um especialista em recuperacao de informacao juridica no contexto brasileiro.

Dada a pergunta original abaixo, gere {count} variantes de busca que capturem diferentes aspectos, sinonimos e reformulacoes da mesma consulta juridica.

Diretrizes:
- Cada variante deve ser uma reformulacao semanticamente equivalente ou uma expansao da pergunta
- Use sinonimos juridicos e termos tecnicos alternativos quando apropriado
- Inclua variantes com diferentes niveis de especificidade (geral e especifico)
- Considere tanto a terminologia tecnica quanto a linguagem coloquial juridica
- Cada variante em uma linha separada, sem numeracao ou marcadores
- Mantenha o contexto do direito brasileiro

Pergunta original: {query}

Variantes de busca:"""


QUERY_REWRITE_LEGAL_PROMPT = """Reescreva a pergunta abaixo como uma consulta de busca otimizada para um sistema RAG juridico brasileiro.

Diretrizes:
- Mantenha os termos juridicos essenciais
- Remova palavras vazias e conectivos desnecessarios
- Expanda siglas juridicas importantes (STF, STJ, CPC, CLT, etc.)
- Adicione termos tecnicos sinonimos entre parenteses se relevante
- Mantenha conciso (maximo 50 palavras)
- Resultado em uma unica linha

Pergunta: {query}

Consulta otimizada:"""


# ---------------------------------------------------------------------------
# TTL Cache Implementation
# ---------------------------------------------------------------------------

class TTLCache:
    """
    Thread-safe TTL cache for query expansion results.

    Features:
    - Automatic expiration based on TTL
    - LRU-style eviction when max capacity reached
    - Thread-safe operations
    """

    def __init__(self, max_items: int = 5000, default_ttl: int = 3600):
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.RLock()
        self._max_items = max_items
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    def _make_key(self, prefix: str, text: str) -> str:
        """Create a unique cache key using SHA256 hash."""
        h = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:32]
        return f"{prefix}:{h}"

    def get(self, prefix: str, text: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        key = self._make_key(prefix, text)
        now = time.time()

        with self._lock:
            item = self._cache.get(key)
            if item and item[0] > now:
                self._hits += 1
                return item[1]
            elif item:
                # Expired, remove it
                self._cache.pop(key, None)
            self._misses += 1
        return None

    def set(self, prefix: str, text: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with TTL."""
        key = self._make_key(prefix, text)
        ttl = ttl or self._default_ttl
        now = time.time()

        with self._lock:
            # Evict expired/excess items if needed
            if len(self._cache) >= self._max_items:
                self._evict(now)

            self._cache[key] = (now + ttl, value)

    def _evict(self, now: float) -> None:
        """Evict expired and oldest items."""
        # First, remove all expired entries (up to 1000 at a time for performance)
        expired = [k for k, (exp, _) in self._cache.items() if exp <= now]
        for k in expired[:1000]:
            self._cache.pop(k, None)

        # If still at capacity, remove oldest 20%
        if len(self._cache) >= self._max_items:
            sorted_items = sorted(self._cache.items(), key=lambda x: x[1][0])
            to_remove = len(sorted_items) // 5 or 1
            for k, _ in sorted_items[:to_remove]:
                self._cache.pop(k, None)

    def clear(self) -> None:
        """Clear entire cache."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            now = time.time()
            total = len(self._cache)
            expired = sum(1 for _, (exp, _) in self._cache.items() if exp <= now)
            hit_rate = self._hits / (self._hits + self._misses) if (self._hits + self._misses) > 0 else 0.0
            return {
                "total_entries": total,
                "expired_entries": expired,
                "active_entries": total - expired,
                "max_entries": self._max_items,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
            }


# ---------------------------------------------------------------------------
# RRF (Reciprocal Rank Fusion) Implementation
# ---------------------------------------------------------------------------

def rrf_score(rank: int, k: int = 60) -> float:
    """
    Calculate RRF (Reciprocal Rank Fusion) score for a given rank.

    Formula: 1 / (k + rank)

    Args:
        rank: Position in the result list (1-indexed)
        k: Constant to prevent high scores for top ranks (default 60)

    Returns:
        RRF score as float
    """
    return 1.0 / (k + rank)


def merge_results_rrf(
    result_lists: List[List[Dict[str, Any]]],
    top_k: int = 10,
    k_rrf: int = 60,
    id_field: str = "chunk_uid",
) -> List[Dict[str, Any]]:
    """
    Merge multiple result lists using Reciprocal Rank Fusion.

    Deduplicates results by chunk_uid and combines scores from all lists.

    Args:
        result_lists: List of result lists from different queries/sources
        top_k: Number of results to return
        k_rrf: RRF constant (higher = smoother score distribution)
        id_field: Field to use for deduplication

    Returns:
        Merged and ranked results with final_score and sources
    """
    if not result_lists:
        return []

    # Single list case - no fusion needed
    if len(result_lists) == 1:
        results = result_lists[0][:top_k]
        for item in results:
            item["final_score"] = item.get("score", 0.0)
            item["sources"] = ["query_0"]
        return results

    # Score accumulator by chunk_uid
    scores: Dict[str, float] = {}
    chunks: Dict[str, Dict[str, Any]] = {}
    sources_set: Dict[str, set] = {}

    for list_idx, results in enumerate(result_lists):
        for rank, item in enumerate(results, start=1):
            uid = item.get(id_field)
            if not uid:
                # Fallback: create ID from text hash
                text = item.get("text", "")
                if text:
                    uid = hashlib.md5(text.encode()).hexdigest()[:16]
                else:
                    continue

            # Accumulate RRF score
            score = rrf_score(rank, k_rrf)
            scores[uid] = scores.get(uid, 0.0) + score

            # Store chunk data (first occurrence wins)
            if uid not in chunks:
                chunks[uid] = {
                    id_field: uid,
                    "text": item.get("text", ""),
                    "metadata": item.get("metadata", {}),
                    "original_score": item.get("score", 0.0),
                }

            # Track which sources contributed
            if uid not in sources_set:
                sources_set[uid] = set()
            sources_set[uid].add(f"query_{list_idx}")
            if item.get("engine"):
                sources_set[uid].add(item["engine"])

    # Build final results
    merged = []
    for uid, chunk in chunks.items():
        merged.append({
            **chunk,
            "final_score": scores[uid],
            "sources": sorted(sources_set.get(uid, set())),
            "fusion_count": len(sources_set.get(uid, set())),
        })

    # Sort by score descending
    merged.sort(key=lambda x: x["final_score"], reverse=True)
    return merged[:top_k]


def merge_lexical_vector_rrf(
    lexical: List[Dict[str, Any]],
    vector: List[Dict[str, Any]],
    top_k: int = 10,
    k_rrf: int = 60,
    w_lex: float = 0.5,
    w_vec: float = 0.5,
    id_field: str = "chunk_uid",
) -> List[Dict[str, Any]]:
    """
    Merge lexical and vector search results with weighted RRF.

    This is the core hybrid search fusion function. Weights allow
    adjusting the balance between lexical (BM25) and vector (semantic)
    results.

    Args:
        lexical: Results from lexical/BM25 search
        vector: Results from vector/semantic search
        top_k: Number of results to return
        k_rrf: RRF constant
        w_lex: Weight for lexical results (default 0.5)
        w_vec: Weight for vector results (default 0.5)
        id_field: Field to use for deduplication

    Returns:
        Merged results with hybrid scoring
    """
    if not lexical and not vector:
        return []
    if not lexical:
        for item in vector[:top_k]:
            item["final_score"] = item.get("score", 0.0)
            item["sources"] = ["vector"]
        return vector[:top_k]
    if not vector:
        for item in lexical[:top_k]:
            item["final_score"] = item.get("score", 0.0)
            item["sources"] = ["lexical"]
        return lexical[:top_k]

    scores: Dict[str, float] = {}
    chunks: Dict[str, Dict[str, Any]] = {}
    sources_set: Dict[str, set] = {}
    original_scores: Dict[str, Dict[str, float]] = {}

    # Process lexical results
    for rank, item in enumerate(lexical, start=1):
        uid = item.get(id_field)
        if not uid:
            text = item.get("text", "")
            uid = hashlib.md5(text.encode()).hexdigest()[:16] if text else None
        if not uid:
            continue

        weighted_score = w_lex * rrf_score(rank, k_rrf)
        scores[uid] = scores.get(uid, 0.0) + weighted_score

        if uid not in chunks:
            chunks[uid] = {
                id_field: uid,
                "text": item.get("text", ""),
                "metadata": item.get("metadata", {}),
            }
        if uid not in sources_set:
            sources_set[uid] = set()
        sources_set[uid].add("lexical")

        if uid not in original_scores:
            original_scores[uid] = {}
        original_scores[uid]["lexical"] = item.get("score", 0.0)

    # Process vector results
    for rank, item in enumerate(vector, start=1):
        uid = item.get(id_field)
        if not uid:
            text = item.get("text", "")
            uid = hashlib.md5(text.encode()).hexdigest()[:16] if text else None
        if not uid:
            continue

        weighted_score = w_vec * rrf_score(rank, k_rrf)
        scores[uid] = scores.get(uid, 0.0) + weighted_score

        if uid not in chunks:
            chunks[uid] = {
                id_field: uid,
                "text": item.get("text", ""),
                "metadata": item.get("metadata", {}),
            }
        if uid not in sources_set:
            sources_set[uid] = set()
        sources_set[uid].add("vector")

        if uid not in original_scores:
            original_scores[uid] = {}
        original_scores[uid]["vector"] = item.get("score", 0.0)

    # Build final results
    merged = []
    for uid, chunk in chunks.items():
        merged.append({
            **chunk,
            "final_score": scores[uid],
            "sources": sorted(sources_set.get(uid, set())),
            "original_scores": original_scores.get(uid, {}),
            "is_hybrid": len(sources_set.get(uid, set())) > 1,
        })

    merged.sort(key=lambda x: x["final_score"], reverse=True)
    return merged[:top_k]


# ---------------------------------------------------------------------------
# Brazilian Legal Abbreviation Expander
# ---------------------------------------------------------------------------

LEGAL_ABBREVIATIONS: Dict[str, str] = {
    r"\bSTF\b": "Supremo Tribunal Federal",
    r"\bSTJ\b": "Superior Tribunal de Justica",
    r"\bTST\b": "Tribunal Superior do Trabalho",
    r"\bTSE\b": "Tribunal Superior Eleitoral",
    r"\bSTM\b": "Superior Tribunal Militar",
    r"\bTRF\b": "Tribunal Regional Federal",
    r"\bTRT\b": "Tribunal Regional do Trabalho",
    r"\bTRE\b": "Tribunal Regional Eleitoral",
    r"\bTJ\b": "Tribunal de Justica",
    r"\bCPC\b": "Codigo de Processo Civil",
    r"\bCPP\b": "Codigo de Processo Penal",
    r"\bCC\b": "Codigo Civil",
    r"\bCP\b": "Codigo Penal",
    r"\bCLT\b": "Consolidacao das Leis do Trabalho",
    r"\bCF\b": "Constituicao Federal",
    r"\bCRFB\b": "Constituicao da Republica Federativa do Brasil",
    r"\bCDC\b": "Codigo de Defesa do Consumidor",
    r"\bCTN\b": "Codigo Tributario Nacional",
    r"\bCTB\b": "Codigo de Transito Brasileiro",
    r"\bECA\b": "Estatuto da Crianca e do Adolescente",
    r"\bOAB\b": "Ordem dos Advogados do Brasil",
    r"\bMP\b": "Ministerio Publico",
    r"\bMPF\b": "Ministerio Publico Federal",
    r"\bAGU\b": "Advocacia-Geral da Uniao",
    r"\bDJe\b": "Diario de Justica Eletronico",
    r"\bDOU\b": "Diario Oficial da Uniao",
    r"\bLICC\b": "Lei de Introducao ao Codigo Civil",
    r"\bLINDB\b": "Lei de Introducao as Normas do Direito Brasileiro",
    r"\bLEF\b": "Lei de Execucao Fiscal",
    r"\bLEP\b": "Lei de Execucao Penal",
    r"\bADI\b": "Acao Direta de Inconstitucionalidade",
    r"\bADC\b": "Acao Declaratoria de Constitucionalidade",
    r"\bADPF\b": "Arguicao de Descumprimento de Preceito Fundamental",
    r"\bRE\b": "Recurso Extraordinario",
    r"\bREsp\b": "Recurso Especial",
    r"\bHC\b": "Habeas Corpus",
    r"\bMS\b": "Mandado de Seguranca",
    r"\bMI\b": "Mandado de Injuncao",
    r"\bHD\b": "Habeas Data",
    r"\bACP\b": "Acao Civil Publica",
}


def expand_legal_abbreviations(text: str) -> str:
    """
    Expand common Brazilian legal abbreviations in text.

    Args:
        text: Input text potentially containing abbreviations

    Returns:
        Text with abbreviations expanded
    """
    result = text
    for abbrev_pattern, full_form in LEGAL_ABBREVIATIONS.items():
        result = re.sub(abbrev_pattern, full_form, result, flags=re.IGNORECASE)
    return result


# ---------------------------------------------------------------------------
# Query Expansion Service
# ---------------------------------------------------------------------------

class QueryExpansionService:
    """
    Service for query expansion using HyDE and Multi-Query techniques.

    Provides advanced query expansion capabilities optimized for Brazilian
    legal domain using Gemini as the primary LLM.

    Usage:
        service = QueryExpansionService()

        # HyDE search
        hypothetical = await service.generate_hypothetical_document(
            query="O que e rescisao indireta?"
        )

        # Multi-Query
        variants = await service.generate_query_variants(
            query="requisitos para habeas corpus"
        )

        # Combined search
        results = await service.advanced_search(
            query="prazo prescricional acao trabalhista",
            lexical_search_fn=my_lexical_search,
            vector_search_fn=my_vector_search,
        )
    """

    def __init__(
        self,
        config: Optional[QueryExpansionConfig] = None,
        gemini_api_key: Optional[str] = None,
    ):
        """
        Initialize the QueryExpansionService.

        Args:
            config: Optional configuration (defaults to RAGConfig values)
            gemini_api_key: Optional Gemini API key (defaults to GOOGLE_API_KEY env)
        """
        self._config = config or QueryExpansionConfig.from_rag_config()
        self._cache = TTLCache(
            max_items=self._config.cache_max_items,
            default_ttl=self._config.cache_ttl_seconds,
        )

        # Configure Gemini
        import os
        api_key = gemini_api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)

        self._hyde_model: Optional[genai.GenerativeModel] = None
        self._multiquery_model: Optional[genai.GenerativeModel] = None

    @property
    def hyde_model(self) -> genai.GenerativeModel:
        """Lazy-initialize HyDE Gemini model."""
        if self._hyde_model is None:
            self._hyde_model = genai.GenerativeModel(
                model_name=self._config.hyde_model,
                generation_config={
                    "max_output_tokens": self._config.hyde_max_tokens,
                    "temperature": self._config.hyde_temperature,
                }
            )
        return self._hyde_model

    @property
    def multiquery_model(self) -> genai.GenerativeModel:
        """Lazy-initialize Multi-Query Gemini model."""
        if self._multiquery_model is None:
            self._multiquery_model = genai.GenerativeModel(
                model_name=self._config.multi_query_model,
                generation_config={
                    "max_output_tokens": self._config.multi_query_max_tokens,
                    "temperature": self._config.multi_query_temperature,
                }
            )
        return self._multiquery_model

    # -----------------------------------------------------------------------
    # Async LLM Calls
    # -----------------------------------------------------------------------

    async def _call_gemini(
        self,
        prompt: str,
        model: Optional[genai.GenerativeModel] = None,
        budget_tracker: Optional[Any] = None,
        operation: str = "unknown",
    ) -> str:
        """
        Call Gemini LLM asynchronously.

        Args:
            prompt: The prompt to send
            model: Optional model instance (defaults to hyde_model)
            budget_tracker: Optional BudgetTracker for cost control
            operation: Operation name for tracking ("hyde", "multiquery", etc.)

        Returns:
            Generated text response
        """
        model = model or self.hyde_model
        model_name = getattr(model, "_model_name", self._config.hyde_model)

        # Check budget before making call
        if budget_tracker is not None and BudgetTracker is not None:
            if not budget_tracker.can_make_llm_call():
                logger.warning(f"Skipping {operation}: LLM call budget exceeded")
                return ""

        def _sync_call() -> str:
            try:
                response = model.generate_content(prompt)
                if response and response.text:
                    return response.text.strip()
                return ""
            except Exception as exc:
                logger.warning(f"Gemini call failed: {exc}")
                return ""

        result = await asyncio.to_thread(_sync_call)

        # Track usage after successful call
        if budget_tracker is not None and estimate_tokens is not None and result:
            input_tokens = estimate_tokens(prompt, model_name)
            output_tokens = estimate_tokens(result, model_name)
            budget_tracker.track_llm_call(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model_name,
                operation=operation,
            )

        return result

    # -----------------------------------------------------------------------
    # Pipeline Compatibility (RAGPipeline expects expand/expand_async)
    # -----------------------------------------------------------------------

    async def expand_async(
        self,
        query: str,
        *,
        use_hyde: bool = True,
        use_multiquery: bool = True,
        max_queries: int = 3,
        budget_tracker: Optional[Any] = None,
    ) -> List[str]:
        """
        Return additional expanded queries for the pipeline.

        Note: The pipeline already includes the original query, so this returns
        only *extra* queries (multi-query variants and/or HyDE hypothetical doc).

        Args:
            query: Original query to expand
            use_hyde: Enable HyDE document generation
            use_multiquery: Enable multi-query expansion
            max_queries: Maximum query variants to generate
            budget_tracker: Optional BudgetTracker for cost control

        Returns:
            List of expanded queries (excluding original)
        """
        if not query or not query.strip():
            return []

        query = query.strip()

        extras: List[str] = []

        # Check budget before multi-query expansion
        if use_multiquery and max_queries > 0:
            can_expand = True
            if budget_tracker is not None and BudgetTracker is not None:
                if not budget_tracker.can_make_llm_call():
                    logger.info("Skipping multi-query: budget limit reached")
                    can_expand = False

            if can_expand:
                variants = await self.generate_query_variants(
                    query=query,
                    count=max_queries + 1,
                    budget_tracker=budget_tracker,
                )
                # Drop the original query (always first)
                extras.extend([v for v in variants[1:] if v and v.strip()])

        # Check budget before HyDE generation
        if use_hyde:
            can_hyde = True
            if budget_tracker is not None and BudgetTracker is not None:
                if not budget_tracker.can_make_llm_call():
                    logger.info("Skipping HyDE: budget limit reached")
                    can_hyde = False

            if can_hyde:
                hypo = await self.generate_hypothetical_document(
                    query=query,
                    budget_tracker=budget_tracker,
                )
                if hypo and hypo.strip():
                    extras.append(hypo.strip())

        # Deduplicate while preserving order
        seen = set()
        unique: List[str] = []
        for q in extras:
            key = q.lower().strip()
            if key and key not in seen:
                seen.add(key)
                unique.append(q.strip())
        return unique

    def expand(
        self,
        query: str,
        *,
        use_hyde: bool = True,
        use_multiquery: bool = True,
        max_queries: int = 3,
        budget_tracker: Optional[Any] = None,
    ) -> List[str]:
        """Synchronous wrapper for expand_async (for legacy/sync callers)."""
        return asyncio.run(
            self.expand_async(
                query,
                use_hyde=use_hyde,
                use_multiquery=use_multiquery,
                max_queries=max_queries,
                budget_tracker=budget_tracker,
            )
        )

    # -----------------------------------------------------------------------
    # HyDE Implementation
    # -----------------------------------------------------------------------

    async def generate_hypothetical_document(
        self,
        query: str,
        use_cache: bool = True,
        extended_prompt: bool = False,
        budget_tracker: Optional[Any] = None,
    ) -> str:
        """
        Generate a hypothetical document that would answer the query.

        This implements HyDE (Hypothetical Document Embeddings) for improved
        semantic search. The hypothetical document provides richer context
        for embedding-based retrieval.

        Args:
            query: User query to generate hypothetical answer for
            use_cache: Whether to use/update cache
            extended_prompt: Use longer, more detailed prompt
            budget_tracker: Optional BudgetTracker for cost control

        Returns:
            Hypothetical document text
        """
        if not query or not query.strip():
            return ""

        query = query.strip()

        # Check budget before making LLM call
        if budget_tracker is not None and BudgetTracker is not None:
            if not budget_tracker.can_make_llm_call():
                logger.info(f"Skipping HyDE generation: budget limit reached")
                return ""

        # Check cache first
        if use_cache:
            cache_key = f"{query}:ext={extended_prompt}"
            cached = self._cache.get("hyde", cache_key)
            if cached:
                logger.debug(f"HyDE cache hit for: {query[:50]}...")
                return cached

        # Generate hypothetical document
        prompt_template = HYDE_LEGAL_PROMPT_EXTENDED if extended_prompt else HYDE_LEGAL_PROMPT
        prompt = prompt_template.format(query=query)

        hypothetical = await self._call_gemini(
            prompt,
            self.hyde_model,
            budget_tracker=budget_tracker,
            operation="hyde",
        )

        if hypothetical and use_cache:
            self._cache.set("hyde", cache_key if use_cache else query, hypothetical)
            logger.debug(f"HyDE generated ({len(hypothetical)} chars) for: {query[:50]}...")

        return hypothetical or ""

    async def hyde_search(
        self,
        query: str,
        lexical_search_fn: Callable[[str, int], List[Dict[str, Any]]],
        vector_search_fn: Callable[[str, int], List[Dict[str, Any]]],
        top_k: int = 10,
        fetch_k: int = 30,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Perform HyDE-enhanced hybrid search.

        Strategy:
        1. Generate hypothetical document from query
        2. Use hypothetical doc for semantic search (higher weight)
        3. Use original query for lexical search
        4. Merge with weighted RRF

        Args:
            query: User query
            lexical_search_fn: Function(query, k) -> results
            vector_search_fn: Function(text, k) -> results
            top_k: Final number of results to return
            fetch_k: Results to fetch from each source
            use_cache: Whether to cache hypothetical documents

        Returns:
            Merged and ranked hybrid search results
        """
        if not self._config.hyde_enabled:
            logger.debug("HyDE disabled, using standard hybrid search")
            lexical = await asyncio.to_thread(lexical_search_fn, query, fetch_k)
            vector = await asyncio.to_thread(vector_search_fn, query, fetch_k)
            return merge_lexical_vector_rrf(
                lexical, vector, top_k=top_k, k_rrf=self._config.rrf_k
            )

        # Generate hypothetical document
        hypothetical = await self.generate_hypothetical_document(query, use_cache=use_cache)

        if not hypothetical:
            logger.warning("HyDE generation failed, using original query")
            hypothetical = query

        # Combine query and hypothetical for richer semantic search
        semantic_query = f"{query}\n\n{hypothetical}"

        # Execute searches in parallel
        lexical_task = asyncio.to_thread(lexical_search_fn, query, fetch_k)
        vector_task = asyncio.to_thread(vector_search_fn, semantic_query, fetch_k)

        results = await asyncio.gather(lexical_task, vector_task, return_exceptions=True)

        lexical_results = results[0] if not isinstance(results[0], Exception) else []
        vector_results = results[1] if not isinstance(results[1], Exception) else []

        if isinstance(results[0], Exception):
            logger.error(f"Lexical search failed: {results[0]}")
        if isinstance(results[1], Exception):
            logger.error(f"Vector search failed: {results[1]}")

        # Merge with HyDE weights (semantic gets higher weight)
        merged = merge_lexical_vector_rrf(
            lexical_results,
            vector_results,
            top_k=top_k,
            k_rrf=self._config.rrf_k,
            w_lex=self._config.hyde_lexical_weight,
            w_vec=self._config.hyde_semantic_weight,
        )

        # Add HyDE metadata
        for item in merged:
            item["hyde_used"] = True
            item["hyde_doc_length"] = len(hypothetical)

        return merged

    # -----------------------------------------------------------------------
    # Multi-Query Implementation
    # -----------------------------------------------------------------------

    async def generate_query_variants(
        self,
        query: str,
        count: Optional[int] = None,
        use_cache: bool = True,
        budget_tracker: Optional[Any] = None,
    ) -> List[str]:
        """
        Generate multiple query variants for multi-query RAG.

        Always includes the original query as the first variant.

        Args:
            query: Original user query
            count: Total number of variants (including original)
            use_cache: Whether to use/update cache
            budget_tracker: Optional BudgetTracker for cost control

        Returns:
            List of query variants with original query first
        """
        if not query or not query.strip():
            return [query] if query else []

        query = query.strip()
        count = count or self._config.multi_query_count

        # Always include original
        variants = [query]

        if count <= 1:
            return variants

        # Check budget before making LLM call
        if budget_tracker is not None and BudgetTracker is not None:
            if not budget_tracker.can_make_llm_call():
                logger.info(f"Skipping multi-query generation: budget limit reached")
                # Return original + heuristic variants only
                heuristic = self._generate_heuristic_variants(query, count - 1)
                variants.extend(heuristic)
                return variants[:count]

        # Check cache
        cache_key = f"{query}:{count}"
        if use_cache:
            cached = self._cache.get("multiquery", cache_key)
            if cached:
                logger.debug(f"Multi-query cache hit for: {query[:50]}...")
                return cached

        # Generate variants with LLM
        prompt = MULTI_QUERY_LEGAL_PROMPT.format(query=query, count=count - 1)
        response = await self._call_gemini(
            prompt,
            self.multiquery_model,
            budget_tracker=budget_tracker,
            operation="multiquery",
        )

        # Parse response
        if response:
            lines = [ln.strip() for ln in response.splitlines() if ln.strip()]
            for line in lines:
                # Clean up common prefixes (numbers, bullets, etc.)
                cleaned = re.sub(r"^[\d\.\-\*\)\]]+\s*", "", line).strip()
                cleaned = re.sub(r"^[\"']|[\"']$", "", cleaned)  # Remove quotes
                if cleaned and cleaned.lower() != query.lower() and len(cleaned) > 10:
                    variants.append(cleaned)
                    if len(variants) >= count:
                        break

        # Add heuristic variants if LLM didn't generate enough
        if len(variants) < count:
            heuristic = self._generate_heuristic_variants(query, count - len(variants))
            variants.extend(heuristic)

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for v in variants:
            key = v.lower().strip()
            if key not in seen:
                seen.add(key)
                unique.append(v)

        result = unique[:count]

        if use_cache and len(result) > 1:
            self._cache.set("multiquery", cache_key, result)

        logger.debug(f"Generated {len(result)} query variants for: {query[:50]}...")
        return result

    def _generate_heuristic_variants(self, query: str, count: int) -> List[str]:
        """
        Generate simple heuristic query variants as fallback.

        Args:
            query: Original query
            count: Number of variants to generate

        Returns:
            List of heuristic variants
        """
        variants = []

        # Variant 1: Keywords only (remove stopwords)
        stopwords = {
            "o", "a", "os", "as", "um", "uma", "de", "da", "do", "das", "dos",
            "em", "na", "no", "nas", "nos", "por", "para", "com", "sem",
            "que", "qual", "quais", "como", "quando", "onde", "porque",
            "e", "ou", "mas", "se", "nao", "sim", "muito", "mais", "menos",
            "ja", "ainda", "tambem", "so", "apenas", "mesmo", "proprio",
        }
        tokens = re.split(r"[\s,;:()\[\]{}?!]+", query.lower())
        keywords = [t for t in tokens if len(t) >= 3 and t not in stopwords]
        if keywords:
            keyword_query = " ".join(keywords[:10])
            if keyword_query.lower() != query.lower():
                variants.append(keyword_query)

        # Variant 2: Remove question mark and interrogative form
        if "?" in query:
            no_question = query.replace("?", "").strip()
            # Convert question to statement form
            no_question = re.sub(r"^(o que e|qual e|quais sao|como)\s+", "", no_question, flags=re.IGNORECASE)
            if no_question.lower() != query.lower():
                variants.append(no_question)

        # Variant 3: Expand legal abbreviations
        expanded = expand_legal_abbreviations(query)
        if expanded.lower() != query.lower():
            variants.append(expanded)

        # Variant 4: Add "direito brasileiro" context if not present
        if "brasil" not in query.lower() and "direito" in query.lower():
            contextual = f"{query} no direito brasileiro"
            variants.append(contextual)

        return variants[:count]

    async def multi_query_search(
        self,
        query: str,
        search_fn: Callable[[str, int], List[Dict[str, Any]]],
        top_k: int = 10,
        fetch_k: int = 20,
        variant_count: Optional[int] = None,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Perform multi-query search with RRF fusion.

        Strategy:
        1. Generate query variants
        2. Execute searches in parallel for all variants
        3. Merge results using RRF
        4. Deduplicate by chunk_uid

        Args:
            query: Original user query
            search_fn: Function(query, k) -> results
            top_k: Final number of results
            fetch_k: Results per variant
            variant_count: Number of variants (default from config)
            use_cache: Whether to cache variants

        Returns:
            Merged and ranked results
        """
        if not self._config.multi_query_enabled:
            logger.debug("Multi-query disabled, using single query")
            return await asyncio.to_thread(search_fn, query, top_k)

        # Generate variants
        variants = await self.generate_query_variants(
            query, count=variant_count, use_cache=use_cache
        )

        if len(variants) <= 1:
            return await asyncio.to_thread(search_fn, query, top_k)

        logger.debug(f"Multi-query search with {len(variants)} variants")

        # Execute searches in parallel
        tasks = [
            asyncio.to_thread(search_fn, variant, fetch_k)
            for variant in variants
        ]

        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out failed searches
        valid_results = []
        for i, res in enumerate(results_list):
            if isinstance(res, Exception):
                logger.warning(f"Search failed for variant '{variants[i][:50]}': {res}")
                continue
            valid_results.append(res)

        if not valid_results:
            logger.error("All multi-query searches failed, returning empty")
            return []

        # Merge with RRF
        merged = merge_results_rrf(
            valid_results,
            top_k=top_k,
            k_rrf=self._config.rrf_k,
        )

        # Add metadata
        for item in merged:
            item["multi_query_used"] = True
            item["query_variants_count"] = len(variants)

        return merged

    async def rewrite_query(
        self,
        query: str,
        use_cache: bool = True,
        budget_tracker: Optional[Any] = None,
    ) -> str:
        """
        Rewrite query for optimal retrieval.

        Useful as a preprocessing step before search.

        Args:
            query: Original query
            use_cache: Whether to cache results
            budget_tracker: Optional BudgetTracker for cost control

        Returns:
            Optimized query string
        """
        if not query or not query.strip():
            return query

        query = query.strip()

        # Check budget before making LLM call
        if budget_tracker is not None and BudgetTracker is not None:
            if not budget_tracker.can_make_llm_call():
                logger.info(f"Skipping query rewrite: budget limit reached")
                return query

        if use_cache:
            cached = self._cache.get("rewrite", query)
            if cached:
                return cached

        prompt = QUERY_REWRITE_LEGAL_PROMPT.format(query=query)
        rewritten = await self._call_gemini(
            prompt,
            self.multiquery_model,
            budget_tracker=budget_tracker,
            operation="rewrite",
        )

        result = rewritten.strip() if rewritten else query

        if use_cache and result != query:
            self._cache.set("rewrite", query, result)

        return result

    # -----------------------------------------------------------------------
    # Combined Search (HyDE + Multi-Query)
    # -----------------------------------------------------------------------

    async def advanced_search(
        self,
        query: str,
        lexical_search_fn: Callable[[str, int], List[Dict[str, Any]]],
        vector_search_fn: Callable[[str, int], List[Dict[str, Any]]],
        top_k: int = 10,
        fetch_k: int = 30,
        use_hyde: bool = True,
        use_multi_query: bool = True,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Combined advanced search using HyDE and Multi-Query.

        This is the most comprehensive search strategy:
        1. Generate query variants (Multi-Query)
        2. For each variant, optionally generate hypothetical doc (HyDE)
        3. Execute parallel hybrid searches (lexical + vector per variant)
        4. Merge all results with RRF

        This provides the highest quality retrieval but is also the most
        expensive in terms of LLM calls. Use for critical retrieval tasks.

        Args:
            query: User query
            lexical_search_fn: Function(query, k) -> results
            vector_search_fn: Function(text, k) -> results
            top_k: Final number of results
            fetch_k: Results per source
            use_hyde: Enable HyDE expansion
            use_multi_query: Enable multi-query expansion
            use_cache: Enable caching

        Returns:
            Merged and ranked results with full metadata
        """
        use_hyde = use_hyde and self._config.hyde_enabled
        use_multi_query = use_multi_query and self._config.multi_query_enabled

        # Get query variants
        if use_multi_query:
            variants = await self.generate_query_variants(query, use_cache=use_cache)
        else:
            variants = [query]

        logger.debug(f"Advanced search: {len(variants)} variants, HyDE={use_hyde}")

        all_results: List[List[Dict[str, Any]]] = []

        async def process_variant(variant: str) -> List[Dict[str, Any]]:
            """Process a single query variant with optional HyDE."""
            # Determine semantic query
            if use_hyde:
                hypothetical = await self.generate_hypothetical_document(
                    variant, use_cache=use_cache
                )
                semantic_query = f"{variant}\n\n{hypothetical}" if hypothetical else variant
                w_lex = self._config.hyde_lexical_weight
                w_vec = self._config.hyde_semantic_weight
            else:
                semantic_query = variant
                w_lex = 0.5
                w_vec = 0.5

            # Execute parallel searches
            lex_task = asyncio.to_thread(lexical_search_fn, variant, fetch_k)
            vec_task = asyncio.to_thread(vector_search_fn, semantic_query, fetch_k)

            results = await asyncio.gather(lex_task, vec_task, return_exceptions=True)

            lex_results = results[0] if not isinstance(results[0], Exception) else []
            vec_results = results[1] if not isinstance(results[1], Exception) else []

            # Merge lexical + vector for this variant
            return merge_lexical_vector_rrf(
                lex_results, vec_results,
                top_k=fetch_k,
                k_rrf=self._config.rrf_k,
                w_lex=w_lex,
                w_vec=w_vec,
            )

        # Process all variants in parallel
        variant_tasks = [process_variant(v) for v in variants]
        variant_results = await asyncio.gather(*variant_tasks, return_exceptions=True)

        for res in variant_results:
            if not isinstance(res, Exception) and res:
                all_results.append(res)

        if not all_results:
            logger.error("All advanced search variants failed")
            return []

        # Final merge across all variants
        merged = merge_results_rrf(all_results, top_k=top_k, k_rrf=self._config.rrf_k)

        # Add comprehensive metadata
        for item in merged:
            item["advanced_search"] = True
            item["hyde_used"] = use_hyde
            item["multi_query_used"] = use_multi_query
            item["query_variants_count"] = len(variants)

        return merged

    # -----------------------------------------------------------------------
    # Cache Management
    # -----------------------------------------------------------------------

    def clear_cache(self) -> None:
        """Clear the query expansion cache."""
        self._cache.clear()
        logger.info("Query expansion cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self._cache.stats()

    @property
    def config(self) -> QueryExpansionConfig:
        """Get current configuration."""
        return self._config


# ---------------------------------------------------------------------------
# Singleton / Factory
# ---------------------------------------------------------------------------

_service_instance: Optional[QueryExpansionService] = None
_service_lock = threading.Lock()


def get_query_expansion_service(
    config: Optional[QueryExpansionConfig] = None,
    gemini_api_key: Optional[str] = None,
) -> QueryExpansionService:
    """
    Get or create the singleton QueryExpansionService.

    Thread-safe factory function for the query expansion service.

    Args:
        config: Optional configuration override
        gemini_api_key: Optional Gemini API key

    Returns:
        QueryExpansionService singleton instance

    Usage:
        service = get_query_expansion_service()
        results = await service.hyde_search(...)
    """
    global _service_instance

    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = QueryExpansionService(
                    config=config,
                    gemini_api_key=gemini_api_key,
                )

    return _service_instance


def reset_query_expansion_service() -> None:
    """Reset the singleton instance (useful for testing)."""
    global _service_instance
    with _service_lock:
        if _service_instance is not None:
            _service_instance.clear_cache()
        _service_instance = None


# ---------------------------------------------------------------------------
# Convenience Exports
# ---------------------------------------------------------------------------

__all__ = [
    # Config
    "QueryExpansionConfig",
    # Cache
    "TTLCache",
    # RRF Functions
    "rrf_score",
    "merge_results_rrf",
    "merge_lexical_vector_rrf",
    # Utilities
    "expand_legal_abbreviations",
    "LEGAL_ABBREVIATIONS",
    # Prompts
    "HYDE_LEGAL_PROMPT",
    "HYDE_LEGAL_PROMPT_EXTENDED",
    "MULTI_QUERY_LEGAL_PROMPT",
    "QUERY_REWRITE_LEGAL_PROMPT",
    # Service
    "QueryExpansionService",
    "get_query_expansion_service",
    "reset_query_expansion_service",
]
