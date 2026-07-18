from __future__ import annotations

from typing import Any

from .authorization import ApprovalArtifact, IntentAuthorizer, build_request, decision_event_payload
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
            provenance="agentflight:authorization",
        )
        if decision.outcome != "allow":
            raise PermissionError(decision.reason_code)
        result = self.authorizer.execute(decision, function, **arguments)
        self.tool_call_count += 1
        self.recorder.record(EventType.TOOL_RESULT, name, {"result": result}, parent_id=proposal.id)
        return result
