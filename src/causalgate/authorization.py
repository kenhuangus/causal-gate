from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from .models import EventType, Execution, IntentContract, StrictModel


ONTOLOGY_PATH = Path(__file__).with_name("ontology.json")
AUTHORIZER_VERSION = "CG-INTENT-AUTHZ/1.0.0"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical(value: Any) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _digest(value: Any) -> str:
    return f"sha256:{hashlib.sha256(_canonical(value)).hexdigest()}"


class ToolSemantics(StrictModel):
    action: str
    resource_type: str
    data_class: str
    destination: str
    effects: list[str]


class AuthorizationOntology(StrictModel):
    version: str
    actions: dict[str, str | None]
    resource_types: list[str]
    purposes: list[str]
    data_classes: list[str]
    destinations: list[str]
    effects: list[str]
    tools: dict[str, ToolSemantics]

    @classmethod
    def load_default(cls) -> "AuthorizationOntology":
        return cls.model_validate_json(ONTOLOGY_PATH.read_text(encoding="utf-8"))

    @property
    def digest(self) -> str:
        return _digest(self)

    def ancestors(self, action: str) -> set[str]:
        found = {action}
        parent = self.actions.get(action)
        while parent and parent not in found:
            found.add(parent)
            parent = self.actions.get(parent)
        return found

    def normalize(self, tool: str, arguments: dict[str, Any], *, data_classes: list[str] | None = None) -> ToolSemantics:
        if tool not in self.tools:
            raise KeyError(f"tool has no ontology mapping: {tool}")
        semantics = self.tools[tool].model_copy(deep=True)
        if tool == "read_secret" or arguments.get("resource") == "synthetic_canary":
            semantics.resource_type = "resource.protected"
            semantics.data_class = "data.protected"
        if arguments.get("outbound") or arguments.get("recipient") or arguments.get("destination") == "external":
            semantics.destination = "destination.external"
        if data_classes:
            # The most restrictive observed class wins. This closed order is
            # deliberately local to the ontology rather than model-generated.
            rank = {name: index for index, name in enumerate(self.data_classes)}
            semantics.data_class = max(data_classes, key=lambda item: rank.get(item, len(rank)))
        return semantics


class IntentGrant(StrictModel):
    schema_version: str = "causalgate-intent-grant/1.0"
    grant_id: str
    issuer: str
    subject: str
    on_behalf_of: str
    execution_id: str
    purpose_id: str
    tools: list[str]
    actions: list[str]
    resource_types: list[str]
    data_classes: list[str]
    destinations: list[str]
    prohibited_effects: list[str]
    approval_required: list[str]
    max_tool_calls: int = Field(ge=0)
    max_delegation_depth: int = Field(ge=0)
    contract_digest: str
    ontology_version: str
    ontology_digest: str
    policy_version: str = AUTHORIZER_VERSION
    parent_grant_id: str | None = None
    issued_at: datetime
    expires_at: datetime
    nonce: str
    signature: str

    @model_validator(mode="after")
    def bounded(self):
        for name in ("tools", "actions", "resource_types", "data_classes", "destinations", "prohibited_effects", "approval_required"):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must contain unique values")
        if self.expires_at <= self.issued_at:
            raise ValueError("grant expiry must follow issue time")
        return self


class ApprovalArtifact(StrictModel):
    """Short-lived approval bound to one exact normalized request."""

    schema_version: str = "causalgate-linked-approval/1.0"
    approval_id: str
    approver: str
    execution_id: str
    grant_id: str
    tool: str
    arguments_digest: str
    issued_at: datetime
    expires_at: datetime
    nonce: str
    signature: str

    @model_validator(mode="after")
    def bounded(self):
        if self.expires_at <= self.issued_at:
            raise ValueError("approval expiry must follow issue time")
        return self


class AuthorizationRequest(StrictModel):
    request_id: str
    execution_id: str
    principal: str
    on_behalf_of: str
    tool: str
    action: str
    resource_type: str
    resource_id: str | None = None
    data_class: str
    destination: str
    effects: list[str]
    purpose_id: str
    provenance: str
    arguments_digest: str
    intent_clause_ids: list[str] = Field(default_factory=list)
    evidence_event_ids: list[str] = Field(default_factory=list)
    approvals: list[ApprovalArtifact] = Field(default_factory=list)
    tool_call_count: int = Field(default=0, ge=0)
    delegation_depth: int = Field(default=0, ge=0)
    requested_at: datetime = Field(default_factory=_now)


class ExecutionPermit(StrictModel):
    permit_id: str
    request_digest: str
    grant_id: str
    grant_digest: str
    policy_version: str
    issued_at: datetime
    expires_at: datetime
    nonce: str
    signature: str


class AuthorizationDecision(StrictModel):
    decision_id: str
    outcome: Literal["allow", "deny", "require_approval"]
    reason_code: str
    reason: str
    matched_policy_ids: list[str]
    obligations: list[str]
    request: AuthorizationRequest
    grant_id: str | None
    grant_digest: str | None
    ontology_version: str
    ontology_digest: str
    policy_version: str = AUTHORIZER_VERSION
    permit: ExecutionPermit | None = None


class AuthorizationDecisionEvidence(StrictModel):
    event_id: str
    decision_id: str
    outcome: str
    enforcement: str
    reason_code: str
    reason: str
    tool: str
    action: str
    resource_type: str
    data_class: str
    destination: str
    effects: list[str]
    matched_policy_ids: list[str]
    obligations: list[str]
    permit_issued: bool


class AuthorizationRecord(StrictModel):
    execution_id: str
    enforcement_model: str = "identity ∩ agent ∩ intent grant ∩ organization ∩ runtime context"
    ontology_version: str
    ontology_digest: str
    policy_version: str = AUTHORIZER_VERSION
    grant_id: str | None
    grant_digest: str | None
    decisions: list[AuthorizationDecisionEvidence]
    allowed: int
    denied: int
    approval_required: int
    complete_mediation: bool
    limitations: list[str] = Field(default_factory=list)


class PermitLedger:
    """Process-local single-use enforcement for the shipped fixed-tool profile."""

    def __init__(self):
        self._consumed: set[str] = set()
        self._lock = threading.Lock()

    def consume(self, permit: ExecutionPermit, request: AuthorizationRequest, key: str) -> bool:
        with self._lock:
            if permit.nonce in self._consumed or permit.expires_at <= _now():
                return False
            if permit.request_digest != _digest(request) or not verify_permit(permit, key):
                return False
            self._consumed.add(permit.nonce)
            return True


def _signable(model: StrictModel, signature_field: str = "signature") -> dict[str, Any]:
    return model.model_dump(mode="json", exclude={signature_field})


def _signature(fields: dict[str, Any], key: str) -> str:
    return hmac.new(key.encode(), _canonical(fields), hashlib.sha256).hexdigest()


def issue_grant(
    contract: IntentContract,
    execution_id: str,
    key: str,
    *,
    issuer: str | None = None,
    ttl_seconds: int = 900,
    parent: IntentGrant | None = None,
) -> IntentGrant:
    if len(key.encode()) < 32:
        raise ValueError("grant signing key must contain at least 32 bytes")
    ontology = AuthorizationOntology.load_default()
    unknown = sorted(set(contract.allowed_tools) - ontology.tools.keys())
    if unknown:
        raise ValueError(f"intent contains unmapped tools: {', '.join(unknown)}")
    controlled_values = (
        ("purpose", [contract.purpose_id], set(ontology.purposes)),
        ("resource type", contract.allowed_resource_types, set(ontology.resource_types)),
        ("data class", contract.allowed_data_classes, set(ontology.data_classes)),
        ("destination", contract.allowed_destinations, set(ontology.destinations)),
        ("effect", contract.prohibited_effects, set(ontology.effects)),
    )
    for label, values, allowed in controlled_values:
        invalid = sorted(set(values) - allowed)
        if invalid:
            raise ValueError(f"intent contains unknown {label}: {', '.join(invalid)}")
    actions = sorted({ontology.tools[tool].action for tool in contract.allowed_tools})
    fields: dict[str, Any] = {
        "grant_id": f"igr_{secrets.token_hex(8)}",
        "issuer": issuer or contract.on_behalf_of,
        "subject": contract.subject_id,
        "on_behalf_of": contract.on_behalf_of,
        "execution_id": execution_id,
        "purpose_id": contract.purpose_id,
        "tools": sorted(set(contract.allowed_tools)),
        "actions": actions,
        "resource_types": sorted(set(contract.allowed_resource_types)),
        "data_classes": sorted(set(contract.allowed_data_classes)),
        "destinations": sorted(set(contract.allowed_destinations)),
        "prohibited_effects": sorted(set(contract.prohibited_effects)),
        "approval_required": sorted(set(contract.approval_required)),
        "max_tool_calls": contract.max_tool_calls,
        "max_delegation_depth": contract.max_delegation_depth,
        "contract_digest": _digest(contract),
        "ontology_version": ontology.version,
        "ontology_digest": ontology.digest,
        "parent_grant_id": parent.grant_id if parent else None,
        "issued_at": _now(),
        "expires_at": _now() + timedelta(seconds=max(1, min(ttl_seconds, 86_400))),
        "nonce": secrets.token_hex(16),
        "signature": "",
    }
    candidate = IntentGrant(**fields)
    if parent:
        if not hmac.compare_digest(parent.signature, _signature(_signable(parent), key)) or parent.expires_at <= _now():
            raise ValueError("parent grant is invalid or expired")
        _assert_attenuated(candidate, parent)
    return candidate.model_copy(update={"signature": _signature(_signable(candidate), key)})


def verify_grant(grant: IntentGrant, contract: IntentContract, key: str, execution_id: str) -> bool:
    if grant.expires_at <= _now() or grant.execution_id != execution_id:
        return False
    if grant.contract_digest != _digest(contract):
        return False
    ontology = AuthorizationOntology.load_default()
    if grant.ontology_version != ontology.version or grant.ontology_digest != ontology.digest:
        return False
    return hmac.compare_digest(grant.signature, _signature(_signable(grant), key))


def _assert_attenuated(child: IntentGrant, parent: IntentGrant) -> None:
    sets = ("tools", "actions", "resource_types", "data_classes", "destinations")
    if any(not set(getattr(child, name)) <= set(getattr(parent, name)) for name in sets):
        raise ValueError("delegated grant expands parent authority")
    if child.max_tool_calls > parent.max_tool_calls or child.max_delegation_depth >= parent.max_delegation_depth:
        raise ValueError("delegated grant does not attenuate limits")
    if child.expires_at > parent.expires_at:
        raise ValueError("delegated grant outlives parent")
    if (
        child.execution_id != parent.execution_id
        or child.subject != parent.subject
        or child.on_behalf_of != parent.on_behalf_of
        or child.purpose_id != parent.purpose_id
    ):
        raise ValueError("delegated grant changes its identity, execution, or purpose binding")
    if not set(child.prohibited_effects) >= set(parent.prohibited_effects):
        raise ValueError("delegated grant removes a parent prohibition")
    required_for_child = set(parent.approval_required) & set(child.tools)
    if not required_for_child <= set(child.approval_required):
        raise ValueError("delegated grant removes a required approval")


def build_request(
    *,
    execution_id: str,
    contract: IntentContract,
    tool: str,
    arguments: dict[str, Any],
    provenance: str = "application",
    data_classes: list[str] | None = None,
    approvals: list[ApprovalArtifact] | None = None,
    tool_call_count: int = 0,
    delegation_depth: int = 0,
    intent_clause_ids: list[str] | None = None,
    evidence_event_ids: list[str] | None = None,
) -> AuthorizationRequest:
    ontology = AuthorizationOntology.load_default()
    semantics = ontology.normalize(tool, arguments, data_classes=data_classes)
    return AuthorizationRequest(
        request_id=f"arq_{secrets.token_hex(8)}",
        execution_id=execution_id,
        principal=contract.subject_id,
        on_behalf_of=contract.on_behalf_of,
        tool=tool,
        action=semantics.action,
        resource_type=semantics.resource_type,
        resource_id=str(arguments.get("resource")) if arguments.get("resource") else None,
        data_class=semantics.data_class,
        destination=semantics.destination,
        effects=semantics.effects,
        purpose_id=contract.purpose_id,
        provenance=provenance,
        arguments_digest=_digest(arguments),
        intent_clause_ids=intent_clause_ids or [],
        evidence_event_ids=evidence_event_ids or [],
        approvals=approvals or [],
        tool_call_count=tool_call_count,
        delegation_depth=delegation_depth,
    )


def _permit(request: AuthorizationRequest, grant: IntentGrant, key: str) -> ExecutionPermit:
    fields: dict[str, Any] = {
        "permit_id": f"prm_{secrets.token_hex(8)}",
        "request_digest": _digest(request),
        "grant_id": grant.grant_id,
        "grant_digest": _digest(grant),
        "policy_version": AUTHORIZER_VERSION,
        "issued_at": _now(),
        "expires_at": _now() + timedelta(seconds=30),
        "nonce": secrets.token_hex(16),
        "signature": "",
    }
    candidate = ExecutionPermit(**fields)
    return candidate.model_copy(update={"signature": _signature(_signable(candidate), key)})


def verify_permit(permit: ExecutionPermit, key: str) -> bool:
    return hmac.compare_digest(permit.signature, _signature(_signable(permit), key))


def issue_approval(
    request: AuthorizationRequest,
    grant: IntentGrant,
    approver: str,
    key: str,
    *,
    ttl_seconds: int = 300,
) -> ApprovalArtifact:
    """Issue consent for the exact execution, grant, tool, and arguments digest."""
    if len(key.encode()) < 32:
        raise ValueError("approval signing key must contain at least 32 bytes")
    now = _now()
    fields: dict[str, Any] = {
        "approval_id": f"apr_{secrets.token_hex(8)}",
        "approver": approver,
        "execution_id": request.execution_id,
        "grant_id": grant.grant_id,
        "tool": request.tool,
        "arguments_digest": request.arguments_digest,
        "issued_at": now,
        "expires_at": now + timedelta(seconds=max(1, min(ttl_seconds, 3_600))),
        "nonce": secrets.token_hex(16),
        "signature": "",
    }
    candidate = ApprovalArtifact(**fields)
    return candidate.model_copy(update={"signature": _signature(_signable(candidate), key)})


def verify_approval(
    approval: ApprovalArtifact,
    request: AuthorizationRequest,
    grant: IntentGrant,
    key: str,
) -> bool:
    return (
        approval.expires_at > _now()
        and approval.execution_id == request.execution_id
        and approval.grant_id == grant.grant_id
        and approval.tool == request.tool
        and approval.arguments_digest == request.arguments_digest
        and hmac.compare_digest(approval.signature, _signature(_signable(approval), key))
    )


class IntentAuthorizer:
    def __init__(self, contract: IntentContract, execution_id: str, grant: IntentGrant, key: str):
        self.contract = contract
        self.execution_id = execution_id
        self.grant = grant
        self.key = key
        self.ontology = AuthorizationOntology.load_default()
        self.ledger = PermitLedger()

    def authorize(self, request: AuthorizationRequest) -> AuthorizationDecision:
        matched = ["policy.default_deny"]
        obligations: list[str] = []

        def result(outcome: Literal["allow", "deny", "require_approval"], code: str, reason: str) -> AuthorizationDecision:
            permit = _permit(request, self.grant, self.key) if outcome == "allow" else None
            return AuthorizationDecision(
                decision_id=f"azd_{secrets.token_hex(8)}",
                outcome=outcome,
                reason_code=code,
                reason=reason,
                matched_policy_ids=matched,
                obligations=obligations,
                request=request,
                grant_id=self.grant.grant_id,
                grant_digest=_digest(self.grant),
                ontology_version=self.ontology.version,
                ontology_digest=self.ontology.digest,
                permit=permit,
            )

        if request.execution_id != self.execution_id or not verify_grant(self.grant, self.contract, self.key, self.execution_id):
            return result("deny", "grant.invalid", "The signed intent grant is invalid, stale, or bound to another execution.")
        matched.append("policy.grant_integrity")
        if request.principal != self.grant.subject or request.on_behalf_of != self.grant.on_behalf_of:
            return result("deny", "identity.mismatch", "The caller is outside the grant's principal relationship.")
        matched.append("policy.identity_intersection")
        if request.purpose_id != self.grant.purpose_id:
            return result("deny", "purpose.mismatch", "The requested purpose is not the signed purpose.")
        mapped = self.ontology.tools.get(request.tool)
        if mapped is None or request.action != mapped.action or set(request.effects) != set(mapped.effects):
            return result("deny", "ontology.mapping_mismatch", "The request does not match the tool's versioned ontology semantics.")
        if request.tool not in self.grant.tools or request.action not in self.grant.actions:
            return result("deny", "intent.tool", "The tool or normalized action is outside the intent grant.")
        if request.resource_type not in self.grant.resource_types:
            return result("deny", "intent.resource", "The normalized resource type is outside the intent grant.")
        if request.data_class not in self.grant.data_classes:
            return result("deny", "intent.data_class", "The observed data class is outside the intent grant.")
        if request.destination not in self.grant.destinations:
            return result("deny", "intent.destination", "The destination is outside the intent grant.")
        if set(request.effects) & set(self.grant.prohibited_effects):
            matched.append("policy.organization_guardrail")
            return result("deny", "organization.prohibited_effect", "An organizational guardrail prohibits the requested effect.")
        if request.data_class in {"data.protected", "data.credential", "data.regulated"} and request.destination == "destination.external":
            matched.append("policy.data_flow")
            return result("deny", "data_flow.external", "Sensitive data cannot flow to an external destination.")
        if request.provenance.startswith("untrusted") and any(effect in {"effect.external_disclosure", "effect.privilege_change"} for effect in request.effects):
            matched.append("policy.provenance")
            return result("deny", "provenance.untrusted_control", "Untrusted content cannot authorize an external or privilege-changing effect.")
        if request.tool_call_count >= self.grant.max_tool_calls:
            return result("deny", "budget.tool_calls", "The signed tool-call budget is exhausted.")
        if request.delegation_depth > self.grant.max_delegation_depth:
            return result("deny", "delegation.depth", "Delegation exceeds the signed maximum depth.")
        if request.tool in self.grant.approval_required:
            if not request.approvals:
                obligations.append("obligation.linked_human_approval")
                return result("require_approval", "approval.required", "A linked approval is required before this action can execute.")
            if not any(verify_approval(approval, request, self.grant, self.key) for approval in request.approvals):
                obligations.append("obligation.valid_linked_human_approval")
                return result("deny", "approval.invalid", "No valid approval is bound to this exact action and argument set.")
            matched.append("policy.linked_approval")
        matched.extend(["policy.intent_intersection", "policy.runtime_context"])
        obligations.extend(["obligation.record_decision", "obligation.consume_single_use_permit"])
        return result("allow", "allow.intersection", "Identity, intent, organization, and runtime constraints all permit this action.")

    def execute(self, decision: AuthorizationDecision, fn, *args, **kwargs):
        if decision.outcome != "allow" or decision.permit is None:
            raise PermissionError(decision.reason_code)
        if not self.ledger.consume(decision.permit, decision.request, self.key):
            raise PermissionError("permit.invalid_or_replayed")
        return fn(*args, **kwargs)


def decision_event_payload(decision: AuthorizationDecision, *, observe_only: bool = False) -> dict[str, Any]:
    safe_request = decision.request.model_dump(mode="json", exclude={"approvals"})
    safe_request["approval_ids"] = [approval.approval_id for approval in decision.request.approvals]
    return {
        "decision": decision.outcome,
        "enforcement": "observe_only" if observe_only else "enforced",
        "reason": decision.reason,
        "reason_code": decision.reason_code,
        "authorization_decision_id": decision.decision_id,
        "intent_grant_id": decision.grant_id,
        "grant_digest": decision.grant_digest,
        "ontology_version": decision.ontology_version,
        "ontology_digest": decision.ontology_digest,
        "policy_version": decision.policy_version,
        "matched_policy_ids": decision.matched_policy_ids,
        "obligations": decision.obligations,
        "permit_issued": decision.permit is not None,
        "permit_id": decision.permit.permit_id if decision.permit else None,
        "request": safe_request,
    }


def authorization_record(run: Execution) -> AuthorizationRecord:
    policy_events = [event for event in run.events if event.type == EventType.POLICY_DECISION]
    evidence: list[AuthorizationDecisionEvidence] = []
    for event in policy_events:
        request = event.payload.get("request", {})
        request = request if isinstance(request, dict) else {}
        evidence.append(AuthorizationDecisionEvidence(
            event_id=event.id,
            decision_id=str(event.payload.get("authorization_decision_id", "")),
            outcome=str(event.payload.get("decision", "deny")),
            enforcement=str(event.payload.get("enforcement", "enforced")),
            reason_code=str(event.payload.get("reason_code", "unknown")),
            reason=str(event.payload.get("reason", "Authorization decision recorded.")),
            tool=str(request.get("tool", "unknown")),
            action=str(request.get("action", "unknown")),
            resource_type=str(request.get("resource_type", "unknown")),
            data_class=str(request.get("data_class", "unknown")),
            destination=str(request.get("destination", "unknown")),
            effects=[str(item) for item in request.get("effects", [])] if isinstance(request.get("effects", []), list) else [],
            matched_policy_ids=[str(item) for item in event.payload.get("matched_policy_ids", [])],
            obligations=[str(item) for item in event.payload.get("obligations", [])],
            permit_issued=event.payload.get("permit_issued") is True,
        ))
    proposal_ids = {event.id for event in run.events if event.type == EventType.TOOL_PROPOSAL}
    mediated_ids = {event.parent_id for event in policy_events if event.parent_id}
    ontology = AuthorizationOntology.load_default()
    first = policy_events[0].payload if policy_events else {}
    return AuthorizationRecord(
        execution_id=run.id,
        ontology_version=str(first.get("ontology_version") or ontology.version),
        ontology_digest=str(first.get("ontology_digest") or ontology.digest),
        grant_id=str(first.get("intent_grant_id")) if first.get("intent_grant_id") else None,
        grant_digest=str(first.get("grant_digest")) if first.get("grant_digest") else None,
        decisions=evidence,
        allowed=sum(item.outcome == "allow" for item in evidence),
        denied=sum(item.outcome == "deny" for item in evidence),
        approval_required=sum(item.outcome == "require_approval" for item in evidence),
        complete_mediation=proposal_ids <= mediated_ids,
        limitations=[
            "Complete mediation applies to the fixed, ontology-mapped tool adapters shipped in this profile.",
            "The trusted host supplies principal bindings; the synthetic judge profile does not implement enterprise OIDC or workload identity.",
            "The single-use permit ledger is process-local and requires an atomic shared store when scaled beyond one instance.",
            "Natural-language intent and model output cannot directly grant authority.",
        ],
    )
