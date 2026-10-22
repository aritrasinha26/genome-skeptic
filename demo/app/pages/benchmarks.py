import altair as alt
import pandas as pd
import streamlit as st

from demo.app import ui

st.title("Benchmarking and Validation")
ui.precomputed_banner()
if not ui.guard_bundle():
    st.stop()


def ci_chart(df: pd.DataFrame, label: str, value: str, low: str, high: str, title: str) -> alt.Chart:
    d = df.copy()
    for c in (value, low, high):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    base = alt.Chart(d).encode(y=alt.Y(f"{label}:N", sort=None, title=None))
    bars = base.mark_bar(color="#1f5f7a", opacity=0.85).encode(
        x=alt.X(f"{value}:Q", scale=alt.Scale(domain=[0, 1]), title=title),
        tooltip=[label, alt.Tooltip(value, format=".3f"), alt.Tooltip(low, format=".3f"), alt.Tooltip(high, format=".3f")],
    )
    rule = base.mark_rule(color="#222222").encode(x=f"{low}:Q", x2=f"{high}:Q")
    return (bars + rule).properties(height=36 * len(d))


tabs = st.tabs(["M60 primary benchmark", "Agent effect", "Errors and limitations", "Role-swap study", "Development history"])

with tabs[0]:
    st.markdown(
        """
**M60** is the pre-registered held-out benchmark: 60 public RefSeq assemblies selected after the system was frozen
(commit 8f66868), with truth adjudicated independently of the systems under test. 41 cases had resolvable truth;
19 were labelled *TRUTH_UNCERTAIN* and are excluded from accuracy. None of the M60 cases were used for development.
"""
    )
    summ = ui.table("m60/tables/system_summary.csv")
    st.altair_chart(
        ci_chart(summ, "system", "accuracy", "wilson_ci_low", "wilson_ci_high", "Accuracy on 41 evaluable cases (Wilson 95% CI)"),
        width="stretch",
    )
    st.dataframe(summ[["system", "correct_over_n", "accuracy", "wilson_ci", "completion_rate"]], hide_index=True, width="stretch")

    st.markdown("##### By target")
    ts = ui.table("m60/tables/target_specific.csv")
    st.dataframe(
        ts[["target", "system", "correct", "evaluable_n", "wilson_ci", "sensitivity_denominator", "specificity_denominator"]],
        hide_index=True,
        width="stretch",
    )
    st.caption("rpoB specificity cannot be estimated: no independently resolved negative cases were present.")

    st.markdown("##### Trivial baselines")
    cb = ui.table("m60/tables/constant_baseline.csv")
    st.dataframe(cb[cb["kind"] == "baseline"][["baseline", "correct_over_n", "accuracy_wilson"]], hide_index=True)
    st.warning(
        "A constant per-target rule (always *absent* for tetA, always *present* for rpoB) scores 34/41 — one more "
        "than Genome Skeptic. On this cohort, accuracy alone does not demonstrate biological skill.",
        icon=":material/warning:",
    )
    ui.df_download(summ, "m60_system_summary.csv", "dl_summ")

with tabs[1]:
    st.markdown("##### Did the language-model agent change the answers?")
    avd = ui.table("m60/tables/agent_vs_deterministic.csv")
    get = dict(zip(avd["metric"], avd["value"]))
    c = st.columns(4)
    c[0].metric("Both correct", get.get("A_both_correct"))
    c[1].metric("Agent corrected a deterministic error", get.get("DET_ERRORS_CORRECTED_BY_AGENT"))
    c[2].metric("Agent degraded a correct call", get.get("DET_CORRECT_CALLS_DEGRADED_BY_AGENT"))
    c[3].metric("Both wrong", get.get("D_both_wrong"))
    st.caption(f"Paired comparison on 41 evaluable cases. {get.get('mcnemar_note', '')}.")

    st.markdown("##### Efficiency: agentic vs exhaustive follow-up")
    eff = ui.table("m60/tables/efficiency.csv")
    st.dataframe(
        eff[["system", "total_followup_actions", "median_actions_per_case", "median_runtime_seconds", "note"]],
        hide_index=True,
        width="stretch",
    )
    st.markdown(
        "The agent ran **67.7% fewer** follow-up analyses (61 vs 189) but took **10.6× longer** in median wall-clock "
        "time, because local inference with a 4-billion-parameter model dominates runtime."
    )
    with st.expander("Agent mechanism counts"):
        st.dataframe(ui.table("m60/tables/agent_mechanisms.csv"), hide_index=True, width="stretch")
    with st.expander("Agent vs exhaustive details"):
        st.dataframe(ui.table("m60/tables/agent_vs_exhaustive.csv"), hide_index=True, width="stretch")

with tabs[2]:
    st.markdown("##### Prediction degeneracy")
    deg = ui.table("m60/tables/prediction_degeneracy.csv")
    st.dataframe(deg, hide_index=True, width="stretch")
    st.error(
        "For tet(A)/tet(B), all three Genome Skeptic arms predicted *absent* in all 30 cases (sensitivity 0/7). "
        "This is a real failure of the frozen system, not a display artefact.",
        icon=":material/error:",
    )
    st.markdown("##### Error taxonomy (8 errors shared by all Genome Skeptic arms)")
    st.dataframe(ui.table("m60/tables/error_taxonomy.csv"), hide_index=True, width="stretch")
    st.markdown("##### Post-hoc root cause (diagnostic only, not a re-scored result)")
    st.dataframe(ui.table("m60/tables/posthoc_root_cause.csv"), hide_index=True, width="stretch")
    st.info(
        "Post-hoc analysis identified two validator defects (weak-family relabelling and an rpoB domain-only "
        "architecture rule). A counterfactual patch recovered 3 of 8 errors with no new errors. These are post-hoc "
        "diagnostics on the same cohort and are not a prospective result.",
        icon=":material/science:",
    )
    st.markdown("##### AMRFinderPlus comparator remediation")
    st.dataframe(ui.table("m60/tables/amrfinder_remediation.csv"), hide_index=True, width="stretch")
    st.caption(
        "After unblinding, a parser bug was found in the AMRFinderPlus comparator ('Element symbol' vs 'Gene symbol'). "
        "The fix changes positions 13 and 36 from NEGATIVE to POSITIVE. The locked M60 results were not re-scored."
    )
    with st.expander("Stratum results"):
        st.dataframe(ui.table("m60/tables/stratum.csv"), hide_index=True, width="stretch")
    with st.expander("Class-decomposed results"):
        st.dataframe(ui.table("m60/tables/class_decomposed.csv"), hide_index=True, width="stretch")
    with st.expander("Integrity statement (verbatim)"):
        st.markdown(ui.doc("m60/docs/M60_FINAL_INTEGRITY_STATEMENT.md"))
    with st.expander("Post-hoc manuscript interpretation (verbatim)"):
        st.markdown(ui.doc("m60/docs/POSTHOC_MANUSCRIPT_INTERPRETATION.md"))

with tabs[3]:
    st.markdown(
        """
The **role-swap study** asks who should hold decision authority. On 20 prospective tet(A)/tet(B) genomes (V5
validator), different controllers chose follow-up tests while the deterministic validator decided (arms A, B, C, F).
In arm D, a frontier model (GPT-5.6 Sol) acted as the final judge.
"""
    )
    rs = ui.table("role_swap/controller_summary.csv")
    st.dataframe(rs, hide_index=True, width="stretch")
    stats = ui.bundle_json("role_swap/statistics.json")
    st.error(
        "When the language model held decision authority (arm D), accuracy fell from 18/20 to 11/20: 0 corrections, "
        "7 degradations, McNemar P = 0.0156 (9 true absences became unresolved).",
        icon=":material/gavel:",
    )
    with st.expander("Recorded statistics (JSON)"):
        st.json(stats, expanded=False)
    with st.expander("Efficiency and cost"):
        st.dataframe(ui.table("role_swap/controller_efficiency.csv"), hide_index=True, width="stretch")
    with st.expander("Case-level results"):
        st.dataframe(ui.table("role_swap/case_level_results.csv"), hide_index=True, width="stretch")
    with st.expander("Arm definitions (verbatim)"):
        st.markdown(ui.doc("role_swap/ARM_DEFINITIONS.md"))

with tabs[4]:
    st.markdown(
        "Earlier **development mini-benchmarks** (D8, D12) were used while building the system. They are small, "
        "were not pre-registered as held-out tests, and their cases were excluded from M60. They are shown only as "
        "development history."
    )
    for name, n in (("d8", 8), ("d12", 12)):
        st.markdown(f"##### {name.upper()} (n={n})")
        st.dataframe(ui.table(f"development/{name}_system_summary.csv"), hide_index=True, width="stretch")
        with st.expander(f"{name.upper()} case-level"):
            st.dataframe(ui.table(f"development/{name}_case_level.csv"), hide_index=True, width="stretch")

ui.computational_notice()
