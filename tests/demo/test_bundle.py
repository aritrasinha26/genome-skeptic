import json
import re

import pytest

from demo.app.services import data_loader as dl

FROZEN_GIT = "8f66868850a98494778966bd729b88a6fc2952eb"
FROZEN_CORE = "22ff045c65fa56fa3b00edf159902d85971c04eddd266fbb08893385044a9bb0"


def test_case_index_matches_m60_cohort():
    index = dl.load_case_index()
    assert len(index) == 60
    assert sorted(dl.case_positions()) == list(range(1, 61))
    assert sum(1 for c in index if c["evaluable"]) == 41
    assert sum(1 for c in index if c["truth"] == "TRUTH_UNCERTAIN") == 19


def test_every_case_loads_with_three_arms_and_frozen_provenance():
    for pos in dl.case_positions():
        trace = dl.load_case(pos)
        assert set(trace["arms"]) == {"GS_DETERMINISTIC_V4_1", "GS_AGENTIC_V4_1", "GS_EXHAUSTIVE_V4_1"}
        assert trace["frozen_system"]["git_commit"] == FROZEN_GIT
        assert trace["frozen_system"]["scientific_core_hash"] == FROZEN_CORE
        assert trace["arms"]["GS_AGENTIC_V4_1"]["claim"] is not None


def _correct(index, key):
    return sum(1 for c in index if c["evaluable"] and c[f"{key}_correct"] == "True")


def test_headline_numbers_recomputed_from_case_index_match_locked_tables():
    index = dl.load_case_index()
    summary = {r["system_id"]: int(r["correct"]) for r in dl.load_table("m60/tables/system_summary.csv")}
    for key in ("conventional", "specialist", "gs_det", "gs_agent", "gs_exh"):
        assert _correct(index, key) == summary[key], key
    assert summary == {"conventional": 20, "specialist": 34, "gs_det": 33, "gs_agent": 33, "gs_exh": 33}


def test_curated_examples_meet_their_stated_criteria():
    ex = {e["id"]: e for e in dl.load_examples()}
    assert set(ex) == {"strong_evidence", "uncertain_truth", "validator_rejects_hit", "critic_second_action"}
    strong = dl.load_case(ex["strong_evidence"]["position"])
    assert strong["case"]["truth"] == "POSITIVE" and strong["case"]["gs_agent_correct"] == "True"
    unc = dl.load_case(ex["uncertain_truth"]["position"])
    assert unc["case"]["truth"] == "TRUTH_UNCERTAIN" and not unc["case"]["evaluable"]
    rej = dl.load_case(ex["validator_rejects_hit"]["position"])["case"]
    assert rej["conventional_pred"] == "POSITIVE" and rej["gs_agent_pred"] == "NEGATIVE" and rej["truth"] == "POSITIVE"
    crit = dl.load_case(ex["critic_second_action"]["position"])
    prov = crit["arms"]["GS_AGENTIC_V4_1"]["provenance"]
    assert prov["critic_second_action"]
    assert (prov.get("critic_challenge") or {}).get("verdict") == "challenge"


def test_only_one_case_has_a_critic_second_action():
    hits = [c["position"] for c in dl.load_case_index() if c.get("critic_second_action")]
    assert hits == [27]


def test_invalid_position_and_path_escape_raise_bundle_error():
    with pytest.raises(dl.BundleError):
        dl.load_case(999)
    with pytest.raises(dl.BundleError):
        dl.load_doc("../../README.md")


_LEAKS = [
    re.compile(r"/home/aritr"),
    re.compile(r"/mnt/c/Users"),
    re.compile(r"[A-Za-z]:\\\\Users\\\\"),
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)\"(api_key|authorization|bearer)\""),
]


def test_bundle_contains_no_local_paths_endpoints_or_keys():
    for path in dl.RESULTS_DIR.rglob("*"):
        if path.suffix not in {".json", ".csv", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        for pat in _LEAKS:
            assert not pat.search(text), f"{pat.pattern} in {path.name}"


def test_manifest_lists_sources_with_hashes():
    m = dl.load_manifest()
    assert m["frozen_m60_system"] == {"git_commit": FROZEN_GIT, "scientific_core_hash": FROZEN_CORE}
    assert m["sources"] and all(len(s["sha256"]) == 64 for s in m["sources"])
    json.dumps(m)
