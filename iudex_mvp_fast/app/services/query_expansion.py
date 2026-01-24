"""
Query Expansion Module: HyDE and Multi-Query RAG

This module provides advanced query expansion techniques for legal RAG:
- HyDE (Hypothetical Document Embeddings): Generate hypothetical answers for better semantic search
- Multi-Query: Generate query variants and merge results using RRF

Reference: Based on patterns from apps/api/app/services/ai/rag_helpers.py
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import time
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from openai import OpenAI

logger = logging.getLogger("QueryExpansion")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class QueryExpansionConfig:
    """Configuration for query expansion features."""

    # HyDE settings
    hyde_enabled: bool = True
    hyde_model: str = "gpt-4o"
    hyde_max_tokens: int = 500
    hyde_temperature: float = 0.3
    hyde_semantic_weight: float = 0.7  # Higher weight on semantic for HyDE
    hyde_lexical_weight: float = 0.3

    # Multi-Query settings
    multi_query_enabled: bool = True
    multi_query_model: str = "gpt-4o"
    multi_query_count: int = 4  # 3-5 variants (original + generated)
    multi_query_max_tokens: int = 300
    multi_query_temperature: float = 0.5

    # Cache settings
    cache_ttl_seconds: int = 3600  # 1 hour
    cache_max_items: int = 5000

    # RRF settings
    rrf_k: int = 60

    @classmethod
    def from_env(cls) -> "QueryExpansionConfig":
        """Load configuration from environment variables."""
        return cls(
            hyde_enabled=os.getenv("HYDE_ENABLED", "true").lower() in ("1", "true", "yes", "on"),
            hyde_model=os.getenv("HYDE_MODEL", "gpt-4o"),
            hyde_max_tokens=int(os.getenv("HYDE_MAX_TOKENS", "500")),
            hyde_temperature=float(os.getenv("HYDE_TEMPERATURE", "0.3")),
            hyde_semantic_weight=float(os.getenv("HYDE_SEMANTIC_WEIGHT", "0.7")),
            hyde_lexical_weight=float(os.getenv("HYDE_LEXICAL_WEIGHT", "0.3")),
            multi_query_enabled=os.getenv("MULTI_QUERY_ENABLED", "true").lower() in ("1", "true", "yes", "on"),
            multi_query_model=os.getenv("MULTI_QUERY_MODEL", "gpt-4o"),
            multi_query_count=int(os.getenv("MULTI_QUERY_COUNT", "4")),
            multi_query_max_tokens=int(os.getenv("MULTI_QUERY_MAX_TOKENS", "300")),
            multi_query_temperature=float(os.getenv("MULTI_QUERY_TEMPERATURE", "0.5")),
            cache_ttl_seconds=int(os.getenv("QUERY_EXPANSION_CACHE_TTL", "3600")),
            cache_max_items=int(os.getenv("QUERY_EXPANSION_CACHE_MAX_ITEMS", "5000")),
            rrf_k=int(os.getenv("RRF_K", "60")),
        )


# ---------------------------------------------------------------------------
# Legal Domain Prompts
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


MULTI_QUERY_LEGAL_PROMPT = """Voce e um especialista em recuperacao de informacao juridica. Dada a pergunta original, gere {count} variantes de busca que capturem diferentes aspectos da mesma pergunta.

Regras:
- Cada variante deve ser uma reformulacao ou expansao da pergunta original
- Use sinonimos juridicos e termos tecnicos quando apropriado
- Inclua variantes com diferentes niveis de especificidade
- Cada variante em uma linha separada
- Sem numeracao, marcadores ou prefixos
- Mantenha o contexto legal brasileiro

Pergunta original: {query}

Variantes de busca:"""


QUERY_REWRITE_LEGAL_PROMPT = """Reescreva a pergunta abaixo como uma consulta de busca otimizada para um sistema RAG juridico.

Regras:
- Mantenha os termos juridicos essenciais
- Remova palavras vazias desnecessarias
- Expanda siglas se necessario (STF, STJ, CPC, etc.)
- Mantenha conciso (maximo 50 palavras)
- Resultado em uma unica linha

Pergunta: {query}

Consulta otimizada:"""


# ---------------------------------------------------------------------------
# TTL Cache Implementation
# ---------------------------------------------------------------------------

class TTLCache:
    """Thread-safe TTL cache for query expansion results."""

    def __init__(self, max_items: int = 5000, default_ttl: int = 3600):
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.RLock()
        self._max_items = max_items
        self._default_ttl = default_ttl

    def _make_key(self, prefix: str, text: str) -> str:
        """Create a unique cache key."""
        h = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:32]
        return f"{prefix}:{h}"

    def get(self, prefix: str, text: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        key = self._make_key(prefix, text)
        now = time.time()

        with self._lock:
            item = self._cache.get(key)
            if item and item[0] > now:
                return item[1]
            elif item:
                # Expired, remove it
                self._cache.pop(key, None)
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
        # First, remove expired
        expired = [k for k, (exp, _) in self._cache.items() if exp <= now]
        for k in expired[:1000]:
            self._cache.pop(k, None)

        # If still too large, remove oldest
        if len(self._cache) >= self._max_items:
            # Sort by expiration time and remove oldest 20%
            sorted_items = sorted(self._cache.items(), key=lambda x: x[1][0])
            to_remove = len(sorted_items) // 5
            for k, _ in sorted_items[:to_remove]:
                self._cache.pop(k, None)

    def clear(self) -> None:
        """Clear entire cache."""
        with self._lock:
            self._cache.clear()


# ---------------------------------------------------------------------------
# RRF (Reciprocal Rank Fusion) Implementation
# ---------------------------------------------------------------------------

def rrf_score(rank: int, k: int = 60) -> float:
    """Calculate RRF score for a given rank."""
    return 1.0 / (k + rank)


def merge_results_rrf(
    result_lists: List[List[Dict[str, Any]]],
    top_k: int = 10,
    k_rrf: int = 60,
) -> List[Dict[str, Any]]:
    """
    Merge multiple result lists using Reciprocal Rank Fusion.
    Deduplicates by chunk_uid.
    """
    if not result_lists:
        return []

    # Flatten single list case
    if len(result_lists) == 1:
        return result_lists[0][:top_k]

    # Score accumulator by chunk_uid
    scores: Dict[str, float] = {}
    chunks: Dict[str, Dict[str, Any]] = {}
    sources_set: Dict[str, set] = {}

    for list_idx, results in enumerate(result_lists):
        for rank, item in enumerate(results, start=1):
            uid = item.get("chunk_uid")
            if not uid:
                continue

            # Accumulate RRF score
            score = rrf_score(rank, k_rrf)
            scores[uid] = scores.get(uid, 0.0) + score

            # Store chunk data (first occurrence)
            if uid not in chunks:
                chunks[uid] = {
                    "chunk_uid": uid,
                    "text": item.get("text", ""),
                    "metadata": item.get("metadata", {}),
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
            "sources": list(sources_set.get(uid, set())),
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
) -> List[Dict[str, Any]]:
    """
    Merge lexical and vector results with weighted RRF.
    """
    if not lexical and not vector:
        return []
    if not lexical:
        return vector[:top_k]
    if not vector:
        return lexical[:top_k]

    scores: Dict[str, float] = {}
    chunks: Dict[str, Dict[str, Any]] = {}
    sources_set: Dict[str, set] = {}

    # Process lexical results
    for rank, item in enumerate(lexical, start=1):
        uid = item.get("chunk_uid")
        if not uid:
            continue
        scores[uid] = scores.get(uid, 0.0) + w_lex * rrf_score(rank, k_rrf)
        if uid not in chunks:
            chunks[uid] = {
                "chunk_uid": uid,
                "text": item.get("text", ""),
                "metadata": item.get("metadata", {}),
            }
        if uid not in sources_set:
            sources_set[uid] = set()
        sources_set[uid].add("lexical")

    # Process vector results
    for rank, item in enumerate(vector, start=1):
        uid = item.get("chunk_uid")
        if not uid:
            continue
        scores[uid] = scores.get(uid, 0.0) + w_vec * rrf_score(rank, k_rrf)
        if uid not in chunks:
            chunks[uid] = {
                "chunk_uid": uid,
                "text": item.get("text", ""),
                "metadata": item.get("metadata", {}),
            }
        if uid not in sources_set:
            sources_set[uid] = set()
        sources_set[uid].add("vector")

    # Build final results
    merged = []
    for uid, chunk in chunks.items():
        merged.append({
            **chunk,
            "final_score": scores[uid],
            "sources": list(sources_set.get(uid, set())),
        })

    merged.sort(key=lambda x: x["final_score"], reverse=True)
    return merged[:top_k]


# ---------------------------------------------------------------------------
# Query Expansion Service
# ---------------------------------------------------------------------------

class QueryExpansionService:
    """
    Service for query expansion using HyDE and Multi-Query techniques.

    Usage:
        service = QueryExpansionService(api_key="sk-...")

        # HyDE search
        results = await service.hyde_search(
            query="O que e rescisao indireta?",
            search_fn=my_search_function,
        )

        # Multi-Query search
        results = await service.multi_query_search(
            query="requisitos para habeas corpus",
            search_fn=my_search_function,
        )
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        config: Optional[QueryExpansionConfig] = None,
    ):
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._config = config or QueryExpansionConfig.from_env()
        self._cache = TTLCache(
            max_items=self._config.cache_max_items,
            default_ttl=self._config.cache_ttl_seconds,
        )
        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        """Lazy-initialize OpenAI client."""
        if self._client is None:
            if not self._api_key:
                raise ValueError("OpenAI API key not configured")
            self._client = OpenAI(api_key=self._api_key)
        return self._client

    # -----------------------------------------------------------------------
    # LLM Calls
    # -----------------------------------------------------------------------

    async def _call_llm(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> str:
        """Call OpenAI LLM asynchronously."""
        model = model or self._config.hyde_model

        def _sync_call() -> str:
            try:
                resp = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                if not resp.choices:
                    return ""
                return (resp.choices[0].message.content or "").strip()
            except Exception as exc:
                logger.warning(f"LLM call failed: {exc}")
                return ""

        return await asyncio.to_thread(_sync_call)

    # -----------------------------------------------------------------------
    # HyDE Implementation
    # -----------------------------------------------------------------------

    async def generate_hypothetical_document(
        self,
        query: str,
        use_cache: bool = True,
    ) -> str:
        """
        Generate a hypothetical document that would answer the query.
        Used for HyDE (Hypothetical Document Embeddings).
        """
        if not query or not query.strip():
            return ""

        query = query.strip()

        # Check cache
        if use_cache:
            cached = self._cache.get("hyde", query)
            if cached:
                logger.debug(f"HyDE cache hit for query: {query[:50]}...")
                return cached

        # Generate hypothetical document
        prompt = HYDE_LEGAL_PROMPT.format(query=query)
        hypothetical = await self._call_llm(
            prompt=prompt,
            model=self._config.hyde_model,
            max_tokens=self._config.hyde_max_tokens,
            temperature=self._config.hyde_temperature,
        )

        if hypothetical and use_cache:
            self._cache.set("hyde", query, hypothetical)

        return hypothetical or ""

    async def hyde_search(
        self,
        query: str,
        lexical_search_fn: Callable[[str, int], List[Dict[str, Any]]],
        vector_search_fn: Callable[[str, int], List[Dict[str, Any]]],
        embed_fn: Callable[[str], List[float]],
        top_k: int = 10,
        fetch_k: int = 30,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Perform HyDE-enhanced search.

        1. Generate hypothetical document from query
        2. Use hypothetical doc for semantic search (higher weight)
        3. Use original query for lexical search
        4. Merge with weighted RRF

        Args:
            query: User query
            lexical_search_fn: Function(query, k) -> results for lexical search
            vector_search_fn: Function(embedding_text, k) -> results for vector search
            embed_fn: Function(text) -> embedding vector
            top_k: Number of results to return
            fetch_k: Number of results to fetch from each source
            use_cache: Whether to use cache for hypothetical documents

        Returns:
            Merged and ranked results
        """
        if not self._config.hyde_enabled:
            # Fall back to standard search
            logger.debug("HyDE disabled, using standard search")
            lexical = lexical_search_fn(query, fetch_k)
            vector = vector_search_fn(query, fetch_k)
            return merge_lexical_vector_rrf(
                lexical, vector, top_k=top_k, k_rrf=self._config.rrf_k
            )

        # Generate hypothetical document
        hypothetical = await self.generate_hypothetical_document(query, use_cache=use_cache)

        if not hypothetical:
            logger.warning("HyDE generation failed, falling back to standard search")
            hypothetical = query

        # Combine query and hypothetical for semantic search
        # This gives better results than hypothetical alone
        semantic_query = f"{query}\n\n{hypothetical}"

        # Execute searches
        # Lexical: use original query (better for exact term matching)
        # Vector: use hypothetical doc (better semantic understanding)
        lexical_task = asyncio.to_thread(lexical_search_fn, query, fetch_k)
        vector_task = asyncio.to_thread(vector_search_fn, semantic_query, fetch_k)

        lexical_results, vector_results = await asyncio.gather(
            lexical_task, vector_task, return_exceptions=True
        )

        # Handle exceptions
        if isinstance(lexical_results, Exception):
            logger.error(f"Lexical search failed: {lexical_results}")
            lexical_results = []
        if isinstance(vector_results, Exception):
            logger.error(f"Vector search failed: {vector_results}")
            vector_results = []

        # Merge with HyDE weights (higher semantic weight)
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

        return merged

    # -----------------------------------------------------------------------
    # Multi-Query Implementation
    # -----------------------------------------------------------------------

    async def generate_query_variants(
        self,
        query: str,
        count: Optional[int] = None,
        use_cache: bool = True,
    ) -> List[str]:
        """
        Generate multiple query variants for multi-query RAG.
        Always includes the original query.
        """
        if not query or not query.strip():
            return [query] if query else []

        query = query.strip()
        count = count or self._config.multi_query_count

        # Always include original
        variants = [query]

        if count <= 1:
            return variants

        # Check cache
        cache_key = f"{query}:{count}"
        if use_cache:
            cached = self._cache.get("multi_query", cache_key)
            if cached:
                logger.debug(f"Multi-query cache hit for: {query[:50]}...")
                return cached

        # Generate variants with LLM
        prompt = MULTI_QUERY_LEGAL_PROMPT.format(query=query, count=count - 1)
        response = await self._call_llm(
            prompt=prompt,
            model=self._config.multi_query_model,
            max_tokens=self._config.multi_query_max_tokens,
            temperature=self._config.multi_query_temperature,
        )

        # Parse response
        if response:
            lines = [ln.strip() for ln in response.splitlines() if ln.strip()]
            # Clean up common prefixes
            for line in lines:
                cleaned = re.sub(r"^[\d\.\-\*\)\]]+\s*", "", line).strip()
                if cleaned and cleaned.lower() != query.lower():
                    variants.append(cleaned)
                    if len(variants) >= count:
                        break

        # Add heuristic variants if LLM didn't generate enough
        if len(variants) < count:
            variants.extend(self._heuristic_variants(query, count - len(variants)))

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for v in variants:
            key = v.lower()
            if key not in seen:
                seen.add(key)
                unique.append(v)

        result = unique[:count]

        if use_cache:
            self._cache.set("multi_query", cache_key, result)

        return result

    def _heuristic_variants(self, query: str, count: int) -> List[str]:
        """Generate simple heuristic query variants."""
        variants = []

        # Variant 1: Keywords only
        tokens = [t for t in re.split(r"[\s,;:()\[\]{}]+", query) if len(t) >= 4]
        if tokens:
            keywords = " ".join(tokens[:8])
            if keywords.lower() != query.lower():
                variants.append(keywords)

        # Variant 2: Remove question mark
        if "?" in query:
            no_question = query.replace("?", "").strip()
            if no_question.lower() != query.lower():
                variants.append(no_question)

        # Variant 3: Expand common legal abbreviations
        expanded = self._expand_legal_abbreviations(query)
        if expanded.lower() != query.lower():
            variants.append(expanded)

        return variants[:count]

    def _expand_legal_abbreviations(self, text: str) -> str:
        """Expand common Brazilian legal abbreviations."""
        expansions = {
            r"\bSTF\b": "Supremo Tribunal Federal",
            r"\bSTJ\b": "Superior Tribunal de Justica",
            r"\bTST\b": "Tribunal Superior do Trabalho",
            r"\bCPC\b": "Codigo de Processo Civil",
            r"\bCPP\b": "Codigo de Processo Penal",
            r"\bCC\b": "Codigo Civil",
            r"\bCP\b": "Codigo Penal",
            r"\bCLT\b": "Consolidacao das Leis do Trabalho",
            r"\bCF\b": "Constituicao Federal",
            r"\bCDC\b": "Codigo de Defesa do Consumidor",
            r"\bOAB\b": "Ordem dos Advogados do Brasil",
        }
        result = text
        for abbrev, full in expansions.items():
            result = re.sub(abbrev, full, result, flags=re.IGNORECASE)
        return result

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

        1. Generate query variants
        2. Execute searches in parallel
        3. Merge results using RRF
        4. Deduplicate by chunk_uid

        Args:
            query: Original user query
            search_fn: Function(query, k) -> results
            top_k: Number of results to return
            fetch_k: Number of results to fetch per variant
            variant_count: Number of query variants (default from config)
            use_cache: Whether to use cache

        Returns:
            Merged and ranked results
        """
        if not self._config.multi_query_enabled:
            logger.debug("Multi-query disabled, using single query")
            return search_fn(query, top_k)

        # Generate variants
        variants = await self.generate_query_variants(
            query, count=variant_count, use_cache=use_cache
        )

        if len(variants) <= 1:
            return search_fn(query, top_k)

        logger.debug(f"Multi-query variants: {variants}")

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
                logger.warning(f"Search failed for variant '{variants[i]}': {res}")
                continue
            valid_results.append(res)

        if not valid_results:
            logger.error("All multi-query searches failed")
            return []

        # Merge with RRF
        merged = merge_results_rrf(
            valid_results,
            top_k=top_k,
            k_rrf=self._config.rrf_k,
        )

        # Add multi-query metadata
        for item in merged:
            item["multi_query_used"] = True
            item["query_variants"] = variants

        return merged

    async def rewrite_query(
        self,
        query: str,
        use_cache: bool = True,
    ) -> str:
        """
        Rewrite query for optimal retrieval.
        Useful as a preprocessing step.
        """
        if not query or not query.strip():
            return query

        query = query.strip()

        if use_cache:
            cached = self._cache.get("rewrite", query)
            if cached:
                return cached

        prompt = QUERY_REWRITE_LEGAL_PROMPT.format(query=query)
        rewritten = await self._call_llm(
            prompt=prompt,
            model=self._config.multi_query_model,
            max_tokens=100,
            temperature=0.2,
        )

        result = rewritten.strip() or query

        if use_cache:
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
        embed_fn: Optional[Callable[[str], List[float]]] = None,
        top_k: int = 10,
        fetch_k: int = 30,
        use_hyde: bool = True,
        use_multi_query: bool = True,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Combined advanced search using HyDE and Multi-Query.

        Strategy:
        1. Generate query variants (Multi-Query)
        2. For each variant, optionally generate hypothetical doc (HyDE)
        3. Execute parallel searches (lexical + vector per variant)
        4. Merge all results with RRF

        This is the most comprehensive search but also most expensive.
        Use for high-quality retrieval needs.
        """
        use_hyde = use_hyde and self._config.hyde_enabled
        use_multi_query = use_multi_query and self._config.multi_query_enabled

        # Get query variants
        if use_multi_query:
            variants = await self.generate_query_variants(query, use_cache=use_cache)
        else:
            variants = [query]

        logger.debug(f"Advanced search with {len(variants)} variants, HyDE={use_hyde}")

        all_results: List[List[Dict[str, Any]]] = []

        # Process each variant
        async def process_variant(variant: str) -> List[Dict[str, Any]]:
            # Determine semantic query (with or without HyDE)
            if use_hyde:
                hypothetical = await self.generate_hypothetical_document(variant, use_cache=use_cache)
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

            lex_results, vec_results = await asyncio.gather(
                lex_task, vec_task, return_exceptions=True
            )

            if isinstance(lex_results, Exception):
                lex_results = []
            if isinstance(vec_results, Exception):
                vec_results = []

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

        # Add metadata
        for item in merged:
            item["advanced_search"] = True
            item["hyde_used"] = use_hyde
            item["multi_query_used"] = use_multi_query
            if use_multi_query:
                item["query_variants"] = variants

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
        with self._cache._lock:
            now = time.time()
            total = len(self._cache._cache)
            expired = sum(1 for _, (exp, _) in self._cache._cache.items() if exp <= now)
            return {
                "total_entries": total,
                "expired_entries": expired,
                "active_entries": total - expired,
                "max_entries": self._cache._max_items,
            }


# ---------------------------------------------------------------------------
# Singleton / Factory
# ---------------------------------------------------------------------------

_service_instance: Optional[QueryExpansionService] = None
_service_lock = threading.Lock()


def get_query_expansion_service(
    api_key: Optional[str] = None,
    config: Optional[QueryExpansionConfig] = None,
) -> QueryExpansionService:
    """
    Get or create the singleton QueryExpansionService.

    Usage:
        service = get_query_expansion_service()
        results = await service.hyde_search(...)
    """
    global _service_instance

    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = QueryExpansionService(
                    api_key=api_key,
                    config=config,
                )

    return _service_instance


def reset_query_expansion_service() -> None:
    """Reset the singleton instance (useful for testing)."""
    global _service_instance
    with _service_lock:
        _service_instance = None
