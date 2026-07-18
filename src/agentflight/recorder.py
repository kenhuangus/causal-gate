from __future__ import annotations

import contextvars
import functools
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from .models import Event, EventType, Execution, IntentContract, PolicyMode
from .redaction import redacted_event_payload

_active: contextvars.ContextVar["Recorder | None"] = contextvars.ContextVar("agentflight_recorder", default=None)


class Recorder:
    def __init__(self, intent: IntentContract, policy_mode: PolicyMode = PolicyMode.BASELINE, execution_id: str | None = None):
        self.execution = Execution(id=execution_id or f"run_{uuid4().hex[:12]}", policy_mode=policy_mode, intent=intent)
        self._token = None

    def __enter__(self):
        self._token = _active.set(self)
        self.record(EventType.USER_INTENT, "user", {"goal": self.execution.intent.goal})
        return self

    def __exit__(self, *_):
        if self._token is not None:
            _active.reset(self._token)

    def record(self, event_type: EventType, actor: str, payload: dict[str, Any], **kwargs: Any) -> Event:
        sensitivity = list(kwargs.get("sensitivity", []))
        kwargs.setdefault("logical_clock", len(self.execution.events) + 1)
        kwargs.setdefault("emitter_id", actor)
        event = Event(execution_id=self.execution.id, sequence=len(self.execution.events) + 1,
                      type=event_type, actor=actor, payload=payload,
                      redacted_payload=redacted_event_payload(payload, sensitivity), **kwargs)
        existing_ids = {existing.id for existing in self.execution.events}
        if event.parent_id and event.parent_id not in existing_ids:
            raise ValueError("parent must reference an earlier event in this execution")
        if set(event.causal_predecessor_ids) - existing_ids:
            raise ValueError("causal predecessors must reference earlier events in this execution")
        if event_type in {EventType.PLAN, EventType.DECISION}:
            from .flight_record import intent_clauses

            if set(payload.get("evidence_event_ids", [])) - existing_ids:
                raise ValueError("evidence must reference earlier events in this execution")
            valid_clause_ids = {clause.id for clause in intent_clauses(self.execution.intent)}
            if set(payload.get("intent_clause_ids", [])) - valid_clause_ids:
                raise ValueError("intent clause does not exist in this execution contract")
        self.execution.events.append(event)
        return event

    def finish(self, output: str, unsupported_claim: bool = False, evidence: list[str] | None = None,
               parent_id: str | None = None) -> Execution:
        self.record(EventType.FINAL_ANSWER, "agent", {"output": output, "evidence": evidence or []}, parent_id=parent_id)
        return self.execution


def trace_tool(name: str | None = None):
    def decorate(fn: Callable[..., Any]):
        @functools.wraps(fn)
        def wrapped(*args: Any, **kwargs: Any):
            recorder = _active.get()
            proposal = recorder.record(EventType.TOOL_PROPOSAL, "agent", {"tool": name or fn.__name__, "arguments": kwargs}) if recorder else None
            try:
                result = fn(*args, **kwargs)
                if recorder:
                    recorder.record(EventType.TOOL_RESULT, name or fn.__name__, {"result": result}, parent_id=proposal.id)
                return result
            except Exception as exc:
                if recorder:
                    recorder.record(EventType.ERROR, name or fn.__name__, {"error": type(exc).__name__}, parent_id=proposal.id)
                raise
        return wrapped
    return decorate
