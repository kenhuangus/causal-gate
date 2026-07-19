from __future__ import annotations

import os
import secrets
import threading
import time
from collections import OrderedDict, defaultdict, deque
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .assurance import SuitePromotionGate, run_synthetic_assurance_suite
from .authorization import AuthorizationOntology, AuthorizationRecord, IntentGrant, authorization_record, issue_grant
from .benchmark import run_benchmark
from .demo import compare, run_demo
from .detectors import analyze
from .causal_record import analyze_causal_record
from .models import Comparison, Event, Execution, CausalRecord, IntentContract, PolicyMode, StrictModel
from .live_analysis import AnalysisArtifact, AnalysisUnavailable, analyze_live, verify_recorded_artifact
from .intent_compiler import CompiledIntent, IntentCompilationUnavailable, compile_intent_live
from .reporting import markdown_report
from .redaction import redacted_event_payload
from .storage import TraceStore


class CreateExecution(StrictModel):
    intent: IntentContract
    policy_mode: PolicyMode = PolicyMode.BASELINE


class CompileIntentRequest(StrictModel):
    request: str


class ApproveIntentRequest(StrictModel):
    execution_id: str
    contract: IntentContract
    approver: str
    confirmation: Literal["I_APPROVE_THIS_INTENT"]


PUBLIC_DEMO_MAX_RECORDS = 64
PUBLIC_DEMO_TTL_SECONDS = 60 * 60


def _apply_security_headers(response, *, allow_docs_assets: bool = False):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    if allow_docs_assets:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "font-src 'self' data: https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "connect-src 'self'"
        )
    else:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; connect-src 'self'"
        )
    return response


def _safe_event(event: Event) -> Event:
    safe = event.model_copy(deep=True)
    safe.payload = redacted_event_payload(event.payload, event.sensitivity)
    safe.redacted_payload = safe.payload
    return safe


def _safe_execution(run: Execution) -> Execution:
    safe = run.model_copy(deep=True)
    safe.events = [_safe_event(event) for event in run.events]
    return safe


def create_app(
    store: TraceStore | None = None,
    *,
    demo_max_records: int = PUBLIC_DEMO_MAX_RECORDS,
    demo_ttl_seconds: int = PUBLIC_DEMO_TTL_SECONDS,
) -> FastAPI:
    if demo_max_records < 2 or demo_ttl_seconds <= 0:
        raise ValueError("invalid public demo retention settings")
    app = FastAPI(title="CausalGate", version="0.1.0", docs_url="/api/docs")
    app.state.store = store or TraceStore(os.getenv("CAUSALGATE_DB", "data/causalgate.db"))
    app.state.demo_mode = os.getenv("CAUSALGATE_DEMO_MODE", "true").lower() == "true"
    app.state.demo_ids = OrderedDict()
    app.state.demo_lock = threading.RLock()
    app.state.rate = defaultdict(deque)

    def store_public_demos(runs: list[Execution]) -> list[Execution]:
        now = time.time()
        with app.state.demo_lock:
            saved, removed = app.state.store.put_public_demos(
                runs,
                max_records=demo_max_records,
                ttl_seconds=demo_ttl_seconds,
                now=now,
            )
            for execution_id in removed:
                app.state.demo_ids.pop(execution_id, None)
            for run in saved:
                if run.id not in removed:
                    app.state.demo_ids[run.id] = now + demo_ttl_seconds
                    app.state.demo_ids.move_to_end(run.id)
            return saved

    def require_admin(request: Request):
        if app.state.demo_mode:
            raise HTTPException(403, "general trace API is disabled in synthetic demo mode")
        expected = os.getenv("CAUSALGATE_ADMIN_TOKEN")
        presented = request.headers.get("X-CausalGate-Admin", "")
        if not expected or not secrets.compare_digest(presented, expected):
            raise HTTPException(401, "administrator authorization required")

    def require_execution_access(execution_id: str, request: Request):
        """Keep public access fixture-scoped and private access administrator-scoped."""
        if app.state.demo_mode:
            with app.state.demo_lock:
                expires_at = app.state.demo_ids.get(execution_id)
                if expires_at is not None and expires_at <= time.time():
                    app.state.demo_ids.pop(execution_id, None)
                    app.state.store.delete_public_demo(execution_id)
                    expires_at = None
            if expires_at is None:
                raise HTTPException(404, "execution not found")
            return
        require_admin(request)

    @app.middleware("http")
    async def security_boundary(request: Request, call_next):
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 128_000:
                return _apply_security_headers(PlainTextResponse("request too large", status_code=413))
            chunks.append(chunk)
        body = b"".join(chunks)
        request._body = body
        if request.url.path.startswith("/api/v1/demo") or request.url.path.endswith("/analyze/live") or request.url.path in {
            "/api/v1/benchmark", "/api/v1/assurance-suite", "/api/v1/intent/compile/live"
        }:
            key = request.client.host if request.client else "unknown"
            now, bucket = time.monotonic(), app.state.rate[key]
            while bucket and bucket[0] < now - 60:
                bucket.popleft()
            if len(bucket) >= 30:
                return _apply_security_headers(PlainTextResponse("demo rate limit exceeded", status_code=429))
            bucket.append(now)
        response = await call_next(request)
        return _apply_security_headers(response, allow_docs_assets=request.url.path == "/api/docs")

    @app.get("/health")
    def health():
        live_enabled = os.getenv("CAUSALGATE_LIVE_ANALYSIS_ENABLED", "false").lower() == "true"
        server_key = bool(os.getenv("OPENAI_API_KEY", "").strip())
        live_mode = "server_configured" if live_enabled and server_key else "byok_required" if live_enabled else "disabled"
        return {"status": "ok", "mode": "deterministic", "live_analysis": live_mode, "version": app.version}

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
        baseline, protected = store_public_demos(
            [run_demo(PolicyMode.BASELINE), run_demo(PolicyMode.PROTECTED)]
        )
        return {"baseline": baseline.id, "protected": protected.id}

    @app.post("/api/v1/demo/{mode}", response_model=Execution)
    def demo(mode: PolicyMode):
        run = store_public_demos([run_demo(mode)])[0]
        return _safe_execution(run)

    @app.get("/api/v1/executions/{execution_id}", response_model=Execution)
    def execution(execution_id: str, request: Request):
        require_execution_access(execution_id, request)
        run = app.state.store.get(execution_id)
        if not run:
            raise HTTPException(404, "execution not found")
        return _safe_execution(run)

    @app.get("/api/v1/executions/{execution_id}/causal-record", response_model=CausalRecord)
    @app.get("/api/v1/executions/{execution_id}/intent-causal-record", response_model=CausalRecord)
    def causal_record(execution_id: str, request: Request):
        require_execution_access(execution_id, request)
        run = app.state.store.get(execution_id)
        if not run:
            raise HTTPException(404, "execution not found")
        return analyze_causal_record(run)

    @app.get("/api/v1/executions/{execution_id}/authorization-record", response_model=AuthorizationRecord)
    def execution_authorization_record(execution_id: str, request: Request):
        require_execution_access(execution_id, request)
        run = app.state.store.get(execution_id)
        if not run:
            raise HTTPException(404, "execution not found")
        return authorization_record(run)

    @app.get("/api/v1/authorization/ontology")
    def authorization_ontology():
        ontology = AuthorizationOntology.load_default()
        return {
            "version": ontology.version,
            "digest": ontology.digest,
            "actions": ontology.actions,
            "resource_types": ontology.resource_types,
            "data_classes": ontology.data_classes,
            "destinations": ontology.destinations,
            "effects": ontology.effects,
            "mapped_tools": sorted(ontology.tools),
        }

    @app.post("/api/v1/intent/compile/live", response_model=CompiledIntent)
    def compile_intent(
        body: CompileIntentRequest,
        request: Request,
        x_openai_api_key: str | None = Header(default=None, alias="X-OpenAI-API-Key"),
    ):
        if not app.state.demo_mode:
            require_admin(request)
        try:
            return compile_intent_live(body.request, api_key=x_openai_api_key)
        except IntentCompilationUnavailable as exc:
            raise HTTPException(503, str(exc))

    @app.post("/api/v1/intent/grants", response_model=IntentGrant, status_code=201)
    def approve_intent(body: ApproveIntentRequest, request: Request):
        """Private control-plane operation; model output alone cannot invoke it."""
        require_admin(request)
        key = os.getenv("CAUSALGATE_GRANT_SIGNING_KEY", "")
        if len(key.encode()) < 32:
            raise HTTPException(503, "intent grant signing is not configured")
        try:
            return issue_grant(body.contract, body.execution_id, key, issuer=body.approver)
        except ValueError as exc:
            raise HTTPException(422, str(exc))

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
    def live_analysis(
        execution_id: str,
        request: Request,
        x_openai_api_key: str | None = Header(default=None, alias="X-OpenAI-API-Key"),
    ):
        require_execution_access(execution_id, request)
        run = app.state.store.get(execution_id)
        if not run:
            raise HTTPException(404, "execution not found")
        try:
            return analyze_live(run, api_key=x_openai_api_key)
        except AnalysisUnavailable as exc:
            raise HTTPException(503, str(exc))

    @app.get("/api/v1/recorded-analysis", response_model=AnalysisArtifact)
    def recorded_analysis():
        """Expose the fixture-bound, non-live artifact bundled with the judge image."""
        artifact = Path(os.getenv(
            "CAUSALGATE_RECORDED_ANALYSIS",
            str(Path(__file__).parents[2] / "artifacts" / "recorded-analysis.json"),
        ))
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

    @app.get("/api/v1/assurance-suite", response_model=SuitePromotionGate | None)
    def assurance_suite():
        key = os.getenv("CAUSALGATE_ATTESTATION_KEY", "")
        if len(key.encode()) < 32:
            return None
        return run_synthetic_assurance_suite(key)

    web = Path(os.getenv("CAUSALGATE_WEB_DIR", "apps/web/dist")).resolve()
    if not web.exists():
        web = Path(__file__).parents[2] / "apps" / "web" / "dist"
    if web.exists():
        app.mount("/assets", StaticFiles(directory=web / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            candidate = web / path
            return FileResponse(candidate if path and candidate.is_file() else web / "index.html")

    return app


app = create_app()
