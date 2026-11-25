"""The checks. Deterministic ones run in code; the verifier is a second model call."""
from __future__ import annotations

import json
import re
from typing import Callable, Protocol

from .models import Claim, Document, Flag, Severity

# Short connective text ("Here's what I found:") isn't treated as a claim.
_MIN_CLAIM_WORDS = 4


def is_substantive(text: str) -> bool:
    t = text.strip()
    return bool(t) and (len(t.split()) >= _MIN_CLAIM_WORDS or bool(re.search(r"\d", t)))


# ---------- Check 1: grounding -------------------------------------------------

def check_citation_present(claim: Claim, docs: list[Document]) -> None:
    if not claim.citations:
        claim.flags.append(Flag("citation", Severity.ERROR, "No source passage cited for this claim."))


def check_passages(claim: Claim, docs: list[Document]) -> None:
    """Cited text must really exist in the source, at the indices the model gave."""
    for i, cit in enumerate(claim.citations):
        if not (0 <= cit.document_index < len(docs)):
            claim.flags.append(Flag("passage", Severity.ERROR, f"Citation {i+1} points to a document that doesn't exist."))
            continue
        src = docs[cit.document_index].text
        if cit.cited_text not in src:
            claim.flags.append(Flag("passage", Severity.ERROR,
                                    f"Citation {i+1}: quoted passage not found in '{docs[cit.document_index].title}'."))
            continue
        if cit.start_char_index is not None and cit.end_char_index is not None:
            if src[cit.start_char_index:cit.end_char_index] != cit.cited_text:
                claim.flags.append(Flag("passage", Severity.WARN,
                                        f"Citation {i+1}: passage exists but not at the stated location."))


# ---------- Check 2a: numbers, dates, amounts -----------------------------------

_NUM_RE = re.compile(
    r"\$?\d{1,3}(?:,\d{3})+(?:\.\d+)?"      # 1,234.56
    r"|\$?\d+(?:\.\d+)?%?"                   # 405, 405.00, 20%
)
_DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b")


def _norm(n: str) -> str:
    n = n.replace("$", "").replace(",", "").rstrip("%")
    if "." in n:
        n = n.rstrip("0").rstrip(".")
    return n


def extract_figures(text: str) -> set[str]:
    dates = set(_DATE_RE.findall(text))
    stripped = _DATE_RE.sub(" ", text)
    nums = {_norm(m) for m in _NUM_RE.findall(stripped)}
    return dates | {n for n in nums if n}


def check_numbers(claim: Claim, docs: list[Document]) -> None:
    """Every figure in the claim should appear in the cited passage (or at least the source)."""
    figs = extract_figures(claim.text)
    if not figs:
        return
    cited = " ".join(c.cited_text for c in claim.citations)
    cited_figs = extract_figures(cited)
    source_figs = set().union(*(extract_figures(d.text) for d in docs)) if docs else set()
    for f in sorted(figs):
        if f in cited_figs:
            continue
        if f in source_figs:
            claim.flags.append(Flag("numbers", Severity.WARN,
                                    f"'{f}' is in the source but not in the cited passage."))
        else:
            claim.flags.append(Flag("numbers", Severity.ERROR,
                                    f"'{f}' does not appear anywhere in the source."))


DETERMINISTIC_CHECKS: list[Callable[[Claim, list[Document]], None]] = [
    check_citation_present,
    check_passages,
    check_numbers,
]


# ---------- Check 2b: verifier (second model reads claim vs passage) ------------

class Verifier(Protocol):
    def __call__(self, claim_text: str, passages: list[str]) -> tuple[str, str]:
        """Return (verdict, reason); verdict in {'supported', 'partial', 'unsupported'}."""


VERIFIER_PROMPT = """You are checking whether a claim is supported by source passages.
Judge ONLY from the passages. Do not use outside knowledge.

Claim:
{claim}

Passages:
{passages}

Answer with JSON only: {{"verdict": "supported" | "partial" | "unsupported", "reason": "<one sentence>"}}
- supported: every part of the claim is stated or directly implied by the passages
- partial: some of it is supported, some is not or goes further than the passages
- unsupported: the passages don't support it, or contradict it"""


def apply_verifier(claim: Claim, verifier: Verifier) -> None:
    if not claim.citations:
        return  # already an error; nothing to verify against
    verdict, reason = verifier(claim.text, [c.cited_text for c in claim.citations])
    claim.verdict_reason = reason
    if verdict == "partial":
        claim.flags.append(Flag("verifier", Severity.WARN, f"Partly supported: {reason}"))
    elif verdict != "supported":
        claim.flags.append(Flag("verifier", Severity.ERROR, f"Not supported: {reason}"))


def parse_verdict(raw: str) -> tuple[str, str]:
    """Parse the verifier's JSON; anything unparseable is treated as unsupported (fail closed)."""
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
        verdict = str(data.get("verdict", "")).lower()
        if verdict in {"supported", "partial", "unsupported"}:
            return verdict, str(data.get("reason", ""))
    except json.JSONDecodeError:
        pass
    return "unsupported", "Verifier output could not be parsed."
