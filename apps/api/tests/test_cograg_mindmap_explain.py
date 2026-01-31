"""
Tests for MindMap-Explain node (rule-based reasoning graph artifact).
"""

from __future__ import annotations

import pytest

from app.services.rag.core.cograg.nodes.mindmap_explain import mindmap_explain_node


@pytest.mark.asyncio
async def test_mindmap_explain_gated_off_by_default():
    state = {
        "query": "Teste",
        "verification_status": "approved",
        "sub_questions": [],
        "sub_answers": [],
        "evidence_map": {},
        "cograg_mindmap_explain_enabled": False,
        "cograg_audit_mode": False,
    }
    out = await mindmap_explain_node(state)
    assert out["reasoning_graph"] is None
    assert out["reasoning_graph_mermaid"] is None


@pytest.mark.asyncio
async def test_mindmap_explain_generates_json_and_mermaid():
    state = {
        "query": "Qual é o prazo prescricional?",
        "verification_status": "approved",
        "sub_questions": [{"node_id": "node-1", "question": "Qual prazo?"}],
        "sub_answers": [{"node_id": "node-1", "answer": "Prazo X. [ref:abc]", "evidence_refs": ["abc"]}],
        "evidence_map": {
            "node-1": {
                "graph_triples": [{"text": "(Art. 7)-[:PREVE]->(prazo)"}],
                "graph_paths": [{"path_uid": "p1", "path_text": "(Art. 7)-[:PREVE]->(prazo)"}],
            }
        },
        "cograg_mindmap_explain_enabled": True,
        "cograg_mindmap_explain_format": "both",
    }
    out = await mindmap_explain_node(state)
    assert out["reasoning_graph"] is not None
    assert out["reasoning_graph_mermaid"] is not None
    assert "nodes" in out["reasoning_graph"]
    assert "edges" in out["reasoning_graph"]
    assert "graph TD" in out["reasoning_graph_mermaid"]
