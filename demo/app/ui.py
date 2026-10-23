"""Shared Streamlit rendering helpers for the Genome Skeptic demo."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from demo.app.services import data_loader as dl
from demo.app.services import export as ex
from demo.app.services import trace_model as tm

REPO_URL = "https://github.com/aritrasinha26/genome-skeptic"
DEMO_BRANCH = "demo/streamlit-showcase"
DEMO_URL = "https://genome-skeptic.streamlit.app"
APP_SOURCE_URL = f"{REPO_URL}/blob/{DEMO_BRANCH}/streamlit_app.py"
BENCHMARK_URL = f"{REPO_URL}/tree/main/manuscript_benchmark"

KIND_STYLE = {
    tm.KIND_CONTEXT: ("blue", ":material/help:"),
    tm.KIND_MEASUREMENT: ("green", ":material/biotech:"),
    tm.KIND_RANKER: ("gray", ":material/sort:"),
    tm.KIND_MODEL: ("violet", ":material/psychology:"),
    tm.KIND_CRITIC: ("orange", ":material/rate_review:"),
    tm.KIND_DECISION: ("red", ":material/gavel:"),
}


# ---------------------------------------------------------------------------
# Cached data access
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def case_index() -> list[dict[str, Any]]:
    return dl.load_case_index()


@st.cache_data(show_spinner=False, max_entries=64)
def case(position: int) -> dict[str, Any]:
    return dl.load_case(position)


@st.cache_data(show_spinner=False)
def examples() -> list[dict[str, Any]]:
    return dl.load_examples()


@st.cache_data(show_spinner=False)
def table(relpath: str) -> pd.DataFrame:
    return pd.DataFrame(dl.load_table(relpath))


@st.cache_data(show_spinner=False)
def doc(relpath: str) -> str:
    return dl.load_doc(relpath)


@st.cache_data(show_spinner=False)
def bundle_json(relpath: str) -> Any:
    return dl.load_bundle_json(relpath)


def guard_bundle() -> bool:
    """Show a plain message instead of a stack trace when the bundle is unavailable."""
    try:
        case_index()
        return True
    except dl.BundleError as exc:
        st.error(f"The precomputed results bundle could not be loaded ({exc}). The demo cannot show results.")
        return False


# ---------------------------------------------------------------------------
# Banners and labels
# ---------------------------------------------------------------------------

def precomputed_banner() -> None:
    st.info(
        "**Prerecorded results — Qwen is not running on this server.** "
        "These are precomputed results copied from the frozen M60 benchmark "
        "(model qwen3:4b, commit 8f66868). Planner and critic text are locked model output, not a live call.",
        icon=":material/lock:",
    )


def computational_notice() -> None:
    st.caption(
        "Computational predictions, not experimental validation. Evidence scores are deterministic, "
        "uncalibrated heuristics — not probabilities."
    )


def selected_position() -> int:
    positions = dl.case_positions()
    pos = st.session_state.get("case_position")
    if pos not in positions:
        pos = next((e["position"] for e in examples() if e["id"] == "strong_evidence"), positions[0])
        st.session_state["case_position"] = pos
    return int(pos)


def case_picker(key: str, label: str = "Benchmark case") -> dict[str, Any]:
    """Case selector shared across pages through ``st.session_state['case_position']``."""
    index = case_index()
    by_pos = {c["position"]: c for c in index}
    ex_by_pos = {e["position"]: e for e in examples()}
    positions = [c["position"] for c in index]
    current = selected_position()

    def fmt(p: int) -> str:
        tag = f" — example: {ex_by_pos[p]['category']}" if p in ex_by_pos else ""
        return tm.case_option_label(by_pos[p]) + tag

    choice = st.selectbox(label, positions, index=positions.index(current), format_func=fmt, key=key)
    if choice != current:
        st.session_state["case_position"] = choice
    return case(choice)


def case_header(trace: dict[str, Any]) -> None:
    c = trace["case"]
    st.markdown(f"#### {tm.biological_question(c)}")
    cols = st.columns(4)
    cols[0].metric("Target", tm.target_short(c["target"]))
    cols[1].metric("Independent truth", c["truth"])
    cols[2].metric("GS-Agentic endpoint", tm.endpoint_label(c.get("gs_agent_pred")))
    cols[3].metric("GS-Agentic vs truth", tm.correctness_label(c.get("gs_agent_correct"), c.get("evaluable", False)))
    st.caption(
        f"Stratum: {c['stratum']} · Assembly level: {c.get('assembly_level') or tm.NOT_AVAILABLE} · "
        f"Genome size: {_fmt_bp(c.get('genome_size'))} · {tm.TRUTH_GLOSS.get(c['truth'], c['truth'])}"
    )


def _fmt_bp(v: Any) -> str:
    try:
        return f"{int(float(v)) / 1e6:.2f} Mb"
    except (TypeError, ValueError):
        return tm.NOT_AVAILABLE


# ---------------------------------------------------------------------------
# Inside the engine
# ---------------------------------------------------------------------------

def render_engine_steps(steps: list[tm.EngineStep], *, expand_all: bool = False) -> None:
    for s in steps:
        color, icon = KIND_STYLE.get(s.kind, ("gray", ":material/circle:"))
        with st.container(border=True):
            st.badge(s.kind, color=color, icon=icon)
            st.markdown(f"**Step {s.number}. {s.title}**")
            st.write(s.summary)
            if s.kind in (tm.KIND_MODEL, tm.KIND_CRITIC):
                st.caption(
                    "Recorded model output, shown verbatim. It is an unverified model statement and did not "
                    "assign the final claim."
                )
            if s.details:
                with st.expander("Recorded details", expanded=expand_all):
                    for k, v in s.details.items():
                        st.markdown(f"**{k}**")
                        _render_value(v)


def _render_value(v: Any) -> None:
    if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
        st.dataframe(pd.DataFrame(v), hide_index=True, width="stretch")
    elif isinstance(v, (dict, list)):
        st.json(v, expanded=False)
    elif v is None:
        st.write(tm.NOT_AVAILABLE)
    else:
        st.write(v)


def render_claim_card(claim: dict[str, Any] | None) -> None:
    if not claim:
        st.warning("No claim was recorded for this run.")
        return
    status = claim.get("status")
    cols = st.columns(4)
    cols[0].metric("Claim", tm.CLAIM_TYPE_LABEL.get(claim.get("claim_type"), tm.label_or_na(claim.get("claim_type"))))
    cols[1].metric("Status", tm.label_or_na(status))
    cols[2].metric("Evidence score (uncalibrated)", tm.label_or_na(claim.get("confidence")))
    cols[3].metric("Architecture", tm.label_or_na(claim.get("architecture_state")))
    st.caption(tm.STATUS_GLOSS.get(status, ""))


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

def render_evidence(trace: dict[str, Any], arm: str) -> None:
    rec = trace["arms"][arm]
    fam = tm.family_summary(trace, arm)
    st.markdown("##### Curated-family evidence")
    if fam:
        cols = st.columns(3)
        cols[0].metric("Architecture", tm.label_or_na(fam["Architecture"]))
        cols[1].metric("Supports orthologue", tm.label_or_na(fam["Supports orthologue"]))
        cols[2].metric("Domain-only", tm.label_or_na(fam["Domain-only"]))
        metrics = fam.get("Metrics") or {}
        if metrics:
            st.dataframe(
                pd.DataFrame([{"Metric": k, "Value": v} for k, v in metrics.items()]),
                hide_index=True,
                width="stretch",
            )
        with st.expander("Evidence hierarchy, structural states and limitations"):
            st.json(
                {k: fam[k] for k in ("Evidence hierarchy reached", "Fusion / split / fragmented / paralogue", "Best HMM", "Limitations")},
                expanded=True,
            )
    else:
        st.write(f"Family-orthology evidence: {tm.NOT_AVAILABLE} for this run.")

    st.markdown("##### Hits of curated family members (protein vs translated assembly)")
    rows = tm.member_hits_table(trace, arm)
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.write("No family-member hits were recorded.")

    st.markdown("##### Target-query homology hits")
    rows = tm.hits_table(trace, arm)
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.write("No target-query hits were recorded.")

    st.markdown("##### Falsification attack plan")
    plan = tm.attack_plan_rows(rec.get("claim"))
    if plan:
        st.dataframe(pd.DataFrame(plan), hide_index=True, width="stretch")
    else:
        st.write(tm.NOT_AVAILABLE)

    with st.expander("Full evidence ledger (all recorded evidence objects)"):
        for e in rec.get("evidence") or []:
            st.markdown(f"**{e.get('id')}** · {e.get('kind', '')} · {e.get('summary', '')}")
            st.json(e.get("values") or {}, expanded=False)


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------

def case_downloads(trace: dict[str, Any], key: str) -> None:
    rows = ex.case_export_rows(trace)
    name = trace["case"]["case_id"]
    cols = st.columns(3)
    cols[0].download_button(
        "CSV", ex.to_csv(rows), file_name=f"{name}.csv", mime="text/csv", key=f"{key}_csv", icon=":material/download:"
    )
    cols[1].download_button(
        "TSV",
        ex.to_tsv(rows),
        file_name=f"{name}.tsv",
        mime="text/tab-separated-values",
        key=f"{key}_tsv",
        icon=":material/download:",
    )
    cols[2].download_button(
        "Full trace (JSON)",
        ex.case_json_report(trace),
        file_name=f"{name}.json",
        mime="application/json",
        key=f"{key}_json",
        icon=":material/download:",
    )
    st.caption(
        "Exports carry the analysis mode (precomputed), frozen commit, scientific-core hash, tool and "
        "database versions."
    )


def df_download(df: pd.DataFrame, name: str, key: str) -> None:
    st.download_button(
        f"Download {name}",
        df.to_csv(index=False).encode("utf-8"),
        file_name=name,
        mime="text/csv",
        key=key,
        icon=":material/download:",
    )


def pretty_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str)
