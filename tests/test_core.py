from agentflight.demo import FIXTURE_HASH, compare, run_demo


def test_vulnerable_scenario_finds_all_rules():
    run = run_demo("baseline")
    assert run.fixture_hash == FIXTURE_HASH
    assert {f.rule_id for f in run.findings} == {
        "AFR-EGRESS-001", "AFR-APPROVAL-001", "AFR-CHAIN-001", "AFR-SOURCE-001",
        "AFR-GOAL-001", "AFR-PRIV-001", "AFR-STATE-001", "AFR-COMPLETE-001",
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

