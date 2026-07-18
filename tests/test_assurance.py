from __future__ import annotations

from datetime import datetime, timezone

from agentflight.assurance import (
    attest_provenance,
    evaluate_promotion_suite,
    synthetic_promotion_pairs,
    verify_provenance,
    wilson_interval,
)
from agentflight.demo import run_demo
from agentflight.flight_record import analyze_flight_record, intent_clause_id
from agentflight.models import Event, EventType, IntentClauseKind


KEY = "test-only-assurance-key-with-at-least-32-bytes"


def test_clause_ids_use_canonical_full_sha256_identity():
    plain = intent_clause_id(IntentClauseKind.GOAL, "Review public vendor data")
    whitespace = intent_clause_id(IntentClauseKind.GOAL, "  Review   public vendor data  ")
    assert plain == whitespace
    assert len(plain.rsplit("_", 1)[-1]) == 64


def test_coverage_separates_declaration_verification_and_action_binding():
    record = analyze_flight_record(run_demo("protected"))
    assert record.coverage.declaration_coverage_ratio <= record.coverage.coverage_ratio
    assert record.coverage.verified_coverage_ratio <= record.coverage.coverage_ratio
    assert record.coverage.consequential_action_coverage_ratio == 1
    assert record.coverage.bound_consequential_actions == record.coverage.consequential_actions
    assert record.evaluations
    assert all(evaluation.verifier_version == "2.0.0" for evaluation in record.evaluations)


def test_divergence_frontier_preserves_incomparable_minimal_violations():
    run = run_demo("protected").model_copy(deep=True)
    for sequence in (len(run.events) + 1, len(run.events) + 2):
        run.events.append(Event(
            execution_id=run.id,
            sequence=sequence,
            type=EventType.FINAL_ANSWER,
            actor=f"parallel-worker-{sequence}",
            emitter_id=f"parallel-worker-{sequence}",
            logical_clock=1,
            payload={"output": "unsupported", "evidence": []},
        ))
    record = analyze_flight_record(run)
    assert len(record.divergence_frontier) == 2
    assert {item.sequence for item in record.divergence_frontier} == {8, 9}
    assert record.first_divergence == record.divergence_frontier[0]
    assert all(item.order_basis == "causal_partial_order" for item in record.divergence_frontier)


def test_event_id_renaming_is_metamorphically_invariant():
    original = run_demo("baseline")
    renamed = original.model_copy(deep=True)
    mapping = {event.id: f"renamed-{index}" for index, event in enumerate(renamed.events, 1)}
    for event in renamed.events:
        old_id = event.id
        event.id = mapping[old_id]
        event.parent_id = mapping.get(event.parent_id, event.parent_id)
        event.causal_predecessor_ids = [mapping[item] for item in event.causal_predecessor_ids]
        if isinstance(event.payload.get("evidence_event_ids"), list):
            event.payload["evidence_event_ids"] = [mapping[item] for item in event.payload["evidence_event_ids"]]
    before = analyze_flight_record(original)
    after = analyze_flight_record(renamed)
    assert [(binding.clause_id, binding.status) for binding in before.bindings] == [
        (binding.clause_id, binding.status) for binding in after.bindings
    ]
    assert [item.sequence for item in before.divergence_frontier] == [
        item.sequence for item in after.divergence_frontier
    ]


def test_wilson_interval_reports_uncertainty_instead_of_only_perfect_point_score():
    interval = wilson_interval(16, 16)
    assert interval.estimate == 1
    assert 0.79 < interval.lower < 0.82
    assert interval.upper == 1


def test_authenticated_multi_fixture_gate_detects_tampering_and_underpowered_suite():
    pairs = synthetic_promotion_pairs(12)
    fixtures = [baseline.fixture_hash or "" for baseline, _ in pairs]
    provenance = attest_provenance(
        fixtures,
        KEY,
        source_revision="test-revision",
        runner_identity="test-runner",
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert verify_provenance(provenance, KEY)
    result = evaluate_promotion_suite(pairs, provenance, KEY)
    assert result.eligible
    assert result.scope == "configured_multi_fixture_suite"
    assert result.production_safety_certification is False
    assert result.scenario_families == 4 and result.channels == 3
    assert result.pass_interval.lower >= 0.70

    tampered = provenance.model_copy(update={"source_revision": "forged"})
    rejected = evaluate_promotion_suite(pairs, tampered, KEY)
    assert not rejected.eligible
    assert "authenticated_provenance" in rejected.regressions

    small_pairs = pairs[:2]
    small_provenance = attest_provenance(
        [baseline.fixture_hash or "" for baseline, _ in small_pairs],
        KEY,
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    underpowered = evaluate_promotion_suite(small_pairs, small_provenance, KEY)
    assert not underpowered.eligible
    assert "minimum_fixture_diversity" in underpowered.regressions
    assert "suite_pass_lower_bound" in underpowered.regressions
