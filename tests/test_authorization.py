from __future__ import annotations

import pytest

from causalgate.authorization import (
    AuthorizationOntology,
    IntentAuthorizer,
    authorization_record,
    build_request,
    issue_approval,
    issue_grant,
    verify_grant,
)
from causalgate.demo import DEMO_GRANT_KEY, run_demo
from causalgate.models import IntentContract


KEY = "test-intent-grant-signing-key-with-32-bytes"


def contract(**updates):
    values = {
        "goal": "Research a public vendor.",
        "purpose_id": "purpose.vendor.public_research",
        "subject_id": "agent:research",
        "on_behalf_of": "user:owner",
        "allowed_tools": ["retrieve", "summarize"],
        "allowed_resource_types": ["resource.public"],
        "allowed_data_classes": ["data.public"],
        "allowed_destinations": ["destination.local"],
        "prohibited_effects": ["effect.external_disclosure"],
        "max_tool_calls": 3,
        "max_delegation_depth": 1,
    }
    values.update(updates)
    return IntentContract(**values)


def authorizer(value: IntentContract, execution_id: str = "run_auth"):
    grant = issue_grant(value, execution_id, KEY)
    return IntentAuthorizer(value, execution_id, grant, KEY), grant


def request(value: IntentContract, tool: str, arguments=None, **updates):
    return build_request(
        execution_id=updates.pop("execution_id", "run_auth"),
        contract=value,
        tool=tool,
        arguments=arguments or {},
        **updates,
    )


def test_ontology_is_closed_versioned_and_covers_shipped_effectful_tools():
    ontology = AuthorizationOntology.load_default()
    assert ontology.version == "causalgate-ontology/1.0"
    assert ontology.digest.startswith("sha256:")
    assert {"retrieve", "read_public", "summarize", "read_secret", "send_message", "write_memory", "delegate_agent"} <= ontology.tools.keys()
    for tool in ontology.tools.values():
        assert tool.action in ontology.actions
        assert tool.resource_type in ontology.resource_types
        assert tool.data_class in ontology.data_classes
        assert tool.destination in ontology.destinations
        assert set(tool.effects) <= set(ontology.effects)


def test_public_read_is_allowed_and_execution_permit_is_single_use():
    value = contract()
    engine, grant = authorizer(value)
    proposed = request(value, "retrieve", {"resource": "public.vendor"})
    decision = engine.authorize(proposed)
    assert decision.outcome == "allow"
    assert decision.permit is not None
    assert engine.execute(decision, lambda: "public result") == "public result"
    with pytest.raises(PermissionError, match="permit.invalid_or_replayed"):
        engine.execute(decision, lambda: "replayed")
    assert verify_grant(grant, value, KEY, "run_auth")


def test_unknown_tool_and_grant_tampering_fail_closed():
    value = contract()
    with pytest.raises(KeyError, match="no ontology mapping"):
        request(value, "invented_super_tool")
    engine, grant = authorizer(value)
    tampered = grant.model_copy(update={"destinations": ["destination.external"]})
    engine.grant = tampered
    decision = engine.authorize(request(value, "retrieve"))
    assert decision.outcome == "deny"
    assert decision.reason_code == "grant.invalid"
    clean_engine, _ = authorizer(value)
    mismapped = request(value, "retrieve").model_copy(update={"action": "action.write"})
    assert clean_engine.authorize(mismapped).reason_code == "ontology.mapping_mismatch"
    with pytest.raises(ValueError, match="unknown destination"):
        issue_grant(contract(allowed_destinations=["destination.mars"]), "run_auth", KEY)
    denied_contract = contract(approval_required=["send_message"])
    denied_engine, denied_grant = authorizer(denied_contract)
    denied_request = request(denied_contract, "send_message", {"destination": "external"})
    approval = issue_approval(denied_request, denied_grant, "user:owner", KEY)
    assert denied_engine.authorize(denied_request.model_copy(update={"approvals": [approval]})).reason_code == "intent.tool"


def test_permit_is_bound_to_the_exact_request_and_rejects_toctou_mutation():
    value = contract()
    engine, grant = authorizer(value)
    proposed = request(value, "retrieve", {"resource": "public.vendor"})
    decision = engine.authorize(proposed)
    changed = proposed.model_copy(update={"arguments_digest": "sha256:" + "0" * 64})
    decision.request = changed
    with pytest.raises(PermissionError, match="permit.invalid_or_replayed"):
        engine.execute(decision, lambda: "must not run")


def test_sensitive_external_flow_and_untrusted_control_are_denied():
    value = contract(
        allowed_tools=["send_message"],
        allowed_resource_types=["resource.public", "resource.protected"],
        allowed_data_classes=["data.public", "data.protected"],
        allowed_destinations=["destination.external"],
        prohibited_effects=[],
    )
    engine, grant = authorizer(value)
    sensitive = request(
        value, "send_message", {"destination": "external"},
        data_classes=["data.protected"], provenance="application",
    )
    assert engine.authorize(sensitive).reason_code == "data_flow.external"

    public_untrusted = request(
        value, "send_message", {"destination": "external"},
        data_classes=["data.public"], provenance="untrusted:retrieval",
    )
    assert engine.authorize(public_untrusted).reason_code == "provenance.untrusted_control"


def test_step_up_approval_is_required_then_exact_action_is_allowed():
    value = contract(
        allowed_tools=["send_message"],
        allowed_destinations=["destination.external"],
        prohibited_effects=[],
        approval_required=["send_message"],
    )
    engine, grant = authorizer(value)
    proposed = request(value, "send_message", {"destination": "external"}, provenance="user:authorized")
    waiting = engine.authorize(proposed)
    assert waiting.outcome == "require_approval"
    assert "obligation.linked_human_approval" in waiting.obligations
    approval = issue_approval(proposed, grant, "user:owner", KEY)
    approved = proposed.model_copy(update={"approvals": [approval]})
    assert engine.authorize(approved).outcome == "allow"

    changed = request(
        value, "send_message", {"destination": "external", "recipient": "different"},
        provenance="user:authorized", approvals=[approval],
    )
    assert engine.authorize(changed).reason_code == "approval.invalid"
    tampered = approval.model_copy(update={"approver": "attacker"})
    assert engine.authorize(proposed.model_copy(update={"approvals": [tampered]})).reason_code == "approval.invalid"


def test_budget_delegation_and_attenuation_are_monotonic():
    parent_contract = contract(max_tool_calls=3, max_delegation_depth=2)
    parent = issue_grant(parent_contract, "run_auth", KEY, ttl_seconds=600)
    engine = IntentAuthorizer(parent_contract, "run_auth", parent, KEY)
    exhausted = request(parent_contract, "retrieve", tool_call_count=3)
    assert engine.authorize(exhausted).reason_code == "budget.tool_calls"
    too_deep = request(parent_contract, "retrieve", delegation_depth=3)
    assert engine.authorize(too_deep).reason_code == "delegation.depth"

    child_contract = contract(allowed_tools=["retrieve"], max_tool_calls=1, max_delegation_depth=1)
    child = issue_grant(child_contract, "run_auth", KEY, ttl_seconds=60, parent=parent)
    assert set(child.tools) < set(parent.tools)
    expanded = contract(allowed_tools=["retrieve", "summarize", "send_message"], max_delegation_depth=1)
    with pytest.raises(ValueError, match="expands parent authority"):
        issue_grant(expanded, "run_auth", KEY, ttl_seconds=60, parent=parent)


def test_restrictions_never_create_new_permissions():
    base = contract()
    engine, _ = authorizer(base)
    base_outcome = engine.authorize(request(base, "retrieve")).outcome
    assert base_outcome == "allow"
    restrictions = [
        {"allowed_tools": ["summarize"]},
        {"allowed_resource_types": ["resource.state"]},
        {"allowed_data_classes": ["data.internal"]},
        {"allowed_destinations": ["destination.external"]},
        {"max_tool_calls": 0},
    ]
    for index, update in enumerate(restrictions):
        restricted = contract(**update)
        restricted_engine, _ = authorizer(restricted, f"run_{index}")
        try:
            proposed = request(restricted, "retrieve", execution_id=f"run_{index}")
        except KeyError:
            continue
        assert restricted_engine.authorize(proposed).outcome != "allow"


def test_demo_has_complete_mediation_and_observe_vs_enforce_evidence():
    baseline = authorization_record(run_demo("baseline"))
    protected = authorization_record(run_demo("protected"))
    assert baseline.complete_mediation and protected.complete_mediation
    assert baseline.allowed == 1 and baseline.denied == 2
    assert protected.allowed == 1 and protected.denied == 2
    assert any(item.enforcement == "observe_only" and item.outcome == "deny" for item in baseline.decisions)
    assert all(item.enforcement == "enforced" for item in protected.decisions)
    assert baseline.ontology_digest == protected.ontology_digest
