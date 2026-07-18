from causalgate import IntentContract, start_execution, span, trace_tool


@trace_tool("lookup")
def lookup(*, query: str) -> dict[str, str]:
    return {"answer": f"Public result for {query}"}


intent = IntentContract(goal="Research public vendor data.", allowed_tools=["lookup"])

with start_execution(intent) as recorder:
    with span("research"):
        result = lookup(query="Acme")
    execution = recorder.finish_execution(result["answer"])

print(execution.model_dump_json(indent=2))
