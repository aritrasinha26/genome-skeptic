"""Genome Skeptic — public research demo.

Run locally:  streamlit run streamlit_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

st.set_page_config(
    page_title="Genome Skeptic — Evidence-Grounded Agentic AI for Bacterial Genome Annotation",
    page_icon=":material/genetics:",
    layout="wide",
)

PAGES = Path("demo") / "app" / "pages"

nav = st.navigation(
    {
        "Genome Skeptic": [
            st.Page(PAGES / "overview.py", title="Overview", icon=":material/home:", default=True),
            st.Page(PAGES / "worked_example.py", title="Worked example", icon=":material/science:"),
            st.Page(PAGES / "case_explorer.py", title="Annotation Results", icon=":material/table_view:"),
            st.Page(PAGES / "engine.py", title="Inside the Annotation Engine", icon=":material/account_tree:"),
            st.Page(PAGES / "evidence.py", title="Evidence Explorer", icon=":material/biotech:"),
            st.Page(PAGES / "benchmarks.py", title="Benchmarking and Validation", icon=":material/monitoring:"),
            st.Page(PAGES / "live.py", title="Live Analysis", icon=":material/play_circle:"),
        ],
        "About": [
            st.Page(PAGES / "about.py", title="Contributions and Author", icon=":material/person:"),
        ],
    }
)

with st.sidebar:
    st.caption(
        "Research demonstration. Results shown are computational predictions from a frozen benchmark, "
        "not experimental validation."
    )
    st.link_button("View Streamlit source", "https://github.com/aritrasinha26/genome-skeptic/blob/demo/streamlit-showcase/streamlit_app.py", icon=":material/code:")
    st.link_button("GitHub repository", "https://github.com/aritrasinha26/genome-skeptic", icon=":material/folder:")
    st.link_button(
        "Explore Benchmark Results",
        "https://github.com/aritrasinha26/genome-skeptic/tree/main/manuscript_benchmark",
        icon=":material/dataset:",
    )
    st.caption("Built by Aritra Sinha · University College Cork")

nav.run()
