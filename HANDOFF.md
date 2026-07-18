# AgentFlight Recorder — Codex Implementation Handoff

## 1. Mission

Implement AgentFlight Recorder as a working, testable Developer Tools submission for OpenAI Build Week. The product records tool-using agent executions, reconstructs evidence-linked security failures, compares behavior with a versioned intent contract, and replays the same scenario after a policy change. The demonstration must move from an authorized research task to a detected protected-data egress path, then to a protected replay that blocks the action.

This repository is independent from AI Engineering Book Lab. Do not import its packages, schemas, fixtures, database, interface, copy, screenshots, or video assets. AgentFlight Recorder is an investigation and verification product for engineers; it is not a learning platform.

## 2. Required reading order

Before changing code, read `PRD.md`, `ARCHITECTURE.md`, and `DETAIL-DESIGN.md` in full. Then inspect the repository, existing tests, environment files, and current implementation status. Treat the PRD as the product contract, the architecture as component and trust-boundary guidance, and the detailed design as the initial implementation specification. When documents conflict, preserve the core demonstration and security invariants, record the conflict, and propose the smallest resolution.

## 3. Product outcome

A developer must be able to instrument an agent in under five minutes, run or import a trace, inspect a finding linked to immutable event evidence, replay the scenario under a changed policy, and use the same result as a local CLI or CI security gate. The hosted judge path must work without signup. The local path must work through Docker Compose. A deterministic keyless mode must remain functional when OpenAI Platform access is unavailable.

## 4. Release scope

The shipped judge profile includes the Python SDK, explicit event API, tool wrapper, OpenAI Agents SDK adapter, LangGraph adapter, FastAPI control plane, SQLite profile, React/TypeScript dashboard, eight detector classes, 32 labeled scenarios, replay and comparison, CLI, CI threshold gate, evidence export, mitigation workflow, and benchmark report. Cloud SQL/PostgreSQL, a private Cloud Run analysis worker, Cloud Tasks, Cloud Storage, Secret Manager, and a Cloud Run benchmark job remain target-production topology rather than shipped services.

The eight detectors cover protected-data egress, missing approval, unsafe tool chaining, instruction-source confusion, goal drift, privilege escalation, unsafe durable-state mutation, and unsupported completion claims. Every detector requires adversarial and benign or near-miss fixtures. No detector may be presented as validated because it works on one demonstration trace.

## 5. Model-access contract

Deterministic mode performs trace capture, explicit rules, policy evaluation, replay, comparison, reporting, and CI decisions without an API key. Recorded-analysis mode displays redacted GPT-5.6 results committed as artifacts and tied to exact fixture hashes, prompt versions, and validation results. Live-analysis mode is enabled only when a server-side OpenAI Platform key is configured. The interface must always identify the active mode. Model output is untrusted structured data and cannot execute tools, change policy, invent evidence identifiers, or suppress deterministic findings.

Do not commit an API key. Do not expose a server key to the browser, sample agent, logs, fixtures, or exported report. Do not describe ChatGPT or Codex usage allowances as API credit.

## 6. Security invariants

The demonstration uses only synthetic data and simulated outbound tools. Protected replay is deny-by-default. Trace events are append-only; corrections create new events. Secrets are redacted before persistence, model analysis, logs, and export. Replay cannot repeat an external side effect. Imported events and model outputs pass strict schema validation. Evidence identifiers cited by a finding must exist in the same execution. HTML is escaped, payload size is bounded, and test fixtures cannot escape their configured directories.

## 7. Implementation scope

The implementation scope includes the synthetic research agent, event contracts, SDK, persistence, detector classes, vulnerable and protected runs, replay, evidence interface, framework adapters, live and recorded GPT-5.6 modes, labeled benchmark, investigation interface, CLI, CI gate, mitigation workflow, comparison, exports, pilot validation, performance and security checks, deployment, and frozen submission evidence.

Do not add a detector without labeled fixtures or claim framework support without adapter contract tests. Every implemented capability must preserve a runnable product and recorded verification evidence.

## 8. Required verification

Maintain fast unit tests and release-level verification commands. `make verify-demo` must run both demonstration modes, required detector assertions, redaction, comparison, CI thresholds, and page smoke tests. `make verify-benchmark` must publish metrics for the exact labeled-suite version. `make verify-adapters` must validate both framework adapters. `make verify-clean` must build the complete container stack and the SQLite quickstart from clean state. Recorded and live model analyses require separate verification commands.

Measure setup time, time to first finding, replay determinism, evidence-citation validity, instrumentation overhead, CI consistency, detector precision and recall on the labeled suite, and pilot task completion. Report sample sizes and limitations.

## 9. Codex build record

Keep most core implementation in one primary Codex thread so the project has a defensible `/feedback` session ID. Maintain `docs/codex-build-log.md` with date, request, decisions, files changed, tests requested, tests run, failures discovered, human revisions, and accepted result. Commit at working checkpoints. Never state that Codex produced or tested something unless the session and repository evidence support the statement.

At the end of a work session, update the build log and a short status section containing completed behavior, current failing checks, decisions made, next task, and known risks. A new session must read this handoff, the three design documents, the build log, and the latest test output before implementation.

## 10. First prompt for a new Codex session

Use the following prompt from the repository root:

> Read HANDOFF.md, PRD.md, ARCHITECTURE.md, and DETAIL-DESIGN.md in full. Inspect the repository and tests. Summarize the current implementation against the release gates, identify contradictions or missing prerequisites, and propose the smallest complete vertical-slice plan. Do not write code until the plan names the files, acceptance tests, security invariants, and verification commands. After I approve the plan, implement the first working slice, run the relevant tests, and update docs/codex-build-log.md.

## 11. Definition of submission-ready

Submission-ready means the hosted no-signup demonstration and clean Docker path work; the two adapters and 32 scenarios pass; detectors cite valid evidence; vulnerable and protected replays are reproducible; CI thresholds work; the recorded GPT-5.6 artifact is labeled; live analysis degrades safely; the five-engineer pilot and benchmark are documented; the repository has a license and complete README; the public video is under three minutes with voiceover; and the Devpost entry includes the correct repository, judge test path, category, and primary `/feedback` session ID.
