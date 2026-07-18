from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol, runtime_checkable

from .models import Event, Execution


class TraceSinkError(RuntimeError):
    """Raised when a trace sink cannot accept or flush an execution."""


@runtime_checkable
class TraceSink(Protocol):
    """Transport boundary used by the SDK without coupling capture to storage."""

    def start(self, execution: Execution) -> None: ...

    def write(self, event: Event) -> None: ...

    def finish(self, execution: Execution) -> None: ...

    def flush(self) -> None: ...

    def close(self) -> None: ...


class InMemoryTraceSink:
    def __init__(self) -> None:
        self.executions: dict[str, Execution] = {}

    def start(self, execution: Execution) -> None:
        self.executions[execution.id] = execution.model_copy(deep=True)

    def write(self, event: Event) -> None:
        execution = self.executions.get(event.execution_id)
        if execution is None:
            raise TraceSinkError("execution was not started")
        execution.events.append(event.model_copy(deep=True))

    def finish(self, execution: Execution) -> None:
        self.executions[execution.id] = execution.model_copy(deep=True)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


class JsonlTraceSink:
    """Append redacted SDK records to a local JSON-lines file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._handle = self.path.open("a", encoding="utf-8")

    def _append(self, kind: str, payload: dict) -> None:
        with self._lock:
            self._handle.write(json.dumps({"kind": kind, **payload}, separators=(",", ":"), default=str) + "\n")

    def start(self, execution: Execution) -> None:
        self._append("execution_start", {
            "execution_id": execution.id,
            "policy_mode": execution.policy_mode,
            "intent": execution.intent.model_dump(mode="json"),
        })

    def write(self, event: Event) -> None:
        safe = event.model_copy(deep=True)
        safe.payload = safe.redacted_payload
        self._append("event", {"event": safe.model_dump(mode="json")})

    def finish(self, execution: Execution) -> None:
        self._append("execution_end", {"execution_id": execution.id, "status": execution.status})

    def flush(self) -> None:
        with self._lock:
            self._handle.flush()

    def close(self) -> None:
        with self._lock:
            if not self._handle.closed:
                self._handle.flush()
                self._handle.close()


class ApiTraceSink:
    """Buffered exporter for CausalGate's authenticated ingestion API."""

    def __init__(
        self,
        base_url: str,
        admin_token: str,
        *,
        timeout: float = 5.0,
        retries: int = 2,
        batch_size: int = 20,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must use http or https")
        if not admin_token:
            raise ValueError("admin_token is required")
        if timeout <= 0 or retries < 0 or batch_size <= 0:
            raise ValueError("invalid sink retry or batching configuration")
        self.base_url = base_url.rstrip("/")
        self.admin_token = admin_token
        self.timeout = timeout
        self.retries = retries
        self.batch_size = batch_size
        self._remote_ids: dict[str, str] = {}
        self._queue: list[Event] = []
        self._lock = threading.RLock()

    def _request(self, method: str, path: str, body: dict | None = None, headers: dict[str, str] | None = None) -> dict:
        data = json.dumps(body, separators=(",", ":")).encode() if body is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "X-CausalGate-Admin": self.admin_token, **(headers or {})},
        )
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read())
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                if attempt >= self.retries:
                    raise TraceSinkError(f"CausalGate API export failed: {type(exc).__name__}") from exc
                time.sleep(0.05 * (2 ** attempt))
        raise TraceSinkError("CausalGate API export failed")

    def start(self, execution: Execution) -> None:
        response = self._request("POST", "/api/v1/executions", {
            "intent": execution.intent.model_dump(mode="json"),
            "policy_mode": execution.policy_mode,
        })
        self._remote_ids[execution.id] = response["id"]

    def write(self, event: Event) -> None:
        with self._lock:
            if event.execution_id not in self._remote_ids:
                raise TraceSinkError("execution was not started")
            self._queue.append(event.model_copy(deep=True))
            if len(self._queue) >= self.batch_size:
                self.flush()

    def flush(self) -> None:
        with self._lock:
            pending, self._queue = self._queue, []
            try:
                for event in pending:
                    remote_id = self._remote_ids[event.execution_id]
                    event.execution_id = remote_id
                    event.payload = event.redacted_payload
                    self._request(
                        "POST",
                        f"/api/v1/executions/{remote_id}/events",
                        event.model_dump(mode="json"),
                        {"Idempotency-Key": event.idempotency_key},
                    )
            except Exception:
                self._queue = pending + self._queue
                raise

    def finish(self, execution: Execution) -> None:
        self.flush()
        remote_id = self._remote_ids[execution.id]
        self._request("POST", f"/api/v1/executions/{remote_id}/complete")

    def close(self) -> None:
        self.flush()
