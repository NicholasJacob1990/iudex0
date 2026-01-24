import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))


def test_qdrant_build_filter_accepts_metadata_filters():
    from app.services.rag.storage.qdrant_service import QdrantService

    f = QdrantService.build_filter(
        tenant_id="t1",
        user_id="u1",
        scopes=["global"],
        sigilo_levels=["publico"],
        metadata_filters={"tipo_peca": "peticao_inicial"},
    )

    keys = [getattr(cond, "key", None) for cond in getattr(f, "must", [])]
    assert "tipo_peca" in keys

