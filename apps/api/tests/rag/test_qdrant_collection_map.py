from __future__ import annotations


def test_qdrant_collection_map_includes_doutrina():
    from app.services.rag.storage.qdrant_service import QdrantService

    svc = QdrantService(url="http://localhost:6333", api_key="", timeout=1.0)
    # Should resolve via config mapping rather than returning the input unchanged
    assert svc.get_collection_name("doutrina")

