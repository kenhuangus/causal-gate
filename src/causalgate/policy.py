from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import IntentContract


@dataclass(frozen=True)
class PolicyDecision:
    decision: str
    reason: str
    rule: str


def evaluate(tool: str, arguments: dict[str, Any], contract: IntentContract, protected_data: bool = False) -> PolicyDecision:
    """Deterministic precedence: prohibited outcome, resource, tool, approval, data flow, allow."""
    if arguments.get("outcome") in contract.prohibited_outcomes:
        return PolicyDecision("deny", "prohibited outcome", "prohibited_outcome")
    if arguments.get("resource") in contract.protected_resources:
        return PolicyDecision("deny", "protected resource outside authorization", "resource_boundary")
    if tool not in contract.allowed_tools:
        return PolicyDecision("deny", "tool outside intent contract", "tool_authorization")
    if tool in contract.approval_required:
        return PolicyDecision("require_approval", "tool requires linked approval", "approval_gate")
    if protected_data and arguments.get("outbound"):
        return PolicyDecision("deny", "protected data cannot flow outbound", "data_flow")
    return PolicyDecision("allow", "authorized by intent contract", "allow")
