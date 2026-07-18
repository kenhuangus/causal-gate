from __future__ import annotations

import sqlite3
import hashlib
import threading
from pathlib import Path

from .models import Event, Execution
from .redaction import redacted_event_payload


def _safe_event(event: Event) -> Event:
    """Return the representation permitted to reach durable storage.

    Raw payloads are useful only during the active process for deterministic
    analysis. They must not be written to the local SQLite profile.
    """
    safe = event.model_copy(deep=True)
    safe.payload = redacted_event_payload(event.payload, event.sensitivity)
    safe.redacted_payload = safe.payload
    return safe


def _safe_execution(run: Execution) -> Execution:
    safe = run.model_copy(deep=True)
    safe.events = [_safe_event(event) for event in run.events]
    return safe


class TraceStore:
    def __init__(self, path: str = "agentflight.db"):
        self.path = path
        self._memory: dict[str, Execution] = {}
        self._memory_idempotency: dict[tuple[str, str], tuple[str, str]] = {}
        self._lock = threading.RLock()
        if path == ":memory:":
            return
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS executions (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS events (execution_id TEXT NOT NULL, sequence INTEGER NOT NULL, event_id TEXT NOT NULL UNIQUE, body TEXT NOT NULL, PRIMARY KEY(execution_id, sequence))")
            conn.execute("CREATE TABLE IF NOT EXISTS idempotency (execution_id TEXT NOT NULL, key TEXT NOT NULL, body_hash TEXT NOT NULL, event_id TEXT NOT NULL, PRIMARY KEY(execution_id, key))")

    def _connect(self):
        return sqlite3.connect(self.path)

    def put(self, run: Execution) -> Execution:
        safe = _safe_execution(run)
        with self._lock:
            self._memory[safe.id] = safe
            self._memory_idempotency = {key: value for key, value in self._memory_idempotency.items() if key[0] != safe.id}
            for event in safe.events:
                self._memory_idempotency[(safe.id, event.idempotency_key)] = (hashlib.sha256(event.model_dump_json().encode()).hexdigest(), event.id)
            if self.path == ":memory:":
                return safe
            with self._connect() as conn:
                conn.execute("INSERT INTO executions(id, body) VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET body=excluded.body", (safe.id, safe.model_dump_json()))
        return safe

    def create(self, run: Execution) -> Execution:
        if run.status != "open" or run.events:
            raise ValueError("new execution must be open and empty")
        if run.id in self._memory or self.get(run.id):
            raise ValueError("execution already exists")
        return self.put(run)

    def append(self, execution_id: str, event: Event) -> tuple[Event, bool]:
        # The hash binds an idempotency key to the original request without
        # persisting that request body. The stored event itself is redacted.
        body_hash = hashlib.sha256(event.model_dump_json().encode()).hexdigest()
        safe_event = _safe_event(event)
        with self._lock:
            if self.path == ":memory:":
                run = self.get(execution_id)
                if not run:
                    raise KeyError("execution not found")
                if run.status != "open":
                    raise RuntimeError("execution is sealed")
                prior = self._memory_idempotency.get((execution_id, event.idempotency_key))
                if prior:
                    if prior[0] != body_hash:
                        raise FileExistsError("idempotency key reused with changed body")
                    existing = next(item for item in run.events if item.id == prior[1])
                    return existing, True
                self._validate_append(run, event)
                run.events.append(safe_event)
                self._memory_idempotency[(execution_id, event.idempotency_key)] = (body_hash, event.id)
                self._memory[run.id] = run
                return safe_event, False
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute("SELECT body FROM executions WHERE id = ?", (execution_id,)).fetchone()
                if not row:
                    raise KeyError("execution not found")
                run = Execution.model_validate_json(row[0])
                if run.status != "open":
                    raise RuntimeError("execution is sealed")
                prior = conn.execute("SELECT body_hash, event_id FROM idempotency WHERE execution_id=? AND key=?", (execution_id, event.idempotency_key)).fetchone()
                if prior:
                    if prior[0] != body_hash:
                        raise FileExistsError("idempotency key reused with changed body")
                    found = conn.execute("SELECT body FROM events WHERE execution_id=? AND event_id=?", (execution_id, prior[1])).fetchone()
                    if not found:
                        raise RuntimeError("idempotency record is inconsistent")
                    return Event.model_validate_json(found[0]), True
                self._validate_append(run, event)
                conn.execute("INSERT INTO events VALUES (?, ?, ?, ?)", (execution_id, event.sequence, event.id, safe_event.model_dump_json()))
                conn.execute("INSERT INTO idempotency VALUES (?, ?, ?, ?)", (execution_id, event.idempotency_key, body_hash, event.id))
                run.events.append(safe_event)
                conn.execute("UPDATE executions SET body=? WHERE id=?", (run.model_dump_json(), execution_id))
            self._memory[run.id] = run
            return safe_event, False

    @staticmethod
    def _validate_append(run: Execution, event: Event) -> None:
        if event.execution_id != run.id or event.sequence != len(run.events) + 1:
            raise ValueError("execution or sequence mismatch")
        if event.parent_id and event.parent_id not in {existing.id for existing in run.events}:
            raise ValueError("parent must reference an earlier event in this execution")

    def seal(self, execution_id: str) -> Execution:
        run = self.get(execution_id)
        if not run:
            raise KeyError("execution not found")
        if run.status == "complete":
            return run
        run.status = "complete"
        return self.put(run)

    def get(self, execution_id: str) -> Execution | None:
        if execution_id in self._memory:
            return self._memory[execution_id]
        if self.path == ":memory:":
            return None
        with self._connect() as conn:
            row = conn.execute("SELECT body FROM executions WHERE id = ?", (execution_id,)).fetchone()
        return Execution.model_validate_json(row[0]) if row else None

    def list(self) -> list[Execution]:
        if self.path == ":memory:":
            return list(reversed(self._memory.values()))
        with self._connect() as conn:
            rows = conn.execute("SELECT body FROM executions ORDER BY rowid DESC LIMIT 100").fetchall()
        return [Execution.model_validate_json(row[0]) for row in rows]

    def reset(self) -> None:
        with self._lock:
            self._memory.clear()
            self._memory_idempotency.clear()
            if self.path == ":memory:":
                return
            with self._connect() as conn:
                conn.execute("DELETE FROM idempotency")
                conn.execute("DELETE FROM events")
                conn.execute("DELETE FROM executions")
