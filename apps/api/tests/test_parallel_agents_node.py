import pytest


@pytest.mark.asyncio
async def test_parallel_agents_node_merges_branch_outputs(monkeypatch):
    from app.services.ai.langgraph.nodes import parallel_agents_node as node_module

    class DummyClaudeAgentNode:
        def __init__(
            self,
            node_id: str,
            prompt_template: str,
            model: str = "claude-haiku-4-5",
            **kwargs,
        ):
            self.node_id = node_id
            self.prompt_template = prompt_template
            self.model = model

        async def __call__(self, state):
            rendered = self.prompt_template.replace("{input}", str(state.get("input", "")))
            output = f"{self.model}:{rendered}"
            step_outputs = dict(state.get("step_outputs", {}))
            step_outputs[self.node_id] = {"output": output, "metadata": {"iterations": 1}}
            return {
                **state,
                "output": output,
                "step_outputs": step_outputs,
            }

    monkeypatch.setattr(node_module, "ClaudeAgentNode", DummyClaudeAgentNode)

    node = node_module.ParallelAgentsNode(
        node_id="parallel_agents",
        prompt_templates=["Primeira {input}", "Segunda {input}"],
        models=["claude-haiku-4-5", "claude-sonnet-4-5"],
        aggregation_strategy="concat",
        max_parallel=2,
    )

    state = {
        "input": "consulta",
        "llm_responses": {},
        "variables": {},
        "step_outputs": {},
        "logs": [],
    }
    result = await node(state)

    assert "claude-haiku-4-5:Primeira consulta" in result["output"]
    assert "claude-sonnet-4-5:Segunda consulta" in result["output"]
    assert result["step_outputs"]["parallel_agents"]["metadata"]["branches_total"] == 2
    assert result["step_outputs"]["parallel_agents"]["metadata"]["errors_count"] == 0
    assert result["variables"]["@parallel_agents.output"] == result["output"]


@pytest.mark.asyncio
async def test_parallel_agents_node_keeps_successful_branches_on_failure(monkeypatch):
    from app.services.ai.langgraph.nodes import parallel_agents_node as node_module

    class DummyClaudeAgentNode:
        def __init__(
            self,
            node_id: str,
            prompt_template: str,
            model: str = "claude-haiku-4-5",
            **kwargs,
        ):
            self.node_id = node_id
            self.prompt_template = prompt_template
            self.model = model

        async def __call__(self, state):
            if "falhar" in self.prompt_template:
                raise RuntimeError("branch failed")
            rendered = self.prompt_template.replace("{input}", str(state.get("input", "")))
            output = f"{self.model}:{rendered}"
            return {
                **state,
                "output": output,
                "step_outputs": {
                    **dict(state.get("step_outputs", {})),
                    self.node_id: {"output": output, "metadata": {"iterations": 1}},
                },
            }

    monkeypatch.setattr(node_module, "ClaudeAgentNode", DummyClaudeAgentNode)

    node = node_module.ParallelAgentsNode(
        node_id="parallel_agents",
        prompt_templates=["ok {input}", "falhar {input}"],
        models=["claude-haiku-4-5", "claude-haiku-4-5"],
        aggregation_strategy="concat",
    )

    result = await node(
        {
            "input": "teste",
            "llm_responses": {},
            "variables": {},
            "step_outputs": {},
            "logs": [],
        }
    )

    assert "ok teste" in result["output"]
    assert result["step_outputs"]["parallel_agents"]["metadata"]["branches_total"] == 2
    assert result["step_outputs"]["parallel_agents"]["metadata"]["branches_ok"] == 1
    assert result["step_outputs"]["parallel_agents"]["metadata"]["errors_count"] == 1

