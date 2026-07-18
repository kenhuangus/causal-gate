# AgentFlight Recorder — Product Requirements Document

## 1. Product summary

AgentFlight Recorder is an intent-assurance tool for AI engineers and software factories. It converts an agent execution into an Intent Flight Record that binds a declared intent contract to explicit plans, application-provided decision summaries, tool calls, state mutations, approvals, evidence, and outcomes. It deterministically identifies the first consequential event whose authorization chain diverges from the contract, then replays the same fixture and issues a promotion decision for a candidate control.

The hackathon submission targets the Developer Tools category. The submission supports OpenAI Agents SDK and LangGraph integrations, an intentionally vulnerable demonstration agent, eight detector classes, a hosted dashboard, CLI and CI workflows, a local Docker fallback, and repeatable attack–detect–repair–verify demonstrations.

## 1.1 Track fit and one-sentence value proposition

AgentFlight Recorder fits the Developer Tools objective because it closes the loop between agent debugging and safe improvement. Its value proposition is: **prove where an agent first departed from declared intent, then prove a revision restores that intent before promotion**. The submission shall describe it as an intent-assurance and change-verification instrument, not as a general monitoring dashboard or a security standard.

## 2. Problem

Agent traces usually show what happened but do not establish why a consequential action was believed to be authorized, which clause of the user's intent justified it, or where that justification first became invalid. Developers must manually correlate prompts, retrieved content, explicit decisions, state, tools, approvals, and outcomes. A software factory has an additional problem: even after generating a fix, it needs evidence that the revision restored intent alignment without introducing a regression.

## 3. Target users

The primary user is an AI engineer building tool-using agents. Secondary users are application-security engineers, red-teamers, platform engineers, and reviewers who need evidence from an agent incident without reading raw logs.

## 4. Goals and non-goals

The release must capture complete execution traces, make them understandable, detect eight security conditions, generate evidence-grounded findings, replay recorded scenarios, demonstrate that mitigations change outcomes, and operate as both a local development tool and CI security gate. It must offer a testing path that does not require judges to rebuild the project.

The release will not provide a production SIEM, autonomous remediation in production, uncontrolled self-modification, universal framework support, or formal compliance certification. It does not capture or reconstruct hidden chain-of-thought. It records only application-emitted plan and decision summaries and treats them as untrusted evidence. AIVSS and MAESTRO mappings are explanatory metadata, not certification claims.

## 5. Core user journey

The developer installs the tracing package or runs the bundled sample agent. The developer enters an authorized task such as researching a vendor and summarizing public information. A retrieved document contains an adversarial instruction directing the agent to read a protected local value and transmit it through an outbound tool. The recorder captures each event. The dashboard displays the original intent, execution timeline, data lineage, tool chain, and findings. The developer enables a proposed policy control and replays the same scenario. The second run blocks the unauthorized action, and the dashboard compares both outcomes.

## 6. Functional requirements

### FR-1 Trace capture

The SDK shall create an execution with a unique identifier and record timestamped events for user intent, model request, model response, retrieved content, tool proposal, policy decision, approval, tool execution, state mutation, error, and final answer. Each event shall include a schema version, parent event, actor, provenance, sensitivity labels, and redacted payload representation.

### FR-2 Intent contract

The system shall convert the initial request and optional developer policy into a structured intent contract containing allowed goals, prohibited outcomes, authorized tools, protected resources, approval gates, and completion conditions. The contract shall remain versioned and visible in the report.

### FR-3 Deterministic detectors

The release shall implement detectors for protected-data egress, missing approval, unsafe tool chaining, instruction-source confusion, goal or intent drift, privilege escalation, untrusted memory or state mutation, and unsupported completion claims. Each detector shall emit a finding with rule identifier, severity, evidence event identifiers, explanation, and recommended control. At least the first three detectors shall be fully deterministic; semantic detectors shall combine explicit rules with validated GPT-5.6 analysis.

### FR-4 GPT-5.6 analysis

When Platform access is configured, GPT-5.6 shall evaluate the trace and intent contract for intent divergence and prompt-injection influence. The model must return schema-validated JSON and cite only event identifiers present in the trace. Unsupported claims shall be rejected or marked as unverified. The submitted repository shall include one redacted analysis artifact generated during development, its schema-validation result, prompt version, and referenced fixture hash. The keyless judge path shall label this artifact as recorded and shall never imply that it is a live call.

### FR-5 Timeline and evidence view

The dashboard shall display runs, events, tool calls, policy decisions, findings, and an evidence panel. Selecting a finding shall highlight the referenced events. Secrets shall be masked by default.

### FR-6 Replay

The system shall replay the bundled scenario from a fixture with deterministic tool responses. A user shall be able to select baseline or protected policy mode and compare results without accessing external systems.

### FR-7 Report export

The system shall export a Markdown or JSON incident report containing the intent contract, attack path, findings, evidence references, control recommendation, and replay comparison.

### FR-8 Sample integration

The repository shall contain a vulnerable research agent with a retrieval tool, protected-file tool, and outbound-message tool. All tools shall operate on synthetic local data.

### FR-9 Developer integration

The SDK shall support a minimal integration path consisting of package installation, recorder initialization, and wrapping existing tool functions. The quickstart shall produce a visible trace without requiring a developer to rewrite agent control flow. Framework-specific adapters are optional; the stable event contract and manual SDK path are required.

### FR-10 CLI and CI security gate

The command-line interface shall run a scenario suite, analyze imported traces, compare a candidate run with a baseline, export reports, and return a nonzero status when configured severity or policy thresholds are exceeded. A documented GitHub Actions workflow shall demonstrate pull-request gating without requiring the hosted dashboard.

### FR-11 Security benchmark suite

The repository shall include at least thirty synthetic, versioned scenarios across the eight detector classes, including target-rule-negative near-miss cases. A target-rule-negative trace may retain violations for other detector classes. The benchmark runner shall report per-rule precision and recall on labeled fixtures, replay determinism, runtime overhead, and GPT-5.6 evidence-citation validity. Results shall identify fixture count and version and shall not be generalized beyond the included suite.

### FR-12 Team investigation workflow

Users shall be able to assign a finding status, add a mitigation note, compare policy versions, and export a shareable evidence package. The release may use a single workspace and lightweight local identities; full enterprise identity management is outside scope.

### FR-13 Intent Flight Record

The system shall compile the intent contract into stable clause identifiers and bind consequential events to one or more clauses. The record shall include the causal chain, explicit plan and decision records, intent coverage, unbound consequential actions, the first divergence event, and a human-readable divergence reason. Parent ancestry and evidence identifiers must resolve within the same execution.

### FR-14 Explicit decision records

Applications may emit `plan` and `decision` events containing a concise rationale summary, alternatives considered, confidence, cited evidence-event identifiers, and referenced intent-clause identifiers. These fields shall be labeled as application-provided summaries. The product shall never describe them as hidden model reasoning or chain-of-thought, and missing summaries shall not be synthesized as if observed.

### FR-15 Evidence-gated improvement

Comparison shall treat a protected or revised run as a promotion candidate. The candidate may receive `promote` only when it uses the identical fixture, has no first intent divergence, introduces no deterministic findings, and resolves the baseline's divergent clauses. Otherwise the verdict is `hold`, with cited reasons and regression evidence. Model analysis may propose or explain a change but cannot issue the promotion verdict.

## 7. Security and privacy requirements

Tool execution shall be deny-by-default in protected mode. The demo shall never access real credentials, personal data, email, or external messaging. Stored payloads shall pass through configurable redaction. Model analysis shall receive the minimum necessary trace fields. All model-produced findings shall be treated as untrusted structured data and validated before display. Replay shall use fixtures and shall not repeat external side effects.

## 8. Success metrics

The demo is successful when the baseline run completes, applicable detectors identify seeded violations, GPT-5.6 analysis links conclusions to valid evidence events, protected mode blocks egress, replay shows the changed outcome, and the same scenario fails a configured CI policy check. Setup must work from the documented command, and the principal dashboard path must load reliably on the included fixture. Automated tests should cover event schemas, detectors, redaction, structured model output, framework adapters, CLI behavior, CI thresholds, and replay isolation.

The product-impact hypothesis is that AgentFlight Recorder helps an AI engineer identify the first policy-divergent event and verify a mitigation without manually correlating raw prompts, logs, and tool records. The evaluation shall measure successful finding identification, detector precision and recall on the labeled suite, evidence-citation validity, replay reproducibility, instrumentation overhead, CI decision consistency, and setup completion. A small pilot with at least five AI engineers shall record task completion and structured usability feedback. These prototype measurements shall not be presented as production performance claims.

## 8.1 Judging-criteria proof plan

| Criterion | Evidence the submission must show | Target |
| --- | --- | --- |
| Technological Implementation | Instrumented agent, typed append-only trace, deterministic data-flow rules, validated GPT-5.6 analysis, policy enforcement, and replay | One end-to-end fixture plus automated tests for every security rule |
| Design | A coherent task-to-finding-to-replay journey with progressive disclosure and synthetic data | A judge completes the primary journey without documentation |
| Potential Impact | Named AI-engineer and security-engineer audience, measurable investigation workflow, and exportable evidence | Time-to-first-finding and mitigation-verification measurements included |
| Quality of the Idea | Intent-to-action evidence graph plus counterfactual replay, rather than generic logging or model-only classification | Demo visibly distinguishes trace display, causal evidence, and control verification |

## 8.2 Codex build-evidence requirements

The repository shall maintain `docs/codex-build-log.md` with dated engineering tasks, decisions, generated or revised components, tests created, defects discovered, and human verification. Commits shall reference the relevant build-log entry. The primary `/feedback` session shall contain the implementation of the trace schema, at least one detector, the replay path, and their tests. The submission shall show genuine collaboration and review, not claim that unverified generated code is an achievement.

## 9. Acceptance criteria

The project is accepted for submission when a judge can open a hosted demo or run one documented command, execute both baseline and protected scenarios, inspect at least one evidence-linked finding, export a report, and reproduce the result using sample data. The repository must include a license, architecture overview, setup instructions, test command, sample output, supported platform statement, and a section explaining how Codex and GPT-5.6 were used.

## 10. Release priorities

The release priorities are a complete instrumented scenario, evidence-linked detection, protected replay, benchmark verification, a coherent investigation interface, CLI and CI enforcement, report export, security validation, and a stable judge environment. Each capability must remain independently testable and supported by repository evidence.

## 11. Hackathon demonstration

The video opens with the authorized task, runs the vulnerable agent, and shows the unexpected protected-data egress. It then opens the finding, follows the evidence chain from retrieved injection to tool proposal and outbound call, enables the policy, and replays the same input. The protected run blocks the action and produces a comparison report. The narration identifies which code and tests Codex produced and where GPT-5.6 performs intent-contract and trace analysis.

The video should cover the problem and audience, baseline run, evidence path, protected replay, measurable result, and Codex and GPT-5.6 implementation evidence. The recording shall prioritize the working interface over architecture slides.

## 12. Panel-informed product review

The named panel and public professional profiles suggest several relevant review perspectives. These are product-design inferences, not predictions of individual scores.

| Judge | Publicly visible perspective | Resulting product decision |
| --- | --- | --- |
| Thibault Sottiaux, Head of Product & Platform | Product/platform leadership spanning Codex and broader agent experiences | Present a complete workflow with a stable SDK boundary and credible path beyond the demo |
| Kath Korevec, Member of Product Staff | Developer tools, developer experience, product craft, and prior work across Heroku, GitHub, Vercel, and Google Labs | Make first value fast, error states useful, setup observable, and integration reversible |
| Tara Seshan, Member of Product Staff | Product building across scaled operational products and agent workflows | Show a real investigation job with a decision and verified outcome, not a dashboard tour |
| Leah Belsky, VP of Education | Access, AI literacy, education, and workforce learning | Make the evidence chain understandable to engineers learning secure agent design, without turning this entry into an education product |
| Peter Steinberger, Member of Technical Staff | Hands-on open-source agent building, high-velocity shipping, and practical personal agents | Deliver runnable code, a useful agent scenario, small integration surface, and inspectable implementation |

The panel review sets the priority order to: reliable hosted journey, evidence-linked replay, documented SDK integration, testable open repository, CI usefulness, benchmark evidence, and then breadth of detector and framework support. Feature count never substitutes for a coherent product experience.

## 13. Review sources

The panel names and roles are published on the [OpenAI Build Week page](https://openai.devpost.com/). Product emphasis was informed by [Kath Korevec's description of her developer-product work](https://kathykorevec.substack.com/about), [Tara Seshan's public profile](https://www.linkedin.com/in/tarstarr), [Leah Belsky's education profile](https://asugsvsummit.com/speakers/leah-belsky), a [profile of Thibault Sottiaux's product responsibilities](https://www.wired.com/story/model-behavior-interview-with-openai-codex-lead-tibo-sottiaux), and [Peter Steinberger's discussion of building with Codex](https://www.linkedin.com/posts/romainhuet_excited-to-share-this-conversation-with-peter-activity-7432440027667812352-zL1H). The documents use these sources only to identify plausible evaluation perspectives.

## 13.1 Competitive boundary

This positioning is based on current official product documentation, not a claim that competing platforms cannot be extended.

| Product | Officially documented center of gravity | AgentFlight's deliberately narrower differentiation |
| --- | --- | --- |
| [LangSmith Observability](https://docs.langchain.com/langsmith/observability) | Trace visibility, production metrics, dashboards, and agent debugging | Stable intent-clause bindings, a deterministic first authorization divergence, and an evidence-gated revision verdict |
| [Langfuse Observability](https://langfuse.com/docs/observability/overview) | Full request lifecycle, tool and retrieval relationships, sessions, cost, latency, and attributes | An intent proof that requires every consequential action to justify itself against the declared contract |
| [Arize Phoenix Tracing](https://arize.com/docs/phoenix/tracing/concepts-tracing/what-are-traces) | LLM, tool, agent, and chain spans plus evaluation and trace analysis | A software-factory control loop that turns the first divergence and same-fixture replay into `promote` or `hold` |

AgentFlight should integrate with or ingest conventional traces rather than compete on telemetry breadth. Its novelty claim rests on the contract-to-decision-to-action proof and conservative promotion gate. If those artifacts are absent, the product has fallen back to ordinary observability and has missed its product objective.

## 14. Scope and release gates

| Gate | Required outcome |
| --- | --- |
| Vertical product | One instrumented agent, vulnerable and protected runs, persisted trace, first finding, and replay visible end to end |
| Detection platform | Eight detector classes, thirty-scenario labeled suite, live and recorded GPT-5.6 paths, and two adapters with contract tests |
| Developer experience | Dashboard, CLI, CI gate, evidence export, mitigation workflow, hosted reset, and Docker fallback |
| Validation and submission | Engineer pilot, benchmark report, performance and security checks, documentation, public repository, stable demo, and video |

Every gate requires a deployable vertical product. Experimental production integrations, enterprise SSO, automatic code remediation, and detector claims without fixtures remain excluded.

## 15. Separation from AI Engineering Book Lab

AgentFlight Recorder and AI Engineering Book Lab shall be submitted as separate repositories with no shared application package, database, user interface, demo fixture, video, or product description. AgentFlight Recorder's user is an engineer investigating an executed agent; its input is a trace; its central operation is causal incident analysis and replay; and its output is a security evidence report. Book Lab's user is a learner completing a coding task; its input is learner code; its central operation is isolated evaluation and progressive instruction; and its output is learning evidence and a mastery record. The shared subject of agent security is domain context, not a shared product implementation.

## 16. Submission release gates

The project cannot be marked submission-ready unless the hosted reset works in a clean browser, the Docker path works from a clean checkout, the vulnerable and protected fixture assertions pass, the demo contains no real secret or external side effect, the recorded GPT-5.6 artifact is labeled, the build log matches commits, the repository has a license, the public video is complete, and the Devpost submission is not left in draft state.
