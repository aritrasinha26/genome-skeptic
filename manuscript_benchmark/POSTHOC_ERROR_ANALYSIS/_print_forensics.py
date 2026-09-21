#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

src = Path(__file__).resolve().parent / "_extracted" / "compact_forensics.json"
obj = json.loads(src.read_text(encoding="utf-8"))
lines: list[str] = []


def hmm_s(h):
    if not h:
        return None
    return {
        "tid": h.get("target_id"),
        "score": h.get("full_score"),
        "eval": h.get("full_evalue"),
        "mcov": h.get("model_coverage"),
        "qcov": h.get("query_coverage"),
    }


for pos in sorted(obj, key=int):
    c = obj[pos]
    t = c["truth"]
    lines.append("=" * 72)
    lines.append(f"POS {pos} {c['identity']['case_id']} {c['identity']['target']} {c['identity']['stratum']}")
    lines.append(
        f"TRUTH {t['value']} id={t['sim']} cov={t['cov']} coords={t['coords']} "
        f"hmm_cov={t['hmm'].get('target_hmm_model_coverage')} hmm_score={t['hmm'].get('target_hmm_score')} r1={t['r1']} r2={t['r2']}"
    )
    bt = c["blastx_target_top"][0] if c["blastx_target_top"] else None
    lines.append(f"BLASTX {bt}")
    d = c["det_lock"]
    lines.append(
        f"DET {d['final_result']} arch={d['architecture']} hom={d['homology_support']} ortho={d['orthology_class']}"
    )
    lines.append(f"QWEN_ACT {c['qwen_lock_actions']} EXH_ACT {c['exh_lock_actions']}")
    s = c["sol_lock_actions"]
    lines.append(
        f"SOL planner={s['planner']} critic={s['critic']}/{s['critic_action']} n={s['n_follow_up']} first={s['first']} second={s['second']}"
    )
    for arm, a in c["arms"].items():
        rec = a["recon_locus"]
        cf = a["competitive"]
        lines.append(f"  {arm} files={a['files']}")
        lines.append(
            f"    arch={a['architecture']} domain_only={a['domain_only']} supports={a['supports_orthologue']} hier={a['hierarchy']}"
        )
        lines.append(
            f"    recon_arch={rec.get('architecture')} contig={rec.get('contig')} {rec.get('strand')} "
            f"{rec.get('genomic_start')}-{rec.get('genomic_end')} hmm_cov={rec.get('hmm_coverage')} "
            f"seq_id={rec.get('sequence_identity')} prot_cov={rec.get('protein_coverage')} qid={rec.get('query_identity')} "
            f"gate={rec.get('family_gate_passed')} edge={rec.get('contig_edge')}"
        )
        lines.append(
            f"    class={a['competitive_class']} tgt_score={cf.get('target_family_score')} tgt_hmm={cf.get('target_family_HMM_score')} "
            f"tgt_mcov={cf.get('target_family_model_coverage')} tgt_scov={cf.get('target_family_sequence_coverage')} "
            f"best_comp={cf.get('best_competing_family')} comp_score={cf.get('competing_family_score')} margin={cf.get('score_margin')} "
            f"plen={cf.get('protein_length')} conflicts={cf.get('conflicting_evidence')}"
        )
        lines.append(f"    comps={a['competitors']}")
        multi = a["multiplicity"] or {}
        lines.append(
            f"    multi_n={multi.get('number_of_candidate_loci')} class={multi.get('classification')} coords={multi.get('coordinates')}"
        )
        lines.append(f"    best_hmm={hmm_s(a['best_hmm'])} metrics={a['metrics']}")
        lines.append(f"    member_hits={a['member_hits']}")
        lines.append(f"    claim={a['claim_type']} {a['claim_status']} hom={a['homology_support']}")
        act_s = [
            {
                k: x.get(k)
                for k in ["action_id", "status", "n_new", "classification", "supports_orthologue", "summary"]
            }
            for x in a["actions"]
        ]
        lines.append(f"    actions={act_s}")
        lf = a["locus_final"] or {}
        lines.append(
            f"    locus_n={lf.get('n_loci')} n_accepted={lf.get('n_accepted')} n_source={lf.get('n_source_hits')} coords={lf.get('coordinates')}"
        )

dest = Path(__file__).resolve().parent / "_extracted" / "forensic_print.txt"
dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("wrote", dest, "lines", len(lines), "chars", dest.stat().st_size)
