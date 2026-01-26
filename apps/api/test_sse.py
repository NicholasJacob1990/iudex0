"""
SSE smoke script (NOT a pytest test).

This file used to be picked up by pytest due to the `test_*.py` naming pattern,
but it depends on optional local tooling (`sseclient`) and a running backend.
"""

__test__ = False

import json
from typing import Optional

def main(url: Optional[str] = None) -> int:
    import requests

    try:
        import sseclient  # type: ignore
    except ModuleNotFoundError:
        raise SystemExit(
            "Missing optional dependency `sseclient`.\n"
            "Install: `pip install sseclient-py` (or run this script from an env that has it)."
        )

    url = url or "http://localhost:8001/api/transcription/vomo/batch/stream"
    files = [("files", ("test_audio.txt", b"dummy content", "text/plain"))]
    data = {
        "mode": "RAW",
        "thinking_level": "low",
        "model_selection": "gemini-3-flash-preview",
    }

    print(f"Connecting to {url}...")
    try:
        response = requests.post(url, files=files, data=data, stream=True, timeout=60)
        print(f"Response status: {response.status_code}")

        client = sseclient.SSEClient(response)
        for event in client.events():
            print(f"Event: {event.event}")
            print(f"Data: {event.data}")
            if event.event in ("complete", "error"):
                break
    except Exception as e:
        print(f"Error: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
