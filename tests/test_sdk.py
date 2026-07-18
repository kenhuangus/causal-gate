import asyncio
import json
from types import SimpleNamespace

import pytest
from agents.tracing import TracingProcessor, function_span, set_trace_processors, trace

from causalgate import (
    AgentsSDKTraceAdapter,
    ApiTraceSink,
    InMemoryTraceSink,
    IntentContract,
    JsonlTraceSink,
    LangGraphTraceAdapter,
    Recorder,
    active_recorder,
    span,
    start_execution,
    trace_tool,
)
from causalgate.models import EventType


def intent() -> IntentContract:
    return IntentContract(goal="Exercise the SDK.", allowed_tools=["lookup"])


def test_public_lifecycle_helpers_and_span_events():
    recorder = start_execution(intent())
    with recorder:
        assert active_recorder() is recorder
        with span("prepare", {"stage": 1}):
            recorder.record_retrieval("public document")
        recorder.finish_execution("done")
    assert [event.type for event in recorder.execution.events] == [
        EventType.USER_INTENT,
        EventType.SPAN_START,
        EventType.RETRIEVAL,
        EventType.SPAN_END,
        EventType.FINAL_ANSWER,
    ]


def test_trace_tool_awaits_async_result_and_records_async_error():
    @trace_tool("lookup")
    async def lookup(*, query: str):
        await asyncio.sleep(0)
        return {"query": query}

    @trace_tool("lookup")
    async def fail(*, query: str):
        await asyncio.sleep(0)
        raise LookupError(query)

    async def run():
        with Recorder(intent()) as recorder:
            assert await lookup(query="safe") == {"query": "safe"}
            with pytest.raises(LookupError):
                await fail(query="missing")
        return recorder

    recorder = asyncio.run(run())
    assert [event.type for event in recorder.execution.events][-4:] == [
        EventType.TOOL_PROPOSAL,
        EventType.TOOL_RESULT,
        EventType.TOOL_PROPOSAL,
        EventType.ERROR,
    ]
    assert recorder.execution.events[-3].payload["result"] == {"query": "safe"}


def test_in_memory_and_jsonl_sinks_receive_only_completed_redacted_records(tmp_path):
    memory = InMemoryTraceSink()
    with Recorder(intent(), sink=memory) as recorder:
        recorder.record_tool_result({"api_key": "never-write-me"})
        recorder.finish("done")
    assert memory.executions[recorder.execution.id].status == "complete"

    path = tmp_path / "trace.jsonl"
    sink = JsonlTraceSink(path)
    with Recorder(intent(), sink=sink) as recorder:
        recorder.record_tool_result({"api_key": "never-write-me"})
        recorder.finish("done")
    recorder.close()
    content = path.read_text(encoding="utf-8")
    assert "never-write-me" not in content
    assert "[REDACTED]" in content
    assert [json.loads(line)["kind"] for line in content.splitlines()] == [
        "execution_start", "event", "event", "event", "execution_end",
    ]


def test_sink_fail_open_and_fail_closed_modes():
    class BrokenSink:
        def start(self, execution): raise OSError("offline")
        def write(self, event): raise OSError("offline")
        def finish(self, execution): raise OSError("offline")
        def flush(self): raise OSError("offline")
        def close(self): raise OSError("offline")

    with Recorder(intent(), sink=BrokenSink()) as recorder:
        recorder.finish("local result survives")
    assert recorder.execution.events[-1].payload["output"] == "local result survives"
    assert recorder.sink_errors

    with pytest.raises(OSError, match="offline"):
        with Recorder(intent(), sink=BrokenSink(), fail_open=False):
            pass


def test_api_sink_buffers_redacts_and_preserves_idempotency():
    class FakeApiSink(ApiTraceSink):
        def __init__(self):
            super().__init__("http://causalgate.test", "admin", batch_size=2)
            self.requests = []

        def _request(self, method, path, body=None, headers=None):
            self.requests.append((method, path, body, headers))
            if path == "/api/v1/executions":
                return {"id": "run_remote"}
            return {}

    sink = FakeApiSink()
    with Recorder(intent(), sink=sink, fail_open=False) as recorder:
        recorder.record_tool_result({"access_token": "never-export"})
        recorder.finish("done")
    event_requests = [request for request in sink.requests if request[1].endswith("/events")]
    assert event_requests
    assert all(request[2]["execution_id"] == "run_remote" for request in event_requests)
    assert all(request[3]["Idempotency-Key"] == request[2]["idempotency_key"] for request in event_requests)
    assert "never-export" not in json.dumps(event_requests)


def test_openai_agents_processor_implements_official_interface_and_records_function_spans():
    recorder = Recorder(intent())
    adapter = AgentsSDKTraceAdapter(recorder)
    assert isinstance(adapter, TracingProcessor)
    trace = SimpleNamespace(trace_id="trace_1", name="research")
    data = SimpleNamespace(type="function", name="lookup", input='{"query":"safe"}', output={"answer": 1})
    sdk_span = SimpleNamespace(span_id="span_1", span_data=data, error=None)
    adapter.on_trace_start(trace)
    adapter.on_span_start(sdk_span)
    adapter.on_span_end(sdk_span)
    adapter.on_trace_end(trace)
    assert [event.type for event in recorder.execution.events] == [
        EventType.STATE_MUTATION,
        EventType.TOOL_PROPOSAL,
        EventType.TOOL_RESULT,
        EventType.STATE_MUTATION,
    ]


def test_openai_agents_processor_receives_real_sdk_trace_lifecycle():
    recorder = Recorder(intent())
    adapter = AgentsSDKTraceAdapter(recorder)
    set_trace_processors([adapter])
    try:
        with trace("research"):
            with function_span("lookup", input='{"query":"safe"}') as sdk_span:
                sdk_span.span_data.output = {"answer": 1}
    finally:
        set_trace_processors([])
    assert [event.type for event in recorder.execution.events] == [
        EventType.STATE_MUTATION,
        EventType.TOOL_PROPOSAL,
        EventType.TOOL_RESULT,
        EventType.STATE_MUTATION,
    ]


def test_langgraph_adapter_wraps_sync_and_async_nodes():
    recorder = Recorder(intent())
    adapter = LangGraphTraceAdapter(recorder)

    def sync_node(state):
        return {"count": state["count"] + 1}

    async def async_node(state):
        await asyncio.sleep(0)
        return {"count": state["count"] + 2}

    assert adapter.wrap_node("sync", sync_node)({"count": 0}) == {"count": 1}
    assert asyncio.run(adapter.wrap_node("async", async_node)({"count": 0})) == {"count": 2}
    assert [event.payload["node"] for event in recorder.execution.events] == ["sync", "async"]
