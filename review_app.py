"""Review screen.  pip install streamlit anthropic  &&  streamlit run review_app.py"""
import streamlit as st

from seatbelt import Document, Gate, GateError, Status, run

COLOR = {Status.SUPPORTED: "green", Status.UNCERTAIN: "orange", Status.UNSUPPORTED: "red"}

st.set_page_config(page_title="Seatbelt review", layout="wide")
st.title("Seatbelt review")

if "gate" not in st.session_state:
    st.session_state.gate = Gate("seatbelt_audit.jsonl", strict=True)
gate: Gate = st.session_state.gate

with st.sidebar:
    reviewer = st.text_input("Reviewer", value="shriyan")
    files = st.file_uploader("Source documents (.txt)", type=["txt"], accept_multiple_files=True)
    task = st.text_area("Task", "List the charges on this bill worth disputing, and why.")
    if st.button("Run", disabled=not files):
        docs = [Document(f.name, f.read().decode("utf-8", "replace")) for f in files]
        with st.spinner("Generating and checking..."):
            st.session_state.report = run(task, docs)

report = st.session_state.get("report")
if not report:
    st.info("Upload source documents and press Run.")
    st.stop()

c = report.counts()
st.write(f"**{c['supported']}** supported · **{c['uncertain']}** uncertain · **{c['unsupported']}** unsupported")
if report.unsure_about:
    st.warning("Model says it's not sure about:\n\n" + "\n".join(f"- {u}" for u in report.unsure_about))

for claim in report.claims:
    with st.container(border=True):
        st.markdown(f":{COLOR[claim.status]}[**{claim.status.value.upper()}**]  {claim.text}")
        for cit in claim.citations:
            title = report.documents[cit.document_index].title if 0 <= cit.document_index < len(report.documents) else "?"
            st.caption(f"{title}: “{cit.cited_text.strip()}”")
        for f in claim.flags:
            st.markdown(f"- ⚠️ `{f.check}` {f.message}")
        done = report.reviews.get(claim.id)
        if done:
            st.success(f"{done.decision.value} by {done.reviewer}" + (f" — {done.note}" if done.note else ""))
            continue
        cols = st.columns([1, 1, 1, 3])
        note = cols[3].text_input("Reason / edited text", key=f"n{claim.id}")
        try:
            if cols[0].button("Approve", key=f"a{claim.id}"):
                gate.decide(report, claim.id, "approve", reviewer, note=note); st.rerun()
            if cols[1].button("Edit", key=f"e{claim.id}"):
                gate.decide(report, claim.id, "edit", reviewer, edited_text=note); st.rerun()
            if cols[2].button("Reject", key=f"r{claim.id}"):
                gate.decide(report, claim.id, "reject", reviewer); st.rerun()
        except GateError as e:
            st.error(str(e))

st.divider()
if st.button("Approve report and release"):
    try:
        gate.approve(report, reviewer)
        st.text_area("Released text", gate.release(report), height=250)
    except GateError as e:
        st.error(str(e))
