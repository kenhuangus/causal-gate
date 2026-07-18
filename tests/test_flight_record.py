import pytest
from pydantic import ValidationError

from agentflight.demo import compare, run_demo
from agentflight.flight_record import analyze_flight_record, intent_clauses
from agentflight.models import BindingStatus, Event, EventType, IntentClauseKind


def test_plan_and_decision_events_require_bounded_explicit_summaries():
    common = {"execution_id": "run_contract", "sequence": 1, "actor": "agent"}
    plan = Event(
        **common,
        type=EventType.PLAN,
        payload={
            "summary": "Use only the authorized lookup tool.",
            "subgoal_id": "lookup.public",
            "intent_clause_ids": ["intent_goal_123"],
            "evidence_event_ids": [],
            "alignment": "aligned",
            "proposed_tools": ["lookup"],
        },
    )
    assert plan.type == EventType.PLAN
    with pytest.raises(ValidationError, match="unsupported decision payload fields"):
        Event(
            **common,
            type=EventType.DECISION,
            payload={
                "summary": "Proceed with the authorized action.",
                "intent_clause_ids": ["intent_goal_123"],
                "evidence_event_ids": [],
                "alignment": "aligned",
                "decision": "allow",
                "outcome": "proceed",
                "alternatives_considered": ["stop"],
                "confidence": 0.9,
                "reasoning": "private scratchpad",
            },
        )
    with pytest.raises(ValidationError, match="unique strings"):
        Event(
            **common,
            type=EventType.PLAN,
            payload={
                "summary": "Duplicate bindings are invalid.",
                "subgoal_id": "lookup.public",
                "intent_clause_ids": ["same", "same"],
                "evidence_event_ids": [],
                "alignment": "aligned",
                "proposed_tools": [],
            },
        )


def test_demo_flight_records_are_deterministic_and_keep_event_count():
    baseline, protected = run_demo("baseline"), run_demo("protected")
    assert len(baseline.events) == 13
    assert [event.type for event in baseline.events].count(EventType.PLAN) == 1
    assert [event.type for event in baseline.events].count(EventType.DECISION) == 1
    assert all(
        "reasoning" not in event.payload and "chain_of_thought" not in event.payload
        for event in baseline.events
    )

    baseline_record = analyze_flight_record(baseline)
    protected_record = analyze_flight_record(protected)
    assert baseline_record.first_divergence is not None
    assert baseline_record.first_divergence.sequence == 5
    assert baseline_record.first_divergence.event_id == baseline_record.plan_event_ids[0]
    assert protected_record.first_divergence is None
    assert baseline_record.coverage.coverage_ratio == protected_record.coverage.coverage_ratio
    assert baseline_record.coverage.bound_clauses > 0
    assert baseline_record.first_divergence_event_id == baseline_record.plan_event_ids[0]
    assert baseline_record.first_divergence_reason
    assert baseline_record.intent_coverage == baseline_record.coverage.coverage_ratio
    application_decision = next(item for item in baseline_record.decision_records if item.confidence == 0.91)
    assert application_decision.summary
    assert application_decision.bound_clause_ids
    assert application_decision.evidence_event_ids
    assert application_decision.alternatives_considered
    assert baseline_record.causal_chain_event_ids
    assert baseline_record.unbound_consequential_actions == []
    protected_goal = next(clause for clause in protected_record.clauses if clause.kind == IntentClauseKind.GOAL)
    protected_goal_binding = next(binding for binding in protected_record.bindings if binding.clause_id == protected_goal.id)
    protected_events = {event.id: event for event in protected.events}
    assert protected_goal_binding.status == BindingStatus.SATISFIED
    assert any(protected_events[event_id].type != EventType.USER_INTENT for event_id in protected_goal_binding.event_ids)

    repeated = analyze_flight_record(run_demo("baseline"))
    assert [clause.id for clause in baseline_record.clauses] == [clause.id for clause in repeated.clauses]
    assert [binding.status for binding in baseline_record.bindings] == [binding.status for binding in repeated.bindings]
    assert [clause.id for clause in intent_clauses(baseline.intent)] == [
        clause.id for clause in baseline_record.clauses
    ]
    unrelated = baseline.model_copy(deep=True)
    unrelated_event = Event(
        execution_id=unrelated.id,
        sequence=len(unrelated.events) + 1,
        type=EventType.STATE_MUTATION,
        actor="maintenance",
        payload={"field": "display_preference", "value": "compact"},
    )
    unrelated.events.append(unrelated_event)
    assert unrelated_event.id not in analyze_flight_record(unrelated).causal_chain_event_ids


def test_comparison_promotion_gate_requires_aligned_non_regressing_replay():
    baseline, protected = run_demo("baseline"), run_demo("protected")
    result = compare(baseline, protected)
    assert result.promotion_gate.eligible
    assert result.promotion_gate.verdict == "promote"
    assert result.promotion_gate.restored_clause_ids
    assert result.promotion_gate.regressions == []
    assert all(check.passed for check in result.promotion_gate.checks)

    regressed = protected.model_copy(deep=True)
    decision = next(event for event in regressed.events if event.type == EventType.DECISION)
    decision.payload["alignment"] = "diverged"
    decision.payload["outcome"] = "proceed"
    rejected = compare(baseline, regressed)
    assert not rejected.promotion_gate.eligible
    assert rejected.promotion_gate.verdict == "hold"
    assert "candidate_alignment" in rejected.promotion_gate.regressions
    assert not next(
        check for check in rejected.promotion_gate.checks if check.name == "candidate_alignment"
    ).passed


def test_promotion_requires_all_clause_restoration_no_unbound_actions_and_exact_replay_link():
    baseline, protected = run_demo("baseline"), run_demo("protected")
    partial = protected.model_copy(deep=True)
    prevented = next(
        event for event in partial.events
        if event.type == EventType.TOOL_PROPOSAL and event.payload.get("tool") == "send_message"
    )
    prevented.type = EventType.TOOL_RESULT
    partial_result = compare(baseline, partial)
    assert partial_result.promotion_gate.verdict == "hold"
    assert "all_divergent_clauses_restored" in partial_result.promotion_gate.regressions

    unbound = protected.model_copy(deep=True)
    unbound.events.append(Event(
        execution_id=unbound.id,
        sequence=len(unbound.events) + 1,
        type=EventType.STATE_MUTATION,
        actor="agent",
        payload={"field": "uncontracted_release_flag", "value": True},
    ))
    unbound_result = compare(baseline, unbound)
    assert unbound_result.promotion_gate.verdict == "hold"
    assert "no_unbound_consequential_actions" in unbound_result.promotion_gate.regressions

    unlinked = protected.model_copy(deep=True)
    unlinked.replay_of = "fixture:unverified"
    unlinked_result = compare(baseline, unlinked)
    assert unlinked_result.promotion_gate.verdict == "hold"
    assert "protected_replay" in unlinked_result.promotion_gate.regressions
