from app.services.ai.claude_agent.executor import AgentConfig, ClaudeAgentExecutor
from app.services.ai.shared.sse_protocol import SSEEventType, done_event, token_event


def test_attach_trace_metadata_only_on_done_event():
    executor = ClaudeAgentExecutor(config=AgentConfig(enable_thinking=False, enable_checkpoints=False))
    trace_metadata = {
        "langsmith_run_id": "run-1",
        "langsmith_trace_url": "https://smith.langchain.com/public/run-1",
    }

    stream_event = token_event(job_id="job-1", token="chunk")
    enriched_stream = executor._attach_trace_metadata_to_done_event(stream_event, trace_metadata)
    assert enriched_stream.type == SSEEventType.TOKEN
    assert "langsmith_run_id" not in enriched_stream.data

    completion_event = done_event(job_id="job-1", final_text="ok")
    enriched_done = executor._attach_trace_metadata_to_done_event(completion_event, trace_metadata)
    assert enriched_done.type == SSEEventType.DONE
    assert enriched_done.data["langsmith_run_id"] == "run-1"
    assert enriched_done.data["langsmith_trace_url"] == "https://smith.langchain.com/public/run-1"
    assert enriched_done.data["metadata"]["langsmith_run_id"] == "run-1"
