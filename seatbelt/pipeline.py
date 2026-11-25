"""Wire it together: response blocks in, checked Report out."""
from __future__ import annotations

from typing import Optional

from .checks import DETERMINISTIC_CHECKS, Verifier, apply_verifier, is_substantive
from .models import Citation, Claim, Document, Report


def check_blocks(
    task: str,
    docs: list[Document],
    blocks: list[tuple[str, list[Citation]]],
    verifier: Optional[Verifier] = None,
    unsure_about: Optional[list[str]] = None,
) -> Report:
    """Run every check on an already-generated answer. Works on canned answers too (used by evals)."""
    claims = []
    for text, cits in blocks:
        if not is_substantive(text):
            continue
        claim = Claim(text=text.strip(), citations=list(cits))
        for check in DETERMINISTIC_CHECKS:
            check(claim, docs)
        if verifier is not None:
            apply_verifier(claim, verifier)
        claims.append(claim)
    return Report(task=task, documents=docs, claims=claims, unsure_about=list(unsure_about or []))


def run(task: str, docs: list[Document], verifier: Optional[Verifier] = None, client=None) -> Report:
    """Generate with Claude (citations on), then check. Uses ClaudeVerifier unless one is passed."""
    from .claude_client import ClaudeVerifier, generate
    blocks, unsure = generate(task, docs, client=client)
    verifier = verifier or ClaudeVerifier(client=client)
    return check_blocks(task, docs, blocks, verifier=verifier, unsure_about=unsure)
