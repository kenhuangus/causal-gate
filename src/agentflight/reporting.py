from __future__ import annotations

from .models import Execution


def markdown_report(run: Execution) -> str:
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

## Findings

{finding_text}

## Evidence integrity

Every referenced event identifier was validated against this execution. Public payload representations and exports are redacted.
"""
