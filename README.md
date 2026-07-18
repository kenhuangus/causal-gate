# AgentFlight Recorder

AgentFlight Recorder turns a tool-using AI-agent run into an **Intent Flight Record**: versioned contract-conformance evidence connecting declared intent to explicit plans, application-provided decision summaries, tool calls, state changes, and outcomes. It returns the causal-minimal frontier of detected contract violations, then evaluates a candidate control through fixture replay and an authenticated multi-fixture promotion suite.

This is not another trace viewer. Traces answer what happened; AgentFlight answers which intent clause authorized an action, where that authorization chain first broke, and whether a candidate change restored the intended behavior without a detected regression. The included judge path is deterministic, uses synthetic data, makes no network calls, and requires no OpenAI API key.

AgentFlight never claims access to hidden model chain-of-thought. `plan` and `decision` events are explicit records emitted by the application: concise rationale summaries, considered alternatives, self-reported uncalibrated confidence, cited evidence events, and referenced intent clauses. They are inspectable engineering artifacts, not private model reasoning.

## Judge quickstart

```bash
AGENTFLIGHT_ATTESTATION_KEY=$(openssl rand -hex 32) docker compose up --build --wait
```

Open `http://localhost:8080`, select **Run vulnerable scenario**, inspect the first divergence in the Intent Flight Record, then select **Replay with protection**. The baseline run seeds eight documented security conditions. The protected replay uses the same fixture hash, blocks the unauthorized read before synthetic data can reach the simulated outbound tool, and produces an evidence-gated promotion decision.

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
AGENTFLIGHT_ATTESTATION_KEY='replace-with-at-least-32-random-bytes' make verify-assurance
make verify-adapters
AGENTFLIGHT_ATTESTATION_KEY='replace-with-at-least-32-random-bytes' make verify-release
```

`make verify-demo` runs the Python tests and end-to-end CLI assertion. `make verify-release` adds the benchmark, authenticated assurance suite, adapters, recorded artifact, and production frontend checks. The 32-case labeled benchmark consists of two target-rule-positive and two target-rule-negative variants per detector; a target-rule-negative trace may still contain other seeded violations. Results include two-sided 95% Wilson intervals and apply only to this synthetic suite.

## SDK integration

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
AGENTFLIGHT_ATTESTATION_KEY='replace-with-at-least-32-random-bytes' uv run agentflight assurance-suite
```

The GitHub Actions workflow executes the complete keyless verification path. It has read-only repository permissions and receives no product runtime key.

## Architecture

The FastAPI service serves both the versioned API and the React investigation interface. SQLite provides a zero-configuration local profile. Cloud Run can deploy the same container; Cloud SQL and a private worker are the documented scale-out path. Trace capture, redaction, deterministic analysis, replay, report export, and adapters are separate modules with strict Pydantic contracts.

The eight rules are protected-data egress, missing approval, unsafe tool chaining, instruction-source confusion, goal drift, privilege escalation, unsafe authorization-state mutation, and unsupported completion. Every finding cites event identifiers validated against its execution.

The intent-analysis layer compiles each contract into full canonical SHA-256 clause identifiers, emits versioned clause evaluations, reconstructs recorded causal provenance, and returns separate declaration, verified-behavior, and action coverage plus a causal-minimal divergence frontier. Baseline-versus-candidate comparison is useful in an AI-engineering or software-factory loop:

`intent contract → versioned evaluation → causal frontier → candidate control → fixture replay → authenticated suite gate`

The gate is deliberately conservative: model-generated explanations or code changes cannot promote themselves. A fixture replay produces only a scoped recommendation. The software-factory gate additionally requires a signed fixture manifest, content-addressed verifier artifact, minimum fixture diversity, all replay checks, and a preregistered lower confidence bound. Neither result is a general production-safety certification.

The formal semantics, trusted-computing-base boundary, statistical protocol, and claim limitations are specified in [`docs/ASSURANCE-SPEC.md`](docs/ASSURANCE-SPEC.md).

## Security model

The demonstration contains no real secret, external retrieval, or outbound side effect. Baseline mode is explicitly observational; protected mode is deny-by-default. Event payloads have a separate redacted representation, byte-accurate bounds, same-run parent checks, and immutable idempotency keys. Model output, when added, must remain untrusted structured data and cannot suppress deterministic findings or execute tools. `.env*` files are ignored except `.env.example`.

Public deployments run with `AGENTFLIGHT_DEMO_MODE=true`. In this mode anonymous users can run the synthetic scenarios and access only execution identifiers created by those actions; list, create, append, and complete APIs are disabled, guessed identifiers return 404, request streams are capped, and demo actions are rate-limited. Public demo retention is bounded to 64 execution records with a one-hour TTL; insertion and pruning share the same store transaction, and expired identifiers lose access. Private developer ingestion requires `AGENTFLIGHT_DEMO_MODE=false` plus a server-side `AGENTFLIGHT_ADMIN_TOKEN`; creation, retrieval, reporting, comparison, and live analysis all require that token in this profile. This token is not a substitute for production workspace identity and authorization.

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
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
gcloud artifacts repositories create agentflight --repository-format=docker --location=us-central1
openssl rand -hex 32 | gcloud secrets create agentflight-attestation-key --data-file=-
gcloud secrets add-iam-policy-binding agentflight-attestation-key --member="serviceAccount:agentflight-web@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
gcloud builds submit --config cloudbuild.yaml
```

Cloud Build tags the image with its always-populated build ID, so the same configuration works for manual submissions and repository-triggered builds.

The configuration exposes only the synthetic judge service. Cloud SQL, a private worker, Secret Manager, long-term production retention, and authenticated workspaces are target-production topology, not included in this repository's deployed judge profile. Do not inject a product runtime key during image build.

## Repository map

`src/agentflight` contains the SDK, contracts, detectors, replay, API, adapters, storage, report export, and CLI. `apps/web` contains the React/TypeScript interface. `tests` contains unit, adapter, API, replay, and security tests. The four uppercase Markdown documents remain the governing product specifications.

Licensed under MIT.
