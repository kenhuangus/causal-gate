# AgentFlight intent-assurance thesis

## Product claim

AgentFlight is not differentiated by recording spans. Its product primitive is the **Intent Flight Record**: an evidence object that answers whether every consequential action remained justified by a declared intent contract.

The minimum useful record connects:

`intent clause → explicit plan → application-provided decision summary → evidence → tool action → state change → outcome`

The analyzer identifies the earliest event where that justification becomes invalid or absent. A same-fixture replay then decides whether a candidate revision restored the affected clauses without introducing a detected regression.

## What “reasoning capture” means

AgentFlight does not access, reconstruct, or claim hidden model chain-of-thought. An instrumented application may record a compact decision artifact with:

- the decision or selected action;
- a concise rationale summary intended for inspection;
- alternatives considered;
- confidence;
- evidence-event identifiers;
- intent-clause identifiers.

These fields are untrusted observations. AgentFlight validates their references and compares them with behavior. A plausible rationale does not override contradictory tool or state evidence, and absence of a record remains absence rather than being filled in by a model.

## Why this matters to an AI engineer

Traditional debugging begins with a failure and asks which prompt, tool, or span produced it. Intent assurance begins with the authorized objective and asks where the execution lost its justification. That changes the engineering unit from a trace span to a testable contract-to-action claim.

The developer receives:

1. a stable intent clause that was violated;
2. the first divergent event rather than only the final incident;
3. the causal ancestors and explicit decision record available at that point;
4. a concrete control recommendation;
5. a replay result for the identical fixture;
6. a machine-readable `promote` or `hold` verdict.

This can shorten the loop from incident to regression test because the evidence package already names the contract, divergence, fixture, and expected restoration.

## Software-factory control loop

An AI software factory can use AgentFlight as an independent promotion stage:

1. A runtime or evaluation failure produces an Intent Flight Record.
2. A coding agent receives the bounded failure record and proposes a code, prompt, tool-policy, or contract change.
3. The candidate runs in a sandbox against the same fixture and the broader regression suite.
4. AgentFlight recomputes intent bindings and the first divergence.
5. The promotion gate checks fixture parity, restored clauses, candidate divergence, and new deterministic findings.
6. Passing changes may proceed to the next delivery gate; failing changes return an evidence package for another revision.

This is recursive improvement with an external evidence gate, not uncontrolled recursive self-modification. The generator and the verifier have different authority: a model may suggest a change, while deterministic policy and test evidence decide whether it advances.

## Promotion semantics

`promote` requires all of the following:

- baseline and candidate carry the same recorded fixture digest and the candidate's replay link names that digest;
- the candidate has no first deterministic intent divergence;
- the candidate introduces no deterministic finding absent from the baseline;
- the clauses implicated in the baseline are restored;
- evidence references resolve inside their respective executions.

Otherwise the verdict is `hold`. The gate reports missing conditions and regressions rather than collapsing them into a score.

The prototype proves these semantics on a synthetic prompt-injection fixture. It does not establish that an untested production revision is safe, that the detector set is complete, or that a passing fixture authorizes deployment.

## Competitive boundary

Current official documentation positions [LangSmith](https://docs.langchain.com/langsmith/observability) around trace visibility and production observability, [Langfuse](https://langfuse.com/docs/observability/overview) around the full LLM request lifecycle and causal trace relationships, and [Arize Phoenix](https://arize.com/docs/phoenix/tracing/concepts-tracing/what-are-traces) around LLM/tool/agent spans, analysis, and evaluation. Those products provide valuable telemetry that AgentFlight can ingest or complement.

AgentFlight's deliberately narrow novelty claim is not better span collection. It is the combination of stable intent clauses, explicit decision artifacts, deterministic first-divergence analysis, and a same-fixture promotion gate. If AgentFlight only displays traces and findings, it is not meaningfully differentiated.

## Design invariants

- Behavior outranks rationale: a decision summary cannot make an unauthorized action authorized.
- Missing evidence stays missing: no synthetic explanation is presented as observed reasoning.
- Earliest cause over loudest symptom: the first divergence is ordered by the recorded causal execution, not finding severity.
- Same-fixture proof: a changed outcome is comparable only when the fixture digest matches and the candidate replay link names it. This is recorded provenance, not cryptographic attestation of an external runner.
- Independent gate: semantic model output cannot issue, suppress, or alter the promotion verdict.
- Bounded claims: synthetic benchmark metrics describe only the checked-in suite.
