import json
from types import SimpleNamespace

import pytest

from seatbelt import Decision, Document, Gate, GateError, Status, check_blocks
from seatbelt.checks import extract_figures, parse_verdict
from seatbelt.claude_client import split_response
from seatbelt.review import review_cli
from evals.cases import CASES, DOCS, L1, L6, cite, fake_cite
from evals.run_evals import evaluate


# ---- checks --------------------------------------------------------------------

def test_figures_normalize_money_and_dates():
    assert extract_figures("billed $1,250.00 on 09/22/2026") == {"1250", "09/22/2026"}
    assert extract_figures("20% off 145") == {"20", "145"}


def test_good_claim_is_supported():
    r = check_blocks("t", DOCS, [("The ER visit is billed at $1,250.00 twice.", [cite(0, L1), cite(0, L6)])])
    assert r.claims[0].status == Status.SUPPORTED


def test_uncited_claim_is_unsupported():
    r = check_blocks("t", DOCS, [("The hospital overcharged you by a lot.", [])])
    assert r.claims[0].status == Status.UNSUPPORTED


def test_fabricated_passage_is_unsupported():
    r = check_blocks("t", DOCS, [("A discount was applied already.", [fake_cite(0, "Discount applied")])])
    assert r.claims[0].status == Status.UNSUPPORTED


def test_short_connective_text_is_not_a_claim():
    r = check_blocks("t", DOCS, [("Here's what", []), ("I found:", [])])
    assert r.claims == []


# ---- verifier ------------------------------------------------------------------

def test_verifier_downgrades_claim():
    deny = lambda claim, passages: ("unsupported", "passage says nothing about denial")
    r = check_blocks("t", DOCS, [("The insurer denied the ER visit.", [cite(0, L1)])], verifier=deny)
    assert r.claims[0].status == Status.UNSUPPORTED
    partial = lambda claim, passages: ("partial", "half right")
    r = check_blocks("t", DOCS, [("The insurer denied the ER visit.", [cite(0, L1)])], verifier=partial)
    assert r.claims[0].status == Status.UNCERTAIN


def test_parse_verdict_fails_closed():
    assert parse_verdict('{"verdict": "supported", "reason": "ok"}') == ("supported", "ok")
    assert parse_verdict("sure, looks fine")[0] == "unsupported"
    assert parse_verdict('{"verdict": "maybe"}')[0] == "unsupported"


# ---- API response parsing ------------------------------------------------------

def test_split_response_handles_citations_and_unsure_tail():
    blocks = [
        {"type": "text", "text": "The ER visit is billed twice. ",
         "citations": [{"type": "char_location", "document_index": 0, "cited_text": L1,
                        "start_char_index": 0, "end_char_index": 10}]},
        SimpleNamespace(type="text", text="\n\nWHAT I'M NOT SURE ABOUT:\n- whether line 6 is a second visit\n- nothing",
                        citations=None),
    ]
    out, unsure = split_response(blocks)
    assert len(out) == 1 and out[0][1][0].cited_text == L1
    assert unsure == ["whether line 6 is a second visit"]


# ---- gate ----------------------------------------------------------------------

@pytest.fixture
def report_and_gate(tmp_path):
    r = check_blocks("t", DOCS, [
        ("The ER visit is billed twice at $1,250.00.", [cite(0, L1), cite(0, L6)]),
        ("You are owed a refund of $500.00.", []),
    ])
    return r, Gate(tmp_path / "audit.jsonl", strict=True)


def test_cannot_release_without_approval(report_and_gate):
    r, g = report_and_gate
    with pytest.raises(GateError):
        g.release(r)


def test_cannot_approve_with_undecided_claims(report_and_gate):
    r, g = report_and_gate
    g.decide(r, r.claims[0].id, "approve", "shriyan")
    with pytest.raises(GateError):
        g.approve(r, "shriyan")


def test_strict_mode_needs_reason_for_unsupported(report_and_gate):
    r, g = report_and_gate
    with pytest.raises(GateError):
        g.decide(r, r.claims[1].id, "approve", "shriyan")
    g.decide(r, r.claims[1].id, "approve", "shriyan", note="confirmed by phone with billing")


def test_release_drops_rejected_and_applies_edits(report_and_gate):
    r, g = report_and_gate
    g.decide(r, r.claims[0].id, Decision.EDIT, "shriyan", edited_text="ER visit billed twice.")
    g.decide(r, r.claims[1].id, Decision.REJECT, "shriyan")
    g.approve(r, "shriyan")
    assert g.release(r) == "ER visit billed twice."
    events = [json.loads(l)["event"] for l in g.log_path.read_text().splitlines()]
    assert events == ["decision", "decision", "approved", "released"]


def test_new_decision_reopens_approved_report(report_and_gate):
    r, g = report_and_gate
    for c in r.claims:
        g.decide(r, c.id, "reject", "shriyan")
    g.approve(r, "shriyan")
    g.decide(r, r.claims[0].id, "approve", "shriyan")
    with pytest.raises(GateError):
        g.release(r)


def test_cli_review_end_to_end(report_and_gate):
    r, g = report_and_gate
    answers = iter(["a", "a", "", "r", "y"])  # 2nd claim: approve blocked (no reason) -> then reject
    out = review_cli(r, g, "shriyan", input_fn=lambda _: next(answers), print_fn=lambda *a: None)
    assert out == r.claims[0].text


# ---- eval ----------------------------------------------------------------------

def test_offline_eval_catches_all_deterministic_errors_with_no_false_alarms():
    res = evaluate(verifier=None)
    det = res["by_kind"]["deterministic"]
    assert det["caught"] == det["planted"]
    assert res["false_positives"] == 0


def test_semantic_errors_need_the_verifier():
    names = {n for n, k, *_ in CASES if k == "semantic"}
    # a perfect stub verifier stands in for Claude here
    truth = {c[2][0][0]: "unsupported" for c in CASES if c[0] in names}
    stub = lambda claim, passages: (truth.get(claim, "supported"), "stub")
    res = evaluate(verifier=stub)
    assert res["caught"] == res["planted"] and res["false_positives"] == 0
