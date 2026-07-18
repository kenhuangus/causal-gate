from typing_extensions import TypedDict
from langgraph.graph import END, START, StateGraph

from causalgate import IntentContract, LangGraphTraceAdapter, Recorder


class State(TypedDict):
    count: int


def increment(state: State) -> dict[str, int]:
    return {"count": state["count"] + 1}


recorder = Recorder(IntentContract(goal="Increment a counter.", allowed_tools=[]))
adapter = LangGraphTraceAdapter(recorder)
builder = StateGraph(State)
builder.add_node("increment", adapter.wrap_node("increment", increment))
builder.add_edge(START, "increment")
builder.add_edge("increment", END)
graph = builder.compile()

print(graph.invoke({"count": 0}))
