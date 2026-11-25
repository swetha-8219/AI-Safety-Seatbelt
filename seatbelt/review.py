"""Zero-dependency terminal review. For a nicer screen, see review_app.py (Streamlit)."""
from __future__ import annotations

from .gate import Gate, GateError
from .models import Report, Status

_ICON = {Status.SUPPORTED: "OK ", Status.UNCERTAIN: "?? ", Status.UNSUPPORTED: "XX "}


def review_cli(report: Report, gate: Gate, reviewer: str, input_fn=input, print_fn=print) -> str | None:
    print_fn(f"\nTask: {report.task}\nCounts: {report.counts()}\n")
    if report.unsure_about:
        print_fn("Model says it's not sure about:")
        for u in report.unsure_about:
            print_fn(f"  - {u}")
        print_fn("")
    for c in report.claims:
        print_fn(f"[{_ICON[c.status]}{c.status.value}] {c.text}")
        for cit in c.citations:
            print_fn(f"    source ({report.documents[cit.document_index].title if 0 <= cit.document_index < len(report.documents) else '?'}): \"{cit.cited_text.strip()}\"")
        for f in c.flags:
            print_fn(f"    ! {f.check}/{f.severity.value}: {f.message}")
        while True:
            choice = input_fn("  (a)pprove / (e)dit / (r)eject? ").strip().lower()[:1]
            try:
                if choice == "a":
                    note = input_fn("  reason (required if unsupported): ") if c.status == Status.UNSUPPORTED else ""
                    gate.decide(report, c.id, "approve", reviewer, note=note)
                elif choice == "e":
                    gate.decide(report, c.id, "edit", reviewer, edited_text=input_fn("  new text: "))
                elif choice == "r":
                    gate.decide(report, c.id, "reject", reviewer)
                else:
                    continue
                break
            except GateError as e:
                print_fn(f"  blocked: {e}")
        print_fn("")
    if input_fn("Approve and release the report? (y/n) ").strip().lower().startswith("y"):
        gate.approve(report, reviewer)
        return gate.release(report)
    return None
