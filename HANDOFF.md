# CausalGate — Codex Implementation Handoff

## 1. Mission

Implement CausalGate as a working, testable intent-assurance tool for AI engineers and software factories. The product must produce an Intent Causal Record connecting a versioned intent contract to explicit plan and decision summaries, consequential actions, state, evidence, and outcomes; identify the first deterministic divergence; and replay the same scenario to issue an evidence-gated promotion decision. The demonstration must move from authorized research intent to the first unjustified decision, through the protected-data egress chain, and finally to a protected replay that restores intent alignment.

This product does not capture hidden chain-of-thought. Preserve that boundary in code, copy, screenshots, and submission materials. Only application-emitted decision summaries, alternatives, self-reported uncalibrated confidence, evidence references, and clause bindings may be described as captured reasoning context.

This repository is independent from AI Engineering Book Lab. Do not import its packages, schemas, fixtures, database, interface, copy, screenshots, or video assets. CausalGate is an investigation and verification product for engineers; it is not a learning platform.

## 2. Required reading order

Before changing code, read `PRD.md`, `ARCHITECTURE.md`, and `DETAIL-DESIGN.md` in full. Then inspect the repository, existing tests, environment files, and current implementation status. Treat the PRD as the product contract, the architecture as component and trust-boundary guidance, and the detailed design as the initial implementation specification. When documents conflict, preserve the core demonstration and security invariants, record the conflict, and propose the smallest resolution.

## 3. Product outcome

A developer must be able to instrument an agent, inspect the Intent Causal Record and its first divergence, replay the scenario under a candidate policy or code revision, and use the resulting promotion gate in local development, CI, or a software-factory pipeline. The hosted judge path works without signup and exposes the full deterministic journey without a key. Live GPT-5.6 Sol analysis is an explicit BYOK action. The local path works through Docker Compose.

## 4. Release scope

The shipped judge profile includes the Python SDK, explicit event API, tool wrapper, OpenAI Agents SDK adapter, LangGraph adapter, FastAPI control plane, SQLite profile, React/TypeScript dashboard, eight detector classes, 32 labeled scenarios, intent-based authorization, replay and comparison, CLI, CI threshold gate, evidence export, and benchmark report. Cloud SQL/PostgreSQL, a private Cloud Run analysis worker, Cloud Tasks, Cloud Storage, and tenant credential vaulting remain target-production topology.

The eight detectors cover protected-data egress, missing approval, unsafe tool chaining, instruction-source confusion, goal drift, privilege escalation, unsafe durable-state mutation, and unsupported completion claims. Every detector requires adversarial and benign or near-miss fixtures. No detector may be presented as validated because it works on one demonstration trace.

## 5. Model-access contract

Deterministic mode performs trace capture, explicit rules, policy evaluation, replay, comparison, reporting, and CI decisions without an API key. Recorded-analysis mode displays a redacted historical artifact tied to an exact fixture hash, prompt version, and integrity digest. Live-analysis mode requests GPT-5.6 Sol with medium reasoning only after a hosted judge supplies an ephemeral key or a self-hosted operator configures one server-side. Model output is untrusted structured data and cannot execute tools, issue grants, satisfy approval, change policy, invent evidence identifiers, suppress deterministic findings, or promote a release.

Do not commit an API key. Do not store a judge-supplied key, copy it into application state beyond the active request, expose it in logs, fixtures, traces, or exports, or describe ChatGPT or Codex allowances as API credit. Public deployment must not contain a shared OpenAI credential.

## 6. Security invariants

The demonstration uses only synthetic data and simulated outbound tools. Protected replay is deny-by-default. Trace events are append-only; corrections create new events. Secrets are redacted before persistence, model analysis, logs, and export. Replay cannot repeat an external side effect. Imported events and model outputs pass strict schema validation. Evidence identifiers cited by a finding must exist in the same execution. HTML is escaped, payload size is bounded, and test fixtures cannot escape their configured directories.

## 7. Implementation scope

The shipped implementation scope includes the synthetic research agent, event contracts, SDK, persistence, detector classes, vulnerable and protected runs, intent-based authorization, replay, evidence interface, framework adapters, live GPT-5.6 Sol and recorded historical model modes, labeled benchmark, investigation interface, CLI, CI gate, deterministic comparison, authenticated suite gate, exports, security checks, container packaging, and Cloud Run deployment configuration. Public deployment, rendered-browser validation, the video, and Devpost publication remain external submission tasks until evidence is recorded.

Do not add a detector without labeled fixtures or claim framework support without adapter contract tests. Every implemented capability must preserve a runnable product and recorded verification evidence.

## 8. Required verification

Maintain fast unit tests and release-level verification commands. `make verify-demo` runs the Python suite and both deterministic demonstration modes. `make verify-benchmark` publishes metrics for the exact labeled-suite version. `make verify-assurance` runs the authenticated suite gate with an explicit attestation key. `make verify-adapters` validates both framework adapters. `make verify-web` runs UI contracts, production build, and dependency audit. `make verify-clean` builds the container image. Recorded and live model analyses have separate verification commands; a public-deployment browser pass is recorded separately.

Measure setup completion, successful finding identification, replay determinism, evidence-citation validity, instrumentation overhead, CI consistency, and detector precision and recall on the labeled suite. Any future human study must report its sample size and limitations and must not be described as completed until evidence is committed.

## 9. Codex build record

Keep most core implementation in one primary Codex thread so the project has a defensible `/feedback` session ID. Maintain `docs/codex-build-log.md` with date, request, decisions, files changed, tests requested, tests run, failures discovered, human revisions, and accepted result. Commit at working checkpoints. Never state that Codex produced or tested something unless the session and repository evidence support the statement.

At the end of a work session, update the build log and a short status section containing completed behavior, current failing checks, decisions made, next task, and known risks. A new session must read this handoff, the three design documents, the build log, and the latest test output before implementation.

## 10. First prompt for a new Codex session

Use the following prompt from the repository root:

> Read HANDOFF.md, PRD.md, ARCHITECTURE.md, and DETAIL-DESIGN.md in full. Inspect the repository and tests. Summarize the current implementation against the release gates, identify contradictions or missing prerequisites, and propose the smallest complete vertical-slice plan. Do not write code until the plan names the files, acceptance tests, security invariants, and verification commands. After I approve the plan, implement the first working slice, run the relevant tests, and update docs/codex-build-log.md.

## 11. Definition of submission-ready

Repository-ready means the two adapters and 32 scenarios pass; detectors cite valid evidence; vulnerable and protected replays are reproducible; authorization and CI gates work; the historical recorded artifact is labeled; live analysis degrades safely; the benchmark is documented; and the repository has a license and complete README. Submission-ready additionally requires a clean Docker build, deployed no-signup URL, rendered-browser verification, public video, and published Devpost entry. External items must not be inferred from source files alone.
