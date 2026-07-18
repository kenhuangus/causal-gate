from __future__ import annotations

from .causal_record import analyze_causal_record
from .models import Execution


def markdown_report(run: Execution) -> str:
    record = analyze_causal_record(run)
    divergence = (
        f"Event `{record.first_divergence.event_id}` at sequence {record.first_divergence.sequence}: "
        f"{record.first_divergence.summary}"
        if record.first_divergence
        else "No configured verifier detected an intent-contract violation."
    )
    binding_text = "\n".join(
        f"- `{binding.clause_id}` — {binding.status}; evidence: {', '.join(binding.event_ids)}"
        for binding in record.bindings
    ) or "No clause bindings were recorded."
    finding_text = "\n".join(
        f"### {f.rule_id}: {f.title}\n\nSeverity: {f.severity}. Evidence: {', '.join(f.evidence_event_ids)}.\n\n{f.explanation}\n\nControl: {f.recommended_control}\n"
        for f in run.findings
    ) or "No deterministic findings."
    return f"""# CausalGate incident report

Execution: `{run.id}`  
Fixture: `{run.fixture_hash or 'imported'}`  
Policy mode: `{run.policy_mode}`

## Intent contract

Goal: {run.intent.goal}

Allowed tools: {', '.join(run.intent.allowed_tools)}

## Intent Causal Record

Declaration coverage: {record.coverage.declared_clauses}/{record.coverage.total_clauses} ({record.coverage.declaration_coverage_ratio:.0%})

Behaviorally verified coverage: {record.coverage.verified_clauses}/{record.coverage.total_clauses} ({record.coverage.verified_coverage_ratio:.0%})

Consequential-action coverage: {record.coverage.bound_consequential_actions}/{record.coverage.consequential_actions} ({record.coverage.consequential_action_coverage_ratio:.0%})

Divergence-frontier representative: {divergence}

Causal-minimal detected violations: {len(record.divergence_frontier)}

### Clause bindings

{binding_text}

Decision and plan summaries, alternatives, and confidence values in this report are application-provided structured records. Confidence is self-reported and uncalibrated. CausalGate does not capture hidden model reasoning or chain-of-thought.

## Findings

{finding_text}

## Evidence integrity

Every referenced event identifier was validated against this execution. Public payload representations and exports are redacted. This report is deterministic conformance evidence from configured verifier rules, not a proof of latent intent or production-safety certification.
"""
