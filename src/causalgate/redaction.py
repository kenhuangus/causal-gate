from __future__ import annotations

import re
from typing import Any

SENSITIVE_KEYS = {"api_key", "authorization", "credential", "password", "secret", "token", "private_key"}
PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]+"),
]
PROTECTED_STRUCTURAL_KEYS = {
    "tool", "blocked", "outbound", "protected_read", "decision", "outcome",
    "rule", "field", "prevented_by_event_id", "intent_clause_ids", "evidence_event_ids",
}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: "[REDACTED]" if _is_sensitive_key(k) else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        for pattern in PATTERNS:
            value = pattern.sub("[REDACTED]", value)
    return value


def _is_sensitive_key(key: object) -> bool:
    """Recognize common header and configuration spellings, not only exact keys."""
    normalized = str(key).lower().replace("-", "_").replace(" ", "_")
    return normalized in SENSITIVE_KEYS or normalized.endswith(("_api_key", "_authorization", "_credential", "_password", "_secret", "_token", "_private_key"))


def redacted_event_payload(payload: dict[str, Any], sensitivity: list[str]) -> dict[str, Any]:
    """Build the only payload representation safe to return through the API."""
    value = redact(payload)
    if "protected" in sensitivity:
        return {
            key: item if key in PROTECTED_STRUCTURAL_KEYS else "[PROTECTED]"
            for key, item in value.items()
        }
    return value
