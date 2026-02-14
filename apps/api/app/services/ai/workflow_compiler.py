"""
Workflow Compiler — Converts React Flow graph JSON to LangGraph StateGraph.

Takes the visual graph definition (nodes + edges) from the frontend workflow
builder and compiles it into an executable LangGraph state machine.

Supported node types:
- file_upload: Collect file from user input
- selection: Present choices to user
- condition: Branch based on state value
- prompt: LLM call (Claude/GPT/Gemini)
- claude_agent: Claude Agent SDK/raw executor as a single LangGraph node
- parallel_agents: fan-out of multiple Claude agent branches with fan-in merge
- rag_search: Search knowledge base
- human_review: Pause for human approval (HIL)
- tool_call: Execute a pre-configured tool via MCP
- review_table: Extract structured fields from multiple documents into a comparative table
- output: Assemble final response from variable references
- user_input: Collect text/files/selections with optional defaults
- trigger: Entry point for event-driven workflows (teams, email, djen, schedule, webhook)
- delivery: Dispatch output to destinations (email, teams, calendar, webhook, outlook reply)
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional, TypedDict

from loguru import logger

try:
    from langgraph.graph import StateGraph, END
    from langgraph.graph.state import CompiledStateGraph

    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    StateGraph = None
    END = None
    CompiledStateGraph = None


# ---------------------------------------------------------------------------
# Workflow State
# ---------------------------------------------------------------------------


class WorkflowState(TypedDict, total=False):
    """State that flows through the workflow graph."""
    # Execution context (used to stream progress via JobManager, e.g. hard deep research)
    job_id: Optional[str]
    input: str
    output: str
    current_node: str
    files: list
    selections: dict
    rag_results: list
    llm_responses: dict
    tool_results: dict
    human_edits: dict
    logs: list
    error: Optional[str]
    # Named variables system (@node_id references)
    variables: dict      # {"@node_id": "value", "@node_id.output": "value"}
    step_outputs: dict   # {node_id: {output: str, sources: list, metadata: dict}}
    # User context for per-user credential resolution (PJe, etc.)
    user_id: Optional[str]
    # Trigger/delivery context for event-driven workflows
    trigger_event: dict       # Data from the event that triggered the workflow
    delivery_results: list    # Results from each delivery dispatch


# ---------------------------------------------------------------------------
# Node Factories
# ---------------------------------------------------------------------------


def _create_file_upload_node(node_config: Dict[str, Any]) -> Callable:
    """File upload node — passes through file data from input."""
    field_name = node_config.get("collects", "file")
    is_optional = node_config.get("optional", False)
    default_template = node_config.get("default_template", "")

    def file_upload_node(state: WorkflowState) -> WorkflowState:
        logger.debug(f"[Workflow] file_upload: collects={field_name}")
        files = state.get("files", [])
        nid = node_config.get("id", "file_upload")

        # Apply default template if optional and no files provided
        fallback_value = ""
        if not files and is_optional and default_template:
            fallback_value = default_template
            logger.debug(f"[Workflow] file_upload {nid}: using default template")

        variables = dict(state.get("variables", {}))
        variables[f"@{nid}"] = str(files) if files else fallback_value
        variables[f"@{nid}.files"] = files

        step_outputs = dict(state.get("step_outputs", {}))
        step_outputs[nid] = {
            "output": str(files) if files else fallback_value,
            "files": files,
            "used_default": bool(not files and fallback_value),
        }

        return {
            **state,
            "current_node": nid,
            "variables": variables,
            "step_outputs": step_outputs,
            "logs": state.get("logs", []) + [
                {"node": node_config.get("id"), "event": "file_upload", "field": field_name}
            ],
        }

    return file_upload_node


def _create_selection_node(node_config: Dict[str, Any]) -> Callable:
    """Selection node — records user choice from input_data."""
    field_name = node_config.get("collects", "selection")
    options = node_config.get("options", [])
    is_optional = node_config.get("optional", False)
    default_template = node_config.get("default_template", "")

    def selection_node(state: WorkflowState) -> WorkflowState:
        selections = dict(state.get("selections", {}))
        # Prefer explicit selections payload (common for API runs), fallback to legacy
        # `state.input` (older callers/UX that feed values step-by-step).
        value = selections.get(field_name, "")
        if not value:
            value = state.get("input", "")

        # Apply default template if optional and empty
        if not value and is_optional and default_template:
            value = default_template
            logger.debug(f"[Workflow] selection {node_config.get('id')}: using default template")

        selections[field_name] = value
        logger.debug(f"[Workflow] selection: {field_name}={value}")

        nid = node_config.get("id")
        variables = dict(state.get("variables", {}))
        variables[f"@{nid}"] = value

        step_outputs = dict(state.get("step_outputs", {}))
        step_outputs[nid] = {"output": value, "used_default": bool(not state.get("input", "") and value)}

        return {
            **state,
            "selections": selections,
            "current_node": nid,
            "variables": variables,
            "step_outputs": step_outputs,
            "logs": state.get("logs", []) + [
                {"node": node_config.get("id"), "event": "selection", "field": field_name, "value": value}
            ],
        }

    return selection_node


def _create_condition_node(node_config: Dict[str, Any]) -> Callable:
    """Condition node — returns a routing key based on state."""
    field = node_config.get("condition_field", "selection")
    branches = node_config.get("branches", {})

    def condition_node(state: WorkflowState) -> str:
        value = state.get("selections", {}).get(field, "")
        # Match against branch keys
        for branch_key, target in branches.items():
            if str(value).lower() == str(branch_key).lower():
                logger.debug(f"[Workflow] condition: {field}={value} → {target}")
                return target
        # Default: first branch or END
        default = list(branches.values())[0] if branches else END
        logger.debug(f"[Workflow] condition: {field}={value} → default={default}")
        return default

    return condition_node


def _create_prompt_node(node_config: Dict[str, Any]) -> Callable:
    """Prompt node — calls LLM with configured prompt template."""
    prompt_template = node_config.get("prompt", "")
    model = node_config.get("model", "claude-sonnet-4-20250514")
    node_id = node_config.get("id", "prompt")

    async def prompt_node(state: WorkflowState) -> WorkflowState:
        from app.services.ai.agent_clients import get_agent_client
        from app.services.ai.variable_resolver import VariableResolver

        # Resolve @variable references first
        resolver = VariableResolver()
        filled_prompt = resolver.resolve(prompt_template, state)

        # Then do legacy {key} interpolation for backwards compat
        context = {
            "input": state.get("input", ""),
            "output": state.get("output", ""),
            "rag_results": json.dumps(state.get("rag_results", []), ensure_ascii=False),
            **state.get("selections", {}),
        }
        for key, value in context.items():
            filled_prompt = filled_prompt.replace(f"{{{key}}}", str(value))

        logger.debug(f"[Workflow] prompt node {node_id}: model={model}")

        # Load knowledge sources (max 2 per prompt block)
        knowledge_sources = node_config.get("knowledge_sources", [])
        source_context = ""
        source_citations: list = []
        if knowledge_sources:
            from app.services.ai.knowledge_source_loader import KnowledgeSourceLoader

            loader = KnowledgeSourceLoader()
            source_context, source_citations = await loader.load_sources(
                knowledge_sources,
                query=state.get("input", "") or filled_prompt[:200],
                user_id=state.get("user_id"),
            )
            if source_context:
                filled_prompt = (
                    f"{filled_prompt}\n\n"
                    f"## Fontes de Conhecimento\n\n{source_context}\n\n"
                    f"IMPORTANTE: Cite todas as fontes utilizadas usando o formato "
                    f"[N] onde N é o número da fonte. Liste as citações ao final "
                    f"da resposta no formato:\n"
                    f"[1] Nome da fonte - trecho relevante\n"
                    f"[2] Nome da fonte - trecho relevante"
                )

        try:
            client = get_agent_client(model)
            response = await client.chat(
                messages=[{"role": "user", "content": filled_prompt}],
                model=model,
            )
            result_text = response.get("content", "") if isinstance(response, dict) else str(response)
        except Exception as e:
            logger.error(f"[Workflow] prompt node {node_id} failed: {type(e).__name__}")
            result_text = "[Erro na geração de conteúdo. Tente novamente.]"
            # Propagate error in state so downstream nodes can detect it
            error_info = state.get("error") or ""
            error_info = f"{error_info}; " if error_info else ""
            state = {**state, "error": f"{error_info}Node {node_id}: erro na geração de conteúdo"}

        llm_responses = dict(state.get("llm_responses", {}))
        llm_responses[node_id] = result_text

        # Parse inline citations [N] from the LLM output
        parsed_citations: list = []
        if source_citations:
            parsed_citations = list(source_citations)
        # Also extract citations from the text itself
        citation_pattern = re.compile(
            r"\[(\d+)\]\s*(.+?)(?:\s*[-–—]\s*(.+?))?(?=\n\[|\n*$)", re.MULTILINE
        )
        for match in citation_pattern.finditer(result_text):
            num = int(match.group(1))
            source_name = match.group(2).strip()
            excerpt = (match.group(3) or "").strip()
            # Only add if not already present from knowledge source loader
            already_exists = any(
                c.get("number") == num or c.get("source") == source_name
                for c in parsed_citations
                if isinstance(c, dict)
            )
            if not already_exists:
                parsed_citations.append({
                    "number": num,
                    "source": source_name,
                    "excerpt": excerpt,
                })

        step_outputs = dict(state.get("step_outputs", {}))
        step_outputs[node_id] = {
            "output": result_text,
            "model": model,
            "citations": parsed_citations,
        }

        variables = dict(state.get("variables", {}))
        variables[f"@{node_id}"] = result_text
        variables[f"@{node_id}.output"] = result_text

        return {
            **state,
            "output": result_text,
            "llm_responses": llm_responses,
            "variables": variables,
            "step_outputs": step_outputs,
            "current_node": node_id,
            "logs": state.get("logs", []) + [
                {"node": node_id, "event": "llm_call", "model": model}
            ],
        }

    return prompt_node


def _create_deep_research_node(node_config: Dict[str, Any]) -> Callable:
    """
    Deep research node — runs either standard deep research (single provider) or
    hard deep research (multi-provider + Claude agentic loop).
    """
    node_id = node_config.get("id", "deep_research")
    query_template = node_config.get("query", "") or node_config.get("prompt", "")
    mode = str(node_config.get("mode") or "hard").strip().lower()
    effort = str(node_config.get("effort") or "medium").strip().lower()
    provider = (node_config.get("provider") or "").strip().lower() or None
    providers = node_config.get("providers") or [
        "gemini",
        "perplexity",
        "openai",
        "rag_global",
        "rag_local",
    ]
    timeout_per_provider = int(node_config.get("timeout_per_provider") or 120)
    total_timeout = int(node_config.get("total_timeout") or 300)
    search_focus = node_config.get("search_focus")
    domain_filter = node_config.get("domain_filter")
    include_sources = bool(node_config.get("include_sources", True))

    async def deep_research_node(state: WorkflowState) -> WorkflowState:
        from app.services.ai.variable_resolver import VariableResolver
        from app.services.job_manager import job_manager

        resolver = VariableResolver()
        query = resolver.resolve(query_template or "", state) if query_template else ""
        if not query:
            query = str(state.get("input", "") or state.get("output", "") or "").strip()

        # Backwards-compat for legacy placeholders like {input}
        legacy_ctx = {
            "input": state.get("input", ""),
            "output": state.get("output", ""),
            "rag_results": json.dumps(state.get("rag_results", []), ensure_ascii=False),
            **(state.get("selections", {}) or {}),
        }
        for k, v in legacy_ctx.items():
            query = query.replace(f"{{{k}}}", str(v))

        logger.info(f"[Workflow] deep_research node {node_id}: mode={mode} effort={effort}")

        job_id = state.get("job_id")
        report_text = ""
        sources: list[dict] = []
        metadata: dict = {"mode": mode, "effort": effort}

        if mode == "hard":
            from app.services.ai.deep_research_hard_service import deep_research_hard_service

            hard_cfg = {
                "effort": effort,
                "providers": providers,
                "tenant_id": state.get("tenant_id"),
                "case_id": state.get("case_id"),
                "search_focus": search_focus,
                "domain_filter": domain_filter,
                "timeout_per_provider": timeout_per_provider,
                "total_timeout": total_timeout,
                "plan_key": node_id,
            }

            try:
                async for ev in deep_research_hard_service.stream_hard_research(query, config=hard_cfg):
                    etype = str((ev or {}).get("type", "") or "hard_research_event")

                    if etype == "study_token":
                        delta = str(ev.get("delta", "") or "")
                        if delta:
                            report_text += delta
                            if job_id:
                                job_manager.emit_event(
                                    job_id,
                                    "token",
                                    {"token": delta, "node_id": node_id, "kind": "hard_research"},
                                    phase="workflow",
                                    node=node_id,
                                )
                        continue

                    if etype == "study_done":
                        sources = ev.get("sources", []) or []
                        metadata.update(
                            {
                                "sources_count": ev.get("sources_count"),
                                "iterations": ev.get("iterations"),
                                "elapsed_ms": ev.get("elapsed_ms"),
                                "provider_summaries": ev.get("provider_summaries"),
                                "providers": providers,
                            }
                        )

                    if job_id:
                        # Keep for debug/observability in RunViewer.
                        job_manager.emit_event(
                            job_id,
                            etype,
                            {**dict(ev), "node_id": node_id},
                            phase="workflow",
                            node=node_id,
                        )
            except Exception as exc:
                logger.exception(f"[Workflow] deep_research hard failed: {exc}")
                report_text = report_text or f"[Erro no Hard Deep Research: {exc}]"
                metadata["error"] = str(exc)

        else:
            from app.services.ai.deep_research_service import DeepResearchService

            cfg = {
                "effort": effort,
                **({"provider": provider} if provider else {}),
                "search_focus": search_focus,
                "domain_filter": domain_filter,
                "require_sources": True,
            }
            svc = DeepResearchService()
            try:
                res = await svc.run_research_task(query, config=cfg)
                report_text = str(getattr(res, "text", "") or "")
                sources = list(getattr(res, "sources", []) or []) if include_sources else []
                metadata.update(
                    {
                        "from_cache": bool(getattr(res, "from_cache", False)),
                        "success": bool(getattr(res, "success", True)),
                    }
                )
                if job_id and report_text:
                    chunk_size = 200
                    for i in range(0, len(report_text), chunk_size):
                        job_manager.emit_event(
                            job_id,
                            "token",
                            {"token": report_text[i : i + chunk_size], "node_id": node_id, "kind": "deep_research"},
                            phase="workflow",
                            node=node_id,
                        )
            except Exception as exc:
                logger.exception(f"[Workflow] deep_research failed: {exc}")
                report_text = f"[Erro no Deep Research: {exc}]"
                metadata["error"] = str(exc)

        # Convert sources -> citations for UI panel (best-effort)
        citations: list[dict] = []
        if include_sources and sources:
            try:
                from app.services.ai.citations.base import stable_numbering, sources_to_citations

                url_title: list[tuple[str, str]] = []
                for s in sources:
                    if not isinstance(s, dict):
                        continue
                    url = str(s.get("url") or s.get("uri") or "").strip()
                    title = str(s.get("title") or s.get("name") or url).strip()
                    if url:
                        url_title.append((url, title or url))
                _, stable_sources = stable_numbering(url_title)
                citations = sources_to_citations(stable_sources)
            except Exception:
                citations = []

        llm_responses = dict(state.get("llm_responses", {}))
        llm_responses[node_id] = report_text

        variables = dict(state.get("variables", {}))
        variables[f"@{node_id}"] = report_text
        variables[f"@{node_id}.output"] = report_text
        variables[f"@{node_id}.metadata"] = metadata

        step_outputs = dict(state.get("step_outputs", {}))
        step_outputs[node_id] = {
            "output": report_text,
            "metadata": metadata,
            "sources": sources if include_sources else [],
            "citations": citations,
        }

        return {
            **state,
            "output": report_text,
            "current_node": node_id,
            "llm_responses": llm_responses,
            "variables": variables,
            "step_outputs": step_outputs,
            "logs": state.get("logs", []) + [{"node": node_id, "event": "deep_research", **metadata}],
        }

    return deep_research_node


def _create_claude_agent_node(node_config: Dict[str, Any]) -> Callable:
    """Claude agent node — executes ClaudeAgentExecutor inside workflow graph."""
    from app.services.ai.langgraph.nodes import ClaudeAgentNode

    node_id = node_config.get("id", "claude_agent")
    prompt_template = node_config.get("prompt", "{input}")
    model = node_config.get("model", "claude-opus-4-6")
    system_prompt = node_config.get("system_prompt", "")
    max_iterations = int(node_config.get("max_iterations", 8) or 8)
    max_tokens = int(node_config.get("max_tokens", 4096) or 4096)
    include_mcp = bool(node_config.get("include_mcp", True))
    use_sdk = bool(node_config.get("use_sdk", True))

    tool_names_raw = node_config.get("tool_names")
    tool_names: Optional[List[str]] = None
    if isinstance(tool_names_raw, str):
        names = [x.strip() for x in tool_names_raw.split(",") if x and x.strip()]
        tool_names = names or None
    elif isinstance(tool_names_raw, list):
        names = [str(x).strip() for x in tool_names_raw if str(x).strip()]
        tool_names = names or None

    node = ClaudeAgentNode(
        node_id=node_id,
        prompt_template=prompt_template,
        model=model,
        system_prompt=system_prompt,
        max_iterations=max_iterations,
        max_tokens=max_tokens,
        include_mcp=include_mcp,
        tool_names=tool_names,
        use_sdk=use_sdk,
    )

    async def run_node(state: WorkflowState) -> WorkflowState:
        return await node(state)

    return run_node


def _create_parallel_agents_node(node_config: Dict[str, Any]) -> Callable:
    """Parallel agents node - runs multiple Claude branches in parallel."""
    from app.services.ai.langgraph.nodes import ParallelAgentsNode

    node_id = node_config.get("id", "parallel_agents")
    prompt_template = str(node_config.get("prompt", "") or "").strip()
    prompts_raw = node_config.get("prompts")
    prompt_templates: List[str] = []
    if isinstance(prompts_raw, list):
        prompt_templates = [str(p).strip() for p in prompts_raw if str(p).strip()]
    elif isinstance(prompts_raw, str):
        prompt_templates = [part.strip() for part in prompts_raw.split("\n---\n") if part.strip()]
    if not prompt_templates and prompt_template:
        prompt_templates = [prompt_template]

    model_raw = node_config.get("model")
    models_raw = node_config.get("models")
    models: List[str] = []
    if isinstance(models_raw, list):
        models = [str(m).strip() for m in models_raw if str(m).strip()]
    elif isinstance(models_raw, str):
        models = [part.strip() for part in models_raw.split(",") if part.strip()]
    elif isinstance(model_raw, str) and model_raw.strip():
        models = [model_raw.strip()]

    tool_names_raw = node_config.get("tool_names")
    tool_names: Optional[List[str]] = None
    if isinstance(tool_names_raw, list):
        parsed_names = [str(item).strip() for item in tool_names_raw if str(item).strip()]
        tool_names = parsed_names or None
    elif isinstance(tool_names_raw, str):
        parsed_names = [part.strip() for part in tool_names_raw.split(",") if part.strip()]
        tool_names = parsed_names or None

    node = ParallelAgentsNode(
        node_id=node_id,
        prompt_templates=prompt_templates,
        models=models or None,
        system_prompt=str(node_config.get("system_prompt", "") or ""),
        max_iterations=int(node_config.get("max_iterations", 4) or 4),
        max_tokens=int(node_config.get("max_tokens", 2048) or 2048),
        include_mcp=bool(node_config.get("include_mcp", False)),
        tool_names=tool_names,
        use_sdk=bool(node_config.get("use_sdk", False)),
        max_parallel=int(node_config.get("max_parallel", 3) or 3),
        aggregation_strategy=str(node_config.get("aggregation_strategy", "concat") or "concat"),
    )

    async def run_node(state: WorkflowState) -> WorkflowState:
        return await node(state)

    return run_node


def _create_rag_search_node(node_config: Dict[str, Any]) -> Callable:
    """RAG search node — queries knowledge base."""
    sources = node_config.get("sources", [])
    top_k = node_config.get("limit", 10)
    node_id = node_config.get("id", "rag_search")

    async def rag_search_node(state: WorkflowState) -> WorkflowState:
        from app.services.rag_module import get_scoped_knowledge_graph

        query = state.get("input", "") or state.get("output", "")
        logger.debug(f"[Workflow] rag_search: query={query[:50]}...")

        try:
            rag = get_scoped_knowledge_graph()
            results = rag.hybrid_search(
                query=query,
                sources=sources or None,
                top_k=top_k,
                include_global=True,
            )
        except Exception as e:
            logger.error(f"[Workflow] rag_search failed: {e}")
            results = []

        step_outputs = dict(state.get("step_outputs", {}))
        step_outputs[node_id] = {
            "output": json.dumps(results, ensure_ascii=False, default=str)[:2000],
            "sources": results,
        }

        variables = dict(state.get("variables", {}))
        variables[f"@{node_id}"] = json.dumps(results, ensure_ascii=False, default=str)[:2000]
        variables[f"@{node_id}.sources"] = results

        return {
            **state,
            "rag_results": results,
            "variables": variables,
            "step_outputs": step_outputs,
            "current_node": node_id,
            "logs": state.get("logs", []) + [
                {"node": node_id, "event": "rag_search", "results_count": len(results)}
            ],
        }

    return rag_search_node


def _create_human_review_node(node_config: Dict[str, Any]) -> Callable:
    """Human review node — passthrough that triggers interrupt_before."""
    node_id = node_config.get("id", "human_review")
    instructions = node_config.get("instructions", "Revise o conteúdo e aprove.")

    def human_review_node(state: WorkflowState) -> WorkflowState:
        logger.debug(f"[Workflow] human_review: {node_id}")
        return {
            **state,
            "current_node": node_id,
            "logs": state.get("logs", []) + [
                {"node": node_id, "event": "human_review_reached", "instructions": instructions}
            ],
        }

    return human_review_node


def _create_tool_call_node(node_config: Dict[str, Any]) -> Callable:
    """Tool call node — executes a pre-configured tool via Tool Gateway."""
    tool_name = node_config.get("tool_name", "")
    node_id = node_config.get("id", "tool_call")

    async def tool_call_node(state: WorkflowState) -> WorkflowState:
        from app.services.ai.tool_gateway import tool_registry

        logger.debug(f"[Workflow] tool_call: {tool_name}")

        try:
            tool_registry.initialize()
            tool_def = tool_registry.get(tool_name)
            if not tool_def:
                raise ValueError(f"Tool '{tool_name}' not found in registry")

            # Build arguments from node config (supports legacy tool_input from early UI)
            args: Dict[str, Any] = {}
            raw_args = node_config.get("arguments", None)
            if isinstance(raw_args, dict):
                args.update(raw_args)
            elif raw_args is not None:
                # If arguments are a string accidentally, ignore (UI bug / legacy)
                pass

            if not args:
                legacy = node_config.get("tool_input", None)
                if isinstance(legacy, dict):
                    args.update(legacy)
                elif isinstance(legacy, str) and legacy.strip():
                    try:
                        parsed = json.loads(legacy)
                        if isinstance(parsed, dict):
                            args.update(parsed)
                    except Exception:
                        pass

            # Inject workflow context (similar to MCP server injection)
            if "tenant_id" in state and "tenant_id" not in args:
                args["tenant_id"] = state.get("tenant_id")
            if state.get("user_id") and "user_id" not in args:
                args["user_id"] = state.get("user_id")
            if "case_id" in state and "case_id" not in args:
                args["case_id"] = state.get("case_id")

            # Only pass the free-text query if the tool schema accepts it.
            schema_props = (tool_def.input_schema or {}).get("properties") if isinstance(tool_def.input_schema, dict) else {}
            if isinstance(schema_props, dict) and "query" in schema_props and "query" not in args:
                args["query"] = state.get("input", "") or state.get("output", "")
            result = await tool_def.function(**args)
        except Exception as e:
            logger.error(f"[Workflow] tool_call {tool_name} failed: {e}")
            result = {"error": str(e)}

        tool_results = dict(state.get("tool_results", {}))
        tool_results[node_id] = result

        result_str = json.dumps(result, ensure_ascii=False, default=str)[:2000] if isinstance(result, (dict, list)) else str(result)

        variables = dict(state.get("variables", {}))
        variables[f"@{node_id}"] = result_str
        variables[f"@{node_id}.output"] = result_str

        step_outputs = dict(state.get("step_outputs", {}))
        step_outputs[node_id] = {"output": result_str, "tool": tool_name}

        return {
            **state,
            "tool_results": tool_results,
            "variables": variables,
            "step_outputs": step_outputs,
            "current_node": node_id,
            "logs": state.get("logs", []) + [
                {"node": node_id, "event": "tool_call", "tool": tool_name}
            ],
        }

    return tool_call_node


def _create_legal_workflow_node(node_config: Dict[str, Any]) -> Callable:
    """Legal workflow node — runs the full LangGraph minuta/parecer pipeline.

    Bridges the visual Workflow Builder with the existing
    ``langgraph_legal_workflow.legal_workflow_app`` compiled graph, exposing the
    entire outline → research → citer_verifier → debate → audit → HIL pipeline
    as a single visual node.

    Configurable fields in ``node_config``:
        mode              – "minuta" | "parecer" | "chat"  (default: "minuta")
        models            – list of model IDs               (default: ["claude-sonnet-4-20250514"])
        doc_kind          – document subtype                 (optional)
        tese              – central thesis                   (optional)
        citation_style    – "abnt" | "ieee"                  (default: "abnt")
        auto_approve      – skip ALL HIL inside pipeline     (default: False)
        thinking_level    – "low" | "medium" | "high"        (default: "medium")

        template_structure – markdown template that pre-defines the outline
                            sections. When set, the pipeline uses this instead of
                            generating an outline from scratch.
        outline           – explicit list of section titles (alternative to
                            template_structure). If both are set, template takes
                            priority.
        hil_outline       – pause for human review of the outline before
                            proceeding to research/debate. (default: False)
        hil_sections      – list of section titles that require human review
                            after drafting. Empty = no per-section HIL.
        hil_section_policy– "all" | "divergence_only" | "high_risk_only" | "none"
                            Controls which sections trigger HIL. (default: "divergence_only")
        force_final_hil   – always pause for final review even if auto_approve
                            is True. (default: False)
    """
    node_id = node_config.get("id", "legal_workflow")
    mode = node_config.get("mode", "minuta")
    models = node_config.get("models", ["claude-sonnet-4-20250514"])
    doc_kind = node_config.get("doc_kind")
    tese = node_config.get("tese", "")
    citation_style = node_config.get("citation_style", "abnt")
    auto_approve = node_config.get("auto_approve", False)
    thinking_level = node_config.get("thinking_level", "medium")

    # Template / Outline
    template_id = node_config.get("template_id", "")  # LibraryItem.id
    template_structure = node_config.get("template_structure", "")
    outline = node_config.get("outline", [])

    # HIL control
    hil_outline = node_config.get("hil_outline", False)
    hil_sections = node_config.get("hil_sections", [])
    hil_section_policy = node_config.get("hil_section_policy", "divergence_only")
    force_final_hil = node_config.get("force_final_hil", False)

    async def legal_workflow_node(state: WorkflowState) -> WorkflowState:
        from app.services.ai.langgraph_legal_workflow import run_workflow_async

        input_text = state.get("input", "") or state.get("output", "")
        logger.info(
            f"[Workflow] legal_workflow node {node_id}: mode={mode}, "
            f"models={models}, input_len={len(input_text)}"
        )

        # Map WorkflowState → DocumentState (partial)
        doc_state: Dict[str, Any] = {
            "job_id": f"wf_{node_id}_{id(state)}",
            "input_text": input_text,
            "mode": mode,
            "selected_models": models,
            "drafter_models": models,
            "reviewer_models": models[:1],
            "judge_model": models[0],
            "citation_style": citation_style,
            "thinking_level": thinking_level,
            "auto_approve_hil": auto_approve,
            "stream_tokens": False,  # We collect the final result, not stream
        }
        if doc_kind:
            doc_state["doc_kind"] = doc_kind
        if tese:
            doc_state["tese"] = tese

        # Template / Outline — let user pre-define document structure
        # Priority: template_id (from /models page) > template_structure (manual) > outline
        effective_template = template_structure
        if template_id and not effective_template:
            try:
                from app.models.library import LibraryItem
                from app.core.database import AsyncSessionLocal
                async with AsyncSessionLocal() as db_session:
                    item = await db_session.get(LibraryItem, template_id)
                    if item and item.description:
                        effective_template = item.description
                        logger.debug(
                            f"[Workflow] Loaded template '{item.name}' "
                            f"(id={template_id}, {len(effective_template)} chars)"
                        )
            except Exception as e:
                logger.warning(f"[Workflow] Failed to load template {template_id}: {e}")

        if effective_template:
            doc_state["template_structure"] = effective_template
        if outline:
            doc_state["outline"] = outline

        # HIL control — let user decide where human review happens
        doc_state["hil_outline_enabled"] = hil_outline
        if hil_sections:
            doc_state["hil_target_sections"] = hil_sections
        doc_state["hil_section_policy"] = hil_section_policy
        doc_state["force_final_hil"] = force_final_hil

        # Inject RAG results from prior workflow nodes (if any)
        rag_results = state.get("rag_results", [])
        if rag_results:
            rag_text = "\n\n".join(
                r.get("content", str(r)) if isinstance(r, dict) else str(r)
                for r in rag_results
            )
            doc_state["case_bundle_text_pack"] = rag_text

        # Inject human edits from prior HIL nodes
        human_edits = state.get("human_edits", {})
        if human_edits:
            doc_state["human_edits"] = json.dumps(human_edits, ensure_ascii=False)

        try:
            final_state = await run_workflow_async(doc_state)

            # Extract the generated document
            full_document = final_state.get("full_document", "")
            if not full_document:
                sections = final_state.get("processed_sections", [])
                if sections:
                    full_document = "\n\n".join(
                        s.get("content", "") for s in sections if isinstance(s, dict)
                    )

            result_meta = {
                "mode": mode,
                "sections_count": len(final_state.get("processed_sections", [])),
                "outline": final_state.get("outline", []),
                "audit_status": final_state.get("audit_status"),
                "final_decision": final_state.get("final_decision"),
            }

        except ImportError:
            logger.warning("[Workflow] langgraph_legal_workflow not available")
            full_document = f"[Erro: LangGraph Legal Workflow não disponível]"
            result_meta = {"error": "langgraph_legal_workflow not importable"}

        except Exception as e:
            logger.exception(f"[Workflow] legal_workflow node {node_id} failed: {e}")
            full_document = f"[Erro na geração: {e}]"
            result_meta = {"error": str(e)}

        llm_responses = dict(state.get("llm_responses", {}))
        llm_responses[node_id] = full_document

        variables = dict(state.get("variables", {}))
        variables[f"@{node_id}"] = full_document
        variables[f"@{node_id}.output"] = full_document
        variables[f"@{node_id}.metadata"] = result_meta

        step_outputs = dict(state.get("step_outputs", {}))
        step_outputs[node_id] = {
            "output": full_document,
            "metadata": result_meta,
            "mode": mode,
        }

        return {
            **state,
            "output": full_document,
            "llm_responses": llm_responses,
            "variables": variables,
            "step_outputs": step_outputs,
            "current_node": node_id,
            "logs": state.get("logs", []) + [
                {
                    "node": node_id,
                    "event": "legal_workflow",
                    "mode": mode,
                    "models": models,
                    **result_meta,
                }
            ],
        }

    return legal_workflow_node


def _create_review_table_node(node_config: Dict[str, Any]) -> Callable:
    """Review table node — extracts structured fields from multiple documents into a table.

    Collects input documents from connected file_upload nodes or previous prompt outputs,
    then uses an LLM to extract user-defined columns from each document, returning
    structured JSON table data (rows = documents, columns = extraction fields).
    """
    node_id = node_config.get("id", "review_table")
    columns = node_config.get("columns", [])
    model = node_config.get("model", "claude-sonnet-4-20250514")
    prompt_prefix = node_config.get(
        "prompt_prefix", "Extraia as seguintes informações de cada documento:"
    )

    async def review_table_node(state: WorkflowState) -> WorkflowState:
        from app.services.ai.agent_clients import get_agent_client

        # Collect all input documents from previous step outputs
        documents: list[dict] = []
        step_outputs = state.get("step_outputs", {})
        for sid, sdata in step_outputs.items():
            if not isinstance(sdata, dict):
                continue
            # Files from file_upload or user_input nodes
            files = sdata.get("files", [])
            if files:
                for f in files:
                    doc_name = f.get("name", f.get("filename", sid)) if isinstance(f, dict) else str(f)
                    doc_content = f.get("content", f.get("text", str(f))) if isinstance(f, dict) else str(f)
                    documents.append({"name": doc_name, "content": doc_content})
            # Text output from prompt nodes
            elif sdata.get("output"):
                documents.append({"name": sid, "content": str(sdata["output"])})

        # Also check raw files in state
        raw_files = state.get("files", [])
        if raw_files and not documents:
            for f in raw_files:
                doc_name = f.get("name", f.get("filename", "documento")) if isinstance(f, dict) else str(f)
                doc_content = f.get("content", f.get("text", str(f))) if isinstance(f, dict) else str(f)
                documents.append({"name": doc_name, "content": doc_content})

        # Fallback: use plain input text as a single document
        if not documents and state.get("input"):
            documents.append({"name": "input", "content": state["input"]})

        if not documents:
            logger.warning(f"[Workflow] review_table {node_id}: no documents found")
            empty_result = json.dumps({"rows": []}, ensure_ascii=False)
            variables = dict(state.get("variables", {}))
            variables[f"@{node_id}"] = empty_result
            step_out = dict(state.get("step_outputs", {}))
            step_out[node_id] = {"output": empty_result, "rows": []}
            return {
                **state,
                "variables": variables,
                "step_outputs": step_out,
                "current_node": node_id,
                "logs": state.get("logs", []) + [
                    {"node": node_id, "event": "review_table", "docs": 0, "error": "no_documents"}
                ],
            }

        # Build extraction prompt
        columns_desc = "\n".join(
            f'- "{col.get("name", col.get("id", ""))}" ({col.get("id", "")}): '
            f'{col.get("description", col.get("name", ""))}'
            for col in columns
        )
        col_ids = [col.get("id", f"col_{i}") for i, col in enumerate(columns)]

        docs_text = ""
        for i, doc in enumerate(documents):
            docs_text += f"\n\n--- DOCUMENTO {i+1}: {doc['name']} ---\n{doc['content'][:8000]}"

        col_example = ", ".join(f'"{cid}": "valor extraído"' for cid in col_ids)
        extraction_prompt = (
            f"{prompt_prefix}\n\n"
            f"Campos a extrair para cada documento:\n{columns_desc}\n\n"
            f"Documentos:{docs_text}\n\n"
            f"IMPORTANTE: Responda EXCLUSIVAMENTE com JSON válido no seguinte formato, "
            f"sem texto adicional:\n"
            f'{{\n  "rows": [\n    '
            f'{{"_doc": "nome_do_documento", {col_example}}}'
            f"\n  ]\n}}\n\n"
            f'Se não encontrar a informação para algum campo, use "-" como valor.'
        )

        logger.debug(
            f"[Workflow] review_table {node_id}: {len(documents)} docs, "
            f"{len(columns)} columns, model={model}"
        )

        rows: list = []
        table_data: dict = {"rows": []}
        try:
            client = get_agent_client(model)
            response = await client.chat(
                messages=[{"role": "user", "content": extraction_prompt}],
                model=model,
            )
            result_text = (
                response.get("content", "") if isinstance(response, dict) else str(response)
            )

            # Parse JSON from response (handle markdown code blocks)
            json_text = result_text.strip()
            if json_text.startswith("```"):
                lines = json_text.split("\n")
                lines = [ln for ln in lines if not ln.strip().startswith("```")]
                json_text = "\n".join(lines)

            table_data = json.loads(json_text)
            rows = table_data.get("rows", [])

        except json.JSONDecodeError as e:
            logger.error(f"[Workflow] review_table {node_id} JSON parse error: {e}")
            try:
                match = re.search(r'\{[\s\S]*"rows"[\s\S]*\}', result_text)
                if match:
                    table_data = json.loads(match.group())
                    rows = table_data.get("rows", [])
                else:
                    table_data = {"rows": [], "error": f"JSON parse failed: {e}"}
            except Exception:
                table_data = {"rows": [], "error": f"JSON parse failed: {e}"}

        except Exception as e:
            logger.error(f"[Workflow] review_table {node_id} failed: {e}")
            table_data = {"rows": [], "error": str(e)}

        result_json = json.dumps(table_data, ensure_ascii=False)

        variables = dict(state.get("variables", {}))
        variables[f"@{node_id}"] = result_json
        variables[f"@{node_id}.output"] = result_json
        variables[f"@{node_id}.rows"] = rows

        llm_responses = dict(state.get("llm_responses", {}))
        llm_responses[node_id] = result_json

        step_out = dict(state.get("step_outputs", {}))
        step_out[node_id] = {
            "output": result_json,
            "rows": rows,
            "columns": columns,
            "model": model,
            "documents_count": len(documents),
        }

        return {
            **state,
            "output": result_json,
            "llm_responses": llm_responses,
            "variables": variables,
            "step_outputs": step_out,
            "current_node": node_id,
            "logs": state.get("logs", []) + [
                {
                    "node": node_id,
                    "event": "review_table",
                    "docs": len(documents),
                    "columns": len(columns),
                    "rows": len(rows),
                    "model": model,
                }
            ],
        }

    return review_table_node


def _create_output_node(node_config: Dict[str, Any]) -> Callable:
    """Output node — assembles final response from @variable references."""
    node_id = node_config.get("id", "output")
    sections = node_config.get("sections", [])  # [{label, variable_ref, order}]
    show_all = node_config.get("show_all", True)

    def output_node(state: WorkflowState) -> WorkflowState:
        from app.services.ai.variable_resolver import VariableResolver
        resolver = VariableResolver()

        parts = []
        if sections:
            for section in sorted(sections, key=lambda s: s.get("order", 0)):
                label = section.get("label", "")
                ref = section.get("variable_ref", "")
                content = resolver.resolve(ref, state) if ref else ""
                if label:
                    parts.append(f"## {label}\n\n{content}")
                else:
                    parts.append(content)
        elif show_all:
            # Show all step outputs
            step_outputs = state.get("step_outputs", {})
            for sid, sdata in step_outputs.items():
                output_val = sdata.get("output", "") if isinstance(sdata, dict) else str(sdata)
                if output_val:
                    parts.append(output_val)

        if not parts:
            parts.append(state.get("output", ""))

        final_output = "\n\n---\n\n".join(parts)

        logger.debug(f"[Workflow] output node {node_id}: {len(parts)} sections, {len(final_output)} chars")
        return {
            **state,
            "output": final_output,
            "current_node": node_id,
            "logs": state.get("logs", []) + [
                {"node": node_id, "event": "output", "sections_count": len(parts)}
            ],
        }

    return output_node


def _create_user_input_node(node_config: Dict[str, Any]) -> Callable:
    """User input node — collects text/files/selections with optional defaults."""
    node_id = node_config.get("id", "user_input")
    field_name = node_config.get("collects", "input")
    input_type = node_config.get("input_type", "text")  # text, file, both, selection
    is_optional = node_config.get("optional", False)
    default_text = node_config.get("default_text", "") or node_config.get("default_template", "")
    placeholder = node_config.get("placeholder", "")

    def user_input_node(state: WorkflowState) -> WorkflowState:
        # Get value from input_data
        value = state.get("input", "") if field_name == "input" else state.get("selections", {}).get(field_name, "")
        files = state.get("files", [])

        # Apply defaults if optional and empty
        if not value and is_optional and default_text:
            value = default_text
            logger.debug(f"[Workflow] user_input {node_id}: using default text")

        if not value and not files and not is_optional:
            logger.warning(f"[Workflow] user_input {node_id}: required field '{field_name}' is empty")

        # Export as variables
        variables = dict(state.get("variables", {}))
        step_outputs = dict(state.get("step_outputs", {}))

        if input_type in ("file", "both"):
            variables[f"@{node_id}"] = str(files) if files else value
            variables[f"@{node_id}.files"] = files
            step_outputs[node_id] = {"output": value or str(files), "files": files}
        else:
            variables[f"@{node_id}"] = value
            step_outputs[node_id] = {"output": value}

        variables[f"@{node_id}.output"] = value

        logger.debug(f"[Workflow] user_input {node_id}: type={input_type}, has_value={bool(value)}")
        return {
            **state,
            "variables": variables,
            "step_outputs": step_outputs,
            "current_node": node_id,
            "logs": state.get("logs", []) + [
                {"node": node_id, "event": "user_input", "field": field_name, "type": input_type}
            ],
        }

    return user_input_node


def _create_trigger_node(node_config: Dict[str, Any]) -> Callable:
    """Trigger node — entry point for event-driven workflows.

    Injects the trigger_event data into WorkflowState from input_data.
    Supported trigger_types: teams_command, outlook_email, djen_movement, schedule, webhook.
    """
    node_id = node_config.get("id", "trigger")
    trigger_type = node_config.get("trigger_type", "webhook")

    def trigger_node(state: WorkflowState) -> WorkflowState:
        # The trigger_event comes from input_data when the Celery task runs
        trigger_event = state.get("trigger_event", {})
        if not trigger_event:
            # Fallback: entire input_data is the trigger event
            trigger_event = {
                "type": trigger_type,
                "input": state.get("input", ""),
            }

        logger.debug(
            f"[Workflow] trigger {node_id}: type={trigger_type}, "
            f"event_keys={list(trigger_event.keys())}"
        )

        variables = dict(state.get("variables", {}))
        variables[f"@{node_id}"] = str(trigger_event)
        variables[f"@{node_id}.type"] = trigger_type

        # Expose common event fields as variables
        for key in ("subject", "body", "sender", "command", "text", "npu", "tipo"):
            if key in trigger_event:
                variables[f"@{node_id}.{key}"] = str(trigger_event[key])

        step_outputs = dict(state.get("step_outputs", {}))
        step_outputs[node_id] = {
            "output": str(trigger_event),
            "trigger_type": trigger_type,
            "event": trigger_event,
        }

        # Also set input from event text/body for downstream prompt nodes
        input_text = (
            trigger_event.get("text")
            or trigger_event.get("body")
            or trigger_event.get("command")
            or state.get("input", "")
        )

        return {
            **state,
            "input": input_text,
            "trigger_event": trigger_event,
            "variables": variables,
            "step_outputs": step_outputs,
            "current_node": node_id,
            "logs": state.get("logs", []) + [
                {"node": node_id, "event": "trigger", "trigger_type": trigger_type}
            ],
        }

    return trigger_node


def _create_delivery_node(node_config: Dict[str, Any]) -> Callable:
    """Delivery node — dispatches workflow output to external destination.

    Supported delivery_types: email, teams_message, calendar_event, webhook_out, outlook_reply.

    In sync execution (SSE), this is a passthrough that records the config.
    In async execution (Celery), the delivery is dispatched by _run_triggered().
    """
    node_id = node_config.get("id", "delivery")
    delivery_type = node_config.get("delivery_type", "email")
    delivery_config = node_config.get("delivery_config", {})

    def delivery_node(state: WorkflowState) -> WorkflowState:
        logger.debug(
            f"[Workflow] delivery {node_id}: type={delivery_type}, "
            f"config_keys={list(delivery_config.keys())}"
        )

        # Record the delivery config in step_outputs for later dispatch
        step_outputs = dict(state.get("step_outputs", {}))
        step_outputs[node_id] = {
            "output": f"Delivery: {delivery_type}",
            "delivery_type": delivery_type,
            "delivery_config": delivery_config,
        }

        variables = dict(state.get("variables", {}))
        variables[f"@{node_id}"] = f"Delivery ({delivery_type}) configurado"

        return {
            **state,
            "variables": variables,
            "step_outputs": step_outputs,
            "current_node": node_id,
            "logs": state.get("logs", []) + [
                {"node": node_id, "event": "delivery", "delivery_type": delivery_type}
            ],
        }

    return delivery_node


# ---------------------------------------------------------------------------
# Node Factory Map
# ---------------------------------------------------------------------------

NODE_FACTORIES = {
    "file_upload": _create_file_upload_node,
    "selection": _create_selection_node,
    "condition": _create_condition_node,
    "prompt": _create_prompt_node,
    "deep_research": _create_deep_research_node,
    "claude_agent": _create_claude_agent_node,
    "parallel_agents": _create_parallel_agents_node,
    "rag_search": _create_rag_search_node,
    "human_review": _create_human_review_node,
    "tool_call": _create_tool_call_node,
    "legal_workflow": _create_legal_workflow_node,
    "review_table": _create_review_table_node,
    "output": _create_output_node,
    "user_input": _create_user_input_node,
    "trigger": _create_trigger_node,
    "delivery": _create_delivery_node,
}

VALID_NODE_TYPES = set(NODE_FACTORIES.keys())


# ---------------------------------------------------------------------------
# Graph Validation
# ---------------------------------------------------------------------------


class GraphValidationError(Exception):
    """Raised when the graph JSON is invalid."""
    pass


def validate_graph(graph_json: Dict[str, Any]) -> List[str]:
    """Validate a React Flow graph JSON. Returns list of errors (empty = valid)."""
    errors: list[str] = []

    nodes = graph_json.get("nodes", [])
    edges = graph_json.get("edges", [])

    if not nodes:
        errors.append("Graph must have at least one node")
        return errors

    node_ids = set()
    for node in nodes:
        nid = node.get("id")
        ntype = node.get("type")

        if not nid:
            errors.append("Node missing 'id'")
        if nid in node_ids:
            errors.append(f"Duplicate node id: {nid}")
        node_ids.add(nid)

        if ntype not in VALID_NODE_TYPES:
            errors.append(f"Invalid node type '{ntype}' for node '{nid}'. Valid: {VALID_NODE_TYPES}")

    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source not in node_ids:
            errors.append(f"Edge source '{source}' not found in nodes")
        if target not in node_ids:
            errors.append(f"Edge target '{target}' not found in nodes")

    return errors


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------


class WorkflowCompiler:
    """Compiles React Flow graph JSON into an executable LangGraph StateGraph."""

    def compile(self, graph_json: Dict[str, Any]) -> CompiledStateGraph:
        """
        Compile a graph definition into a LangGraph compiled graph.

        Args:
            graph_json: { "nodes": [...], "edges": [...] }

        Returns:
            CompiledStateGraph ready to execute.

        Raises:
            GraphValidationError: If graph is invalid.
            ImportError: If LangGraph is not available.
        """
        if not LANGGRAPH_AVAILABLE:
            raise ImportError("LangGraph not installed. Install with: pip install langgraph")

        # Validate structure
        errors = validate_graph(graph_json)
        if errors:
            raise GraphValidationError(f"Graph validation failed: {'; '.join(errors)}")

        # Validate execution limits (warn only)
        from app.services.ai.sandbox import ExecutionLimits
        from app.services.ai.sandbox.execution_limits import validate_workflow_graph
        limit_errors = validate_workflow_graph(graph_json)
        if limit_errors:
            for err in limit_errors:
                logger.warning(f"Workflow validation: {err}")

        nodes = graph_json["nodes"]
        edges = graph_json["edges"]

        # Build StateGraph
        graph = StateGraph(WorkflowState)

        # Add nodes
        condition_nodes = set()
        for node in nodes:
            node_id = node["id"]
            node_type = node["type"]
            node_data = node.get("data", {})
            node_config = {**node_data, "id": node_id}

            if node_type == "condition":
                condition_nodes.add(node_id)
                # Condition nodes are handled as conditional edges
                continue

            factory = NODE_FACTORIES[node_type]
            graph.add_node(node_id, factory(node_config))

        # Build adjacency map
        adjacency: Dict[str, List[str]] = {}
        for edge in edges:
            src = edge["source"]
            tgt = edge["target"]
            adjacency.setdefault(src, []).append(tgt)

        node_type_by_id = {n["id"]: n.get("type") for n in nodes}

        # Normalize simple fan-out to multiple delivery nodes by chaining them.
        # The visual builder commonly models "send to email + calendar + teams" as
        # multiple outgoing edges. LangGraph requires all nodes reachable and this
        # compiler supports only a single next node per step, so we serialize
        # delivery fan-out deterministically.
        for src, outs in list(adjacency.items()):
            if len(outs) <= 1:
                continue
            non_condition = [t for t in outs if t not in condition_nodes]
            if len(non_condition) <= 1:
                continue
            if all(node_type_by_id.get(t) == "delivery" for t in non_condition):
                # Chain: src -> delivery1 -> delivery2 -> ... (only if deliveries have no explicit next)
                adjacency[src] = [non_condition[0]]
                for a, b in zip(non_condition, non_condition[1:]):
                    if adjacency.get(a):
                        # If a delivery already has an outgoing edge, don't rewrite (leave as-is).
                        # This keeps behavior predictable for complex graphs.
                        break
                    adjacency[a] = [b]

        # Find entry point (node with no incoming edges)
        targets = {e["target"] for e in edges}
        entry_nodes = [n["id"] for n in nodes if n["id"] not in targets]
        if not entry_nodes:
            entry_nodes = [nodes[0]["id"]]

        # If there are multiple root nodes (common in templates where several input
        # nodes feed the same downstream prompt), LangGraph compilation fails due to
        # unreachable roots. We rewrite the adjacency of root input nodes into a
        # deterministic chain when it's safe (all roots have the same single target).
        if len(entry_nodes) > 1:
            input_like = {"file_upload", "selection", "user_input"}
            if all(node_type_by_id.get(nid) in input_like for nid in entry_nodes):
                next_targets = []
                ok = True
                for nid in entry_nodes:
                    outs = adjacency.get(nid, [])
                    if len(outs) != 1:
                        ok = False
                        break
                    next_targets.append(outs[0])
                common_target = next_targets[0] if next_targets else None
                if ok and common_target and all(t == common_target for t in next_targets):
                    for a, b in zip(entry_nodes, entry_nodes[1:]):
                        adjacency[a] = [b]
                    adjacency[entry_nodes[-1]] = [common_target]

        # Set entry point
        entry = entry_nodes[0]
        if entry in condition_nodes:
            # If entry is condition, skip to first target
            first_targets = adjacency.get(entry, [])
            entry = first_targets[0] if first_targets else nodes[0]["id"]
        graph.set_entry_point(entry)

        # Add edges
        for node in nodes:
            node_id = node["id"]
            if node_id in condition_nodes:
                continue

            next_nodes = adjacency.get(node_id, [])

            if not next_nodes:
                # Terminal node
                graph.add_edge(node_id, END)
            elif len(next_nodes) == 1:
                target = next_nodes[0]
                if target in condition_nodes:
                    # Next is a condition node — add conditional edges
                    cond_node = next(n for n in nodes if n["id"] == target)
                    cond_config = {**cond_node.get("data", {}), "id": target}
                    cond_fn = _create_condition_node(cond_config)
                    cond_targets = adjacency.get(target, [])

                    if cond_targets:
                        branches = cond_config.get("branches", {})
                        # Build mapping from condition output to node
                        path_map = {}
                        for t in cond_targets:
                            path_map[t] = t
                        # Add all branch values pointing to targets
                        for bk, bv in branches.items():
                            if bv in {n["id"] for n in nodes}:
                                path_map[bv] = bv

                        graph.add_conditional_edges(node_id, cond_fn, path_map)
                    else:
                        graph.add_edge(node_id, END)
                else:
                    graph.add_edge(node_id, target)
            else:
                # Multiple targets — first non-condition (fan-out not supported)
                non_condition_targets = [t for t in next_nodes if t not in condition_nodes]
                if len(non_condition_targets) > 1:
                    logger.warning(
                        f"[WorkflowCompiler] Node '{node_id}' has {len(non_condition_targets)} "
                        f"non-condition targets, only first will be used: {non_condition_targets}"
                    )
                for t in next_nodes:
                    if t not in condition_nodes:
                        graph.add_edge(node_id, t)
                        break

        # Identify HIL nodes for interrupt_before
        hil_nodes = [
            n["id"] for n in nodes if n["type"] == "human_review"
        ]

        # Use MemorySaver checkpointer for HIL state persistence
        checkpointer = None
        if hil_nodes:
            try:
                from langgraph.checkpoint.memory import MemorySaver
                checkpointer = MemorySaver()
            except ImportError:
                logger.warning("[WorkflowCompiler] MemorySaver not available, HIL resume may not work")

        compiled = graph.compile(
            interrupt_before=hil_nodes if hil_nodes else None,
            checkpointer=checkpointer,
        )

        logger.info(
            f"[WorkflowCompiler] Compiled graph: "
            f"{len(nodes)} nodes, {len(edges)} edges, "
            f"{len(hil_nodes)} HIL interrupts"
        )
        return compiled
