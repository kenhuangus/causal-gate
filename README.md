# CausalGate

**Intent assurance and intent-based access control for AI agents.**

CausalGate shows AI engineers not only *what* an agent did, but **which declared intent authorized each consequential action, where behavior first diverged, whether the action should have been allowed, and whether a proposed fix is safe to promote**.

It combines an evidence-linked Intent Causal Record, deterministic intent-based access control, counterfactual replay, an authenticated software-factory promotion gate, and an optional GPT-5.6 Sol investigator in one runnable developer tool.

> Track: **Developer Tools** · Built for **OpenAI Build Week** · Python 3.11+ · React · FastAPI · OpenAI Responses API

## Why judges should care

| Judging criterion | Evidence in the project |
|---|---|
| **Technological implementation** | A working SDK, API, closed authorization ontology, signed grants and approvals, single-use permits, causal conformance engine, eight detectors, replay system, authenticated release gate, OpenAI integration, CLI, CI, and adversarial tests—not a mocked prototype |
| **Design** | One coherent judge journey from seeded incident to authorization decision, causal divergence, evidence inspection, protected replay, and promotion verdict, with responsive and accessible states |
| **Potential impact** | Gives AI engineers and software factories a practical control plane for answering whether an agent action was authorized by user intent and whether a repair is ready to ship |
| **Quality of the idea** | Moves beyond trace viewing by making intent executable: signed least-privilege authority before action, causal-minimal divergence after action, and evidence-gated improvement before release |

## Judge quick path

The complete deterministic demonstration runs without an account, external service, real secret, or OpenAI API key.

### One-command local launch

Windows PowerShell:

```powershell
git clone https://github.com/kenhuangus/causal-gate.git
Set-Location causal-gate
powershell -ExecutionPolicy Bypass -File .\scripts\local\run-windows.ps1
```

macOS or Linux:

```bash
git clone https://github.com/kenhuangus/causal-gate.git
cd causal-gate
./scripts/local/run-macos-linux.sh
```

The launchers generate CausalGate's local signing secrets in a git-ignored file, build the container, wait for health, and open `http://localhost:8080`. They do not request or store an OpenAI key.

### Manual Docker launch

```bash
git clone https://github.com/kenhuangus/causal-gate.git
cd causal-gate
export CAUSALGATE_ATTESTATION_KEY="$(openssl rand -hex 32)"
docker compose up --build --wait
```

Open [http://localhost:8080](http://localhost:8080), then:

1. Select **Run vulnerable scenario**.
2. Inspect the **Intent-Based Access Control** record and **Intent Causal Record**.
3. Follow the causal frontier from untrusted retrieval to protected read and simulated egress.
4. Select **Replay with protection**.
5. Inspect the same fixture under enforcement and the evidence-gated promotion verdict.

Stop the application with:

```bash
docker compose down
```

The demo uses a synthetic canary and simulated tools. It performs no external retrieval or outbound action.

For Windows, macOS, Linux, Google Cloud Run, and AWS App Runner instructions, see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Python SDK quickstart

The repository ships an alpha Python SDK for local capture, intent enforcement, redacted JSON-lines export, private API export, OpenAI Agents SDK tracing, and LangGraph node instrumentation. Until the first PyPI release, install it from a checkout:

```bash
pip install .
python examples/basic_sdk.py
```

```python
from causalgate import IntentContract, start_execution, trace_tool

@trace_tool("lookup")
async def lookup(*, query: str):
    return {"answer": query}

intent = IntentContract(goal="Research public data.", allowed_tools=["lookup"])
with start_execution(intent) as recorder:
    result = recorder.finish_execution("complete")
```

The default SDK performs no network or model call. See [the complete SDK guide](docs/SDK.md) for sinks, fail-open/fail-closed behavior, async instrumentation, and framework integration examples.

## Why this project exists

Agent observability platforms are excellent at collecting spans, prompts, latency, token usage, tool calls, and model outputs. Those traces answer:

> What happened?

AI engineers still have to answer harder questions manually:

- Did this tool call serve the user's approved purpose?
- Which intent clause authorized access to this resource and destination?
- Did untrusted content redirect the agent into a new objective?
- Where is the earliest causal point at which behavior stopped conforming?
- Can a candidate repair be promoted without introducing another intent regression?
- Can authorization remain deterministic even when a model helps interpret intent?

CausalGate is built around those questions. It treats intent as an executable, reviewable security boundary rather than another trace attribute.

## What CausalGate does

### 1. Builds an Intent Causal Record

An `IntentContract` becomes a canonical set of versioned clauses covering the goal, tools, protected resources, approval gates, prohibited effects, and completion conditions. CausalGate binds recorded plans, application-provided decision summaries, tool proposals, results, state changes, and final answers to those clauses.

The record separates three measurements that are often incorrectly collapsed into one score:

- **Declaration coverage:** the application claimed a relationship.
- **Verified coverage:** a deterministic verifier found behavior-specific evidence.
- **Consequential-action coverage:** effectful actions have explicit clause bindings.

CausalGate does not claim access to hidden chain-of-thought. Decision summaries, alternatives, confidence, evidence references, and clause references are explicit application records. Confidence is labeled self-reported and uncalibrated.

### 2. Finds the causal-minimal divergence frontier

Executions are treated as causal graphs, not merely timestamped lists. Parent, evidence, and declared predecessor edges establish a partial order. CausalGate returns every detected violating event that has no earlier violating causal ancestor.

That matters for parallel agents: two incomparable failures remain two frontier events instead of being forced into a misleading single “first” event.

### 3. Enforces intent-based access control

CausalGate ships a closed, versioned authorization ontology. Every mapped effectful tool is normalized into:

`action + resource type + data class + destination + effects`

Human-approved contracts become short-lived, signed intent grants. Runtime authority is the deterministic intersection:

```text
identity ∩ agent ∩ signed intent grant ∩ organization policy ∩ runtime context
```

The authorizer returns `allow`, `deny`, or `require_approval`. An allowed request receives a short-lived permit bound to the exact request and grant digests. The mediated executor consumes the permit once, immediately before the tool call.

Implemented protections include:

- closed-ontology and default-deny behavior;
- contract, ontology, execution, purpose, subject, and expiry binding;
- HMAC-signed grants and exact-action approvals;
- tool, action, resource, data-class, destination, and effect constraints;
- sensitive-data egress and untrusted-provenance controls;
- tool-call budgets and delegation-depth limits;
- monotonic child-grant attenuation;
- argument-mutation and permit-replay rejection; and
- complete-mediation evidence for the shipped mapped-tool adapter profile.

Approval is conjunctive: it can add a restriction but can never create authority that is absent from the grant.

### 4. Replays the failure under a candidate control

The bundled fixture contains an indirect prompt injection that asks the agent to read a protected synthetic canary and send it externally.

- **Baseline:** deterministic authorization records the denials in observe-only mode while the simulator preserves the unsafe counterfactual.
- **Protected replay:** the same fixture hash runs under enforcement; the protected read and outbound action are blocked.

The comparison shows changed decisions, restored clauses, resolved rules, blocked tools, coverage regressions, and unbound consequential actions.

### 5. Gates software-factory promotion with evidence

A coding agent may consume a failure record and propose a code or policy change. It cannot approve its own work.

The fixture gate requires exact replay linkage, fixture parity, restored intent clauses, no new deterministic finding, non-regressing coverage, and no unbound candidate action. The separate authenticated suite gate additionally binds:

- the fixture manifest;
- verifier source and dependency digests;
- source revision, detector version, and policy version;
- runner identity and HMAC attestation;
- minimum task-family and action-channel diversity; and
- a preregistered 95% Wilson lower-bound threshold.

The bundled authenticated suite currently contains 12 content-addressed fixtures across four task families and three action channels. A passing result is a scoped promotion recommendation, not a general production-safety certificate.

### 6. Uses GPT-5.6 Sol without giving the model authority

The optional OpenAI path uses the Responses API with `gpt-5.6-sol`, explicit medium reasoning, strict JSON Schema output, bounded retries, sanitized failures, and rate limiting.

GPT-5.6 Sol has two bounded roles:

1. **Intent compiler:** converts natural language into a least-privilege candidate contract. Unknown ontology terms are removed and ambiguity forces clarification.
2. **Semantic investigator:** analyzes a minimized, redacted trace for semantic intent drift and prompt-injection influence, citing only event IDs from that execution.

Model output cannot issue a grant, satisfy human approval, execute a tool, suppress deterministic findings, change policy, or promote a release. The UI records requested and resolved model identifiers and clearly distinguishes live from recorded analysis.

## Why it is different

| Conventional agent observability | CausalGate |
|---|---|
| Records prompts, spans, outputs, and tool calls | Connects consequential actions to canonical intent clauses |
| Uses time order as the primary investigation view | Reconstructs recorded causal provenance and preserves concurrent divergence |
| Explains a failure after it happens | Enforces signed intent before a mapped effectful tool executes |
| Treats approval as a workflow event | Cryptographically binds approval to the exact grant, execution, tool, and arguments |
| Compares traces and metrics | Tests whether a control restores intent without detected regression |
| Produces evaluation scores | Produces authenticated, content-addressed release evidence with uncertainty bounds |
| Lets an LLM interpret behavior | Uses the model as an untrusted proposer and investigator; deterministic code owns authority |

CausalGate is designed to complement tracing systems, not replace them. Existing OpenAI Agents SDK and LangGraph applications can normalize their events through the included adapters.

## Architecture

```text
User-approved task
       │
       ▼
IntentContract ──► human approval ──► signed IntentGrant
       │                                  │
       ▼                                  ▼
instrumented agent ──► tool proposal ──► deterministic authorizer
       │                                  │
       │                       deny / require approval / permit
       │                                  │
       ▼                                  ▼
append-only trace ◄──────────── mediated tool execution
       │
       ├──► Intent Causal Record + divergence frontier
       ├──► deterministic security findings
       ├──► optional GPT-5.6 Sol semantic investigation
       └──► fixture replay ──► authenticated promotion gate
```

The shipped judge profile is a single FastAPI and React container with SQLite. It is intentionally small, reproducible, and safe to expose with synthetic data. The documented production extension replaces the process-local permit ledger with an atomic shared store and adds workload identity, private workers, durable storage, and workspace authorization.

## Demonstrated security conditions

The baseline fixture exercises eight evidence-linked detector classes:

| Rule | Condition |
|---|---|
| `CG-EGRESS-001` | Protected data proposed for egress |
| `CG-APPROVAL-001` | Required approval missing |
| `CG-CHAIN-001` | Unsafe read-to-send tool chain |
| `CG-SOURCE-001` | Untrusted instructions influence control flow |
| `CG-GOAL-001` | Behavior departs from the declared goal or tools |
| `CG-PRIV-001` | Unauthorized protected-resource or privilege transition |
| `CG-STATE-001` | Untrusted input mutates authorization-relevant state |
| `CG-COMPLETE-001` | Completion is claimed without required evidence |

Every finding cites validated event identifiers from its own execution.

## Run locally without Docker

### Prerequisites

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Node.js 22 and npm
- OpenSSL for generating a local assurance key

Install dependencies and build the web application:

```bash
git clone https://github.com/kenhuangus/causal-gate.git
cd causal-gate
make install
cd apps/web
npm run build
cd ../..
```

Start CausalGate:

```bash
export CAUSALGATE_ATTESTATION_KEY="$(openssl rand -hex 32)"
UV_CACHE_DIR=/tmp/causalgate-uv-cache uv run --isolated \
  uvicorn causalgate.api:app --host 0.0.0.0 --port 8080
```

Open [http://localhost:8080](http://localhost:8080). Stop the server with `Ctrl+C`.

## Optional GPT-5.6 Sol analysis with your own key

The entire deterministic judge journey works without OpenAI access. Live semantic investigation is deliberately opt-in and uses the judge's or end user's own OpenAI project key.

### Hosted judge path: ephemeral BYOK

1. Run the vulnerable scenario without a key.
2. Open **Optional · Bring Your Own Key**.
3. Paste a restricted OpenAI project key.
4. Select **Investigate with GPT-5.6 Sol**.

The browser sends the key once in the `X-OpenAI-API-Key` request header over same-origin HTTPS. CausalGate uses it for that provider request, does not persist it, and clears the input immediately. Use a restricted project key with a small budget and rotate it after testing. Do not use this flow on a deployment you do not trust.

### Self-hosted path: server environment

For local or private deployment, keep the key out of the browser and supply it as a server runtime environment variable:

```bash
export OPENAI_API_KEY="your-runtime-key"
export OPENAI_MODEL="gpt-5.6-sol"
export CAUSALGATE_LIVE_ANALYSIS_ENABLED=true
export CAUSALGATE_LIVE_ANALYSIS_LIMIT=3
export CAUSALGATE_ATTESTATION_KEY="$(openssl rand -hex 32)"

docker compose up --build --wait
```

The key is read only by the server. It is not used during the image build, embedded in the browser bundle, written to traces, or committed to the repository. The public `cloudbuild.yaml` intentionally deploys no shared OpenAI credential.

In the UI, run the baseline and select **Investigate with GPT-5.6 Sol**.

To exercise the same live semantic-analysis path from the CLI without replacing the submitted artifact:

```bash
UV_CACHE_DIR=/tmp/causalgate-uv-cache uv run --isolated \
  causalgate record-analysis --output /tmp/causalgate-live-analysis.json
```

To compile a natural-language request into a non-authoritative candidate contract:

```bash
curl --fail-with-body \
  --request POST http://localhost:8080/api/v1/intent/compile/live \
  --header 'Content-Type: application/json' \
  --header 'X-OpenAI-API-Key: YOUR_RESTRICTED_PROJECT_KEY' \
  --data '{"request":"Research Acme using public sources and produce a local cited summary."}'
```

The production multi-tenant roadmap, tenant isolation boundary, credential-vault option, pricing model, and abuse controls are documented in [`docs/SAAS-BYOK.md`](docs/SAAS-BYOK.md).

## CLI-only judge test

The deterministic scenario can be verified without starting the web server:

```bash
UV_CACHE_DIR=/tmp/causalgate-uv-cache uv run --isolated causalgate verify-demo
```

Expected summary:

```json
{
  "passed": true,
  "baseline_findings": 8,
  "protected_findings": 0
}
```

Run an individual scenario:

```bash
# Baseline intentionally exits non-zero because it contains critical findings.
UV_CACHE_DIR=/tmp/causalgate-uv-cache uv run --isolated causalgate demo --mode baseline

# Protected mode exits zero.
UV_CACHE_DIR=/tmp/causalgate-uv-cache uv run --isolated causalgate demo --mode protected
```

## Verification and reproducibility

Run the complete release verification:

```bash
export CAUSALGATE_ATTESTATION_KEY="$(openssl rand -hex 32)"
make verify-release
```

Or run each layer independently:

```bash
make verify-demo                 # Python, API, policy, replay, and security tests
make verify-benchmark            # 32 labeled deterministic scenarios
make verify-assurance            # authenticated 12-fixture promotion suite
make verify-adapters             # framework adapter contract tests
make verify-recorded-analysis    # fixture and artifact integrity
make verify-web                  # UI tests, production build, and npm audit
```

Verified repository evidence at the time of this README revision:

- 63 Python tests passing;
- 9 judge-UI contract tests passing;
- production TypeScript and Vite build passing;
- zero npm production-audit vulnerabilities;
- 32 unique labeled benchmark scenarios with reproducible output;
- 16 true positives, 16 true negatives, zero false positives, and zero false negatives in the synthetic corpus; and
- authenticated 12-fixture gate passing with a 95% Wilson lower bound of 75.8% against a preregistered 70% threshold.

These measurements describe the included synthetic regression evidence only. They do not establish production detector accuracy.

## API highlights

| Method and path | Purpose |
|---|---|
| `POST /api/v1/demo/baseline` | Run the synthetic observe-only incident |
| `POST /api/v1/demo/protected` | Run the enforced counterfactual replay |
| `GET /api/v1/executions/{id}/intent-causal-record` | Retrieve clause bindings and divergence frontier |
| `GET /api/v1/executions/{id}/authorization-record` | Retrieve intent-authorization evidence |
| `GET /api/v1/authorization/ontology` | Inspect the closed ontology version and digest |
| `GET /api/v1/comparisons/{left}/{right}` | Compare replay outcomes and promotion evidence |
| `POST /api/v1/executions/{id}/analyze/live` | Run bounded GPT-5.6 Sol semantic analysis |
| `POST /api/v1/intent/compile/live` | Produce a candidate intent contract |
| `GET /api/v1/benchmark` | Run the labeled detector benchmark |
| `GET /api/v1/assurance-suite` | Run the authenticated multi-fixture gate |
| `GET /api/docs` | OpenAPI documentation |

Public demo mode exposes only synthetic, fixture-scoped records. General ingestion and signed-grant issuance require private mode and an administrator token.

## Google Cloud Run deployment

The included `cloudbuild.yaml` builds the container, pushes it to Artifact Registry, and deploys one public synthetic judge service. It injects only CausalGate's attestation and grant-signing secrets. There is no platform-funded or shared OpenAI key; judges bring their own key only when they explicitly request live analysis.

Set the project and region:

```bash
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"
gcloud config set project "$PROJECT_ID"
```

Enable services and create the runtime identity:

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com

gcloud artifacts repositories create causalgate \
  --repository-format=docker \
  --location="$REGION"

gcloud iam service-accounts create causalgate-web \
  --display-name="CausalGate judge runtime"
```

Create the two CausalGate runtime secrets:

```bash
openssl rand -hex 32 | \
  gcloud secrets create causalgate-attestation-key --data-file=-

openssl rand -hex 32 | \
  gcloud secrets create causalgate-grant-signing-key --data-file=-
```

Allow the Cloud Run identity to read only those secrets:

```bash
for SECRET in \
  causalgate-attestation-key \
  causalgate-grant-signing-key
do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --member="serviceAccount:causalgate-web@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
done
```

Submit the build:

```bash
gcloud builds submit \
  --config cloudbuild.yaml \
  --substitutions="_REGION=${REGION}"
```

Retrieve the public URL:

```bash
gcloud run services describe causal-gate \
  --region="$REGION" \
  --format='value(status.url)'
```

Cloud Build and Cloud Run service-account permissions must be granted according to the policies of the target GCP organization. No OpenAI API key is required or accepted as a Docker build argument or shared Cloud Run secret.

## Supported platforms

- Linux
- macOS
- Windows through Docker Desktop or WSL2
- Google Cloud Run
- Python 3.11+
- Current Chromium, Firefox, and Safari-class browsers
- OpenAI Agents SDK and LangGraph through the included normalization adapters

The shipped SQLite and process-local permit-ledger profile is intended for the judge demo and local developer workflows. Multi-instance production deployment requires a shared database or atomic nonce store and real workload identity.

## Codex collaboration and human decisions

Codex was used as an engineering collaborator across schemas, deterministic authorization, causal analysis, replay, API routes, React UI, adversarial tests, documentation, packaging, and deployment configuration. The dated record is in [`docs/codex-build-log.md`](docs/codex-build-log.md), with commit history providing the corresponding repository evidence.

Codex accelerated implementation and review, but did not own the product boundary. Key human-directed decisions included:

- positioning CausalGate as intent assurance rather than another observability dashboard;
- refusing to claim hidden chain-of-thought capture;
- keeping authorization and promotion deterministic;
- treating GPT-5.6 Sol output as untrusted candidate evidence;
- separating declaration coverage from verified behavioral coverage;
- retaining all causal-minimal concurrent divergences;
- requiring exact-action approval and single-use permits; and
- scoping benchmark and promotion claims to their actual evidence.

GPT-5.6 Sol is also a meaningful runtime component: it compiles candidate intent and performs evidence-linked semantic investigation. It is deliberately prevented from granting itself authority.

OpenAI Build Week requires the README to explain how Codex and GPT-5.6 Sol contributed, and evaluates technological implementation, design, potential impact, and quality of the idea equally. See the [official rules](https://openai.devpost.com/rules).

## Security and scientific claim boundary

CausalGate provides deterministic conformance evidence for declared contracts and recorded events. It does not recover latent human intent, inspect private chain-of-thought, prove detector completeness, certify philosophical causation, replace a SIEM, or establish general production safety.

The trusted computing base includes the contract source, host identity binding, recorder, ontology, mediated adapters, authorizer, storage validation, verifier implementation, fixture corpus, runner, signing-key custody, and human release authority.

Known scale boundaries are disclosed in the API authorization record and [`docs/ASSURANCE-SPEC.md`](docs/ASSURANCE-SPEC.md). General scientific validation would require independently annotated real-world traces, held-out evaluation, inter-reviewer agreement, distribution-shift testing, calibration studies, and external replication.

## Repository map

```text
src/causalgate/             Python SDK, API, authorization, analysis, replay
apps/web/                    React and TypeScript judge interface
tests/                       Unit, adversarial, API, replay, and adapter tests
evals/                       Versioned assurance fixtures
artifacts/                   Integrity-checked recorded analysis
docs/ASSURANCE-SPEC.md       Formal definitions and claim boundaries
docs/SAAS-BYOK.md             SaaS, tenant isolation, and BYOK architecture
docs/codex-build-log.md      Codex collaboration evidence
PRD.md                       Product requirements
ARCHITECTURE.md              System and trust-boundary architecture
DETAIL-DESIGN.md             Component-level behavior
HANDOFF.md                   Implementation and submission handoff
cloudbuild.yaml              Google Cloud build and deployment
```

## License

CausalGate is released under the permissive **MIT License**. See [`LICENSE`](LICENSE).

The OpenAI Build Week rules require a public repository to include relevant licensing but do not mandate a specific license. MIT makes the inspection and testing rights clear while preserving the required copyright and warranty notice. Third-party dependencies remain governed by their respective licenses and terms.

---

**CausalGate: trace what happened, prove where intent diverged, enforce what may happen next.**
