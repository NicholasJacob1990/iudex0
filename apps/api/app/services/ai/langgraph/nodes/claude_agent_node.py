from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from loguru import logger

from app.services.ai.claude_agent.executor import AgentConfig, ClaudeAgentExecutor
from app.services.ai.shared.sse_protocol import SSEEventType
from app.services.ai.variable_resolver import VariableResolver


@dataclass
class ClaudeAgentNode:
    """
    LangGraph node wrapper for ClaudeAgentExecutor.

    The node compiles a prompt from workflow state, executes the Claude agent loop,
    and writes the result into `output`, `llm_responses`, `variables`, and `step_outputs`.
    """

    node_id: str
    prompt_template: str
    model: str = "claude-opus-4-6"
    system_prompt: str = ""
    max_iterations: int = 8
    max_tokens: int = 4096
    include_mcp: bool = True
    tool_names: Optional[List[str]] = None
    use_sdk: bool = True

    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        resolver = VariableResolver()
        prompt = resolver.resolve(self.prompt_template or "", state)
        if not prompt:
            prompt = str(state.get("input", "") or "")

        # Legacy placeholder interpolation for compatibility with existing prompt nodes.
        context = {
            "input": state.get("input", ""),
            "output": state.get("output", ""),
            "rag_results": state.get("rag_results", []),
            **(state.get("selections", {}) or {}),
        }
        for key, value in context.items():
            prompt = prompt.replace(f"{{{key}}}", str(value))

        logger.debug(
            f"[Workflow] claude_agent node {self.node_id}: model={self.model} use_sdk={self.use_sdk}"
        )

        config = AgentConfig(
            model=self.model,
            max_iterations=int(self.max_iterations),
            max_tokens=int(self.max_tokens),
            use_sdk=bool(self.use_sdk),
            enable_checkpoints=False,
        )
        executor = ClaudeAgentExecutor(config=config)
        executor.load_unified_tools(include_mcp=bool(self.include_mcp), tool_names=self.tool_names)

        final_text = ""
        done_metadata: Dict[str, Any] = {}

        async for event in executor.run(
            prompt=prompt,
            system_prompt=self.system_prompt,
            context=None,
            user_id=state.get("user_id"),
            case_id=state.get("case_id"),
            db=state.get("db"),
        ):
            if event.type == SSEEventType.TOKEN:
                final_text += str(event.data.get("token", "") or "")
                continue
            if event.type == SSEEventType.DONE:
                final_text = str(event.data.get("final_text", "") or final_text)
                done_metadata = (
                    dict(event.data.get("metadata", {}))
                    if isinstance(event.data.get("metadata"), dict)
                    else {}
                )
                continue
            if event.type == SSEEventType.ERROR:
                error_text = str(event.data.get("error", "Erro no ClaudeAgentNode"))
                logger.warning(f"[Workflow] claude_agent node {self.node_id} failed: {error_text}")
                final_text = final_text or f"[Erro no Claude Agent: {error_text}]"

        llm_responses = dict(state.get("llm_responses", {}))
        llm_responses[self.node_id] = final_text

        variables = dict(state.get("variables", {}))
        variables[f"@{self.node_id}"] = final_text
        variables[f"@{self.node_id}.output"] = final_text

        step_outputs = dict(state.get("step_outputs", {}))
        step_outputs[self.node_id] = {
            "output": final_text,
            "model": self.model,
            "metadata": done_metadata,
        }

        logs = list(state.get("logs", []))
        logs.append(
            {
                "node": self.node_id,
                "event": "claude_agent",
                "model": self.model,
                "max_iterations": self.max_iterations,
            }
        )

        return {
            **state,
            "output": final_text,
            "current_node": self.node_id,
            "llm_responses": llm_responses,
            "variables": variables,
            "step_outputs": step_outputs,
            "logs": logs,
        }

