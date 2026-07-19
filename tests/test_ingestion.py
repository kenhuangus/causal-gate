from concurrent.futures import ThreadPoolExecutor
import sqlite3
from contextlib import closing

from fastapi.testclient import TestClient

from causalgate.api import create_app
from causalgate.causal_record import intent_clauses
from causalgate.models import Event, EventType, Execution
from causalgate.storage import TraceStore


ADMIN = {"X-CausalGate-Admin": "test-admin-token"}


def _created(client: TestClient):
    body = {"intent": {"goal": "summarize", "allowed_tools": ["lookup"]}, "policy_mode": "baseline"}
    response = client.post("/api/v1/executions", json=body, headers=ADMIN)
    assert response.status_code == 201
    return response.json()


def test_identical_retry_succeeds_changed_body_conflicts_and_seal_blocks(monkeypatch):
    monkeypatch.setenv("CAUSALGATE_DEMO_MODE", "false")
    monkeypatch.setenv("CAUSALGATE_ADMIN_TOKEN", "test-admin-token")
    client = TestClient(create_app(TraceStore(":memory:")))
    run = _created(client)
    event = Event(execution_id=run["id"], sequence=1, type=EventType.USER_INTENT, actor="user",
                  payload={"goal": "summarize"}, redacted_payload={"goal": "summarize"}, idempotency_key="retry-key-001")
    headers = {**ADMIN, "Idempotency-Key": event.idempotency_key}
    assert client.post(f"/api/v1/executions/{run['id']}/events", json=event.model_dump(mode="json"), headers=headers).status_code == 200
    assert client.post(f"/api/v1/executions/{run['id']}/events", json=event.model_dump(mode="json"), headers=headers).status_code == 200
    changed = event.model_copy(deep=True)
    changed.payload["goal"] = "changed"
    assert client.post(f"/api/v1/executions/{run['id']}/events", json=changed.model_dump(mode="json"), headers=headers).status_code == 409
    assert client.post(f"/api/v1/executions/{run['id']}/complete", headers=ADMIN).status_code == 200
    next_event = Event(execution_id=run["id"], sequence=2, type=EventType.RETRIEVAL, actor="tool", payload={"document": "x"}, idempotency_key="retry-key-002")
    assert client.post(f"/api/v1/executions/{run['id']}/events", json=next_event.model_dump(mode="json"), headers={**ADMIN, "Idempotency-Key": next_event.idempotency_key}).status_code == 409


def test_parent_must_be_earlier_same_run(monkeypatch):
    monkeypatch.setenv("CAUSALGATE_DEMO_MODE", "false")
    monkeypatch.setenv("CAUSALGATE_ADMIN_TOKEN", "test-admin-token")
    client = TestClient(create_app(TraceStore(":memory:")))
    run = _created(client)
    event = Event(execution_id=run["id"], sequence=1, type=EventType.RETRIEVAL, actor="tool", payload={"document": "x"},
                  parent_id="evt_from_another_run", idempotency_key="parent-key-001")
    response = client.post(f"/api/v1/executions/{run['id']}/events", json=event.model_dump(mode="json"), headers={**ADMIN, "Idempotency-Key": event.idempotency_key})
    assert response.status_code == 422


def test_decision_evidence_and_intent_clauses_must_resolve_in_same_run(monkeypatch):
    monkeypatch.setenv("CAUSALGATE_DEMO_MODE", "false")
    monkeypatch.setenv("CAUSALGATE_ADMIN_TOKEN", "test-admin-token")
    client = TestClient(create_app(TraceStore(":memory:")))
    run = _created(client)
    intent_event = Event(
        execution_id=run["id"], sequence=1, type=EventType.USER_INTENT, actor="user",
        payload={"goal": "summarize"}, idempotency_key="intent-proof-001",
    )
    assert client.post(
        f"/api/v1/executions/{run['id']}/events",
        json=intent_event.model_dump(mode="json"),
        headers={**ADMIN, "Idempotency-Key": intent_event.idempotency_key},
    ).status_code == 200
    valid_clause = intent_clauses(Execution.model_validate(run).intent)[0].id
    base_payload = {
        "summary": "Use the authorized lookup path.", "subgoal_id": "summary.lookup",
        "intent_clause_ids": [valid_clause], "evidence_event_ids": ["evt_other_run"],
        "alignment": "aligned", "proposed_tools": ["lookup"],
    }
    bad_evidence = Event(
        execution_id=run["id"], sequence=2, type=EventType.PLAN, actor="agent",
        payload=base_payload, idempotency_key="intent-proof-002",
    )
    response = client.post(
        f"/api/v1/executions/{run['id']}/events",
        json=bad_evidence.model_dump(mode="json"),
        headers={**ADMIN, "Idempotency-Key": bad_evidence.idempotency_key},
    )
    assert response.status_code == 422
    bad_clause = bad_evidence.model_copy(deep=True)
    bad_clause.idempotency_key = "intent-proof-003"
    bad_clause.payload["evidence_event_ids"] = [intent_event.id]
    bad_clause.payload["intent_clause_ids"] = ["intent_goal_not_in_contract"]
    response = client.post(
        f"/api/v1/executions/{run['id']}/events",
        json=bad_clause.model_dump(mode="json"),
        headers={**ADMIN, "Idempotency-Key": bad_clause.idempotency_key},
    )
    assert response.status_code == 422


def test_public_demo_mode_blocks_general_trace_api():
    client = TestClient(create_app(TraceStore(":memory:")))
    assert client.get("/api/v1/executions").status_code == 403
    assert client.post("/api/v1/executions", json={"intent": {"goal": "x", "allowed_tools": []}}).status_code == 403
    assert client.get("/api/v1/executions/guessed-id").status_code == 404


def test_private_execution_reads_and_reports_require_admin(monkeypatch):
    monkeypatch.setenv("CAUSALGATE_DEMO_MODE", "false")
    monkeypatch.setenv("CAUSALGATE_ADMIN_TOKEN", "test-admin-token")
    client = TestClient(create_app(TraceStore(":memory:")))
    run = _created(client)
    assert client.get(f"/api/v1/executions/{run['id']}").status_code == 401
    assert client.get(f"/api/v1/executions/{run['id']}/report").status_code == 401
    assert client.get(f"/api/v1/executions/{run['id']}", headers=ADMIN).status_code == 200
    assert client.get(f"/api/v1/executions/{run['id']}/report", headers=ADMIN).status_code == 200
    assert client.get(f"/api/v1/executions/{run['id']}/causal-record").status_code == 401
    causal_record = client.get(f"/api/v1/executions/{run['id']}/causal-record", headers=ADMIN)
    assert causal_record.status_code == 200
    assert causal_record.json()["execution_id"] == run["id"]


def test_stream_body_limit():
    client = TestClient(create_app(TraceStore(":memory:")))
    response = client.post("/api/v1/demo/baseline", content=b"x" * 128_001)
    assert response.status_code == 413
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Content-Security-Policy"] == (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; connect-src 'self'"
    )


def test_rate_limit_response_keeps_security_headers():
    client = TestClient(create_app(TraceStore(":memory:")))
    for _ in range(30):
        assert client.post("/api/v1/demo/baseline").status_code == 200
    response = client.post("/api/v1/demo/baseline")
    assert response.status_code == 429
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "fonts.googleapis.com" not in response.headers["Content-Security-Policy"]
    assert "fonts.gstatic.com" not in response.headers["Content-Security-Policy"]


def test_client_supplied_redacted_payload_is_not_trusted(monkeypatch):
    monkeypatch.setenv("CAUSALGATE_DEMO_MODE", "false")
    monkeypatch.setenv("CAUSALGATE_ADMIN_TOKEN", "test-admin-token")
    client = TestClient(create_app(TraceStore(":memory:")))
    run = _created(client)
    event = Event(execution_id=run["id"], sequence=1, type=EventType.TOOL_RESULT, actor="tool",
                  payload={"api_key": "sk-synthetic-not-a-key"}, redacted_payload={"api_key": "attacker lied"},
                  idempotency_key="redaction-key-001")
    response = client.post(f"/api/v1/executions/{run['id']}/events", json=event.model_dump(mode="json"),
                           headers={**ADMIN, "Idempotency-Key": event.idempotency_key})
    assert response.status_code == 200
    assert response.json()["payload"]["api_key"] == "[REDACTED]"
    assert "sk-synthetic-not-a-key" not in response.text


def test_sqlite_persistence_never_contains_raw_event_payload(tmp_path):
    path = tmp_path / "trace.db"
    store = TraceStore(str(path))
    run = store.create(Execution(id="run_persist", policy_mode="baseline", intent={"goal": "x", "allowed_tools": []}, status="open"))
    event = Event(execution_id=run.id, sequence=1, type=EventType.TOOL_RESULT, actor="tool",
                  payload={"access_token": "must-not-persist", "nested": {"x-api-key": "also-not-persist"}},
                  idempotency_key="persist-key-001")
    stored, retry = store.append(run.id, event)
    assert not retry and stored.payload["access_token"] == "[REDACTED]"
    # A new store simulates process restart and proves the durable body is safe.
    restored = TraceStore(str(path)).get(run.id)
    assert restored and restored.events[0].payload["nested"]["x-api-key"] == "[REDACTED]"
    with closing(sqlite3.connect(path)) as connection:
        durable_text = " ".join(str(value) for row in connection.execute("SELECT body FROM executions UNION ALL SELECT body FROM events") for value in row)
    assert "must-not-persist" not in durable_text and "also-not-persist" not in durable_text
    same, retry = store.append(run.id, event)
    assert retry and same.id == event.id
