from agentflight.adapters import AgentsSDKTraceAdapter, LangGraphTraceAdapter
from agentflight.models import EventType, IntentContract
from agentflight.recorder import Recorder


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

