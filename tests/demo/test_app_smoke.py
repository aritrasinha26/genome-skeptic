"""Start the Streamlit app headlessly and render every page."""
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from demo.app.services import live_runner as lr  # noqa: E402

APP = str(Path(__file__).resolve().parents[2] / "streamlit_app.py")
PAGES = [
    "demo/app/pages/worked_example.py",
    "demo/app/pages/overview.py",
    "demo/app/pages/case_explorer.py",
    "demo/app/pages/engine.py",
    "demo/app/pages/evidence.py",
    "demo/app/pages/benchmarks.py",
    "demo/app/pages/about.py",
]


def _run(page: str | None = None) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    if page:
        at.switch_page(page)
        at.run()
    return at


def test_app_starts_on_overview():
    at = _run()
    assert not at.exception
    assert at.title[0].value == "Genome Skeptic"


def test_worked_example_shows_prerecorded_rpob():
    at = _run("demo/app/pages/worked_example.py")
    assert not at.exception
    assert at.title[0].value == "Worked example"
    text = " ".join(i.value for i in at.info) + " " + " ".join(m.value for m in at.markdown)
    assert "Prerecorded" in text
    assert "Qwen is not running" in text
    assert "rpoB" in text or "RNA polymerase" in text


@pytest.mark.parametrize("page", PAGES)
def test_every_showcase_page_renders_without_error(page):
    at = _run(page)
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error or page.endswith("benchmarks.py")


def test_engine_page_follows_selected_case_and_arm():
    at = _run("demo/app/pages/engine.py")
    at.selectbox(key="engine_case").set_value(27).run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "Critic reviews the plan" in text
    assert "requested by critic" in text


def test_showcase_pages_are_labelled_precomputed():
    labelled = [p for p in PAGES if p.endswith(("worked_example.py", "case_explorer.py", "engine.py", "evidence.py", "benchmarks.py"))]
    for page in labelled:
        at = _run(page)
        assert any("precomputed results" in i.value for i in at.info), page


def test_live_page_without_tools_shows_unavailable_and_no_engine(monkeypatch):
    monkeypatch.setattr(lr.shutil, "which", lambda exe: None)
    import streamlit as st

    st.cache_resource.clear()
    at = _run("demo/app/pages/live.py")
    assert not at.exception
    assert any("unavailable" in w.value for w in at.warning)
    assert not any(b.label == "Run Genome Skeptic" for b in at.button)
    st.cache_resource.clear()


def test_live_page_with_tools_loads_and_validates_example(monkeypatch):
    monkeypatch.setattr(lr.shutil, "which", lambda exe: f"/usr/bin/{exe}")
    monkeypatch.setattr(lr, "_version", lambda exe: "test 1.0")
    import streamlit as st

    st.cache_resource.clear()
    at = _run("demo/app/pages/live.py")
    assert not at.exception
    assert any(m.label == "Total length" for m in at.metric)
    run_btn = next(b for b in at.button if b.label == "Run Genome Skeptic")
    assert not run_btn.disabled
    st.cache_resource.clear()
