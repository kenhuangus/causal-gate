from causalgate.models import EventType, IntentContract
from causalgate.recorder import Recorder, trace_tool


def test_payload_is_redacted_before_recording():
    recorder = Recorder(IntentContract(goal="test", allowed_tools=[]))
    recorder.record(EventType.TOOL_RESULT, "tool", {"api_key": "synthetic-never-store-this", "nested": {"authorization": "Bearer abc.def"}})
    payload = recorder.execution.events[0].redacted_payload
    assert payload == {"api_key": "[REDACTED]", "nested": {"authorization": "[REDACTED]"}}


def test_redaction_covers_common_header_and_configuration_key_spellings():
    recorder = Recorder(IntentContract(goal="test", allowed_tools=[]))
    recorder.record(EventType.TOOL_RESULT, "tool", {
        "access_token": "token-value",
        "x-api-key": "key-value",
        "nested": {"client_secret": "secret-value", "public": "safe"},
    })
    assert recorder.execution.events[0].redacted_payload == {
        "access_token": "[REDACTED]",
        "x-api-key": "[REDACTED]",
        "nested": {"client_secret": "[REDACTED]", "public": "safe"},
    }


def test_trace_tool_records_proposal_and_result():
    @trace_tool("add")
    def add(*, left: int, right: int):
        return left + right
    with Recorder(IntentContract(goal="add", allowed_tools=["add"])) as recorder:
        assert add(left=2, right=3) == 5
    assert [event.type for event in recorder.execution.events][-2:] == [EventType.TOOL_PROPOSAL, EventType.TOOL_RESULT]
