# AgentFlight Assurance Specification

Status: implemented reference specification  
Schema: `agentflight-assurance-suite/1.0`  
Intent verifier: `AFR-INTENT-CONFORMANCE/2.0.0`

## 1. Claim boundary

AgentFlight is a deterministic contract-conformance and replay-evidence system. Given a declared contract and a recorded event graph, it evaluates configured predicates, returns the causal-minimal frontier of detected violations, and can issue a scoped release recommendation for an authenticated fixture suite.

AgentFlight does not recover latent user intent, inspect hidden model reasoning, prove detector completeness, establish philosophical causation, or certify general production safety.

Supported terms are:

- **conformance evidence**: a versioned verifier result with cited events;
- **recorded causal provenance**: parent, evidence, and declared causal-predecessor edges;
- **divergence frontier**: all detected violations with no detected violating causal ancestor;
- **fixture replay recommendation**: one baseline/candidate comparison;
- **suite promotion recommendation**: the authenticated multi-fixture gate result.

## 2. Formal objects

An intent contract is a finite clause set `C = {c1, ..., cm}`. A clause contains a kind, canonical subject, statement, and identifier. Its identifier is the complete SHA-256 digest of a domain separator, schema version, clause kind, and Unicode-NFKC/whitespace-canonicalized subject. It establishes canonical string identity, not semantic equivalence.

An execution is a directed acyclic graph `G = (V, E)`. Vertices are recorded events. Edges are validated `parent_id`, `evidence_event_ids`, or `causal_predecessor_ids` references. Ingestion accepts only references to earlier events in the same execution. A supplied logical clock must advance beyond every declared causal predecessor.

Recorder sequence is a deterministic presentation order. It is not treated as causality when two events have no path between them.

## 3. Clause evaluation

Each verifier implements `phi(c, e, G) -> (status, evidence, verifier ID, version)`. Status is `unknown`, `observed`, `satisfied`, or `violated`.

`observed` means the application declared a relationship. It never constitutes behavioral satisfaction. `unknown` means no configured verifier has behavior-specific evidence. The flight record retains event-level evaluations so a later repair cannot erase `ever_violated` history.

The binding summary is conservative: `violated` dominates `satisfied`, which dominates `observed`. Consumers needing current-state semantics must use event-level evaluations.

## 4. Coverage

- Declaration coverage = clauses with an application-declared observation / all clauses.
- Verified coverage = clauses with behavior-specific satisfied or violated evidence / all clauses.
- Action coverage = consequential events with a clause binding / all consequential events.

None is a safety score. Unknown clauses and unbound consequential actions are explicit.

## 5. Divergence frontier

Let `D = {e in V | some configured clause verifier classifies e as violated}`. The frontier is `F = {e in D | no d in D causally precedes e}`.

Every member of `F` is a causal-minimal detected violation. If `|F| = 1`, the record has a unique first detected divergence. If `|F| > 1`, those violations are incomparable under recorded provenance. The API retains all members and supplies a sequence-ordered representative only for backward-compatible display.

This follows Lamport's distinction between partial causal order and an imposed total order.

## 6. Decision records

Plan and decision summaries, alternatives, alignment, and confidence are application-provided. They are allowlisted, bounded, linked to earlier evidence, and separated from hidden chain-of-thought.

`confidence` has semantics `self_reported_uncalibrated`. It is not a probability and cannot affect promotion until a held-out study reports reliability diagrams, Brier score, and a preregistered calibration-error measure.

## 7. Intent authorization semantics

Let `I`, `A`, `G`, `O`, and `R` be the action sets permitted by authenticated identity, the configured agent, the signed intent grant, organizational policy, and runtime context. An action is eligible only if it is in `I ∩ A ∩ G ∩ O ∩ R`; restrictions never add an element. The implementation refines membership over the tuple `(purpose, tool, action, resource type, data class, destination, effects, provenance, budget, delegation depth, approval)` using a closed, content-digested ontology. Unknown terms and missing mappings deny.

An intent grant is valid only if its HMAC, expiry, execution identifier, contract digest, ontology version, and ontology digest verify. Delegated grants must be set-subsets of parent authority, cannot weaken prohibitions or approvals, must reduce delegation depth, cannot expand budgets, and cannot outlive the parent. A linked approval is valid only for the exact execution, grant, tool, and arguments digest. Approval is conjunctive and never overrides absent grant authority.

An allow decision produces a short-lived permit whose signature binds the complete authorization-request digest and grant digest. Execution atomically consumes its nonce; mutation after decision or replay fails. Complete mediation means every recorded effectful tool proposal in the fixed ontology-mapped adapter profile has a linked authorization decision. It is not a claim that arbitrary uninstrumented code is mediated.

The GPT-5.6 Sol compiler produces only a candidate contract. Deterministic ontology validation and an authenticated, explicit human approval are separate prerequisites for signed grant issuance. No model response, confidence, or explanation participates in the authorization predicate.

## 8. Gate hierarchy

### 8.1 Fixture replay gate

The fixture gate checks identical fixture digest, exact replay linkage, detected divergence restoration, finding resolution, non-regressing coverage, and zero unbound consequential candidate actions. Its scope is `single_fixture_replay`; `production_safety_certification` is always false.

### 8.2 Authenticated suite gate

The software-factory gate evaluates multiple baseline/candidate pairs and requires:

1. an HMAC-SHA256 runner attestation using a secret unavailable to user-controlled build steps;
2. a SHA-256 digest covering verifier source and dependency lockfiles;
3. an exact signed fixture manifest;
4. the configured minimum number of distinct content-addressed fixtures;
5. declared task-family and action-channel diversity thresholds;
6. every fixture replay gate to pass; and
7. the two-sided 95% Wilson lower bound for suite pass rate to meet the preregistered threshold.

The verdict is bound to suite, source revision, artifact digest, detector version, policy version, runner identity, fixture set, and timestamp. Changed evidence invalidates the attestation.

The bundled synthetic suite uses a modest demonstration threshold. Production thresholds require domain-specific risk analysis, representative sampling, independent labels, and human authorization for high-impact actions.

## 9. Validation protocol

Validation uses immutable corpus manifests with stable case IDs, fixture hashes, target-rule labels, label source, split, and annotation status. Development and locked-test cases must be separated before detector changes.

Reports include confusion counts, precision, recall, specificity, per-rule results, and two-sided 95% Wilson intervals. Point estimates must include evidence scope and uncertainty.

Required adversarial properties include:

- renaming event IDs preserves classifications and causal structure;
- reordering incomparable events preserves divergence-frontier membership;
- declaration-only references never satisfy a clause;
- forged, cross-run, future, duplicate, and self-referential evidence is rejected;
- removing a required causal edge cannot strengthen a conclusion;
- tampering with provenance or the fixture manifest invalidates attestation.
- restricting any grant dimension never converts a deny into an allow;
- grant, approval, request, or permit tampering fails closed;
- approvals do not authorize tools absent from the grant;
- permits reject argument mutation and second use; and
- child grants never exceed parent authority.

## 10. Trusted computing base

The trusted computing base comprises the contract source, recorder, storage validation, verifier and policy implementations, fixture corpus, suite runner, attestation-key custody, and human release authority. Findings stored with sealed redacted runs are trusted inputs because redaction can remove detector evidence; production runners should generate and sign them inside the trusted boundary.

## 11. Remaining scientific validation

The bundled corpus is synthetic regression evidence. General validity requires independently annotated real-world traces, inter-reviewer agreement, a locked held-out dataset, preregistered thresholds, distribution-shift testing, calibration if confidence is used, and external replication. Implementation cannot truthfully manufacture that external evidence.
