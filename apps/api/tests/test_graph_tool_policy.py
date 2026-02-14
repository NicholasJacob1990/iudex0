from app.services.ai.orchestration.graph_tool_policy import (
    GraphIntent,
    classify_graph_intent,
    build_tool_allowlist,
)


def test_graph_ui_defaults_to_basic():
    intent = classify_graph_intent(user_prompt="oi", extra_instructions="MODO GRAFO (UI)")
    assert intent == GraphIntent.GRAPH_BASIC
    tools = build_tool_allowlist(user_prompt="oi", extra_instructions="MODO GRAFO (UI)")
    assert "ask_graph" in tools


def test_graph_gds_intent():
    intent = classify_graph_intent(user_prompt="mostre comunidades usando leiden", extra_instructions=None)
    assert intent == GraphIntent.GRAPH_GDS
    tools = build_tool_allowlist(user_prompt="mostre comunidades usando leiden", extra_instructions=None)
    assert "ask_graph" in tools
    assert "scan_graph_risk" not in tools


def test_graph_risk_intent_enables_risk_tools():
    intent = classify_graph_intent(user_prompt="faça um scan de risco de fraude", extra_instructions=None)
    assert intent == GraphIntent.GRAPH_RISK
    tools = build_tool_allowlist(user_prompt="faça um scan de risco de fraude", extra_instructions=None)
    assert "ask_graph" in tools
    assert "scan_graph_risk" in tools
    assert "audit_graph_edge" in tools
    assert "audit_graph_chain" in tools


def test_non_graph_prompt_does_not_enable_graph_tools():
    intent = classify_graph_intent(user_prompt="explique prescricao", extra_instructions=None)
    assert intent == GraphIntent.GRAPH_NONE
    tools = build_tool_allowlist(user_prompt="explique prescricao", extra_instructions=None)
    assert "ask_graph" not in tools

