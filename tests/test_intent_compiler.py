import json

import pytest

from agentflight.intent_compiler import (
    IntentCompilationUnavailable,
    _calls,
    compile_intent_live,
)


class Response:
    id = "resp_intent_123"
    model = "gpt-5.6-sol-2026-07-01"

    def __init__(self, output):
        self.output_text = json.dumps(output)


class Responses:
    def __init__(self, output=None, error=None):
        self.output = output
        self.error = error
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return Response(self.output)


class Client:
    def __init__(self, output=None, error=None):
        self.responses = Responses(output, error)


@pytest.fixture(autouse=True)
def live_enabled(monkeypatch):
    _calls.clear()
    monkeypatch.setenv("AGENTFLIGHT_LIVE_ANALYSIS_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)


def candidate(**updates):
    value = {
        "goal": "Research a public vendor and produce a local summary.",
        "purpose_id": "purpose.vendor.public_research",
        "allowed_tools": ["retrieve", "summarize"],
        "allowed_resource_types": ["resource.public"],
        "allowed_data_classes": ["data.public"],
        "allowed_destinations": ["destination.local"],
        "prohibited_effects": ["effect.external_disclosure"],
        "approval_required": [],
        "completion_conditions": ["public summary", "source citation"],
        "ambiguities": [],
    }
    value.update(updates)
    return value


def test_compiler_uses_sol_medium_strict_schema_and_only_proposes_authority():
    client = Client(candidate())
    result = compile_intent_live("Research Acme using only public sources.", client=client)
    assert result.status == "ready_for_human_approval"
    assert result.requested_model == "gpt-5.6-sol"
    assert result.resolved_model == Response.model
    assert result.reasoning_effort == "medium"
    assert "no authority" in result.disclosure.lower()
    sent = client.responses.kwargs
    assert sent["model"] == "gpt-5.6-sol"
    assert sent["reasoning"] == {"effort": "medium"}
    assert sent["text"]["format"]["strict"] is True
    assert result.candidate_contract.allowed_tools == ["retrieve", "summarize"]


def test_unknown_or_ambiguous_terms_never_become_authority():
    result = compile_intent_live(
        "Do the thing.",
        client=Client(candidate(allowed_tools=["retrieve", "root_shell"], ambiguities=["Which vendor?"])),
    )
    assert result.status == "requires_clarification"
    assert result.unknown_terms == ["root_shell"]
    assert result.candidate_contract.allowed_tools == ["retrieve"]


def test_disabled_and_provider_failures_are_sanitized(monkeypatch):
    monkeypatch.setenv("AGENTFLIGHT_LIVE_ANALYSIS_ENABLED", "false")
    client = Client(candidate())
    with pytest.raises(IntentCompilationUnavailable, match="disabled"):
        compile_intent_live("Research Acme.", client=client)
    assert client.responses.kwargs is None

    monkeypatch.setenv("AGENTFLIGHT_LIVE_ANALYSIS_ENABLED", "true")
    with pytest.raises(IntentCompilationUnavailable, match="failed safely") as exc:
        compile_intent_live("Research Acme.", client=Client(error=RuntimeError("provider secret")))
    assert "provider secret" not in str(exc.value)
