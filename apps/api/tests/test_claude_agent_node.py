from unittest.mock import MagicMock

import pytest

from app.services.ai.shared.sse_protocol import done_event, token_event
from app.services.ai.workflow_compiler import validate_graph


@pytest.mark.asyncio
async def test_claude_agent_node_executes_and_updates_state(monkeypatch):
    from app.services.ai.langgraph.nodes import claude_agent_node as node_module

    class DummyExecutor:
        last_load_kwargs = None
        last_run_kwargs = None

        def __init__(self, config=None, tool_executor=None, client=None):
            self.config = config

        def load_unified_tools(self, include_mcp=True, tool_names=None, execution_context=None):
            DummyExecutor.last_load_kwargs = {
                "include_mcp": include_mcp,
                "tool_names": tool_names,
                "execution_context": execution_context,
            }

        async def run(
            self,
            prompt: str,
            system_prompt: str = "",
            context=None,
            job_id=None,
            initial_messages=None,
            user_id=None,
            case_id=None,
            session_id=None,
            db=None,
        ):
            DummyExecutor.last_run_kwargs = {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "context": context,
                "user_id": user_id,
                "case_id": case_id,
                "db": db,
            }
            yield token_event(job_id=job_id or "job", token="parcial ")
            yield done_event(
                job_id=job_id or "job",
                final_text="resposta final",
                metadata={"iterations": 2},
            )

    monkeypatch.setattr(node_module, "ClaudeAgentExecutor", DummyExecutor)

    node = node_module.ClaudeAgentNode(
        node_id="agent_node",
        prompt_template="Analise: {input}",
        model="claude-haiku-4-5",
        system_prompt="system",
        max_iterations=4,
        max_tokens=2048,
        include_mcp=False,
        tool_names=["search_rag"],
        use_sdk=False,
    )

    state = {
        "input": "peticao inicial",
        "variables": {},
        "step_outputs": {},
        "llm_responses": {},
        "logs": [],
        "user_id": "user-1",
        "case_id": "case-1",
        "db": MagicMock(),
    }

    result = await node(state)

    assert result["output"] == "resposta final"
    assert result["llm_responses"]["agent_node"] == "resposta final"
    assert result["variables"]["@agent_node"] == "resposta final"
    assert result["variables"]["@agent_node.output"] == "resposta final"
    assert result["step_outputs"]["agent_node"]["metadata"] == {"iterations": 2}

    assert DummyExecutor.last_load_kwargs == {
        "include_mcp": False,
        "tool_names": ["search_rag"],
        "execution_context": None,
    }
    assert DummyExecutor.last_run_kwargs is not None
    assert DummyExecutor.last_run_kwargs["prompt"] == "Analise: peticao inicial"
    assert DummyExecutor.last_run_kwargs["user_id"] == "user-1"
    assert DummyExecutor.last_run_kwargs["case_id"] == "case-1"


def test_workflow_compiler_accepts_claude_agent_node_type():
    graph = {
        "nodes": [
            {
                "id": "node-1",
                "type": "claude_agent",
                "data": {"prompt": "Analise {input}"},
            }
        ],
        "edges": [],
    }

    errors = validate_graph(graph)
    assert errors == []


def test_workflow_compiler_accepts_parallel_agents_node_type():
    graph = {
        "nodes": [
            {
                "id": "node-1",
                "type": "parallel_agents",
                "data": {"prompts": ["Analise {input}", "Valide {input}"]},
            }
        ],
        "edges": [],
    }

    errors = validate_graph(graph)
    assert errors == []
