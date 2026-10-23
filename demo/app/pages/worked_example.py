"""Recruiter walkthrough: one real gene, prerecorded end to end."""
import pandas as pd
import streamlit as st

from demo.app import ui
from demo.app.services import trace_model as tm

ARM = "GS_AGENTIC_V4_1"


def _seq_block(title: str, record: dict | None) -> None:
    st.markdown(f"**{title}**")
    if not record or not record.get("sequence"):
        st.write(tm.NOT_AVAILABLE)
        return
    seq = record["sequence"]
    st.caption(f"{record.get('origin') or ''} · {len(seq)} amino acids")
    preview = seq[:180] + ("…" if len(seq) > 180 else "")
    st.code(f">{record.get('header') or 'sequence'}\n{preview}", language=None)
    with st.expander("Full recorded sequence"):
        st.code(f">{record.get('header') or 'sequence'}\n{seq}", language=None)


st.title("Worked example")
st.markdown(
    "Pick a real benchmark gene and read the locked record from input through the final decision. "
    "The language model chose follow-up tests only. It did not assign the annotation."
)
ui.precomputed_banner()
if not ui.guard_bundle():
    st.stop()

examples = ui.examples()
by_pos = {e["position"]: e for e in examples}
positions = [e["position"] for e in examples]
default_pos = next(e["position"] for e in examples if e["id"] == "strong_evidence")
if st.session_state.get("case_position") not in positions:
    st.session_state["case_position"] = default_pos


def _label(pos: int) -> str:
    case = ui.case(pos)["case"]
    ex = by_pos[pos]
    return f"{tm.target_short(case['target'])} — {case['organism']} · {ex['category']}"


choice = st.selectbox(
    "Example gene",
    positions,
    index=positions.index(st.session_state["case_position"]),
    format_func=_label,
    key="worked_gene",
)
st.session_state["case_position"] = choice
trace = ui.case(choice)
case = trace["case"]
rec = trace["arms"][ARM]
prov = rec.get("provenance") or {}
planner = rec.get("planner_decision") or {}
critic = rec.get("critic_review") or {}
claim = rec.get("claim") or {}
example = by_pos[choice]

st.caption(example["why"])

st.subheader("1. Input")
st.markdown(tm.biological_question(case))
info = tm.TARGET_INFO.get(case["target"], {})
st.markdown(f"**Endpoint under test:** {info.get('endpoint', tm.NOT_AVAILABLE)}")
cols = st.columns(3)
cols[0].metric("Gene", tm.target_short(case["target"]))
cols[1].metric("Assembly", case["accession"])
cols[2].metric("Organism", case["organism"])
seqs = trace.get("sequences") or {}
left, right = st.columns(2)
with left:
    _seq_block("Query protein (curated family representative)", seqs.get("query_protein"))
with right:
    _seq_block("Candidate protein reconstructed from the assembly", seqs.get("candidate_protein"))

st.subheader("2. Deterministic tool output")
st.caption("BLAST+, HMMER, MMseqs2 and DIAMOND measurements. These numbers were not written by the language model.")
ui.render_evidence(trace, ARM)

st.subheader("3. Proposed annotation")
st.caption(
    "Reading of the measurements, plus the planner's follow-up choice. "
    "The planner text is prerecorded qwen3:4b output and is not the final call."
)
fam = tm.family_summary(trace, ARM) or {}
pcols = st.columns(3)
pcols[0].metric("Architecture from tools", tm.label_or_na(fam.get("Architecture")))
pcols[1].metric("Tools support an orthologue", tm.label_or_na(fam.get("Supports orthologue")))
pcols[2].metric("Planner requested", ", ".join(planner.get("requested_actions") or []) or tm.NOT_AVAILABLE)
st.markdown("**Planner rationale (verbatim, unverified)**")
st.write(planner.get("rationale") or tm.NOT_AVAILABLE)
st.caption(
    f"Model: {prov.get('model_name') or tm.NOT_AVAILABLE}. "
    f"Grounding status: {prov.get('planner_grounding_status') or tm.NOT_AVAILABLE}."
)

st.subheader("4. Verification findings")
st.caption("Critic assessment is prerecorded model text. The falsification tests are deterministic.")
v1, v2 = st.columns(2)
v1.metric("Critic verdict", critic.get("verdict") or (prov.get("critic_challenge") or {}).get("verdict") or tm.NOT_AVAILABLE)
v2.metric("Second test triggered", prov.get("critic_second_action") or "none")
st.markdown("**Critic rationale (verbatim, unverified)**")
st.write(critic.get("rationale") or (prov.get("critic_challenge") or {}).get("rationale") or tm.NOT_AVAILABLE)
st.markdown("**Falsification attack plan**")
plan = tm.attack_plan_rows(claim)
if plan:
    st.dataframe(pd.DataFrame(plan), hide_index=True, width="stretch")
else:
    st.write(tm.NOT_AVAILABLE)

st.subheader("5. Final decision")
st.caption("Assigned by the deterministic validator. Language-model text did not supply the measurements.")
ui.render_claim_card(claim)
st.write(claim.get("statement") or tm.NOT_AVAILABLE)
dcols = st.columns(3)
dcols[0].metric("Endpoint", tm.endpoint_label(case.get("gs_agent_pred")))
dcols[1].metric("Independent truth", case.get("truth") or tm.NOT_AVAILABLE)
dcols[2].metric(
    "Versus truth",
    tm.correctness_label(case.get("gs_agent_correct"), case.get("evaluable", False)),
)
st.caption(tm.STATUS_GLOSS.get(claim.get("status"), ""))

st.page_link("demo/app/pages/engine.py", label="Open the full step trace for this case", icon=":material/account_tree:")
ui.computational_notice()
