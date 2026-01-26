#!/usr/bin/env python3
"""
SSE Deep Research E2E checker (not a pytest test).

Example:
  python3 apps/api/scripts/check_deep_research_stream.py \\
    --base-url http://localhost:8000/api \\
    --token <JWT> \\
    --provider openai \\
    --query "Panorama jurisprudencial sobre responsabilidade civil do Estado"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, Iterable, List, Optional


def _iter_sse_data_lines(response: "requests.Response") -> Iterable[str]:
    buffer: List[str] = []
    for raw_line in response.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue
        line = raw_line.rstrip("\r")
        if not line:
            if buffer:
                yield "\n".join(buffer)
                buffer = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            buffer.append(line[5:].lstrip())
    if buffer:
        yield "\n".join(buffer)


def _parse_models(value: str) -> List[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _request_headers(token: Optional[str]) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def main() -> int:
    parser = argparse.ArgumentParser(description="Deep Research SSE stream checker")
    parser.add_argument("--base-url", default=os.getenv("IUDEX_BASE_URL", "http://localhost:8000/api"))
    parser.add_argument("--token", default=os.getenv("IUDEX_API_TOKEN"))
    parser.add_argument("--provider", choices=("openai", "google", "perplexity"), required=True)
    parser.add_argument("--model", default="")
    parser.add_argument("--effort", default="medium")
    parser.add_argument("--models", default=os.getenv("IUDEX_CHAT_MODELS", "gpt-4o-mini"))
    parser.add_argument("--query", default="Resumo sobre jurisprudência recente em responsabilidade civil do Estado.")
    parser.add_argument("--timeout", type=int, default=180)
    expect_group = parser.add_mutually_exclusive_group()
    expect_group.add_argument("--expect-sources", dest="expect_sources", action="store_true", default=True)
    expect_group.add_argument("--no-expect-sources", dest="expect_sources", action="store_false")
    parser.add_argument("--expect-error", action="store_true", default=False)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    headers = _request_headers(args.token)

    try:
        import requests  # type: ignore
    except ModuleNotFoundError:
        print("Missing dependency: requests. Install with `pip install requests`.", file=sys.stderr)
        return 1

    # 1) Create thread
    # Multi-model thread endpoints live under /multi-chat.
    create_url = f"{base_url}/multi-chat/threads"
    resp = requests.post(create_url, headers=headers, json={"title": "Deep Research SSE Test"}, timeout=30)
    if resp.status_code >= 300:
        print(f"Failed to create thread: {resp.status_code} {resp.text}", file=sys.stderr)
        return 1
    payload = resp.json() if isinstance(resp.json(), dict) else {}
    thread_id = payload.get("id") or payload.get("thread_id")
    if not thread_id:
        print(f"Thread id missing in response: {payload}", file=sys.stderr)
        return 1

    # 2) Stream message
    stream_url = f"{base_url}/multi-chat/threads/{thread_id}/messages"
    body = {
        "message": args.query,
        "models": _parse_models(args.models),
        "dense_research": True,
        "deep_research_effort": args.effort,
        "deep_research_provider": args.provider,
        # Make deep research deterministic for the checker.
        "research_policy": "force",
    }
    if args.model:
        body["deep_research_model"] = args.model

    print(f"Streaming: {stream_url}")
    response = requests.post(stream_url, headers=headers, json=body, stream=True, timeout=args.timeout)
    if response.status_code >= 300:
        print(f"Stream request failed: {response.status_code} {response.text}", file=sys.stderr)
        return 1

    seen_sources = 0
    seen_error = False
    first_error: Optional[str] = None
    last_event_type = None

    for data in _iter_sse_data_lines(response):
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        last_event_type = event_type
        if event_type == "step.add_source":
            seen_sources += 1
        if event_type in ("research_error", "error"):
            seen_error = True
            if first_error is None:
                first_error = str(event.get("message") or event.get("error") or "").strip() or "<no message>"

    print(f"Sources seen: {seen_sources}")
    print(f"Error seen: {seen_error}")
    if first_error:
        print(f"First error: {first_error[:240]}")
    if args.expect_error and not seen_error:
        print("Expected an error event, but none was seen.", file=sys.stderr)
        return 2
    if args.expect_sources and seen_sources == 0:
        print("Expected at least one step.add_source, but none was seen.", file=sys.stderr)
        return 3
    print(f"Last event type: {last_event_type}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
