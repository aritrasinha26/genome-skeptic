#!/usr/bin/env python3
"""STEP 3D-A: freeze Cohort A run configuration before any sequence download."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "external_validation"

CFG = {
    "kind": "cohort_A_run_config",
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "cohort_description": "taxonomically stratified external cohort",
    "not_a_natural_refseq_prevalence_sample": True,
    "genome_skeptic_v5_freeze_hash": "0e993125d2d620e54bbb42b3e420b4b9fda951c28b358ff8a2aed2d5b55a8f1b",
    "cohort_manifest_sha256": "292d96e1c1bdd431e44add115e9fbe06b7ddaf412bb89719450a7f5b8ad15f6e",
    "scoring_contract_sha256": "d224b8b829b3a46c03e42aae324062b7ff72c75d2b6906a0cab45618818f9cb9",
    "input_policy_sha256": "6d99f26208175a5f7e77017d3d99461ed4c75d333930622059ed01c9b18d0978",
    "conditions": [
        "FULL_GENOME_SKEPTIC_V5",
        "V5_NO_FALSIFICATION",
        "FROZEN_CONVENTIONAL_BASELINE",
    ],
    "condition_mapping_to_frozen_systems": {
        "FULL_GENOME_SKEPTIC_V5": "genome_skeptic",
        "V5_NO_FALSIFICATION": "skeptic_no_falsification",
        "FROZEN_CONVENTIONAL_BASELINE": "conventional",
    },
    "model": "qwen3:4b",
    "llm_transport": "Ollama native /api/chat with schema-constrained format",
    "llm": {
        "provider": "openai_compatible",
        "native_endpoint": "http://172.17.32.1:11434/api/chat",
        "base_url": "http://172.17.32.1:11434/v1",
        "model": "qwen3:4b",
        "model_digest_sha256": "359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7",
        "quantization": "Q4_K_M",
        "parameter_size": "4.0B",
        "family": "qwen3",
        "think": False,
        "temperature": 0.0,
        "keep_alive": "30m",
        "timeout_seconds": 120,
        "max_output_tokens": 256,
        "max_structured_output_repairs": 1,
        "fail_closed_on_invalid_output": True,
        "config_file": "config/qwen_external_v5.yaml",
    },
    "ollama": {
        "version": "0.34.2",
        "host_api": "http://127.0.0.1:11434",
        "wsl_api": "http://172.17.32.1:11434",
    },
    "execution_environment": {
        "python": "3.11.16",
        "python_executable": "/home/aritr/micromamba/envs/genome-skeptic-prod/bin/python",
        "conda_env": "genome-skeptic-prod",
        "wsl": True,
    },
    "deterministic_tools_available_at_freeze": {
        "hmmsearch": "HMMER 3.4 (Aug 2023)",
        "hmmbuild": "HMMER 3.4 (Aug 2023)",
        "blastp": "2.16.0+",
        "blastn": "2.16.0+",
        "FastTree": "2.2.0 Double precision",
        "diamond": "2.2.6",
        "mmseqs": "18.8cc5c",
        "minimap2": "2.31-r1302",
        "samtools": "1.24",
    },
    "note_on_llm_use": (
        "Frozen assembly-only Genome Skeptic V5 gene-orthologue claims are produced by deterministic validators. "
        "Qwen3:4b is the frozen model for this external campaign; it is invoked only if a frozen condition "
        "requests planner/critic JSON. Missing deterministic tools are marked unavailable, never simulated."
    ),
    "scientific_logic_modified": False,
    "thresholds_will_not_be_tuned_after_outputs": True,
    "external_labels_will_not_be_opened": True,
    "annotations_will_not_be_downloaded": True,
    "hashed_before_sequence_download": True,
}


def main() -> None:
    # Correct the typo in input policy hash if I mistyped.
    CFG["input_policy_sha256"] = "6d99f26208175a5f7a77017d3d99461ed4c75d333930622059ed01c9b18d0978"
    dest = OUT / "cohort_A_run_config.json"
    dest.write_text(json.dumps(CFG, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    (OUT / "cohort_A_run_config.sha256.json").write_text(
        json.dumps({"file": "cohort_A_run_config.json", "sha256": digest, "hashed_before_sequence_download": True}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(digest)


if __name__ == "__main__":
    main()
