import pandas as pd
import streamlit as st

from demo.app import ui
from demo.app.services import export as ex
from demo.app.services import trace_model as tm

st.title("Annotation Results")
ui.precomputed_banner()
if not ui.guard_bundle():
    st.stop()

index = ui.case_index()

st.subheader("Select a case")
mode = st.segmented_control(
    "Browse",
    ["Curated examples", "All 60 benchmark cases"],
    default="Curated examples",
    key="explorer_mode",
)
if mode == "Curated examples":
    exs = ui.examples()
    labels = {e["position"]: f"{e['category']} — {e['title']}" for e in exs}
    current = st.session_state.get("case_position")
    options = list(labels)
    pick = st.selectbox(
        "Example",
        options,
        index=options.index(current) if current in options else 0,
        format_func=lambda p: labels[p],
        key="example_pick",
    )
    st.session_state["case_position"] = pick
    st.caption(next(e["why"] for e in exs if e["position"] == pick))
    trace = ui.case(pick)
else:
    trace = ui.case_picker("explorer_case")

ui.case_header(trace)

st.markdown("##### Every system on this case")
st.dataframe(
    pd.DataFrame(tm.arm_comparison(trace)),
    hide_index=True,
    width="stretch",
    column_config={
        "Evidence score": st.column_config.NumberColumn(help="Deterministic, uncalibrated evidence heuristic", format="%.3f"),
        "Runtime (s)": st.column_config.NumberColumn(format="%.1f"),
    },
)
conf = tm.conflicts(trace)
if conf["systems_disagree"]:
    st.warning("Systems disagree on this case. See *Evidence Explorer* for the recorded measurements.", icon=":material/compare_arrows:")
if conf["amrfinder_remediation_changed_call"]:
    st.info(
        "A post-unblinding fix to the AMRFinderPlus result parser changes the specialist call for this case "
        f"(locked: {conf['amrfinder_remediation'].get('old_call')} → remediated: "
        f"{conf['amrfinder_remediation'].get('binary_call')}). The locked M60 results were not re-scored.",
        icon=":material/build:",
    )

st.markdown("##### Sequences recorded for this case")
seqs = trace.get("sequences") or {}
cols = st.columns(2)
for col, key, title in (
    (cols[0], "query_protein", "Query: curated family representative"),
    (cols[1], "candidate_protein", "Candidate protein reconstructed from the assembly"),
):
    with col:
        s = seqs.get(key)
        st.markdown(f"**{title}**")
        if s and s.get("sequence"):
            st.caption(f"{s.get('origin', '')} · {len(s['sequence'])} aa")
            st.code(f">{s.get('header', '')}\n{s['sequence']}", language=None, wrap_lines=True)
        else:
            st.write(f"{tm.NOT_AVAILABLE} — no candidate protein was reconstructed for this case.")
st.caption(
    "Assemblies are public NCBI RefSeq records and are not redistributed here; retrieve them by accession."
)

st.markdown("##### Download this case")
ui.case_downloads(trace, "explorer")

st.divider()
st.subheader("All benchmark cases")
c1, c2, c3 = st.columns(3)
targets = c1.multiselect("Target", sorted({tm.target_short(c["target"]) for c in index}))
truths = c2.multiselect("Independent truth", sorted({c["truth"] for c in index}))
outcome = c3.multiselect("GS-Agentic vs truth", ["Correct", "Incorrect", tm.NOT_EVALUATED])
df = pd.DataFrame(tm.index_table(index))
if targets:
    df = df[df["Target"].isin(targets)]
if truths:
    df = df[df["Truth"].isin(truths)]
if outcome:
    df = df[df["GS-Agentic vs truth"].isin(outcome)]
st.dataframe(
    df,
    hide_index=True,
    width="stretch",
    column_config={"Evidence score": st.column_config.NumberColumn(format="%.3f")},
)
st.caption(f"{len(df)} of {len(index)} cases shown.")
rows = ex.index_export_rows(index)
cols = st.columns(3)
cols[0].download_button("All cases (CSV)", ex.to_csv(rows), "genome_skeptic_m60_cases.csv", "text/csv", icon=":material/download:")
cols[1].download_button(
    "All cases (TSV)", ex.to_tsv(rows), "genome_skeptic_m60_cases.tsv", "text/tab-separated-values", icon=":material/download:"
)
cols[2].download_button(
    "Bundle provenance manifest (JSON)",
    ui.pretty_json(ui.bundle_json("BUNDLE_MANIFEST.json")).encode("utf-8"),
    "BUNDLE_MANIFEST.json",
    "application/json",
    icon=":material/download:",
)
ui.computational_notice()
