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


def test_missing_execution_is_404():
    assert client().get("/api/v1/executions/not-found").status_code == 404


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


def test_recorded_analysis_is_available_and_validated_in_judge_profile():
    response = client().get("/api/v1/recorded-analysis")
    assert response.status_code == 200
    assert response.json()["mode"] == "recorded"
    assert response.json()["artifact_digest"]
