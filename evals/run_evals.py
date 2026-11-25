"""Run the planted-error eval.

    python -m evals.run_evals            # offline: code checks only (no API key needed)
    python -m evals.run_evals --live     # adds the Claude verifier (needs ANTHROPIC_API_KEY)
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict

from seatbelt import Status, check_blocks
from evals.cases import CASES, DOCS


def evaluate(verifier=None) -> dict:
    by_kind = defaultdict(lambda: {"planted": 0, "caught": 0})
    false_pos = total_good = 0
    rows = []
    for name, kind, blocks, should_flag in CASES:
        report = check_blocks(name, DOCS, blocks, verifier=verifier)
        flagged = {i for i, c in enumerate(report.claims) if c.status != Status.SUPPORTED}
        caught = should_flag & flagged
        fps = flagged - should_flag
        by_kind[kind]["planted"] += len(should_flag)
        by_kind[kind]["caught"] += len(caught)
        false_pos += len(fps)
        total_good += len(report.claims) - len(should_flag)
        ok = caught == should_flag and not fps
        rows.append((ok, name, kind, report))
    planted = sum(v["planted"] for v in by_kind.values())
    caught = sum(v["caught"] for v in by_kind.values())
    return {"rows": rows, "by_kind": dict(by_kind), "planted": planted, "caught": caught,
            "false_positives": false_pos, "correct_claims": total_good}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="use the Claude verifier")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    verifier = None
    if args.live:
        from seatbelt.claude_client import ClaudeVerifier
        verifier = ClaudeVerifier()

    res = evaluate(verifier)
    if args.json:
        print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=2))
        return

    for ok, name, kind, report in res["rows"]:
        print(f"{'PASS' if ok else 'MISS'}  {name:28s} [{kind}]")
        if not ok:
            for c in report.claims:
                print(f"        {c.status.value:11s} {c.text}")
                for f in c.flags:
                    print(f"            - {f.check}/{f.severity.value}: {f.message}")
    print()
    mode = "live (code checks + Claude verifier)" if args.live else "offline (code checks only)"
    print(f"Mode: {mode}")
    for kind, v in res["by_kind"].items():
        if v["planted"]:
            print(f"  {kind:14s} caught {v['caught']}/{v['planted']}")
    print(f"Planted errors caught: {res['caught']}/{res['planted']} "
          f"({100 * res['caught'] / max(res['planted'], 1):.0f}%)")
    print(f"False alarms on correct claims: {res['false_positives']}/{res['correct_claims']}")


if __name__ == "__main__":
    main()
