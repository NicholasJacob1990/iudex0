from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger

from .claude_agent_node import ClaudeAgentNode


@dataclass
class ParallelAgentsNode:
    """
    Execute multiple ClaudeAgentNode branches in parallel and merge outputs.

    This node is intentionally lightweight and deterministic:
    - each branch receives an isolated copy of the workflow state
    - branch failures are captured and do not fail the whole node
    - merged output is written back to the standard workflow keys
    """

    node_id: str
    prompt_templates: List[str] = field(default_factory=list)
    models: Optional[List[str]] = None
    system_prompt: str = ""
    max_iterations: int = 4
    max_tokens: int = 2048
    include_mcp: bool = False
    tool_names: Optional[List[str]] = None
    use_sdk: bool = False
    max_parallel: int = 3
    aggregation_strategy: str = "concat"  # concat | best_effort | json

    async def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        prompts = self._resolve_prompts(state)
        if not prompts:
            prompts = ["{input}"]

        semaphore = asyncio.Semaphore(max(1, min(int(self.max_parallel), 8)))
        tasks = [
            asyncio.create_task(self._run_branch(index=i, prompt_template=prompt, state=state, semaphore=semaphore))
            for i, prompt in enumerate(prompts)
        ]
        branch_results = await asyncio.gather(*tasks)

        successes = [item for item in branch_results if not item.get("error")]
        errors = [item for item in branch_results if item.get("error")]
        merged_output = self._merge_outputs(successes)

        llm_responses = dict(state.get("llm_responses", {}))
        llm_responses[self.node_id] = merged_output

        variables = dict(state.get("variables", {}))
        variables[f"@{self.node_id}"] = merged_output
        variables[f"@{self.node_id}.output"] = merged_output
        variables[f"@{self.node_id}.branches"] = branch_results

        step_outputs = dict(state.get("step_outputs", {}))
        step_outputs[self.node_id] = {
            "output": merged_output,
            "branches": branch_results,
            "metadata": {
                "branches_total": len(branch_results),
                "branches_ok": len(successes),
                "errors_count": len(errors),
                "aggregation_strategy": self.aggregation_strategy,
            },
        }

        logs = list(state.get("logs", []))
        logs.append(
            {
                "node": self.node_id,
                "event": "parallel_agents",
                "branches_total": len(branch_results),
                "branches_ok": len(successes),
                "errors_count": len(errors),
                "aggregation_strategy": self.aggregation_strategy,
            }
        )

        return {
            **state,
            "output": merged_output,
            "current_node": self.node_id,
            "llm_responses": llm_responses,
            "variables": variables,
            "step_outputs": step_outputs,
            "logs": logs,
        }

    async def _run_branch(
        self,
        *,
        index: int,
        prompt_template: str,
        state: Dict[str, Any],
        semaphore: asyncio.Semaphore,
    ) -> Dict[str, Any]:
        branch_id = f"{self.node_id}_branch_{index + 1}"
        model = self._resolve_model(index)
        branch_state = {
            **state,
            "llm_responses": dict(state.get("llm_responses", {})),
            "variables": dict(state.get("variables", {})),
            "step_outputs": dict(state.get("step_outputs", {})),
            "logs": list(state.get("logs", [])),
        }

        branch_node = ClaudeAgentNode(
            node_id=branch_id,
            prompt_template=prompt_template,
            model=model,
            system_prompt=self.system_prompt,
            max_iterations=int(self.max_iterations),
            max_tokens=int(self.max_tokens),
            include_mcp=bool(self.include_mcp),
            tool_names=self.tool_names,
            use_sdk=bool(self.use_sdk),
        )

        async with semaphore:
            try:
                result = await branch_node(branch_state)
            except Exception as exc:
                logger.warning(f"[Workflow] parallel branch {branch_id} failed: {exc}")
                return {
                    "branch_id": branch_id,
                    "index": index,
                    "model": model,
                    "prompt_template": prompt_template,
                    "output": "",
                    "error": str(exc),
                }

        output = str(result.get("output", "") or "")
        branch_step = result.get("step_outputs", {}).get(branch_id, {}) if isinstance(result, dict) else {}
        metadata = branch_step.get("metadata", {}) if isinstance(branch_step, dict) else {}
        return {
            "branch_id": branch_id,
            "index": index,
            "model": model,
            "prompt_template": prompt_template,
            "output": output,
            "error": None,
            "metadata": metadata if isinstance(metadata, dict) else {},
        }

    def _resolve_model(self, index: int) -> str:
        if not self.models:
            return "claude-haiku-4-5"
        if index < len(self.models):
            return str(self.models[index] or "claude-haiku-4-5")
        return str(self.models[-1] or "claude-haiku-4-5")

    def _resolve_prompts(self, state: Dict[str, Any]) -> List[str]:
        prompts = [str(item).strip() for item in (self.prompt_templates or []) if str(item).strip()]
        if prompts:
            return prompts
        fallback = str(state.get("input") or state.get("output") or "").strip()
        if fallback:
            return [fallback]
        return []

    def _merge_outputs(self, branches: List[Dict[str, Any]]) -> str:
        if not branches:
            return ""

        strategy = (self.aggregation_strategy or "concat").strip().lower()
        if strategy == "json":
            payload = [
                {
                    "branch_id": item.get("branch_id"),
                    "model": item.get("model"),
                    "output": item.get("output"),
                }
                for item in branches
            ]
            return json.dumps(payload, ensure_ascii=False)

        if strategy == "best_effort":
            best = max(branches, key=lambda item: len(str(item.get("output") or "")))
            return str(best.get("output") or "")

        chunks: List[str] = []
        for item in sorted(branches, key=lambda value: int(value.get("index", 0))):
            chunks.append(
                f"### Branch {int(item.get('index', 0)) + 1} ({item.get('model', 'unknown')})\n"
                f"{str(item.get('output') or '').strip()}"
            )
        return "\n\n".join(chunk for chunk in chunks if chunk.strip())

