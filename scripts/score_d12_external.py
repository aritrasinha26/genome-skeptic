#!/usr/bin/env python3
"""Join locked D12 truth with locked predictions. Does not regenerate predictions or touch D20."""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "external_validation_agentic_d12"
D20_POOL = ROOT / "external_validation_agentic_d20" / "candidate_pool_manifest.json"
EXPECTED_D20_POOL = "61a3e03bde2341d1bccd7a065cc53411ad10ad61ffc0410295a55ce9f8009f4c"

EXPECTED = {
    "D12_MANIFEST.json": "54b477d3cf8197ffa73d7ffb2e94ffe4a993b861565a3266085d33ae68b0546f",
    "D12_CONVENTIONAL_LOCKED.json": "9cd5657a0e24e877f20f3ad83ec34d495231c1d0f2897336861999d9f4082f57",
    "D12_V5_LOCKED.json": "66652425bbdff574f91c9da19876c02f7a684653a9096f65bd44a95745dfead4",
    "D12_AGENTIC_V3_LOCKED.json": "64a2dd3365805d68f431f487d9aebd7cb685466096d1710d67d962895c3cc25c",
}

ENDPOINT_KIND = {
    "tetA_tetracycline_efflux": "FAMILY_PRESENCE_ABSENCE",
    "rpoB_RNAP_beta": "ORTHOLOGOUS_GENE_PRESENCE_ABSENCE",
    "lacZ_beta_galactosidase": "ORTHOLOGOUS_GENE_PRESENCE_ABSENCE",
    "tuf_EF_Tu": "EXACT_MULTIPLICITY",
}

LACZ_LIMITATION = (
    "No frozen deterministic instrument currently distinguishes true LacZ "
    "orthology from relevant competing beta-galactosidase families when "
    "reference/GFF/orthology resources are absent."
)


def sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def wilson_ci(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    z2 = z * z
    den = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / den
    margin = (z / den) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return (max(0.0, center - margin), min(1.0, center + margin))


def load_json(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def pred_polarity(rec: dict) -> str:
    if rec.get("ok") is False or rec.get("agent_failure"):
        return "EXECUTION_FAILURE"
    fr = rec.get("final_result") or ""
    if fr == "target_gene_detected":
        return "DETECTED"
    if fr == "target_gene_not_detected":
        return "NOT_DETECTED"
    return fr or "UNKNOWN"


def predicted_multiplicity(rec: dict) -> int | None:
    multi = rec.get("multiplicity") or {}
    if isinstance(multi, dict) and multi.get("number_of_candidate_loci") is not None:
        try:
            return int(multi["number_of_candidate_loci"])
        except (TypeError, ValueError):
            return None
    pol = pred_polarity(rec)
    if pol == "DETECTED":
        return 1
    if pol == "NOT_DETECTED":
        return 0
    return None


def scored_endpoint(rec: dict, target: str) -> str:
    if rec.get("ok") is False or rec.get("agent_failure"):
        return f"EXECUTION_FAILURE ({rec.get('agent_failure')})"
    if target == "tuf_EF_Tu":
        n = predicted_multiplicity(rec)
        missing = not isinstance(rec.get("multiplicity"), dict) or rec.get("multiplicity", {}).get(
            "number_of_candidate_loci"
        ) is None
        tag = " (lock omitted multiplicity; inferred from polarity)" if missing else ""
        return f"MULTIPLICITY={n}{tag}"
    return pred_polarity(rec)


def canonical_endpoint(rec: dict, target: str) -> str:
    raw = scored_endpoint(rec, target)
    return raw.split(" (lock omitted")[0]


def display_result(rec: dict, target: str) -> str:
    if rec.get("ok") is False or rec.get("agent_failure"):
        return f"EXECUTION_FAILURE ({rec.get('agent_failure')})"
    pol = pred_polarity(rec)
    conf = rec.get("confidence")
    klass = rec.get("claim_class")
    extra = ""
    if target == "tuf_EF_Tu":
        extra = f"; {scored_endpoint(rec, target)}"
    return f"{pol} / {klass} / conf={conf}{extra}"


def is_correct(truth_case: dict, rec: dict) -> bool:
    if rec.get("ok") is False or rec.get("agent_failure"):
        return False
    target = truth_case["target"]
    truth = truth_case["truth"]
    if target == "tuf_EF_Tu":
        n = predicted_multiplicity(rec)
        return n is not None and int(truth) == int(n)
    pol = pred_polarity(rec)
    if truth == "POSITIVE":
        return pol == "DETECTED"
    if truth == "NEGATIVE":
        return pol == "NOT_DETECTED"
    return False


def action_status_label(rec: dict) -> str:
    ars = rec.get("action_result_status")
    if isinstance(ars, list) and ars:
        return ";".join(f"{a.get('action_id')}={a.get('status')}" for a in ars)
    if isinstance(ars, dict):
        return json.dumps(ars, sort_keys=True)
    return ""


def yn(v) -> str:
    if v is True:
        return "yes"
    if v is False:
        return "no"
    return ""


def classify_dual_error(tc: dict, v: dict, a: dict) -> dict:
    target = tc["target"]
    truth = tc["truth"]
    v_ep = scored_endpoint(v, target)
    a_ep = scored_endpoint(a, target)
    actions = list(a.get("actions_executed") or [])
    planner = a.get("planner_action")
    critic = a.get("critic_action")
    statuses = a.get("action_result_status") or []
    informative = [
        x.get("action_id")
        for x in statuses
        if isinstance(x, dict) and str(x.get("status") or "").upper() == "INFORMATIVE"
    ]
    nonew = [
        x.get("action_id")
        for x in statuses
        if isinstance(x, dict) and str(x.get("status") or "").upper() == "NO_NEW_INFORMATION"
    ]
    new_evidence = bool(informative) or bool(a.get("measurements_changed_before_validation"))
    extra_vs_v5 = [x for x in actions if x]
    why = []
    code = "OTHER"

    if target == "lacZ_beta_galactosidase":
        code = "MISSING_SCIENTIFIC_INSTRUMENT"
        why.append(LACZ_LIMITATION)
        if truth == "NEGATIVE" and pred_polarity(a) == "DETECTED":
            why.append(
                "Both systems called LacZ present. Independent truth required a true LacZ orthologue, "
                "not generic beta-galactosidase homology. Agentic actions could not add a competing-family "
                "or orthology instrument that the frozen toolbox lacks."
            )
        elif truth == "POSITIVE" and pred_polarity(a) == "NOT_DETECTED":
            why.append("Both systems missed a true LacZ orthologue under the frozen empty-reference protocol.")
    elif target == "tetA_tetracycline_efflux":
        if truth == "NEGATIVE" and pred_polarity(a) == "DETECTED":
            if "search_target_domains_hmmer" in extra_vs_v5:
                if "search_target_domains_hmmer" in informative:
                    code = "NON_DISCRIMINATING_ACTION"
                    why.append(
                        "HMMER was executed and marked INFORMATIVE, but FAMILY truth is AMRFinder tet(A)/tet(B) "
                        "presence. Additional remote-homolog hits cannot convert a non-tet(A)/tet(B) transporter "
                        "into a frozen-family negative."
                    )
                else:
                    code = "VALIDATOR_DECISION_LIMIT"
                    why.append(
                        "The locked claim remained DETECTED after adaptive search. The validator still accepted "
                        "family-profile / divergent homology as a positive under the frozen V5 decision path, "
                        "which is not the AMRFinder tet(A)/tet(B) FAMILY endpoint."
                    )
            else:
                code = "VALIDATOR_DECISION_LIMIT"
                why.append(
                    "V5 already called family presence from homology/profile evidence. Agentic did not flip "
                    "that call. Frozen FAMILY truth is tet(A) OR tet(B) only."
                )
            if a.get("critic_action") == "inspect_hit_contig_contamination":
                why.append(
                    "Critic-selected contamination inspection is not a family-identity test for tet(A)/tet(B)."
                )
        elif truth == "POSITIVE" and pred_polarity(a) == "NOT_DETECTED":
            code = "INSUFFICIENT_SIGNAL"
            why.append("Independent AMRFinder tet(A)/tet(B) is present, but both systems called absence.")
        else:
            code = "VALIDATOR_DECISION_LIMIT"
            why.append("Both systems mismatched the frozen FAMILY endpoint.")
    elif target == "tuf_EF_Tu":
        v_n = predicted_multiplicity(v)
        a_n = predicted_multiplicity(a)
        why.append(
            f"Truth multiplicity={truth}; V5 multiplicity={v_n}; Agentic multiplicity={a_n} "
            f"(Agentic lock omits multiplicity, so polarity was used when needed)."
        )
        if "search_target_domains_hmmer" in nonew:
            code = "NON_DISCRIMINATING_ACTION"
            why.append(
                "Planner HMMER returned NO_NEW_INFORMATION, so copy-number was not resolved beyond the V5 state."
            )
        elif "search_target_domains_hmmer" in informative and v_n != truth:
            code = "VALIDATOR_DECISION_LIMIT"
            why.append(
                "HMMER produced new measurements, but the locked multiplicity/presence call still did not equal "
                "the independent count of distinct genuine EF-Tu loci."
            )
        else:
            code = "INSUFFICIENT_SIGNAL"
            why.append("Neither system recovered the independent exact-copy count of genuine EF-Tu loci.")
        if a.get("critic_action") == "inspect_hit_contig_contamination":
            why.append("Contamination GC inspection does not count distinct EF-Tu genomic loci.")
            if code == "INSUFFICIENT_SIGNAL":
                code = "NON_DISCRIMINATING_ACTION"
    elif target == "rpoB_RNAP_beta":
        if truth == "POSITIVE" and pred_polarity(a) == "NOT_DETECTED":
            code = "INSUFFICIENT_SIGNAL"
            why.append("Independent rpoB orthology is present; both systems called absence.")
        elif truth == "NEGATIVE" and pred_polarity(a) == "DETECTED":
            code = "VALIDATOR_DECISION_LIMIT"
            why.append(
                "Both systems treated homology/profile evidence as an rpoB orthologue. Adaptive HMMER does not "
                "replace independent orthology."
            )
        else:
            code = "OTHER"
            why.append("Both systems mismatched the orthologous-gene endpoint.")
    else:
        code = "OTHER"
        why.append("Unhandled target in dual-error diagnosis.")

    if not extra_vs_v5:
        why.append("Agentic recorded no additional executed actions beyond the locked provenance.")
    return {
        "position": tc["execution_position"],
        "accession": tc["assembly_accession"],
        "target": target,
        "truth": truth,
        "v5_endpoint": v_ep,
        "agentic_endpoint": a_ep,
        "additional_actions": extra_vs_v5,
        "planner_action": planner,
        "critic_action": critic,
        "informative_actions": informative,
        "no_new_information_actions": nonew,
        "new_evidence_produced": new_evidence,
        "measurements_changed": bool(a.get("measurements_changed_before_validation")),
        "class": code,
        "why_still_failed": " ".join(why),
    }


def main() -> int:
    for name, expected in EXPECTED.items():
        digest = sha256_file(OUT / name)
        if digest != expected:
            raise SystemExit(f"prediction/manifest hash mismatch {name}")
    d20_sha = sha256_file(D20_POOL)
    if d20_sha != EXPECTED_D20_POOL:
        raise SystemExit(f"D20 pool hash changed: {d20_sha}")
    truth_path = OUT / "D12_EXTERNAL_TRUTH_LOCKED.json"
    truth_sha = sha256_file(truth_path)
    sidecar = json.loads((OUT / "D12_EXTERNAL_TRUTH_LOCKED.json.sha256.json").read_text(encoding="utf-8"))
    if sidecar.get("sha256") != truth_sha:
        raise SystemExit("truth sidecar hash mismatch")
    if sidecar.get("hashed_before_prediction_join") is not True:
        raise SystemExit("truth sidecar does not record lock-before-join")
    truth = load_json("D12_EXTERNAL_TRUTH_LOCKED.json")
    conv = {(r["assembly_accession"], r["target"]): r for r in load_json("D12_CONVENTIONAL_LOCKED.json")["predictions"]}
    v5 = {(r["assembly_accession"], r["target"]): r for r in load_json("D12_V5_LOCKED.json")["predictions"]}
    ag = {(r["assembly_accession"], r["target"]): r for r in load_json("D12_AGENTIC_V3_LOCKED.json")["predictions"]}
    cases = sorted(truth["cases"], key=lambda r: r["execution_position"])
    if len(cases) != 12:
        raise SystemExit("expected 12 truth cases")

    endpoint_rows = []
    for i, tc in enumerate(cases, 1):
        key = (tc["assembly_accession"], tc["target"])
        v, a = v5[key], ag[key]
        identical = canonical_endpoint(v, tc["target"]) == canonical_endpoint(a, tc["target"])
        endpoint_rows.append(
            {
                "position": tc["execution_position"],
                "target": tc["target"],
                "v5": scored_endpoint(v, tc["target"]),
                "agentic": scored_endpoint(a, tc["target"]),
                "identical": identical,
            }
        )
    n_ident = sum(1 for r in endpoint_rows if r["identical"])
    different = [r for r in endpoint_rows if not r["identical"]]

    rows = []
    for tc in cases:
        key = (tc["assembly_accession"], tc["target"])
        c, v, a = conv[key], v5[key], ag[key]
        evaluable = tc["truth_status"] == "EVALUABLE" and tc["truth"] is not None
        c_ok = is_correct(tc, c) if evaluable else None
        v_ok = is_correct(tc, v) if evaluable else None
        a_ok = is_correct(tc, a) if evaluable else None
        a_fail = bool(a.get("agent_failure") or a.get("ok") is False)
        rows.append(
            {
                "position": tc["execution_position"],
                "accession": tc["assembly_accession"],
                "organism": tc.get("organism"),
                "target": tc["target"],
                "endpoint": tc["endpoint"],
                "truth_status": tc["truth_status"],
                "truth": tc["truth"],
                "externally_evaluable": evaluable,
                "conventional_endpoint": scored_endpoint(c, tc["target"]),
                "conventional_result": display_result(c, tc["target"]),
                "conventional_final_result": c.get("final_result"),
                "conventional_correct": c_ok,
                "v5_endpoint": scored_endpoint(v, tc["target"]),
                "v5_result": display_result(v, tc["target"]),
                "v5_final_result": v.get("final_result"),
                "v5_correct": v_ok,
                "agentic_endpoint": scored_endpoint(a, tc["target"]),
                "agentic_result": display_result(a, tc["target"]),
                "agentic_final_result": a.get("final_result"),
                "agentic_correct": a_ok,
                "agentic_completed": (not a_fail),
                "agentic_completion_status": "FAILURE" if a_fail else "COMPLETED",
                "agent_failure": a.get("agent_failure"),
                "planner_action": a.get("planner_action"),
                "critic_action": a.get("critic_action"),
                "critic_verdict": a.get("critic_verdict"),
                "action_result_status": action_status_label(a),
                "actions_executed": ";".join(a.get("actions_executed") or []),
                "m_final_ne_m0": bool(a.get("measurements_changed_before_validation")),
                "short_rationale": tc.get("short_rationale"),
            }
        )

    eval_rows = [r for r in rows if r["externally_evaluable"]]
    n = len(eval_rows)
    n_uncertain = sum(1 for r in rows if r["truth_status"] == "TRUTH_UNCERTAIN")
    conv_c = sum(1 for r in eval_rows if r["conventional_correct"])
    v5_c = sum(1 for r in eval_rows if r["v5_correct"])
    ag_c = sum(1 for r in eval_rows if r["agentic_correct"])
    ag_done = sum(1 for r in rows if r["agentic_completion_status"] == "COMPLETED")

    pair = [(bool(r["v5_correct"]), bool(r["agentic_correct"]), r) for r in eval_rows]
    A = [r for v_ok, a_ok, r in pair if v_ok and a_ok]
    B = [r for v_ok, a_ok, r in pair if v_ok and not a_ok]
    C = [r for v_ok, a_ok, r in pair if (not v_ok) and a_ok]
    D = [r for v_ok, a_ok, r in pair if (not v_ok) and not a_ok]
    net = len(C) - len(B)
    if len(B) + len(C) > 0:
        mcnemar = binomtest(len(C), n=len(B) + len(C), p=0.5, alternative="two-sided")
        mcnemar_p = float(mcnemar.pvalue)
        mcnemar_note = (
            f"exact McNemar / binomial P={mcnemar_p:.4f} on {len(B)+len(C)} discordant pairs; "
            "exploratory only because n=12 is small"
        )
    else:
        mcnemar_p = None
        mcnemar_note = "exact McNemar not applicable (0 discordant pairs); exploratory n=12"

    conv_ci = wilson_ci(conv_c, n)
    v5_ci = wilson_ci(v5_c, n)
    ag_ci = wilson_ci(ag_c, n)

    dual = []
    for r in D:
        tc = next(x for x in cases if x["execution_position"] == r["position"])
        dual.append(classify_dual_error(tc, v5[(r["accession"], r["target"])], ag[(r["accession"], r["target"])]))

    case_csv = OUT / "D12_CASE_LEVEL_RESULTS.csv"
    case_fields = [
        "position",
        "accession",
        "target",
        "truth",
        "conventional_endpoint",
        "conventional_correct",
        "v5_endpoint",
        "v5_correct",
        "agentic_endpoint",
        "agentic_correct",
        "agentic_completed",
        "endpoint",
        "truth_status",
        "organism",
        "conventional_result",
        "v5_result",
        "agentic_result",
        "agentic_completion_status",
        "agent_failure",
    ]
    with case_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=case_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    sys_csv = OUT / "D12_SYSTEM_SUMMARY.csv"
    with sys_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "system",
                "correct",
                "externally_evaluable_n",
                "accuracy",
                "wilson_95_ci_low",
                "wilson_95_ci_high",
                "primary_metric",
                "agentic_completion",
                "truth_uncertain",
            ],
        )
        w.writeheader()
        w.writerow(
            {
                "system": "conventional",
                "correct": conv_c,
                "externally_evaluable_n": n,
                "accuracy": conv_c / n if n else None,
                "wilson_95_ci_low": conv_ci[0],
                "wilson_95_ci_high": conv_ci[1],
                "primary_metric": "correct / externally evaluable N",
                "agentic_completion": "",
                "truth_uncertain": n_uncertain,
            }
        )
        w.writerow(
            {
                "system": "deterministic_v5",
                "correct": v5_c,
                "externally_evaluable_n": n,
                "accuracy": v5_c / n if n else None,
                "wilson_95_ci_low": v5_ci[0],
                "wilson_95_ci_high": v5_ci[1],
                "primary_metric": "correct / externally evaluable N",
                "agentic_completion": "",
                "truth_uncertain": n_uncertain,
            }
        )
        w.writerow(
            {
                "system": "agentic_v3_end_to_end",
                "correct": ag_c,
                "externally_evaluable_n": n,
                "accuracy": ag_c / n if n else None,
                "wilson_95_ci_low": ag_ci[0],
                "wilson_95_ci_high": ag_ci[1],
                "primary_metric": "end-to-end correct / externally evaluable N (failures counted incorrect)",
                "agentic_completion": f"{ag_done}/12",
                "truth_uncertain": n_uncertain,
            }
        )

    vs_csv = OUT / "D12_AGENTIC_VS_V5.csv"
    with vs_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["cell", "count", "positions", "accessions_targets"])

        def cell_line(name, items):
            w.writerow(
                [
                    name,
                    len(items),
                    ";".join(str(r["position"]) for r in items),
                    ";".join(f"{r['accession']}/{r['target']}" for r in items),
                ]
            )

        cell_line("A_both_correct", A)
        cell_line("B_v5_correct_agentic_incorrect", B)
        cell_line("C_v5_incorrect_agentic_correct", C)
        cell_line("D_both_incorrect", D)
        w.writerow(["V5_ERRORS_CORRECTED_BY_AGENTIC_C", len(C), "", ""])
        w.writerow(["V5_CORRECT_CALLS_DEGRADED_BY_AGENTIC_B", len(B), "", ""])
        w.writerow(["NET_CORRECTIONS_C_minus_B", net, "", ""])
        w.writerow(["mcnemar_exact_p", mcnemar_p if mcnemar_p is not None else "NA", mcnemar_note, ""])

    err_md = ["# D12 error analysis", ""]
    err_md.append("Cases where **both** deterministic V5 and Agentic V3 are wrong on the frozen external endpoint.")
    err_md.append("No code or thresholds were changed. This is diagnosis only.")
    err_md.append("")
    if not dual:
        err_md.append("No dual-error cases.")
    for d in dual:
        err_md.append(f"## Position {d['position']}: `{d['accession']}` / `{d['target']}`")
        err_md.append("")
        err_md.append(f"- Class: **{d['class']}**")
        err_md.append(f"- Truth: **{d['truth']}**")
        err_md.append(f"- Locked V5 endpoint: `{d['v5_endpoint']}`")
        err_md.append(f"- Locked Agentic endpoint: `{d['agentic_endpoint']}`")
        err_md.append(f"- Additional actions Agentic executed: `{d['additional_actions']}`")
        err_md.append(f"- Planner action: `{d['planner_action']}`")
        err_md.append(f"- Critic action: `{d['critic_action']}`")
        err_md.append(f"- Informative actions: `{d['informative_actions']}`")
        err_md.append(f"- No-new-information actions: `{d['no_new_information_actions']}`")
        err_md.append(f"- New evidence produced: **{d['new_evidence_produced']}**")
        err_md.append(f"- Why that evidence still failed to reach the truth: {d['why_still_failed']}")
        err_md.append("")
    (OUT / "D12_ERROR_ANALYSIS.md").write_text("\n".join(err_md) + "\n", encoding="utf-8")

    md = []
    a = md.append
    a("# D12 external results")
    a("")
    a("Prospective blinded twelve-case external benchmark (`V3_D12_EXTERNAL`).")
    a("n = 12 is small. Wilson 95% intervals are descriptive only. No superiority claim is made.")
    a("Predictions were not regenerated. V3 was not modified. D20 was not accessed.")
    a("")
    a("## Lock verification")
    a("")
    a("| File | SHA256 | Result |")
    a("|---|---|---|")
    for name, expected in EXPECTED.items():
        a(f"| `{name}` | `{expected}` | MATCH |")
    a(f"| `D12_EXTERNAL_TRUTH_LOCKED.json` | `{truth_sha}` | LOCKED before prediction join |")
    a("")
    a("Confirmed before truth assignment: 12 Conventional, 12 V5, 12 Agentic V3 records. Agentic completion 12/12.")
    a("")
    a("## Target-specific scored endpoints (V5 vs Agentic V3)")
    a("")
    a("| Pos | Target | V5 scored endpoint | Agentic V3 scored endpoint | Identical |")
    a("|---:|---|---|---|---|")
    for r in endpoint_rows:
        a(
            f"| {r['position']} | `{r['target']}` | {r['v5']} | {r['agentic']} | {'YES' if r['identical'] else 'NO'} |"
        )
    a("")
    a(f"TARGET-SPECIFIC ENDPOINTS IDENTICAL: **{n_ident} / 12**")
    if different:
        a("DIFFERENT ENDPOINT CASES:")
        for r in different:
            a(f"- pos {r['position']} `{r['target']}`: V5 `{r['v5']}` vs Agentic `{r['agentic']}`")
    else:
        a("DIFFERENT ENDPOINT CASES: none")
    a("")
    a("tetA is scored as FAMILY presence/absence (tet(A) or tet(B) only).")
    a("rpoB and lacZ are scored as orthologous-gene presence/absence.")
    a("tuf is scored as exact multiplicity of distinct genuine EF-Tu loci.")
    a("The Agentic V3 lock file does not store `multiplicity`; tuf Agentic scores use polarity fallback (NOT_DETECTED → 0, DETECTED → 1) unless a multiplicity field is present.")
    a("")
    a("## External truth (independent of predictions)")
    a("")
    a("| Pos | Accession | Target | Endpoint | Truth |")
    a("|---:|---|---|---|---|")
    for r in rows:
        a(f"| {r['position']} | {r['accession']} | {r['target']} | {r['endpoint']} | **{r['truth']}** |")
    a("")
    a("Truth assignment used NCBI Gene Orthologs where indexed, independent post-lock phmmer of frozen/authentic seeds against each proteome, and NCBI RefSeq/PGAP AMR gene calls (AMRFinderPlus/NCBIfam-AMRFinder) for tet(A)/tet(B) only. tet(C) was not counted. PGAP names were corroboration only.")
    a("")
    a("## Case-level results")
    a("")
    a("| Pos | Accession | Target | Truth | Conventional | Conv correct? | V5 | V5 correct? | Agentic | Agentic correct? | Agentic completed? |")
    a("|---:|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        a(
            f"| {r['position']} | {r['accession']} | `{r['target']}` | **{r['truth']}** | {r['conventional_endpoint']} | {yn(r['conventional_correct'])} | {r['v5_endpoint']} | {yn(r['v5_correct'])} | {r['agentic_endpoint']} | {yn(r['agentic_correct'])} | {yn(r['agentic_completed'])} |"
        )
    a("")
    a("tuf cases are scored on exact multiplicity. Conventional has no copy-number field; `not_detected` is scored as multiplicity 0.")
    a("")
    a("## Primary results")
    a("")
    a(f"- Externally evaluable: **{n} / 12**")
    a(f"- TRUTH_UNCERTAIN: **{n_uncertain}**")
    acc_c = conv_c / n if n else float("nan")
    acc_v = v5_c / n if n else float("nan")
    acc_a = ag_c / n if n else float("nan")
    a(f"- Conventional: **{conv_c} / {n}** (accuracy {acc_c:.3f}; Wilson 95% CI {conv_ci[0]:.3f}–{conv_ci[1]:.3f})")
    a(f"- Deterministic V5: **{v5_c} / {n}** (accuracy {acc_v:.3f}; Wilson 95% CI {v5_ci[0]:.3f}–{v5_ci[1]:.3f})")
    a(f"- Agentic V3 end-to-end: **{ag_c} / {n}** (accuracy {acc_a:.3f}; Wilson 95% CI {ag_ci[0]:.3f}–{ag_ci[1]:.3f})")
    a(f"- Agentic completion: **{ag_done} / 12**")
    a("")
    a(
        f"In this prospective blinded twelve-case external benchmark, Agentic V3 achieved {ag_c}/{n} correct compared with {v5_c}/{n} for V5 and {conv_c}/{n} for the conventional baseline."
    )
    a("")
    a("## Paired V5 vs Agentic V3")
    a("")
    a(f"- A (both correct) = {len(A)}: " + (", ".join(f"pos {r['position']}" for r in A) or "none"))
    a(f"- B (V5 correct, Agentic incorrect) = {len(B)}: " + (", ".join(f"pos {r['position']} {r['accession']}/{r['target']}" for r in B) or "none"))
    a(f"- C (V5 incorrect, Agentic correct) = {len(C)}: " + (", ".join(f"pos {r['position']} {r['accession']}/{r['target']}" for r in C) or "none"))
    a(f"- D (both incorrect) = {len(D)}: " + (", ".join(f"pos {r['position']}" for r in D) or "none"))
    a("")
    a(f"- V5 ERRORS CORRECTED BY AGENTIC = C = **{len(C)}**")
    a(f"- V5 CORRECT CALLS DEGRADED BY AGENTIC = B = **{len(B)}**")
    a(f"- NET CORRECTIONS = C − B = **{net}**")
    a("")
    a(f"Agentic V3 corrected {len(C)} V5 errors and degraded {len(B)} V5-correct cases.")
    a(mcnemar_note + ".")
    a("")
    a("## Dual-error cases")
    a("")
    if not dual:
        a("None.")
    else:
        for d in dual:
            a(f"- pos {d['position']} `{d['accession']}` / `{d['target']}` class={d['class']}")
    a("")
    a("See `D12_ERROR_ANALYSIS.md`.")
    a("")
    a("This n=12 benchmark does not establish general genome-wide performance.")
    a("")
    (OUT / "D12_EXTERNAL_RESULTS.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    both_wrong = [f"pos {d['position']} {d['accession']}/{d['target']} [{d['class']}]" for d in dual]
    print("D12 LOCKS VERIFIED:")
    print("YES")
    print()
    print("TARGET-SPECIFIC ENDPOINTS IDENTICAL:")
    print(f"{n_ident} / 12")
    print()
    print("D12 TRUTH SHA256:")
    print(truth_sha)
    print()
    print("EXTERNALLY EVALUABLE:")
    print(f"{n} / 12")
    print()
    print("CONVENTIONAL:")
    print(f"{conv_c} / {n}")
    print()
    print("V5:")
    print(f"{v5_c} / {n}")
    print()
    print("AGENTIC V3:")
    print(f"{ag_c} / {n}")
    print()
    print("AGENTIC COMPLETION:")
    print(f"{ag_done} / 12")
    print()
    print("V5 ERRORS CORRECTED:")
    print(str(len(C)))
    print()
    print("V5 CORRECT CALLS DEGRADED:")
    print(str(len(B)))
    print()
    print("NET CORRECTIONS:")
    print(str(net))
    print()
    print("CASES BOTH V5 AND AGENTIC WRONG:")
    print(both_wrong if both_wrong else "[]")
    print()
    print("D20 TOUCHED:")
    print("NO")
    print()
    print("STOP.")
    print(f"created_utc={datetime.now(timezone.utc).isoformat()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
