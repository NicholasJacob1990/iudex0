import os
import re
import time
import logging
import inspect
import uuid
from typing import Optional, Dict, Any, AsyncGenerator, List, Tuple, Iterable
from dataclasses import dataclass

from app.services.job_manager import job_manager
from app.services.api_call_tracker import record_api_call
from app.services.billing_service import get_default_deep_research_effort, normalize_effort
from app.services.ai.citations import extract_perplexity
from app.services.ai.citations.base import sources_to_citations, stable_numbering
from app.services.ai.model_registry import get_api_model_name
from app.services.ai.perplexity_config import (
    normalize_perplexity_search_mode,
    normalize_perplexity_recency,
    normalize_perplexity_date,
    parse_csv_list,
    normalize_float,
)

logger = logging.getLogger("DeepResearchService")

# Optional OpenAI client (for OpenAI Deep Research models).
try:
    import openai  # type: ignore
    OPENAI_AVAILABLE = True
except Exception:  # pragma: no cover
    openai = None  # type: ignore
    OPENAI_AVAILABLE = False

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

def _generate_step_id() -> str:
    """Generate a short unique step ID for SSE tracking."""
    return str(uuid.uuid4())[:8]


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
        self.openai_client = None
        if GENAI_AVAILABLE:
            try:
                project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
                location = os.getenv("VERTEX_AI_LOCATION", "global")
                auth_mode = (os.getenv("IUDEX_GEMINI_AUTH") or "auto").strip().lower()

                use_vertex = False
                if auth_mode in ("vertex", "vertexai", "gcp"):
                    use_vertex = True
                elif auth_mode in ("apikey", "api_key"):
                    use_vertex = False
                else:
                    use_vertex = bool(project_id)

                if use_vertex and project_id:
                    self.google_client = genai.Client(
                        vertexai=True,
                        project=project_id,
                        location=location,
                    )
                    logger.info(f"✅ DeepResearchService: Connected via Vertex AI ({location})")
                else:
                    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
                    if api_key:
                        self.google_client = genai.Client(api_key=api_key)
                        logger.info("✅ DeepResearchService: Connected via Google AI Studio (API Key)")
            except Exception as e:
                logger.warning(f"Could not initialize Google GenAI client: {e}")
                self.google_client = None

        self.perplexity_api_key = os.getenv("PERPLEXITY_API_KEY") or None

        if OPENAI_AVAILABLE:
            api_key = os.getenv("OPENAI_API_KEY") or None
            if api_key:
                try:
                    base_url = os.getenv("OPENAI_BASE_URL") or None
                    if base_url:
                        self.openai_client = openai.OpenAI(api_key=api_key, base_url=base_url)  # type: ignore[attr-defined]
                    else:
                        self.openai_client = openai.OpenAI(api_key=api_key)  # type: ignore[attr-defined]
                except Exception as e:
                    logger.warning(f"Could not initialize OpenAI client: {e}")
                    self.openai_client = None

        if not self.google_client and not self.perplexity_api_key and not self.openai_client:
            logger.warning(
                "⚠️ Nenhuma API configurada (GOOGLE_API_KEY/GEMINI_API_KEY, PERPLEXITY_API_KEY, OPENAI_API_KEY). "
                "Deep Research não funcionará."
            )

    def _resolve_provider(self, config: Optional[Dict[str, Any]] = None) -> str:
        explicit = str((config or {}).get("provider") or "").strip().lower()
        if explicit in ("pplx", "sonar"):
            explicit = "perplexity"
        if explicit in ("gemini", "google-genai", "google_genai"):
            explicit = "google"
        if explicit in ("oai",):
            explicit = "openai"
        if explicit and explicit != "auto":
            return explicit
        env = os.getenv("DEEP_RESEARCH_PROVIDER", "auto").strip().lower()
        if env in ("pplx", "sonar"):
            env = "perplexity"
        if env in ("gemini", "google-genai", "google_genai"):
            env = "google"
        if env in ("oai",):
            env = "openai"
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
                if cfg and cfg.provider in ("perplexity", "google", "openai"):
                    inferred = cfg.provider
            except Exception:
                inferred = None

            # Heuristics for API model names / aliases.
            if inferred is None:
                if "sonar" in lowered or "perplexity" in lowered:
                    inferred = "perplexity"
                elif ("deep-research" in lowered) and (lowered.startswith("o3") or lowered.startswith("o4")):
                    inferred = "openai"
                elif "deep-research" in lowered:
                    inferred = "google"

            # Auto mode: prefer the inferred provider if configured; otherwise fall back to the other.
            if inferred == "perplexity":
                if self.perplexity_api_key:
                    return "perplexity"
                if self.google_client:
                    return "google"
                if self.openai_client:
                    return "openai"
                return "perplexity"
            if inferred == "google":
                if self.google_client:
                    return "google"
                if self.perplexity_api_key:
                    return "perplexity"
                if self.openai_client:
                    return "openai"
                return "google"
            if inferred == "openai":
                if self.openai_client:
                    return "openai"
                if self.google_client:
                    return "google"
                if self.perplexity_api_key:
                    return "perplexity"
                return "openai"
        if self.google_client:
            return "google"
        if self.perplexity_api_key:
            return "perplexity"
        if self.openai_client:
            return "openai"
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
        raw = (config or {}).get("model") or os.getenv("DEEP_RESEARCH_GOOGLE_MODEL", "gemini-2.5-flash")
        model_id = str(raw or "").strip()
        if not model_id:
            return "gemini-2.5-flash"
        lowered = model_id.lower()
        if lowered.startswith("sonar") or lowered == "sonar-deep-research":
            logger.warning(f"⚠️ Modelo Perplexity recebido em provider=google: '{model_id}'. Usando gemini-2.5-flash.")
            return "gemini-2.5-flash"
        return model_id

    def _resolve_openai_model(self, config: Optional[Dict[str, Any]] = None) -> str:
        # 1. Explicit model from caller config
        model_id = str((config or {}).get("model") or "").strip()
        if model_id:
            return model_id

        # 2. Tier-based model selection from billing config
        plan_key = str((config or {}).get("plan_key") or "").strip()
        if plan_key:
            try:
                from app.services.billing_service import load_billing_config
                bcfg = load_billing_config()
                tier_map = bcfg.get("deep_research_openai_model_by_plan") or {}
                tier_model = tier_map.get(plan_key)
                if tier_model:
                    return str(tier_model).strip()
            except Exception:
                pass

        # 3. Environment variable fallback
        model_id = os.getenv("OPENAI_DEEP_RESEARCH_MODEL", "o4-mini-deep-research").strip()
        return model_id or "o4-mini-deep-research"

    def _iter_url_title_pairs(self, obj: Any) -> Iterable[Tuple[str, str]]:
        """
        Best-effort extractor for (url, title) pairs in arbitrary SDK objects / dicts.
        We treat these as "consulted sources" when providers expose tool results / citations.
        """
        seen_ids: set[int] = set()

        def _walk(node: Any):
            if node is None:
                return
            nid = id(node)
            if nid in seen_ids:
                return
            # Avoid infinite loops on SDK objects with self-references.
            seen_ids.add(nid)

            if isinstance(node, str):
                return

            if isinstance(node, dict):
                # Common shapes: {url/title}, {uri/title}, {link/title}
                url = node.get("url") or node.get("uri") or node.get("link")
                if isinstance(url, str) and url.strip().startswith(("http://", "https://")):
                    title = node.get("title") or node.get("name") or url
                    yield (url.strip(), str(title or url).strip())

                for v in node.values():
                    yield from _walk(v)
                return

            if isinstance(node, (list, tuple, set)):
                for it in node:
                    yield from _walk(it)
                return

            # Generic object: scan attributes conservatively.
            url = getattr(node, "url", None) or getattr(node, "uri", None) or getattr(node, "link", None)
            if isinstance(url, str) and url.strip().startswith(("http://", "https://")):
                title = getattr(node, "title", None) or getattr(node, "name", None) or url
                yield (url.strip(), str(title or url).strip())

            # If SDK object provides a dict-like representation, walk it.
            as_dict = None
            for attr in ("to_dict", "dict", "model_dump"):
                fn = getattr(node, attr, None)
                if callable(fn):
                    try:
                        as_dict = fn()
                    except Exception:
                        as_dict = None
                    break
            if isinstance(as_dict, dict):
                yield from _walk(as_dict)
                return

            # Fallback: walk shallow __dict__
            d = getattr(node, "__dict__", None)
            if isinstance(d, dict):
                for v in d.values():
                    yield from _walk(v)

        yield from _walk(obj)

    def _resolve_require_sources(self, config: Optional[Dict[str, Any]] = None) -> bool:
        if isinstance(config, dict) and "require_sources" in config:
            return bool(config.get("require_sources"))
        env = os.getenv("DEEP_RESEARCH_REQUIRE_SOURCES", "1").strip().lower()
        return env in ("1", "true", "yes", "on")

    async def _fallback_web_sources(
        self,
        *,
        query: str,
        config: Optional[Dict[str, Any]] = None,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Fallback sources via internal web search when provider doesn't return citations.
        Returns list of citations (number/title/url).
        """
        try:
            from app.services.web_search_service import web_search_service
        except Exception:
            return []

        cfg = config or {}
        search_focus, web_search_options = self._build_perplexity_web_search_options(cfg)
        language_filter = parse_csv_list(cfg.get("search_language_filter"), max_items=20)
        search_region = (cfg.get("search_region") or "").strip() or None
        search_city = (cfg.get("search_city") or "").strip() or None
        search_latitude = normalize_float(cfg.get("search_latitude"))
        search_longitude = normalize_float(cfg.get("search_longitude"))
        max_tokens = cfg.get("search_max_tokens")
        max_tokens_per_page = cfg.get("search_max_tokens_per_page")
        return_images = bool(cfg.get("return_images"))
        return_videos = bool(cfg.get("return_videos"))

        try:
            payload = await web_search_service.search(
                query=query,
                num_results=max_results,
                search_mode=search_focus,
                domain_filter=web_search_options.get("search_domain_filter"),
                language_filter=language_filter or None,
                recency_filter=web_search_options.get("search_recency_filter"),
                search_after_date=web_search_options.get("search_after_date"),
                search_before_date=web_search_options.get("search_before_date"),
                last_updated_after=web_search_options.get("last_updated_after"),
                last_updated_before=web_search_options.get("last_updated_before"),
                country=web_search_options.get("search_country"),
                search_region=search_region,
                search_city=search_city,
                search_latitude=search_latitude,
                search_longitude=search_longitude,
                max_tokens=max_tokens,
                max_tokens_per_page=max_tokens_per_page,
                return_images=return_images,
                return_videos=return_videos,
            )
        except Exception:
            return []

        results = payload.get("results") or []
        url_title_stream = [
            (str(r.get("url") or "").strip(), str(r.get("title") or "").strip())
            for r in results
            if isinstance(r, dict) and r.get("url")
        ]
        if not url_title_stream:
            return []
        _, numbered = stable_numbering(url_title_stream)
        return sources_to_citations(numbered)

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
        items: List[Any] = []
        if search_results:
            items.extend(search_results)
        if citations:
            items.extend(citations)
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
        elif provider == "openai":
            model = self._resolve_openai_model(config)
        effort = self._resolve_effort(config)
        points_multiplier = self._resolve_points_multiplier(config)
        require_sources = self._resolve_require_sources(config)
        fallback_max_sources = int((config or {}).get("fallback_max_sources") or 10)
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

        if provider == "openai":
            if not (self.openai_client and hasattr(self.openai_client, "responses")):
                return DeepResearchResult(text="", error="Client OpenAI não inicializado", success=False)

            openai_model = model or "o4-mini-deep-research"
            logger.info(f"🚀 Iniciando Deep Research (OpenAI {openai_model}): '{query}'")

            # Tool type names have changed over time; prefer preview if available, fallback to stable.
            tools = [{"type": "web_search_preview"}]
            reasoning = {"effort": effort, "summary": "auto"} if effort else {"summary": "auto"}
            # Reasoning models (o1, o3, o4) do not support temperature parameter
            is_reasoning_model = any(openai_model.startswith(p) for p in ("o1", "o3", "o4"))
            temp_kwargs = {} if is_reasoning_model else {"temperature": 0.2}
            try:
                resp = self.openai_client.responses.create(  # type: ignore[union-attr]
                    model=openai_model,
                    input=[{"role": "user", "content": query}],
                    tools=tools,
                    reasoning=reasoning,
                    max_output_tokens=4096,
                    **temp_kwargs,
                )
            except Exception:
                resp = self.openai_client.responses.create(  # type: ignore[union-attr]
                    model=openai_model,
                    input=[{"role": "user", "content": query}],
                    tools=[{"type": "web_search"}],
                    reasoning=reasoning,
                    max_output_tokens=4096,
                    **temp_kwargs,
                )

            # "All sources consulted" (best-effort): union of url_citations + tool-result URLs.
            text, cited_sources = extract_perplexity("openai", resp)
            if not text:
                text = getattr(resp, "output_text", "") or ""

            seen: Dict[str, str] = {}  # url -> title (insertion order)
            for s in cited_sources or []:
                url = getattr(s, "url", "") if not isinstance(s, dict) else (s.get("url") or "")
                title = getattr(s, "title", "") if not isinstance(s, dict) else (s.get("title") or "")
                if url and url not in seen:
                    seen[str(url)] = str(title or url)

            output = getattr(resp, "output", None)
            if output is None and isinstance(resp, dict):
                output = resp.get("output")
            for url, title in self._iter_url_title_pairs(output):
                if url and url not in seen:
                    seen[url] = title or url

            _, numbered_sources = stable_numbering([(u, t) for u, t in seen.items()])
            citations = sources_to_citations(numbered_sources)
            if require_sources and not citations:
                citations = await self._fallback_web_sources(
                    query=query,
                    config=config,
                    max_results=fallback_max_sources,
                )
                if not citations:
                    return DeepResearchResult(text=text or "", error="Não foi possível obter fontes confiáveis.", success=False)

            record_api_call(
                kind="deep_research",
                provider="openai",
                model=openai_model,
                success=bool(text),
                meta={"effort": effort, "points_multiplier": points_multiplier},
            )
            if text:
                job_manager.cache_deep_research(
                    query=cache_query,
                    report=text,
                    sources=citations,
                    thinking_steps=[],
                )
            return DeepResearchResult(
                text=text or "",
                log="",
                success=bool(text),
                sources=citations,
                thinking_steps=[],
                from_cache=False,
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
                    # Prefer grounding_chunks (all consulted sources) over grounding_supports (cited subset).
                    url_title_stream: List[Tuple[str, str]] = []
                    grounding = getattr(resp, 'grounding_metadata', None) or getattr(resp, 'groundingMetadata', None)
                    if grounding:
                        chunks = (
                            getattr(grounding, 'grounding_chunks', None) or
                            getattr(grounding, 'groundingChunks', None) or []
                        )
                        for chunk in chunks:
                            web = getattr(chunk, 'web', None)
                            if not web:
                                continue
                            url = str(getattr(web, 'uri', '') or '').strip()
                            title = str(getattr(web, 'title', '') or url).strip()
                            if url:
                                url_title_stream.append((url, title or url))
                    _, numbered_sources = stable_numbering(url_title_stream)
                    citations = sources_to_citations(numbered_sources)

                    text, _sources = extract_perplexity("gemini", resp)
                    if require_sources and not citations:
                        citations = await self._fallback_web_sources(
                            query=query,
                            config=config,
                            max_results=fallback_max_sources,
                        )
                        if not citations:
                            return DeepResearchResult(text=text or "", error="Não foi possível obter fontes confiáveis.", success=False)

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
                            sources=citations,
                            thinking_steps=[],
                        )
                    return DeepResearchResult(
                        text=text or "",
                        log="",
                        success=bool(text),
                        sources=citations,
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

                if require_sources and not sources:
                    sources = await self._fallback_web_sources(
                        query=query,
                        config=config,
                        max_results=fallback_max_sources,
                    )
                    if not sources:
                        return DeepResearchResult(text=final_report, error="Não foi possível obter fontes confiáveis.", success=False)

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
                if require_sources and not sources:
                    sources = await self._fallback_web_sources(
                        query=query,
                        config=config,
                        max_results=fallback_max_sources,
                    )
                    if not sources:
                        return DeepResearchResult(text=final_text, error="Não foi possível obter fontes confiáveis.", success=False)
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
        elif provider == "openai":
            model = self._resolve_openai_model(config)
        effort = self._resolve_effort(config)
        points_multiplier = self._resolve_points_multiplier(config)
        require_sources = self._resolve_require_sources(config)
        fallback_max_sources = int((config or {}).get("fallback_max_sources") or 10)
        cache_query = self._cache_query_key(provider, model, query)

        # 1. Try Cache
        cached = job_manager.get_cached_deep_research(cache_query)
        if cached:
            yield {"type": "cache_hit", "key": cached['cache_key']}
            # Keep the Activity Panel consistent: even on cache hits, emit step.* and sources.
            step_id = _generate_step_id()
            yield {"type": "step.start", "step_name": "Pesquisando", "step_id": step_id}

            sources = cached.get("sources") or []
            if not isinstance(sources, list):
                sources = []
            sources = [s for s in sources if isinstance(s, dict)]

            if require_sources and not any(str(s.get("url") or "").strip() for s in sources):
                sources = await self._fallback_web_sources(
                    query=query,
                    config=config,
                    max_results=fallback_max_sources,
                )

            if require_sources and not any(str(s.get("url") or "").strip() for s in (sources or [])):
                yield {"type": "step.done", "step_id": step_id}
                yield {"type": "error", "message": "Não foi possível obter fontes confiáveis."}
                return

            for s in sources or []:
                url = str(s.get("url") or "").strip()
                title = str(s.get("title") or url).strip()
                if not url:
                    continue
                yield {
                    "type": "step.add_source",
                    "step_id": step_id,
                    "source": {"title": title or url, "url": url},
                }
            yield {"type": "step.done", "step_id": step_id}
            # Replay thinking
            for step in cached['thinking_steps']:
                yield {"type": "thinking", "text": step['text'], "from_cache": True}
                # Artificial delay for UI pacing if needed, but skipped for speed
            
            yield {"type": "content", "text": cached['report'], "from_cache": True}
            yield {"type": "done", "sources": sources}
            return

        if provider == "openai":
            if not (self.openai_client and hasattr(self.openai_client, "responses")):
                yield {"type": "error", "message": "Client OpenAI não inicializado"}
                return

            step_id = _generate_step_id()
            yield {"type": "step.start", "step_name": "Pesquisando", "step_id": step_id}
            yield {"type": "thinking", "text": f"Iniciando pesquisa via OpenAI ({model}).", "from_cache": False}

            final_report = ""
            thinking_steps: List[Dict[str, Any]] = []
            # Preserve insertion order for stable numbering.
            seen_sources: Dict[str, str] = {}
            openai_search_active = False
            final_response_obj: Any = None

            def _add_source(url: str, title: str) -> None:
                key = (url or "").strip()
                if not key or key in seen_sources:
                    return
                seen_sources[key] = (title or url).strip() or key
                # Normalize to the same shape used in step.add_source
                yield_event = {"type": "step.add_source", "step_id": step_id, "source": {"title": title or url, "url": url}}
                # We can't yield from nested function directly; stash as attribute.
                pending_events.append(yield_event)

            pending_events: List[Dict[str, Any]] = []

            def _drain_pending() -> List[Dict[str, Any]]:
                nonlocal pending_events
                if not pending_events:
                    return []
                evs = pending_events
                pending_events = []
                return evs

            try:
                reasoning = {"effort": effort, "summary": "auto"} if effort else {"summary": "auto"}
                is_reasoning_model = any((model or "").startswith(p) for p in ("o1", "o3", "o4"))
                temp_kwargs = {} if is_reasoning_model else {"temperature": 0.2}

                # Tool name variants differ across model families; prefer preview tool, fallback to stable.
                try:
                    stream = self.openai_client.responses.create(  # type: ignore[union-attr]
                        model=model,
                        input=[{"role": "user", "content": query}],
                        tools=[{"type": "web_search_preview"}],
                        reasoning=reasoning,
                        max_output_tokens=4096,
                        stream=True,
                        **temp_kwargs,
                    )
                except Exception:
                    stream = self.openai_client.responses.create(  # type: ignore[union-attr]
                        model=model,
                        input=[{"role": "user", "content": query}],
                        tools=[{"type": "web_search"}],
                        reasoning=reasoning,
                        **temp_kwargs,
                        max_output_tokens=4096,
                        stream=True,
                    )

                record_api_call(
                    kind="deep_research",
                    provider="openai",
                    model=model,
                    success=True,
                    meta={"effort": effort, "points_multiplier": points_multiplier, "stream": True},
                )

                for ev in stream:
                    ev_type = getattr(ev, "type", "") or ""
                    maybe_resp = getattr(ev, "response", None)
                    if maybe_resp is not None:
                        final_response_obj = maybe_resp

                    # Tool progress events
                    if ev_type in ("response.web_search_call.in_progress", "response.web_search_call.searching"):
                        if not openai_search_active:
                            openai_search_active = True
                            yield {"type": "step.start", "step_name": "Pesquisando na web", "step_id": f"{step_id}_web"}
                        q = getattr(ev, "query", None) or getattr(ev, "q", None)
                        if q:
                            yield {"type": "step.add_query", "step_id": f"{step_id}_web", "query": str(q)[:200]}
                        continue

                    if ev_type == "response.web_search_call.completed":
                        if openai_search_active:
                            yield {"type": "step.done", "step_id": f"{step_id}_web"}
                            openai_search_active = False
                        continue

                    # Reasoning summary deltas (good for UI step logs)
                    if ev_type == "response.reasoning_summary_text.delta":
                        delta = getattr(ev, "delta", None)
                        if delta:
                            text = str(delta)
                            thinking_steps.append({"text": text, "timestamp": time.time()})
                            yield {"type": "thinking", "text": text, "from_cache": False}
                        continue

                    # Main content deltas
                    if ev_type == "response.output_text.delta":
                        delta = getattr(ev, "delta", None)
                        if delta:
                            text = str(delta)
                            final_report += text
                            yield {"type": "content", "text": text, "from_cache": False}
                        continue

                    # Inline citations / annotations (best-effort extraction)
                    if ev_type == "response.output_text.annotation.added":
                        ann = getattr(ev, "annotation", None) or getattr(ev, "annotations", None)
                        url = None
                        title = None
                        if isinstance(ann, dict):
                            url = ann.get("url") or ann.get("uri") or ann.get("source")
                            title = ann.get("title") or ann.get("name")
                        else:
                            url = getattr(ann, "url", None) or getattr(ann, "uri", None) or getattr(ann, "source", None)
                            title = getattr(ann, "title", None) or getattr(ann, "name", None)
                        if url:
                            _add_source(str(url), str(title or url))
                            for pending in _drain_pending():
                                yield pending
                        continue

                    if ev_type in ("response.completed", "response.failed", "response.canceled"):
                        maybe_resp = getattr(ev, "response", None)
                        if maybe_resp is not None:
                            final_response_obj = maybe_resp
                        break

                # Best-effort: extract citations (best titles) + tool-result URLs from the full Responses object.
                if final_response_obj is not None:
                    try:
                        _text, cited_sources = extract_perplexity("openai", final_response_obj)
                        for s in cited_sources or []:
                            _add_source(getattr(s, "url", ""), getattr(s, "title", "") or getattr(s, "url", ""))
                        for pending in _drain_pending():
                            yield pending
                    except Exception:
                        pass

                    try:
                        output = getattr(final_response_obj, "output", None)
                        if output is None and isinstance(final_response_obj, dict):
                            output = final_response_obj.get("output")
                        for url, title in self._iter_url_title_pairs(output):
                            _add_source(url, title)
                        for pending in _drain_pending():
                            yield pending
                    except Exception:
                        pass

                url_title_stream = [(url, title) for url, title in seen_sources.items()]
                _, numbered_sources = stable_numbering(url_title_stream)
                sources = sources_to_citations(numbered_sources)
                if require_sources and not sources:
                    sources = await self._fallback_web_sources(
                        query=query,
                        config=config,
                        max_results=fallback_max_sources,
                    )
                    if sources:
                        for s in sources:
                            url = str(s.get("url") or "").strip()
                            title = str(s.get("title") or url).strip()
                            if url:
                                yield {
                                    "type": "step.add_source",
                                    "step_id": step_id,
                                    "source": {"title": title or url, "url": url},
                                }
                    else:
                        yield {"type": "step.done", "step_id": step_id}
                        yield {"type": "error", "message": "Não foi possível obter fontes confiáveis."}
                        return
                if final_report:
                    job_manager.cache_deep_research(
                        query=cache_query,
                        report=final_report,
                        sources=sources,
                        thinking_steps=thinking_steps,
                    )
                yield {"type": "step.done", "step_id": step_id}
                yield {"type": "done", "sources": sources}
                return

            except Exception as e:
                record_api_call(
                    kind="deep_research",
                    provider="openai",
                    model=model,
                    success=False,
                    meta={"effort": effort, "points_multiplier": points_multiplier, "stream": True},
                )
                logger.error(f"❌ Stream Deep Research Error (OpenAI): {e}")
                yield {"type": "step.done", "step_id": step_id}
                yield {"type": "error", "message": str(e)}
                return

        if provider == "google":
            if not self.google_client:
                yield {"type": "error", "message": "Client Google GenAI não inicializado"}
                return
            google_model = model or "deep-research-pro-preview-12-2025"
            if not self._is_google_deep_research_agent(google_model):
                step_id = _generate_step_id()
                yield {"type": "step.start", "step_name": "Pesquisando", "step_id": step_id}
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

                    # Extract grounding metadata for queries and sources.
                    # For "all consulted sources", prefer grounding_chunks (can include more than cited supports).
                    url_title_stream: List[Tuple[str, str]] = []
                    grounding = getattr(resp, 'grounding_metadata', None) or getattr(resp, 'groundingMetadata', None)
                    if grounding:
                        search_queries = (
                            getattr(grounding, 'web_search_queries', None) or
                            getattr(grounding, 'webSearchQueries', None) or []
                        )
                        for q in search_queries:
                            if q:
                                yield {"type": "step.add_query", "step_id": step_id, "query": str(q)[:200]}

                        chunks = (
                            getattr(grounding, 'grounding_chunks', None) or
                            getattr(grounding, 'groundingChunks', None) or []
                        )
                        for chunk in chunks:
                            web = getattr(chunk, 'web', None)
                            if web:
                                url = str(getattr(web, 'uri', '') or '').strip()
                                title = str(getattr(web, 'title', '') or url).strip()
                                if url:
                                    url_title_stream.append((url, title or url))
                                    yield {"type": "step.add_source", "step_id": step_id, "source": {"title": title, "url": url}}

                    text, _sources = extract_perplexity("gemini", resp)
                    _, numbered_sources = stable_numbering(url_title_stream)
                    citations = sources_to_citations(numbered_sources)
                    if require_sources and not citations:
                        citations = await self._fallback_web_sources(
                            query=query,
                            config=config,
                            max_results=fallback_max_sources,
                        )
                        if citations:
                            for s in citations:
                                url = str(s.get("url") or "").strip()
                                title = str(s.get("title") or url).strip()
                                if url:
                                    yield {
                                        "type": "step.add_source",
                                        "step_id": step_id,
                                        "source": {"title": title or url, "url": url},
                                    }
                        else:
                            yield {"type": "step.done", "step_id": step_id}
                            yield {"type": "error", "message": "Não foi possível obter fontes confiáveis."}
                            return
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
                            sources=citations,
                            thinking_steps=[],
                        )
                    yield {"type": "step.done", "step_id": step_id}
                    yield {"type": "content", "text": text or ""}
                    yield {"type": "done", "sources": citations}
                except Exception as e:
                    record_api_call(
                        kind="deep_research",
                        provider="google",
                        model=google_model,
                        success=False,
                        meta={"effort": effort, "points_multiplier": points_multiplier},
                    )
                    logger.error(f"❌ Falha crítica no Deep Research (Google {google_model}): {e}")
                    yield {"type": "step.done", "step_id": step_id}
                    yield {"type": "error", "message": str(e)}
                return

            step_id = _generate_step_id()
            try:
                yield {"type": "step.start", "step_name": "Pesquisando", "step_id": step_id}

                final_report = ""
                full_thinking = []
                seen_queries: set = set()
                seen_sources: set = set()
                url_title_stream: List[Tuple[str, str]] = []
                interaction_id: Optional[str] = None
                last_event_id: Optional[str] = None
                resume_attempts = 0

                # Patterns to detect search queries in thinking text
                query_patterns = [
                    r'(?:Buscando|Pesquisando|Searching|Looking for|Querying)[:\s]+["\']?([^"\']+)["\']?',
                    r'(?:Query|Busca|Search)[:\s]+["\']?([^"\']+)["\']?',
                ]
                url_pattern = re.compile(r'https?://[^\s<>"\']+')

                def _extract_event_id(ev: Any) -> Optional[str]:
                    for key in ("event_id", "eventId", "id"):
                        value = getattr(ev, key, None)
                        if value:
                            return str(value)
                    return None

                def _extract_interaction_id(ev: Any) -> Optional[str]:
                    for key in ("interaction_id", "interactionId", "session_id", "sessionId", "id"):
                        value = getattr(ev, key, None)
                        if value:
                            return str(value)
                    return None

                def _create_kwargs() -> Dict[str, Any]:
                    try:
                        sig = inspect.signature(self.google_client.interactions.create)
                        allowed = set(sig.parameters)
                    except Exception:
                        allowed = set()
                    # background execution is more reliable when stored; store=True is default today,
                    # but we pass it explicitly when supported.
                    return {"store": True} if "store" in allowed else {}

                def _get_resume_kwargs() -> Dict[str, Any]:
                    if not last_event_id:
                        return {}
                    try:
                        sig = inspect.signature(self.google_client.interactions.get)
                        allowed = set(sig.parameters)
                    except Exception:
                        allowed = set()
                    kwargs: Dict[str, Any] = {}
                    if "stream" in allowed:
                        kwargs["stream"] = True
                    if "last_event_id" in allowed:
                        kwargs["last_event_id"] = last_event_id
                    elif "lastEventId" in allowed:
                        kwargs["lastEventId"] = last_event_id
                    return kwargs

                while True:
                    if (
                        resume_attempts > 0
                        and interaction_id
                        and last_event_id
                        and hasattr(self.google_client.interactions, "get")
                    ):
                        interaction = self.google_client.interactions.get(interaction_id, **_get_resume_kwargs())
                    else:
                        interaction = self.google_client.interactions.create(
                            input=query,
                            agent=google_model,
                            background=True,
                            stream=True,
                            agent_config={"type": "deep-research", "thinking_summaries": "auto"},
                            **_create_kwargs(),
                        )

                    if interaction_id is None:
                        interaction_id = (
                            getattr(interaction, "id", None) or getattr(interaction, "interaction_id", None)
                        )
                        if interaction_id:
                            interaction_id = str(interaction_id)

                    record_api_call(
                        kind="deep_research",
                        provider="google",
                        model=google_model,
                        success=True,
                        meta={"effort": effort, "points_multiplier": points_multiplier},
                    )

                    try:
                        for event in interaction:
                            ev_id = _extract_event_id(event)
                            if ev_id:
                                last_event_id = ev_id
                            ev_interaction_id = _extract_interaction_id(event)
                            if ev_interaction_id:
                                interaction_id = ev_interaction_id

                            if event.type == "thinking":
                                text = event.text or ""

                                # Extract search queries from thinking
                                for pattern in query_patterns:
                                    matches = re.findall(pattern, text, re.IGNORECASE)
                                    for match in matches:
                                        query_text = str(match).strip()[:200]
                                        if query_text and query_text not in seen_queries:
                                            seen_queries.add(query_text)
                                            yield {"type": "step.add_query", "step_id": step_id, "query": query_text}

                                # Extract URLs as sources (fallback; reliable sources come from interaction outputs below)
                                urls = url_pattern.findall(text)
                                for url in urls:
                                    url = url.strip()
                                    if url and url not in seen_sources:
                                        seen_sources.add(url)
                                        url_title_stream.append((url, url))
                                        yield {"type": "step.add_source", "step_id": step_id, "source": {"title": url, "url": url}}

                                full_thinking.append({"text": text, "timestamp": time.time()})
                                yield {"type": "thinking", "text": text, "from_cache": False}
                            elif event.type == "content":
                                final_report += event.text
                                yield {"type": "content", "text": event.text, "from_cache": False}
                            elif event.type == "interaction.end":
                                break
                        break
                    except Exception as stream_exc:
                        if resume_attempts < 1 and interaction_id and last_event_id:
                            resume_attempts += 1
                            logger.warning(
                                "⚠️ Stream Deep Research interrompido; tentando retomar (interaction_id=%s, last_event_id=%s)",
                                interaction_id,
                                last_event_id,
                            )
                            continue
                        raise stream_exc

                # Best-effort: fetch stored interaction outputs and extract tool-result URLs.
                if interaction_id and hasattr(self.google_client.interactions, "get"):
                    try:
                        interaction_obj = self.google_client.interactions.get(interaction_id)
                        outputs = getattr(interaction_obj, "outputs", None)
                        if outputs is None and isinstance(interaction_obj, dict):
                            outputs = interaction_obj.get("outputs")
                        for url, title in self._iter_url_title_pairs(outputs):
                            if url and url not in seen_sources:
                                seen_sources.add(url)
                                url_title_stream.append((url, title or url))
                                yield {
                                    "type": "step.add_source",
                                    "step_id": step_id,
                                    "source": {"title": title or url, "url": url},
                                }
                    except Exception:
                        pass

                _, numbered_sources = stable_numbering(url_title_stream)
                citations = sources_to_citations(numbered_sources)
                if require_sources and not citations:
                    citations = await self._fallback_web_sources(
                        query=query,
                        config=config,
                        max_results=fallback_max_sources,
                    )
                    if citations:
                        for s in citations:
                            url = str(s.get("url") or "").strip()
                            title = str(s.get("title") or url).strip()
                            if url and url not in seen_sources:
                                seen_sources.add(url)
                                yield {
                                    "type": "step.add_source",
                                    "step_id": step_id,
                                    "source": {"title": title or url, "url": url},
                                }
                    else:
                        yield {"type": "step.done", "step_id": step_id}
                        yield {"type": "error", "message": "Não foi possível obter fontes confiáveis."}
                        return

                if final_report:
                    job_manager.cache_deep_research(
                        query=cache_query,
                        report=final_report,
                        sources=citations,
                        thinking_steps=full_thinking
                    )

                yield {"type": "step.done", "step_id": step_id}
                yield {"type": "done", "sources": citations}
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
                yield {"type": "step.done", "step_id": step_id}
                yield {"type": "error", "message": str(e)}
                return

        if provider == "perplexity":
            if not (PERPLEXITY_AVAILABLE and self.perplexity_api_key and AsyncPerplexity):
                yield {"type": "error", "message": "Perplexity não configurada (PERPLEXITY_API_KEY/perplexityai)."}
                return

            step_id = _generate_step_id()
            yield {"type": "step.start", "step_name": "Pesquisando", "step_id": step_id}
            yield {"type": "thinking", "text": f"Iniciando pesquisa via Perplexity ({model}).", "from_cache": False}

            final_report = ""
            thinking_steps = [{"text": f"Iniciando pesquisa via Perplexity ({model}).", "timestamp": time.time()}]
            search_results: List[Any] = []
            citations: List[Any] = []
            emitted_sources: set = set()

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
                            for result in chunk_results:
                                url, title = self._to_url_title(result)
                                if url and url not in emitted_sources:
                                    emitted_sources.add(url)
                                    yield {"type": "step.add_source", "step_id": step_id, "source": {"title": title, "url": url}}
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
                            for result in chunk_results:
                                url, title = self._to_url_title(result)
                                if url and url not in emitted_sources:
                                    emitted_sources.add(url)
                                    yield {"type": "step.add_source", "step_id": step_id, "source": {"title": title, "url": url}}
                            search_results.extend(chunk_results)

                        chunk_citations = _get(chunk, "citations", None)
                        if isinstance(chunk_citations, list) and chunk_citations:
                            citations.extend(chunk_citations)

                sources = self._extract_perplexity_sources(search_results=search_results, citations=citations)
                if require_sources and not sources:
                    sources = await self._fallback_web_sources(
                        query=query,
                        config=config,
                        max_results=fallback_max_sources,
                    )
                    if sources:
                        for s in sources:
                            url = str(s.get("url") or "").strip()
                            title = str(s.get("title") or url).strip()
                            if url and url not in emitted_sources:
                                emitted_sources.add(url)
                                yield {
                                    "type": "step.add_source",
                                    "step_id": step_id,
                                    "source": {"title": title or url, "url": url},
                                }
                    else:
                        yield {"type": "step.done", "step_id": step_id}
                        yield {"type": "error", "message": "Não foi possível obter fontes confiáveis."}
                        return

                if final_report:
                    job_manager.cache_deep_research(
                        query=cache_query,
                        report=final_report,
                        sources=sources,
                        thinking_steps=thinking_steps,
                    )

                yield {"type": "step.done", "step_id": step_id}
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
                yield {"type": "step.done", "step_id": step_id}
                yield {"type": "error", "message": str(e)}
                return

        yield {"type": "error", "message": "Nenhum provider de Deep Research disponível."}

deep_research_service = DeepResearchService()
