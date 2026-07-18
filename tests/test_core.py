from causalgate.demo import FIXTURE_HASH, compare, run_demo


def test_vulnerable_scenario_finds_all_rules():
    run = run_demo("baseline")
    assert run.fixture_hash == FIXTURE_HASH
    assert {f.rule_id for f in run.findings} == {
        "CG-EGRESS-001", "CG-APPROVAL-001", "CG-CHAIN-001", "CG-SOURCE-001",
        "CG-GOAL-001", "CG-PRIV-001", "CG-STATE-001", "CG-COMPLETE-001",
    }
    assert all(set(f.evidence_event_ids) <= {e.id for e in run.events} for f in run.findings)


def test_protected_replay_is_clean_and_comparable():
    base, protected = run_demo("baseline"), run_demo("protected")
    assert protected.findings == []
    result = compare(base, protected)
    assert result.fixture_hash == FIXTURE_HASH
    assert len(result.resolved_rules) == 8
    assert "read_secret" in result.blocked_tools


def test_replay_semantics_are_deterministic():
    first, second = run_demo("baseline"), run_demo("baseline")
    assert [e.type for e in first.events] == [e.type for e in second.events]
    assert [f.rule_id for f in first.findings] == [f.rule_id for f in second.findings]

