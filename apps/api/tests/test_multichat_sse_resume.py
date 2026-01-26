import pytest


@pytest.mark.asyncio
async def test_multichat_sse_resume_replays_from_last_event_id():
    from app.api.endpoints.chat import ChatStreamSession, _stream_from_session, sse_event

    session = ChatStreamSession(request_id="req1", thread_id="thread1", user_id="user1")

    await session.append(sse_event({"type": "token", "delta": "a"}))
    await session.append(sse_event({"type": "token", "delta": "b"}))
    await session.append(sse_event({"type": "token", "delta": "c"}))

    session.done = True
    async with session._cond:
        session._cond.notify_all()

    collected = []
    async for ev in _stream_from_session(session, "1", heartbeat_interval=0.01):
        # Skip keepalive comments
        if ev.lstrip().startswith(":"):
            continue
        collected.append(ev)

    joined = "\n".join(collected)
    assert "id: 1" not in joined
    assert "id: 2" in joined
    assert "id: 3" in joined

