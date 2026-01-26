import json

def _parse_sse_events(raw: str):
    events = []
    for frame in (raw or "").split("\n\n"):
        lines = [ln.rstrip("\r") for ln in frame.splitlines() if ln.strip()]
        data_lines = []
        for ln in lines:
            if ln.lstrip().startswith(":"):
                continue
            if ln.startswith("data:"):
                data_lines.append(ln[5:].lstrip())
        if not data_lines:
            continue
        payload = "\n".join(data_lines).strip()
        if not payload:
            continue
        try:
            events.append(json.loads(payload))
        except Exception:
            continue
    return events


def test_single_chat_gemini_grounding_emits_step_add_source(client, auth_headers, monkeypatch):
    # Ensure Gemini grounding metadata is not treated as "text tokens" and is surfaced as step.* + citations.
    from app.api.endpoints import chats as chats_endpoint

    async def fake_stream_vertex_gemini_async(_client, _prompt, **_kwargs):
        yield ("grounding_query", "jurisprudencia responsabilidade civil do estado")
        yield ("grounding_source", {"title": "Example", "url": "https://example.com/a"})
        yield ("text", "Resposta final.")

    monkeypatch.setattr(chats_endpoint, "get_gemini_client", lambda: object())
    monkeypatch.setattr(chats_endpoint, "stream_vertex_gemini_async", fake_stream_vertex_gemini_async)

    chat_resp = client.post(
        "/api/chats/",
        headers=auth_headers,
        json={"title": "t", "mode": "MINUTA", "context": {}},
    )
    assert chat_resp.status_code == 200
    chat_id = chat_resp.json()["id"]

    resp = client.post(
        f"/api/chats/{chat_id}/messages/stream",
        headers=auth_headers,
        json={"content": "oi", "model": "gemini-3-flash"},
    )
    assert resp.status_code == 200
    events = _parse_sse_events(resp.text)

    assert any(e.get("type") == "step.start" for e in events)
    assert any(e.get("type") == "step.add_query" for e in events)
    assert any(e.get("type") == "step.add_source" for e in events)
    done = next(e for e in events if e.get("type") == "done")
    citations = done.get("citations") or []
    assert any(c.get("url") == "https://example.com/a" for c in citations)
