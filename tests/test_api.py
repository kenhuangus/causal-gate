import sqlite3

from fastapi.testclient import TestClient

from agentflight.api import create_app
from agentflight.storage import TraceStore
from agentflight.demo import FIXTURE


def client():
    return TestClient(create_app(TraceStore(":memory:")))


def test_health_and_demo_journey():
    c = client()
    assert c.get("/health").json()["status"] == "ok"
    baseline = c.post("/api/v1/demo/baseline").json()
    protected = c.post("/api/v1/demo/protected").json()
    comparison = c.get(f"/api/v1/comparisons/{baseline['id']}/{protected['id']}")
    assert comparison.status_code == 200
    assert len(comparison.json()["resolved_rules"]) == 8
    report = c.get(f"/api/v1/executions/{baseline['id']}/report")
    assert "AFR-EGRESS-001" in report.text
    flight_record = c.get(f"/api/v1/executions/{baseline['id']}/intent-flight-record")
    assert flight_record.status_code == 200
    assert flight_record.json()["first_divergence"]["sequence"] == 3
    assert flight_record.json()["plan_event_ids"]
    assert flight_record.json()["decision_records"]
    assert flight_record.json()["causal_chain_event_ids"]
    assert comparison.json()["promotion_gate"]["verdict"] == "promote"


def test_missing_execution_is_404():
    assert client().get("/api/v1/executions/not-found").status_code == 404
    assert client().get("/api/v1/executions/not-found/flight-record").status_code == 404
    assert client().get("/api/v1/executions/not-found/intent-flight-record").status_code == 404


def test_live_analysis_disabled_fails_safely(monkeypatch):
    monkeypatch.setenv("AGENTFLIGHT_LIVE_ANALYSIS_ENABLED", "false")
    c = client()
    run = c.post("/api/v1/demo/baseline").json()
    response = c.post(f"/api/v1/executions/{run['id']}/analyze/live")
    assert response.status_code == 503
    assert "disabled" in response.json()["detail"]
    assert c.get("/health").json()["live_analysis"] == "disabled"


def test_public_demo_returns_only_redacted_event_payloads():
    c = client()
    response = c.post("/api/v1/demo/baseline")
    assert response.status_code == 200
    body = response.text
    assert FIXTURE["canary"] not in body
    assert "[PROTECTED]" in body


def test_reset_is_scoped_and_does_not_delete_another_judge_run():
    c = client()
    first = c.post("/api/v1/demo/reset").json()
    second = c.post("/api/v1/demo/reset").json()
    assert first != second
    assert c.get(f"/api/v1/executions/{first['baseline']}").status_code == 200
    assert c.get(f"/api/v1/executions/{second['baseline']}").status_code == 200


def test_public_demo_quota_prunes_records_and_access_ids():
    store = TraceStore(":memory:")
    app = create_app(store, demo_max_records=3)
    c = TestClient(app)
    ids = [c.post("/api/v1/demo/baseline").json()["id"] for _ in range(4)]
    assert list(app.state.demo_ids) == ids[-3:]
    assert store.get(ids[0]) is None
    assert c.get(f"/api/v1/executions/{ids[0]}").status_code == 404
    assert c.get(f"/api/v1/executions/{ids[-1]}").status_code == 200


def test_public_demo_ttl_expires_access_and_storage(monkeypatch):
    now = 1_000.0
    monkeypatch.setattr("agentflight.api.time.time", lambda: now)
    store = TraceStore(":memory:")
    app = create_app(store, demo_ttl_seconds=10)
    c = TestClient(app)
    execution_id = c.post("/api/v1/demo/baseline").json()["id"]
    now = 1_011.0
    assert c.get(f"/api/v1/executions/{execution_id}").status_code == 404
    assert execution_id not in app.state.demo_ids
    assert store.get(execution_id) is None


def test_public_demo_sqlite_batch_pruning_is_bounded(tmp_path):
    path = tmp_path / "demo.db"
    store = TraceStore(str(path))
    c = TestClient(create_app(store, demo_max_records=2))
    first = c.post("/api/v1/demo/reset").json()
    second = c.post("/api/v1/demo/reset").json()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM public_demo_executions").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM executions").fetchone()[0] == 2
    assert c.get(f"/api/v1/executions/{first['baseline']}").status_code == 404
    assert c.get(f"/api/v1/executions/{second['baseline']}").status_code == 200


def test_recorded_analysis_is_available_and_validated_in_judge_profile():
    response = client().get("/api/v1/recorded-analysis")
    assert response.status_code == 200
    assert response.json()["mode"] == "recorded"
    assert response.json()["artifact_digest"]


def test_assurance_suite_requires_runtime_attestation_and_returns_scoped_verdict(monkeypatch):
    monkeypatch.delenv("AGENTFLIGHT_ATTESTATION_KEY", raising=False)
    assert client().get("/api/v1/assurance-suite").status_code == 503
    monkeypatch.setenv("AGENTFLIGHT_ATTESTATION_KEY", "runtime-only-test-key-with-at-least-32-bytes")
    response = client().get("/api/v1/assurance-suite")
    assert response.status_code == 200
    body = response.json()
    assert body["eligible"] is True
    assert body["scope"] == "configured_multi_fixture_suite"
    assert body["production_safety_certification"] is False
    assert body["pass_interval"]["lower"] >= 0.70
