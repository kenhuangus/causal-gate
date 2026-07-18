"""Registration-only example. It makes no OpenAI API call."""

from agents.tracing import add_trace_processor

from causalgate import AgentsSDKTraceAdapter, IntentContract, Recorder


intent = IntentContract(goal="Research public vendor data.", allowed_tools=["lookup"])
recorder = Recorder(intent)
processor = AgentsSDKTraceAdapter(recorder)
add_trace_processor(processor)

print("CausalGate Agents SDK tracing processor registered")
