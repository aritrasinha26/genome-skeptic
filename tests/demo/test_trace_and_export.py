import csv
import io
import json

from demo.app.services import data_loader as dl
from demo.app.services import export as ex
from demo.app.services import trace_model as tm


def test_agentic_trace_separates_evidence_model_critic_and_decision():
    steps = tm.engine_steps(dl.load_case(27), "GS_AGENTIC_V4_1")
    kinds = [s.kind for s in steps]
    assert kinds[0] == tm.KIND_CONTEXT
    assert kinds[-1] == tm.KIND_DECISION
    assert kinds.index(tm.KIND_MODEL) < kinds.index(tm.KIND_CRITIC) < kinds.index(tm.KIND_DECISION)
    assert any("requested by critic" in s.title for s in steps)
    assert [s.number for s in steps] == list(range(1, len(steps) + 1))


def test_deterministic_trace_has_no_model_or_critic_steps():
    for arm in ("GS_DETERMINISTIC_V4_1", "GS_EXHAUSTIVE_V4_1"):
        kinds = {s.kind for s in tm.engine_steps(dl.load_case(2), arm)}
        assert tm.KIND_MODEL not in kinds and tm.KIND_CRITIC not in kinds
        assert tm.KIND_DECISION in kinds


def test_decision_step_reports_recorded_claim_values():
    trace = dl.load_case(2)
    claim = trace["arms"]["GS_AGENTIC_V4_1"]["claim"]
    final = tm.engine_steps(trace)[-1]
    assert final.details["Evidence score (uncalibrated)"] == claim["confidence"]
    assert final.details["Statement"] == claim["statement"]


def test_missing_evidence_renders_not_available():
    trace = {
        "case": {"target": "rpoB_RNAP_beta", "accession": "X", "organism": "Y", "evaluable": False},
        "arms": {"GS_DETERMINISTIC_V4_1": {"provenance": {}, "claim": None, "evidence": []}},
    }
    steps = tm.engine_steps(trace, "GS_DETERMINISTIC_V4_1")
    assert tm.NOT_AVAILABLE in steps[1].summary
    assert tm.hits_table(trace, "GS_DETERMINISTIC_V4_1") == []
    assert tm.family_summary(trace, "GS_DETERMINISTIC_V4_1") is None
    assert tm.attack_plan_rows(None) == []


def test_uncertain_truth_is_not_evaluated():
    trace = dl.load_case(3)
    assert trace["case"]["truth"] == "TRUTH_UNCERTAIN"
    rows = tm.arm_comparison(trace)
    assert {r["Correct vs truth"] for r in rows} == {tm.NOT_EVALUATED}
    for r in ex.case_export_rows(trace):
        assert r["correct_vs_truth"] == "Not evaluated"


def test_correctness_label_never_invents_values():
    assert tm.correctness_label("", True) == tm.NOT_AVAILABLE
    assert tm.correctness_label(None, True) == tm.NOT_AVAILABLE
    assert tm.correctness_label("True", False) == tm.NOT_EVALUATED
    assert tm.endpoint_label(None) == tm.NOT_AVAILABLE


def test_case_exports_are_marked_precomputed_with_provenance():
    trace = dl.load_case(13)
    rows = list(csv.DictReader(io.StringIO(ex.to_csv(ex.case_export_rows(trace)).decode("utf-8"))))
    assert len(rows) == 5
    assert all(r["analysis_mode"] == ex.PRECOMPUTED_MODE for r in rows)
    assert all(r["git_commit"] == trace["frozen_system"]["git_commit"] for r in rows)
    assert {r["system"] for r in rows} >= {"CONVENTIONAL", "GS_AGENTIC_V4_1"}
    gs = next(r for r in rows if r["system"] == "GS_AGENTIC_V4_1")
    assert float(gs["evidence_score_uncalibrated"]) == trace["arms"]["GS_AGENTIC_V4_1"]["claim"]["confidence"]

    tsv = ex.to_tsv(ex.case_export_rows(trace)).decode("utf-8").splitlines()
    assert tsv[0].split("\t")[: len(ex.CASE_COLUMNS)] == ex.CASE_COLUMNS

    payload = json.loads(ex.case_json_report(trace))
    assert payload["analysis_mode"] == ex.PRECOMPUTED_MODE
    assert "Not experimental validation" in payload["notice"]


def test_live_exports_are_marked_live_and_never_precomputed():
    result = {
        "arm": "GS_DETERMINISTIC_V4_1",
        "target": "rpoB_RNAP_beta",
        "record": {"claim": {"claim_type": "target_gene_detected", "status": "weakened", "confidence": 0.5}, "provenance": {}},
        "core_check": {"content_identical_to_frozen": False, "byte_level_scientific_core_hash": "abc"},
    }
    rows = ex.live_export_rows(result, {"label": "uploaded assembly", "sha256_sanitized": "f" * 64})
    assert rows[0]["analysis_mode"] == ex.LIVE_MODE
    assert rows[0]["independent_truth"] == "Not evaluated"
    assert rows[0]["content_identical_to_frozen_m60_core"] is False
    payload = json.loads(ex.live_json_report(result))
    assert payload["analysis_mode"] == ex.LIVE_MODE
    assert ex.LIVE_MODE != ex.PRECOMPUTED_MODE
