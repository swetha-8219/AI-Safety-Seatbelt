# AI Safety Seatbelt

A safety layer for any AI tool: every claim is tied to its source passage, anything shaky is
flagged, and nothing leaves without a human decision on record.

## The three checks

| # | Check | How | Catches |
|---|-------|-----|---------|
| 1 | Grounding | Claude citations API + code verifies each quoted passage exists at the stated location | uncited claims, made-up quotes |
| 2a | Figures | Every number, amount and date in a claim must appear in its cited passage | wrong amounts, wrong dates, figures borrowed from another line |
| 2b | Verifier | A second Claude call judges claim vs. passage (fails closed if unparseable) | real passage that doesn't actually support the claim |
| 3 | Gate | Per-claim approve / edit / reject; strict mode needs a written reason to approve an unsupported claim; `release()` is the only way out; JSONL audit log | anything reaching a person without review |

Status per claim: any error flag → **unsupported**, any warning → **uncertain**, else **supported**.

## Use

```python
from seatbelt import Document, run, Gate
from seatbelt.review import review_cli

report = run("List charges worth disputing", [Document("Bill", open("bill.txt").read())])
gate = Gate("audit.jsonl", strict=True)
final_text = review_cli(report, gate, reviewer="shriyan")   # or: streamlit run review_app.py
```

Already have output from another tool? Use `check_blocks(task, docs, blocks, verifier=...)`
with `blocks = [(text, [Citation(...)]), ...]`.

## Setup

```
pip install anthropic pytest        # + streamlit for the review screen
export ANTHROPIC_API_KEY=...
export SEATBELT_MODEL=claude-sonnet-5-5          # optional
```

## Tests and eval

```
python -m pytest                    # 16 tests, no API key needed
python -m evals.run_evals           # offline: code checks only
python -m evals.run_evals --live    # adds the Claude verifier
```

The eval plants known errors in canned answers about a hospital bill + insurance EOB and checks
which ones get flagged, plus false alarms on correct claims.

Offline baseline: **8/8 deterministic errors caught, 0/4 semantic, 0 false alarms (8/12 overall).**
The 4 semantic cases are the verifier's job; run `--live` to get the real number.

## Next steps
- Add ~8 more cases to `evals/cases.py` (target 20), especially semantic ones and tricky clean ones.
- Run `--live`, record catch rate and false alarms; tune `VERIFIER_PROMPT` if needed.
- Plug into the medical bill decoder: the decoder produces blocks, seatbelt checks and gates them.
