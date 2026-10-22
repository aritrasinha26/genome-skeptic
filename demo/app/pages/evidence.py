import streamlit as st

from demo.app import ui
from demo.app.services import trace_model as tm

st.title("Biological Evidence Explorer")
ui.precomputed_banner()
if not ui.guard_bundle():
    st.stop()

trace = ui.case_picker("evidence_case")
arm = st.segmented_control(
    "Arm",
    list(tm.ARM_LABELS),
    default="GS_AGENTIC_V4_1",
    format_func=lambda a: tm.ARM_LABELS[a].split(" (")[0],
    key="evidence_arm",
) or "GS_AGENTIC_V4_1"
ui.case_header(trace)

info = tm.TARGET_INFO.get(trace["case"]["target"], {})
with st.container(border=True):
    st.markdown(f"**Target:** {info.get('display', trace['case']['target'])}")
    st.markdown(f"**Exact endpoint:** {info.get('endpoint', tm.NOT_AVAILABLE)}")
    st.markdown(f"**Competing families checked:** {info.get('competitors', tm.NOT_AVAILABLE)}")

ui.render_evidence(trace, arm)

st.markdown("##### Disagreements and open questions")
conf = tm.conflicts(trace)
st.dataframe(
    [{"System": k, "Endpoint": tm.endpoint_label(v)} for k, v in conf["predictions"].items()],
    hide_index=True,
)
cols = st.columns(3)
with cols[0]:
    st.markdown("**Alternative explanations kept open**")
    st.write(conf["alternative_explanations"] or "None recorded")
with cols[1]:
    st.markdown("**Unavailable tests**")
    st.write(conf["unavailable_tests"] or "None recorded")
with cols[2]:
    st.markdown("**Unresolved tests**")
    st.write(conf["unresolved_tests"] or "None recorded")

spec = trace.get("specialist") or {}
if spec.get("pgap_comparator"):
    with st.expander("RefSeq/PGAP comparator record"):
        st.json(spec["pgap_comparator"], expanded=False)
if trace.get("amrfinder_remediation"):
    with st.expander("AMRFinderPlus post-unblinding parser remediation"):
        st.json(trace["amrfinder_remediation"], expanded=True)

conv = trace.get("conventional") or {}
with st.expander("Conventional baseline record (≥80% identity and coverage)"):
    st.json({"claim": conv.get("claim"), "hits": conv.get("hits")}, expanded=False)
ui.computational_notice()
