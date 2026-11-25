"""Planted-error eval set. Each case is a canned answer with known mistakes.

This measures the seatbelt, not the generator: we control exactly which claims are wrong,
then check whether the seatbelt flags them (and leaves the correct ones alone).

kind:  clean            -> no claim should be flagged (tests false positives)
       deterministic    -> code checks alone should catch it
       semantic         -> only the model verifier can catch it (passage is real but doesn't support the claim)
"""
from seatbelt.models import Citation, Document

BILL = Document("Hospital bill", """VALLEY GENERAL HOSPITAL - ITEMIZED STATEMENT
Patient: J. Doe    Account: 88231    Statement date: 10/14/2026
Date of service: 09/22/2026

Line 1  99284  Emergency dept visit, high severity      $1,250.00
Line 2  70450  CT head without contrast                  $2,100.00
Line 3  85025  Complete blood count                        $145.00
Line 4  85025  Complete blood count                        $145.00
Line 5  J1100  Dexamethasone injection 1mg                  $38.00
Line 6  99284  Emergency dept visit, high severity      $1,250.00

Total charges: $4,928.00
Insurance payments: $0.00
Amount due: $4,928.00   Due by 11/13/2026
""")

EOB = Document("Insurance EOB", """BLUE OAK HEALTH PLAN - EXPLANATION OF BENEFITS
Claim 55-9102   Provider: Valley General Hospital   Service date: 09/22/2026
99284 ER visit: allowed $890.00, plan paid $712.00, you owe $178.00
70450 CT head: allowed $640.00, plan paid $512.00, you owe $128.00
85025 CBC: allowed $22.00, plan paid $17.60, you owe $4.40
Claim status: processed. This is not a bill.
""")

DOCS = [BILL, EOB]


def cite(doc_index: int, passage: str, docs=DOCS) -> Citation:
    """Build a correct citation (real passage, real indices)."""
    start = docs[doc_index].text.index(passage)
    return Citation(doc_index, passage, start, start + len(passage))


def fake_cite(doc_index: int, passage: str) -> Citation:
    return Citation(doc_index, passage, None, None)


L1 = "Line 1  99284  Emergency dept visit, high severity      $1,250.00"
L3 = "Line 3  85025  Complete blood count                        $145.00"
L4 = "Line 4  85025  Complete blood count                        $145.00"
L6 = "Line 6  99284  Emergency dept visit, high severity      $1,250.00"
TOTAL = "Total charges: $4,928.00"
INS = "Insurance payments: $0.00"
DUE = "Amount due: $4,928.00   Due by 11/13/2026"
EOB_ER = "99284 ER visit: allowed $890.00, plan paid $712.00, you owe $178.00"
EOB_CT = "70450 CT head: allowed $640.00, plan paid $512.00, you owe $128.00"
EOB_STATUS = "Claim status: processed."

# Each case: (name, kind, blocks, indices of claims that SHOULD be flagged)
# blocks are (text, [citations]) exactly like the API returns them.
CASES = [
    ("clean_duplicate_er", "clean", [
        ("The ER visit (99284) is billed twice, for $1,250.00 each time.", [cite(0, L1), cite(0, L6)]),
        ("The complete blood count appears on two separate lines.", [cite(0, L3), cite(0, L4)]),
    ], set()),
    ("clean_insurance_gap", "clean", [
        ("The hospital bill shows no insurance payments.", [cite(0, INS)]),
        ("The insurer says the claim was processed.", [cite(1, EOB_STATUS)]),
        ("Under the plan you owe $178.00 for the ER visit.", [cite(1, EOB_ER)]),
    ], set()),
    ("uncited_claim", "deterministic", [
        ("The total charges are $4,928.00.", [cite(0, TOTAL)]),
        ("Hospitals in California must offer a payment plan on request.", []),
    ], {1}),
    ("fabricated_passage", "deterministic", [
        ("The hospital already applied a 20% self-pay discount.", [fake_cite(0, "Self-pay discount applied: 20%")]),
    ], {0}),
    ("wrong_amount", "deterministic", [
        ("The CT scan is billed at $2,400.00.", [cite(0, "Line 2  70450  CT head without contrast                  $2,100.00")]),
    ], {0}),
    ("amount_not_in_source", "deterministic", [
        ("You owe $3,120.00 after insurance.", [cite(0, DUE)]),
    ], {0}),
    ("wrong_date", "deterministic", [
        ("Payment is due by 12/13/2026.", [cite(0, DUE)]),
    ], {0}),
    ("number_from_wrong_passage", "deterministic", [
        ("The plan allowed $640.00 for the ER visit.", [cite(1, EOB_ER)]),
    ], {0}),
    ("wrong_location", "deterministic", [
        ("Account 88231 belongs to J. Doe.", [Citation(0, "Patient: J. Doe    Account: 88231", 0, 33)]),
    ], {0}),
    ("mixed_one_bad", "deterministic", [
        ("The ER visit is billed twice.", [cite(0, L1), cite(0, L6)]),
        ("The duplicate charges add up to $1,395.00.", [cite(0, L6), cite(0, L4)]),
        ("The insurer processed the claim.", [cite(1, EOB_STATUS)]),
    ], {1}),
    ("wrong_passage_semantic", "semantic", [
        ("The insurer denied the CT scan.", [cite(1, EOB_CT)]),
    ], {0}),
    ("overclaim_semantic", "semantic", [
        ("The hospital admitted the second ER charge was a billing error.", [cite(0, L6)]),
    ], {0}),
    ("negation_semantic", "semantic", [
        ("The EOB says this is a bill you must pay.", [cite(1, "Claim status: processed. This is not a bill.")]),
    ], {0}),
    ("unrelated_passage_semantic", "semantic", [
        ("The dexamethasone injection was not covered by the plan.", [cite(0, INS)]),
    ], {0}),
]
