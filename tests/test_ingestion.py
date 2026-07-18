from concurrent.futures import ThreadPoolExecutor
import sqlite3

from fastapi.testclient import TestClient

from agentflight.api import create_app
from agentflight.models import Event, EventType, Execution
from agentflight.storage import TraceStore


ADMIN = {"X-AgentFlight-Admin": "test-admin-token"}


def _created(client: TestClient):
    body = {"intent": {"goal": "summarize", "allowed_tools": ["lookup"]}, "policy_mode": "baseline"}
    response = client.post("/api/v1/executions", json=body, headers=ADMIN)
    assert response.status_code == 201
    return response.json()


def test_identical_retry_succeeds_changed_body_conflicts_and_seal_blocks(monkeypatch):
    monkeypatch.setenv("AGENTFLIGHT_DEMO_MODE", "false")
    monkeypatch.setenv("AGENTFLIGHT_ADMIN_TOKEN", "test-admin-token")
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
    monkeypatch.setenv("AGENTFLIGHT_DEMO_MODE", "false")
    monkeypatch.setenv("AGENTFLIGHT_ADMIN_TOKEN", "test-admin-token")
    client = TestClient(create_app(TraceStore(":memory:")))
    run = _created(client)
    event = Event(execution_id=run["id"], sequence=1, type=EventType.RETRIEVAL, actor="tool", payload={"document": "x"},
                  parent_id="evt_from_another_run", idempotency_key="parent-key-001")
    response = client.post(f"/api/v1/executions/{run['id']}/events", json=event.model_dump(mode="json"), headers={**ADMIN, "Idempotency-Key": event.idempotency_key})
    assert response.status_code == 422


def test_public_demo_mode_blocks_general_trace_api():
    client = TestClient(create_app(TraceStore(":memory:")))
    assert client.get("/api/v1/executions").status_code == 403
    assert client.post("/api/v1/executions", json={"intent": {"goal": "x", "allowed_tools": []}}).status_code == 403
    assert client.get("/api/v1/executions/guessed-id").status_code == 404


def test_private_execution_reads_and_reports_require_admin(monkeypatch):
    monkeypatch.setenv("AGENTFLIGHT_DEMO_MODE", "false")
    monkeypatch.setenv("AGENTFLIGHT_ADMIN_TOKEN", "test-admin-token")
    client = TestClient(create_app(TraceStore(":memory:")))
    run = _created(client)
    assert client.get(f"/api/v1/executions/{run['id']}").status_code == 401
    assert client.get(f"/api/v1/executions/{run['id']}/report").status_code == 401
    assert client.get(f"/api/v1/executions/{run['id']}", headers=ADMIN).status_code == 200
    assert client.get(f"/api/v1/executions/{run['id']}/report", headers=ADMIN).status_code == 200


def test_stream_body_limit():
    client = TestClient(create_app(TraceStore(":memory:")))
    response = client.post("/api/v1/demo/baseline", content=b"x" * 128_001)
    assert response.status_code == 413


def test_client_supplied_redacted_payload_is_not_trusted(monkeypatch):
    monkeypatch.setenv("AGENTFLIGHT_DEMO_MODE", "false")
    monkeypatch.setenv("AGENTFLIGHT_ADMIN_TOKEN", "test-admin-token")
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
    with sqlite3.connect(path) as connection:
        durable_text = " ".join(str(value) for row in connection.execute("SELECT body FROM executions UNION ALL SELECT body FROM events") for value in row)
    assert "must-not-persist" not in durable_text and "also-not-persist" not in durable_text
    same, retry = store.append(run.id, event)
    assert retry and same.id == event.id
