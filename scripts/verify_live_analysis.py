import os

if os.getenv("AGENTFLIGHT_LIVE_ANALYSIS_ENABLED", "false").lower() != "true":
    print("SKIP: live analysis is explicitly disabled. No API call was attempted.")
    raise SystemExit(0)
if not os.getenv("OPENAI_API_KEY"):
    print("FAIL: live analysis is enabled but OPENAI_API_KEY is unavailable.")
    raise SystemExit(1)
print("READY: run `agentflight record-analysis` to exercise the gated product path.")
