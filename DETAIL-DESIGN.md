# CausalGate — Detailed Design

## 1. Repository layout

```text
causal-gate/
  src/causalgate/           API, SDK, contracts, detectors, authorization, replay, CLI
  apps/web/                  React and TypeScript dashboard
  evals/                     versioned benign and adversarial scenarios
  tests/                     unit, integration, security, adapter, and API tests
  artifacts/                 redacted, fixture-bound recorded model evidence
  scripts/                   release and model-analysis verification helpers
  docs/                      assurance specification and dated build record
  docker-compose.yml
  cloudbuild.yaml
  README.md
```

## 2. Event schema

Each event is represented by `TraceEventV1` with `event_id`, `execution_id`, `sequence`, `occurred_at`, `event_type`, `actor`, `parent_event_id`, `payload`, `redacted_payload`, `provenance`, `sensitivity`, `idempotency_key`, and `schema_version`. Event types are a closed enumeration. Payload schemas are discriminated by event type so a tool proposal cannot be confused with a completed tool execution.

Provenance contains source type, source identifier, content hash, and producing event. Sensitivity is an array drawn from `public`, `internal`, `personal`, `credential`, and `regulated`. Unknown payload keys are rejected on ingestion in strict mode.

`plan` and `decision` extend the event enumeration. A plan includes `summary`, `subgoal_id`, `intent_clause_ids`, and `evidence_event_ids`. A decision includes `decision`, `summary`, `alternatives_considered`, `confidence`, `intent_clause_ids`, and `evidence_event_ids`. The application supplies these fields at runtime. Confidence is labeled self-reported and uncalibrated and cannot affect a gate. CausalGate validates and displays the records but never claims they expose hidden model chain-of-thought. Payload schemas are allowlisted; unknown reasoning or metadata fields are rejected.

## 2.1 Intent Causal Record algorithm

1. Compile stable contract clauses for the goal, each allowed tool, prohibited outcome, protected resource, approval gate, and completion condition.
2. Validate event parent references and walk ancestry in sequence order.
3. Treat tool proposals, authorization-relevant state mutations, and final answers as consequential events.
4. Bind each consequential event to the contract clauses it advances or constrains.
5. Mark the earliest event `divergent` when an unauthorized tool or resource, missing approval, untrusted control ancestry, prohibited flow, or unsupported completion is observed.
6. Mark a consequential action `unbound` when no clause or validated decision record justifies it.
7. Calculate declaration coverage, behaviorally verified clause coverage, and consequential-action coverage separately. Report unknown clauses and unbound consequential actions; no coverage measure is a safety score.

The divergence frontier is deterministic for a fixed graph and verifier version. Semantic model analysis may add an explanation, but cannot create a causal edge, remove a frontier member, create a missing event, or change a verifier result.

## 3. SDK interface

The SDK exposes `start_execution(intent, policy_mode)`, `span(name, attributes)`, `record_retrieval(document)`, `propose_tool(name, arguments)`, `record_policy_decision(decision)`, `record_tool_result(result)`, `record_state_change(before, after)`, and `finish_execution(output, status)`. A `@trace_tool` decorator records proposals, decisions, results, timing, and exceptions. Context variables propagate execution and parent identifiers across asynchronous calls.

The quickstart target is three conceptual operations: configure a sink, start an execution around the existing agent call, and decorate or wrap tools. The SDK emits a local trace URL at completion. Configuration validation returns actionable field-level errors. Batching, retry, and shutdown behavior are deterministic, and an explicit `flush()` is available for command-line applications.

## 4. Intent contract generation

GPT-5.6 Sol with explicit medium reasoning receives the initial user request, a developer-supplied tool manifest, and a policy template. It returns a candidate `IntentContractV1`. The validator rejects unknown tool names, contradictory approval rules, absent goals, and resource references outside the manifest. A model-produced contract cannot issue authority: an authenticated human-confirmed endpoint must separately validate it and issue a signed grant.

An example contract permits `web_search` and `summarize`, prohibits disclosure of protected values, requires approval for `send_message`, and defines completion as a sourced summary. Policy evaluation uses explicit fields, while free-text rationale is displayed only for explanation.

## 5. Detector algorithms

`CG-EGRESS-001` fires when an outbound tool argument contains a token or hash-derived marker previously labeled protected. The demo uses synthetic canary values, enabling deterministic matching without sending a secret to a model.

`CG-APPROVAL-001` fires when a tool marked `approval_required` reaches execution without a preceding approved decision linked to the proposal event.

`CG-CHAIN-001` builds a per-execution data-flow graph from retrieval, state, and tool events. It fires when data flows from a protected source through a read-capable tool to an outbound tool and no policy decision breaks the path.

`CG-SOURCE-001` compares instruction provenance with the intent contract and flags control-like instructions originating from retrieved or tool-generated content when they influence a protected proposal.

`CG-GOAL-001` compares planned and executed goals with the versioned intent contract. Deterministic rules own the finding and gate result; optional GPT-5.6 Sol analysis can add evidence-linked semantic investigation without changing either.

`CG-PRIV-001` identifies a transition from a lower-privilege action or agent identity to a higher-privilege tool, resource, or delegated agent without a matching authorization event.

`CG-STATE-001` tracks untrusted data entering durable memory or authorization-relevant state and fires when later decisions consume it without validation or provenance constraints.

`CG-COMPLETE-001` compares completion claims with required completion conditions and evidence events. It flags a claimed result when required tool results, validations, or output artifacts are absent.

The optional GPT-5.6 Sol investigator receives a minimized redacted trace projection and the intent contract. Its output includes `finding_type`, `summary`, `reasoning_summary`, `severity`, `confidence`, `evidence_event_ids`, and `recommended_control`. Strict schema validation and evidence-ID validation reject unsupported output. Model findings remain separate from deterministic authorization and promotion decisions.

## 6. Policy evaluation

`authorize(request, signed_grant, runtime_context)` returns `allow`, `deny`, or `require_approval`. A closed ontology first normalizes tool, action, resource, data, destination, and effects. Evaluation verifies grant integrity and execution binding, then intersects identity, purpose, tool/action, resource, data class, destination, organizational prohibitions, sensitive data flow, untrusted provenance, tool budget, delegation depth, and exact-action approval. An allow result carries a signed 30-second permit bound to the complete request and grant digests; the mediated adapter consumes its nonce once immediately before execution. Baseline demo mode records the same decision in observe-only mode but allows only the synthetic simulator to continue. Protected mode enforces it. Approval never creates permission, and child grants must monotonically attenuate parent authority.

## 7. Replay design

A replay fixture is a version-controlled YAML or JSON file containing the user request, injected document, tool catalog, simulated results, expected vulnerable outcome, and expected protected outcome. Replay creates a new execution, copies no sensitive runtime payloads, fixes time and random seed where needed, and disables network access in tool adapters. A comparison service aligns events by semantic step rather than sequence number and reports changed decisions, calls, findings, and final outcomes.

The comparison service creates a fixture-scoped `PromotionGate`. Its recommendation requires an exact fixture-digest link, no detected candidate divergence, no new deterministic rules, behavior-specific satisfied evidence for every baseline-divergent clause, and no unbound candidate consequential action. The separate authenticated suite gate requires multiple fixtures, signed provenance, a content-addressed verifier, exact manifest parity, all fixture checks, and a preregistered Wilson lower bound. Application assertions count as observed, never satisfied. Neither gate permits a model to edit or deploy production code autonomously or certifies general production safety.

## 8. API contract

`POST /api/v1/executions` creates a run. `POST /api/v1/executions/{id}/events` appends an event. `POST /api/v1/executions/{id}/complete` seals the trace. `GET /api/v1/executions/{id}` returns the run. `GET /api/v1/executions/{id}/intent-causal-record` returns clauses, versioned evaluations, bindings, causal provenance, coverage measures, and the divergence frontier. `GET /api/v1/assurance-suite` executes the authenticated synthetic multi-fixture gate. Other endpoints provide optional semantic analysis, fixture comparison, benchmark evidence, and report export.

All mutation endpoints accept an idempotency key. Errors use a stable envelope with code, message, correlation identifier, and field details. Raw secret fields are never returned unless the local demo explicitly enables a synthetic-data reveal toggle.

## 9. User interface

The runs page shows status, policy mode, start time, finding count, and risk. The execution page places the intent contract beside a vertical event timeline. Finding selection filters and highlights evidence. The replay control offers baseline and protected modes. The comparison page shows intent, policy decisions, tool calls, and outcomes in aligned columns. A report action downloads the evidence package.

## 10. Test design

Unit tests validate schemas, redaction, each detector, authorization precedence, signed grants, exact-action approvals, single-use permits, evidence verification, and comparison alignment. Integration tests execute vulnerable and protected fixtures through the API and SQLite store. Contract tests mock GPT-5.6 Sol structured responses, including invalid evidence and provider failures. CLI and API tests confirm seeded egress in observe-only baseline mode, denial in protected mode, report export, and the authenticated suite gate.

## 11. Definition of done

The repository implementation is complete when clean-checkout setup succeeds, automated tests pass, both adapters emit valid traces, all 32 benchmark scenarios run, every detector has adversarial and benign evidence, replay modes work, CI thresholds behave deterministically, model failure degrades safely, reports export, and the README covers installation, supported platforms, testing, architecture, Codex usage, GPT-5.6 Sol usage, limitations, and licensing. Public Cloud Run deployment, rendered-browser verification against that URL, the demo video, and the final Devpost entry are separate submission operations and must not be implied by repository code alone.

## 12. Judge test script

The hosted landing page exposes `Run vulnerable scenario`, `Inspect evidence`, and `Replay with protection` as the primary actions. The vulnerable action resets and executes the seeded fixture. The evidence action opens `CG-CHAIN-001`, highlights the retrieved injection, protected read, missing approval, and outbound proposal, and shows their immutable identifiers. The replay action runs the identical fixture hash under protected policy and displays the denied outbound action. A copyable verification command returns the fixture hash, detector assertions, and test status.

The local path is `docker compose up --build`, followed by `http://localhost:8080`. `make verify-demo` runs the Python suite plus the baseline and protected CLI scenarios without a model key. `make verify-live-analysis` performs the optional live GPT-5.6 Sol structured-output test when the runtime environment explicitly enables it and supplies a key.

## 13. Requirement-to-evidence matrix

| Requirement | Implementation evidence | Demo or test evidence |
| --- | --- | --- |
| FR-1 and FR-5 | Typed event schemas, ingestion route, timeline components | Timeline contains every seeded event in sequence |
| FR-2 and FR-4 | Intent schema, prompt version, structured-output validator | Contract and cited semantic finding use valid identifiers |
| FR-3 | Eight deterministic detector classes | Labeled adversarial and near-miss fixtures exercise every class |
| FR-6 | Fixture loader, simulator adapters, comparison service | Same fixture hash produces different policy outcome |
| FR-7 | Markdown and JSON serializers | Export contains contract, evidence, decision, and comparison |
| FR-8 | Synthetic research-agent package | Clean judge environment runs without external tools |
| FR-9 | SDK package, manual calls, decorators, adapter examples | New example emits a valid trace through the documented integration |
| FR-10 | CLI commands and CI workflow | Seeded critical scenario returns the configured failing status |
| FR-11 | At least 30 labeled fixtures and benchmark runner | Versioned precision, recall, citation, overhead, and replay metrics publish |
| FR-12 | Finding workflow fields and evidence package | A mitigation is assigned, compared, and exported without altering trace evidence |

## 14. Codex contribution ledger

Each material component records task statement, Codex session, affected files, tests requested, tests run, human changes, and accepted result in `docs/codex-build-log.md`. A release check rejects an empty ledger or an entry without verification. This ledger supplies concrete evidence for technological implementation while keeping authorship claims accurate.

## 15. Product-state acceptance tests

Automated UI contract tests cover the primary judge copy and controls, responsive and accessible styling invariants, Intent Causal Record, complete mediation, signed grant and single-use permit language, GPT-5.6 Sol boundaries, and the promotion gate. TypeScript and the production Vite build are verified separately. Rendered-browser interaction against a public deployment remains an explicit external release check; it is not claimed by source-level UI contract tests.

SDK experience tests install the package in a clean example environment, execute the minimal integration, verify the printed trace URL, and confirm that a recorder outage produces the documented fail-open result. Protocol tests prove that a second sink and a test detector can be implemented without importing private modules.

## 16. Implementation scope

The shipped implementation includes the fixture, event contracts, SDK, SQLite persistence, eight detector classes, intent authorizer, replay, framework adapters, live GPT-5.6 Sol and recorded legacy-model modes, labeled benchmark, React investigation experience, CLI and CI thresholds, evidence exports, deterministic comparison, authenticated suite gate, security tests, container packaging, and Cloud Run deployment configuration. It does not claim a completed public deployment, human usability pilot, or rendered-browser run.

Direct event calls remain supported, but the packaged SDK, CLI, and adapters are release requirements. Additional detectors are accepted only with labeled adversarial and benign fixtures.

## 17. Release verification commands

`make verify-demo` runs the Python test suite and both deterministic demonstration modes. `make verify-benchmark` evaluates all labeled scenarios. `make verify-assurance` runs the authenticated multi-fixture promotion suite when an attestation key is supplied. `make verify-adapters` runs framework contract tests. `make verify-web` installs the locked frontend dependencies, runs UI contract tests, builds production assets, and audits high-severity dependencies. `make verify-clean` builds the container image. `make verify-recorded-analysis` validates the stored legacy-model artifact against its fixture hash and schema. `make verify-live-analysis` makes an authorized live call only when runtime configuration is present. `make verify-release` composes the keyless and attested release checks; rendered-browser and public-deployment checks remain external.
