#!/usr/bin/env python3
import json
from pathlib import Path

eval_dir = Path("/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor/benchmarks/real_genomes_dev_eval")

def brief_error(val):
    if val is None:
        return None
    if isinstance(val, str):
        return val[:300]
    if isinstance(val, dict):
        keys = list(val.keys())
        msg = val.get("error") or val.get("stderr") or val.get("message")
        return f"dict keys={keys[:12]} msg={str(msg)[:200]}"
    return str(val)[:300]

def dump(path, label):
    report = json.loads(Path(path).read_text())
    print(f"===== {label} =====")
    prod = report.get("production") or {}
    print("assembled", prod.get("assembled"), "unavailable", prod.get("assembly_unavailable"))
    print("failed_tools", report.get("failed_tools"))
    print("cases", [c.get("case_id") for c in report.get("cases") or []])
    print("resource_rerun_case_ids", report.get("resource_rerun_case_ids"))
    for row in report.get("cases") or []:
        cid = row.get("case_id")
        p = row.get("production") or {}
        print(f"-- {cid} ok={p.get('ok')} assembly={p.get('assembly')} failed={p.get('failed')} missing={p.get('missing')}")
        for st in p.get("stages") or []:
            if st.get("stage") in ("fastp", "spades") or not st.get("ok"):
                params = st.get("parameters") or {}
                print("   ", st.get("stage"), "ok", st.get("ok"), "exit", st.get("exit_code"),
                      "m", params.get("intended_memory_gb"), "t", params.get("threads"),
                      "reused", params.get("reused_existing_assembly"),
                      "sel", params.get("resource_selection"),
                      "err", brief_error(st.get("error")))
        print("   systems", list((row.get("systems") or {}).keys()))

dump(eval_dir / "preserved/realgenome_production_report.original_m2.json", "ORIGINAL")
print()
dump(eval_dir / "realgenome_production_report.json", "CURRENT")
