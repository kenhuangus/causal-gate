# CausalGate Python SDK

CausalGate's SDK captures intent-linked execution evidence locally and can optionally export it to a private CausalGate API. Capture, redaction, deterministic analysis, and framework adapters do not require an OpenAI API key.

## Status and compatibility

- Package: `causal-gate` 0.1.x (alpha)
- Python: 3.11+
- OpenAI Agents SDK: `openai-agents` 0.18.x through the `TracingProcessor` interface
- LangGraph: node wrappers compatible with the v1 `StateGraph.add_node` contract; install the `langgraph` extra to run the example
- Stability: names exported from `causalgate.__all__` form the supported 0.1 public surface

Until a PyPI release exists, install from a checkout or GitHub:

```bash
pip install .
# or
pip install "causal-gate @ git+https://github.com/kenhuangus/causal-gate.git"
```

For LangGraph examples:

```bash
pip install ".[langgraph]"
```

## Minimal lifecycle

```python
from causalgate import IntentContract, start_execution, span, trace_tool

@trace_tool("lookup")
def lookup(*, query: str) -> dict:
    return {"answer": f"Public result for {query}"}

intent = IntentContract(goal="Research public vendor data.", allowed_tools=["lookup"])

with start_execution(intent) as recorder:
    with span("research"):
        result = lookup(query="Acme")
    execution = recorder.finish_execution(result["answer"])

print(execution.id)
```

`@trace_tool` supports both synchronous and asynchronous functions. It records proposals, results, and exception types. It does not persist exception messages or credentials.

## Sinks

The default recorder is process-local and performs no network I/O. Supply one sink when durable export is required:

- `InMemoryTraceSink`: test and embedded workflows.
- `JsonlTraceSink`: append-only, redacted local evidence.
- `ApiTraceSink`: buffered export to the authenticated private ingestion API.

```python
from causalgate import ApiTraceSink, Recorder

sink = ApiTraceSink("https://causalgate.example", admin_token="runtime-secret")
with Recorder(intent, sink=sink, fail_open=True) as recorder:
    recorder.finish("done")
recorder.close()
```

`fail_open=True` is the default: sink failures are recorded in `recorder.sink_errors` and do not break the host agent. Use `fail_open=False` for protected workflows that must not proceed without evidence delivery. `flush()` forces queued delivery; `close()` flushes and releases sink resources.

## OpenAI Agents SDK

The adapter implements the official `agents.tracing.TracingProcessor` interface. Register it once with the Agents SDK trace provider. It captures workflow boundaries and function-tool spans without making an extra model call or storing model prompts.

```python
from agents.tracing import add_trace_processor
from causalgate import AgentsSDKTraceAdapter, Recorder

recorder = Recorder(intent)
processor = AgentsSDKTraceAdapter(recorder)
add_trace_processor(processor)
```

The processor is global because that is the Agents SDK registration model. Create it for a process-level recorder or sink, register it during application startup, and call `processor.shutdown()` during application shutdown. The complete runnable wiring is in `examples/openai_agents_processor.py`; it does not run a model unless you explicitly add a `Runner.run` call and configure an API key.

## LangGraph

Wrap nodes before adding them to a graph:

```python
adapter = LangGraphTraceAdapter(recorder)
builder.add_node("research", adapter.wrap_node("research", research_node))
```

Both synchronous and asynchronous nodes are supported. The adapter records the incoming state and returned partial update. Configure sensitivity metadata or avoid putting secrets in graph state because application state is evidence input.

## Explicit recording helpers

`Recorder` exposes `record`, `record_retrieval`, `propose_tool`, `record_tool_result`, `record_state_change`, `span`, `finish_execution`, `flush`, and `close`. Low-level `record` calls use the validated `EventType` schema and reject invalid parent or causal references.

## Security defaults

- Sinks receive redacted payloads for durable export.
- API export requires an administrator token and never reads `OPENAI_API_KEY`.
- Provider tracing data is limited to workflow metadata and function-tool inputs/outputs; model prompt and generation bodies are not copied.
- Network export is disabled unless an `ApiTraceSink` is explicitly configured.
- Local capture can be fail-open; protected deployments can select fail-closed behavior.
