from __future__ import annotations

from typing import Any

from .models import EventType
from .recorder import Recorder


class AgentsSDKTraceAdapter:
    """Stable adapter boundary for OpenAI Agents SDK run/trace callbacks.

    Applications pass normalized callback dictionaries; no model call occurs here.
    This keeps capture testable and lets runtime integrations track SDK releases.
    """
    def __init__(self, recorder: Recorder):
        self.recorder = recorder

    def on_tool_start(self, name: str, arguments: dict[str, Any]):
        return self.recorder.record(EventType.TOOL_PROPOSAL, "openai-agents", {"tool": name, "arguments": arguments})

    def on_tool_end(self, proposal_id: str, result: Any):
        return self.recorder.record(EventType.TOOL_RESULT, "openai-agents", {"result": result}, parent_id=proposal_id)


class LangGraphTraceAdapter:
    def __init__(self, recorder: Recorder):
        self.recorder = recorder

    def on_node(self, node: str, state_before: dict[str, Any], state_after: dict[str, Any]):
        return self.recorder.record(EventType.STATE_MUTATION, "langgraph", {"node": node, "before": state_before, "after": state_after})

