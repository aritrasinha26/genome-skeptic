from __future__ import annotations

from pathlib import Path

from genome_skeptic.models import RunState


def write_report(state: RunState, path: Path) -> None:
    lines: list[str] = []
    lines.append(f"# Genome Skeptic report: {state.run_id}\n")
    lines.append("## Run status\n")
    lines.append(f"Stopped: {state.stopped}\n")
    if state.stop_reason:
        lines.append(f"Reason: {state.stop_reason}\n")

    lines.append("## Evidence ledger\n")
    for e in state.evidence:
        lines.append(f"### {e.id}\n")
        lines.append(f"Stage: {e.stage}\n\n{e.summary}\n")
        if e.values:
            lines.append("```json\n")
            import json
            lines.append(json.dumps(e.values, indent=2))
            lines.append("\n```\n")

    lines.append("## Anomalies\n")
    if not state.anomalies:
        lines.append("No configured anomalies were triggered.\n")
    for a in state.anomalies:
        lines.append(f"### {a.id} [{a.severity.value}]\n")
        lines.append(a.message + "\n")
        if a.possible_explanations:
            lines.append("Possible explanations: " + "; ".join(a.possible_explanations) + "\n")

    lines.append("## Agent decisions\n")
    for d in state.decisions:
        lines.append(f"Decision: {d.decision}. Confidence: {d.confidence:.2f}\n\n{d.rationale}\n")
        if d.concerns:
            lines.append("Concerns: " + "; ".join(d.concerns) + "\n")

    lines.append("## Adversarial reviews\n")
    for c in state.critic_reviews:
        lines.append(f"Verdict: {c.verdict}\n\n{c.rationale}\n")
        if c.failure_modes:
            lines.append("Failure modes considered: " + "; ".join(c.failure_modes) + "\n")
        if c.disconfirming_tests:
            lines.append("Disconfirming tests: " + "; ".join(c.disconfirming_tests) + "\n")

    lines.append("## Claims\n")
    for c in state.claims:
        lines.append(f"### {c.claim_id} [{c.claim_type.value}]: {c.statement}\n")
        lines.append(f"Status: {c.status.value}. Confidence: {c.confidence:.2f}. Evidence completeness: {c.evidence_completeness:.2f}\n")
        lines.append("Status and confidence are separate from evidence completeness. Supported is not certainty.\n")
        lines.append(f"\n{c.rationale}\n")
        if c.supporting_evidence_ids:
            lines.append("Supporting evidence: " + ", ".join(c.supporting_evidence_ids) + "\n")
        if c.contradicting_evidence_ids:
            lines.append("Contradicting evidence: " + ", ".join(c.contradicting_evidence_ids) + "\n")
        if c.alternative_explanations:
            lines.append("Alternative explanations: " + "; ".join(c.alternative_explanations) + "\n")
        if c.completed_tests:
            lines.append("Completed falsification tests: " + ", ".join(c.completed_tests) + "\n")
        if c.unavailable_tests:
            lines.append("Unavailable tests: " + ", ".join(c.unavailable_tests) + "\n")
        if c.recommended_next_actions:
            lines.append("Recommended next actions: " + ", ".join(c.recommended_next_actions) + "\n")
        if c.falsification_tests:
            lines.append("Attack plan:\n")
            for t in c.falsification_tests:
                lim = f" limitation={t.limitation}" if t.limitation else ""
                lines.append(f"- {t.test_id}: {t.status}/{t.result.value}{lim}\n")
        if c.provenance.attack_plan_id:
            lines.append(f"Provenance: {c.provenance.created_by} / {c.provenance.stage} / {c.provenance.attack_plan_id}\n")
            lines.append(c.provenance.notes + "\n")

    if state.locus_evidence:
        import json
        lines.append("## Locus evidence\n")
        lines.append("These records were produced by the deterministic locus validator. The language model did not invent orthologues, identities, gene order, or reciprocal hits.\n")
        for le in state.locus_evidence:
            lines.append(f"### {le.target} vs {le.reference_genome or 'no reference'}\n")
            lines.append("```json\n")
            lines.append(json.dumps(le.model_dump(), indent=2))
            lines.append("\n```\n")

    if state.relations:
        lines.append("## Evidence relations\n")
        for rel in state.relations:
            note = f" ({rel.note})" if rel.note else ""
            lines.append(f"- {rel.source_id} {rel.kind.value} {rel.target_id}{note}\n")

    path.write_text("\n".join(lines))
