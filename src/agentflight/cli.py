from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .assurance import run_synthetic_assurance_suite
from .benchmark import run_benchmark
from .demo import compare, run_demo
from .models import PolicyMode
from .reporting import markdown_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentflight")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="run the synthetic scenario")
    demo.add_argument("--mode", choices=[m.value for m in PolicyMode], default="baseline")
    demo.add_argument("--json", action="store_true")
    sub.add_parser("verify-demo")
    sub.add_parser("benchmark")
    sub.add_parser("assurance-suite", help="run the authenticated multi-fixture promotion suite")
    record = sub.add_parser("record-analysis", help="generate a labeled recorded semantic-analysis artifact")
    record.add_argument("--output", default="artifacts/recorded-analysis.json")
    args = parser.parse_args(argv)
    if args.command == "demo":
        run = run_demo(args.mode)
        print(run.model_dump_json(indent=2) if args.json else markdown_report(run))
        return 1 if any(f.severity == "critical" for f in run.findings) else 0
    if args.command == "verify-demo":
        base, protected = run_demo("baseline"), run_demo("protected")
        result = compare(base, protected)
        required = {"AFR-EGRESS-001", "AFR-APPROVAL-001", "AFR-CHAIN-001"}
        passed = required <= {f.rule_id for f in base.findings} and not protected.findings and len(result.resolved_rules) == 8
        print(json.dumps({"passed": passed, "baseline_findings": len(base.findings), "protected_findings": len(protected.findings),
                          "fixture_hash": base.fixture_hash, "resolved": result.resolved_rules}, indent=2))
        return 0 if passed else 1
    if args.command == "record-analysis":
        from .live_analysis import AnalysisUnavailable, generate_recorded_artifact
        try:
            artifact = generate_recorded_artifact(run_demo("baseline"), Path(args.output))
            print(json.dumps({"status": "passed", "mode": artifact.mode, "fixture_hash": artifact.fixture_hash, "output": args.output}, indent=2))
            return 0
        except AnalysisUnavailable as exc:
            print(str(exc), file=sys.stderr)
            return 2
    if args.command == "assurance-suite":
        import os
        key = os.getenv("AGENTFLIGHT_ATTESTATION_KEY", "")
        if len(key.encode()) < 32:
            print("AGENTFLIGHT_ATTESTATION_KEY must contain at least 32 bytes", file=sys.stderr)
            return 2
        result = run_synthetic_assurance_suite(key)
        print(result.model_dump_json(indent=2))
        return 0 if result.eligible else 1
    result = run_benchmark()
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.precision == 1 and result.recall == 1 and result.deterministic else 1


if __name__ == "__main__":
    sys.exit(main())
