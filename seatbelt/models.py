"""Core data model: sources, claims, flags, and the report that carries them."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Status(str, Enum):
    SUPPORTED = "supported"
    UNCERTAIN = "uncertain"
    UNSUPPORTED = "unsupported"


class Severity(str, Enum):
    WARN = "warn"    # makes a claim UNCERTAIN
    ERROR = "error"  # makes a claim UNSUPPORTED


class Decision(str, Enum):
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"


@dataclass
class Document:
    title: str
    text: str


@dataclass
class Citation:
    """A passage the model says supports a claim (mirrors the API's char_location citation)."""
    document_index: int
    cited_text: str
    start_char_index: Optional[int] = None
    end_char_index: Optional[int] = None


@dataclass
class Flag:
    check: str          # which check raised it, e.g. "passage", "numbers", "verifier"
    severity: Severity
    message: str


@dataclass
class Claim:
    text: str
    citations: list[Citation] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    verdict_reason: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    @property
    def status(self) -> Status:
        if any(f.severity == Severity.ERROR for f in self.flags):
            return Status.UNSUPPORTED
        if any(f.severity == Severity.WARN for f in self.flags):
            return Status.UNCERTAIN
        return Status.SUPPORTED


@dataclass
class ReviewRecord:
    claim_id: str
    decision: Decision
    reviewer: str
    note: str = ""
    edited_text: Optional[str] = None


@dataclass
class Report:
    task: str
    documents: list[Document]
    claims: list[Claim]
    unsure_about: list[str] = field(default_factory=list)
    reviews: dict[str, ReviewRecord] = field(default_factory=dict)
    approved: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def claim(self, claim_id: str) -> Claim:
        for c in self.claims:
            if c.id == claim_id:
                return c
        raise KeyError(claim_id)

    def counts(self) -> dict[str, int]:
        out = {s.value: 0 for s in Status}
        for c in self.claims:
            out[c.status.value] += 1
        return out

    def to_dict(self) -> dict:
        d = asdict(self)
        for c, cd in zip(self.claims, d["claims"]):
            cd["status"] = c.status.value
        return d
