"""Public CausalGate SDK."""
from .recorder import Recorder, active_recorder, span, start_execution, trace_tool
from .sinks import ApiTraceSink, InMemoryTraceSink, JsonlTraceSink, TraceSink, TraceSinkError
from .adapters import AgentsSDKTraceAdapter, LangGraphTraceAdapter, MediatedToolExecutor
from .causal_record import analyze_causal_record, intent_clauses
from .models import Event, EventType, Finding, CausalRecord, IntentContract, PolicyMode

__all__ = [
    "Recorder", "start_execution", "active_recorder", "span", "trace_tool",
    "TraceSink", "TraceSinkError", "InMemoryTraceSink", "JsonlTraceSink", "ApiTraceSink",
    "AgentsSDKTraceAdapter", "LangGraphTraceAdapter", "MediatedToolExecutor",
    "Event", "EventType", "Finding", "CausalRecord",
    "IntentContract", "PolicyMode", "analyze_causal_record", "intent_clauses",
]
__version__ = "0.1.0"
