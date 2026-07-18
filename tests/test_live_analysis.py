import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from agentflight.demo import FIXTURE_HASH, run_demo
from agentflight.live_analysis import AnalysisUnavailable, _calls, analyze_live, generate_recorded_artifact, minimized_trace, verify_recorded_artifact


class Response:
    id = "resp_test_123"
    model = "gpt-test-semantic-resolved"
    def __init__(self, output): self.output_text = json.dumps(output)


class Responses:
    def __init__(self, output=None, error=None): self.output, self.error, self.kwargs = output, error, None
    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error: raise self.error
        return Response(self.output)


class Client:
    def __init__(self, output=None, error=None): self.responses = Responses(output, error)


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    _calls.clear()
    monkeypatch.setenv("AGENTFLIGHT_LIVE_ANALYSIS_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test-semantic")


def valid_output(run):
    return {"findings": [{"finding_type": "intent_drift", "summary": "Retrieved instructions influenced the plan.",
        "reasoning_summary": "The cited proposal follows untrusted retrieval.", "severity": "high", "confidence": 0.92,
        "evidence_event_ids": [run.events[1].id, run.events[2].id], "recommended_control": "Enforce instruction provenance."}]}


def test_live_analysis_uses_redacted_schema_without_mutation():
    run = run_demo("baseline"); before = run.model_dump_json(); client = Client(valid_output(run))
    artifact = analyze_live(run, client=client)
    assert artifact.mode == "live" and artifact.model == "gpt-test-semantic-resolved"
    assert artifact.requested_model == "gpt-test-semantic" and artifact.reasoning_effort == "medium"
    assert artifact.provenance == "openai_responses_api" and artifact.validation == "passed"
    sent = client.responses.kwargs
    assert sent["text"]["format"]["strict"] is True
    assert sent["reasoning"] == {"effort": "medium"}
    assert "AFR_SYNTHETIC_CANARY" not in sent["input"][1]["content"]
    assert run.model_dump_json() == before


def test_unknown_evidence_and_provider_errors_fail_safely():
    run = run_demo("baseline"); invalid = valid_output(run); invalid["findings"][0]["evidence_event_ids"] = ["evt_unknown"]
    with pytest.raises(AnalysisUnavailable, match="failed safely"): analyze_live(run, client=Client(invalid))
    _calls.clear()
    with pytest.raises(AnalysisUnavailable, match="failed safely") as exc: analyze_live(run, client=Client(error=RuntimeError("provider secret detail")))
    assert "provider secret detail" not in str(exc.value)


def test_disabled_gate_never_invokes_client(monkeypatch):
    monkeypatch.setenv("AGENTFLIGHT_LIVE_ANALYSIS_ENABLED", "false"); client = Client(valid_output(run_demo("baseline")))
    with pytest.raises(AnalysisUnavailable, match="disabled"): analyze_live(run_demo("baseline"), client=client)
    assert client.responses.kwargs is None


def test_generate_and_verify_recorded_artifact(tmp_path: Path):
    run = run_demo("baseline"); output = tmp_path / "recorded.json"
    artifact = generate_recorded_artifact(run, output, client=Client(valid_output(run)))
    assert artifact.mode == "recorded" and verify_recorded_artifact(output, FIXTURE_HASH) == artifact
    tampered = json.loads(output.read_text())
    tampered["findings"][0]["summary"] = "changed after generation"
    output.write_text(json.dumps(tampered))
    with pytest.raises(ValueError, match="integrity"):
        verify_recorded_artifact(output, FIXTURE_HASH)


def test_minimized_trace_contains_no_raw_protected_payload():
    value = json.dumps(minimized_trace(run_demo("baseline")))
    assert "AFR_SYNTHETIC_CANARY" not in value and "[PROTECTED]" in value


def test_recorded_verifier_fails_missing_unless_explicitly_optional(tmp_path: Path):
    missing = tmp_path / "missing.json"
    if Path(sys.executable).exists():
        command = [sys.executable, "scripts/verify_recorded_analysis.py", "--artifact", str(missing)]
    else:
        # Some sandboxed uv environments expose a dangling interpreter symlink.
        # Use the project runner in that case; normal CI takes the direct path.
        command = [shutil.which("uv") or "uv", "run", "python3", "scripts/verify_recorded_analysis.py", "--artifact", str(missing)]
    env = {**os.environ, "AGENTFLIGHT_RECORDED_ANALYSIS_OPTIONAL": "false"}
    assert subprocess.run(command, env=env, capture_output=True, text=True).returncode == 1
    env["AGENTFLIGHT_RECORDED_ANALYSIS_OPTIONAL"] = "true"
    skipped = subprocess.run(command, env=env, capture_output=True, text=True)
    assert skipped.returncode == 0 and "SKIP" in skipped.stdout
