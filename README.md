# AgentFlight Recorder

AgentFlight Recorder turns a tool-using AI-agent run into an evidence-linked security investigation and replays the identical scenario under a changed policy. The included judge path is deterministic, uses synthetic data, makes no network calls, and requires no OpenAI API key.

## Judge quickstart

```bash
docker compose up --build --wait
```

Open `http://localhost:8080`, select **Run vulnerable scenario**, inspect a finding, then select **Replay with protection**. The baseline run seeds eight documented security conditions. The protected replay uses the same fixture hash and blocks the unauthorized read before synthetic data can reach the simulated outbound tool.

Without Docker:

```bash
uv sync --extra dev
cd apps/web && npm install && npm run build && cd ../..
uv run python main.py
```

## Verification

```bash
make verify-demo
make verify-benchmark
make verify-adapters
```

`make verify-demo` runs Python tests, the end-to-end CLI assertion, and the production frontend build. The 32-case labeled benchmark consists of two adversarial and two benign near-miss variants for each of the eight detector classes. Reported precision and recall apply only to this synthetic suite.

## Five-minute SDK integration

```python
from agentflight import IntentContract, Recorder, trace_tool

@trace_tool("lookup")
def lookup(*, query: str):
    return {"title": "Synthetic result", "query": query}

contract = IntentContract(goal="Research a public vendor", allowed_tools=["lookup"])
with Recorder(contract) as recorder:
    result = lookup(query="Acme")
    execution = recorder.finish(f"Found {result['title']}")

print(execution.model_dump_json(indent=2))
```

The `AgentsSDKTraceAdapter` and `LangGraphTraceAdapter` normalize framework callbacks into the same append-only contract. The adapter layer intentionally does not call a model; applications retain control of runtime credentials and model selection.

## CLI and CI gate

```bash
uv run agentflight demo --mode baseline --json  # exits 1 on critical findings
uv run agentflight demo --mode protected        # exits 0
uv run agentflight verify-demo
uv run agentflight benchmark
```

The GitHub Actions workflow executes the complete keyless verification path. It has read-only repository permissions and receives no product runtime key.

## Architecture

The FastAPI service serves both the versioned API and the React investigation interface. SQLite provides a zero-configuration local profile. Cloud Run can deploy the same container; Cloud SQL and a private worker are the documented scale-out path. Trace capture, redaction, deterministic analysis, replay, report export, and adapters are separate modules with strict Pydantic contracts.

The eight rules are protected-data egress, missing approval, unsafe tool chaining, instruction-source confusion, goal drift, privilege escalation, unsafe authorization-state mutation, and unsupported completion. Every finding cites event identifiers validated against its execution.

## Security model

The demonstration contains no real secret, external retrieval, or outbound side effect. Baseline mode is explicitly observational; protected mode is deny-by-default. Event payloads have a separate redacted representation, byte-accurate bounds, same-run parent checks, and immutable idempotency keys. Model output, when added, must remain untrusted structured data and cannot suppress deterministic findings or execute tools. `.env*` files are ignored except `.env.example`.

Public deployments run with `AGENTFLIGHT_DEMO_MODE=true`. In this mode anonymous users can run the synthetic scenarios and access only execution identifiers created by those actions; list, create, append, and complete APIs are disabled, guessed identifiers return 404, request streams are capped, and demo actions are rate-limited. Private developer ingestion requires `AGENTFLIGHT_DEMO_MODE=false` plus a server-side `AGENTFLIGHT_ADMIN_TOKEN`; creation, retrieval, reporting, comparison, and live analysis all require that token in this profile. This token is not a substitute for production workspace identity and authorization.

This prototype is a developer security instrument, not a SIEM, compliance certification, or claim of production-scale detector validation.

## OpenAI and Codex usage

The implementation follows the OpenAI Agents SDK pattern of one explicit agent path, narrow deterministic tools, stable trace boundaries, and behavior-oriented evals. The deterministic release path does not make an OpenAI API call. The browser, tests, CLI fixtures, build, and documentation do not need or access a runtime key.

The optional server-only semantic analyzer is disabled unless both `AGENTFLIGHT_LIVE_ANALYSIS_ENABLED=true` and `OPENAI_API_KEY` are present. It uses the official OpenAI Responses API with `OPENAI_MODEL` (default `gpt-5.6`), a minimized redacted trace, strict structured output, same-run evidence validation, bounded timeout/retry, sanitized errors, and a small hourly process quota. Its results are separate provenance-labeled artifacts: they cannot suppress deterministic findings, change policy, or execute a tool. The judge image includes the fixture-bound non-live artifact at `GET /api/v1/recorded-analysis`; its SHA-256 integrity field is verified before serving.

To generate the submission's recorded artifact through the same product path at runtime:

```bash
AGENTFLIGHT_LIVE_ANALYSIS_ENABLED=true uv run agentflight record-analysis --output artifacts/recorded-analysis.json
uv run python scripts/verify_recorded_analysis.py
```

The generator reads credentials only through the server runtime environment. Missing recorded evidence fails verification by default. A deterministic-only profile may explicitly set `AGENTFLIGHT_RECORDED_ANALYSIS_OPTIONAL=true`, which produces a labeled `SKIP` rather than a false pass.

Codex assisted with the implementation and verification described in `docs/codex-build-log.md`. No claim is made beyond the recorded files and commands.

## Google Cloud deployment

Create an Artifact Registry repository named `agentflight`, then submit the pinned container through Cloud Build:

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
gcloud artifacts repositories create agentflight --repository-format=docker --location=us-central1
gcloud builds submit --config cloudbuild.yaml
```

The configuration exposes only the synthetic judge service. Cloud SQL, a private worker, Secret Manager, retention, and authenticated workspaces are target-production topology, not included in this repository's deployed judge profile. Do not inject a product runtime key during image build.

## Repository map

`src/agentflight` contains the SDK, contracts, detectors, replay, API, adapters, storage, report export, and CLI. `apps/web` contains the React/TypeScript interface. `tests` contains unit, adapter, API, replay, and security tests. The four uppercase Markdown documents remain the governing product specifications.

Licensed under MIT.
