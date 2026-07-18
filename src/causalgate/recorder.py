from __future__ import annotations

import contextvars
import functools
import inspect
import threading
from contextlib import contextmanager
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from .models import Event, EventType, Execution, IntentContract, PolicyMode
from .redaction import redacted_event_payload
from .sinks import TraceSink

_active: contextvars.ContextVar["Recorder | None"] = contextvars.ContextVar("causal_gate", default=None)


class Recorder:
    def __init__(self, intent: IntentContract, policy_mode: PolicyMode = PolicyMode.BASELINE,
                 execution_id: str | None = None, *, sink: TraceSink | None = None, fail_open: bool = True):
        self.execution = Execution(id=execution_id or f"run_{uuid4().hex[:12]}", policy_mode=policy_mode, intent=intent)
        self.sink = sink
        self.fail_open = fail_open
        self.sink_errors: list[str] = []
        self._token = None
        self._lock = threading.RLock()

    def _sink_call(self, method: str, *args: Any) -> None:
        if self.sink is None:
            return
        try:
            getattr(self.sink, method)(*args)
        except Exception as exc:
            if not self.fail_open:
                raise
            self.sink_errors.append(f"{method}: {type(exc).__name__}")

    def __enter__(self):
        self._token = _active.set(self)
        self._sink_call("start", self.execution)
        self.record(EventType.USER_INTENT, "user", {"goal": self.execution.intent.goal})
        return self

    def __exit__(self, *_):
        self.flush()
        if self._token is not None:
            _active.reset(self._token)

    def record(self, event_type: EventType, actor: str, payload: dict[str, Any], **kwargs: Any) -> Event:
        with self._lock:
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
                from .causal_record import intent_clauses

                if set(payload.get("evidence_event_ids", [])) - existing_ids:
                    raise ValueError("evidence must reference earlier events in this execution")
                valid_clause_ids = {clause.id for clause in intent_clauses(self.execution.intent)}
                if set(payload.get("intent_clause_ids", [])) - valid_clause_ids:
                    raise ValueError("intent clause does not exist in this execution contract")
            self.execution.events.append(event)
            self._sink_call("write", event)
            return event

    def finish(self, output: str, unsupported_claim: bool = False, evidence: list[str] | None = None,
               parent_id: str | None = None) -> Execution:
        self.record(EventType.FINAL_ANSWER, "agent", {
            "output": output,
            "evidence": evidence or [],
            "unsupported_claim": unsupported_claim,
        }, parent_id=parent_id)
        self.execution.status = "complete"
        self._sink_call("finish", self.execution)
        return self.execution

    finish_execution = finish

    def flush(self) -> None:
        self._sink_call("flush")

    def close(self) -> None:
        self._sink_call("close")

    def record_retrieval(self, document: Any, *, actor: str = "retrieval", **kwargs: Any) -> Event:
        return self.record(EventType.RETRIEVAL, actor, {"document": document}, **kwargs)

    def propose_tool(self, name: str, arguments: dict[str, Any], **kwargs: Any) -> Event:
        return self.record(EventType.TOOL_PROPOSAL, "agent", {"tool": name, "arguments": arguments}, **kwargs)

    def record_tool_result(self, result: Any, *, actor: str = "tool", **kwargs: Any) -> Event:
        return self.record(EventType.TOOL_RESULT, actor, {"result": result}, **kwargs)

    def record_state_change(self, before: Any, after: Any, *, node: str = "application", **kwargs: Any) -> Event:
        return self.record(EventType.STATE_MUTATION, "application", {"node": node, "before": before, "after": after}, **kwargs)

    @contextmanager
    def span(self, name: str, attributes: dict[str, Any] | None = None):
        start = self.record(EventType.SPAN_START, "application", {"name": name, "attributes": attributes or {}})
        try:
            yield start
        except Exception as exc:
            self.record(EventType.ERROR, "application", {"error": type(exc).__name__, "span": name}, parent_id=start.id)
            raise
        else:
            self.record(EventType.SPAN_END, "application", {"name": name}, parent_id=start.id)


def start_execution(intent: IntentContract, policy_mode: PolicyMode = PolicyMode.BASELINE, **kwargs: Any) -> Recorder:
    return Recorder(intent, policy_mode, **kwargs)


def active_recorder() -> Recorder:
    recorder = _active.get()
    if recorder is None:
        raise RuntimeError("no active CausalGate execution")
    return recorder


def span(name: str, attributes: dict[str, Any] | None = None):
    return active_recorder().span(name, attributes)


def trace_tool(name: str | None = None):
    def decorate(fn: Callable[..., Any]):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapped(*args: Any, **kwargs: Any):
                recorder = _active.get()
                proposal = recorder.propose_tool(name or fn.__name__, kwargs) if recorder else None
                try:
                    result = await fn(*args, **kwargs)
                    if recorder:
                        recorder.record_tool_result(result, actor=name or fn.__name__, parent_id=proposal.id)
                    return result
                except Exception as exc:
                    if recorder:
                        recorder.record(EventType.ERROR, name or fn.__name__, {"error": type(exc).__name__}, parent_id=proposal.id)
                    raise
            return async_wrapped

        @functools.wraps(fn)
        def wrapped(*args: Any, **kwargs: Any):
            recorder = _active.get()
            proposal = recorder.propose_tool(name or fn.__name__, kwargs) if recorder else None
            try:
                result = fn(*args, **kwargs)
                if recorder:
                    recorder.record_tool_result(result, actor=name or fn.__name__, parent_id=proposal.id)
                return result
            except Exception as exc:
                if recorder:
                    recorder.record(EventType.ERROR, name or fn.__name__, {"error": type(exc).__name__}, parent_id=proposal.id)
                raise
        return wrapped
    return decorate
