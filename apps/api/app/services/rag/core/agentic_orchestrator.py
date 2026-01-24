"""
Agentic RAG Orchestrator - Multi-step orchestration for complex queries.

Handles three scenarios:
1. Deep Research - Iterative refinement with multiple retrieval rounds
2. Open-ended Questions - Strategy/recommendation with multiple perspectives
3. Cross-reference/Comparison - Parallel retrieval and synthesis
"""

import asyncio
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, AsyncGenerator
from datetime import datetime

logger = logging.getLogger(__name__)


class OrchestrationMode(Enum):
    """Type of orchestration to perform."""
    DEEP_RESEARCH = "deep_research"
    OPEN_ENDED = "open_ended"
    COMPARISON = "comparison"


class ResearchPhase(Enum):
    """Phases of deep research."""
    INITIAL_SEARCH = "initial_search"
    GAP_ANALYSIS = "gap_analysis"
    TARGETED_SEARCH = "targeted_search"
    SYNTHESIS = "synthesis"
    VALIDATION = "validation"


@dataclass
class ResearchStep:
    """A single step in the research process."""
    phase: ResearchPhase
    query: str
    results: List[Dict[str, Any]] = field(default_factory=list)
    gaps_identified: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    tokens_used: int = 0


@dataclass
class OrchestrationResult:
    """Result of agentic orchestration."""
    mode: OrchestrationMode
    original_query: str
    steps: List[ResearchStep] = field(default_factory=list)
    final_context: str = ""
    sources: List[Dict[str, Any]] = field(default_factory=list)
    comparison_table: Optional[Dict[str, Any]] = None  # For comparison mode
    recommendations: List[str] = field(default_factory=list)  # For open-ended
    total_iterations: int = 0
    total_tokens: int = 0
    duration_ms: int = 0


class AgenticOrchestrator:
    """
    Orchestrates complex multi-step RAG queries.

    Unlike simple RAG which does one retrieval, this orchestrator:
    - Analyzes gaps in retrieved information
    - Performs targeted follow-up searches
    - Synthesizes information from multiple sources
    - Handles parallel retrieval for comparisons
    """

    def __init__(
        self,
        retriever_fn: Callable,
        llm_fn: Callable,
        max_iterations: int = 5,
        min_confidence: float = 0.7,
        enable_streaming: bool = True,
    ):
        """
        Args:
            retriever_fn: Function to retrieve documents (query, top_k) -> List[Dict]
            llm_fn: Function to call LLM (prompt, max_tokens) -> str
            max_iterations: Maximum research iterations
            min_confidence: Minimum confidence to stop iterating
            enable_streaming: Enable streaming progress updates
        """
        self.retriever_fn = retriever_fn
        self.llm_fn = llm_fn
        self.max_iterations = max_iterations
        self.min_confidence = min_confidence
        self.enable_streaming = enable_streaming

    async def orchestrate(
        self,
        query: str,
        mode: OrchestrationMode,
        sub_queries: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> OrchestrationResult:
        """
        Main orchestration entry point.

        Args:
            query: Original user query
            mode: Type of orchestration (deep_research, open_ended, comparison)
            sub_queries: Pre-extracted sub-queries (for comparison mode)
            context: Additional context (case_id, tenant_id, etc.)

        Returns:
            OrchestrationResult with all steps and final context
        """
        start_time = datetime.utcnow()

        if mode == OrchestrationMode.DEEP_RESEARCH:
            result = await self._deep_research(query, context)
        elif mode == OrchestrationMode.COMPARISON:
            result = await self._comparison_research(query, sub_queries or [], context)
        elif mode == OrchestrationMode.OPEN_ENDED:
            result = await self._open_ended_research(query, context)
        else:
            raise ValueError(f"Unknown orchestration mode: {mode}")

        # Calculate duration
        end_time = datetime.utcnow()
        result.duration_ms = int((end_time - start_time).total_seconds() * 1000)

        return result

    async def orchestrate_stream(
        self,
        query: str,
        mode: OrchestrationMode,
        sub_queries: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Streaming version of orchestrate that yields progress updates.

        Yields:
            Dict with 'type' (phase, result, gap, synthesis) and 'data'
        """
        start_time = datetime.utcnow()

        if mode == OrchestrationMode.DEEP_RESEARCH:
            async for update in self._deep_research_stream(query, context):
                yield update
        elif mode == OrchestrationMode.COMPARISON:
            async for update in self._comparison_research_stream(query, sub_queries or [], context):
                yield update
        elif mode == OrchestrationMode.OPEN_ENDED:
            async for update in self._open_ended_research_stream(query, context):
                yield update

        end_time = datetime.utcnow()
        yield {
            "type": "complete",
            "duration_ms": int((end_time - start_time).total_seconds() * 1000),
        }

    # =========================================================================
    # DEEP RESEARCH MODE
    # =========================================================================

    async def _deep_research(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> OrchestrationResult:
        """
        Deep research with iterative refinement.

        Flow:
        1. Initial broad search
        2. Analyze gaps in retrieved information
        3. Targeted searches to fill gaps
        4. Repeat until confident or max iterations
        5. Synthesize final context
        """
        result = OrchestrationResult(
            mode=OrchestrationMode.DEEP_RESEARCH,
            original_query=query,
        )

        all_sources = []
        iteration = 0
        confidence = 0.0
        current_query = query

        while iteration < self.max_iterations and confidence < self.min_confidence:
            iteration += 1

            # Phase 1: Search
            phase = ResearchPhase.INITIAL_SEARCH if iteration == 1 else ResearchPhase.TARGETED_SEARCH
            step = ResearchStep(phase=phase, query=current_query)

            # Retrieve documents
            docs = await self._retrieve(current_query, top_k=10, context=context)
            step.results = docs
            all_sources.extend(docs)

            # Phase 2: Gap analysis
            if iteration < self.max_iterations:
                gaps, confidence = await self._analyze_gaps(query, docs, all_sources)
                step.gaps_identified = gaps

                if gaps and confidence < self.min_confidence:
                    # Generate targeted query for the most important gap
                    current_query = await self._generate_targeted_query(query, gaps[0])

            result.steps.append(step)
            result.total_tokens += step.tokens_used

        # Phase 3: Synthesis
        result.final_context = await self._synthesize_context(query, all_sources)
        result.sources = self._deduplicate_sources(all_sources)
        result.total_iterations = iteration

        return result

    async def _deep_research_stream(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Streaming version of deep research."""
        all_sources = []
        iteration = 0
        confidence = 0.0
        current_query = query

        while iteration < self.max_iterations and confidence < self.min_confidence:
            iteration += 1

            yield {
                "type": "phase",
                "phase": "searching",
                "iteration": iteration,
                "query": current_query,
            }

            # Retrieve documents
            docs = await self._retrieve(current_query, top_k=10, context=context)
            all_sources.extend(docs)

            yield {
                "type": "results",
                "count": len(docs),
                "sources": [d.get("metadata", {}).get("source", "unknown") for d in docs[:5]],
            }

            # Gap analysis
            if iteration < self.max_iterations:
                yield {"type": "phase", "phase": "analyzing_gaps"}

                gaps, confidence = await self._analyze_gaps(query, docs, all_sources)

                yield {
                    "type": "gaps",
                    "gaps": gaps,
                    "confidence": confidence,
                }

                if gaps and confidence < self.min_confidence:
                    current_query = await self._generate_targeted_query(query, gaps[0])

        # Synthesis
        yield {"type": "phase", "phase": "synthesizing"}
        final_context = await self._synthesize_context(query, all_sources)

        yield {
            "type": "synthesis",
            "context": final_context,
            "total_sources": len(self._deduplicate_sources(all_sources)),
        }

    async def _analyze_gaps(
        self,
        original_query: str,
        recent_docs: List[Dict[str, Any]],
        all_docs: List[Dict[str, Any]],
    ) -> tuple[List[str], float]:
        """
        Analyze what information is still missing.

        Returns:
            Tuple of (gaps list, confidence score)
        """
        # Combine document texts
        doc_texts = "\n---\n".join([
            d.get("text", d.get("content", ""))[:500]
            for d in recent_docs[:5]
        ])

        prompt = f"""Analise se os documentos recuperados respondem completamente à pergunta.

Pergunta original: {original_query}

Documentos recuperados (resumo):
{doc_texts}

Identifique LACUNAS - informações importantes que ainda faltam para responder completamente.

Responda em JSON:
{{
  "gaps": ["lacuna 1", "lacuna 2"],
  "confidence": 0.0-1.0,
  "reasoning": "breve justificativa"
}}

Se não houver lacunas significativas, retorne gaps vazio e confidence alta."""

        try:
            response = await self._call_llm(prompt, max_tokens=300)

            import json
            import re
            json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return result.get("gaps", []), float(result.get("confidence", 0.5))
        except Exception as e:
            logger.warning(f"Gap analysis failed: {e}")

        return [], 0.5

    async def _generate_targeted_query(self, original_query: str, gap: str) -> str:
        """Generate a targeted query to fill a specific gap."""
        prompt = f"""Gere uma query de busca específica para preencher esta lacuna de informação.

Pergunta original: {original_query}
Lacuna identificada: {gap}

Gere APENAS a query de busca (sem explicações):"""

        try:
            response = await self._call_llm(prompt, max_tokens=100)
            return response.strip().strip('"')
        except Exception as e:
            logger.warning(f"Targeted query generation failed: {e}")
            return f"{original_query} {gap}"

    # =========================================================================
    # COMPARISON MODE
    # =========================================================================

    async def _comparison_research(
        self,
        query: str,
        sub_queries: List[str],
        context: Optional[Dict[str, Any]] = None,
    ) -> OrchestrationResult:
        """
        Parallel retrieval for comparison queries.

        Flow:
        1. Search each sub-query in parallel
        2. Extract key points from each
        3. Build comparison table
        4. Synthesize unified analysis
        """
        result = OrchestrationResult(
            mode=OrchestrationMode.COMPARISON,
            original_query=query,
        )

        if len(sub_queries) < 2:
            # Extract sub-queries from the original query
            sub_queries = await self._extract_comparison_parts(query)

        if len(sub_queries) < 2:
            # Fallback to single search
            sub_queries = [query]

        # Parallel search for each sub-query
        search_tasks = [
            self._retrieve(sq, top_k=8, context=context)
            for sq in sub_queries
        ]
        search_results = await asyncio.gather(*search_tasks)

        # Create steps for each sub-query
        all_sources = []
        comparison_data = {}

        for sq, docs in zip(sub_queries, search_results):
            step = ResearchStep(
                phase=ResearchPhase.INITIAL_SEARCH,
                query=sq,
                results=docs,
            )
            result.steps.append(step)
            all_sources.extend(docs)

            # Extract key points for this side of comparison
            key_points = await self._extract_key_points(sq, docs)
            comparison_data[sq] = key_points

        # Build comparison table
        result.comparison_table = await self._build_comparison_table(
            query, sub_queries, comparison_data
        )

        # Synthesize
        result.final_context = await self._synthesize_comparison(
            query, sub_queries, comparison_data
        )
        result.sources = self._deduplicate_sources(all_sources)
        result.total_iterations = 1

        return result

    async def _comparison_research_stream(
        self,
        query: str,
        sub_queries: List[str],
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Streaming version of comparison research."""
        if len(sub_queries) < 2:
            sub_queries = await self._extract_comparison_parts(query)

        yield {
            "type": "phase",
            "phase": "parallel_search",
            "sub_queries": sub_queries,
        }

        # Parallel search
        all_sources = []
        comparison_data = {}

        for sq in sub_queries:
            yield {"type": "searching", "query": sq}

            docs = await self._retrieve(sq, top_k=8, context=context)
            all_sources.extend(docs)

            yield {
                "type": "results",
                "query": sq,
                "count": len(docs),
            }

            key_points = await self._extract_key_points(sq, docs)
            comparison_data[sq] = key_points

            yield {
                "type": "key_points",
                "query": sq,
                "points": key_points[:3],  # First 3 points
            }

        yield {"type": "phase", "phase": "building_comparison"}

        comparison_table = await self._build_comparison_table(
            query, sub_queries, comparison_data
        )

        yield {
            "type": "comparison_table",
            "table": comparison_table,
        }

        yield {"type": "phase", "phase": "synthesizing"}

        final_context = await self._synthesize_comparison(
            query, sub_queries, comparison_data
        )

        yield {
            "type": "synthesis",
            "context": final_context,
        }

    async def _extract_comparison_parts(self, query: str) -> List[str]:
        """Extract comparison parts using LLM."""
        prompt = f"""Extraia as duas partes sendo comparadas nesta query.

Query: {query}

Responda em JSON:
{{"parts": ["parte 1", "parte 2"]}}"""

        try:
            response = await self._call_llm(prompt, max_tokens=100)
            import json
            import re
            json_match = re.search(r'\{[^}]+\}', response)
            if json_match:
                result = json.loads(json_match.group())
                return result.get("parts", [])
        except Exception as e:
            logger.warning(f"Comparison extraction failed: {e}")

        return [query]

    async def _extract_key_points(
        self,
        query: str,
        docs: List[Dict[str, Any]],
    ) -> List[str]:
        """Extract key points from documents for comparison."""
        doc_texts = "\n---\n".join([
            d.get("text", d.get("content", ""))[:400]
            for d in docs[:5]
        ])

        prompt = f"""Extraia os pontos-chave dos documentos sobre: {query}

Documentos:
{doc_texts}

Liste até 5 pontos-chave, um por linha:"""

        try:
            response = await self._call_llm(prompt, max_tokens=300)
            points = [p.strip().lstrip("-•") for p in response.strip().split("\n") if p.strip()]
            return points[:5]
        except Exception as e:
            logger.warning(f"Key points extraction failed: {e}")
            return []

    async def _build_comparison_table(
        self,
        query: str,
        sub_queries: List[str],
        comparison_data: Dict[str, List[str]],
    ) -> Dict[str, Any]:
        """Build a structured comparison table."""
        table = {
            "headers": sub_queries,
            "rows": [],
            "summary": "",
        }

        # Find common aspects to compare
        all_points = []
        for points in comparison_data.values():
            all_points.extend(points)

        prompt = f"""Com base nos pontos abaixo, identifique 3-5 aspectos para comparar.

Query: {query}

Pontos de cada lado:
{comparison_data}

Liste aspectos para comparar (ex: "Entendimento sobre X", "Requisitos para Y"):"""

        try:
            response = await self._call_llm(prompt, max_tokens=200)
            aspects = [a.strip().lstrip("-•1234567890.") for a in response.strip().split("\n") if a.strip()]

            for aspect in aspects[:5]:
                row = {"aspect": aspect, "values": {}}
                for sq in sub_queries:
                    # Find relevant point for this aspect
                    relevant = next(
                        (p for p in comparison_data.get(sq, []) if aspect.lower() in p.lower()),
                        "Não especificado"
                    )
                    row["values"][sq] = relevant
                table["rows"].append(row)
        except Exception as e:
            logger.warning(f"Comparison table building failed: {e}")

        return table

    async def _synthesize_comparison(
        self,
        query: str,
        sub_queries: List[str],
        comparison_data: Dict[str, List[str]],
    ) -> str:
        """Synthesize a unified comparison analysis."""
        data_str = "\n\n".join([
            f"**{sq}:**\n" + "\n".join(f"- {p}" for p in points)
            for sq, points in comparison_data.items()
        ])

        prompt = f"""Sintetize uma análise comparativa respondendo à pergunta.

Pergunta: {query}

Dados coletados:
{data_str}

Escreva uma análise comparativa clara e objetiva, destacando:
1. Principais diferenças
2. Pontos em comum
3. Conclusão/Recomendação"""

        try:
            return await self._call_llm(prompt, max_tokens=800)
        except Exception as e:
            logger.warning(f"Comparison synthesis failed: {e}")
            return f"Dados comparativos:\n{data_str}"

    # =========================================================================
    # OPEN-ENDED MODE
    # =========================================================================

    async def _open_ended_research(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> OrchestrationResult:
        """
        Handle open-ended strategy/recommendation questions.

        Flow:
        1. Decompose into sub-questions
        2. Search for each perspective
        3. Generate recommendations
        4. Synthesize with pros/cons
        """
        result = OrchestrationResult(
            mode=OrchestrationMode.OPEN_ENDED,
            original_query=query,
        )

        # Decompose the question
        perspectives = await self._decompose_open_question(query)

        all_sources = []

        # Search for each perspective
        for perspective in perspectives[:4]:  # Max 4 perspectives
            step = ResearchStep(
                phase=ResearchPhase.INITIAL_SEARCH,
                query=perspective,
            )
            docs = await self._retrieve(perspective, top_k=6, context=context)
            step.results = docs
            all_sources.extend(docs)
            result.steps.append(step)

        # Generate recommendations
        result.recommendations = await self._generate_recommendations(
            query, perspectives, all_sources
        )

        # Synthesize
        result.final_context = await self._synthesize_open_ended(
            query, perspectives, all_sources, result.recommendations
        )
        result.sources = self._deduplicate_sources(all_sources)
        result.total_iterations = len(perspectives)

        return result

    async def _open_ended_research_stream(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Streaming version of open-ended research."""
        yield {"type": "phase", "phase": "decomposing"}

        perspectives = await self._decompose_open_question(query)

        yield {
            "type": "perspectives",
            "perspectives": perspectives,
        }

        all_sources = []

        for perspective in perspectives[:4]:
            yield {"type": "searching", "perspective": perspective}

            docs = await self._retrieve(perspective, top_k=6, context=context)
            all_sources.extend(docs)

            yield {
                "type": "results",
                "perspective": perspective,
                "count": len(docs),
            }

        yield {"type": "phase", "phase": "generating_recommendations"}

        recommendations = await self._generate_recommendations(
            query, perspectives, all_sources
        )

        yield {
            "type": "recommendations",
            "recommendations": recommendations,
        }

        yield {"type": "phase", "phase": "synthesizing"}

        final_context = await self._synthesize_open_ended(
            query, perspectives, all_sources, recommendations
        )

        yield {
            "type": "synthesis",
            "context": final_context,
        }

    async def _decompose_open_question(self, query: str) -> List[str]:
        """Decompose an open-ended question into searchable perspectives."""
        prompt = f"""Decomponha esta pergunta aberta em sub-perguntas pesquisáveis.

Pergunta: {query}

Gere 3-4 perspectivas/ângulos para pesquisar. Uma por linha:"""

        try:
            response = await self._call_llm(prompt, max_tokens=200)
            perspectives = [
                p.strip().lstrip("-•1234567890.")
                for p in response.strip().split("\n")
                if p.strip()
            ]
            return perspectives[:4]
        except Exception as e:
            logger.warning(f"Question decomposition failed: {e}")
            return [query]

    async def _generate_recommendations(
        self,
        query: str,
        perspectives: List[str],
        docs: List[Dict[str, Any]],
    ) -> List[str]:
        """Generate actionable recommendations."""
        doc_texts = "\n---\n".join([
            d.get("text", d.get("content", ""))[:300]
            for d in docs[:8]
        ])

        prompt = f"""Com base nas informações coletadas, gere recomendações práticas.

Pergunta: {query}
Perspectivas analisadas: {perspectives}

Informações:
{doc_texts}

Gere 3-5 recomendações práticas e acionáveis, uma por linha:"""

        try:
            response = await self._call_llm(prompt, max_tokens=400)
            recommendations = [
                r.strip().lstrip("-•1234567890.")
                for r in response.strip().split("\n")
                if r.strip()
            ]
            return recommendations[:5]
        except Exception as e:
            logger.warning(f"Recommendations generation failed: {e}")
            return []

    async def _synthesize_open_ended(
        self,
        query: str,
        perspectives: List[str],
        docs: List[Dict[str, Any]],
        recommendations: List[str],
    ) -> str:
        """Synthesize open-ended analysis with recommendations."""
        doc_summary = "\n".join([
            f"- {d.get('text', d.get('content', ''))[:200]}..."
            for d in docs[:5]
        ])

        rec_str = "\n".join(f"- {r}" for r in recommendations)

        prompt = f"""Sintetize uma resposta completa para esta pergunta aberta.

Pergunta: {query}

Perspectivas consideradas:
{perspectives}

Base de conhecimento (resumo):
{doc_summary}

Recomendações geradas:
{rec_str}

Escreva uma resposta estruturada que:
1. Contextualize o problema
2. Apresente as opções/abordagens
3. Discuta prós e contras
4. Conclua com recomendação fundamentada"""

        try:
            return await self._call_llm(prompt, max_tokens=1000)
        except Exception as e:
            logger.warning(f"Open-ended synthesis failed: {e}")
            return f"Recomendações:\n{rec_str}"

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    async def _retrieve(
        self,
        query: str,
        top_k: int = 10,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve documents using the injected retriever function."""
        try:
            # Support both sync and async retrievers
            if asyncio.iscoroutinefunction(self.retriever_fn):
                return await self.retriever_fn(query, top_k, context)
            else:
                return self.retriever_fn(query, top_k, context)
        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            return []

    async def _call_llm(self, prompt: str, max_tokens: int = 500) -> str:
        """Call LLM using the injected function."""
        try:
            if asyncio.iscoroutinefunction(self.llm_fn):
                return await self.llm_fn(prompt, max_tokens)
            else:
                return self.llm_fn(prompt, max_tokens)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    async def _synthesize_context(
        self,
        query: str,
        docs: List[Dict[str, Any]],
    ) -> str:
        """Synthesize final context from all retrieved documents."""
        # Deduplicate and sort by relevance
        unique_docs = self._deduplicate_sources(docs)

        doc_texts = "\n\n---\n\n".join([
            f"[Fonte: {d.get('metadata', {}).get('source', 'desconhecida')}]\n{d.get('text', d.get('content', ''))}"
            for d in unique_docs[:10]
        ])

        prompt = f"""Sintetize as informações para responder à pergunta.

Pergunta: {query}

Documentos recuperados:
{doc_texts}

Escreva uma síntese coesa e completa, citando as fontes quando relevante:"""

        try:
            return await self._call_llm(prompt, max_tokens=1000)
        except Exception as e:
            logger.warning(f"Synthesis failed: {e}")
            return doc_texts

    def _deduplicate_sources(self, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate documents based on content hash."""
        seen = set()
        unique = []

        for doc in docs:
            content = doc.get("text", doc.get("content", ""))
            content_hash = hash(content[:200])  # Hash first 200 chars

            if content_hash not in seen:
                seen.add(content_hash)
                unique.append(doc)

        return unique
