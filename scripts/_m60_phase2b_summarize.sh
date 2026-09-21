#!/usr/bin/env bash
set -euo pipefail
REPO="/mnt/c/Users/aritr/Downloads/GenomeSkeptic_Cursor/GenomeSkeptic_Cursor"
export PATH="/home/aritr/micromamba/envs/genome-skeptic-prod/bin:/usr/bin:/bin:${PATH}"
export PYTHONPATH="${REPO}/src"
cd "$REPO"
python "${REPO}/scripts/lock_m60_positions_1_5.py"
python - <<'PY'
import json
from pathlib import Path
root = Path("manuscript_benchmark/POSITION_LOCKS")
for pos in range(1, 6):
    pdir = root / f"position_{pos:02d}"
    lock = json.loads((pdir / "POSITION_LOCK.json").read_text())
    agent = json.loads((pdir / "GS_AGENTIC_V4_1.json").read_text())
    exh = json.loads((pdir / "GS_EXHAUSTIVE_V4_1.json").read_text())
    spec_name = "AMRFINDERPLUS" if (pdir / "AMRFINDERPLUS.json").exists() else "NCBI_REFSEQ_PGAP"
    spec = json.loads((pdir / f"{spec_name}.json").read_text()) if (pdir / f"{spec_name}.json").exists() else {}
    conv = json.loads((pdir / "CONVENTIONAL.json").read_text())
    det = json.loads((pdir / "GS_DETERMINISTIC_V4_1.json").read_text())
    def acts(row):
        integ = row.get("integrity") or {}
        if integ.get("n_deterministic_followup_analyses") is not None:
            n = integ["n_deterministic_followup_analyses"]
            ids = integ.get("actions_executed") or row.get("actions_executed") or []
            return n, ids
        ids = row.get("actions_executed") or []
        return len(ids) if isinstance(ids, list) else 0, ids
    an, aids = acts(agent)
    en, eids = acts(exh)
    print("=" * 40)
    print("POS", pos)
    print("acc", lock["accession"])
    print("target", lock["target"])
    print("stratum", lock["stratum"])
    print("conv", conv.get("completion_status"), conv.get("ok"))
    print("spec", spec_name, spec.get("completion_status"), spec.get("ok"), spec.get("binary_call"))
    print("det", det.get("completion_status"), det.get("ok"))
    print("agent", agent.get("completion_status"), agent.get("ok"), "fail", agent.get("agent_failure"))
    print("agent_integrity", (agent.get("integrity") or {}).get("integrity_pass"))
    print("agent_unreg", (agent.get("integrity") or {}).get("unregistered_actions") or agent.get("unregistered_actions"))
    print("agent_silent", agent.get("silent_deterministic_fallback"))
    print("agent_llm_meas", agent.get("llm_measurement_entered_claim"))
    print("agent_val_final", agent.get("validator_consumed_final_state"))
    print("agent_followups", an, aids)
    print("exh", exh.get("completion_status"), exh.get("ok"))
    print("exh_followups", en, eids)
    print("exh_inelig", (exh.get("integrity") or {}).get("n_ineligible_recorded"))
    print("agent_m0", agent.get("m0_hash"))
    print("agent_mf", agent.get("m_final_hash"))
    print("agent_digest", agent.get("model_digest"))
    print("agent_planner", agent.get("planner_calls") or agent.get("planner_call_count"))
    print("agent_critic", agent.get("critic_calls") or agent.get("critic_call_count"))
PY
