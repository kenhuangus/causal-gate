from __future__ import annotations

import os
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .benchmark import run_benchmark
from .demo import compare, run_demo
from .detectors import analyze
from .models import Comparison, Event, Execution, IntentContract, PolicyMode, StrictModel
from .live_analysis import AnalysisArtifact, AnalysisUnavailable, analyze_live, verify_recorded_artifact
from .reporting import markdown_report
from .redaction import redacted_event_payload
from .storage import TraceStore


class CreateExecution(StrictModel):
    intent: IntentContract
    policy_mode: PolicyMode = PolicyMode.BASELINE


def _safe_event(event: Event) -> Event:
    safe = event.model_copy(deep=True)
    safe.payload = redacted_event_payload(event.payload, event.sensitivity)
    safe.redacted_payload = safe.payload
    return safe


def _safe_execution(run: Execution) -> Execution:
    safe = run.model_copy(deep=True)
    safe.events = [_safe_event(event) for event in run.events]
    return safe


def create_app(store: TraceStore | None = None) -> FastAPI:
    app = FastAPI(title="AgentFlight Recorder", version="0.1.0", docs_url="/api/docs")
    app.state.store = store or TraceStore(os.getenv("AGENTFLIGHT_DB", "data/agentflight.db"))
    app.state.demo_mode = os.getenv("AGENTFLIGHT_DEMO_MODE", "true").lower() == "true"
    app.state.demo_ids = set()
    app.state.rate = defaultdict(deque)

    def require_admin(request: Request):
        if app.state.demo_mode:
            raise HTTPException(403, "general trace API is disabled in synthetic demo mode")
        expected = os.getenv("AGENTFLIGHT_ADMIN_TOKEN")
        presented = request.headers.get("X-AgentFlight-Admin", "")
        if not expected or not secrets.compare_digest(presented, expected):
            raise HTTPException(401, "administrator authorization required")

    def require_execution_access(execution_id: str, request: Request):
        """Keep public access fixture-scoped and private access administrator-scoped."""
        if app.state.demo_mode:
            if execution_id not in app.state.demo_ids:
                raise HTTPException(404, "execution not found")
            return
        require_admin(request)

    @app.middleware("http")
    async def security_boundary(request: Request, call_next):
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 128_000:
                return PlainTextResponse("request too large", status_code=413)
            chunks.append(chunk)
        body = b"".join(chunks)
        request._body = body
        if request.url.path.startswith("/api/v1/demo") or request.url.path == "/api/v1/benchmark":
            key = request.client.host if request.client else "unknown"
            now, bucket = time.monotonic(), app.state.rate[key]
            while bucket and bucket[0] < now - 60:
                bucket.popleft()
            if len(bucket) >= 30:
                return PlainTextResponse("demo rate limit exceeded", status_code=429)
            bucket.append(now)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; connect-src 'self'"
        return response

    @app.get("/health")
    def health():
        live_enabled = os.getenv("AGENTFLIGHT_LIVE_ANALYSIS_ENABLED", "false").lower() == "true"
        return {"status": "ok", "mode": "deterministic", "live_analysis": "enabled" if live_enabled else "disabled", "version": app.version}

    @app.get("/api/v1/executions", response_model=list[Execution])
    def executions(request: Request):
        require_admin(request)
        return [_safe_execution(run) for run in app.state.store.list()]

    @app.post("/api/v1/executions", response_model=Execution, status_code=201)
    def create_execution(body: CreateExecution, request: Request):
        require_admin(request)
        run = Execution(id=f"run_{uuid4().hex[:12]}", intent=body.intent, policy_mode=body.policy_mode, status="open")
        return _safe_execution(app.state.store.create(run))

    @app.post("/api/v1/executions/{execution_id}/events", response_model=Event)
    def append_event(execution_id: str, event: Event, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        require_admin(request)
        if event.idempotency_key != idempotency_key:
            raise HTTPException(422, "header and event idempotency keys must match")
        try:
            event.redacted_payload = redacted_event_payload(event.payload, event.sensitivity)
            saved, _ = app.state.store.append(execution_id, event)
            return _safe_event(saved)
        except KeyError as exc:
            raise HTTPException(404, str(exc))
        except FileExistsError as exc:
            raise HTTPException(409, str(exc))
        except RuntimeError as exc:
            raise HTTPException(409, str(exc))
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.post("/api/v1/executions/{execution_id}/complete", response_model=Execution)
    def complete_execution(execution_id: str, request: Request):
        require_admin(request)
        try:
            run = app.state.store.get(execution_id)
            if not run:
                raise KeyError("execution not found")
            run.findings = analyze(run)
            return _safe_execution(app.state.store.seal(execution_id))
        except KeyError as exc:
            raise HTTPException(404, str(exc))

    @app.post("/api/v1/demo/reset")
    def reset():
        baseline = app.state.store.put(run_demo(PolicyMode.BASELINE))
        protected = app.state.store.put(run_demo(PolicyMode.PROTECTED))
        app.state.demo_ids.update({baseline.id, protected.id})
        return {"baseline": baseline.id, "protected": protected.id}

    @app.post("/api/v1/demo/{mode}", response_model=Execution)
    def demo(mode: PolicyMode):
        run = app.state.store.put(run_demo(mode))
        app.state.demo_ids.add(run.id)
        return _safe_execution(run)

    @app.get("/api/v1/executions/{execution_id}", response_model=Execution)
    def execution(execution_id: str, request: Request):
        require_execution_access(execution_id, request)
        run = app.state.store.get(execution_id)
        if not run:
            raise HTTPException(404, "execution not found")
        return _safe_execution(run)

    @app.get("/api/v1/executions/{execution_id}/report")
    def report(execution_id: str, request: Request, format: str = "markdown"):
        require_execution_access(execution_id, request)
        run = app.state.store.get(execution_id)
        if not run:
            raise HTTPException(404, "execution not found")
        if format == "json":
            return _safe_execution(run)
        return PlainTextResponse(markdown_report(run), media_type="text/markdown",
                                 headers={"Content-Disposition": f'attachment; filename="{execution_id}.md"'})

    @app.post("/api/v1/executions/{execution_id}/analyze/live", response_model=AnalysisArtifact)
    def live_analysis(execution_id: str, request: Request):
        require_execution_access(execution_id, request)
        run = app.state.store.get(execution_id)
        if not run:
            raise HTTPException(404, "execution not found")
        try:
            return analyze_live(run)
        except AnalysisUnavailable as exc:
            raise HTTPException(503, str(exc))

    @app.get("/api/v1/recorded-analysis", response_model=AnalysisArtifact)
    def recorded_analysis():
        """Expose the fixture-bound, non-live artifact bundled with the judge image."""
        artifact = Path(__file__).parents[2] / "artifacts" / "recorded-analysis.json"
        if not artifact.exists():
            raise HTTPException(404, "recorded analysis artifact is unavailable")
        try:
            return verify_recorded_artifact(artifact)
        except (OSError, ValueError):
            raise HTTPException(503, "recorded analysis artifact is invalid") from None

    @app.get("/api/v1/comparisons/{left_id}/{right_id}", response_model=Comparison)
    def comparison(left_id: str, right_id: str, request: Request):
        require_execution_access(left_id, request)
        require_execution_access(right_id, request)
        left, right = app.state.store.get(left_id), app.state.store.get(right_id)
        if not left or not right:
            raise HTTPException(404, "execution not found")
        if left.fixture_hash != right.fixture_hash:
            raise HTTPException(409, "fixture hashes do not match")
        return compare(left, right)

    @app.get("/api/v1/benchmark")
    def benchmark():
        return run_benchmark().as_dict()

    web = Path(__file__).parents[2] / "apps" / "web" / "dist"
    if web.exists():
        app.mount("/assets", StaticFiles(directory=web / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            candidate = web / path
            return FileResponse(candidate if path and candidate.is_file() else web / "index.html")

    return app


app = create_app()
