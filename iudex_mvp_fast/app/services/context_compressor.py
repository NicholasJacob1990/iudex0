"""
Context compression service for RAG pipelines.

Provides intelligent compression of retrieved chunks to fit within
token budgets while preserving the most relevant information.

Features:
- Sentence-level compression (keep relevant sentences)
- Keyword-based filtering with Portuguese stopwords
- Token budget management
- Preservation of full_text for audit trails
- Metadata preservation through transformations
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("ContextCompressor")


# Portuguese stopwords for keyword extraction
PORTUGUESE_STOPWORDS: Set[str] = {
    # Articles
    "o", "a", "os", "as", "um", "uma", "uns", "umas",
    # Prepositions and contractions
    "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas",
    "por", "pelo", "pela", "pelos", "pelas", "para", "com", "sem",
    "sob", "sobre", "entre", "contra", "desde", "ate", "apos",
    # Conjunctions
    "e", "ou", "mas", "porem", "contudo", "todavia", "entretanto",
    "quando", "enquanto", "como", "porque", "pois", "portanto",
    # Pronouns
    "eu", "tu", "ele", "ela", "nos", "vos", "eles", "elas",
    "me", "te", "se", "lhe", "nos", "vos", "lhes",
    "meu", "minha", "teu", "tua", "seu", "sua", "nosso", "nossa",
    "este", "esta", "esse", "essa", "aquele", "aquela", "isto", "isso", "aquilo",
    "que", "qual", "quais", "quem", "cujo", "cuja",
    # Adverbs
    "nao", "sim", "muito", "pouco", "mais", "menos", "bem", "mal",
    "ja", "ainda", "sempre", "nunca", "jamais", "talvez", "assim",
    "onde", "aqui", "ali", "la", "ca", "dentro", "fora",
    # Verbs (common)
    "ser", "estar", "ter", "haver", "fazer", "poder", "dever",
    "foi", "era", "sido", "sendo", "esta", "estao", "estava",
    "tem", "tinha", "teve", "tendo", "tido",
    "ha", "havia", "houve", "havendo",
    # Other common words
    "ao", "aos", "pela", "pelas", "pelo", "pelos",
    "mesmo", "mesma", "mesmos", "mesmas",
    "todo", "toda", "todos", "todas",
    "outro", "outra", "outros", "outras",
    "cada", "algum", "alguma", "alguns", "algumas",
    "nenhum", "nenhuma", "nenhuns", "nenhumas",
    "certo", "certa", "certos", "certas",
}

# Sentence splitting pattern
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[\.\?!;:])\s+")

# Word tokenization pattern
WORD_PATTERN = re.compile(r"\b\w+\b", re.UNICODE)


@dataclass
class CompressionConfig:
    """Configuration for the context compressor."""

    # Maximum characters per compressed chunk
    max_chars_per_chunk: int = 1000

    # Total token budget (approximate, using 4 chars per token)
    token_budget: int = 4000

    # Chars per token approximation
    chars_per_token: float = 4.0

    # Minimum keyword length to consider
    min_keyword_length: int = 4

    # Preserve full_text field for audit
    preserve_full_text: bool = True

    # Minimum sentences to keep per chunk
    min_sentences: int = 1

    # Maximum sentences to evaluate per chunk
    max_sentences_to_evaluate: int = 50

    # Boost factor for sentences with multiple keyword matches
    multi_keyword_boost: float = 1.5

    @classmethod
    def from_env(cls) -> "CompressionConfig":
        """Load configuration from environment variables."""
        return cls(
            max_chars_per_chunk=int(os.getenv("COMPRESSOR_MAX_CHARS", "1000")),
            token_budget=int(os.getenv("COMPRESSOR_TOKEN_BUDGET", "4000")),
            chars_per_token=float(os.getenv("COMPRESSOR_CHARS_PER_TOKEN", "4.0")),
            min_keyword_length=int(os.getenv("COMPRESSOR_MIN_KEYWORD_LEN", "4")),
            preserve_full_text=os.getenv("COMPRESSOR_PRESERVE_FULL", "true").lower() in ("1", "true", "yes"),
            min_sentences=int(os.getenv("COMPRESSOR_MIN_SENTENCES", "1")),
            max_sentences_to_evaluate=int(os.getenv("COMPRESSOR_MAX_SENTENCES", "50")),
            multi_keyword_boost=float(os.getenv("COMPRESSOR_KEYWORD_BOOST", "1.5")),
        )


@dataclass
class CompressionResult:
    """Result of a compression operation."""

    results: List[Dict[str, Any]]
    original_chars: int
    compressed_chars: int
    chunks_compressed: int
    chunks_unchanged: int
    chunks_empty: int
    compression_ratio: float = 0.0
    duration_ms: float = 0.0


class ContextCompressor:
    """
    Context compressor for RAG results.

    Compresses retrieved chunks to fit within token budgets while
    preserving the most query-relevant content using keyword matching
    and sentence-level extraction.
    """

    def __init__(self, config: Optional[CompressionConfig] = None):
        self.config = config or CompressionConfig.from_env()

    def extract_keywords(self, query: str) -> List[str]:
        """
        Extract meaningful keywords from a query.

        Filters out stopwords and short tokens.
        """
        if not query:
            return []

        tokens = WORD_PATTERN.findall(query.lower())
        keywords = [
            token for token in tokens
            if len(token) >= self.config.min_keyword_length
            and token not in PORTUGUESE_STOPWORDS
        ]

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique.append(kw)

        return unique

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        if not text:
            return []

        sentences = SENTENCE_SPLIT_PATTERN.split(text.strip())
        return [s.strip() for s in sentences if s.strip()]

    def _score_sentence(self, sentence: str, keywords: List[str]) -> float:
        """
        Score a sentence based on keyword matches.

        Returns a score based on:
        - Number of keyword matches
        - Multi-keyword bonus
        """
        if not sentence or not keywords:
            return 0.0

        lower_sentence = sentence.lower()
        matches = sum(1 for kw in keywords if kw in lower_sentence)

        if matches == 0:
            return 0.0

        # Base score from matches
        score = float(matches)

        # Bonus for multiple keywords (indicates high relevance)
        if matches > 1:
            score *= self.config.multi_keyword_boost

        return score

    def compress_text(
        self,
        text: str,
        keywords: List[str],
        max_chars: Optional[int] = None,
    ) -> str:
        """
        Compress a single text block based on keyword relevance.

        Args:
            text: The text to compress
            keywords: Keywords to match for relevance
            max_chars: Maximum characters in output

        Returns:
            Compressed text preserving most relevant sentences
        """
        if not text:
            return ""

        text = text.strip()
        max_chars = max_chars or self.config.max_chars_per_chunk

        # Already within budget
        if len(text) <= max_chars:
            return text

        sentences = self._split_sentences(text)
        if not sentences:
            return text[:max_chars]

        # Limit sentences to evaluate
        if len(sentences) > self.config.max_sentences_to_evaluate:
            sentences = sentences[:self.config.max_sentences_to_evaluate]

        # Score sentences
        scored = []
        for i, sentence in enumerate(sentences):
            score = self._score_sentence(sentence, keywords)
            # Add position bonus for earlier sentences (often more important)
            position_bonus = 0.1 * (1.0 - i / len(sentences))
            scored.append((score + position_bonus, i, sentence))

        # Sort by score (descending), then by position (ascending)
        scored.sort(key=lambda x: (-x[0], x[1]))

        # Select sentences until budget exhausted
        selected_indices = []
        current_chars = 0

        for score, idx, sentence in scored:
            sentence_len = len(sentence)
            if current_chars + sentence_len + 1 <= max_chars:
                selected_indices.append(idx)
                current_chars += sentence_len + 1  # +1 for space
            elif len(selected_indices) >= self.config.min_sentences:
                break

        # Ensure minimum sentences
        while len(selected_indices) < self.config.min_sentences and len(scored) > len(selected_indices):
            for score, idx, sentence in scored:
                if idx not in selected_indices:
                    selected_indices.append(idx)
                    break

        if not selected_indices:
            # Fallback: return truncated original
            return text[:max_chars].strip()

        # Reconstruct in original order
        selected_indices.sort()
        selected_sentences = [sentences[i] for i in selected_indices]
        compressed = " ".join(selected_sentences)

        # Final truncation if still over budget
        if len(compressed) > max_chars:
            compressed = compressed[:max_chars].strip()

        return compressed

    def compress_chunk(
        self,
        chunk: Dict[str, Any],
        keywords: List[str],
        max_chars: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Compress a single retrieval result chunk.

        Preserves metadata and optionally stores full_text for audit.
        """
        result = chunk.copy()
        text = chunk.get("text", "")

        if not text or not text.strip():
            result["compressed"] = False
            return result

        max_chars = max_chars or self.config.max_chars_per_chunk
        original_len = len(text)

        # Already within budget
        if original_len <= max_chars:
            result["compressed"] = False
            return result

        # Compress
        compressed_text = self.compress_text(text, keywords, max_chars)

        # Preserve full text for audit if enabled
        if self.config.preserve_full_text:
            result["full_text"] = text

        result["text"] = compressed_text
        result["compressed"] = True
        result["original_length"] = original_len
        result["compressed_length"] = len(compressed_text)

        return result

    def compress_results(
        self,
        query: str,
        results: List[Dict[str, Any]],
        max_chars_per_chunk: Optional[int] = None,
        token_budget: Optional[int] = None,
    ) -> CompressionResult:
        """
        Compress a list of retrieval results to fit token budget.

        Args:
            query: The search query for keyword extraction
            results: List of retrieval results with 'text' field
            max_chars_per_chunk: Override for per-chunk limit
            token_budget: Override for total token budget

        Returns:
            CompressionResult with compressed results and statistics
        """
        import time
        start_time = time.perf_counter()

        if not results:
            return CompressionResult(
                results=[],
                original_chars=0,
                compressed_chars=0,
                chunks_compressed=0,
                chunks_unchanged=0,
                chunks_empty=0,
                compression_ratio=1.0,
                duration_ms=0.0,
            )

        keywords = self.extract_keywords(query)
        max_chars = max_chars_per_chunk or self.config.max_chars_per_chunk
        budget = token_budget or self.config.token_budget
        budget_chars = int(budget * self.config.chars_per_token)

        # First pass: compress individual chunks
        compressed_results = []
        original_chars = 0
        chunks_compressed = 0
        chunks_unchanged = 0
        chunks_empty = 0

        for chunk in results:
            text = chunk.get("text", "")
            original_chars += len(text)

            if not text or not text.strip():
                chunks_empty += 1
                compressed_results.append(chunk.copy())
                continue

            compressed = self.compress_chunk(chunk, keywords, max_chars)

            if compressed.get("compressed"):
                chunks_compressed += 1
            else:
                chunks_unchanged += 1

            compressed_results.append(compressed)

        # Second pass: enforce total budget if needed
        current_chars = sum(len(r.get("text", "")) for r in compressed_results)

        if current_chars > budget_chars:
            # Need to truncate further
            # Distribute budget proportionally based on scores
            scores = []
            for r in compressed_results:
                score = r.get("rerank_score") or r.get("final_score") or r.get("score", 0.5)
                scores.append(max(0.1, float(score)))

            total_score = sum(scores)
            allocated_chars = []

            for score in scores:
                share = (score / total_score) * budget_chars if total_score > 0 else budget_chars / len(scores)
                allocated_chars.append(int(share))

            # Recompress with tighter limits
            for i, (chunk, limit) in enumerate(zip(compressed_results, allocated_chars)):
                text = chunk.get("text", "")
                if len(text) > limit:
                    new_text = self.compress_text(text, keywords, limit)
                    if not chunk.get("full_text") and self.config.preserve_full_text:
                        chunk["full_text"] = text
                    chunk["text"] = new_text
                    chunk["compressed"] = True

        final_chars = sum(len(r.get("text", "")) for r in compressed_results)
        compression_ratio = final_chars / original_chars if original_chars > 0 else 1.0

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"Compressed {len(results)} chunks: {original_chars} -> {final_chars} chars "
            f"({compression_ratio:.1%}) in {duration_ms:.1f}ms"
        )

        return CompressionResult(
            results=compressed_results,
            original_chars=original_chars,
            compressed_chars=final_chars,
            chunks_compressed=chunks_compressed,
            chunks_unchanged=chunks_unchanged,
            chunks_empty=chunks_empty,
            compression_ratio=compression_ratio,
            duration_ms=duration_ms,
        )


@dataclass
class TokenBudgetManager:
    """
    Manages token budgets across multiple context sources.

    Helps allocate tokens between RAG results, graph context,
    and other context sources.
    """

    total_budget: int = 8000
    chars_per_token: float = 4.0

    # Allocation percentages
    rag_share: float = 0.6
    graph_share: float = 0.25
    reserved_share: float = 0.15  # For system prompts, etc.

    def get_rag_budget(self) -> Tuple[int, int]:
        """Get RAG budget in tokens and chars."""
        tokens = int(self.total_budget * self.rag_share)
        chars = int(tokens * self.chars_per_token)
        return tokens, chars

    def get_graph_budget(self) -> Tuple[int, int]:
        """Get graph context budget in tokens and chars."""
        tokens = int(self.total_budget * self.graph_share)
        chars = int(tokens * self.chars_per_token)
        return tokens, chars

    def get_reserved_budget(self) -> Tuple[int, int]:
        """Get reserved budget in tokens and chars."""
        tokens = int(self.total_budget * self.reserved_share)
        chars = int(tokens * self.chars_per_token)
        return tokens, chars

    def allocate(
        self,
        rag_chars: int,
        graph_chars: int,
    ) -> Tuple[int, int]:
        """
        Allocate budgets dynamically based on actual content.

        If one source is under budget, the other can use the surplus.

        Returns:
            (rag_budget_chars, graph_budget_chars)
        """
        total_chars = int((self.total_budget - self.total_budget * self.reserved_share) * self.chars_per_token)

        # Start with default allocations
        rag_budget, _ = self.get_rag_budget()
        graph_budget, _ = self.get_graph_budget()
        rag_budget_chars = int(rag_budget * self.chars_per_token)
        graph_budget_chars = int(graph_budget * self.chars_per_token)

        # Reallocate if one is under
        if rag_chars < rag_budget_chars:
            surplus = rag_budget_chars - rag_chars
            graph_budget_chars = min(graph_chars, graph_budget_chars + surplus)
        elif graph_chars < graph_budget_chars:
            surplus = graph_budget_chars - graph_chars
            rag_budget_chars = min(rag_chars, rag_budget_chars + surplus)

        return rag_budget_chars, graph_budget_chars

    @classmethod
    def from_env(cls) -> "TokenBudgetManager":
        """Load configuration from environment variables."""
        return cls(
            total_budget=int(os.getenv("CONTEXT_TOKEN_BUDGET", "8000")),
            chars_per_token=float(os.getenv("CONTEXT_CHARS_PER_TOKEN", "4.0")),
            rag_share=float(os.getenv("CONTEXT_RAG_SHARE", "0.6")),
            graph_share=float(os.getenv("CONTEXT_GRAPH_SHARE", "0.25")),
            reserved_share=float(os.getenv("CONTEXT_RESERVED_SHARE", "0.15")),
        )


# Convenience function for simple usage
def compress_context(
    query: str,
    results: List[Dict[str, Any]],
    max_chars_per_chunk: Optional[int] = None,
    token_budget: Optional[int] = None,
    config: Optional[CompressionConfig] = None,
) -> List[Dict[str, Any]]:
    """
    Convenience function to compress retrieval results.

    Args:
        query: The search query
        results: List of retrieval results
        max_chars_per_chunk: Maximum characters per chunk
        token_budget: Total token budget
        config: Optional compression configuration

    Returns:
        Compressed list of results
    """
    compressor = ContextCompressor(config)
    result = compressor.compress_results(query, results, max_chars_per_chunk, token_budget)
    return result.results
