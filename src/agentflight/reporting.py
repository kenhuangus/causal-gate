from __future__ import annotations

from .flight_record import analyze_flight_record
from .models import Execution


def markdown_report(run: Execution) -> str:
    flight = analyze_flight_record(run)
    divergence = (
        f"Event `{flight.first_divergence.event_id}` at sequence {flight.first_divergence.sequence}: "
        f"{flight.first_divergence.summary}"
        if flight.first_divergence
        else "No deterministic intent divergence was recorded."
    )
    binding_text = "\n".join(
        f"- `{binding.clause_id}` — {binding.status}; evidence: {', '.join(binding.event_ids)}"
        for binding in flight.bindings
    ) or "No clause bindings were recorded."
    finding_text = "\n".join(
        f"### {f.rule_id}: {f.title}\n\nSeverity: {f.severity}. Evidence: {', '.join(f.evidence_event_ids)}.\n\n{f.explanation}\n\nControl: {f.recommended_control}\n"
        for f in run.findings
    ) or "No deterministic findings."
    return f"""# AgentFlight incident report

Execution: `{run.id}`  
Fixture: `{run.fixture_hash or 'imported'}`  
Policy mode: `{run.policy_mode}`

## Intent contract

Goal: {run.intent.goal}

Allowed tools: {', '.join(run.intent.allowed_tools)}

## Intent Flight Record

Intent-clause coverage: {flight.coverage.bound_clauses}/{flight.coverage.total_clauses} ({flight.coverage.coverage_ratio:.0%})

First divergence: {divergence}

### Clause bindings

{binding_text}

Decision and plan summaries in this report are application-provided structured records. AgentFlight does not capture hidden model reasoning or chain-of-thought.

## Findings

{finding_text}

## Evidence integrity

Every referenced event identifier was validated against this execution. Public payload representations and exports are redacted.
"""
