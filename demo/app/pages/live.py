import pandas as pd
import streamlit as st

from demo.app import ui
from demo.app.services import export as ex
from demo.app.services import live_runner as lr
from demo.app.services import trace_model as tm
from demo.app.utils import fasta

st.title("Live Analysis")
st.markdown(
    "Run the deployed Genome Skeptic code on a bacterial genome assembly. This is **separate from the Research "
    "Showcase**: results here are computed now, are not part of any benchmark, and have no independent truth label."
)


@st.cache_resource(ttl=3600, show_spinner="Checking installed bioinformatics tools…")
def tools() -> lr.ToolReport:
    return lr.detect_tools()


with st.container(border=True):
    st.markdown("**Data handling**")
    st.markdown(
        "- Your FASTA headers are discarded and replaced with `contig_1`, `contig_2`, … before analysis, so header "
        "text cannot reach any model.\n"
        "- The sequence is written to a temporary directory on this server for the duration of the analysis and "
        "deleted afterwards. Results are kept only in your browser session.\n"
        "- Deterministic arms run locally with BLAST+, HMMER, MMseqs2 and DIAMOND and send nothing to any external "
        "service.\n"
        + (
            f"- **The agentic arm sends derived measurement summaries (evidence IDs, hit coordinates, identity, "
            f"coverage, contig numbers) — not raw sequence — to the model endpoint at `{lr.agentic_endpoint_host()}`.**"
            if lr.agentic_endpoint()
            else "- The agentic arm is not available on this deployment (no model endpoint is configured)."
        )
    )
    st.caption("Do not upload confidential or unpublished sequence data to a public deployment.")

disabled = lr.live_disabled_reason()
rep = tools()
with st.expander("Installed tools", expanded=not rep.live_ready):
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Tool": k,
                    "Required": k in lr.REQUIRED_TOOLS,
                    "Status": v or "not installed",
                }
                for k, v in rep.available.items()
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    if rep.missing_optional:
        st.caption(
            f"Optional tools missing: {', '.join(rep.missing_optional)}. Follow-up tests that need them are recorded "
            "by the pipeline as unavailable rather than substituted."
        )

if disabled or not rep.live_ready:
    st.warning(
        (disabled or f"Live analysis is unavailable here: required tools are not installed ({', '.join(rep.missing_required)}).")
        + " No substitute engine is used. The Research Showcase pages show the real locked benchmark results.",
        icon=":material/block:",
    )
    st.page_link("demo/app/pages/case_explorer.py", label="Go to the Research Showcase", icon=":material/table_view:")
    st.stop()

st.subheader("1. Choose the question")
c1, c2 = st.columns(2)
target = c1.selectbox(
    "Target gene orthologue",
    list(tm.TARGET_INFO),
    format_func=lambda t: tm.TARGET_INFO[t]["display"],
)
arms = ["GS_DETERMINISTIC_V4_1", "GS_EXHAUSTIVE_V4_1"] + (["GS_AGENTIC_V4_1"] if lr.agentic_endpoint() else [])
arm = c2.selectbox("Analysis arm", arms, format_func=lambda a: tm.ARM_LABELS[a])
st.caption(tm.TARGET_INFO[target]["endpoint"])

st.subheader("2. Provide a nucleotide assembly")
source = st.segmented_control(
    "Input", ["Example assembly", "Upload FASTA", "Paste FASTA"], default="Example assembly", key="live_source"
)
text, label, accession = None, None, None
if source == "Example assembly":
    exs = lr.example_assemblies()
    if not exs:
        st.info("No example assemblies are bundled with this deployment.")
    else:
        pick = st.selectbox(
            "Example (public NCBI RefSeq assembly from the M60 benchmark)",
            exs,
            format_func=lambda e: f"{e['organism']} ({e['accession']}) · M60 #{e['m60_position']} · "
            f"{tm.target_short(e['target'])} truth {e['independent_truth']}",
        )
        if pick["target"] != target:
            st.caption(
                f"This assembly was benchmarked for {tm.target_short(pick['target'])}. Select that target to compare "
                "with its locked result."
            )
        try:
            text = lr.load_example_text(pick["accession"])
            label, accession = f"example {pick['accession']}", pick["accession"]
        except (KeyError, ValueError):
            st.error("The example assembly could not be loaded.")
elif source == "Upload FASTA":
    up = st.file_uploader("Assembly FASTA (plain text, ≤ 15 MB)", type=[e.lstrip(".") for e in fasta.ALLOWED_EXTENSIONS])
    if up is not None:
        err = fasta.check_filename(up.name)
        if not err:
            text, err = fasta.decode_upload(up.getvalue())
        if err:
            st.error(err)
            text = None
        label = "uploaded assembly"
elif source == "Paste FASTA":
    pasted = st.text_area("Paste nucleotide FASTA", height=160, placeholder=">contig\nATGC…")
    text = pasted or None
    label = "pasted sequence"

val = fasta.validate_assembly_fasta(text) if text else None
if val is not None:
    if val.ok:
        c = st.columns(4)
        c[0].metric("Records", f"{val.n_records:,}")
        c[1].metric("Total length", f"{val.total_bp:,} bp")
        c[2].metric("GC", f"{val.gc_fraction:.1%}")
        c[3].metric("N", f"{val.n_fraction:.2%}")
        for w in val.warnings:
            st.warning(w)
    else:
        for e in val.errors:
            st.error(e)

st.subheader("3. Run")
st.caption(f"Time limit: {lr.TIMEOUT_SECONDS[arm]} s. One analysis runs at a time on this server.")
if st.button("Run Genome Skeptic", type="primary", disabled=not (val and val.ok), icon=":material/play_arrow:"):
    with st.spinner("Running BLAST+/HMMER searches and the validator… this usually takes 15–60 s."):
        try:
            res = lr.run_live(val.sanitized_fasta, target, arm)
        except lr.LiveBusy as busy:
            res = None
            st.warning(str(busy))
    if res is not None:
        st.session_state["live_result"] = {
            "result": res.payload,
            "ok": res.ok,
            "message": res.message,
            "input": {
                "label": label,
                "accession": accession,
                "n_records": val.n_records,
                "total_bp": val.total_bp,
                "sha256_sanitized": val.sha256_sanitized,
            },
        }

live = st.session_state.get("live_result")
if not live:
    st.stop()

st.divider()
st.subheader("Result")
if live["ok"]:
    st.success(f"**{ex.LIVE_MODE}**", icon=":material/bolt:")
else:
    st.error(f"The analysis did not complete: {live['message']}", icon=":material/error:")
result = live["result"] or {}
record = result.get("record")
if not live["ok"] or not record:
    st.stop()

core = result.get("core_check") or {}
if core.get("content_identical_to_frozen"):
    st.info("The deployed scientific core is content-identical to the frozen M60 system (line endings aside).", icon=":material/verified:")
else:
    st.warning(
        "The deployed scientific core **differs** from the frozen M60 system, so this result may not match what the "
        "benchmarked system would report. Differences: " + "; ".join(core.get("differences") or ["unknown"]),
        icon=":material/difference:",
    )

ui.render_claim_card(record.get("claim"))
st.caption(f"Runtime {result.get('runtime_seconds', tm.NOT_AVAILABLE)} s · arm {tm.ARM_LABELS.get(result.get('arm'), result.get('arm'))}")

live_trace = {
    "case": {"target": result.get("target"), "accession": live["input"].get("accession") or "(uploaded)", "organism": "organism not declared"},
    "arms": {result.get("arm"): record},
}

acc = live["input"].get("accession")
if acc:
    idx = next((c for c in ui.case_index() if c["accession"] == acc and c["target"] == result.get("target")), None)
    if idx:
        locked = (ui.case(idx["position"])["arms"].get(result.get("arm")) or {}).get("claim") or {}
        live_claim = record.get("claim") or {}
        st.markdown("##### Live result vs locked M60 record for the same assembly")
        st.dataframe(
            pd.DataFrame(
                [
                    {"Field": f, "Live (now)": live_claim.get(f), "Locked M60": locked.get(f), "Same": live_claim.get(f) == locked.get(f)}
                    for f in ("claim_type", "status", "confidence", "architecture_state", "homology_support")
                ]
            ),
            hide_index=True,
            width="stretch",
        )

tabs = st.tabs(["Inside the engine", "Evidence", "Downloads"])
with tabs[0]:
    ui.render_engine_steps(tm.engine_steps(live_trace, result.get("arm")))
with tabs[1]:
    ui.render_evidence(live_trace, result.get("arm"))
with tabs[2]:
    rows = ex.live_export_rows(result, live["input"])
    c = st.columns(3)
    c[0].download_button("CSV", ex.to_csv(rows), "genome_skeptic_live.csv", "text/csv", icon=":material/download:")
    c[1].download_button("TSV", ex.to_tsv(rows), "genome_skeptic_live.tsv", "text/tab-separated-values", icon=":material/download:")
    c[2].download_button(
        "Full result (JSON)",
        ex.live_json_report({**result, "input": live["input"]}),
        "genome_skeptic_live.json",
        "application/json",
        icon=":material/download:",
    )
ui.computational_notice()
