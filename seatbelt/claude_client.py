"""Calls to Claude: the generator (with citations on) and the verifier.

The `anthropic` package is imported lazily so the rest of the library, the tests and
the offline eval all run without it. Install with:  pip install anthropic
"""
from __future__ import annotations

import os
from typing import Any

from .checks import VERIFIER_PROMPT, parse_verdict
from .models import Citation, Document

DEFAULT_MODEL = os.environ.get("SEATBELT_MODEL", "claude-sonnet-5-5")
VERIFIER_MODEL = os.environ.get("SEATBELT_VERIFIER_MODEL", DEFAULT_MODEL)
UNSURE_MARKER = "WHAT I'M NOT SURE ABOUT"

SYSTEM = f"""Answer only from the provided documents. Cite the documents for every factual statement.
If the documents don't say something, say so instead of guessing.
End with a section headed exactly "{UNSURE_MARKER}:" listing, one per line starting with "- ",
anything you are unsure about, anything the documents don't cover, or "- nothing" if none."""


def _client():
    import anthropic  # lazy
    return anthropic.Anthropic()


def generate(task: str, docs: list[Document], model: str = DEFAULT_MODEL, client: Any = None):
    """Return (blocks, unsure_about). blocks = list of (text, [Citation])."""
    client = client or _client()
    content = [
        {
            "type": "document",
            "source": {"type": "text", "media_type": "text/plain", "data": d.text},
            "title": d.title,
            "citations": {"enabled": True},
        }
        for d in docs
    ]
    content.append({"type": "text", "text": task})
    resp = client.messages.create(
        model=model, max_tokens=4000, system=SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    return split_response(resp.content)


def split_response(content_blocks) -> tuple[list[tuple[str, list[Citation]]], list[str]]:
    """Turn API text blocks into claim blocks + the model's 'not sure about' list."""
    blocks: list[tuple[str, list[Citation]]] = []
    tail: list[str] = []
    in_tail = False
    for b in content_blocks:
        if _get(b, "type") != "text":
            continue
        text = _get(b, "text") or ""
        if not in_tail and UNSURE_MARKER in text.upper():
            idx = text.upper().index(UNSURE_MARKER)
            before, text = text[:idx], text[idx + len(UNSURE_MARKER):]
            if before.strip():
                blocks.append((before, _citations(b)))
            in_tail = True
        if in_tail:
            tail.append(text)
        else:
            blocks.append((text, _citations(b)))
    unsure = [ln.strip().lstrip("-:• ").strip() for ln in "".join(tail).splitlines()]
    unsure = [u for u in unsure if u and u.lower() not in {"nothing", "none"}]
    return blocks, unsure


def _citations(block) -> list[Citation]:
    out = []
    for c in _get(block, "citations") or []:
        out.append(Citation(
            document_index=_get(c, "document_index") or 0,
            cited_text=_get(c, "cited_text") or "",
            start_char_index=_get(c, "start_char_index"),
            end_char_index=_get(c, "end_char_index"),
        ))
    return out


def _get(obj, key):
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


class ClaudeVerifier:
    """Second, independent call: does the passage support the claim?"""

    def __init__(self, model: str = VERIFIER_MODEL, client: Any = None):
        self.model = model
        self.client = client or _client()

    def __call__(self, claim_text: str, passages: list[str]) -> tuple[str, str]:
        joined = "\n".join(f"[{i+1}] {p}" for i, p in enumerate(passages))
        resp = self.client.messages.create(
            model=self.model, max_tokens=300,
            messages=[{"role": "user", "content": VERIFIER_PROMPT.format(claim=claim_text, passages=joined)}],
        )
        raw = "".join(_get(b, "text") or "" for b in resp.content)
        return parse_verdict(raw)
