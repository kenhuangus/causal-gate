import pytest

from causalgate.adapters import AgentsSDKTraceAdapter, LangGraphTraceAdapter, MediatedToolExecutor
from causalgate.authorization import IntentAuthorizer, issue_grant
from causalgate.models import EventType, IntentContract
from causalgate.recorder import Recorder


def test_agents_adapter_links_tool_events():
    recorder = Recorder(IntentContract(goal="x", allowed_tools=["lookup"]))
    adapter = AgentsSDKTraceAdapter(recorder)
    proposal = adapter.on_tool_start("lookup", {"q": "safe"})
    result = adapter.on_tool_end(proposal.id, {"answer": 1})
    assert result.parent_id == proposal.id


def test_langgraph_adapter_records_state_change():
    recorder = Recorder(IntentContract(goal="x", allowed_tools=[]))
    event = LangGraphTraceAdapter(recorder).on_node("plan", {}, {"next": "done"})
    assert event.type == EventType.STATE_MUTATION


def test_mediated_executor_records_policy_and_consumes_permit_before_calling_tool():
    value = IntentContract(
        goal="Research public data.", purpose_id="purpose.vendor.public_research",
        subject_id="agent:test", on_behalf_of="user:test", allowed_tools=["retrieve"],
        allowed_resource_types=["resource.public"], allowed_data_classes=["data.public"],
        allowed_destinations=["destination.local"],
    )
    recorder = Recorder(value)
    key = "adapter-test-signing-key-with-at-least-32-bytes"
    grant = issue_grant(value, recorder.execution.id, key)
    executor = MediatedToolExecutor(
        recorder, IntentAuthorizer(value, recorder.execution.id, grant, key)
    )
    assert executor.call("retrieve", {"resource": "public.vendor"}, lambda resource: resource) == "public.vendor"
    assert [event.type for event in recorder.execution.events][-3:] == [
        EventType.TOOL_PROPOSAL, EventType.POLICY_DECISION, EventType.TOOL_RESULT,
    ]

    called = False
    def forbidden(resource):
        nonlocal called
        called = True
        return resource
    with pytest.raises(PermissionError, match="intent.tool"):
        executor.call("read_secret", {"resource": "synthetic_canary"}, forbidden)
    assert called is False
    assert recorder.execution.events[-1].type == EventType.POLICY_DECISION
