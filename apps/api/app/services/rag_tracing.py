import os
from typing import Any, Dict


def emit_trace(event: str, payload: Dict[str, Any]) -> None:
    backend = os.getenv("RAG_TRACE_EXPORT", "").strip().lower()
    if not backend:
        return

    backends = [b.strip() for b in backend.replace("+", ",").split(",") if b.strip()]
    if "both" in backends:
        backends = ["otel", "langsmith"]

    for target in backends:
        if target == "otel":
            try:
                from opentelemetry import trace
            except Exception:
                continue
            tracer = trace.get_tracer("rag")
            with tracer.start_as_current_span(event) as span:
                for key, value in payload.items():
                    try:
                        span.set_attribute(key, value)
                    except Exception:
                        span.set_attribute(key, str(value))
            continue

        if target == "langsmith":
            try:
                from langsmith import Client
            except Exception:
                continue
            try:
                client = Client()
                client.create_run(
                    name=event,
                    run_type="tool",
                    inputs=payload,
                    outputs={},
                )
            except Exception:
                continue
