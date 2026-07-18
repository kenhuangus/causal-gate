from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PolicyMode(StrEnum):
    BASELINE = "baseline"
    PROTECTED = "protected"


class EventType(StrEnum):
    USER_INTENT = "user_intent"
    RETRIEVAL = "retrieval"
    TOOL_PROPOSAL = "tool_proposal"
    POLICY_DECISION = "policy_decision"
    APPROVAL = "approval"
    TOOL_RESULT = "tool_result"
    STATE_MUTATION = "state_mutation"
    FINAL_ANSWER = "final_answer"
    ERROR = "error"


class IntentContract(StrictModel):
    version: int = 1
    goal: str
    allowed_tools: list[str]
    prohibited_outcomes: list[str] = Field(default_factory=lambda: ["disclose protected data"])
    protected_resources: list[str] = Field(default_factory=list)
    approval_required: list[str] = Field(default_factory=list)
    completion_conditions: list[str] = Field(default_factory=list)


class Event(StrictModel):
    id: str = Field(default_factory=lambda: f"evt_{uuid4().hex[:12]}")
    execution_id: str
    sequence: int
    type: EventType
    actor: str
    payload: dict[str, Any]
    redacted_payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(default_factory=lambda: f"idem_{uuid4().hex}", min_length=8, max_length=128)
    parent_id: str | None = None
    provenance: str = "application"
    sensitivity: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = "1.0"

    @field_validator("payload")
    @classmethod
    def bounded_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        import json
        if len(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()) > 64_000:
            raise ValueError("payload exceeds 64KB")
        return value

    @model_validator(mode="after")
    def validate_shape(self):
        required = {
            EventType.USER_INTENT: {"goal"}, EventType.TOOL_PROPOSAL: {"tool"},
            EventType.POLICY_DECISION: {"decision"}, EventType.FINAL_ANSWER: {"output"},
        }.get(self.type, set())
        missing = required - self.payload.keys()
        if missing:
            raise ValueError(f"{self.type} payload missing: {sorted(missing)}")
        if self.parent_id == self.id:
            raise ValueError("event cannot parent itself")
        return self


class Finding(StrictModel):
    id: str = Field(default_factory=lambda: f"fnd_{uuid4().hex[:12]}")
    execution_id: str
    rule_id: str
    title: str
    severity: str
    explanation: str
    evidence_event_ids: list[str]
    recommended_control: str
    status: str = "open"
    source: str = "deterministic"


class Execution(StrictModel):
    id: str
    policy_mode: PolicyMode
    intent: IntentContract
    events: list[Event] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    fixture_hash: str | None = None
    status: str = "complete"
    replay_of: str | None = None


class Comparison(StrictModel):
    left_id: str
    right_id: str
    fixture_hash: str
    changed_decisions: list[dict[str, str]]
    blocked_tools: list[str]
    resolved_rules: list[str]
    outcome: str
