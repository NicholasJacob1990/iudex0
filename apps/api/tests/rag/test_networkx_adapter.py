import pytest


@pytest.fixture
def nx_adapter(tmp_path):
    from app.services.rag.core.graph_factory import NetworkXAdapter

    persist_path = tmp_path / "graph.json"
    return NetworkXAdapter(persist_path=str(persist_path), scope="global", scope_id="global")


def test_networkx_adapter_add_and_get_entity(nx_adapter):
    assert nx_adapter.add_entity(
        entity_id="lei_123",
        entity_type="lei",
        name="Lei 123",
        properties={"year": 2020},
    )

    data = nx_adapter.get_entity("lei_123")
    assert data is not None
    assert data["entity_id"] == "lei_123"
    assert data["entity_type"] == "lei"
    assert data["name"] == "Lei 123"


def test_networkx_adapter_relationship_and_neighbors(nx_adapter):
    nx_adapter.add_entity(entity_id="a", entity_type="lei", name="Lei A")
    nx_adapter.add_entity(entity_id="b", entity_type="artigo", name="Artigo B")

    assert nx_adapter.add_relationship(
        from_entity="a",
        to_entity="b",
        relationship_type="CITA",
        properties={"weight": 0.9},
    )

    neighbors = nx_adapter.get_neighbors(entity_id="a", max_hops=1)
    neighbor_ids = {n.get("entity_id") for n in neighbors}
    assert "b" in neighbor_ids


def test_networkx_adapter_search_and_context(nx_adapter):
    nx_adapter.add_entity(entity_id="sum_1", entity_type="sumula", name="Súmula 1")
    nx_adapter.add_entity(entity_id="tese_9", entity_type="tese", name="Tese 9")
    nx_adapter.add_relationship(from_entity="sum_1", to_entity="tese_9", relationship_type="RELACIONADA")

    hits = nx_adapter.search_entities("Súmula", limit=5)
    assert any(h.get("entity_id") == "sum_1" for h in hits)

    ctx = nx_adapter.get_context_for_query("Súmula 1", max_tokens=200)
    assert isinstance(ctx, str)
    assert "Súmula 1" in ctx or "Sum" in ctx  # tolerate normalization

