from causalgate.benchmark import RULES, evaluate_cases, run_benchmark
from causalgate.models import IntentContract
from causalgate.policy import evaluate


def test_policy_precedence():
    contract = IntentContract(goal="research", allowed_tools=["send"], protected_resources=["secret"], approval_required=["send"])
    assert evaluate("send", {"outcome": "disclose protected data", "resource": "secret"}, contract).rule == "prohibited_outcome"
    assert evaluate("send", {"resource": "secret"}, contract).rule == "resource_boundary"
    assert evaluate("unknown", {}, contract).rule == "tool_authorization"
    assert evaluate("send", {}, contract).rule == "approval_gate"


def test_benchmark_executes_distinct_labeled_fixtures():
    cases = evaluate_cases()
    assert len(cases) == 32
    assert len({case.id for case in cases}) == 32
    assert len({case.fixture_hash for case in cases}) == 32
    for rule in RULES:
        target = [case for case in cases if case.rule_id == rule]
        assert len(target) == 4
        assert all(case.observed == case.label for case in target)
    result = run_benchmark()
    assert result.true_positives == 16 and result.false_positives == 0 and result.false_negatives == 0
    assert result.true_negatives == 16 and result.specificity == 1
    assert result.deterministic is True
    assert result.evidence_scope == "synthetic_regression_evidence_not_production_validation"
    assert result.confidence_intervals["recall"]["lower"] < result.recall
    assert len(result.per_rule) == len(RULES)
    assert all(item["sensitivity_interval"]["trials"] == 2 for item in result.per_rule)
