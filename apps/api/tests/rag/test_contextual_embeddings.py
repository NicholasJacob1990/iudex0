from __future__ import annotations


def test_build_context_prefix_basic():
    from app.services.rag.core.contextual_embeddings import build_context_prefix

    meta = {
        "title": "Lei 8.666/1993",
        "source_type": "lei",
        "jurisdiction": "BR",
        "scope": "global",
    }
    prefix = build_context_prefix(meta, max_chars=240)
    assert "Documento: Lei 8.666/1993" in prefix
    assert "Fonte: lei" in prefix
    assert "Jurisdicao: BR" in prefix
    assert "Escopo: global" in prefix


def test_build_context_prefix_truncation():
    from app.services.rag.core.contextual_embeddings import build_context_prefix

    meta = {"title": "X" * 500, "source_type": "lei", "scope": "global"}
    prefix = build_context_prefix(meta, max_chars=80)
    assert len(prefix) <= 80
    # Uses an ellipsis when truncated
    assert prefix.endswith("…")


def test_build_embedding_input_disabled():
    from app.services.rag.core.contextual_embeddings import build_embedding_input

    emb_in, info = build_embedding_input(
        "Texto do art. 37 ...",
        {"title": "CF/88", "scope": "global"},
        enabled=False,
    )
    assert emb_in == "Texto do art. 37 ..."
    assert info.to_payload_fields() == {"_embedding_variant": "raw"}


def test_build_embedding_input_enabled_adds_prefix():
    from app.services.rag.core.contextual_embeddings import build_embedding_input

    emb_in, info = build_embedding_input(
        "Art. 37. A administracao publica ...",
        {"title": "Constituicao Federal", "source_type": "lei", "scope": "global", "jurisdiction": "BR"},
        enabled=True,
        max_prefix_chars=120,
    )
    assert emb_in.startswith("Documento:")
    assert "\n\nArt. 37." in emb_in
    payload = info.to_payload_fields()
    assert payload["_embedding_variant"] == "ctx_v1"
    assert "Documento:" in payload["_embedding_prefix"]

