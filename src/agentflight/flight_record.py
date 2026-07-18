from __future__ import annotations

import hashlib
import unicodedata
from collections import defaultdict

from .models import (
    BindingStatus,
    ClauseEvaluation,
    ConsequentialAction,
    DecisionRecord,
    Event,
    EventType,
    Execution,
    FirstDivergence,
    FlightRecord,
    IntentBinding,
    IntentClause,
    IntentClauseKind,
    IntentContract,
    IntentCoverage,
)


def intent_clause_id(kind: IntentClauseKind, subject: str) -> str:
    canonical_subject = " ".join(unicodedata.normalize("NFKC", subject).split())
    digest = hashlib.sha256(f"agentflight:intent-clause:v2\0{kind.value}\0{canonical_subject}".encode()).hexdigest()
    return f"intent_{kind.value}_{digest}"


def intent_clauses(contract: IntentContract) -> list[IntentClause]:
    specifications: list[tuple[IntentClauseKind, str, str]] = [
        (IntentClauseKind.GOAL, contract.goal, f"Advance the authorized goal: {contract.goal}"),
        *[
            (IntentClauseKind.TOOL_AUTHORIZATION, tool, f"Tool is authorized: {tool}")
            for tool in contract.allowed_tools
        ],
        *[
            (IntentClauseKind.PROHIBITED_OUTCOME, outcome, f"Outcome is prohibited: {outcome}")
            for outcome in contract.prohibited_outcomes
        ],
        *[
            (IntentClauseKind.RESOURCE_BOUNDARY, resource, f"Resource requires protection: {resource}")
            for resource in contract.protected_resources
        ],
        *[
            (IntentClauseKind.APPROVAL_GATE, tool, f"Tool requires approval: {tool}")
            for tool in contract.approval_required
        ],
        *[
            (IntentClauseKind.COMPLETION_CONDITION, condition, f"Completion requires evidence: {condition}")
            for condition in contract.completion_conditions
        ],
    ]
    clauses: list[IntentClause] = []
    seen: set[str] = set()
    for kind, subject, statement in specifications:
        clause_id = intent_clause_id(kind, subject)
        if clause_id not in seen:
            clauses.append(IntentClause(
                id=clause_id,
                kind=kind,
                subject=subject,
                statement=statement,
                critical=kind != IntentClauseKind.TOOL_AUTHORIZATION,
            ))
            seen.add(clause_id)
    return clauses


def analyze_flight_record(run: Execution) -> FlightRecord:
    """Bind trace evidence to intent without generating or exposing model reasoning."""
    clauses = intent_clauses(run.intent)
    clause_by_id = {clause.id: clause for clause in clauses}
    clause_by_kind_subject = {(clause.kind, clause.subject): clause for clause in clauses}
    event_by_id = {event.id: event for event in run.events}
    evidence: dict[str, list[tuple[Event, BindingStatus, str]]] = defaultdict(list)
    evaluations: list[ClauseEvaluation] = []

    def bind(
        clause: IntentClause | None,
        event: Event,
        status: BindingStatus,
        summary: str,
        verifier_id: str = "AFR-INTENT-CONFORMANCE",
    ) -> None:
        if clause is not None:
            evidence[clause.id].append((event, status, summary))
            evidence_ids = list(dict.fromkeys([
                *([event.parent_id] if event.parent_id else []),
                *event.causal_predecessor_ids,
                *event.payload.get("evidence_event_ids", []),
                event.id,
            ]))
            evaluations.append(ClauseEvaluation(
                clause_id=clause.id,
                event_id=event.id,
                status=status,
                verifier_id=verifier_id,
                verifier_version="2.0.0",
                evidence_event_ids=evidence_ids,
                summary=summary,
            ))

    goal = next((clause for clause in clauses if clause.kind == IntentClauseKind.GOAL), None)
    approvals = {
        event.parent_id
        for event in run.events
        if event.type == EventType.APPROVAL and event.payload.get("decision") == "approved"
    }
    executed = {event.parent_id for event in run.events if event.type == EventType.TOOL_RESULT}

    for event in run.events:
        if event.type == EventType.USER_INTENT:
            bind(goal, event, BindingStatus.OBSERVED, "Intent contract was recorded; behavior has not yet satisfied it.")

        if event.type == EventType.POLICY_DECISION:
            request = event.payload.get("request", {})
            request = request if isinstance(request, dict) else {}
            enforcement = event.payload.get("enforcement")
            outcome = event.payload.get("decision")
            # A policy decision proves that authorization was evaluated, not
            # that the effect was actually blocked or completed. The linked
            # proposal/result supplies behavior-specific satisfaction.
            status = BindingStatus.OBSERVED
            explicit_ids = request.get("intent_clause_ids", [])
            for clause_id in explicit_ids if isinstance(explicit_ids, list) else []:
                bind(
                    clause_by_id.get(str(clause_id)), event, status,
                    f"Intent authorization returned {outcome}: {event.payload.get('reason_code', 'policy decision')}.",
                    verifier_id="AFR-INTENT-AUTHZ",
                )
            requested_tool = str(request.get("tool", ""))
            tool_clause = clause_by_kind_subject.get((IntentClauseKind.TOOL_AUTHORIZATION, requested_tool))
            if tool_clause and tool_clause.id not in explicit_ids:
                bind(
                    tool_clause, event, status,
                    f"Intent authorization evaluated tool {requested_tool}.",
                    verifier_id="AFR-INTENT-AUTHZ",
                )
            if not explicit_ids and tool_clause is None:
                bind(
                    goal, event, status,
                    f"Intent authorization evaluated {requested_tool or 'a consequential action'}.",
                    verifier_id="AFR-INTENT-AUTHZ",
                )

        if event.type in {EventType.PLAN, EventType.DECISION}:
            for clause_id in event.payload.get("intent_clause_ids", []):
                bind(
                    clause_by_id.get(clause_id), event, BindingStatus.OBSERVED,
                    f"Application asserted binding: {event.payload.get('summary')}",
                )
            if event.type == EventType.PLAN:
                proposed_tools = set(event.payload.get("proposed_tools", []))
                unauthorized = proposed_tools - set(run.intent.allowed_tools)
                if unauthorized:
                    status = BindingStatus.SATISFIED if event.payload.get("blocked") else BindingStatus.VIOLATED
                    bind(goal, event, status, f"Plan referenced unauthorized tools: {', '.join(sorted(unauthorized))}.")
            else:
                parent = event_by_id.get(event.parent_id) if event.parent_id else None
                parent_tool = (
                    str(parent.payload.get("tool"))
                    if parent and parent.type == EventType.TOOL_PROPOSAL
                    else ""
                )
                parent_args = parent.payload.get("arguments", {}) if parent else {}
                protected_resource = (
                    parent_args.get("resource") in run.intent.protected_resources
                    if isinstance(parent_args, dict)
                    else False
                )
                blocked = event.payload.get("outcome") == "block"
                status = BindingStatus.SATISFIED if blocked else BindingStatus.VIOLATED
                if parent_tool and parent_tool not in run.intent.allowed_tools:
                    bind(goal, event, status, f"Decision {'blocked' if blocked else 'continued'} an unauthorized tool.")
                if protected_resource:
                    resource_clause = clause_by_kind_subject.get(
                        (IntentClauseKind.RESOURCE_BOUNDARY, str(parent_args.get("resource")))
                    )
                    bind(resource_clause, event, status, "Decision evaluated a protected resource boundary.")
                if parent_tool in run.intent.approval_required:
                    approval_clause = clause_by_kind_subject.get((IntentClauseKind.APPROVAL_GATE, parent_tool))
                    bind(approval_clause, event, status, "Decision evaluated a required approval gate.")

        tool = None
        if event.type == EventType.RETRIEVAL:
            tool = event.actor
        elif event.type == EventType.TOOL_PROPOSAL:
            tool = str(event.payload.get("tool", ""))
        if tool:
            tool_clause = clause_by_kind_subject.get((IntentClauseKind.TOOL_AUTHORIZATION, tool))
            if tool_clause:
                bind(tool_clause, event, BindingStatus.SATISFIED, f"Observed authorized tool {tool}.")
            elif event.type == EventType.TOOL_PROPOSAL:
                status = BindingStatus.SATISFIED if event.payload.get("blocked") else BindingStatus.VIOLATED
                bind(goal, event, status, f"Unauthorized tool proposal {tool} was {'blocked' if event.payload.get('blocked') else 'allowed'}.")

        if event.type == EventType.TOOL_PROPOSAL:
            arguments = event.payload.get("arguments", {})
            resource = arguments.get("resource") if isinstance(arguments, dict) else None
            resource_clause = clause_by_kind_subject.get((IntentClauseKind.RESOURCE_BOUNDARY, resource))
            if resource_clause:
                status = BindingStatus.SATISFIED if event.payload.get("blocked") else BindingStatus.VIOLATED
                bind(resource_clause, event, status, "Protected resource boundary was evaluated.")

            approval_clause = clause_by_kind_subject.get((IntentClauseKind.APPROVAL_GATE, tool or ""))
            if approval_clause and (event.payload.get("blocked") or event.id in executed):
                status = (
                    BindingStatus.SATISFIED
                    if event.payload.get("blocked") or event.id in approvals
                    else BindingStatus.VIOLATED
                )
                bind(approval_clause, event, status, "Required approval gate was evaluated.")

            if event.payload.get("outbound") and "protected" in event.sensitivity:
                for clause in clauses:
                    if clause.kind == IntentClauseKind.PROHIBITED_OUTCOME:
                        status = BindingStatus.SATISFIED if event.payload.get("blocked") else BindingStatus.VIOLATED
                        bind(clause, event, status, "Protected outbound outcome was evaluated.")

        if event.type == EventType.FINAL_ANSWER:
            supplied = set(event.payload.get("evidence", []))
            for clause in clauses:
                if clause.kind == IntentClauseKind.COMPLETION_CONDITION:
                    status = BindingStatus.SATISFIED if clause.subject in supplied else BindingStatus.VIOLATED
                    bind(clause, event, status, "Completion evidence was evaluated.")

    bindings: list[IntentBinding] = []
    for clause in clauses:
        entries = evidence.get(clause.id, [])
        if not entries:
            continue
        statuses = {entry[1] for entry in entries}
        status = (
            BindingStatus.VIOLATED
            if BindingStatus.VIOLATED in statuses
            else BindingStatus.SATISFIED
            if BindingStatus.SATISFIED in statuses
            else BindingStatus.OBSERVED
        )
        event_ids = list(dict.fromkeys(entry[0].id for entry in entries))
        summaries = list(dict.fromkeys(entry[2] for entry in entries))
        verified_event_ids = list(dict.fromkeys(
            entry[0].id for entry in entries
            if entry[1] in {BindingStatus.SATISFIED, BindingStatus.VIOLATED}
        ))
        bindings.append(
            IntentBinding(
                clause_id=clause.id,
                status=status,
                event_ids=event_ids,
                summaries=summaries,
                verified_event_ids=verified_event_ids,
                verifier_ids=["AFR-INTENT-CONFORMANCE"] if verified_event_ids else [],
                ever_violated=BindingStatus.VIOLATED in statuses,
            )
        )

    predecessors: dict[str, set[str]] = defaultdict(set)
    for event in run.events:
        sources = (
            ([event.parent_id] if event.parent_id else [])
            + event.causal_predecessor_ids
            + list(event.payload.get("evidence_event_ids", []))
        )
        predecessors[event.id].update(source_id for source_id in sources if source_id in event_by_id)

    ancestor_cache: dict[str, set[str]] = {}

    def ancestors(event_id: str) -> set[str]:
        if event_id in ancestor_cache:
            return ancestor_cache[event_id]
        found: set[str] = set()
        frontier = list(predecessors.get(event_id, set()))
        while frontier:
            source_id = frontier.pop()
            if source_id not in found:
                found.add(source_id)
                frontier.extend(predecessors.get(source_id, set()))
        ancestor_cache[event_id] = found
        return found

    violated_by_event: dict[str, list[str]] = defaultdict(list)
    for clause_id, entries in evidence.items():
        for event, status, _ in entries:
            if status == BindingStatus.VIOLATED:
                violated_by_event[event.id].append(clause_id)
    violated_ids = set(violated_by_event)
    frontier_ids = {
        event_id for event_id in violated_ids
        if not (ancestors(event_id) & violated_ids)
    }

    def divergence(event_id: str) -> FirstDivergence:
        divergent_event = event_by_id[event_id]
        clause_ids = sorted(set(violated_by_event[divergent_event.id]))
        causal_ids = sorted(
            ancestors(event_id) | {event_id},
            key=lambda item: (event_by_id[item].sequence, item),
        )
        return FirstDivergence(
            event_id=divergent_event.id,
            sequence=divergent_event.sequence,
            clause_ids=clause_ids,
            summary=f"{divergent_event.type.value} has behavior-specific evidence violating {len(clause_ids)} intent clause(s).",
            causal_event_ids=causal_ids,
        )

    divergence_frontier = [
        divergence(event_id)
        for event_id in sorted(frontier_ids, key=lambda item: (event_by_id[item].sequence, item))
    ]
    first_divergence = divergence_frontier[0] if divergence_frontier else None

    bound_ids = {binding.clause_id for binding in bindings}
    verified_ids = {
        evaluation.clause_id for evaluation in evaluations
        if evaluation.status in {BindingStatus.SATISFIED, BindingStatus.VIOLATED}
    }
    declared_ids = {
        evaluation.clause_id for evaluation in evaluations
        if evaluation.status == BindingStatus.OBSERVED
    }
    satisfied = sum(binding.status == BindingStatus.SATISFIED for binding in bindings)
    violated = sum(binding.status == BindingStatus.VIOLATED for binding in bindings)
    consequential_types = {
        EventType.PLAN,
        EventType.DECISION,
        EventType.POLICY_DECISION,
        EventType.TOOL_PROPOSAL,
        EventType.STATE_MUTATION,
        EventType.FINAL_ANSWER,
    }
    bound_event_ids = {
        event_id
        for binding in bindings
        for event_id in binding.event_ids
    }
    unbound_actions = [
        ConsequentialAction(
            event_id=event.id,
            action=str(event.payload.get("tool") or event.payload.get("field") or event.type.value),
            reason="No intent clause was bound to this consequential event.",
        )
        for event in run.events
        if event.type in consequential_types and event.id not in bound_event_ids
    ]
    consequential_events = [event for event in run.events if event.type in consequential_types]
    bound_consequential = len(consequential_events) - len(unbound_actions)
    total_clauses = len(clauses)
    critical_ids = {clause.id for clause in clauses if clause.critical}
    coverage = IntentCoverage(
        total_clauses=total_clauses,
        bound_clauses=len(bound_ids),
        satisfied_clauses=satisfied,
        violated_clauses=violated,
        coverage_ratio=len(bound_ids) / max(total_clauses, 1),
        unbound_clause_ids=[clause.id for clause in clauses if clause.id not in bound_ids],
        declaration_coverage_ratio=len(declared_ids) / max(total_clauses, 1),
        verified_coverage_ratio=len(verified_ids) / max(total_clauses, 1),
        consequential_action_coverage_ratio=bound_consequential / max(len(consequential_events), 1),
        declared_clauses=len(declared_ids),
        verified_clauses=len(verified_ids),
        consequential_actions=len(consequential_events),
        bound_consequential_actions=bound_consequential,
        unknown_clause_ids=[clause.id for clause in clauses if clause.id not in verified_ids],
        critical_clauses=len(critical_ids),
        verified_critical_clauses=len(critical_ids & verified_ids),
        unknown_critical_clause_ids=sorted(critical_ids - verified_ids),
    )
    decision_records = []
    for event in run.events:
        if event.type not in {EventType.DECISION, EventType.POLICY_DECISION}:
            continue
        explicit_clause_ids = [
            clause_id
            for clause_id in event.payload.get("intent_clause_ids", [])
            if clause_id in clause_by_id
        ]
        inferred_clause_ids = [
            binding.clause_id for binding in bindings if event.id in binding.event_ids
        ]
        clause_ids = list(dict.fromkeys(explicit_clause_ids + inferred_clause_ids))
        decision_records.append(
            DecisionRecord(
                event_id=event.id,
                sequence=event.sequence,
                action=str(event.payload.get("rule") or event.payload.get("reason_code") or "intent evaluation"),
                decision=str(event.payload.get("decision") or event.payload.get("outcome") or "recorded"),
                outcome=str(event.payload["outcome"]) if event.payload.get("outcome") is not None else None,
                summary=str(
                    event.payload.get("summary")
                    or event.payload.get("reason")
                    or "Application decision recorded."
                ),
                clause_ids=clause_ids,
                bound_clause_ids=clause_ids,
                evidence_event_ids=[
                    evidence_id
                    for evidence_id in event.payload.get("evidence_event_ids", [])
                    if evidence_id in event_by_id and event_by_id[evidence_id].sequence < event.sequence
                ],
                alternatives_considered=list(event.payload.get("alternatives_considered", [])),
                confidence=float(event.payload.get("confidence", 0)),
            )
        )
    children: dict[str, set[str]] = defaultdict(set)
    for event in run.events:
        for source_id in predecessors.get(event.id, set()):
            children[source_id].add(event.id)
    if first_divergence is not None:
        causal_ids = set(first_divergence.causal_event_ids)
        frontier = [first_divergence.event_id]
        while frontier:
            source_id = frontier.pop()
            for child_id in children.get(source_id, set()):
                if child_id not in causal_ids:
                    causal_ids.add(child_id)
                    frontier.append(child_id)
    else:
        causal_ids = set()
        for event in run.events:
            if event.type not in consequential_types:
                continue
            cursor: Event | None = event
            while cursor is not None and cursor.id not in causal_ids:
                causal_ids.add(cursor.id)
                cursor = event_by_id.get(cursor.parent_id) if cursor.parent_id else None
    causal_ids.update(event.id for event in run.events if event.type == EventType.USER_INTENT)
    causal_chain_ids = [event.id for event in sorted(run.events, key=lambda item: item.sequence) if event.id in causal_ids]
    return FlightRecord(
        execution_id=run.id,
        intent_version=run.intent.version,
        clauses=clauses,
        bindings=bindings,
        evaluations=evaluations,
        first_divergence=first_divergence,
        divergence_frontier=divergence_frontier,
        coverage=coverage,
        plan_event_ids=[event.id for event in run.events if event.type == EventType.PLAN],
        decision_event_ids=[event.id for event in run.events if event.type == EventType.DECISION],
        causal_chain_event_ids=causal_chain_ids,
        decision_records=decision_records,
        first_divergence_event_id=first_divergence.event_id if first_divergence else None,
        first_divergence_reason=first_divergence.summary if first_divergence else None,
        intent_coverage=coverage.coverage_ratio,
        unbound_consequential_actions=unbound_actions,
    )
