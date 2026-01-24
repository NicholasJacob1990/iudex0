"""
Hybrid Router - Routes queries using rules first, LLM only for ambiguous cases.

This router minimizes LLM calls by using pattern matching and heuristics first.
Only falls back to LLM when confidence is low.
"""

import re
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    """Query intent classification."""
    LEXICAL = "lexical"          # Legal citations, article numbers, law references
    SEMANTIC = "semantic"        # Conceptual questions, explanations
    COMPARISON = "comparison"    # Compare X vs Y
    DEEP_RESEARCH = "deep_research"  # Complex multi-step research
    OPEN_ENDED = "open_ended"    # Strategy, recommendation questions
    UNKNOWN = "unknown"          # Ambiguous - needs LLM


class RetrievalStrategy(Enum):
    """Which retrieval strategy to use."""
    VECTOR_FIRST = "vector_first"      # Semantic search primary
    GRAPH_FIRST = "graph_first"        # Neo4j/Graph primary
    HYBRID_RRF = "hybrid_rrf"          # Combine both with RRF
    MULTI_QUERY = "multi_query"        # Generate multiple query variations
    ITERATIVE = "iterative"            # Multiple rounds of retrieval


@dataclass
class RoutingDecision:
    """Result of routing decision."""
    intent: QueryIntent
    strategy: RetrievalStrategy
    confidence: float  # 0.0 to 1.0
    requires_agentic: bool = False  # Needs multi-step orchestration
    sub_queries: List[str] = field(default_factory=list)  # For comparison/research
    reasoning: str = ""
    used_llm: bool = False


class HybridRouter:
    """
    Routes queries using rules first, LLM fallback for ambiguous cases.

    Flow:
    1. Pattern matching (fast, no LLM)
    2. Heuristic scoring
    3. If confidence < threshold → LLM routing
    """

    # Legal citation patterns (Portuguese/Brazilian)
    LEXICAL_PATTERNS = [
        r"\b[Aa]rt(?:igo)?\.?\s*\d+",                    # Art. 5, Artigo 37
        r"\b[Ll]ei\s+(?:n[ºo°]?\s*)?\d+[\d.]*/?(?:\d{2,4})?",  # Lei 8.666/93
        r"\b[Ss]úmula\s+(?:[Vv]inculante\s+)?\d+",       # Súmula 331, Súmula Vinculante 13
        r"\b[Tt]ema\s+\d+",                              # Tema 1234
        r"\b(?:STF|STJ|TST|TSE|TRF|TRT|TJ)\b",           # Tribunals
        r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}",         # CNJ process number
        r"\b[Cc]ódigo\s+(?:Civil|Penal|Tributário|Processo)",  # Códigos
        r"\b[Cc]onstituição\s+[Ff]ederal",               # CF
        r"\bCF/?88\b",                                    # CF/88
        r"\bCLT\b",                                       # CLT
        r"\bCPC\b",                                       # CPC
        r"\bCTN\b",                                       # CTN
        r"\bOAB/?[A-Z]{2}\s*\d+",                        # OAB/SP 123456
    ]

    # Comparison patterns
    COMPARISON_PATTERNS = [
        r"\bcompar[ae]\b",                               # compare, compara
        r"\bdiferença\s+entre\b",                        # diferença entre
        r"\bversus\b|\bvs\.?\b|\bx\b",                   # versus, vs, x
        r"\b(?:STF|STJ|TST).+(?:STF|STJ|TST)\b",         # STF...STJ (tribunal comparison)
        r"\bcontrast[ae]\b",                             # contraste, contrasta
        r"\bdisting[ue]\b",                              # distingue, distinga
    ]

    # Deep research patterns
    DEEP_RESEARCH_PATTERNS = [
        r"\bpesquis[ae]\s+(?:profunda|completa|detalhada)\b",
        r"\banális[ei]s?\s+(?:completa|detalhada|aprofundada)\b",
        r"\bestudo\s+(?:completo|detalhado)\b",
        r"\blevantamento\b",
        r"\bmapeamento\b",
        r"\brevisão\s+(?:bibliográfica|doutrinária|jurisprudencial)\b",
        r"\bevolução\s+(?:histórica|jurisprudencial)\b",
        r"\btese\s+(?:de|para)\b",
    ]

    # Open-ended patterns
    OPEN_ENDED_PATTERNS = [
        r"\bqual\s+(?:a\s+)?melhor\s+(?:estratégia|abordagem|forma)\b",
        r"\bcomo\s+(?:devo|posso|devemos)\b",
        r"\bo\s+que\s+(?:você\s+)?recomenda\b",
        r"\bqual\s+(?:sua\s+)?(?:opinião|sugestão)\b",
        r"\bquais\s+(?:as\s+)?(?:opções|alternativas|possibilidades)\b",
        r"\bme\s+ajud[ae]\s+a\b",
        r"\bpreciso\s+de\s+(?:ajuda|orientação)\b",
    ]

    def __init__(
        self,
        confidence_threshold: float = 0.6,
        enable_llm_fallback: bool = True,
        llm_provider: str = "gemini",
        llm_model: str = "gemini-2.0-flash",
    ):
        self.confidence_threshold = confidence_threshold
        self.enable_llm_fallback = enable_llm_fallback
        self.llm_provider = llm_provider
        self.llm_model = llm_model

        # Compile patterns for efficiency
        self._lexical_re = [re.compile(p, re.IGNORECASE) for p in self.LEXICAL_PATTERNS]
        self._comparison_re = [re.compile(p, re.IGNORECASE) for p in self.COMPARISON_PATTERNS]
        self._deep_research_re = [re.compile(p, re.IGNORECASE) for p in self.DEEP_RESEARCH_PATTERNS]
        self._open_ended_re = [re.compile(p, re.IGNORECASE) for p in self.OPEN_ENDED_PATTERNS]

    def route(self, query: str, context: Optional[Dict[str, Any]] = None) -> RoutingDecision:
        """
        Route a query to the appropriate retrieval strategy.

        Args:
            query: The user's query
            context: Optional context (case_id, previous queries, etc.)

        Returns:
            RoutingDecision with intent, strategy, and confidence
        """
        # Step 1: Pattern-based classification
        scores = self._compute_pattern_scores(query)

        # Step 2: Determine intent and confidence
        intent, confidence = self._determine_intent(scores)

        # Step 3: If low confidence and LLM enabled, use LLM
        used_llm = False
        if confidence < self.confidence_threshold and self.enable_llm_fallback:
            llm_result = self._llm_route(query, context)
            if llm_result:
                intent = llm_result["intent"]
                confidence = llm_result["confidence"]
                used_llm = True

        # Step 4: Determine strategy based on intent
        strategy = self._intent_to_strategy(intent)

        # Step 5: Check if agentic orchestration is needed
        requires_agentic = intent in [
            QueryIntent.DEEP_RESEARCH,
            QueryIntent.COMPARISON,
            QueryIntent.OPEN_ENDED,
        ]

        # Step 6: Generate sub-queries for complex cases
        sub_queries = []
        if requires_agentic and intent == QueryIntent.COMPARISON:
            sub_queries = self._extract_comparison_parts(query)

        reasoning = self._generate_reasoning(intent, scores, used_llm)

        return RoutingDecision(
            intent=intent,
            strategy=strategy,
            confidence=confidence,
            requires_agentic=requires_agentic,
            sub_queries=sub_queries,
            reasoning=reasoning,
            used_llm=used_llm,
        )

    def _compute_pattern_scores(self, query: str) -> Dict[str, float]:
        """Compute pattern match scores for each intent type."""
        scores = {
            "lexical": 0.0,
            "comparison": 0.0,
            "deep_research": 0.0,
            "open_ended": 0.0,
        }

        # Count matches for each pattern type
        lexical_matches = sum(1 for p in self._lexical_re if p.search(query))
        comparison_matches = sum(1 for p in self._comparison_re if p.search(query))
        deep_research_matches = sum(1 for p in self._deep_research_re if p.search(query))
        open_ended_matches = sum(1 for p in self._open_ended_re if p.search(query))

        # Normalize scores (more matches = higher confidence)
        scores["lexical"] = min(lexical_matches / 2.0, 1.0)  # 2+ matches = 1.0
        scores["comparison"] = min(comparison_matches / 1.5, 1.0)  # 1.5+ matches = 1.0
        scores["deep_research"] = min(deep_research_matches / 1.0, 1.0)  # 1 match = 1.0
        scores["open_ended"] = min(open_ended_matches / 1.0, 1.0)  # 1 match = 1.0

        return scores

    def _determine_intent(self, scores: Dict[str, float]) -> Tuple[QueryIntent, float]:
        """Determine intent from scores."""
        # Priority: comparison > deep_research > open_ended > lexical > semantic

        if scores["comparison"] >= 0.7:
            return QueryIntent.COMPARISON, scores["comparison"]

        if scores["deep_research"] >= 0.7:
            return QueryIntent.DEEP_RESEARCH, scores["deep_research"]

        if scores["open_ended"] >= 0.7:
            return QueryIntent.OPEN_ENDED, scores["open_ended"]

        if scores["lexical"] >= 0.5:
            return QueryIntent.LEXICAL, scores["lexical"]

        # Check if any score is moderate
        max_score = max(scores.values())
        if max_score >= 0.3:
            # Return the highest scoring intent
            max_key = max(scores, key=scores.get)
            intent_map = {
                "lexical": QueryIntent.LEXICAL,
                "comparison": QueryIntent.COMPARISON,
                "deep_research": QueryIntent.DEEP_RESEARCH,
                "open_ended": QueryIntent.OPEN_ENDED,
            }
            return intent_map[max_key], max_score

        # Default to semantic if nothing matches
        if max_score < 0.2:
            return QueryIntent.SEMANTIC, 0.8  # High confidence it's semantic

        return QueryIntent.UNKNOWN, max_score

    def _intent_to_strategy(self, intent: QueryIntent) -> RetrievalStrategy:
        """Map intent to retrieval strategy."""
        strategy_map = {
            QueryIntent.LEXICAL: RetrievalStrategy.GRAPH_FIRST,
            QueryIntent.SEMANTIC: RetrievalStrategy.VECTOR_FIRST,
            QueryIntent.COMPARISON: RetrievalStrategy.MULTI_QUERY,
            QueryIntent.DEEP_RESEARCH: RetrievalStrategy.ITERATIVE,
            QueryIntent.OPEN_ENDED: RetrievalStrategy.HYBRID_RRF,
            QueryIntent.UNKNOWN: RetrievalStrategy.HYBRID_RRF,
        }
        return strategy_map.get(intent, RetrievalStrategy.HYBRID_RRF)

    def _extract_comparison_parts(self, query: str) -> List[str]:
        """Extract the parts being compared from a comparison query."""
        sub_queries = []

        # Try to find "X vs Y" or "X versus Y" or "X x Y"
        vs_pattern = re.compile(
            r"(.+?)\s+(?:versus|vs\.?|x)\s+(.+?)(?:\s+sobre|\s+em|\s+no|\s+na|\?|$)",
            re.IGNORECASE
        )
        match = vs_pattern.search(query)
        if match:
            part1, part2 = match.groups()
            # Extract topic if present
            topic_match = re.search(r"sobre\s+(.+?)(?:\?|$)", query, re.IGNORECASE)
            topic = topic_match.group(1).strip() if topic_match else ""

            if topic:
                sub_queries.append(f"{part1.strip()} {topic}")
                sub_queries.append(f"{part2.strip()} {topic}")
            else:
                sub_queries.append(part1.strip())
                sub_queries.append(part2.strip())

        # Try "diferença entre X e Y"
        diff_pattern = re.compile(
            r"diferença\s+entre\s+(.+?)\s+e\s+(.+?)(?:\s+sobre|\s+em|\s+no|\s+na|\?|$)",
            re.IGNORECASE
        )
        match = diff_pattern.search(query)
        if match and not sub_queries:
            part1, part2 = match.groups()
            sub_queries.append(part1.strip())
            sub_queries.append(part2.strip())

        return sub_queries

    def _llm_route(self, query: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Use LLM to classify ambiguous queries."""
        try:
            from ...ai.model_registry import get_model_client

            prompt = f"""Classifique a query jurídica abaixo em uma das categorias:

1. LEXICAL - Referência a artigos, leis, súmulas, processos específicos
2. SEMANTIC - Pergunta conceitual, explicação de termos
3. COMPARISON - Comparação entre tribunais, teses, jurisprudências
4. DEEP_RESEARCH - Pesquisa complexa que exige análise aprofundada
5. OPEN_ENDED - Pergunta sobre estratégia, recomendação, "melhor forma de..."

Query: "{query}"

Responda APENAS com JSON:
{{"intent": "CATEGORIA", "confidence": 0.0-1.0, "reasoning": "breve justificativa"}}"""

            client = get_model_client(self.llm_provider)
            response = client.generate(
                prompt=prompt,
                model=self.llm_model,
                max_tokens=150,
                temperature=0.0,
            )

            # Parse JSON response
            import json
            # Extract JSON from response
            text = response.get("content", response.get("text", ""))
            # Try to find JSON in response
            json_match = re.search(r'\{[^}]+\}', text)
            if json_match:
                result = json.loads(json_match.group())
                intent_str = result.get("intent", "UNKNOWN").upper()
                intent_map = {
                    "LEXICAL": QueryIntent.LEXICAL,
                    "SEMANTIC": QueryIntent.SEMANTIC,
                    "COMPARISON": QueryIntent.COMPARISON,
                    "DEEP_RESEARCH": QueryIntent.DEEP_RESEARCH,
                    "OPEN_ENDED": QueryIntent.OPEN_ENDED,
                }
                return {
                    "intent": intent_map.get(intent_str, QueryIntent.UNKNOWN),
                    "confidence": float(result.get("confidence", 0.7)),
                }
        except Exception as e:
            logger.warning(f"LLM routing failed: {e}")
            return None

        return None

    def _generate_reasoning(
        self,
        intent: QueryIntent,
        scores: Dict[str, float],
        used_llm: bool
    ) -> str:
        """Generate human-readable reasoning for the routing decision."""
        parts = []

        if used_llm:
            parts.append("Classificado via LLM (padrões ambíguos)")
        else:
            parts.append("Classificado via regras")

        if scores["lexical"] > 0:
            parts.append(f"citações legais detectadas (score={scores['lexical']:.2f})")
        if scores["comparison"] > 0:
            parts.append(f"padrão de comparação (score={scores['comparison']:.2f})")
        if scores["deep_research"] > 0:
            parts.append(f"indicadores de pesquisa profunda (score={scores['deep_research']:.2f})")
        if scores["open_ended"] > 0:
            parts.append(f"pergunta aberta/estratégica (score={scores['open_ended']:.2f})")

        return "; ".join(parts)


# Singleton instance
_router_instance: Optional[HybridRouter] = None


def get_hybrid_router(
    confidence_threshold: float = 0.6,
    enable_llm_fallback: bool = True,
) -> HybridRouter:
    """Get or create the hybrid router singleton."""
    global _router_instance
    if _router_instance is None:
        _router_instance = HybridRouter(
            confidence_threshold=confidence_threshold,
            enable_llm_fallback=enable_llm_fallback,
        )
    return _router_instance


def reset_hybrid_router():
    """Reset the router singleton (for testing)."""
    global _router_instance
    _router_instance = None
