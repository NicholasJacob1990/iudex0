import os
import sys
import tempfile


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))


def test_argument_pack_builds_context_from_retrieval_results():
    from app.services.argument_pack import ARGUMENT_PACK
    from app.services.rag_graph import create_knowledge_graph

    with tempfile.TemporaryDirectory() as tmpdir:
        graph = create_knowledge_graph(persist_path=os.path.join(tmpdir, "kg.json"))

        ARGUMENT_PACK.ingest_chunk(
            graph,
            text="O autor afirma que o pagamento foi realizado em 2023.",
            metadata={
                "doc_id": "d1",
                "chunk_id": 1,
                "title": "Doc 1",
                "actor": "Autor",
                "stance": "asserts",
            },
        )

        results = [
            {
                "text": "O autor afirma que o pagamento foi realizado em 2023.",
                "metadata": {"doc_id": "d1", "chunk_id": 1, "title": "Doc 1"},
                "scope": "private",
                "scope_id": None,
            }
        ]

        ctx, stats = ARGUMENT_PACK.build_debate_context_from_results_with_stats(
            graph,
            results,
            hops=2,
        )

        assert "CLAIM:" in ctx
        assert "Evidências a favor" in ctx
        assert "doc_id=d1" in ctx
        assert "chunk_id=1" in ctx
        assert stats.get("results_seen") == 1
        assert stats.get("evidence_nodes") == 1
        assert (stats.get("seed_nodes") or 0) >= 1


def test_argument_pack_results_based_context_empty_when_no_matching_evidence():
    from app.services.argument_pack import ARGUMENT_PACK
    from app.services.rag_graph import create_knowledge_graph

    with tempfile.TemporaryDirectory() as tmpdir:
        graph = create_knowledge_graph(persist_path=os.path.join(tmpdir, "kg.json"))

        ARGUMENT_PACK.ingest_chunk(
            graph,
            text="A ré contesta o fato e nega a assinatura do contrato.",
            metadata={
                "doc_id": "d1",
                "chunk_id": 2,
                "title": "Doc 1",
                "actor": "Ré",
                "stance": "disputes",
            },
        )

        results = [{"metadata": {"doc_id": "other", "chunk_id": 999}}]
        ctx, stats = ARGUMENT_PACK.build_debate_context_from_results_with_stats(
            graph,
            results,
            hops=2,
        )

        assert ctx.strip() == ""
        assert stats.get("evidence_nodes") == 0

