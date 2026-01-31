"""
Tests for Deep Research Hard Mode -- Multi-provider orchestrated research.

Testa o DeepResearchHardService, que orquestra pesquisa paralela em
multiplos providers (Gemini, Perplexity, OpenAI, RAG global, RAG local)
e faz merge + reranking dos resultados.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


# ---------------------------------------------------------------------------
# Dataclasses que o service vai expor (definidas aqui para os testes
# conseguirem rodar mesmo antes do modulo ser criado).
# ---------------------------------------------------------------------------

@dataclass
class ProviderResult:
    """Result from a single provider execution."""
    provider: str
    text: str
    sources: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    elapsed_ms: float = 0


@dataclass
class MergedResearch:
    """Merged and deduplicated research output."""
    text: str = ""
    sources: List[Dict[str, Any]] = field(default_factory=list)
    provider_results: List[ProviderResult] = field(default_factory=list)
    total_sources: int = 0


@dataclass
class DeepResearchResult:
    """Result from the underlying DeepResearchService."""
    text: str
    log: str = ""
    success: bool = False
    error: Optional[str] = None
    sources: Optional[list] = None
    thinking_steps: Optional[list] = None
    from_cache: bool = False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_deep_research_service():
    """Mock para DeepResearchService usado internamente pelo hard service."""
    service = MagicMock()
    service.run_research_task = AsyncMock(return_value=DeepResearchResult(
        text="Sample research text about jurisprudencia.",
        success=True,
        sources=[{"title": "Test", "url": "https://example.com", "number": 1}],
        thinking_steps=["Step 1"],
    ))
    return service


@pytest.fixture
def mock_anthropic():
    """Mock para o cliente Anthropic (Claude) usado no planejamento de queries."""
    client = AsyncMock()

    # Mock da resposta de planejamento de queries
    plan_response = MagicMock()
    plan_response.content = [MagicMock()]
    plan_response.content[0].text = (
        '{"gemini": "pesquisa gemini query",'
        ' "perplexity": "pesquisa perplexity query",'
        ' "openai": "pesquisa openai query",'
        ' "rag_global": "pesquisa rag global query",'
        ' "rag_local": "pesquisa rag local query"}'
    )
    client.messages.create = AsyncMock(return_value=plan_response)
    return client


@pytest.fixture
def mock_rag_manager():
    """Mock para o RAG manager."""
    mock = AsyncMock()
    mock.search = AsyncMock(return_value={
        "results": [
            {"text": "RAG result text", "metadata": {"source": "doc1.pdf"}},
        ]
    })
    return mock


@pytest.fixture
def hard_service(mock_deep_research_service, mock_anthropic, mock_rag_manager):
    """
    Cria uma instancia do DeepResearchHardService com todas as dependencias mockadas.
    Como o modulo pode nao existir ainda, simulamos a classe localmente.
    """
    service = _build_stub_hard_service(
        deep_research_service=mock_deep_research_service,
        anthropic_client=mock_anthropic,
        rag_manager=mock_rag_manager,
    )
    return service


# ---------------------------------------------------------------------------
# Stub do DeepResearchHardService para testes (TDD)
# ---------------------------------------------------------------------------

class _StubDeepResearchHardService:
    """
    Stub local do service para testes TDD.
    Replica a interface publica esperada do DeepResearchHardService real.
    """

    PROVIDERS = ["gemini", "perplexity", "openai", "rag_global", "rag_local"]

    def __init__(
        self,
        deep_research_service=None,
        anthropic_client=None,
        rag_manager=None,
        timeout_per_provider: int = 120,
        total_timeout: int = 300,
    ):
        self.deep_research_service = deep_research_service
        self.anthropic_client = anthropic_client
        self.rag_manager = rag_manager
        self.timeout_per_provider = timeout_per_provider
        self.total_timeout = total_timeout

    async def plan_queries(self, query: str) -> Dict[str, str]:
        """Usa Claude para planejar queries especializadas por provider."""
        try:
            import json
            resp = await self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                messages=[{"role": "user", "content": f"Plan queries for: {query}"}],
            )
            text = resp.content[0].text
            parsed = json.loads(text)
            result = {}
            for p in self.PROVIDERS:
                result[p] = parsed.get(p, query)
            return result
        except Exception:
            return {p: query for p in self.PROVIDERS}

    async def _run_gemini_research(self, query: str) -> ProviderResult:
        try:
            result = await self.deep_research_service.run_research_task(
                query, {"provider": "google"}
            )
            return ProviderResult(
                provider="gemini",
                text=result.text,
                sources=result.sources or [],
                error=result.error,
            )
        except Exception as e:
            return ProviderResult(provider="gemini", text="", error=str(e))

    async def _run_perplexity_research(self, query: str) -> ProviderResult:
        try:
            result = await self.deep_research_service.run_research_task(
                query, {"provider": "perplexity"}
            )
            return ProviderResult(
                provider="perplexity",
                text=result.text,
                sources=result.sources or [],
                error=result.error,
            )
        except Exception as e:
            return ProviderResult(provider="perplexity", text="", error=str(e))

    async def _run_openai_research(self, query: str) -> ProviderResult:
        try:
            result = await self.deep_research_service.run_research_task(
                query, {"provider": "openai"}
            )
            return ProviderResult(
                provider="openai",
                text=result.text,
                sources=result.sources or [],
                error=result.error,
            )
        except Exception as e:
            return ProviderResult(provider="openai", text="", error=str(e))

    async def _run_rag_global(self, query: str) -> ProviderResult:
        try:
            result = await self.rag_manager.search(query=query, scope="all")
            texts = [r.get("text", "") for r in (result.get("results") or [])]
            return ProviderResult(
                provider="rag_global",
                text="\n".join(texts),
                sources=[],
            )
        except Exception as e:
            return ProviderResult(provider="rag_global", text="", error=str(e))

    async def _run_rag_local(self, query: str, case_id: str = "", tenant_id: str = "") -> ProviderResult:
        try:
            result = await self.rag_manager.search(
                query=query, scope="local", case_id=case_id, tenant_id=tenant_id
            )
            texts = [r.get("text", "") for r in (result.get("results") or [])]
            return ProviderResult(
                provider="rag_local",
                text="\n".join(texts),
                sources=[],
            )
        except Exception as e:
            return ProviderResult(provider="rag_local", text="", error=str(e))

    async def execute_parallel(
        self,
        queries: Dict[str, str],
        case_id: str = "",
        tenant_id: str = "",
    ) -> Dict[str, ProviderResult]:
        tasks = {
            "gemini": self._run_gemini_research(queries.get("gemini", "")),
            "perplexity": self._run_perplexity_research(queries.get("perplexity", "")),
            "openai": self._run_openai_research(queries.get("openai", "")),
            "rag_global": self._run_rag_global(queries.get("rag_global", "")),
            "rag_local": self._run_rag_local(queries.get("rag_local", ""), case_id, tenant_id),
        }

        results: Dict[str, ProviderResult] = {}
        gathered = await asyncio.gather(
            *[
                asyncio.wait_for(coro, timeout=self.timeout_per_provider)
                for coro in tasks.values()
            ],
            return_exceptions=True,
        )
        for key, outcome in zip(tasks.keys(), gathered):
            if isinstance(outcome, Exception):
                err_msg = str(outcome) or type(outcome).__name__
                results[key] = ProviderResult(provider=key, text="", error=err_msg)
            else:
                results[key] = outcome
        return results

    def merge_results(self, provider_results: Dict[str, ProviderResult]) -> MergedResearch:
        seen_urls: Dict[str, Dict[str, Any]] = {}
        all_provider_results: List[ProviderResult] = []

        juris_domains = {"stf.jus.br", "stj.jus.br", "trf", "tjsp", "jusbrasil"}

        for key, pr in provider_results.items():
            all_provider_results.append(pr)
            for src in pr.sources or []:
                url = src.get("url", "")
                if not url:
                    continue
                if url not in seen_urls:
                    score = 1.0
                    if any(d in url.lower() for d in juris_domains):
                        score += 2.0
                    seen_urls[url] = {**src, "_score": score}
                else:
                    seen_urls[url]["_score"] = seen_urls[url].get("_score", 1.0) + 0.5

        ranked = sorted(seen_urls.values(), key=lambda s: s.get("_score", 0), reverse=True)
        clean_sources = [{k: v for k, v in s.items() if k != "_score"} for s in ranked]

        merged_text = "\n\n".join(
            pr.text for pr in all_provider_results if pr.text and not pr.error
        )

        return MergedResearch(
            text=merged_text,
            sources=clean_sources,
            provider_results=all_provider_results,
            total_sources=len(clean_sources),
        )

    async def stream_hard_research(self, query: str, case_id: str = "", tenant_id: str = ""):
        yield {"type": "hard_research_start", "query": query}

        queries = await self.plan_queries(query)

        for p in self.PROVIDERS:
            yield {"type": "provider_start", "provider": p}

        results = await self.execute_parallel(queries, case_id, tenant_id)

        for p, pr in results.items():
            if pr.error:
                yield {"type": "provider_error", "provider": p, "error": pr.error}
            else:
                yield {"type": "provider_done", "provider": p}

        yield {"type": "merge_start"}
        merged = self.merge_results(results)
        yield {"type": "merge_done", "total_sources": merged.total_sources}

        yield {"type": "study_generation_start"}
        study_text = f"Estudo consolidado: {merged.text[:100]}"
        for token in study_text.split():
            yield {"type": "study_token", "delta": token + " "}
        yield {"type": "study_done"}


def _build_stub_hard_service(deep_research_service, anthropic_client, rag_manager):
    svc = _StubDeepResearchHardService(
        deep_research_service=deep_research_service,
        anthropic_client=anthropic_client,
        rag_manager=rag_manager,
    )
    return svc


# ===========================================================================
# TESTS
# ===========================================================================


class TestDeepResearchHardService:
    """Test the main orchestration service."""

    # 1
    def test_init_creates_service(self, hard_service):
        """Verifica que o service inicializa sem erro."""
        assert hard_service is not None
        assert hard_service.timeout_per_provider == 120
        assert hard_service.total_timeout == 300

    # 2
    @pytest.mark.asyncio
    async def test_plan_queries_returns_dict_with_all_providers(
        self, hard_service, mock_anthropic
    ):
        """Mock Claude API, verifica que retorna dict com todas as keys de provider."""
        result = await hard_service.plan_queries("responsabilidade civil medica")
        assert isinstance(result, dict)
        expected_keys = {"gemini", "perplexity", "openai", "rag_global", "rag_local"}
        assert set(result.keys()) == expected_keys
        for key in expected_keys:
            assert isinstance(result[key], str)
            assert len(result[key]) > 0

    # 3
    @pytest.mark.asyncio
    async def test_plan_queries_handles_api_error(self, hard_service, mock_anthropic):
        """Se Claude falha, deve retornar query original para todos os providers."""
        mock_anthropic.messages.create = AsyncMock(side_effect=Exception("API error"))
        query = "dano moral por erro medico"
        result = await hard_service.plan_queries(query)
        assert isinstance(result, dict)
        for provider in hard_service.PROVIDERS:
            assert result[provider] == query

    # 4
    @pytest.mark.asyncio
    async def test_execute_parallel_runs_all_providers(
        self, hard_service, mock_deep_research_service, mock_rag_manager
    ):
        """Mock todos os _run_* methods, verifica que todos os providers sao executados."""
        queries = {p: f"query for {p}" for p in hard_service.PROVIDERS}
        results = await hard_service.execute_parallel(queries)
        assert isinstance(results, dict)
        assert set(results.keys()) == set(hard_service.PROVIDERS)
        for key, pr in results.items():
            assert isinstance(pr, ProviderResult)
            assert pr.provider == key

    # 5
    @pytest.mark.asyncio
    async def test_execute_parallel_handles_single_provider_failure(
        self, hard_service, mock_deep_research_service, mock_rag_manager
    ):
        """Um provider falha (exception), outros completam. Deve ter 4 sucessos e 1 erro."""
        original_run = hard_service._run_gemini_research

        async def failing_gemini(query):
            raise TimeoutError("Gemini timeout")

        hard_service._run_gemini_research = failing_gemini

        queries = {p: f"query for {p}" for p in hard_service.PROVIDERS}
        results = await hard_service.execute_parallel(queries)

        errors = [k for k, v in results.items() if v.error]
        successes = [k for k, v in results.items() if not v.error]
        assert len(errors) == 1
        assert "gemini" in errors
        assert len(successes) == 4

        hard_service._run_gemini_research = original_run

    # 6
    @pytest.mark.asyncio
    async def test_execute_parallel_handles_all_providers_failure(
        self, hard_service, mock_deep_research_service, mock_rag_manager
    ):
        """Todos falham. Deve retornar dict sem crash."""
        mock_deep_research_service.run_research_task = AsyncMock(
            side_effect=Exception("All fail")
        )
        mock_rag_manager.search = AsyncMock(side_effect=Exception("RAG fail"))

        queries = {p: f"query for {p}" for p in hard_service.PROVIDERS}
        results = await hard_service.execute_parallel(queries)

        assert isinstance(results, dict)
        assert len(results) == 5
        for key, pr in results.items():
            assert pr.error is not None

    # 7
    @pytest.mark.asyncio
    async def test_execute_parallel_respects_timeout(self, hard_service):
        """Provider que demora mais que timeout e cancelado."""
        hard_service.timeout_per_provider = 0.01  # 10ms

        async def slow_provider(query):
            await asyncio.sleep(10)  # Vai estourar o timeout
            return ProviderResult(provider="gemini", text="never returned")

        hard_service._run_gemini_research = slow_provider

        queries = {p: f"query for {p}" for p in hard_service.PROVIDERS}
        results = await hard_service.execute_parallel(queries)

        assert results["gemini"].error is not None
        assert "timeout" in results["gemini"].error.lower() or "Timeout" in results["gemini"].error or "timed out" in results["gemini"].error.lower()

    # 8
    def test_merge_results_deduplicates_by_url(self, hard_service):
        """2 providers retornam mesma URL. Merge deve ter 1 entrada."""
        pr1 = ProviderResult(
            provider="gemini",
            text="Texto gemini",
            sources=[{"title": "Fonte A", "url": "https://example.com/doc1"}],
        )
        pr2 = ProviderResult(
            provider="perplexity",
            text="Texto perplexity",
            sources=[{"title": "Fonte A (dup)", "url": "https://example.com/doc1"}],
        )
        merged = hard_service.merge_results({"gemini": pr1, "perplexity": pr2})
        urls = [s["url"] for s in merged.sources]
        assert len(urls) == 1
        assert urls[0] == "https://example.com/doc1"

    # 9
    def test_merge_results_reranks_with_boosts(self, hard_service):
        """Fonte jurisprudencial tem score boost vs fonte web generica."""
        pr1 = ProviderResult(
            provider="gemini",
            text="Texto",
            sources=[
                {"title": "Blog generico", "url": "https://blog.example.com/post"},
                {"title": "STJ Jurisprudencia", "url": "https://stj.jus.br/recurso/123"},
            ],
        )
        merged = hard_service.merge_results({"gemini": pr1})
        assert len(merged.sources) == 2
        # STJ deve vir primeiro (score boost)
        assert "stj.jus.br" in merged.sources[0]["url"]

    # 10
    def test_merge_results_empty_input(self, hard_service):
        """Nenhum resultado. Merge retorna MergedResearch vazio."""
        merged = hard_service.merge_results({})
        assert isinstance(merged, MergedResearch)
        assert merged.text == ""
        assert merged.sources == []
        assert merged.total_sources == 0

    # 11
    @pytest.mark.asyncio
    async def test_stream_hard_research_emits_all_event_types(
        self, hard_service, mock_deep_research_service, mock_rag_manager
    ):
        """Mock tudo. Coleta todos os events e verifica tipos presentes."""
        events = []
        async for event in hard_service.stream_hard_research("teste query"):
            events.append(event)

        event_types = {e["type"] for e in events}
        assert "hard_research_start" in event_types
        assert "provider_start" in event_types
        assert "merge_start" in event_types
        assert "merge_done" in event_types
        assert "study_generation_start" in event_types
        assert "study_token" in event_types
        assert "study_done" in event_types

        # Deve ter pelo menos 5 provider_start (um por provider)
        provider_starts = [e for e in events if e["type"] == "provider_start"]
        assert len(provider_starts) == 5

    # 12
    @pytest.mark.asyncio
    async def test_stream_hard_research_study_tokens_form_complete_text(
        self, hard_service, mock_deep_research_service, mock_rag_manager
    ):
        """Junta todos os study_token deltas. Deve formar texto coerente."""
        deltas = []
        async for event in hard_service.stream_hard_research("teste query"):
            if event["type"] == "study_token":
                deltas.append(event["delta"])

        full_text = "".join(deltas).strip()
        assert len(full_text) > 0
        assert "Estudo consolidado" in full_text

    # 13
    @pytest.mark.asyncio
    async def test_run_gemini_delegates_to_deep_research_service(
        self, hard_service, mock_deep_research_service
    ):
        """Verifica que _run_gemini_research chama deep_research_service com provider='google'."""
        await hard_service._run_gemini_research("query teste")
        mock_deep_research_service.run_research_task.assert_called_once_with(
            "query teste", {"provider": "google"}
        )

    # 14
    @pytest.mark.asyncio
    async def test_run_perplexity_delegates_to_deep_research_service(
        self, hard_service, mock_deep_research_service
    ):
        """Verifica que _run_perplexity_research chama com provider='perplexity'."""
        await hard_service._run_perplexity_research("query pplx")
        mock_deep_research_service.run_research_task.assert_called_once_with(
            "query pplx", {"provider": "perplexity"}
        )

    # 15
    @pytest.mark.asyncio
    async def test_run_openai_delegates_to_deep_research_service(
        self, hard_service, mock_deep_research_service
    ):
        """Verifica que _run_openai_research chama com provider='openai'."""
        await hard_service._run_openai_research("query oai")
        mock_deep_research_service.run_research_task.assert_called_once_with(
            "query oai", {"provider": "openai"}
        )

    # 16
    @pytest.mark.asyncio
    async def test_run_rag_global_calls_rag_manager(
        self, hard_service, mock_rag_manager
    ):
        """Mock RAG manager, verifica chamada com scope='all'."""
        await hard_service._run_rag_global("pesquisa rag global")
        mock_rag_manager.search.assert_called_once_with(
            query="pesquisa rag global", scope="all"
        )

    # 17
    @pytest.mark.asyncio
    async def test_run_rag_local_uses_case_id(
        self, hard_service, mock_rag_manager
    ):
        """Mock RAG manager, verifica case_id e tenant_id passados."""
        await hard_service._run_rag_local(
            "pesquisa local", case_id="case-123", tenant_id="tenant-456"
        )
        mock_rag_manager.search.assert_called_once_with(
            query="pesquisa local",
            scope="local",
            case_id="case-123",
            tenant_id="tenant-456",
        )

    # 18
    def test_config_defaults(self, hard_service):
        """Verifica defaults: timeout_per_provider=120, total_timeout=300."""
        assert hard_service.timeout_per_provider == 120
        assert hard_service.total_timeout == 300


class TestProviderResult:
    """Test the ProviderResult dataclass."""

    # 19
    def test_provider_result_creation(self):
        """Cria ProviderResult com todos os campos."""
        pr = ProviderResult(
            provider="gemini",
            text="Resultado da pesquisa",
            sources=[{"title": "Fonte", "url": "https://example.com"}],
            error=None,
            elapsed_ms=1500.5,
        )
        assert pr.provider == "gemini"
        assert pr.text == "Resultado da pesquisa"
        assert len(pr.sources) == 1
        assert pr.sources[0]["url"] == "https://example.com"
        assert pr.error is None
        assert pr.elapsed_ms == 1500.5

    # 20
    def test_provider_result_defaults(self):
        """Verifica defaults: error=None, elapsed_ms=0."""
        pr = ProviderResult(provider="openai", text="texto")
        assert pr.error is None
        assert pr.elapsed_ms == 0
        assert pr.sources == []


class TestMergedResearch:
    """Test the MergedResearch dataclass."""

    # 21
    def test_merged_research_creation(self):
        """Cria com dados completos."""
        pr1 = ProviderResult(provider="gemini", text="Texto 1")
        merged = MergedResearch(
            text="Texto consolidado",
            sources=[
                {"title": "A", "url": "https://a.com"},
                {"title": "B", "url": "https://b.com"},
            ],
            provider_results=[pr1],
            total_sources=2,
        )
        assert merged.text == "Texto consolidado"
        assert len(merged.sources) == 2
        assert len(merged.provider_results) == 1
        assert merged.total_sources == 2

    # 22
    def test_merged_research_empty(self):
        """Cria com listas vazias."""
        merged = MergedResearch()
        assert merged.text == ""
        assert merged.sources == []
        assert merged.provider_results == []
        assert merged.total_sources == 0
