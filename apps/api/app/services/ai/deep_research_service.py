import os
import time
import logging
import inspect
from typing import Optional, Dict, Any, AsyncGenerator, List, Tuple
from dataclasses import dataclass

from app.services.job_manager import job_manager
from app.services.api_call_tracker import record_api_call
from app.services.billing_service import get_default_deep_research_effort, normalize_effort
from app.services.ai.citations import extract_perplexity
from app.services.ai.citations.base import sources_to_citations
from app.services.ai.model_registry import get_api_model_name
from app.services.ai.perplexity_config import (
    normalize_perplexity_search_mode,
    normalize_perplexity_recency,
    normalize_perplexity_date,
    parse_csv_list,
    normalize_float,
)

logger = logging.getLogger("DeepResearchService")

# Tentar importar SDK Google GenAI (v1.53+)
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    logger.error("❌ google-genai não instalado. Deep Research indisponível.")

try:
    from perplexity import AsyncPerplexity
    PERPLEXITY_AVAILABLE = True
except Exception:
    AsyncPerplexity = None  # type: ignore
    PERPLEXITY_AVAILABLE = False

@dataclass
class DeepResearchResult:
    text: str
    log: str = ""
    success: bool = False
    error: Optional[str] = None
    sources: Optional[list] = None
    thinking_steps: Optional[list] = None
    from_cache: bool = False

class DeepResearchService:
    """
    Service wrapper for Deep Research providers.

    Providers:
    - google: Google GenAI Deep Research agent
    - perplexity: Perplexity Sonar Deep Research (chat completions)
    Provides methods for background execution and polling/streaming of research tasks.
    """
    
    def __init__(self):
        self.google_client = None
        if GENAI_AVAILABLE:
            api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            if api_key:
                try:
                    self.google_client = genai.Client(api_key=api_key)
                    logger.info("✅ DeepResearchService: Connected via Google AI Studio (API Key)")
                except Exception as e:
                     logger.warning(f"Could not initialize Google GenAI client: {e}")
                     self.google_client = None

        self.perplexity_api_key = os.getenv("PERPLEXITY_API_KEY") or None

        if not self.google_client and not self.perplexity_api_key:
            logger.warning("⚠️ Nenhuma API configurada (GOOGLE_API_KEY/GEMINI_API_KEY ou PERPLEXITY_API_KEY). Deep Research não funcionará.")

    def _resolve_provider(self, config: Optional[Dict[str, Any]] = None) -> str:
        explicit = str((config or {}).get("provider") or "").strip().lower()
        if explicit in ("pplx", "sonar"):
            explicit = "perplexity"
        if explicit in ("gemini", "google-genai", "google_genai"):
            explicit = "google"
        if explicit and explicit != "auto":
            return explicit
        env = os.getenv("DEEP_RESEARCH_PROVIDER", "auto").strip().lower()
        if env in ("pplx", "sonar"):
            env = "perplexity"
        if env in ("gemini", "google-genai", "google_genai"):
            env = "google"
        if env and env != "auto":
            return env

        # If the caller selected a model, infer provider from it.
        model_hint = str((config or {}).get("model") or "").strip()
        if model_hint:
            inferred: Optional[str] = None
            lowered = model_hint.lower()
            # Canonical ids from the app registry (preferred).
            try:
                from app.services.ai.model_registry import get_model_config
                cfg = get_model_config(model_hint)
                if cfg and cfg.provider in ("perplexity", "google"):
                    inferred = cfg.provider
            except Exception:
                inferred = None

            # Heuristics for API model names / aliases.
            if inferred is None:
                if "sonar" in lowered or "perplexity" in lowered:
                    inferred = "perplexity"
                elif "deep-research" in lowered:
                    inferred = "google"

            # Auto mode: prefer the inferred provider if configured; otherwise fall back to the other.
            if inferred == "perplexity":
                if self.perplexity_api_key:
                    return "perplexity"
                if self.google_client:
                    return "google"
                return "perplexity"
            if inferred == "google":
                if self.google_client:
                    return "google"
                if self.perplexity_api_key:
                    return "perplexity"
                return "google"
        if self.google_client:
            return "google"
        if self.perplexity_api_key:
            return "perplexity"
        return "none"

    def _resolve_perplexity_model(self, config: Optional[Dict[str, Any]] = None) -> str:
        model_id = str((config or {}).get("model") or "").strip()
        if not model_id:
            model_id = os.getenv("PERPLEXITY_DEEP_RESEARCH_MODEL", "sonar-deep-research").strip() or "sonar-deep-research"
        try:
            from app.services.ai.model_registry import get_api_model_name
            resolved = get_api_model_name(model_id) or model_id
        except Exception:
            resolved = model_id

        # Guardrail: in this app, Perplexity "Deep Research" is restricted to Sonar Deep Research.
        if (resolved or "").strip().lower() != "sonar-deep-research":
            logger.warning(f"⚠️ Modelo Perplexity Deep Research inválido/inesperado: '{resolved}'. Forçando 'sonar-deep-research'.")
            return "sonar-deep-research"
        return "sonar-deep-research"

    def _resolve_google_model(self, config: Optional[Dict[str, Any]] = None) -> str:
        raw = (config or {}).get("model") or os.getenv("DEEP_RESEARCH_GOOGLE_MODEL", "gemini-3-flash")
        model_id = str(raw or "").strip()
        if not model_id:
            return "gemini-3-flash"
        lowered = model_id.lower()
        if lowered.startswith("sonar") or lowered == "sonar-deep-research":
            logger.warning(f"⚠️ Modelo Perplexity recebido em provider=google: '{model_id}'. Usando gemini-3-flash.")
            return "gemini-3-flash"
        return model_id

    def _is_google_deep_research_agent(self, model_id: str) -> bool:
        return (model_id or "").strip().lower().startswith("deep-research")

    def _resolve_effort(self, config: Optional[Dict[str, Any]] = None) -> str:
        raw = (config or {}).get("effort") or (config or {}).get("reasoning_effort")
        default_effort = get_default_deep_research_effort()
        return normalize_effort(raw, default_effort)

    def _resolve_points_multiplier(self, config: Optional[Dict[str, Any]] = None) -> float:
        raw = (config or {}).get("points_multiplier")
        try:
            return float(raw) if raw is not None else 1.0
        except (TypeError, ValueError):
            return 1.0

    def _build_perplexity_web_search_options(
        self,
        config: Optional[Dict[str, Any]] = None,
    ) -> tuple[Optional[str], Dict[str, Any]]:
        cfg = config or {}
        search_focus = normalize_perplexity_search_mode(cfg.get("search_focus") or cfg.get("search_mode"))
        web_search_options: Dict[str, Any] = {}

        domain_filter = parse_csv_list(cfg.get("search_domain_filter"), max_items=20)
        if domain_filter:
            web_search_options["search_domain_filter"] = domain_filter

        after_date = normalize_perplexity_date(cfg.get("search_after_date"))
        if after_date:
            web_search_options["search_after_date"] = after_date

        before_date = normalize_perplexity_date(cfg.get("search_before_date"))
        if before_date:
            web_search_options["search_before_date"] = before_date

        recency_filter = cfg.get("search_recency_filter") or cfg.get("recency_filter")
        normalized_recency = normalize_perplexity_recency(recency_filter)
        if normalized_recency and not (after_date or before_date):
            web_search_options["search_recency_filter"] = normalized_recency

        updated_after = normalize_perplexity_date(cfg.get("last_updated_after"))
        if updated_after:
            web_search_options["last_updated_after"] = updated_after

        updated_before = normalize_perplexity_date(cfg.get("last_updated_before"))
        if updated_before:
            web_search_options["last_updated_before"] = updated_before

        country = (cfg.get("search_country") or "").strip()
        if country:
            web_search_options["search_country"] = country.upper()

        latitude = normalize_float(cfg.get("search_latitude"))
        longitude = normalize_float(cfg.get("search_longitude"))
        if latitude is not None and longitude is not None:
            web_search_options["search_latitude"] = latitude
            web_search_options["search_longitude"] = longitude

        return search_focus, web_search_options

    def _cache_query_key(self, provider: str, model: str, query: str) -> str:
        normalized_provider = (provider or "none").strip().lower()
        normalized_model = (model or "").strip().lower()
        return f"[{normalized_provider}:{normalized_model}] {query}"

    def _to_url_title(self, item: Any) -> Tuple[str, str]:
        if isinstance(item, str):
            return item.strip(), item.strip()
        if isinstance(item, dict):
            url = str(item.get("url") or item.get("uri") or "").strip()
            title = str(item.get("title") or item.get("name") or url).strip()
            return url, title
        url = str(getattr(item, "url", "") or getattr(item, "uri", "") or "").strip()
        title = str(getattr(item, "title", "") or getattr(item, "name", "") or url).strip()
        return url, title

    def _extract_perplexity_sources(self, *, search_results: List[Any], citations: List[Any]) -> List[Dict[str, Any]]:
        url_title_stream: List[Tuple[str, str]] = []
        items = citations or search_results or []
        for item in items:
            url, title = self._to_url_title(item)
            if url:
                url_title_stream.append((url, title or url))
        if not url_title_stream:
            return []
        from app.services.ai.citations.base import stable_numbering, sources_to_citations
        _, sources = stable_numbering(url_title_stream)
        return sources_to_citations(sources)

    async def run_research_task(self, query: str, config: Optional[Dict[str, Any]] = None) -> DeepResearchResult:
        """
        Executes Deep Research with caching strategy.
        1. Check Cache
        2. If miss, run agent
        3. Cache result
        """
        provider = self._resolve_provider(config)
        model = ""
        if provider == "perplexity":
            model = self._resolve_perplexity_model(config)
        elif provider == "google":
            model = self._resolve_google_model(config)
        effort = self._resolve_effort(config)
        points_multiplier = self._resolve_points_multiplier(config)
        cache_query = self._cache_query_key(provider, model, query)

        # 1. Try Cache
        cached = job_manager.get_cached_deep_research(cache_query)
        if cached:
            logger.info(f"⚡ Deep Research Cache Hit: {cached['cache_key']}")
            return DeepResearchResult(
                text=cached['report'],
                log="\n".join([t['text'] for t in cached['thinking_steps']]),
                success=True,
                sources=cached['sources'],
                thinking_steps=cached['thinking_steps'],
                from_cache=True
            )

        if provider == "google":
            if not self.google_client:
                return DeepResearchResult(text="", error="Client Google GenAI não inicializado", success=False)

            google_model = model or "deep-research-pro-preview-12-2025"
            logger.info(f"🚀 Iniciando Deep Research (Google {google_model}): '{query}'")

            if not self._is_google_deep_research_agent(google_model):
                system_instruction = (
                    "Você é um pesquisador jurídico. Faça pesquisa profunda, "
                    "use busca do Google quando necessário e cite fontes com [n]. "
                    "Responda em português com clareza e precisão."
                )
                try:
                    tool = types.Tool(google_search=types.GoogleSearch())
                    config_obj = types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        tools=[tool],
                    )
                    api_model = get_api_model_name(google_model) or google_model
                    resp = self.google_client.models.generate_content(
                        model=api_model,
                        contents=query,
                        config=config_obj,
                    )
                    text, sources = extract_perplexity("gemini", resp)
                    record_api_call(
                        kind="deep_research",
                        provider="google",
                        model=google_model,
                        success=bool(text),
                        meta={"effort": effort, "points_multiplier": points_multiplier},
                    )
                    if text:
                        job_manager.cache_deep_research(
                            query=cache_query,
                            report=text,
                            sources=sources_to_citations(sources),
                            thinking_steps=[],
                        )
                    return DeepResearchResult(
                        text=text or "",
                        log="",
                        success=bool(text),
                        sources=sources_to_citations(sources),
                        thinking_steps=[],
                        from_cache=False,
                    )
                except Exception as e:
                    record_api_call(
                        kind="deep_research",
                        provider="google",
                        model=google_model,
                        success=False,
                        meta={"effort": effort, "points_multiplier": points_multiplier},
                    )
                    logger.error(f"❌ Falha crítica no Deep Research (Google {google_model}): {e}")
                    return DeepResearchResult(text="", error=str(e), success=False)

            agent_model = google_model or "deep-research-pro-preview-12-2025"

            try:
                interaction = self.google_client.interactions.create(
                    input=query,
                    agent=agent_model,
                    background=True,
                    stream=True,
                    agent_config={
                        "type": "deep-research",
                        "thinking_summaries": "auto"
                    }
                )
                record_api_call(
                    kind="deep_research",
                    provider="google",
                    model=agent_model,
                    success=True,
                    meta={"effort": effort, "points_multiplier": points_multiplier},
                )

                final_report = ""
                full_thinking = []

                for event in interaction:
                    if event.type == "thinking":
                        logger.debug(f"💭 Thinking: {event.text[:50]}...")
                        full_thinking.append({"text": event.text, "timestamp": time.time()})
                    elif event.type == "content":
                        final_report += event.text
                    elif event.type == "interaction.end":
                        break
                    elif event.type == "error":
                        return DeepResearchResult(text="", error=event.text, success=False)

                sources: List[Dict[str, Any]] = []

                if final_report:
                    job_manager.cache_deep_research(
                        query=cache_query,
                        report=final_report,
                        sources=sources,
                        thinking_steps=full_thinking
                    )

                return DeepResearchResult(
                    text=final_report,
                    log="\n".join([t['text'] for t in full_thinking]),
                    success=True,
                    sources=sources,
                    thinking_steps=full_thinking,
                    from_cache=False
                )

            except Exception as e:
                record_api_call(
                    kind="deep_research",
                    provider="google",
                    model=agent_model,
                    success=False,
                    meta={"effort": effort, "points_multiplier": points_multiplier},
                )
                logger.error(f"❌ Falha crítica no Deep Research (Google): {e}")
                return DeepResearchResult(text="", error=str(e), success=False)

        if provider == "perplexity":
            if not (PERPLEXITY_AVAILABLE and self.perplexity_api_key and AsyncPerplexity):
                return DeepResearchResult(text="", error="Perplexity não configurada (PERPLEXITY_API_KEY/perplexityai).", success=False)

            logger.info(f"🚀 Iniciando Deep Research (Perplexity {model}): '{query}'")

            thinking_steps = [{"text": f"Iniciando pesquisa via Perplexity ({model}).", "timestamp": time.time()}]
            final_text = ""
            search_results: List[Any] = []
            citations: List[Any] = []

            def _get(obj: Any, key: str, default=None):
                if isinstance(obj, dict):
                    return obj.get(key, default)
                return getattr(obj, key, default)

            try:
                client = AsyncPerplexity(api_key=self.perplexity_api_key)
                req_payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": query}],
                    "temperature": 0.2,
                    "max_tokens": 4096,
                }
                if effort:
                    req_payload["reasoning_effort"] = effort
                search_focus, web_search_options = self._build_perplexity_web_search_options(config)
                if search_focus:
                    req_payload["search_mode"] = search_focus
                if web_search_options:
                    req_payload["web_search_options"] = web_search_options
                resp_obj = client.chat.completions.create(**req_payload)
                if inspect.isawaitable(resp_obj):
                    resp_obj = await resp_obj
                usage = _get(resp_obj, "usage", None) or _get(resp_obj, "usage_metadata", None)
                tokens_in = _get(usage, "prompt_tokens", None) or _get(usage, "input_tokens", None)
                tokens_out = _get(usage, "completion_tokens", None) or _get(usage, "output_tokens", None)
                citation_tokens = _get(usage, "citation_tokens", None)
                reasoning_tokens = _get(usage, "reasoning_tokens", None)
                search_queries = _get(usage, "search_queries", None) or _get(resp_obj, "search_queries", None)
                record_meta = {
                    "effort": effort,
                    "points_multiplier": points_multiplier,
                }
                if tokens_in is not None:
                    record_meta["tokens_in"] = int(tokens_in)
                if tokens_out is not None:
                    record_meta["tokens_out"] = int(tokens_out)
                if citation_tokens is not None:
                    record_meta["citation_tokens"] = int(citation_tokens)
                if reasoning_tokens is not None:
                    record_meta["reasoning_tokens"] = int(reasoning_tokens)
                if search_queries is not None:
                    record_meta["search_queries"] = int(search_queries)
                choices = _get(resp_obj, "choices", []) or []
                msg = _get(choices[0], "message", None) if choices else None
                final_text = str(_get(msg, "content", "") or "")

                chunk_results = _get(resp_obj, "search_results", None) or _get(resp_obj, "searchResults", None)
                if isinstance(chunk_results, list) and chunk_results:
                    search_results.extend(chunk_results)

                chunk_citations = _get(resp_obj, "citations", None)
                if isinstance(chunk_citations, list) and chunk_citations:
                    citations.extend(chunk_citations)

                sources = self._extract_perplexity_sources(search_results=search_results, citations=citations)
                if search_results and "search_queries" not in record_meta:
                    record_meta["search_queries"] = 1

                record_api_call(
                    kind="deep_research",
                    provider="perplexity",
                    model=model,
                    success=True,
                    meta=record_meta,
                )

                if final_text:
                    job_manager.cache_deep_research(
                        query=cache_query,
                        report=final_text,
                        sources=sources,
                        thinking_steps=thinking_steps,
                    )

                return DeepResearchResult(
                    text=final_text,
                    log="\n".join([t['text'] for t in thinking_steps]),
                    success=bool(final_text),
                    sources=sources,
                    thinking_steps=thinking_steps,
                    from_cache=False,
                )

            except Exception as e:
                record_api_call(
                    kind="deep_research",
                    provider="perplexity",
                    model=model,
                    success=False,
                    meta={"effort": effort, "points_multiplier": points_multiplier},
                )
                logger.error(f"❌ Falha crítica no Deep Research (Perplexity): {e}")
                return DeepResearchResult(text="", error=str(e), success=False)

        return DeepResearchResult(text="", error="Nenhum provider de Deep Research disponível.", success=False)

    async def stream_research_task(
        self,
        query: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Async generator that yields events: 
        - type: 'thinking', 'content', 'cache_hit', 'done'
        """
        provider = self._resolve_provider(config)
        model = ""
        if provider == "perplexity":
            model = self._resolve_perplexity_model(config)
        elif provider == "google":
            model = self._resolve_google_model(config)
        effort = self._resolve_effort(config)
        points_multiplier = self._resolve_points_multiplier(config)
        cache_query = self._cache_query_key(provider, model, query)

        # 1. Try Cache
        cached = job_manager.get_cached_deep_research(cache_query)
        if cached:
            yield {"type": "cache_hit", "key": cached['cache_key']}
            # Replay thinking
            for step in cached['thinking_steps']:
                yield {"type": "thinking", "text": step['text'], "from_cache": True}
                # Artificial delay for UI pacing if needed, but skipped for speed
            
            yield {"type": "content", "text": cached['report'], "from_cache": True}
            yield {"type": "done", "sources": cached['sources']}
            return

        if provider == "google":
            if not self.google_client:
                yield {"type": "error", "message": "Client Google GenAI não inicializado"}
                return
            google_model = model or "deep-research-pro-preview-12-2025"
            if not self._is_google_deep_research_agent(google_model):
                yield {"type": "thinking", "text": f"Iniciando pesquisa via Google ({google_model})."}
                try:
                    tool = types.Tool(google_search=types.GoogleSearch())
                    config_obj = types.GenerateContentConfig(
                        system_instruction=(
                            "Você é um pesquisador jurídico. Faça pesquisa profunda, "
                            "use busca do Google quando necessário e cite fontes com [n]. "
                            "Responda em português com clareza e precisão."
                        ),
                        tools=[tool],
                    )
                    api_model = get_api_model_name(google_model) or google_model
                    resp = self.google_client.models.generate_content(
                        model=api_model,
                        contents=query,
                        config=config_obj,
                    )
                    text, sources = extract_perplexity("gemini", resp)
                    record_api_call(
                        kind="deep_research",
                        provider="google",
                        model=google_model,
                        success=bool(text),
                        meta={"effort": effort, "points_multiplier": points_multiplier},
                    )
                    if text:
                        job_manager.cache_deep_research(
                            query=cache_query,
                            report=text,
                            sources=sources_to_citations(sources),
                            thinking_steps=[],
                        )
                    yield {"type": "content", "text": text or ""}
                    yield {"type": "done", "sources": sources_to_citations(sources)}
                except Exception as e:
                    record_api_call(
                        kind="deep_research",
                        provider="google",
                        model=google_model,
                        success=False,
                        meta={"effort": effort, "points_multiplier": points_multiplier},
                    )
                    logger.error(f"❌ Falha crítica no Deep Research (Google {google_model}): {e}")
                    yield {"type": "error", "message": str(e)}
                return

            try:
                interaction = self.google_client.interactions.create(
                    input=query,
                    agent=google_model,
                    background=True,
                    stream=True,
                    agent_config={"type": "deep-research", "thinking_summaries": "auto"}
                )
                record_api_call(
                    kind="deep_research",
                    provider="google",
                    model=google_model,
                    success=True,
                    meta={"effort": effort, "points_multiplier": points_multiplier},
                )

                final_report = ""
                full_thinking = []

                for event in interaction:
                    if event.type == "thinking":
                        full_thinking.append({"text": event.text, "timestamp": time.time()})
                        yield {"type": "thinking", "text": event.text, "from_cache": False}
                    elif event.type == "content":
                        final_report += event.text
                        yield {"type": "content", "text": event.text, "from_cache": False}
                    elif event.type == "interaction.end":
                        break

                if final_report:
                    job_manager.cache_deep_research(
                        query=cache_query,
                        report=final_report,
                        sources=[],
                        thinking_steps=full_thinking
                    )

                yield {"type": "done", "sources": []}
                return

            except Exception as e:
                record_api_call(
                    kind="deep_research",
                    provider="google",
                    model="deep-research-pro-preview-12-2025",
                    success=False,
                    meta={"effort": effort, "points_multiplier": points_multiplier},
                )
                logger.error(f"❌ Stream Deep Research Error (Google): {e}")
                yield {"type": "error", "message": str(e)}
                return

        if provider == "perplexity":
            if not (PERPLEXITY_AVAILABLE and self.perplexity_api_key and AsyncPerplexity):
                yield {"type": "error", "message": "Perplexity não configurada (PERPLEXITY_API_KEY/perplexityai)."}
                return

            yield {"type": "thinking", "text": f"Iniciando pesquisa via Perplexity ({model}).", "from_cache": False}

            final_report = ""
            thinking_steps = [{"text": f"Iniciando pesquisa via Perplexity ({model}).", "timestamp": time.time()}]
            search_results: List[Any] = []
            citations: List[Any] = []

            def _get(obj: Any, key: str, default=None):
                if isinstance(obj, dict):
                    return obj.get(key, default)
                return getattr(obj, key, default)

            try:
                client = AsyncPerplexity(api_key=self.perplexity_api_key)
                req_payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": query}],
                    "temperature": 0.2,
                    "max_tokens": 4096,
                    "stream": True,
                }
                if effort:
                    req_payload["reasoning_effort"] = effort
                search_focus, web_search_options = self._build_perplexity_web_search_options(config)
                if search_focus:
                    req_payload["search_mode"] = search_focus
                if web_search_options:
                    req_payload["web_search_options"] = web_search_options
                stream_obj = client.chat.completions.create(**req_payload)
                if inspect.isawaitable(stream_obj):
                    stream_obj = await stream_obj
                record_api_call(
                    kind="deep_research",
                    provider="perplexity",
                    model=model,
                    success=True,
                    meta={"effort": effort, "points_multiplier": points_multiplier},
                )

                if hasattr(stream_obj, "__aiter__"):
                    async for chunk in stream_obj:
                        choices = _get(chunk, "choices", []) or []
                        if choices:
                            delta = _get(choices[0], "delta", None) or {}
                            content = _get(delta, "content", None) or ""
                            if content:
                                final_report += str(content)
                                yield {"type": "content", "text": str(content), "from_cache": False}

                        chunk_results = _get(chunk, "search_results", None) or _get(chunk, "searchResults", None)
                        if isinstance(chunk_results, list) and chunk_results:
                            search_results.extend(chunk_results)

                        chunk_citations = _get(chunk, "citations", None)
                        if isinstance(chunk_citations, list) and chunk_citations:
                            citations.extend(chunk_citations)
                else:
                    for chunk in stream_obj:
                        choices = _get(chunk, "choices", []) or []
                        if choices:
                            delta = _get(choices[0], "delta", None) or {}
                            content = _get(delta, "content", None) or ""
                            if content:
                                final_report += str(content)
                                yield {"type": "content", "text": str(content), "from_cache": False}

                        chunk_results = _get(chunk, "search_results", None) or _get(chunk, "searchResults", None)
                        if isinstance(chunk_results, list) and chunk_results:
                            search_results.extend(chunk_results)

                        chunk_citations = _get(chunk, "citations", None)
                        if isinstance(chunk_citations, list) and chunk_citations:
                            citations.extend(chunk_citations)

                sources = self._extract_perplexity_sources(search_results=search_results, citations=citations)

                if final_report:
                    job_manager.cache_deep_research(
                        query=cache_query,
                        report=final_report,
                        sources=sources,
                        thinking_steps=thinking_steps,
                    )

                yield {"type": "done", "sources": sources}
                return

            except Exception as e:
                record_api_call(
                    kind="deep_research",
                    provider="perplexity",
                    model=model,
                    success=False,
                    meta={"effort": effort, "points_multiplier": points_multiplier},
                )
                logger.error(f"❌ Stream Deep Research Error (Perplexity): {e}")
                yield {"type": "error", "message": str(e)}
                return

        yield {"type": "error", "message": "Nenhum provider de Deep Research disponível."}

deep_research_service = DeepResearchService()
