"""
Deep Research Hard Mode — Agentic Multi-provider Orchestrated Research.

Claude atua como agente orquestrador com loop agentico completo:
- Decide quais providers pesquisar e com quais queries
- Analisa resultados e decide se precisa de mais dados
- Pode pedir input/aprovacao do usuario em pontos criticos
- Itera ate ficar satisfeito com a qualidade
- Gera estudo profissional com citacoes ABNT

Tools disponiveis para o agente:
- search_gemini: Pesquisa via Google Gemini Deep Research
- search_perplexity: Pesquisa via Perplexity Sonar Deep Research
- search_openai: Pesquisa via OpenAI Deep Research
- search_rag_global: Busca em legislacao, jurisprudencia, sumulas, pecas
- search_rag_local: Busca em documentos do caso/processo
- analyze_results: Analisa e consolida resultados coletados
- ask_user: Pausa e pede input/aprovacao do usuario
- generate_study_section: Gera uma secao do estudo final
- verify_citations: Verifica se citacoes tem fonte valida
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from app.services.ai.deep_research_service import DeepResearchService, DeepResearchResult
from app.services.api_call_tracker import record_api_call
from app.services.ai.citations.base import stable_numbering, sources_to_citations

logger = logging.getLogger("DeepResearchHardService")

# ---------------------------------------------------------------------------
# Optional anthropic SDK
# ---------------------------------------------------------------------------
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    anthropic = None  # type: ignore[assignment]
    ANTHROPIC_AVAILABLE = False
    logger.warning("anthropic SDK nao instalado. Hard Research agentico indisponivel.")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ALL_PROVIDERS: List[str] = ["gemini", "perplexity", "openai", "rag_global", "rag_local"]
DEFAULT_PROVIDER_TIMEOUT_S = 120
MAX_AGENT_ITERATIONS = 15

AGENT_SYSTEM_PROMPT = """\
Voce e um pesquisador juridico senior brasileiro, atuando como agente autonomo de pesquisa profunda.

## Seu Objetivo
Produzir um ESTUDO DE PESQUISA APROFUNDADA completo, com capa, sumario, citacoes ABNT e referencias bibliograficas.

## Ferramentas Disponiveis

Voce tem acesso a estas ferramentas para conduzir sua pesquisa:

1. **search_gemini** — Pesquisa web profunda via Google Gemini
2. **search_perplexity** — Pesquisa academica/juridica via Perplexity Sonar
3. **search_openai** — Analise profunda via OpenAI Deep Research
4. **search_rag_global** — Busca em bases internas: legislacao, jurisprudencia, sumulas, pecas modelo
5. **search_rag_local** — Busca em documentos do caso/processo do usuario
6. **analyze_results** — Consolida e analisa os resultados coletados ate o momento
7. **ask_user** — Pausa para pedir input, esclarecimento ou aprovacao do usuario
8. **generate_study_section** — Gera uma secao do estudo final
9. **verify_citations** — Verifica se afirmacoes tem fontes validas

## Estrategia de Pesquisa

1. PRIMEIRO: Analise o tema e planeje quais fontes consultar
2. SEGUNDO: Execute pesquisas em paralelo (chame multiplas tools de search)
3. TERCEIRO: Analise os resultados com analyze_results
4. QUARTO: Se os resultados forem insuficientes, pesquise mais com queries refinadas
5. QUINTO: Se houver ambiguidade ou decisao critica, use ask_user
6. SEXTO: Gere o estudo secao por secao com generate_study_section
7. SETIMO: Verifique citacoes com verify_citations

## Regras

- Use PELO MENOS 2 fontes de pesquisa diferentes antes de gerar o estudo
- Toda afirmacao juridica DEVE ter citacao [N]
- Se uma fonte falhar, tente outra — nao desista facilmente
- Prefira fontes primarias (legislacao, decisoes) sobre secundarias
- O estudo deve ter: CAPA, SUMARIO, INTRODUCAO, DESENVOLVIMENTO, CONCLUSAO, REFERENCIAS
- Formato ABNT para todas as referencias
- Se o usuario pediu algo especifico, priorize isso
- Voce pode iterar: pesquisar, analisar, pesquisar mais, ate ter material suficiente
"""

# ---------------------------------------------------------------------------
# Tool definitions for Claude API
# ---------------------------------------------------------------------------

AGENT_TOOLS = [
    {
        "name": "search_gemini",
        "description": "Pesquisa web profunda via Google Gemini Deep Research. Boa para contexto geral, noticias, artigos recentes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Query de pesquisa otimizada para busca web"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_perplexity",
        "description": "Pesquisa academica e juridica via Perplexity Sonar Deep Research. Boa para papers, decisoes, artigos especializados.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Query focada em fontes academicas/juridicas"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_openai",
        "description": "Analise profunda via OpenAI Deep Research. Bom para reasoning complexo e analise comparativa.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Query analitica com foco em reasoning"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_rag_global",
        "description": "Busca em bases internas consolidadas: legislacao federal/estadual, jurisprudencia (STF, STJ, TRFs, TJs), sumulas, pecas modelo aprovadas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Termos legais especificos (artigos, leis, tribunais)"},
                "scope": {
                    "type": "string",
                    "enum": ["all", "lei", "juris", "sei", "pecas_modelo"],
                    "description": "Escopo da busca (default: all)",
                },
                "top_k": {"type": "integer", "description": "Numero maximo de resultados (default: 10)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_rag_local",
        "description": "Busca em documentos do caso/processo do usuario. Retorna trechos relevantes dos autos, contratos, laudos, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Query contextualizada ao caso"},
                "top_k": {"type": "integer", "description": "Numero maximo de resultados (default: 5)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "analyze_results",
        "description": "Consolida e analisa todos os resultados de pesquisa coletados ate o momento. Retorna resumo, lacunas identificadas e sugestoes de aprofundamento.",
        "input_schema": {
            "type": "object",
            "properties": {
                "focus": {"type": "string", "description": "Aspecto especifico para focar na analise (opcional)"},
            },
        },
    },
    {
        "name": "ask_user",
        "description": "Pausa a pesquisa e envia uma pergunta ao usuario. Use quando precisar de esclarecimento, confirmacao de direcionamento, ou aprovacao antes de continuar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Pergunta clara e especifica para o usuario"},
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Opcoes de resposta sugeridas (opcional)",
                },
                "context": {"type": "string", "description": "Contexto breve sobre por que esta perguntando"},
            },
            "required": ["question"],
        },
    },
    {
        "name": "generate_study_section",
        "description": "Gera uma secao do estudo final usando todo o material coletado. Chame uma vez por secao principal.",
        "input_schema": {
            "type": "object",
            "properties": {
                "section_title": {"type": "string", "description": "Titulo da secao (ex: '1. Introducao', '2. Analise Jurisprudencial')"},
                "instructions": {"type": "string", "description": "Instrucoes especificas para esta secao"},
                "include_citations": {"type": "boolean", "description": "Se deve incluir citacoes ABNT (default: true)"},
            },
            "required": ["section_title"],
        },
    },
    {
        "name": "verify_citations",
        "description": "Verifica se as citacoes no texto gerado tem fontes validas nos resultados da pesquisa.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Texto com citacoes [N] para verificar"},
            },
            "required": ["text"],
        },
    },
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ProviderResult:
    """Resultado de um unico provider de pesquisa."""
    provider: str
    text: str
    sources: List[Dict[str, Any]]
    thinking_steps: List[str]
    success: bool
    error: Optional[str] = None
    elapsed_ms: int = 0


@dataclass
class MergedResearch:
    """Resultado consolidado de todos os providers apos merge e dedup."""
    combined_text: str
    all_sources: List[Dict[str, Any]]
    deduplicated_sources: List[Dict[str, Any]]
    provider_summaries: Dict[str, str]
    total_before_dedup: int
    total_after_dedup: int


@dataclass
class AgentState:
    """Estado acumulado do agente durante a pesquisa."""
    collected_results: Dict[str, ProviderResult] = field(default_factory=dict)
    all_sources: List[Dict[str, Any]] = field(default_factory=list)
    generated_sections: List[Dict[str, str]] = field(default_factory=list)
    iteration: int = 0
    waiting_for_user: bool = False
    user_question: Optional[str] = None
    user_response: Optional[str] = None
    study_text: str = ""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class DeepResearchHardService:
    """
    Agente de pesquisa profunda multi-provider (Hard Mode).

    Claude opera como agente autonomo com loop agentico completo:
    - Decide quais ferramentas usar e quando
    - Itera ate ter material suficiente
    - Pode pedir input do usuario
    - Gera estudo profissional secao por secao
    """

    def __init__(self) -> None:
        self.deep_research = DeepResearchService()
        self._claude_client: Optional[Any] = None
        self._claude_model = os.getenv(
            "HARD_RESEARCH_CLAUDE_MODEL", "claude-sonnet-4-20250514"
        )
        if ANTHROPIC_AVAILABLE:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                try:
                    self._claude_client = anthropic.AsyncAnthropic(api_key=api_key)
                    logger.info("DeepResearchHardService: Claude agentic client inicializado.")
                except Exception as exc:
                    logger.warning("Falha ao inicializar Anthropic client: %s", exc)
            else:
                logger.warning("ANTHROPIC_API_KEY nao configurada.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def stream_hard_research(
        self,
        query: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Loop agentico principal. Claude decide autonomamente o que fazer.

        Yields SSE events para o frontend acompanhar em tempo real.
        Suporta pausa para input do usuario via ask_user tool.
        """
        cfg = config or {}
        enabled_providers = cfg.get("providers", ALL_PROVIDERS)
        state = AgentState()
        start_time = time.time()

        yield {
            "type": "hard_research_start",
            "providers": enabled_providers,
            "mode": "agentic",
        }

        if not self._claude_client:
            yield {"type": "error", "message": "Claude client nao disponivel para modo agentico"}
            return

        # Filter tools by enabled providers
        available_tools = self._filter_tools(enabled_providers)

        # Build initial user message
        user_msg = self._build_initial_message(query, cfg, enabled_providers)

        messages: List[Dict[str, Any]] = [
            {"role": "user", "content": user_msg},
        ]

        # Agent loop
        for iteration in range(MAX_AGENT_ITERATIONS):
            state.iteration = iteration + 1

            yield {
                "type": "agent_iteration",
                "iteration": state.iteration,
                "max_iterations": MAX_AGENT_ITERATIONS,
            }

            try:
                response = await self._claude_client.messages.create(
                    model=self._claude_model,
                    max_tokens=16384,
                    temperature=0.3,
                    system=AGENT_SYSTEM_PROMPT,
                    tools=available_tools,
                    messages=messages,
                )

                record_api_call(
                    kind="hard_research_agent",
                    provider="anthropic",
                    model=self._claude_model,
                    success=True,
                    meta={"iteration": state.iteration},
                )

            except Exception as exc:
                logger.error("Agent iteration %d failed: %s", state.iteration, exc)
                yield {"type": "error", "message": f"Agent error: {str(exc)}"}
                break

            # Process response content blocks
            tool_results: List[Dict[str, Any]] = []
            has_tool_use = False

            for block in response.content:
                if block.type == "text":
                    # Agent is communicating — emit as thinking
                    text = block.text.strip()
                    if text:
                        yield {
                            "type": "agent_thinking",
                            "text": text,
                            "iteration": state.iteration,
                        }

                elif block.type == "tool_use":
                    has_tool_use = True
                    tool_name = block.name
                    tool_input = block.input or {}
                    tool_use_id = block.id

                    yield {
                        "type": "agent_tool_call",
                        "tool": tool_name,
                        "input": _safe_serialize(tool_input),
                        "iteration": state.iteration,
                    }

                    # Execute tool
                    tool_output, extra_events = await self._execute_tool(
                        tool_name, tool_input, state, cfg
                    )

                    # Emit any extra events from tool execution
                    for evt in extra_events:
                        yield evt

                    # Check for user interaction
                    if tool_name == "ask_user" and state.waiting_for_user:
                        yield {
                            "type": "agent_ask_user",
                            "question": tool_input.get("question", ""),
                            "options": tool_input.get("options"),
                            "context": tool_input.get("context", ""),
                        }
                        # The frontend will send user response back
                        # For now, we continue with a placeholder
                        # In production, this would pause and wait
                        state.waiting_for_user = False

                    yield {
                        "type": "agent_tool_result",
                        "tool": tool_name,
                        "success": "error" not in str(tool_output).lower()[:50],
                        "summary": _truncate(str(tool_output), 200),
                        "iteration": state.iteration,
                    }

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": str(tool_output)[:30000],
                    })

                    # If this is generate_study_section, stream the content
                    if tool_name == "generate_study_section":
                        section_text = str(tool_output)
                        state.study_text += section_text + "\n\n"
                        # Stream in chunks for real-time UI
                        chunk_size = 100
                        for i in range(0, len(section_text), chunk_size):
                            chunk = section_text[i:i + chunk_size]
                            yield {
                                "type": "study_token",
                                "delta": chunk,
                                "section": tool_input.get("section_title", ""),
                            }

            # Add assistant response to messages
            messages.append({"role": "assistant", "content": response.content})

            # If tool calls were made, add results and continue loop
            if has_tool_use and tool_results:
                messages.append({"role": "user", "content": tool_results})
                continue

            # If stop_reason is end_turn (no more tool calls), agent is done
            if response.stop_reason == "end_turn":
                logger.info("Agent finished after %d iterations", state.iteration)
                break

        # Final merge of all collected sources
        yield {"type": "merge_start"}
        merged = self._merge_results(state.collected_results)
        yield {
            "type": "merge_done",
            "total_sources": merged.total_before_dedup,
            "deduplicated": merged.total_after_dedup,
        }

        # Emit study outline from generated sections
        if state.generated_sections:
            yield {
                "type": "study_outline",
                "sections": [s["title"] for s in state.generated_sections],
            }

        elapsed_total = int((time.time() - start_time) * 1000)
        yield {
            "type": "study_done",
            "total_chars": len(state.study_text),
            "sources_count": merged.total_after_dedup,
            "iterations": state.iteration,
            "elapsed_ms": elapsed_total,
        }

        logger.info(
            "Hard Research agentico concluido: %d iteracoes, %d fontes, %d chars, %dms",
            state.iteration, merged.total_after_dedup, len(state.study_text), elapsed_total,
        )

    # ------------------------------------------------------------------
    # Tool Execution
    # ------------------------------------------------------------------

    async def _execute_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        state: AgentState,
        config: Dict[str, Any],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Execute a tool call and return (result_text, extra_sse_events).
        """
        events: List[Dict[str, Any]] = []

        if tool_name == "search_gemini":
            return await self._tool_search_provider("gemini", tool_input, state, config, events)

        elif tool_name == "search_perplexity":
            return await self._tool_search_provider("perplexity", tool_input, state, config, events)

        elif tool_name == "search_openai":
            return await self._tool_search_provider("openai", tool_input, state, config, events)

        elif tool_name == "search_rag_global":
            return await self._tool_search_rag_global(tool_input, state, config, events)

        elif tool_name == "search_rag_local":
            return await self._tool_search_rag_local(tool_input, state, config, events)

        elif tool_name == "analyze_results":
            return self._tool_analyze_results(tool_input, state, events)

        elif tool_name == "ask_user":
            return self._tool_ask_user(tool_input, state, events)

        elif tool_name == "generate_study_section":
            return await self._tool_generate_section(tool_input, state, config, events)

        elif tool_name == "verify_citations":
            return self._tool_verify_citations(tool_input, state, events)

        else:
            return f"Tool desconhecida: {tool_name}", events

    async def _tool_search_provider(
        self,
        provider: str,
        tool_input: Dict[str, Any],
        state: AgentState,
        config: Dict[str, Any],
        events: List[Dict[str, Any]],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Execute search on a deep research provider."""
        query = tool_input.get("query", "")
        events.append({"type": "provider_start", "provider": provider, "query": query})

        t0 = time.time()
        try:
            provider_config = {**config, "provider": _provider_map(provider)}
            # OpenAI o4-mini-deep-research does not support effort "low"
            if provider == "openai" and provider_config.get("effort") == "low":
                provider_config["effort"] = "medium"
            result: DeepResearchResult = await asyncio.wait_for(
                self.deep_research.run_research_task(
                    query=query,
                    config=provider_config,
                ),
                timeout=config.get("timeout_per_provider", DEFAULT_PROVIDER_TIMEOUT_S),
            )

            elapsed = int((time.time() - t0) * 1000)
            pr = ProviderResult(
                provider=provider,
                text=result.text or "",
                sources=result.sources or [],
                thinking_steps=[
                    s.get("text", "") if isinstance(s, dict) else str(s)
                    for s in (result.thinking_steps or [])
                ],
                success=result.success,
                error=result.error,
                elapsed_ms=elapsed,
            )

            state.collected_results[f"{provider}_{state.iteration}"] = pr
            state.all_sources.extend(pr.sources)

            for src in pr.sources[:5]:
                events.append({
                    "type": "provider_source",
                    "provider": provider,
                    "source": {"title": src.get("title", ""), "url": src.get("url", "")},
                })

            events.append({
                "type": "provider_done",
                "provider": provider,
                "results_count": len(pr.sources),
                "elapsed_ms": elapsed,
            })

            summary = f"Pesquisa {provider} concluida: {len(pr.sources)} fontes encontradas em {elapsed}ms.\n"
            if pr.text:
                summary += f"\nResumo ({len(pr.text)} chars):\n{pr.text[:3000]}"
            if pr.sources:
                summary += f"\n\nFontes encontradas:\n"
                for i, s in enumerate(pr.sources[:10], 1):
                    summary += f"[{i}] {s.get('title', 'Sem titulo')} — {s.get('url', '')}\n"

            return summary, events

        except asyncio.TimeoutError:
            elapsed = int((time.time() - t0) * 1000)
            events.append({
                "type": "provider_error",
                "provider": provider,
                "error": f"timeout ({DEFAULT_PROVIDER_TIMEOUT_S}s)",
            })
            return f"Erro: {provider} timeout apos {DEFAULT_PROVIDER_TIMEOUT_S}s", events

        except Exception as exc:
            elapsed = int((time.time() - t0) * 1000)
            events.append({"type": "provider_error", "provider": provider, "error": str(exc)})
            return f"Erro na pesquisa {provider}: {str(exc)}", events

    async def _tool_search_rag_global(
        self,
        tool_input: Dict[str, Any],
        state: AgentState,
        config: Dict[str, Any],
        events: List[Dict[str, Any]],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Search RAG global bases."""
        query = tool_input.get("query", "")
        scope = tool_input.get("scope", "all")
        top_k = tool_input.get("top_k", 10)

        events.append({"type": "provider_start", "provider": "rag_global", "query": query})
        t0 = time.time()

        try:
            from app.services.rag.pipeline_adapter import build_rag_context_unified

            sources_map = {
                "all": ["lei", "juris", "sei", "pecas_modelo"],
                "lei": ["lei"],
                "juris": ["juris"],
                "sei": ["sei"],
                "pecas_modelo": ["pecas_modelo"],
            }

            rag_context, graph_context, raw_results = await build_rag_context_unified(
                query=query,
                rag_sources=sources_map.get(scope, ["lei", "juris", "sei", "pecas_modelo"]),
                rag_top_k=top_k,
                tenant_id=config.get("tenant_id", "default"),
                allow_global_scope=True,
                dense_research=True,
            )

            sources: List[Dict[str, Any]] = []
            texts: List[str] = []
            for r in (raw_results or []):
                text = r.get("text", "")
                if text:
                    texts.append(text)
                sources.append({
                    "title": r.get("title", "") or r.get("doc_title", "") or r.get("source_type", "RAG Global"),
                    "url": r.get("url", ""),
                    "source_type": r.get("source_type", r.get("dataset", "global")),
                    "score": r.get("score", r.get("final_score", 0.0)),
                })

            elapsed = int((time.time() - t0) * 1000)
            pr = ProviderResult(
                provider="rag_global",
                text="\n\n---\n\n".join(texts),
                sources=sources,
                thinking_steps=[f"RAG Global ({scope}): {len(sources)} resultados."],
                success=bool(texts),
                elapsed_ms=elapsed,
            )
            state.collected_results[f"rag_global_{state.iteration}"] = pr
            state.all_sources.extend(sources)

            events.append({
                "type": "provider_done",
                "provider": "rag_global",
                "results_count": len(sources),
                "elapsed_ms": elapsed,
            })

            summary = f"RAG Global ({scope}): {len(sources)} resultados em {elapsed}ms.\n"
            for i, t in enumerate(texts[:5], 1):
                summary += f"\n--- Resultado {i} ---\n{t[:500]}\n"

            return summary, events

        except Exception as exc:
            elapsed = int((time.time() - t0) * 1000)
            events.append({"type": "provider_error", "provider": "rag_global", "error": str(exc)})
            return f"Erro RAG Global: {str(exc)}", events

    async def _tool_search_rag_local(
        self,
        tool_input: Dict[str, Any],
        state: AgentState,
        config: Dict[str, Any],
        events: List[Dict[str, Any]],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Search RAG local (case documents)."""
        query = tool_input.get("query", "")
        top_k = tool_input.get("top_k", 5)
        case_id = config.get("case_id")

        events.append({"type": "provider_start", "provider": "rag_local", "query": query})

        if not case_id:
            events.append({"type": "provider_error", "provider": "rag_local", "error": "Sem case_id"})
            return "RAG Local indisponivel: nenhum caso/processo vinculado a esta pesquisa.", events

        t0 = time.time()
        try:
            from app.services.rag.pipeline_adapter import build_rag_context_unified

            rag_context, graph_context, raw_results = await build_rag_context_unified(
                query=query,
                rag_sources=["sei"],
                rag_top_k=top_k,
                tenant_id=config.get("tenant_id", "default"),
                allow_global_scope=False,
                dense_research=True,
            )

            sources: List[Dict[str, Any]] = []
            texts: List[str] = []
            for r in (raw_results or []):
                text = r.get("text", "")
                if text:
                    texts.append(text)
                sources.append({
                    "title": r.get("title", "") or r.get("doc_title", "") or r.get("doc_label", "Doc Local"),
                    "url": r.get("url", ""),
                    "source_type": "local",
                    "from_rag_local": True,
                    "score": r.get("score", r.get("final_score", 0.0)),
                })

            elapsed = int((time.time() - t0) * 1000)
            pr = ProviderResult(
                provider="rag_local",
                text="\n\n---\n\n".join(texts),
                sources=sources,
                thinking_steps=[f"RAG Local: {len(sources)} resultados do caso."],
                success=bool(texts),
                elapsed_ms=elapsed,
            )
            state.collected_results[f"rag_local_{state.iteration}"] = pr
            state.all_sources.extend(sources)

            events.append({
                "type": "provider_done",
                "provider": "rag_local",
                "results_count": len(sources),
                "elapsed_ms": elapsed,
            })

            summary = f"RAG Local: {len(sources)} documentos do caso em {elapsed}ms.\n"
            for i, t in enumerate(texts[:5], 1):
                summary += f"\n--- Doc {i} ---\n{t[:500]}\n"

            return summary, events

        except Exception as exc:
            elapsed = int((time.time() - t0) * 1000)
            events.append({"type": "provider_error", "provider": "rag_local", "error": str(exc)})
            return f"Erro RAG Local: {str(exc)}", events

    def _tool_analyze_results(
        self,
        tool_input: Dict[str, Any],
        state: AgentState,
        events: List[Dict[str, Any]],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Analyze collected results so far."""
        focus = tool_input.get("focus", "")
        merged = self._merge_results(state.collected_results)

        analysis = f"""## Analise dos Resultados Coletados

### Resumo
- Total de pesquisas realizadas: {len(state.collected_results)}
- Fontes totais (antes dedup): {merged.total_before_dedup}
- Fontes unicas (apos dedup): {merged.total_after_dedup}
- Secoes ja geradas: {len(state.generated_sections)}

### Por Provider:
"""
        for provider, summary in merged.provider_summaries.items():
            analysis += f"- **{provider}**: {summary}\n"

        analysis += f"\n### Material Consolidado ({len(merged.combined_text)} caracteres)\n"

        if focus:
            analysis += f"\n### Foco da Analise: {focus}\n"

        # Identify gaps
        analysis += "\n### Lacunas Potenciais:\n"
        if merged.total_after_dedup < 5:
            analysis += "- POUCOS RESULTADOS: Considere refinar queries ou usar mais providers.\n"
        if not any("juris" in k for k in state.collected_results):
            analysis += "- SEM JURISPRUDENCIA: Considere buscar em rag_global com scope='juris'.\n"
        if not any("lei" in str(v.sources) for v in state.collected_results.values()):
            analysis += "- SEM LEGISLACAO: Considere buscar em rag_global com scope='lei'.\n"

        return analysis, events

    def _tool_ask_user(
        self,
        tool_input: Dict[str, Any],
        state: AgentState,
        events: List[Dict[str, Any]],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Pause and ask user for input."""
        state.waiting_for_user = True
        state.user_question = tool_input.get("question", "")

        # In this implementation, we provide a default continuation
        # The frontend will handle the actual user interaction
        if state.user_response:
            response = state.user_response
            state.user_response = None
            return f"Resposta do usuario: {response}", events

        return (
            "Pergunta enviada ao usuario. Continuando com a pesquisa enquanto aguarda. "
            "Se necessario, o usuario podera fornecer input adicional via chat."
        ), events

    async def _tool_generate_section(
        self,
        tool_input: Dict[str, Any],
        state: AgentState,
        config: Dict[str, Any],
        events: List[Dict[str, Any]],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Generate a study section using collected material."""
        section_title = tool_input.get("section_title", "Secao")
        instructions = tool_input.get("instructions", "")
        include_citations = tool_input.get("include_citations", True)

        events.append({
            "type": "study_generation_start",
            "section": section_title,
        })

        # Build context from collected results
        merged = self._merge_results(state.collected_results)
        sources_text = self._format_sources_for_prompt(merged.deduplicated_sources)

        prompt = f"""Gere a secao "{section_title}" do estudo.

## Material de Pesquisa Disponivel:
{merged.combined_text[:30000]}

## Fontes ({merged.total_after_dedup}):
{sources_text}

## Instrucoes Adicionais:
{instructions or 'Siga a estrutura padrao de um estudo juridico profissional.'}

## Regras:
- {'Inclua citacoes ABNT com [N] referenciando as fontes acima' if include_citations else 'Sem citacoes nesta secao'}
- Escreva em portugues brasileiro formal
- Use Markdown
- Seja preciso e fundamentado
"""

        if not self._claude_client:
            return f"## {section_title}\n\n(Claude indisponivel para geracao)\n", events

        try:
            response = await self._claude_client.messages.create(
                model=self._claude_model,
                max_tokens=8192,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text if response.content else ""
            state.generated_sections.append({"title": section_title, "text": text})

            return text, events

        except Exception as exc:
            logger.error("Erro ao gerar secao '%s': %s", section_title, exc)
            return f"## {section_title}\n\n[Erro na geracao: {exc}]\n", events

    def _tool_verify_citations(
        self,
        tool_input: Dict[str, Any],
        state: AgentState,
        events: List[Dict[str, Any]],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Verify citations in generated text against collected sources."""
        import re
        text = tool_input.get("text", "")
        cited_numbers = set(int(n) for n in re.findall(r"\[(\d{1,3})\]", text))

        merged = self._merge_results(state.collected_results)
        available = len(merged.deduplicated_sources)

        verified = []
        unverified = []
        for n in sorted(cited_numbers):
            if n <= available:
                src = merged.deduplicated_sources[n - 1]
                verified.append(f"[{n}] {src.get('title', 'OK')} — VERIFICADA")
            else:
                unverified.append(f"[{n}] — SEM FONTE CORRESPONDENTE")

        report = f"## Verificacao de Citacoes\n\n"
        report += f"Total citadas: {len(cited_numbers)}\n"
        report += f"Verificadas: {len(verified)}\n"
        report += f"Sem fonte: {len(unverified)}\n\n"

        if verified:
            report += "### Verificadas:\n" + "\n".join(verified) + "\n\n"
        if unverified:
            report += "### Pendentes:\n" + "\n".join(unverified) + "\n"
            report += "\nACAO RECOMENDADA: Pesquisar mais para cobrir citacoes pendentes.\n"

        return report, events

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _filter_tools(self, enabled_providers: List[str]) -> List[Dict[str, Any]]:
        """Filter agent tools based on user-enabled providers."""
        provider_tool_map = {
            "gemini": "search_gemini",
            "perplexity": "search_perplexity",
            "openai": "search_openai",
            "rag_global": "search_rag_global",
            "rag_local": "search_rag_local",
        }

        enabled_tool_names = set()
        for p in enabled_providers:
            tool_name = provider_tool_map.get(p)
            if tool_name:
                enabled_tool_names.add(tool_name)

        # Always include non-search tools
        always_available = {
            "analyze_results", "ask_user", "generate_study_section", "verify_citations"
        }
        enabled_tool_names.update(always_available)

        return [t for t in AGENT_TOOLS if t["name"] in enabled_tool_names]

    def _build_initial_message(
        self,
        query: str,
        config: Dict[str, Any],
        enabled_providers: List[str],
    ) -> str:
        """Build the initial user message for the agent."""
        providers_desc = ", ".join(enabled_providers)
        case_info = ""
        if config.get("case_id"):
            case_info = f"\nCaso/Processo vinculado: {config['case_id']}"

        return f"""## Solicitacao de Pesquisa Aprofundada

**Tema:** {query}

**Providers habilitados pelo usuario:** {providers_desc}
**Nivel de esforco:** {config.get('effort', 'medium')}
{case_info}

---

Conduza uma pesquisa profunda e abrangente sobre o tema acima.
Use as ferramentas disponiveis para coletar material de multiplas fontes,
analise os resultados, e produza um estudo profissional completo.

Comece planejando sua estrategia de pesquisa e depois execute as buscas."""

    def _merge_results(
        self, all_results: Dict[str, ProviderResult]
    ) -> MergedResearch:
        """Merge and deduplicate results from all providers."""
        combined_texts: List[str] = []
        all_sources: List[Dict[str, Any]] = []
        provider_summaries: Dict[str, str] = {}

        for key, result in all_results.items():
            provider = result.provider
            if result.success and result.text:
                combined_texts.append(
                    f"## Fonte: {provider.upper()}\n\n{result.text}"
                )
            if result.success:
                provider_summaries[key] = (
                    f"OK ({len(result.sources)} fontes, {result.elapsed_ms}ms)"
                )
            else:
                provider_summaries[key] = f"ERRO: {result.error or 'desconhecido'}"
            all_sources.extend(result.sources or [])

        total_before = len(all_sources)

        # Dedup by URL hash
        seen_hashes: set = set()
        deduped: List[Dict[str, Any]] = []
        for source in all_sources:
            url = str(source.get("url", "")).strip()
            title = str(source.get("title", "")).strip()
            key = url if url else title
            if not key:
                continue
            h = hashlib.md5(key.encode("utf-8")).hexdigest()[:16]
            if h in seen_hashes:
                continue
            seen_hashes.add(h)
            deduped.append(source)

        # Rerank with source type boosts
        source_boosts = {
            "lei": 0.15, "juris": 0.12, "sei": 0.10,
            "pecas_modelo": 0.08, "web": 0.05, "global": 0.05, "local": 0.10,
        }
        for source in deduped:
            base_score = float(source.get("score", 0.0))
            stype = str(source.get("source_type", "")).lower()
            source["final_score"] = base_score + source_boosts.get(stype, 0.0)

        deduped.sort(key=lambda s: s.get("final_score", 0.0), reverse=True)

        return MergedResearch(
            combined_text="\n\n".join(combined_texts),
            all_sources=all_sources,
            deduplicated_sources=deduped,
            provider_summaries=provider_summaries,
            total_before_dedup=total_before,
            total_after_dedup=len(deduped),
        )

    def _format_sources_for_prompt(
        self,
        sources: List[Dict[str, Any]],
        max_sources: int = 50,
    ) -> str:
        """Format sources for inclusion in study generation prompt."""
        lines: List[str] = []
        for i, src in enumerate(sources[:max_sources], 1):
            title = src.get("title", "Fonte")
            url = src.get("url", "")
            stype = src.get("source_type", "")
            line = f"[{i}] {title}"
            if url:
                line += f" — {url}"
            if stype:
                line += f" ({stype})"
            lines.append(line)
        return "\n".join(lines) if lines else "(Nenhuma fonte disponivel)"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _provider_map(provider: str) -> str:
    """Map internal provider name to deep_research_service provider."""
    return {"gemini": "google", "perplexity": "perplexity", "openai": "openai"}.get(
        provider, provider
    )


def _safe_serialize(obj: Any) -> Any:
    """Safely serialize tool input for SSE events."""
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)


def _truncate(text: str, max_len: int = 200) -> str:
    """Truncate text for summary display."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

deep_research_hard_service = DeepResearchHardService()
