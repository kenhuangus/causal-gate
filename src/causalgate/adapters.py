from __future__ import annotations

import functools
import inspect
import json
import threading
from typing import Any

from agents.tracing import TracingProcessor

from .authorization import ApprovalArtifact, IntentAuthorizer, build_request, decision_event_payload
from .models import EventType
from .recorder import Recorder


class AgentsSDKTraceAdapter(TracingProcessor):
    """OpenAI Agents SDK tracing processor backed by a CausalGate Recorder."""
    def __init__(self, recorder: Recorder):
        self.recorder = recorder
        self._proposals: dict[str, str] = {}
        self._lock = threading.RLock()

    def on_tool_start(self, name: str, arguments: dict[str, Any]):
        return self.recorder.record(EventType.TOOL_PROPOSAL, "openai-agents", {"tool": name, "arguments": arguments})

    def on_tool_end(self, proposal_id: str, result: Any):
        return self.recorder.record(EventType.TOOL_RESULT, "openai-agents", {"result": result}, parent_id=proposal_id)

    def on_trace_start(self, trace) -> None:
        self.recorder.record_state_change({}, {"phase": "started", "trace_id": trace.trace_id}, node=trace.name)

    def on_trace_end(self, trace) -> None:
        self.recorder.record_state_change({"phase": "started"}, {"phase": "completed", "trace_id": trace.trace_id}, node=trace.name)

    def on_span_start(self, sdk_span) -> None:
        data = sdk_span.span_data
        if getattr(data, "type", None) != "function":
            return
        raw = getattr(data, "input", None)
        try:
            arguments = json.loads(raw) if isinstance(raw, str) else raw or {}
        except json.JSONDecodeError:
            arguments = {"input": raw}
        if not isinstance(arguments, dict):
            arguments = {"input": arguments}
        proposal = self.on_tool_start(getattr(data, "name", "function"), arguments)
        with self._lock:
            self._proposals[sdk_span.span_id] = proposal.id

    def on_span_end(self, sdk_span) -> None:
        data = sdk_span.span_data
        if getattr(data, "type", None) != "function":
            return
        with self._lock:
            proposal_id = self._proposals.pop(sdk_span.span_id, None)
        if proposal_id is None:
            return
        error = getattr(sdk_span, "error", None)
        if error:
            self.recorder.record(EventType.ERROR, "openai-agents", {"error": "AgentsSDKToolError"}, parent_id=proposal_id)
        else:
            self.on_tool_end(proposal_id, getattr(data, "output", None))

    def force_flush(self) -> None:
        self.recorder.flush()

    def shutdown(self) -> None:
        self.recorder.close()


class LangGraphTraceAdapter:
    def __init__(self, recorder: Recorder):
        self.recorder = recorder

    def on_node(self, node: str, state_before: dict[str, Any], state_after: dict[str, Any]):
        return self.recorder.record(EventType.STATE_MUTATION, "langgraph", {"node": node, "before": state_before, "after": state_after})

    def wrap_node(self, node: str, function):
        """Wrap a LangGraph node before passing it to StateGraph.add_node."""
        if inspect.iscoroutinefunction(function):
            @functools.wraps(function)
            async def async_wrapped(state, *args, **kwargs):
                result = await function(state, *args, **kwargs)
                self.on_node(node, state, result)
                return result
            return async_wrapped

        @functools.wraps(function)
        def wrapped(state, *args, **kwargs):
            result = function(state, *args, **kwargs)
            self.on_node(node, state, result)
            return result
        return wrapped


class MediatedToolExecutor:
    """Complete-mediation adapter for the fixed, ontology-mapped tool profile."""

    def __init__(self, recorder: Recorder, authorizer: IntentAuthorizer):
        self.recorder = recorder
        self.authorizer = authorizer
        self.tool_call_count = 0

    def call(
        self,
        name: str,
        arguments: dict[str, Any],
        function,
        *,
        parent_id: str | None = None,
        provenance: str = "application",
        data_classes: list[str] | None = None,
        approvals: list[ApprovalArtifact] | None = None,
        delegation_depth: int = 0,
    ):
        request = build_request(
            execution_id=self.recorder.execution.id,
            contract=self.recorder.execution.intent,
            tool=name,
            arguments=arguments,
            provenance=provenance,
            data_classes=data_classes,
            approvals=approvals,
            tool_call_count=self.tool_call_count,
            delegation_depth=delegation_depth,
        )
        decision = self.authorizer.authorize(request)
        proposal = self.recorder.record(
            EventType.TOOL_PROPOSAL,
            "agent",
            {"tool": name, "arguments": arguments, "blocked": decision.outcome != "allow"},
            parent_id=parent_id,
        )
        self.recorder.record(
            EventType.POLICY_DECISION,
            "intent-authorizer",
            decision_event_payload(decision),
            parent_id=proposal.id,
            provenance="causalgate:authorization",
        )
        if decision.outcome != "allow":
            raise PermissionError(decision.reason_code)
        result = self.authorizer.execute(decision, function, **arguments)
        self.tool_call_count += 1
        self.recorder.record(EventType.TOOL_RESULT, name, {"result": result}, parent_id=proposal.id)
        return result
