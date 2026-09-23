#!/usr/bin/env python3
"""M60 reanalysis R1: re-score locked predictions against locked truth.

Read-only on locked inputs. Does not re-execute any arm. Does not write
POSITION_LOCKS, TRUTH_M60, or RESULTS_M60. Does not modify score_m60_phase4.py.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

MB = ROOT / "manuscript_benchmark"
TRUTH_ROOT = MB / "TRUTH_M60"
OUT = MB / "REANALYSIS_R1"
SOL56_DIR = MB / "SOL56_FULL_ABLATION"

EXPECTED = {
    "system_manifest": "97a94dfefcecc855ebbba2010fd3f02f79ae84fbc61ca0f173e718d6bffd863b",
    "scientific_core": "22ff045c65fa56fa3b00edf159902d85971c04eddd266fbb08893385044a9bb0",
    "protocol_v11": "73aebeba60e7c03390920c866541a977f86776a2711f804e0b960c08a3aa8660",
    "cohort": "014950b8af086c1148b68292276cdcc50f22844e14e1836381072dd936d51655",
    "prediction_lock": "5317b33fa554f81855fa6c68854ad732c5f5127fc0ad41f224fede9159a90791",
    "final_truth": "a64dea4fd429ede5ea543404fba71e49280495efbbf6d68dc6de324eec35a4a9",
    "final_truth_lock": "787f7a96224c2c61b21a8747bc9e9e46025b126e4b9d0f5b9dd38b4b89f54eb4",
    "git": "8f66868850a98494778966bd729b88a6fc2952eb",
    "sol56_manifest": "2a9f86956ca12026b4ff39fc7bcaf297db992ba4db53421a9482683ae1885a39",
    "sol56_case_level": "7d4854d5cef5a6b762d5a71c8e9074bfe11d0f51293731ff55b8a6bcd82bafcf",
}

SYSTEMS = ("conventional", "specialist", "gs_det", "gs_agent", "gs_exh")
SYSTEM_LABELS = {
    "conventional": "Conventional",
    "specialist": "Specialist comparator",
    "gs_det": "GS-Deterministic V4.1",
    "gs_agent": "GS-Agentic V4.1",
    "gs_exh": "GS-Exhaustive V4.1",
}
GS_ARMS = ("gs_det", "gs_agent", "gs_exh")
TARGETS = ("tetA_tetracycline_efflux", "rpoB_RNAP_beta")
NA_SPEC = "n/a (no negatives)"
N_UNCERTAIN = 19
N_RPOB_UNCERTAIN = 15
CONTROL_TOTALS = {"conventional": 20, "specialist": 34, "gs_det": 33, "gs_agent": 33, "gs_exh": 33}
CONSTANT_PER_TARGET_K = 34


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_sha256_sidecar(path: Path, extra: dict | None = None) -> str:
    digest = sha256_file(path)
    payload = {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": digest,
        "hashed_utc": utc_now(),
        "truth_opened": True,
        "d20_touched": False,
        "accuracy_scored": True,
        "post_unblind": True,
        "predictions_regenerated": False,
    }
    if extra:
        payload.update(extra)
    (path.parent / f"{path.name}.sha256.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    return digest


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})
    return write_sha256_sidecar(path)


def write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return write_sha256_sidecar(path)


def wilson_ci(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    z2 = z * z
    den = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / den
    margin = (z / den) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return (max(0.0, center - margin), min(1.0, center + margin))


def fmt_ci(ci: tuple[float, float]) -> str:
    if any(math.isnan(x) for x in ci):
        return "NA"
    return f"{ci[0]:.3f}–{ci[1]:.3f}"


def iqr(values: list[float]) -> tuple[float, float, float]:
    if not values:
        return (float("nan"), float("nan"), float("nan"))
    q1, q2, q3 = np.percentile(values, [25, 50, 75])
    return (float(q1), float(q2), float(q3))


def check(name: str, path: Path, expected: str, *, lf: bool = False) -> str:
    if not path.is_file():
        raise SystemExit(f"LOCKED INPUT MISSING {name}: {path}")
    raw = sha256_file(path)
    if lf:
        got_lf = sha256_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
        ok = raw == expected or got_lf == expected
        got = raw if raw == expected else got_lf
    else:
        ok = raw == expected
        got = raw
    if not ok:
        raise SystemExit(f"HASH MISMATCH {name}: got={raw} expected={expected}")
    return got


def verify_locks() -> dict:
    from genome_skeptic.manuscript.scientific_core import scientific_core_hashes

    rows = {}
    rows["system_manifest"] = {
        "sha256": check("system_manifest", MB / "GENOME_SKEPTIC_V4_1_MANUSCRIPT_manifest.json", EXPECTED["system_manifest"])
    }
    core = scientific_core_hashes()["scientific_core_hash"]
    if core != EXPECTED["scientific_core"]:
        raise SystemExit(f"HASH MISMATCH scientific_core: got={core}")
    rows["scientific_core"] = {"sha256": core}
    rows["protocol_v11"] = {
        "sha256": check("protocol_v11", MB / "M60_PROTOCOL_V1_1.md", EXPECTED["protocol_v11"], lf=True)
    }
    rows["cohort"] = {"sha256": check("cohort", MB / "M60_COHORT_MANIFEST.json", EXPECTED["cohort"])}
    rows["prediction_lock"] = {
        "sha256": check("prediction_lock", MB / "M60_PREDICTION_LOCK_MANIFEST.json", EXPECTED["prediction_lock"])
    }
    rows["final_truth"] = {
        "sha256": check("final_truth", TRUTH_ROOT / "M60_EXTERNAL_TRUTH_FINAL_LOCKED.json", EXPECTED["final_truth"])
    }
    rows["final_truth_lock"] = {
        "sha256": check(
            "final_truth_lock", TRUTH_ROOT / "M60_TRUTH_FINAL_LOCK_MANIFEST.json", EXPECTED["final_truth_lock"]
        )
    }
    pred_lock = load_json(MB / "M60_PREDICTION_LOCK_MANIFEST.json")
    inner = {}
    for name, expected in (pred_lock.get("file_sha256") or {}).items():
        got = sha256_file(MB / name)
        if got != expected:
            raise SystemExit(f"LOCKED PREDICTION FILE HASH MISMATCH {name}: got={got} expected={expected}")
        inner[name] = got
    if pred_lock.get("n_cases") != 60:
        raise SystemExit("prediction lock n_cases != 60")
    rows["prediction_inner_files"] = inner
    rows["sol56_manifest"] = {
        "sha256": check(
            "sol56_manifest", SOL56_DIR / "SOL56_M60_MANIFEST.json", EXPECTED["sol56_manifest"], lf=True
        )
    }
    rows["sol56_case_level"] = {
        "sha256": check(
            "sol56_case_level", SOL56_DIR / "SOL56_M60_CASE_LEVEL.csv", EXPECTED["sol56_case_level"], lf=True
        )
    }
    return rows


def gs_binary(rec: dict) -> str:
    if rec.get("ok") is False or rec.get("completion_status") not in {None, "complete"}:
        if rec.get("completion_status") == "complete":
            pass
        elif rec.get("ok") is False or rec.get("completion_status") in {"failed", "error"}:
            return "UNRESOLVED"
    fr = rec.get("final_result") or rec.get("binary_call")
    if fr == "target_gene_detected" or fr == "POSITIVE":
        return "POSITIVE"
    if fr == "target_gene_not_detected" or fr == "NEGATIVE":
        return "NEGATIVE"
    if fr in {"POSITIVE", "NEGATIVE"}:
        return fr
    return "UNRESOLVED"


def conventional_binary(rec: dict) -> str:
    if rec.get("ok") is False or rec.get("completion_status") in {"failed", "error"}:
        return "UNRESOLVED"
    return gs_binary(rec)


def specialist_binary(rec: dict) -> str:
    if rec.get("ok") is False or rec.get("completion_status") in {"failed", "error"}:
        return "UNRESOLVED"
    call = rec.get("binary_call")
    if call in {"POSITIVE", "NEGATIVE"}:
        return call
    return "UNRESOLVED"


def is_correct(truth: str, pred: str) -> bool | None:
    if truth == "TRUTH_UNCERTAIN":
        return None
    if truth in {"POSITIVE", "NEGATIVE"}:
        return pred == truth
    return None


def index_preds(payload: dict) -> dict:
    out = {}
    for rec in payload["predictions"]:
        out[rec["case_id"]] = rec
    if len(out) != 60:
        raise SystemExit(f"{payload.get('kind')} n={len(out)}")
    return out


def action_ids(rec: dict) -> list[str]:
    acts = rec.get("actions_executed")
    if acts is None or acts is False:
        return []
    if not isinstance(acts, list):
        text = str(acts).strip()
        return [text] if text else []
    out = []
    for item in acts:
        if isinstance(item, dict):
            out.append(str(item.get("action_id") or item.get("action") or item))
        else:
            text = str(item).strip()
            if text:
                out.append(text)
    return out


def display(value) -> str:
    if value is None or value == "":
        return "(null)"
    return str(value)


def mcnemar(gs_ok: list[bool], base_ok: list[bool]) -> dict:
    if len(gs_ok) != len(base_ok):
        raise SystemExit("McNemar length mismatch")
    b = sum(1 for g, c in zip(gs_ok, base_ok) if c and not g)
    c = sum(1 for g, c in zip(gs_ok, base_ok) if (not c) and g)
    net = c - b
    if b + c == 0:
        return {
            "b": b,
            "c": c,
            "net": net,
            "mcnemar_p": "",
            "mcnemar_note": "McNemar not applicable (B+C = 0)",
        }
    p = float(binomtest(c, n=b + c, p=0.5, alternative="two-sided").pvalue)
    return {
        "b": b,
        "c": c,
        "net": net,
        "mcnemar_p": f"{p:.6g}",
        "mcnemar_note": f"exact two-sided McNemar / binomial P={p:.6g} on B+C={b + c}",
    }


def constant_pred(row: dict, mode: str) -> str:
    if mode == "CONSTANT_PER_TARGET":
        return "NEGATIVE" if row["target"].startswith("tetA") else "POSITIVE"
    if mode == "CONSTANT_ALL_NEGATIVE":
        return "NEGATIVE"
    if mode == "CONSTANT_ALL_POSITIVE":
        return "POSITIVE"
    raise SystemExit(f"unknown constant mode {mode}")


def confusion(rows: list[dict], pred_key: str) -> dict:
    tp = tn = fp = fn = 0
    for r in rows:
        truth = r["truth"]
        pred = r[pred_key]
        if truth == "POSITIVE" and pred == "POSITIVE":
            tp += 1
        elif truth == "NEGATIVE" and pred == "NEGATIVE":
            tn += 1
        elif truth == "NEGATIVE" and pred != "NEGATIVE":
            fp += 1
        elif truth == "POSITIVE" and pred != "POSITIVE":
            fn += 1
    n_pos = tp + fn
    n_neg = tn + fp
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn, "n_pos": n_pos, "n_neg": n_neg}


def rate_block(k: int, n: int) -> tuple[object, object, object, str]:
    if n <= 0:
        return NA_SPEC, NA_SPEC, NA_SPEC, NA_SPEC
    acc = k / n
    ci = wilson_ci(k, n)
    return acc, ci[0], ci[1], fmt_ci(ci)


def class_row(target: str, system: str, subset: list[dict]) -> dict:
    pred_key = f"{system}_pred"
    corr_key = f"{system}_correct"
    n = len(subset)
    k = sum(1 for r in subset if r[corr_key] is True)
    acc, acc_lo, acc_hi, acc_ci = rate_block(k, n)
    cm = confusion(subset, pred_key)
    n_pos, n_neg = cm["n_pos"], cm["n_neg"]
    sens, sens_lo, sens_hi, sens_ci = rate_block(cm["tp"], n_pos)
    if n_neg <= 0:
        spec = spec_lo = spec_hi = spec_ci = NA_SPEC
    else:
        spec, spec_lo, spec_hi, spec_ci = rate_block(cm["tn"], n_neg)
    return {
        "target": target,
        "system": SYSTEM_LABELS[system],
        "system_id": system,
        "n": n,
        "correct": k,
        "accuracy": acc,
        "accuracy_wilson_low": acc_lo,
        "accuracy_wilson_high": acc_hi,
        "accuracy_wilson": acc_ci,
        "n_pos": n_pos,
        "sensitivity": sens,
        "sensitivity_wilson_low": sens_lo,
        "sensitivity_wilson_high": sens_hi,
        "sensitivity_wilson": sens_ci,
        "n_neg": n_neg,
        "specificity": spec,
        "specificity_wilson_low": spec_lo,
        "specificity_wilson_high": spec_hi,
        "specificity_wilson": spec_ci,
        "correct_over_n": f"{k}/{n}",
    }


def score_constant(eval_rows: list[dict], mode: str) -> dict:
    k = 0
    for r in eval_rows:
        pred = constant_pred(r, mode)
        if is_correct(r["truth"], pred) is True:
            k += 1
    n = len(eval_rows)
    acc, lo, hi, ci = rate_block(k, n)
    return {
        "kind": "baseline",
        "baseline": mode,
        "gs_arm": "",
        "n": n,
        "correct": k,
        "accuracy": acc,
        "accuracy_wilson_low": lo,
        "accuracy_wilson_high": hi,
        "accuracy_wilson": ci,
        "correct_over_n": f"{k}/{n}",
        "b": "",
        "c": "",
        "net": "",
        "mcnemar_p": "",
        "mcnemar_note": "",
    }


def join_ids(rows: list[dict]) -> str:
    return ";".join(f"{r['position']}:{r['case_id']}" for r in sorted(rows, key=lambda x: x["position"]))


def load_sol56() -> list[dict]:
    path = SOL56_DIR / "SOL56_M60_CASE_LEVEL.csv"
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def md_table(headers: list[str], rows: list[list[object]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def main() -> int:
    verified = verify_locks()
    print("LOCKED_INPUT_HASHES_VERIFIED = YES", flush=True)

    truth_obj = load_json(TRUTH_ROOT / "M60_EXTERNAL_TRUTH_FINAL_LOCKED.json")
    truth_cases = {c["case_id"]: c for c in truth_obj["cases"]}
    if len(truth_cases) != 60:
        raise SystemExit("truth n != 60")

    conv = index_preds(load_json(MB / "M60_CONVENTIONAL_LOCKED.json"))
    spec = index_preds(load_json(MB / "M60_SPECIALIST_COMPARATORS_LOCKED.json"))
    det = index_preds(load_json(MB / "M60_GS_DETERMINISTIC_LOCKED.json"))
    agent = index_preds(load_json(MB / "M60_GS_AGENTIC_LOCKED.json"))
    exh = index_preds(load_json(MB / "M60_GS_EXHAUSTIVE_LOCKED.json"))

    rows = []
    for cid, tcase in sorted(truth_cases.items(), key=lambda kv: int(kv[1]["position"])):
        for store, name in (
            (conv, "conventional"),
            (spec, "specialist"),
            (det, "gs_det"),
            (agent, "gs_agent"),
            (exh, "gs_exh"),
        ):
            if cid not in store:
                raise SystemExit(f"missing prediction {name} {cid}")
        c_rec, s_rec, d_rec, a_rec, e_rec = conv[cid], spec[cid], det[cid], agent[cid], exh[cid]
        if not (
            c_rec["accession"]
            == s_rec["accession"]
            == d_rec["accession"]
            == a_rec["accession"]
            == e_rec["accession"]
            == tcase["accession"]
        ):
            raise SystemExit(f"accession mismatch {cid}")
        truth = tcase["truth_value"]
        preds = {
            "conventional": conventional_binary(c_rec),
            "specialist": specialist_binary(s_rec),
            "gs_det": gs_binary(d_rec),
            "gs_agent": gs_binary(a_rec),
            "gs_exh": gs_binary(e_rec),
        }
        recs = {
            "conventional": c_rec,
            "specialist": s_rec,
            "gs_det": d_rec,
            "gs_agent": a_rec,
            "gs_exh": e_rec,
        }
        row = {
            "case_id": cid,
            "position": int(tcase["position"]),
            "accession": tcase["accession"],
            "target": tcase["target"],
            "stratum": tcase["stratum"],
            "truth": truth,
            "evaluable": truth in {"POSITIVE", "NEGATIVE"},
            "recs": recs,
        }
        for s in SYSTEMS:
            row[f"{s}_pred"] = preds[s]
            row[f"{s}_correct"] = is_correct(truth, preds[s])
        rows.append(row)

    if len(rows) != 60:
        raise SystemExit("joined n != 60")

    def n_truth(prefix: str, value: str) -> int:
        return sum(1 for r in rows if r["target"].startswith(prefix) and r["truth"] == value)

    dist = {
        "total": 60,
        "tetA_POSITIVE": n_truth("tetA", "POSITIVE"),
        "tetA_NEGATIVE": n_truth("tetA", "NEGATIVE"),
        "tetA_TRUTH_UNCERTAIN": n_truth("tetA", "TRUTH_UNCERTAIN"),
        "rpoB_POSITIVE": n_truth("rpoB", "POSITIVE"),
        "rpoB_NEGATIVE": n_truth("rpoB", "NEGATIVE"),
        "rpoB_TRUTH_UNCERTAIN": n_truth("rpoB", "TRUTH_UNCERTAIN"),
    }
    expected_dist = {
        "total": 60,
        "tetA_POSITIVE": 7,
        "tetA_NEGATIVE": 19,
        "tetA_TRUTH_UNCERTAIN": 4,
        "rpoB_POSITIVE": 15,
        "rpoB_NEGATIVE": 0,
        "rpoB_TRUTH_UNCERTAIN": 15,
    }
    if dist != expected_dist:
        raise SystemExit(f"TRUTH DISTRIBUTION MISMATCH {dist}")

    eval_rows = [r for r in rows if r["evaluable"]]
    if len(eval_rows) != 41:
        raise SystemExit(f"evaluable {len(eval_rows)} != 41")

    controls = {s: sum(1 for r in eval_rows if r[f"{s}_correct"] is True) for s in SYSTEMS}
    for s, expected_k in CONTROL_TOTALS.items():
        if controls[s] != expected_k:
            raise SystemExit(
                f"CONTROL TOTAL MISMATCH {s}: got {controls[s]}/41 expected {expected_k}/41"
            )
    print(
        "CONTROL_TOTALS_OK conventional=20/41 specialist=34/41 "
        "gs_det=33/41 gs_agent=33/41 gs_exh=33/41",
        flush=True,
    )

    OUT.mkdir(parents=True, exist_ok=True)
    output_sha = {}

    # A. class-decomposed
    class_fields = [
        "target", "system", "system_id", "n", "correct", "accuracy",
        "accuracy_wilson_low", "accuracy_wilson_high", "accuracy_wilson",
        "n_pos", "sensitivity", "sensitivity_wilson_low", "sensitivity_wilson_high",
        "sensitivity_wilson", "n_neg", "specificity", "specificity_wilson_low",
        "specificity_wilson_high", "specificity_wilson", "correct_over_n",
    ]
    class_rows = []
    for target in TARGETS:
        subset = [r for r in eval_rows if r["target"] == target]
        for s in SYSTEMS:
            class_rows.append(class_row(target, s, subset))
    output_sha["M60_CLASS_DECOMPOSED.csv"] = write_csv(
        OUT / "M60_CLASS_DECOMPOSED.csv", class_rows, class_fields
    )

    # B. constant baselines
    const_modes = ("CONSTANT_PER_TARGET", "CONSTANT_ALL_NEGATIVE", "CONSTANT_ALL_POSITIVE")
    const_rows = [score_constant(eval_rows, mode) for mode in const_modes]
    cpt = next(r for r in const_rows if r["baseline"] == "CONSTANT_PER_TARGET")
    if cpt["correct"] != CONSTANT_PER_TARGET_K:
        raise SystemExit(
            f"CONSTANT_PER_TARGET MISMATCH: got {cpt['correct']}/41 expected {CONSTANT_PER_TARGET_K}/41"
        )
    print("CONSTANT_PER_TARGET_OK 34/41", flush=True)

    cpt_ok = [is_correct(r["truth"], constant_pred(r, "CONSTANT_PER_TARGET")) is True for r in eval_rows]
    for s in GS_ARMS:
        gs_ok = [r[f"{s}_correct"] is True for r in eval_rows]
        stats = mcnemar(gs_ok, cpt_ok)
        const_rows.append(
            {
                "kind": "mcnemar_gs_vs_CONSTANT_PER_TARGET",
                "baseline": "CONSTANT_PER_TARGET",
                "gs_arm": s,
                "n": 41,
                "correct": "",
                "accuracy": "",
                "accuracy_wilson_low": "",
                "accuracy_wilson_high": "",
                "accuracy_wilson": "",
                "correct_over_n": "",
                **stats,
            }
        )
    const_fields = [
        "kind", "baseline", "gs_arm", "n", "correct", "accuracy",
        "accuracy_wilson_low", "accuracy_wilson_high", "accuracy_wilson",
        "correct_over_n", "b", "c", "net", "mcnemar_p", "mcnemar_note",
    ]
    output_sha["M60_CONSTANT_BASELINE.csv"] = write_csv(
        OUT / "M60_CONSTANT_BASELINE.csv", const_rows, const_fields
    )

    # C. prediction degeneracy (all 60)
    deg_rows = []
    for s in SYSTEMS:
        for target in TARGETS:
            subset = [r for r in rows if r["target"] == target]
            labels = [r[f"{s}_pred"] for r in subset]
            counts = Counter(labels)
            distinct = sorted(counts)
            deg_rows.append(
                {
                    "system": SYSTEM_LABELS[s],
                    "system_id": s,
                    "target": target,
                    "n_cases": len(subset),
                    "n_POSITIVE": counts.get("POSITIVE", 0),
                    "n_NEGATIVE": counts.get("NEGATIVE", 0),
                    "n_UNRESOLVED": counts.get("UNRESOLVED", 0),
                    "n_distinct_predicted_labels": len(distinct),
                    "predicted_labels": ";".join(distinct),
                }
            )
    deg_fields = [
        "system", "system_id", "target", "n_cases", "n_POSITIVE", "n_NEGATIVE",
        "n_UNRESOLVED", "n_distinct_predicted_labels", "predicted_labels",
    ]
    output_sha["M60_PREDICTION_DEGENERACY.csv"] = write_csv(
        OUT / "M60_PREDICTION_DEGENERACY.csv", deg_rows, deg_fields
    )

    # D. uncertainty bounds
    uncertain = [r for r in rows if r["truth"] == "TRUTH_UNCERTAIN"]
    if len(uncertain) != N_UNCERTAIN:
        raise SystemExit(f"TRUTH_UNCERTAIN n={len(uncertain)} != {N_UNCERTAIN}")
    rpob_unc = [r for r in uncertain if r["target"].startswith("rpoB")]
    if len(rpob_unc) != N_RPOB_UNCERTAIN:
        raise SystemExit(f"rpoB TRUTH_UNCERTAIN n={len(rpob_unc)}")

    bound_rows = []
    for s in SYSTEMS:
        k_eval = controls[s]
        for scenario, k, n, note in (
            (
                "best_uncertain_counted_correct",
                k_eval + N_UNCERTAIN,
                60,
                "41 locked-evaluable scored as locked; all 19 TRUTH_UNCERTAIN counted correct",
            ),
            (
                "worst_uncertain_counted_incorrect",
                k_eval,
                60,
                "41 locked-evaluable scored as locked; all 19 TRUTH_UNCERTAIN counted incorrect",
            ),
        ):
            acc, lo, hi, ci = rate_block(k, n)
            bound_rows.append(
                {
                    "system": SYSTEM_LABELS[s],
                    "system_id": s,
                    "scenario": scenario,
                    "k": k,
                    "n": n,
                    "accuracy": acc,
                    "accuracy_wilson_low": lo,
                    "accuracy_wilson_high": hi,
                    "accuracy_wilson": ci,
                    "correct_over_n": f"{k}/{n}",
                    "assumption": note,
                }
            )
        extra_k = 0
        for r in rpob_unc:
            assumed_ok = r[f"{s}_pred"] == "POSITIVE"
            extra_k += int(assumed_ok)
        k_assumed = k_eval + extra_k
        n_assumed = 41 + N_RPOB_UNCERTAIN
        acc, lo, hi, ci = rate_block(k_assumed, n_assumed)
        bound_rows.append(
            {
                "system": SYSTEM_LABELS[s],
                "system_id": s,
                "scenario": "rpob_uncertain_assumed_POSITIVE",
                "k": k_assumed,
                "n": n_assumed,
                "accuracy": acc,
                "accuracy_wilson_low": lo,
                "accuracy_wilson_high": hi,
                "accuracy_wilson": ci,
                "correct_over_n": f"{k_assumed}/{n_assumed}",
                "assumption": (
                    "ASSUMPTION (not a truth-file change): 15 rpoB TRUTH_UNCERTAIN "
                    "scored as if truth=POSITIVE; 4 tetA TRUTH_UNCERTAIN remain excluded; "
                    "denominator 56 = 41 locked-evaluable + 15"
                ),
            }
        )
    bound_fields = [
        "system", "system_id", "scenario", "k", "n", "accuracy",
        "accuracy_wilson_low", "accuracy_wilson_high", "accuracy_wilson",
        "correct_over_n", "assumption",
    ]
    output_sha["M60_UNCERTAINTY_BOUNDS.csv"] = write_csv(
        OUT / "M60_UNCERTAINTY_BOUNDS.csv", bound_rows, bound_fields
    )

    # E. leave position 34 out
    loo_eval = [r for r in eval_rows if r["position"] != 34]
    if len(loo_eval) != 40:
        raise SystemExit(f"LOO evaluable {len(loo_eval)} != 40")
    pos34 = [r for r in eval_rows if r["position"] == 34]
    if len(pos34) != 1 or pos34[0]["accession"] != "GCF_054953385.1":
        raise SystemExit("position 34 is not the expected tetA GCF_054953385.1 evaluable case")
    if pos34[0]["truth"] != "NEGATIVE":
        raise SystemExit(f"position 34 truth is {pos34[0]['truth']}, expected NEGATIVE")

    loo_rows = []
    for s in SYSTEMS:
        k = sum(1 for r in loo_eval if r[f"{s}_correct"] is True)
        acc, lo, hi, ci = rate_block(k, 40)
        loo_rows.append(
            {
                "table": "overall",
                "target": "pooled_40",
                "system": SYSTEM_LABELS[s],
                "system_id": s,
                "n": 40,
                "correct": k,
                "accuracy": acc,
                "accuracy_wilson_low": lo,
                "accuracy_wilson_high": hi,
                "accuracy_wilson": ci,
                "n_pos": "",
                "sensitivity": "",
                "sensitivity_wilson": "",
                "n_neg": "",
                "specificity": "",
                "specificity_wilson": "",
                "correct_over_n": f"{k}/40",
                "b": "",
                "c": "",
                "net": "",
                "mcnemar_p": "",
                "mcnemar_note": "",
            }
        )
    for target in TARGETS:
        subset = [r for r in loo_eval if r["target"] == target]
        for s in SYSTEMS:
            cr = class_row(target, s, subset)
            loo_rows.append(
                {
                    "table": "class_decomposed",
                    "target": cr["target"],
                    "system": cr["system"],
                    "system_id": cr["system_id"],
                    "n": cr["n"],
                    "correct": cr["correct"],
                    "accuracy": cr["accuracy"],
                    "accuracy_wilson_low": cr["accuracy_wilson_low"],
                    "accuracy_wilson_high": cr["accuracy_wilson_high"],
                    "accuracy_wilson": cr["accuracy_wilson"],
                    "n_pos": cr["n_pos"],
                    "sensitivity": cr["sensitivity"],
                    "sensitivity_wilson": cr["sensitivity_wilson"],
                    "n_neg": cr["n_neg"],
                    "specificity": cr["specificity"],
                    "specificity_wilson": cr["specificity_wilson"],
                    "correct_over_n": cr["correct_over_n"],
                    "b": "",
                    "c": "",
                    "net": "",
                    "mcnemar_p": "",
                    "mcnemar_note": "",
                }
            )
    for mode in const_modes:
        scored = score_constant(loo_eval, mode)
        loo_rows.append(
            {
                "table": "constant_baseline",
                "target": mode,
                "system": mode,
                "system_id": mode,
                "n": scored["n"],
                "correct": scored["correct"],
                "accuracy": scored["accuracy"],
                "accuracy_wilson_low": scored["accuracy_wilson_low"],
                "accuracy_wilson_high": scored["accuracy_wilson_high"],
                "accuracy_wilson": scored["accuracy_wilson"],
                "n_pos": "",
                "sensitivity": "",
                "sensitivity_wilson": "",
                "n_neg": "",
                "specificity": "",
                "specificity_wilson": "",
                "correct_over_n": scored["correct_over_n"],
                "b": "",
                "c": "",
                "net": "",
                "mcnemar_p": "",
                "mcnemar_note": "",
            }
        )
    cpt_ok_loo = [is_correct(r["truth"], constant_pred(r, "CONSTANT_PER_TARGET")) is True for r in loo_eval]
    for s in GS_ARMS:
        gs_ok = [r[f"{s}_correct"] is True for r in loo_eval]
        stats = mcnemar(gs_ok, cpt_ok_loo)
        loo_rows.append(
            {
                "table": "mcnemar_gs_vs_CONSTANT_PER_TARGET",
                "target": "pooled_40",
                "system": SYSTEM_LABELS[s],
                "system_id": s,
                "n": 40,
                "correct": "",
                "accuracy": "",
                "accuracy_wilson_low": "",
                "accuracy_wilson_high": "",
                "accuracy_wilson": "",
                "n_pos": "",
                "sensitivity": "",
                "sensitivity_wilson": "",
                "n_neg": "",
                "specificity": "",
                "specificity_wilson": "",
                "correct_over_n": "",
                **stats,
            }
        )
    loo_fields = [
        "table", "target", "system", "system_id", "n", "correct", "accuracy",
        "accuracy_wilson_low", "accuracy_wilson_high", "accuracy_wilson",
        "n_pos", "sensitivity", "sensitivity_wilson", "n_neg", "specificity",
        "specificity_wilson", "correct_over_n", "b", "c", "net", "mcnemar_p",
        "mcnemar_note",
    ]
    output_sha["M60_LOO_POSITION34.csv"] = write_csv(
        OUT / "M60_LOO_POSITION34.csv", loo_rows, loo_fields
    )

    # F. action counts
    action_n = {s: [len(action_ids(r["recs"][s])) for r in rows] for s in GS_ARMS}
    totals = {s: sum(action_n[s]) for s in GS_ARMS}
    act_rows = []
    for s in GS_ARMS:
        vals = action_n[s]
        q1, med, q3 = iqr([float(v) for v in vals])
        mean = statistics.mean(vals) if vals else float("nan")
        red_det = (
            100.0 * (totals["gs_det"] - totals[s]) / totals["gs_det"] if totals["gs_det"] else float("nan")
        )
        red_exh = (
            100.0 * (totals["gs_exh"] - totals[s]) / totals["gs_exh"] if totals["gs_exh"] else float("nan")
        )
        act_rows.append(
            {
                "kind": "summary",
                "system": SYSTEM_LABELS[s],
                "system_id": s,
                "n_cases": 60,
                "total_actions": totals[s],
                "mean_actions_per_case": mean,
                "median_actions_per_case": med,
                "iqr_q1": q1,
                "iqr_q3": q3,
                "reduction_vs_deterministic_percent": red_det if s != "gs_det" else "",
                "reduction_vs_exhaustive_percent": red_exh if s != "gs_exh" else "",
                "agentic_n_actions": "",
                "agentic_n_cases_with_that_count": "",
            }
        )
    for n_act, n_cases in sorted(Counter(action_n["gs_agent"]).items()):
        act_rows.append(
            {
                "kind": "agentic_per_case_distribution",
                "system": SYSTEM_LABELS["gs_agent"],
                "system_id": "gs_agent",
                "n_cases": "",
                "total_actions": "",
                "mean_actions_per_case": "",
                "median_actions_per_case": "",
                "iqr_q1": "",
                "iqr_q3": "",
                "reduction_vs_deterministic_percent": "",
                "reduction_vs_exhaustive_percent": "",
                "agentic_n_actions": n_act,
                "agentic_n_cases_with_that_count": n_cases,
            }
        )
    act_fields = [
        "kind", "system", "system_id", "n_cases", "total_actions",
        "mean_actions_per_case", "median_actions_per_case", "iqr_q1", "iqr_q3",
        "reduction_vs_deterministic_percent", "reduction_vs_exhaustive_percent",
        "agentic_n_actions", "agentic_n_cases_with_that_count",
    ]
    output_sha["M60_ACTION_COUNTS.csv"] = write_csv(
        OUT / "M60_ACTION_COUNTS.csv", act_rows, act_fields
    )

    # G. measurement-state divergence
    for r in rows:
        for s in GS_ARMS:
            rec = r["recs"][s]
            if not rec.get("m0_hash") or not rec.get("m_final_hash"):
                raise SystemExit(f"missing m0/m_final hash {s} {r['case_id']}")
    div_rows = []
    for s in GS_ARMS:
        hit = [r for r in rows if r["recs"][s]["m0_hash"] != r["recs"][s]["m_final_hash"]]
        div_rows.append(
            {
                "metric": "m0_ne_m_final",
                "arm_or_pair": s,
                "n": len(hit),
                "n_denom": 60,
                "case_ids": join_ids(hit),
            }
        )
    pair_m = (
        ("gs_det", "gs_agent", "m_final_det_ne_agent"),
        ("gs_det", "gs_exh", "m_final_det_ne_exh"),
        ("gs_agent", "gs_exh", "m_final_agent_ne_exh"),
    )
    for a, b, metric in pair_m:
        hit = [r for r in rows if r["recs"][a]["m_final_hash"] != r["recs"][b]["m_final_hash"]]
        div_rows.append(
            {
                "metric": metric,
                "arm_or_pair": f"{a}/{b}",
                "n": len(hit),
                "n_denom": 60,
                "case_ids": join_ids(hit),
            }
        )
    pair_e = (
        ("gs_det", "gs_agent", "endpoint_det_ne_agent"),
        ("gs_det", "gs_exh", "endpoint_det_ne_exh"),
        ("gs_agent", "gs_exh", "endpoint_agent_ne_exh"),
    )
    for a, b, metric in pair_e:
        hit = [r for r in rows if r[f"{a}_pred"] != r[f"{b}_pred"]]
        div_rows.append(
            {
                "metric": metric,
                "arm_or_pair": f"{a}/{b}",
                "n": len(hit),
                "n_denom": 60,
                "case_ids": join_ids(hit),
            }
        )
    any_ep = [
        r
        for r in rows
        if len({r["gs_det_pred"], r["gs_agent_pred"], r["gs_exh_pred"]}) != 1
    ]
    div_rows.append(
        {
            "metric": "endpoint_differs_any_gs_pair",
            "arm_or_pair": "gs_det/gs_agent/gs_exh",
            "n": len(any_ep),
            "n_denom": 60,
            "case_ids": join_ids(any_ep),
        }
    )
    div_fields = ["metric", "arm_or_pair", "n", "n_denom", "case_ids"]
    output_sha["M60_MEASUREMENT_STATE_DIVERGENCE.csv"] = write_csv(
        OUT / "M60_MEASUREMENT_STATE_DIVERGENCE.csv", div_rows, div_fields
    )

    # H. planner policy
    pol_rows = []
    for r in rows:
        rec = r["recs"]["gs_agent"]
        for aid in action_ids(rec):
            pol_rows.append(
                {
                    "source": "GS_AGENTIC_V4_1",
                    "facet": "actions_executed",
                    "target": r["target"],
                    "stratum": r["stratum"],
                    "field": "action_id",
                    "value": aid,
                    "count": 1,
                }
            )
        for field in ("planner_decision", "critic_verdict", "planner_grounding_status"):
            pol_rows.append(
                {
                    "source": "GS_AGENTIC_V4_1",
                    "facet": field,
                    "target": r["target"],
                    "stratum": r["stratum"],
                    "field": field,
                    "value": display(rec.get(field)),
                    "count": 1,
                }
            )
    sol_rows = load_sol56()
    if len(sol_rows) != 60:
        raise SystemExit(f"SOL56 case-level n={len(sol_rows)}")
    for rec in sol_rows:
        pol_rows.append(
            {
                "source": "SOL56_FULL_ABLATION",
                "facet": "sol_planner_action",
                "target": rec["target"],
                "stratum": rec["stratum"],
                "field": "sol_planner_action",
                "value": display(rec.get("sol_planner_action")),
                "count": 1,
            }
        )
        pol_rows.append(
            {
                "source": "SOL56_FULL_ABLATION",
                "facet": "sol_critic_disposition",
                "target": rec["target"],
                "stratum": rec["stratum"],
                "field": "sol_critic_disposition",
                "value": display(rec.get("sol_critic_disposition")),
                "count": 1,
            }
        )
    collapsed: dict[tuple, int] = Counter()
    for rec in pol_rows:
        key = (rec["source"], rec["facet"], rec["target"], rec["stratum"], rec["field"], rec["value"])
        collapsed[key] += rec["count"]
    policy_out = []
    for key, n in sorted(collapsed.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], kv[0][3], kv[0][5])):
        src, facet, target, stratum, field, value = key
        policy_out.append(
            {
                "source": src,
                "facet": facet,
                "target": target,
                "stratum": stratum,
                "field": field,
                "value": value,
                "count": n,
            }
        )
    pol_fields = ["source", "facet", "target", "stratum", "field", "value", "count"]
    output_sha["M60_PLANNER_POLICY.csv"] = write_csv(
        OUT / "M60_PLANNER_POLICY.csv", policy_out, pol_fields
    )

    # Summary markdown
    def class_md_rows(target: str) -> list[list[object]]:
        out = []
        for rec in class_rows:
            if rec["target"] != target:
                continue
            out.append(
                [
                    rec["system"],
                    rec["correct_over_n"],
                    rec["accuracy_wilson"],
                    rec["n_pos"],
                    rec["sensitivity"] if rec["sensitivity"] == NA_SPEC else f"{rec['sensitivity']:.6f}",
                    rec["sensitivity_wilson"],
                    rec["n_neg"],
                    rec["specificity"] if rec["specificity"] == NA_SPEC else f"{rec['specificity']:.6f}",
                    rec["specificity_wilson"],
                ]
            )
        return out

    md = []
    md.append("# M60 REANALYSIS R1")
    md.append("")
    md.append("Locked predictions re-scored against locked truth. No arm was re-executed.")
    md.append("")
    md.append("## Control totals (41 locked-evaluable cases)")
    md.append("")
    md.append(
        md_table(
            ["system", "correct/n"],
            [[SYSTEM_LABELS[s], f"{controls[s]}/41"] for s in SYSTEMS],
        )
    )
    md.append("")
    md.append("## A. Class-decomposed performance")
    md.append("")
    headers_a = [
        "system", "correct/n", "accuracy Wilson 95%", "n_pos", "sensitivity",
        "sens. Wilson 95%", "n_neg", "specificity", "spec. Wilson 95%",
    ]
    md.append("### tetA_tetracycline_efflux")
    md.append("")
    md.append(md_table(headers_a, class_md_rows("tetA_tetracycline_efflux")))
    md.append("")
    md.append("### rpoB_RNAP_beta")
    md.append("")
    md.append(md_table(headers_a, class_md_rows("rpoB_RNAP_beta")))
    md.append("")
    md.append("## B. Constant-baseline comparison")
    md.append("")
    md.append(
        md_table(
            ["baseline", "correct/n", "accuracy Wilson 95%"],
            [
                [r["baseline"], r["correct_over_n"], r["accuracy_wilson"]]
                for r in const_rows
                if r["kind"] == "baseline"
            ],
        )
    )
    md.append("")
    md.append("Paired 2x2 of each GS arm versus CONSTANT_PER_TARGET on the 41 evaluable cases.")
    md.append("b = CONSTANT_PER_TARGET correct and GS incorrect; c = CONSTANT_PER_TARGET incorrect and GS correct; net = c − b.")
    md.append("")
    md.append(
        md_table(
            ["GS arm", "b", "c", "net", "McNemar"],
            [
                [SYSTEM_LABELS[r["gs_arm"]], r["b"], r["c"], r["net"], r["mcnemar_note"]]
                for r in const_rows
                if r["kind"] == "mcnemar_gs_vs_CONSTANT_PER_TARGET"
            ],
        )
    )
    md.append("")
    md.append("## C. Prediction-degeneracy audit (all 60 cases)")
    md.append("")
    md.append(
        md_table(
            ["system", "target", "n", "POSITIVE", "NEGATIVE", "UNRESOLVED", "n distinct labels", "labels"],
            [
                [
                    r["system"], r["target"], r["n_cases"], r["n_POSITIVE"], r["n_NEGATIVE"],
                    r["n_UNRESOLVED"], r["n_distinct_predicted_labels"], r["predicted_labels"],
                ]
                for r in deg_rows
            ],
        )
    )
    md.append("")
    md.append("## D. Uncertain-truth bounds")
    md.append("")
    md.append(
        md_table(
            ["system", "scenario", "k/n", "Wilson 95%", "assumption"],
            [
                [r["system"], r["scenario"], r["correct_over_n"], r["accuracy_wilson"], r["assumption"]]
                for r in bound_rows
            ],
        )
    )
    md.append("")
    md.append("## E. Leave-position-34-out (40 evaluable cases)")
    md.append("")
    md.append("Position 34 = tetA GCF_054953385.1, locked truth NEGATIVE.")
    md.append("")
    md.append(
        md_table(
            ["system", "correct/n", "accuracy Wilson 95%"],
            [
                [r["system"], r["correct_over_n"], r["accuracy_wilson"]]
                for r in loo_rows
                if r["table"] == "overall"
            ],
        )
    )
    md.append("")
    md.append(
        md_table(
            ["target", "system", "correct/n", "n_pos", "sensitivity", "n_neg", "specificity"],
            [
                [
                    r["target"], r["system"], r["correct_over_n"], r["n_pos"],
                    r["sensitivity"], r["n_neg"], r["specificity"],
                ]
                for r in loo_rows
                if r["table"] == "class_decomposed"
            ],
        )
    )
    md.append("")
    md.append(
        md_table(
            ["baseline", "correct/n"],
            [
                [r["target"], r["correct_over_n"]]
                for r in loo_rows
                if r["table"] == "constant_baseline"
            ],
        )
    )
    md.append("")
    md.append(
        md_table(
            ["GS arm", "b", "c", "net", "McNemar"],
            [
                [r["system"], r["b"], r["c"], r["net"], r["mcnemar_note"]]
                for r in loo_rows
                if r["table"] == "mcnemar_gs_vs_CONSTANT_PER_TARGET"
            ],
        )
    )
    md.append("")
    md.append("## F. Follow-up action counts (len(actions_executed), all 60 cases)")
    md.append("")
    md.append(
        md_table(
            [
                "system", "total", "mean/case", "median", "IQR q1", "IQR q3",
                "reduction vs Deterministic %", "reduction vs Exhaustive %",
            ],
            [
                [
                    r["system"], r["total_actions"],
                    f"{r['mean_actions_per_case']:.6f}",
                    r["median_actions_per_case"], r["iqr_q1"], r["iqr_q3"],
                    r["reduction_vs_deterministic_percent"],
                    r["reduction_vs_exhaustive_percent"],
                ]
                for r in act_rows
                if r["kind"] == "summary"
            ],
        )
    )
    md.append("")
    md.append("GS-Agentic per-case distribution of action counts:")
    md.append("")
    md.append(
        md_table(
            ["n actions", "n cases"],
            [
                [r["agentic_n_actions"], r["agentic_n_cases_with_that_count"]]
                for r in act_rows
                if r["kind"] == "agentic_per_case_distribution"
            ],
        )
    )
    md.append("")
    md.append("## G. Measurement-state divergence")
    md.append("")
    md.append(
        md_table(
            ["metric", "arm_or_pair", "n", "n_denom"],
            [[r["metric"], r["arm_or_pair"], r["n"], r["n_denom"]] for r in div_rows],
        )
    )
    md.append("")
    md.append("## H. Planner policy")
    md.append("")
    md.append("Counts are in M60_PLANNER_POLICY.csv (source × target × stratum × field × value).")
    md.append("")
    agent_action_tot = Counter()
    agent_plan = Counter()
    agent_crit = Counter()
    agent_ground = Counter()
    sol_plan = Counter()
    sol_crit = Counter()
    for rec in policy_out:
        if rec["source"] == "GS_AGENTIC_V4_1" and rec["facet"] == "actions_executed":
            agent_action_tot[rec["value"]] += rec["count"]
        elif rec["source"] == "GS_AGENTIC_V4_1" and rec["facet"] == "planner_decision":
            agent_plan[rec["value"]] += rec["count"]
        elif rec["source"] == "GS_AGENTIC_V4_1" and rec["facet"] == "critic_verdict":
            agent_crit[rec["value"]] += rec["count"]
        elif rec["source"] == "GS_AGENTIC_V4_1" and rec["facet"] == "planner_grounding_status":
            agent_ground[rec["value"]] += rec["count"]
        elif rec["source"] == "SOL56_FULL_ABLATION" and rec["facet"] == "sol_planner_action":
            sol_plan[rec["value"]] += rec["count"]
        elif rec["source"] == "SOL56_FULL_ABLATION" and rec["facet"] == "sol_critic_disposition":
            sol_crit[rec["value"]] += rec["count"]
    md.append("GS_AGENTIC_V4_1 actions_executed (pooled):")
    md.append("")
    md.append(md_table(["action_id", "count"], [[k, v] for k, v in sorted(agent_action_tot.items())]))
    md.append("")
    md.append("GS_AGENTIC_V4_1 planner_decision (pooled):")
    md.append("")
    md.append(md_table(["planner_decision", "count"], [[k, v] for k, v in sorted(agent_plan.items())]))
    md.append("")
    md.append("GS_AGENTIC_V4_1 critic_verdict (pooled):")
    md.append("")
    md.append(md_table(["critic_verdict", "count"], [[k, v] for k, v in sorted(agent_crit.items())]))
    md.append("")
    md.append("GS_AGENTIC_V4_1 planner_grounding_status (pooled):")
    md.append("")
    md.append(md_table(["planner_grounding_status", "count"], [[k, v] for k, v in sorted(agent_ground.items())]))
    md.append("")
    md.append("SOL56 sol_planner_action (pooled):")
    md.append("")
    md.append(md_table(["sol_planner_action", "count"], [[k, v] for k, v in sorted(sol_plan.items())]))
    md.append("")
    md.append("SOL56 sol_critic_disposition (pooled):")
    md.append("")
    md.append(md_table(["sol_critic_disposition", "count"], [[k, v] for k, v in sorted(sol_crit.items())]))
    md.append("")
    md.append("## Inputs")
    md.append("")
    md.append(f"- created_utc: {utc_now()}")
    md.append(f"- final_truth SHA256: `{EXPECTED['final_truth']}`")
    md.append(f"- prediction_lock SHA256: `{EXPECTED['prediction_lock']}`")
    md.append(f"- scientific_core SHA256: `{EXPECTED['scientific_core']}`")
    md.append("")
    summary_text = "\n".join(md) + "\n"
    output_sha["M60_REANALYSIS_SUMMARY.md"] = write_text(OUT / "M60_REANALYSIS_SUMMARY.md", summary_text)

    manifest = {
        "kind": "M60_REANALYSIS_R1_MANIFEST",
        "created_utc": utc_now(),
        "post_unblind": True,
        "accuracy_scored": True,
        "predictions_regenerated": False,
        "position_locks_written": False,
        "results_m60_written": False,
        "truth_m60_written": False,
        "locked_inputs_verified": verified,
        "control_totals": {s: f"{controls[s]}/41" for s in SYSTEMS},
        "constant_per_target": f"{cpt['correct']}/41",
        "n_evaluable": 41,
        "n_loo_evaluable": 40,
        "loo_excluded": {"position": 34, "accession": "GCF_054953385.1", "target": "tetA_tetracycline_efflux"},
        "expected": EXPECTED,
        "outputs": {name: {"sha256": digest} for name, digest in output_sha.items()},
    }
    man_path = OUT / "M60_REANALYSIS_MANIFEST.json"
    man_path.write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    write_sha256_sidecar(man_path, extra={"n_outputs": len(output_sha)})
    print(f"WROTE {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
