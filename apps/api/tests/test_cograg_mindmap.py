"""
Tests for CogGRAG mindmap data structures.

Covers: NodeState, MindMapNode, CognitiveTree — creation, traversal,
serialisation, and boundary conditions.
"""

import pytest

from app.services.rag.core.cograg.mindmap import (
    CognitiveTree,
    MindMapNode,
    NodeState,
)


# ═══════════════════════════════════════════════════════════════════════════
# NodeState
# ═══════════════════════════════════════════════════════════════════════════

class TestNodeState:
    def test_enum_values(self):
        assert NodeState.CONTINUE.value == "continue"
        assert NodeState.END.value == "end"

    def test_enum_from_value(self):
        assert NodeState("continue") == NodeState.CONTINUE
        assert NodeState("end") == NodeState.END


# ═══════════════════════════════════════════════════════════════════════════
# MindMapNode
# ═══════════════════════════════════════════════════════════════════════════

class TestMindMapNode:
    def test_creation_defaults(self):
        node = MindMapNode(node_id="n1", question="Q?", level=0)
        assert node.state == NodeState.END
        assert node.parent_id is None
        assert node.children == []
        assert node.answer is None
        assert node.verified is False
        assert node.is_leaf()

    def test_is_leaf_with_children(self):
        node = MindMapNode(
            node_id="n1", question="Q?", level=0,
            state=NodeState.CONTINUE, children=["n2"],
        )
        assert not node.is_leaf()

    def test_to_dict_roundtrip(self):
        node = MindMapNode(
            node_id="abc123",
            question="Qual o prazo prescricional?",
            level=1,
            state=NodeState.CONTINUE,
            parent_id="root",
            children=["c1", "c2"],
            answer="5 anos",
            evidence=[{"text": "Art. 206"}],
            verified=True,
            confidence=0.9,
            citations=["lei:10406"],
        )
        d = node.to_dict()
        restored = MindMapNode.from_dict(d)

        assert restored.node_id == "abc123"
        assert restored.question == "Qual o prazo prescricional?"
        assert restored.level == 1
        assert restored.state == NodeState.CONTINUE
        assert restored.parent_id == "root"
        assert restored.children == ["c1", "c2"]
        assert restored.answer == "5 anos"
        assert restored.verified is True
        assert restored.confidence == 0.9
        assert restored.citations == ["lei:10406"]

    def test_to_dict_evidence_count(self):
        node = MindMapNode(
            node_id="n1", question="Q?", level=0,
            evidence=[{"a": 1}, {"b": 2}],
        )
        d = node.to_dict()
        assert d["evidence_count"] == 2


# ═══════════════════════════════════════════════════════════════════════════
# CognitiveTree
# ═══════════════════════════════════════════════════════════════════════════

class TestCognitiveTree:
    def test_auto_root_creation(self):
        tree = CognitiveTree(root_question="Pergunta principal?")
        assert tree.root_id is not None
        root = tree.root()
        assert root is not None
        assert root.question == "Pergunta principal?"
        assert root.level == 0
        assert root.state == NodeState.CONTINUE
        assert tree.node_count() == 1

    def test_leaves_single_root(self):
        tree = CognitiveTree(root_question="Q?")
        root = tree.root()
        root.state = NodeState.END
        leaves = tree.leaves()
        assert len(leaves) == 1
        assert leaves[0].node_id == root.node_id

    def test_add_child(self):
        tree = CognitiveTree(root_question="Q?", max_children=3)
        root = tree.root()

        child = tree.add_child(root.node_id, "Sub-Q 1?")
        assert child is not None
        assert child.level == 1
        assert child.parent_id == root.node_id
        assert child.node_id in root.children
        assert root.state == NodeState.CONTINUE

    def test_add_child_respects_max_children(self):
        tree = CognitiveTree(root_question="Q?", max_children=2)
        root = tree.root()

        c1 = tree.add_child(root.node_id, "Sub 1?")
        c2 = tree.add_child(root.node_id, "Sub 2?")
        c3 = tree.add_child(root.node_id, "Sub 3?")  # Should fail

        assert c1 is not None
        assert c2 is not None
        assert c3 is None
        assert len(root.children) == 2

    def test_add_child_respects_max_depth(self):
        tree = CognitiveTree(root_question="Q?", max_depth=1)
        root = tree.root()

        # Root is level 0, child would be level 1 → exceeds max_depth=1
        child = tree.add_child(root.node_id, "Sub?")
        assert child is None

    def test_add_child_invalid_parent(self):
        tree = CognitiveTree(root_question="Q?")
        child = tree.add_child("nonexistent", "Sub?")
        assert child is None

    def test_multi_level_tree(self):
        tree = CognitiveTree(root_question="Q?", max_depth=3)
        root = tree.root()

        c1 = tree.add_child(root.node_id, "Sub 1?", state=NodeState.CONTINUE)
        c2 = tree.add_child(root.node_id, "Sub 2?", state=NodeState.END)

        c1_1 = tree.add_child(c1.node_id, "Sub 1.1?", state=NodeState.END)
        c1_2 = tree.add_child(c1.node_id, "Sub 1.2?", state=NodeState.END)

        assert tree.node_count() == 5
        assert tree.leaf_count() == 3  # c2, c1_1, c1_2
        assert tree.max_level() == 2

        level_0 = tree.nodes_by_level(0)
        assert len(level_0) == 1
        assert level_0[0].node_id == root.node_id

        level_1 = tree.nodes_by_level(1)
        assert len(level_1) == 2

        level_2 = tree.nodes_by_level(2)
        assert len(level_2) == 2

    def test_set_answer(self):
        tree = CognitiveTree(root_question="Q?")
        root = tree.root()

        tree.set_answer(
            root.node_id,
            answer="Resposta",
            evidence=[{"text": "evidencia"}],
            citations=["lei:123"],
            confidence=0.85,
        )
        assert root.answer == "Resposta"
        assert len(root.evidence) == 1
        assert root.citations == ["lei:123"]
        assert root.confidence == 0.85

    def test_set_answer_nonexistent_node(self):
        tree = CognitiveTree(root_question="Q?")
        # Should not raise
        tree.set_answer("nonexistent", answer="X")

    def test_mark_verified(self):
        tree = CognitiveTree(root_question="Q?")
        root = tree.root()
        assert root.verified is False

        tree.mark_verified(root.node_id)
        assert root.verified is True

        tree.mark_verified(root.node_id, verified=False)
        assert root.verified is False

    def test_to_dict_roundtrip(self):
        tree = CognitiveTree(root_question="Pergunta complexa?", max_depth=2, max_children=3)
        root = tree.root()
        tree.conditions = "Direito trabalhista, CLT art. 468"

        c1 = tree.add_child(root.node_id, "Sub 1?")
        c2 = tree.add_child(root.node_id, "Sub 2?")
        tree.set_answer(c1.node_id, "Resp 1", confidence=0.7)

        d = tree.to_dict()
        assert d["root_question"] == "Pergunta complexa?"
        assert d["conditions"] == "Direito trabalhista, CLT art. 468"
        assert d["node_count"] == 3
        assert d["leaf_count"] == 2
        assert d["max_depth"] == 2
        assert d["max_children"] == 3

        restored = CognitiveTree.from_dict(d)
        assert restored.root_question == "Pergunta complexa?"
        assert restored.conditions == "Direito trabalhista, CLT art. 468"
        assert restored.node_count() == 3
        assert restored.leaf_count() == 2
        assert restored.root_id == root.node_id

        restored_c1 = restored.nodes.get(c1.node_id)
        assert restored_c1 is not None
        assert restored_c1.answer == "Resp 1"
        assert restored_c1.confidence == 0.7

    def test_empty_tree(self):
        tree = CognitiveTree(root_question="")
        # Empty question still creates root
        assert tree.node_count() == 0  # Empty string → __post_init__ skips

    def test_leaves_of_continue_node_without_children(self):
        """A CONTINUE node with no children should still be a leaf."""
        tree = CognitiveTree(root_question="Q?")
        root = tree.root()
        # Root is CONTINUE by default but has no children
        assert root.state == NodeState.CONTINUE
        assert root.children == []
        assert root.is_leaf()  # is_leaf checks children == []
        assert tree.leaf_count() == 1
