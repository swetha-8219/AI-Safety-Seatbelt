"""Check 3: the approval gate. Nothing is released without a recorded human decision."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from .models import Decision, Report, ReviewRecord, Status


class GateError(Exception):
    pass


class Gate:
    def __init__(self, log_path: str | Path = "seatbelt_audit.jsonl", strict: bool = True):
        self.log_path = Path(log_path)
        self.strict = strict  # strict: approving an unsupported claim needs a written reason

    def _log(self, event: str, report: Report, **data) -> None:
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event, "report_id": report.id, **data}
        with self.log_path.open("a") as f:
            f.write(json.dumps(rec) + "\n")

    def decide(self, report: Report, claim_id: str, decision: Decision | str, reviewer: str,
               note: str = "", edited_text: Optional[str] = None) -> None:
        decision = Decision(decision)
        claim = report.claim(claim_id)
        if not reviewer.strip():
            raise GateError("A reviewer name is required.")
        if (self.strict and decision == Decision.APPROVE
                and claim.status == Status.UNSUPPORTED and not note.strip()):
            raise GateError(f"Strict mode: approving unsupported claim {claim_id} needs a written reason.")
        if decision == Decision.EDIT and not (edited_text and edited_text.strip()):
            raise GateError("An edit decision needs the edited text.")
        report.reviews[claim_id] = ReviewRecord(claim_id, decision, reviewer, note, edited_text)
        report.approved = False  # any new decision re-opens the report
        self._log("decision", report, claim_id=claim_id, status=claim.status.value,
                  decision=decision.value, reviewer=reviewer, note=note, edited_text=edited_text)

    def approve(self, report: Report, reviewer: str) -> None:
        missing = [c.id for c in report.claims if c.id not in report.reviews]
        if missing:
            raise GateError(f"{len(missing)} claim(s) have no decision yet: {', '.join(missing)}")
        report.approved = True
        self._log("approved", report, reviewer=reviewer, counts=report.counts())

    def release(self, report: Report) -> str:
        """The ONLY way to get final text out. Rejected claims are dropped, edits applied."""
        if not report.approved:
            raise GateError("Report has not been approved by a human.")
        parts = []
        for c in report.claims:
            r = report.reviews[c.id]
            if r.decision == Decision.REJECT:
                continue
            parts.append(r.edited_text if r.decision == Decision.EDIT else c.text)
        text = "\n\n".join(parts)
        self._log("released", report, chars=len(text))
        return text
