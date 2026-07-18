# AgentFlight Recorder — Detailed Design

## 1. Repository layout

```text
agentflight-recorder/
  apps/api/                 FastAPI application and routes
  apps/web/                 React and TypeScript dashboard
  packages/recorder/        tracing SDK and decorators
  packages/contracts/       Pydantic domain schemas
  packages/detectors/       deterministic and semantic detection rules
  packages/policy/          runtime authorization checks
  packages/replay/          fixtures and simulated tools
  examples/research_agent/  vulnerable and protected demo
  benchmark/scenarios/      labeled benign and adversarial fixtures
  integrations/             OpenAI Agents SDK and LangGraph adapters
  tests/                    unit, integration, benchmark, and end-to-end tests
  docs/                     screenshots and demo narrative
  docker-compose.yml
  README.md
```

## 2. Event schema

Each event is represented by `TraceEventV1` with `event_id`, `execution_id`, `sequence`, `occurred_at`, `event_type`, `actor`, `parent_event_id`, `payload`, `redacted_payload`, `provenance`, `sensitivity`, `idempotency_key`, and `schema_version`. Event types are a closed enumeration. Payload schemas are discriminated by event type so a tool proposal cannot be confused with a completed tool execution.

Provenance contains source type, source identifier, content hash, and producing event. Sensitivity is an array drawn from `public`, `internal`, `personal`, `credential`, and `regulated`. Unknown payload keys are rejected on ingestion in strict mode.

`plan` and `decision` extend the event enumeration. A plan includes `summary`, `subgoal_id`, `intent_clause_ids`, and `evidence_event_ids`. A decision includes `decision`, `summary`, `alternatives_considered`, `confidence`, `intent_clause_ids`, and `evidence_event_ids`. The application supplies these summaries at runtime. AgentFlight validates and displays them but never claims they expose hidden model chain-of-thought. Their payload schemas are allowlisted; unknown reasoning or metadata fields are rejected.

## 2.1 Intent Flight Record algorithm

1. Compile stable contract clauses for the goal, each allowed tool, prohibited outcome, protected resource, approval gate, and completion condition.
2. Validate event parent references and walk ancestry in sequence order.
3. Treat tool proposals, authorization-relevant state mutations, and final answers as consequential events.
4. Bind each consequential event to the contract clauses it advances or constrains.
5. Mark the earliest event `divergent` when an unauthorized tool or resource, missing approval, untrusted control ancestry, prohibited flow, or unsupported completion is observed.
6. Mark a consequential action `unbound` when no clause or validated decision record justifies it.
7. Calculate intent-clause coverage as clauses with at least one validated binding divided by all compiled contract clauses. Report unbound consequential actions separately; coverage is not a safety score.

The first divergence is deterministic and evidence-linked. Semantic model analysis may add an explanation, but it cannot move the divergence point, create a missing event, or change an aligned/divergent verdict.

## 3. SDK interface

The SDK exposes `start_execution(intent, policy_mode)`, `span(name, attributes)`, `record_retrieval(document)`, `propose_tool(name, arguments)`, `record_policy_decision(decision)`, `record_tool_result(result)`, `record_state_change(before, after)`, and `finish_execution(output, status)`. A `@trace_tool` decorator records proposals, decisions, results, timing, and exceptions. Context variables propagate execution and parent identifiers across asynchronous calls.

The quickstart target is three conceptual operations: configure a sink, start an execution around the existing agent call, and decorate or wrap tools. The SDK emits a local trace URL at completion. Configuration validation returns actionable field-level errors. Batching, retry, and shutdown behavior are deterministic, and an explicit `flush()` is available for command-line applications.

## 4. Intent contract generation

GPT-5.6 receives the initial user request, a developer-supplied tool manifest, and a policy template. It returns `IntentContractV1`. The validator rejects unknown tool names, contradictory approval rules, absent goals, and resource references outside the manifest. The initial contract is immutable; changes create a new version with a reason and author.

An example contract permits `web_search` and `summarize`, prohibits disclosure of protected values, requires approval for `send_message`, and defines completion as a sourced summary. Policy evaluation uses explicit fields, while free-text rationale is displayed only for explanation.

## 5. Detector algorithms

`AFR-EGRESS-001` fires when an outbound tool argument contains a token or hash-derived marker previously labeled protected. The demo uses synthetic canary values, enabling deterministic matching without sending a secret to a model.

`AFR-APPROVAL-001` fires when a tool marked `approval_required` reaches execution without a preceding approved decision linked to the proposal event.

`AFR-CHAIN-001` builds a per-execution data-flow graph from retrieval, state, and tool events. It fires when data flows from a protected source through a read-capable tool to an outbound tool and no policy decision breaks the path.

`AFR-SOURCE-001` compares instruction provenance with the intent contract and flags control-like instructions originating from retrieved or tool-generated content when they influence a protected proposal.

`AFR-GOAL-001` compares planned and executed goals with the versioned intent contract. It uses explicit goal and tool boundaries first and invokes GPT-5.6 only for semantically ambiguous divergence.

`AFR-PRIV-001` identifies a transition from a lower-privilege action or agent identity to a higher-privilege tool, resource, or delegated agent without a matching authorization event.

`AFR-STATE-001` tracks untrusted data entering durable memory or authorization-relevant state and fires when later decisions consume it without validation or provenance constraints.

`AFR-COMPLETE-001` compares completion claims with required completion conditions and evidence events. It flags a claimed result when required tool results, validations, or output artifacts are absent.

The GPT-5.6 detector receives event summaries and the intent contract. Its output includes `finding_type`, `summary`, `reasoning_summary`, `severity`, `confidence`, `evidence_event_ids`, and `recommended_control`. The postprocessor removes nonexistent evidence identifiers, downgrades unsupported findings to unverified, and merges overlap using detector type and evidence set.

## 6. Policy evaluation

`evaluate(proposal, contract, trace_context)` returns `allow`, `deny`, or `require_approval`. Evaluation order is prohibited outcome, resource boundary, tool authorization, approval rule, data-flow rule, then default deny. Baseline demo mode records the decision that protected mode would make but allows the simulator to continue. The interface labels this mode as observational.

## 7. Replay design

A replay fixture is a version-controlled YAML or JSON file containing the user request, injected document, tool catalog, simulated results, expected vulnerable outcome, and expected protected outcome. Replay creates a new execution, copies no sensitive runtime payloads, fixes time and random seed where needed, and disables network access in tool adapters. A comparison service aligns events by semantic step rather than sequence number and reports changed decisions, calls, findings, and final outcomes.

The comparison service also creates a `PromotionGate`. `promote` requires an exact recorded fixture-digest link, no candidate first divergence, no new deterministic rules, behavior-specific satisfied evidence for every baseline-divergent clause, and no unbound candidate consequential action. Application-asserted clause IDs count as observed, not satisfied. Any failed condition yields `hold` with machine-readable regressions. This result is suitable for a CI check or software-factory promotion stage; it is not permission for a model to edit or deploy production code autonomously.

## 8. API contract

`POST /api/v1/executions` creates a run. `POST /api/v1/executions/{id}/events` appends an event. `POST /api/v1/executions/{id}/complete` seals the trace. `GET /api/v1/executions/{id}` returns the run. `GET /api/v1/executions/{id}/intent-flight-record` returns clauses, bindings, the causal chain, explicit decision records, coverage, and first divergence. `POST /api/v1/executions/{id}/analyze/live` runs optional semantic analysis. `GET /api/v1/comparisons/{left}/{right}` returns changed decisions, resolved findings, and the promotion gate. `GET /api/v1/executions/{id}/report` exports Markdown or JSON.

All mutation endpoints accept an idempotency key. Errors use a stable envelope with code, message, correlation identifier, and field details. Raw secret fields are never returned unless the local demo explicitly enables a synthetic-data reveal toggle.

## 9. User interface

The runs page shows status, policy mode, start time, finding count, and risk. The execution page places the intent contract beside a vertical event timeline. Finding selection filters and highlights evidence. The replay control offers baseline and protected modes. The comparison page shows intent, policy decisions, tool calls, and outcomes in aligned columns. A report action downloads the evidence package.

## 10. Test design

Unit tests validate all schemas, redaction, each detector, policy precedence, evidence verification, and comparison alignment. Integration tests execute the vulnerable and protected fixtures through the API and database. Contract tests mock GPT-5.6 structured responses, including invalid JSON, nonexistent evidence, and timeouts. The end-to-end test starts the bundled agent, confirms seeded egress in baseline mode, confirms denial in protected mode, and verifies the exported report.

## 11. Definition of done

The submission target is complete when clean-checkout setup succeeds, automated tests pass, the public Cloud Run demo uses synthetic data, any future private worker and benchmark job use least-privilege service accounts, both adapters emit valid traces, all 32 benchmark scenarios run, every detector has adversarial and benign evidence, replay modes work, CI thresholds behave deterministically, findings support mitigation workflow, model failure degrades safely, reports export, the five-engineer pilot is documented, and the README covers installation, supported platforms, testing, architecture, Codex usage, GPT-5.6 usage, limitations, and licensing.

## 12. Judge test script

The hosted landing page exposes `Run vulnerable scenario`, `Inspect evidence`, and `Replay with protection` as the primary actions. The vulnerable action resets and executes the seeded fixture. The evidence action opens `AFR-CHAIN-001`, highlights the retrieved injection, protected read, missing approval, and outbound proposal, and shows their immutable identifiers. The replay action runs the identical fixture hash under protected policy and displays the denied outbound action. A copyable verification command returns the fixture hash, detector assertions, and test status.

The local path is `docker compose up --wait`, followed by the printed application URL. `make verify-demo` runs the baseline and protected scenarios without a model key and checks expected findings. `make verify-gpt` optionally performs the live GPT-5.6 structured-output test when a key is configured.

## 13. Requirement-to-evidence matrix

| Requirement | Implementation evidence | Demo or test evidence |
| --- | --- | --- |
| FR-1 and FR-5 | Typed event schemas, ingestion route, timeline components | Timeline contains every seeded event in sequence |
| FR-2 and FR-4 | Intent schema, prompt version, structured-output validator | Contract and cited semantic finding use valid identifiers |
| FR-3 | Three deterministic detector modules | Seeded attack activates all expected assertions |
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

Browser tests cover first run, empty run list, baseline run, partial trace, deterministic-only analysis, live GPT-5.6 analysis, protected replay, failed replay, finding assignment, mitigation comparison, CI policy explanation, benchmark summary, and report export. The primary journey contains no mandatory form beyond the initial task. A reset action restores the fixture in one interaction. Keyboard focus, color-independent severity indicators, and readable event labels are required for the demonstrated screens.

SDK experience tests install the package in a clean example environment, execute the minimal integration, verify the printed trace URL, and confirm that a recorder outage produces the documented fail-open result. Protocol tests prove that a second sink and a test detector can be implemented without importing private modules.

## 16. Implementation scope

The implementation includes the fixture, event contracts, SDK, persistence, eight detector classes, replay, framework adapters, live and recorded GPT-5.6 modes, the labeled benchmark, the React investigation experience, CLI and CI thresholds, evidence exports, assignments, mitigation comparison, usability validation, security testing, deployment, and frozen submission artifacts.

Direct event calls remain supported, but the packaged SDK, CLI, and adapters are release requirements. Additional detectors are accepted only with labeled adversarial and benign fixtures.

## 17. Release verification commands

`make verify-demo` runs schema tests, both demonstration modes, detector assertions, comparison assertions, redaction checks, CI thresholds, and page smoke tests. `make verify-benchmark` evaluates all labeled scenarios and publishes versioned metrics. `make verify-adapters` runs framework contract suites. `make verify-clean` builds and starts the complete container stack and separately checks the SQLite quickstart. `make verify-recorded-analysis` validates stored GPT-5.6 artifacts against fixture hashes and schemas. `make verify-live-analysis` runs when a key is configured and otherwise reports a clear skip.
