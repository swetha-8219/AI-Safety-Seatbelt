"""seatbelt: grounding, uncertainty flags and a human approval gate for any AI output.

    from seatbelt import Document, run, Gate
    report = run("Find charges worth disputing", [Document("Bill", bill_text)])
    gate = Gate()
    ...  # review each claim (seatbelt.review CLI or review_app.py)
    gate.approve(report, "shriyan")
    final_text = gate.release(report)
"""
from .models import Citation, Claim, Decision, Document, Flag, Report, Severity, Status
from .pipeline import check_blocks, run
from .gate import Gate, GateError

__all__ = ["Citation", "Claim", "Decision", "Document", "Flag", "Report", "Severity", "Status",
           "check_blocks", "run", "Gate", "GateError"]
