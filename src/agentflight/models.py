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
    PLAN = "plan"
    DECISION = "decision"
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
            EventType.PLAN: {"summary", "subgoal_id", "intent_clause_ids", "evidence_event_ids", "alignment", "proposed_tools"},
            EventType.DECISION: {"summary", "intent_clause_ids", "evidence_event_ids", "alignment", "decision", "outcome", "alternatives_considered", "confidence"},
            EventType.POLICY_DECISION: {"decision"}, EventType.FINAL_ANSWER: {"output"},
        }.get(self.type, set())
        missing = required - self.payload.keys()
        if missing:
            raise ValueError(f"{self.type} payload missing: {sorted(missing)}")
        if self.type in {EventType.PLAN, EventType.DECISION}:
            allowed_keys = (
                {"summary", "subgoal_id", "intent_clause_ids", "evidence_event_ids", "alignment", "proposed_tools", "field", "value", "blocked"}
                if self.type == EventType.PLAN
                else {"summary", "intent_clause_ids", "evidence_event_ids", "alignment", "decision", "outcome", "alternatives_considered", "confidence", "reason", "rule"}
            )
            unsupported = self.payload.keys() - allowed_keys
            if unsupported:
                raise ValueError(f"unsupported {self.type.value} payload fields: {sorted(unsupported)}")
            summary = self.payload.get("summary")
            clause_ids = self.payload.get("intent_clause_ids")
            alignment = self.payload.get("alignment")
            if not isinstance(summary, str) or not summary.strip() or len(summary) > 500:
                raise ValueError("plan and decision summaries must be 1-500 characters")
            if (
                not isinstance(clause_ids, list)
                or not clause_ids
                or any(not isinstance(item, str) or not item for item in clause_ids)
                or len(set(clause_ids)) != len(clause_ids)
            ):
                raise ValueError("intent_clause_ids must be a non-empty list of unique strings")
            if alignment not in {"aligned", "diverged"}:
                raise ValueError("alignment must be aligned or diverged")
            evidence_ids = self.payload.get("evidence_event_ids")
            if (
                not isinstance(evidence_ids, list)
                or any(not isinstance(item, str) or not item for item in evidence_ids)
                or len(set(evidence_ids)) != len(evidence_ids)
            ):
                raise ValueError("evidence_event_ids must be a list of unique strings")
        if self.type == EventType.PLAN:
            proposed_tools = self.payload.get("proposed_tools")
            if not isinstance(proposed_tools, list) or any(not isinstance(item, str) for item in proposed_tools):
                raise ValueError("proposed_tools must be a list of strings")
        if self.type == EventType.DECISION:
            if self.payload.get("outcome") not in {"proceed", "block", "revise"}:
                raise ValueError("decision outcome must be proceed, block, or revise")
            alternatives = self.payload.get("alternatives_considered")
            confidence = self.payload.get("confidence")
            if not isinstance(alternatives, list) or any(not isinstance(item, str) or not item for item in alternatives):
                raise ValueError("alternatives_considered must be a list of strings")
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                raise ValueError("decision confidence must be between 0 and 1")
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


class IntentClauseKind(StrEnum):
    GOAL = "goal"
    TOOL_AUTHORIZATION = "tool_authorization"
    PROHIBITED_OUTCOME = "prohibited_outcome"
    RESOURCE_BOUNDARY = "resource_boundary"
    APPROVAL_GATE = "approval_gate"
    COMPLETION_CONDITION = "completion_condition"


class BindingStatus(StrEnum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    OBSERVED = "observed"


class IntentClause(StrictModel):
    id: str
    kind: IntentClauseKind
    subject: str
    statement: str


class IntentBinding(StrictModel):
    clause_id: str
    status: BindingStatus
    event_ids: list[str]
    summaries: list[str]


class FirstDivergence(StrictModel):
    event_id: str
    sequence: int
    clause_ids: list[str]
    summary: str
    causal_event_ids: list[str]


class IntentCoverage(StrictModel):
    total_clauses: int
    bound_clauses: int
    satisfied_clauses: int
    violated_clauses: int
    coverage_ratio: float = Field(ge=0, le=1)
    unbound_clause_ids: list[str]


class DecisionRecord(StrictModel):
    event_id: str
    sequence: int
    action: str
    decision: str
    outcome: str | None = None
    summary: str
    clause_ids: list[str]
    bound_clause_ids: list[str]
    evidence_event_ids: list[str]
    alternatives_considered: list[str]
    confidence: float = Field(ge=0, le=1)


class ConsequentialAction(StrictModel):
    event_id: str
    action: str
    reason: str


class FlightRecord(StrictModel):
    execution_id: str
    intent_version: int
    clauses: list[IntentClause]
    bindings: list[IntentBinding]
    first_divergence: FirstDivergence | None
    coverage: IntentCoverage
    plan_event_ids: list[str]
    decision_event_ids: list[str]
    causal_chain_event_ids: list[str]
    decision_records: list[DecisionRecord]
    first_divergence_event_id: str | None
    first_divergence_reason: str | None
    intent_coverage: float = Field(ge=0, le=1)
    unbound_consequential_actions: list[ConsequentialAction]


class PromotionCheck(StrictModel):
    name: str
    passed: bool
    summary: str


class PromotionGate(StrictModel):
    eligible: bool
    checks: list[PromotionCheck]
    verdict: str
    reason: str
    restored_clause_ids: list[str]
    regressions: list[str]


class Comparison(StrictModel):
    left_id: str
    right_id: str
    fixture_hash: str
    changed_decisions: list[dict[str, str]]
    blocked_tools: list[str]
    resolved_rules: list[str]
    outcome: str
    promotion_gate: PromotionGate
