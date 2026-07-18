import argparse
import os
from pathlib import Path

from causalgate.demo import FIXTURE_HASH
from causalgate.live_analysis import verify_recorded_artifact

parser = argparse.ArgumentParser()
parser.add_argument("--artifact", default="artifacts/recorded-analysis.json")
args = parser.parse_args()
artifact = Path(args.artifact)

if not artifact.exists():
    if os.getenv("CAUSALGATE_RECORDED_ANALYSIS_OPTIONAL", "false").lower() == "true":
        print("SKIP: recorded analysis is explicitly optional for this verification profile.")
        raise SystemExit(0)
    print(f"FAIL: required recorded analysis artifact is missing: {artifact}")
    raise SystemExit(1)

try:
    verified = verify_recorded_artifact(artifact, FIXTURE_HASH)
except Exception as exc:
    print(f"FAIL: invalid recorded analysis artifact: {type(exc).__name__}")
    raise SystemExit(1)

print(f"PASS: recorded {verified.model} analysis validates for fixture {verified.fixture_hash}.")
