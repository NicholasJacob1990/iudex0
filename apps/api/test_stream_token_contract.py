import pytest

from app.services.ai.shared.stream_token_contract import (
    build_compat_token_event,
    extract_stream_token_text,
)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"delta": "abc"}, "abc"),
        ({"token": "abc"}, "abc"),
        ({"delta": "abc", "token": "legacy"}, "abc"),
        ({}, ""),
        (None, ""),
    ],
    ids=["delta-only", "token-only", "delta-and-token", "empty", "none"],
)
def test_extract_stream_token_text(payload, expected):
    assert extract_stream_token_text(payload) == expected


def test_build_compat_token_event_emits_both_fields():
    event = build_compat_token_event("abc", phase="generation")
    assert event["type"] == "token"
    assert event["delta"] == "abc"
    assert event["token"] == "abc"
    assert event["phase"] == "generation"

