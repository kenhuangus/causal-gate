import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

import causalgate.api as api_module
from causalgate.api import create_app
from causalgate.storage import TraceStore
from causalgate.demo import FIXTURE


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
    assert "CG-EGRESS-001" in report.text
    causal_record = c.get(f"/api/v1/executions/{baseline['id']}/intent-causal-record")
    assert causal_record.status_code == 200
    assert causal_record.json()["first_divergence"]["sequence"] == 5
    assert causal_record.json()["plan_event_ids"]
    assert causal_record.json()["decision_records"]
    assert causal_record.json()["causal_chain_event_ids"]
    assert comparison.json()["promotion_gate"]["verdict"] == "promote"
    authorization = c.get(f"/api/v1/executions/{baseline['id']}/authorization-record")
    assert authorization.status_code == 200
    assert authorization.json()["complete_mediation"] is True
    assert authorization.json()["denied"] == 2
    ontology = c.get("/api/v1/authorization/ontology").json()
    assert ontology["version"] == "causalgate-ontology/1.0"
    assert ontology["digest"].startswith("sha256:")


def test_web_ui_is_served_when_package_is_installed_outside_project(monkeypatch, tmp_path):
    web = tmp_path / "apps" / "web" / "dist"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<main>CausalGate UI</main>", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        api_module,
        "__file__",
        str(Path("/usr/local/lib/python3.12/site-packages/causalgate/api.py")),
    )

    response = client().get("/")

    assert response.status_code == 200
    assert "CausalGate UI" in response.text


def test_missing_execution_is_404():
    assert client().get("/api/v1/executions/not-found").status_code == 404
    assert client().get("/api/v1/executions/not-found/causal-record").status_code == 404
    assert client().get("/api/v1/executions/not-found/intent-causal-record").status_code == 404


def test_live_analysis_disabled_fails_safely(monkeypatch):
    monkeypatch.setenv("CAUSALGATE_LIVE_ANALYSIS_ENABLED", "false")
    c = client()
    run = c.post("/api/v1/demo/baseline").json()
    response = c.post(f"/api/v1/executions/{run['id']}/analyze/live")
    assert response.status_code == 503
    assert "disabled" in response.json()["detail"]
    assert c.get("/health").json()["live_analysis"] == "disabled"
    compiled = c.post("/api/v1/intent/compile/live", json={"request": "Research Acme."})
    assert compiled.status_code == 503
    assert "disabled" in compiled.json()["detail"]


def test_public_live_analysis_requires_and_forwards_ephemeral_byok(monkeypatch):
    monkeypatch.setenv("CAUSALGATE_LIVE_ANALYSIS_ENABLED", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    received = []

    def fake_analysis(run, *, api_key=None):
        received.append(api_key)
        from causalgate.live_analysis import AnalysisUnavailable
        raise AnalysisUnavailable("test boundary reached")

    monkeypatch.setattr("causalgate.api.analyze_live", fake_analysis)
    c = client()
    assert c.get("/health").json()["live_analysis"] == "byok_required"
    run = c.post("/api/v1/demo/baseline").json()
    response = c.post(
        f"/api/v1/executions/{run['id']}/analyze/live",
        headers={"X-OpenAI-API-Key": "synthetic-ephemeral-key-at-least-32-bytes"},
    )
    assert response.status_code == 503
    assert received == ["synthetic-ephemeral-key-at-least-32-bytes"]


def test_grant_issuance_is_private_explicit_and_runtime_signed(monkeypatch):
    monkeypatch.setenv("CAUSALGATE_DEMO_MODE", "false")
    monkeypatch.setenv("CAUSALGATE_ADMIN_TOKEN", "admin-test-token")
    monkeypatch.setenv("CAUSALGATE_GRANT_SIGNING_KEY", "runtime-grant-signing-key-at-least-32-bytes")
    body = {
        "execution_id": "run_private",
        "approver": "user:owner",
        "confirmation": "I_APPROVE_THIS_INTENT",
        "contract": {
            "goal": "Research public vendor data.",
            "purpose_id": "purpose.vendor.public_research",
            "subject_id": "agent:research",
            "on_behalf_of": "user:owner",
            "allowed_tools": ["retrieve"],
            "allowed_resource_types": ["resource.public"],
            "allowed_data_classes": ["data.public"],
            "allowed_destinations": ["destination.local"],
        },
    }
    c = client()
    assert c.post("/api/v1/intent/grants", json=body).status_code == 401
    response = c.post("/api/v1/intent/grants", json=body, headers={"X-CausalGate-Admin": "admin-test-token"})
    assert response.status_code == 201
    assert response.json()["execution_id"] == "run_private"
    assert response.json()["signature"]


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
    monkeypatch.setattr("causalgate.api.time.time", lambda: now)
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
    monkeypatch.delenv("CAUSALGATE_ATTESTATION_KEY", raising=False)
    assert client().get("/api/v1/assurance-suite").status_code == 503
    monkeypatch.setenv("CAUSALGATE_ATTESTATION_KEY", "runtime-only-test-key-with-at-least-32-bytes")
    response = client().get("/api/v1/assurance-suite")
    assert response.status_code == 200
    body = response.json()
    assert body["eligible"] is True
    assert body["scope"] == "configured_multi_fixture_suite"
    assert body["production_safety_certification"] is False
    assert body["pass_interval"]["lower"] >= 0.70
