from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from genome_skeptic.agents.critic import critique
from genome_skeptic.agents.ollama import OllamaJSONClient
from genome_skeptic.agents.reasoner import reason
from genome_skeptic.config import Settings
from genome_skeptic.claims.assembly import build_annotation_claim, build_assembly_claim
from genome_skeptic.io_utils import detect_sequence_format, read_fasta, sample_fastq_stats
from genome_skeptic.models import (
    AgentDecision,
    Anomaly,
    CriticReview,
    Evidence,
    EvidenceRelationType,
    RunState,
    Severity,
    TargetProfile,
    ToolResult,
)
from genome_skeptic.provenance import sha256_file, write_manifest
from genome_skeptic.reporting.markdown import write_report
from genome_skeptic.tools.annotation import run_annotation
from genome_skeptic.tools.checkm2 import run_checkm2
from genome_skeptic.tools.fastp import run_fastp
from genome_skeptic.tools.gene_search import (
    local_coverage_for_hits,
    neighborhood_for_hits,
    parse_gff_features,
    run_gene_search,
    search_domains,
    search_proteins,
)
from genome_skeptic.tools.hmmer import hmmer_tools_available, run_hmmbuild_and_search, run_hmmsearch
from genome_skeptic.tools.similarity import run_preferred_similarity_search, similarity_tools_available
from genome_skeptic.isolation import assert_agent_accessible
from genome_skeptic.tools.breaks import run_break_analysis
from genome_skeptic.tools.taxonomy import run_contig_taxonomy, taxonomy_tools_available
from genome_skeptic.locus.validate import build_locus_evidence
from genome_skeptic.targets import load_target_profiles
from genome_skeptic.validators.falsification import TargetMeasurements, build_target_gene_claim
from genome_skeptic.tools.gene_search import is_nucleotide, translate_frame
from genome_skeptic.tools.mapping import run_mapping
from genome_skeptic.tools.quast import run_quast
from genome_skeptic.tools.spades import run_spades
from genome_skeptic.validators import (
    count_gff_features,
    hits_from_metrics,
    validate_annotation,
    validate_assembly,
    validate_completeness,
    validate_fastp,
    validate_mapping,
)


REGISTERED_ACTIONS = [
    "continue_pipeline",
    "stop_and_request_human_review",
    "inspect_raw_reads_more_deeply",
    "repeat_cleaning_with_reviewed_parameters",
    "repeat_assembly_after_diagnosing_fragmentation",
    "investigate_contamination",
    "investigate_coverage_anomalies",
    "request_long_read_data",
    "search_target_genes_nucleotide",
    "search_target_genes_translated",
    "inspect_contig_edges_for_target",
    "inspect_local_coverage_for_target",
    "inspect_synteny_neighborhood_for_target",
    "compare_locus_to_reference",
    "reciprocal_best_hit_search",
    "inspect_gene_order_against_reference",
    "search_target_proteins_mmseqs",
    "search_target_proteins_diamond",
    "search_target_domains_hmmer",
    "inspect_paralogue_copies",
    "inspect_catalytic_residues",
    "inspect_hit_contig_contamination",
    "classify_contig_taxonomy",
    "inspect_read_supported_breaks",
    "place_target_among_homologues",
]


RELATED_EVIDENCE_STAGES = {
    "qc_clean": {"input", "qc_clean"},
    "assembly_qc": {"qc_clean", "assembly", "assembly_qc"},
    "mapping": {"assembly_qc", "mapping"},
    "completeness": {"assembly_qc", "mapping", "completeness"},
    "annotation": {"assembly_qc", "annotation"},
    "target_gene": {"assembly_qc", "mapping", "annotation", "target_gene"},
}


class GenomeOrchestrator:
    def __init__(self, settings: Settings, out_dir: Path):
        self.settings = settings
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.client = OllamaJSONClient(settings.llm.for_role("planner")) if settings.llm.enabled else None
        self.critic_client = OllamaJSONClient(settings.llm.for_role("critic")) if settings.llm.enabled else None
        self._evidence_counter = 0

    def _evidence(self, state: RunState, stage: str, kind: str, summary: str, values: dict, source_path: str | None = None, command: list[str] | None = None) -> Evidence:
        self._evidence_counter += 1
        e = Evidence(
            id=f"E{self._evidence_counter:03d}",
            stage=stage,
            kind=kind,
            summary=summary,
            values=values,
            source_path=source_path,
            command=command,
        )
        state.evidence.append(e)
        return e

    def _record_tool(self, state: RunState, result: ToolResult) -> None:
        state.tool_results.append(result)
        self._evidence(
            state,
            result.stage,
            "tool_result",
            f"{result.name} {'completed' if result.ok else 'failed'}",
            {"ok": result.ok, "returncode": result.returncode, "metrics": result.metrics, "outputs": result.outputs, "error": result.error},
            command=result.command,
        )

    def _hard_gate(self, state: RunState, stage: str) -> str | None:
        hard = [a for a in state.anomalies if a.stage == stage and a.severity == Severity.hard]
        if hard:
            return "; ".join(a.message for a in hard)
        return None

    def _agent_review(self, state: RunState, stage: str) -> tuple[AgentDecision | None, CriticReview | None]:
        if not self.settings.execution.enable_critic:
            return None, None
        if not self.client:
            return None, None
        related = RELATED_EVIDENCE_STAGES.get(stage, {stage})
        stage_evidence = [e for e in state.evidence if e.stage == stage or e.stage in related]
        stage_anomalies = [a for a in state.anomalies if a.stage == stage]
        try:
            d = reason(self.client, stage, stage_evidence, stage_anomalies, REGISTERED_ACTIONS)
            if state.unknown_evidence_ids(d.evidence_ids):
                d = AgentDecision(
                    decision="ask_human",
                    rationale="Reasoner cited evidence IDs that do not exist in the ledger, so its decision was rejected.",
                    concerns=["invalid evidence citation from reasoning model"],
                    confidence=0.0,
                )
            invalid_actions = [a for a in d.requested_actions if a not in REGISTERED_ACTIONS]
            if invalid_actions:
                d = AgentDecision(
                    decision="ask_human",
                    rationale="Reasoner requested unregistered actions, so its decision was rejected.",
                    concerns=[f"unregistered action: {a}" for a in invalid_actions],
                    confidence=0.0,
                )
            state.decisions.append(d)
            c = critique(self.critic_client or self.client, stage, d, stage_evidence, stage_anomalies)
            if state.unknown_evidence_ids(c.evidence_ids):
                c = CriticReview(
                    verdict="challenge",
                    rationale="Critic cited evidence IDs that do not exist in the ledger, so its review was rejected as unreliable.",
                    failure_modes=["invalid evidence citation from critic model"],
                )
            state.critic_reviews.append(c)
            return d, c
        except Exception as exc:
            self._evidence(state, stage, "llm_error", "Local reasoning model was unavailable or returned invalid JSON", {"error": str(exc)})
            return None, None

    def _maybe_stop_after_review(self, state: RunState, stage: str, decision: AgentDecision | None, critic: CriticReview | None) -> bool:
        hard_reason = self._hard_gate(state, stage)
        if hard_reason and self.settings.execution.stop_on_hard_gate:
            state.stopped = True
            state.stop_reason = f"Hard validation gate at {stage}: {hard_reason}"
            return True
        if decision and decision.decision in {"stop", "ask_human"}:
            state.stopped = True
            state.stop_reason = f"Reasoning agent requested {decision.decision}: {decision.rationale}"
            return True
        if critic and critic.verdict == "challenge" and decision and decision.decision == "continue":
            # In v0.1 a challenged continuation is deliberately conservative.
            state.stopped = True
            state.stop_reason = "Adversarial critic challenged continuation. Review the listed failure modes before proceeding."
            return True
        if decision and decision.decision == "rerun":
            state.stopped = True
            state.stop_reason = "Reasoning agent requested an adaptive rerun. v0.1 records the requested action but requires human approval before rerunning."
            return True
        return False

    def run(
        self,
        r1: Path,
        r2: Path | None = None,
        dry_run: bool = False,
        targets: Path | None = None,
        references: Path | None = None,
        declared_organism: str | None = None,
    ) -> RunState:
        run_id = self.out_dir.name or str(uuid.uuid4())[:8]
        state = RunState(run_id=run_id, out_dir=str(self.out_dir), inputs={"r1": str(r1), **({"r2": str(r2)} if r2 else {})})
        from genome_skeptic.isolation import assert_action_args_accessible, reject_hidden_environment
        reject_hidden_environment()
        assert_agent_accessible(r1)
        assert_agent_accessible(r2)
        if declared_organism:
            state.inputs["declared_organism"] = declared_organism

        # Stage 0: input validation and provenance
        for p in [r1] + ([r2] if r2 else []):
            if p is None or not p.exists():
                state.stopped = True
                state.stop_reason = f"Input file missing: {p}"
                return self._finish(state)
            fmt = detect_sequence_format(p)
            if fmt != "fastq":
                state.stopped = True
                state.stop_reason = f"MVP currently expects raw FASTQ reads, got {fmt}: {p}"
                return self._finish(state)
            stats = sample_fastq_stats(p)
            stats["sha256"] = sha256_file(p)
            self._evidence(state, "input", "sequence_input", f"Validated FASTQ input {p.name}", stats, source_path=str(p))

        if targets is not None:
            assert_agent_accessible(targets)
            state.inputs["targets"] = str(targets)
            if not targets.exists():
                state.stopped = True
                state.stop_reason = f"Target FASTA missing: {targets}"
                return self._finish(state)

        ref_path = Path(references) if references else (Path(self.settings.paths.references) if self.settings.paths.references else None)
        if ref_path is not None:
            assert_agent_accessible(ref_path)
            state.inputs["references"] = str(ref_path)
            if not ref_path.exists():
                state.stopped = True
                state.stop_reason = f"Reference set missing: {ref_path}"
                return self._finish(state)

        if dry_run:
            planned = ["fastp", "SPAdes", "QUAST", "read mapping", "CheckM2", "Bakta/Prodigal", "adversarial review"]
            if targets is not None:
                planned.append("target gene reasoning")
                planned.append("claim falsification engine")
                planned.append("reference-aware locus validation")
            self._evidence(state, "plan", "dry_run", "Dry run only. No external bioinformatics tools were executed.", {"planned_stages": planned})
            return self._finish(state)

        # Stage 1: QC + cleaning
        qc_dir = self.out_dir / "01_qc_clean"
        fastp_result = run_fastp(r1, r2, qc_dir, self.settings.project.threads)
        self._record_tool(state, fastp_result)
        if not fastp_result.ok:
            state.stopped = True
            state.stop_reason = f"QC/cleaning failed: {fastp_result.error}"
            return self._finish(state)
        qc_anoms = validate_fastp(fastp_result.metrics, self.settings)
        qc_evidence_id = state.evidence[-1].id
        for a in qc_anoms:
            a.evidence_ids.append(qc_evidence_id)
        state.anomalies.extend(qc_anoms)
        d, c = self._agent_review(state, "qc_clean")
        if self._maybe_stop_after_review(state, "qc_clean", d, c):
            return self._finish(state)

        clean_r1 = Path(fastp_result.outputs["clean_r1"])
        clean_r2 = Path(fastp_result.outputs["clean_r2"]) if fastp_result.outputs.get("clean_r2") else None

        # Stage 2: assembly
        asm_dir = self.out_dir / "02_assembly"
        asm_result = run_spades(clean_r1, clean_r2, asm_dir, self.settings.project.threads)
        self._record_tool(state, asm_result)
        if not asm_result.ok:
            state.stopped = True
            state.stop_reason = f"Assembly failed: {asm_result.error}"
            return self._finish(state)
        contigs = Path(asm_result.outputs["contigs"])

        # Stage 3: assembly QC
        quast_dir = self.out_dir / "03_assembly_qc"
        q = run_quast(contigs, quast_dir, self.settings.project.threads)
        self._record_tool(state, q)
        if not q.ok:
            state.stopped = True
            state.stop_reason = f"Assembly QC failed: {q.error}"
            return self._finish(state)
        asm_anoms = validate_assembly(q.metrics, self.settings)
        eid = state.evidence[-1].id
        for a in asm_anoms:
            a.evidence_ids.append(eid)
        state.anomalies.extend(asm_anoms)
        d, c = self._agent_review(state, "assembly_qc")
        if self._maybe_stop_after_review(state, "assembly_qc", d, c):
            return self._finish(state)

        # Stage 4: read-back mapping
        map_dir = self.out_dir / "04_mapping"
        m = run_mapping(contigs, clean_r1, clean_r2, map_dir, self.settings.project.threads)
        self._record_tool(state, m)
        if m.ok:
            map_anoms = validate_mapping(m.metrics, self.settings)
            eid = state.evidence[-1].id
            for a in map_anoms:
                a.evidence_ids.append(eid)
            state.anomalies.extend(map_anoms)
            d, c = self._agent_review(state, "mapping")
            if self._maybe_stop_after_review(state, "mapping", d, c):
                return self._finish(state)
        else:
            self._evidence(state, "mapping", "missing_validator", "Read-back mapping validator could not run", {"error": m.error})

        # Stage 5: completeness / contamination. Optional but strongly preferred.
        checkm_dir = self.out_dir / "05_checkm2"
        cm = run_checkm2(contigs, checkm_dir, self.settings.project.threads, self.settings.paths.checkm2_db)
        self._record_tool(state, cm)
        if cm.ok:
            comp_anoms = validate_completeness(cm.metrics, self.settings)
            eid = state.evidence[-1].id
            for a in comp_anoms:
                a.evidence_ids.append(eid)
            state.anomalies.extend(comp_anoms)
            d, c = self._agent_review(state, "completeness")
            if self._maybe_stop_after_review(state, "completeness", d, c):
                return self._finish(state)
        else:
            self._evidence(state, "completeness", "missing_validator", "CheckM2 validator could not run; completeness/contamination remain less certain", {"error": cm.error})

        # Claim after orthogonal assembly validators.
        mapping_rate = m.metrics.get("mapping_rate") if m.ok else None
        completeness = cm.metrics.get("completeness") if cm.ok else None
        contamination = cm.metrics.get("contamination") if cm.ok else None
        contradicting = []
        for a in state.anomalies:
            if a.stage in {"assembly_qc", "mapping", "completeness"}:
                contradicting.extend(a.evidence_ids)
        state.bind_claim(build_assembly_claim(
            settings=self.settings,
            mapping_rate=mapping_rate,
            completeness=completeness,
            contamination=contamination,
            assembly_metrics=q.metrics,
            anomalies=state.anomalies,
            supporting_ids=[e.id for e in state.evidence if e.stage in {"assembly_qc", "mapping", "completeness"}],
            contradicting_ids=list(dict.fromkeys(contradicting)),
            tools=[r.name for r in state.tool_results if r.stage in {"assembly_qc", "mapping", "completeness"}],
        ))

        # Stage 6: annotation
        ann_dir = self.out_dir / "06_annotation"
        ann = run_annotation(contigs, ann_dir, self.settings.project.threads, self.settings.paths.bakta_db)
        self._record_tool(state, ann)
        if not ann.ok:
            state.stopped = True
            state.stop_reason = f"Annotation failed: {ann.error}"
        else:
            ann_metrics = {}
            gff = ann.outputs.get("gff")
            if gff and Path(gff).exists():
                ann_metrics = count_gff_features(gff)
                self._evidence(state, "annotation", "annotation_metrics", "Counted predicted annotation features", ann_metrics, source_path=gff)
                ann_anoms = validate_annotation(ann_metrics, q.metrics, self.settings)
                eid = state.evidence[-1].id
                for a in ann_anoms:
                    a.evidence_ids.append(eid)
                state.anomalies.extend(ann_anoms)
            d, c = self._agent_review(state, "annotation")
            if not self._maybe_stop_after_review(state, "annotation", d, c):
                ann_contradict = []
                for a in state.anomalies:
                    if a.stage == "annotation":
                        ann_contradict.extend(a.evidence_ids)
                state.bind_claim(build_annotation_claim(
                    settings=self.settings,
                    annotation_anomalies=[a for a in state.anomalies if a.stage == "annotation"],
                    supporting_ids=[e.id for e in state.evidence if e.stage == "annotation"],
                    contradicting_ids=list(dict.fromkeys(ann_contradict)),
                    tools=[r.name for r in state.tool_results if r.stage == "annotation"],
                    fragmented=(q.metrics.get("contigs") or 0) > self.settings.thresholds.max_contigs_soft,
                ))

        if targets is not None:
            self._run_target_gene_stage(state, contigs, m, ann, targets)

        return self._finish(state)

    def _run_target_gene_stage(
        self,
        state: RunState,
        contigs: Path,
        mapping_result: ToolResult,
        annotation_result: ToolResult,
        targets: Path,
    ) -> None:
        search_dir = self.out_dir / "07_target_gene"
        result = run_gene_search(targets, contigs, search_dir, self.settings)
        self._record_tool(state, result)
        tool_eid = state.evidence[-1].id
        if not result.ok:
            fail = Anomaly(
                id="target_gene_search_failed",
                stage="target_gene",
                severity=Severity.hard,
                message=f"Target gene search failed: {result.error}",
                evidence_ids=[tool_eid],
            )
            state.anomalies.append(fail)
            self._maybe_stop_after_review(state, "target_gene", None, None)
            return

        hits = hits_from_metrics(result.metrics)
        profiles = load_target_profiles(str(targets))
        contig_records = read_fasta(contigs)
        contig_seqs = dict(contig_records)
        contig_gc, genome_gc = _contig_gc(contig_records)
        tools_run = ["internal_gene_search"]
        tools_unavailable: list[str] = []
        measurement_ids = [tool_eid]

        proteins: list[tuple[str, str]] = []
        protein_path = annotation_result.outputs.get("proteins") if annotation_result.ok else None
        if protein_path and Path(protein_path).exists():
            proteins = read_fasta(protein_path)
        for profile in profiles:
            qaa = _query_aa(profile)
            if proteins and qaa:
                hits.extend(search_proteins(profile.query_id, qaa, proteins, self.settings))
            if profile.domains and qaa:
                hits.extend(search_domains(profile.query_id, qaa, profile.domains, contig_records, self.settings))

        query_faa = search_dir / "targets.faa"
        _write_fa(query_faa, [(p.query_id, _query_aa(p)) for p in profiles if _query_aa(p)])
        sim_tools = similarity_tools_available()
        if sim_tools:
            sim_target = Path(protein_path) if protein_path and Path(protein_path).exists() else contigs
            kind = "protein" if protein_path and Path(str(protein_path)).exists() else "translated"
            sim = run_preferred_similarity_search(query_faa, sim_target, search_dir / "similarity", self.settings, kind)
            self._record_tool(state, sim)
            measurement_ids.append(state.evidence[-1].id)
            if sim.ok:
                tools_run.append(sim.name)
                hits.extend(hits_from_metrics(sim.metrics))
            else:
                tools_unavailable.append(sim.name)
        else:
            tools_unavailable.extend(["mmseqs", "diamond"])
            self._evidence(state, "target_gene", "missing_validator", "MMseqs2/DIAMOND unavailable; internal homology search was used", {"tools": ["mmseqs", "diamond"]})
            measurement_ids.append(state.evidence[-1].id)

        hmm_db = self.settings.paths.hmm_db
        if hmm_db and Path(hmm_db).exists() and proteins:
            hmm = run_hmmsearch(Path(hmm_db), Path(protein_path), search_dir / "hmmer", self.settings.project.threads)
            self._record_tool(state, hmm)
            measurement_ids.append(state.evidence[-1].id)
            if hmm.ok:
                tools_run.append("hmmsearch")
                hits.extend(hits_from_metrics(hmm.metrics))
            else:
                tools_unavailable.append("hmmsearch")
        elif hmmer_tools_available() == ["hmmsearch", "hmmbuild"] or set(hmmer_tools_available()) >= {"hmmsearch", "hmmbuild"}:
            hmm = run_hmmbuild_and_search(query_faa, Path(protein_path) if protein_path and Path(protein_path).exists() else _write_translated_orfs(contig_records, search_dir / "orfs.faa"), search_dir / "hmmer", self.settings.project.threads)
            self._record_tool(state, hmm)
            measurement_ids.append(state.evidence[-1].id)
            if hmm.ok:
                tools_run.append("hmmsearch")
                hits.extend(hits_from_metrics(hmm.metrics))
            else:
                tools_unavailable.append("hmmsearch")
        else:
            tools_unavailable.append("hmmsearch")
            self._evidence(state, "target_gene", "missing_validator", "HMMER unavailable; domain evidence used internal windows only", {"tools": ["hmmsearch"]})
            measurement_ids.append(state.evidence[-1].id)

        e_nt = self._evidence(state, "target_gene", "measurement", "Nucleotide homology measurements", {"hits": [h.model_dump() for h in hits if h.search_kind == "nucleotide"]}, command=result.command)
        e_aa = self._evidence(state, "target_gene", "measurement", "Translated homology measurements", {"hits": [h.model_dump() for h in hits if h.search_kind == "translated"]})
        e_prot = self._evidence(state, "target_gene", "measurement", "Predicted-protein homology measurements", {"hits": [h.model_dump() for h in hits if h.search_kind == "protein"]})
        e_dom = self._evidence(state, "target_gene", "measurement", "Domain homology measurements", {"hits": [h.model_dump() for h in hits if h.search_kind == "domain"]})
        for derived in (e_nt, e_aa, e_prot, e_dom):
            state.add_relation(derived.id, tool_eid, EvidenceRelationType.derived_from)
            measurement_ids.append(derived.id)

        coverage_by_hit: dict[str, dict] = {}
        depth_path = mapping_result.outputs.get("depth") if mapping_result.ok else None
        depth_available = bool(depth_path and Path(depth_path).exists())
        if depth_available and hits:
            coverage_by_hit = local_coverage_for_hits(depth_path, hits)
        e_cov = self._evidence(state, "target_gene", "measurement", "Local coverage measurements", {"by_locus": coverage_by_hit, "depth_available": depth_available}, source_path=depth_path)
        measurement_ids.append(e_cov.id)

        neighborhood_by_hit: dict[str, dict] = {}
        gff = annotation_result.outputs.get("gff") if annotation_result.ok else None
        annotation_available = bool(gff and Path(gff).exists())
        if annotation_available:
            neighborhood_by_hit = neighborhood_for_hits(parse_gff_features(gff), hits) if hits else {}
        e_nb = self._evidence(state, "target_gene", "measurement", "Neighborhood measurements", {"by_locus": neighborhood_by_hit, "annotation_available": annotation_available}, source_path=gff)
        measurement_ids.append(e_nb.id)

        checkm_x = None
        for tr in state.tool_results:
            if tr.name == "checkm2" and tr.ok:
                checkm_x = tr.metrics.get("contamination")

        references: list[dict] = []
        ref_yaml = Path(state.inputs["references"]) if state.inputs.get("references") else (
            Path(self.settings.paths.references) if self.settings.paths.references else None
        )
        if ref_yaml and ref_yaml.exists():
            references = load_reference_set(ref_yaml)
            tools_run.append("gff_synteny")
        elif targets is not None:
            self._evidence(
                state, "target_gene", "missing_validator",
                "No trusted reference genome was configured; orthologues and gene order were not invented",
                {"paths.references": self.settings.paths.references},
            )
            measurement_ids.append(state.evidence[-1].id)
            tools_unavailable.append("reference_set")

        assembly_features = parse_gff_features(gff) if annotation_available else []

        contig_taxonomy: dict[str, dict] = {}
        tax_db = self.settings.paths.taxonomy_db
        if tax_db:
            tax = run_contig_taxonomy(contigs, search_dir / "taxonomy", tax_db, self.settings.project.threads)
            self._record_tool(state, tax)
            measurement_ids.append(state.evidence[-1].id)
            if tax.ok:
                contig_taxonomy = tax.metrics.get("by_contig") or {}
                tools_run.append(tax.name)
            else:
                tools_unavailable.append("contig_taxonomy")
        else:
            self._evidence(
                state, "target_gene", "missing_validator",
                "No contig taxonomy database was configured; taxonomy was not invented from reference metadata",
                {"tools": taxonomy_tools_available()},
            )
            measurement_ids.append(state.evidence[-1].id)
            tools_unavailable.append("contig_taxonomy")

        break_evidence: dict[str, dict] = {}
        bam = Path(mapping_result.outputs["bam"]) if mapping_result.ok and mapping_result.outputs.get("bam") else None
        mapping_available = bool(bam and bam.exists())
        loci_spec = []
        for h in hits:
            if h.search_kind == "nucleotide":
                loci_spec.append({
                    "contig": h.contig_id,
                    "start": min(h.tstart, h.tend),
                    "end": max(h.tstart, h.tend),
                    "contig_length": h.contig_length or len(contig_seqs.get(h.contig_id, "")),
                })
        if mapping_available and loci_spec:
            br = run_break_analysis(bam, search_dir / "breaks", loci_spec)
            self._record_tool(state, br)
            measurement_ids.append(state.evidence[-1].id)
            break_evidence = br.metrics.get("by_locus") or {}
            tools_run.append("break_analysis")
        elif hits:
            self._evidence(
                state, "target_gene", "missing_validator",
                "Paired-end mapping was unavailable; read-supported breaks were not invented",
                {"mapping_ok": mapping_result.ok},
            )
            measurement_ids.append(state.evidence[-1].id)

        declared = state.inputs.get("declared_organism")

        for profile in profiles:
            q_hits = [h for h in hits if h.query_id == profile.query_id]
            q_cov = {k: v for k, v in coverage_by_hit.items() if k.startswith(f"{profile.query_id}:")}
            if declared and not profile.expected_taxonomy:
                profile.expected_taxonomy = declared
            loci = build_locus_evidence(
                profile=profile,
                hits=q_hits,
                settings=self.settings,
                assembly_features=assembly_features,
                contig_sequences=contig_seqs,
                query_proteins=dict(proteins),
                references=references,
                coverage=q_cov,
                tools_run=tools_run,
                break_evidence=break_evidence,
                contig_taxonomy=contig_taxonomy,
                mapping_available=mapping_available,
            )
            state.locus_evidence.extend(loci)
            le_e = self._evidence(
                state, "target_gene", "locus_evidence",
                f"Deterministic locus evidence for {profile.query_id}",
                {"records": [le.model_dump() for le in loci]},
            )
            profile_ids = list(measurement_ids) + [le_e.id]
            measurements = TargetMeasurements(
                query_id=profile.query_id,
                profile=profile,
                hits=q_hits,
                coverage_by_hit=q_cov,
                neighborhood_by_hit={k: v for k, v in neighborhood_by_hit.items() if k.startswith(f"{profile.query_id}:")},
                contig_sequences=contig_seqs,
                protein_sequences=dict(proteins),
                contig_gc=contig_gc,
                genome_gc=genome_gc,
                checkm_contamination=checkm_x,
                tools_run=tools_run,
                tools_unavailable=tools_unavailable,
                proteins_available=bool(proteins),
                depth_available=depth_available,
                annotation_available=annotation_available,
                locus_evidence=loci,
                break_evidence=break_evidence,
                contig_taxonomy=contig_taxonomy,
                mapping_available=mapping_available,
                falsification_enabled=self.settings.execution.enable_falsification,
                declared_organism=declared,
                phylogeny=((loci[0].sequence_similarity or {}).get("placement") or {}) if loci else {},
            )
            claim, anoms, tests = build_target_gene_claim(measurements, self.settings, profile_ids)
            plan_e = self._evidence(
                state, "target_gene", "attack_plan",
                f"Adversarial attack plan for {profile.query_id} ({claim.claim_type.value})",
                {"attack_plan_id": claim.provenance.attack_plan_id, "tests": [t.model_dump() for t in tests]},
            )
            state.add_relation(plan_e.id, tool_eid, EvidenceRelationType.derived_from)
            for test in tests:
                te = self._evidence(
                    state, "target_gene", "falsification_test",
                    f"{test.name}: {test.result.value} ({test.status})",
                    test.model_dump(),
                )
                test.evidence_ids = [te.id]
                if test.result.value in {"weakens_claim", "rejects_claim"}:
                    claim.contradicting_evidence_ids.append(te.id)
                elif test.result.value == "supports_claim":
                    claim.supporting_evidence_ids.append(te.id)
            claim.falsification_tests = tests
            claim.completed_tests = [t.test_id for t in tests if t.status == "completed"]
            claim.unresolved_tests = [t.test_id for t in tests if t.status != "completed"]
            claim.supporting_evidence_ids = list(dict.fromkeys(claim.supporting_evidence_ids))
            claim.contradicting_evidence_ids = list(dict.fromkeys(claim.contradicting_evidence_ids))
            for a in anoms:
                if not a.evidence_ids:
                    a.evidence_ids = [eid for t in tests for eid in t.evidence_ids][:1] or [tool_eid]
                a.evidence_ids = [eid for eid in a.evidence_ids if eid not in state.unknown_evidence_ids(a.evidence_ids)]
                state.anomalies.append(a)
            state.bind_claim(claim)

        d, c = self._agent_review(state, "target_gene")
        self._maybe_stop_after_review(state, "target_gene", d, c)


    def _finish(self, state: RunState) -> RunState:
        state_path = self.out_dir / "run_state.json"
        state.save(state_path)
        write_report(state, self.out_dir / "report.md")
        write_manifest(self.out_dir, {
            "inputs": state.inputs,
            "run_id": state.run_id,
            "tool_results": [r.model_dump() for r in state.tool_results],
        })
        return state


def _write_fa(path: Path, records: list[tuple[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f">{name}\n{seq}\n" for name, seq in records if seq))
    return path


def _query_aa(profile: TargetProfile) -> str:
    seq = profile.sequence.upper()
    if not seq:
        return ""
    if is_nucleotide(seq):
        aa = max((translate_frame(seq, f) for f in range(3)), key=len)
        return aa.split("*")[0] if aa else ""
    return seq.replace("*", "")


def _contig_gc(records: list[tuple[str, str]]) -> tuple[dict[str, float], float | None]:
    out: dict[str, float] = {}
    weights: list[tuple[float, int]] = []
    for cid, seq in records:
        s = seq.upper()
        if not s:
            continue
        gc = (s.count("G") + s.count("C")) / len(s)
        out[cid] = gc
        weights.append((gc, len(s)))
    if not weights:
        return out, None
    genome = sum(g * n for g, n in weights) / sum(n for _, n in weights)
    return out, genome


def _write_translated_orfs(records: list[tuple[str, str]], path: Path) -> Path:
    orfs: list[tuple[str, str]] = []
    for cid, seq in records:
        aa = max((translate_frame(seq.upper(), f) for f in range(3)), key=len)
        aa = aa.split("*")[0] if aa else ""
        if aa:
            orfs.append((cid, aa))
    return _write_fa(path, orfs)
