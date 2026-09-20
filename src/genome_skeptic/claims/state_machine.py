from __future__ import annotations

from genome_skeptic.models import ClaimStatus, FalsificationResult, FalsificationTest


def resolve_claim_status(tests: list[FalsificationTest]) -> ClaimStatus:
    """Deterministic claim-state machine.

    `supported` means the *executed* attack plan did not find a successful
    disproof. Skipped/unavailable tests do not force ``unresolved``; they
    lower evidence completeness instead. ``supported`` is not certainty.
    """
    completed = [t for t in tests if t.status == "completed"]
    if any(t.result == FalsificationResult.rejects_claim for t in completed):
        return ClaimStatus.rejected
    if any(t.result == FalsificationResult.weakens_claim for t in completed):
        return ClaimStatus.weakened
    blocking_open = [t for t in tests if t.blocking and t.status == "unresolved"]
    if blocking_open:
        return ClaimStatus.unresolved
    if completed:
        return ClaimStatus.supported
    if any(t.status == "unresolved" for t in tests):
        return ClaimStatus.unresolved
    return ClaimStatus.supported


def confidence_for(
    status: ClaimStatus,
    tests: list[FalsificationTest],
    *,
    base: float,
    max_supported: float,
    not_detected: bool = False,
    homology_support: float | None = None,
) -> float:
    """Status modulates a homology-derived score. Missing optional tests do not flatten distinct hits.

    When homology_support is omitted, the historical status-band formula is used
    so existing unit tests remain meaningful.
    """
    optional_open = sum(1 for t in tests if not t.blocking and t.status != "completed")
    if homology_support is None:
        if status == ClaimStatus.rejected:
            return max(0.05, min(0.25, base))
        if status == ClaimStatus.unresolved:
            return max(0.10, min(0.40, base))
        if status == ClaimStatus.weakened:
            return max(0.15, min(0.50, base))
        cap = max_supported - 0.04 * optional_open
        if not_detected:
            cap = min(cap, max_supported - 0.20)
        cap = min(cap, 0.85)
        return min(cap, max(base, 0.55 if not not_detected else 0.50))

    h = max(0.0, min(1.0, homology_support))
    contradict = sum(1 for t in tests if t.status == "completed" and t.result in {FalsificationResult.weakens_claim, FalsificationResult.rejects_claim})
    if status == ClaimStatus.rejected:
        conf = 0.06 + 0.18 * h
        return max(0.05, min(0.25, round(conf, 4)))
    if status == ClaimStatus.unresolved:
        conf = 0.12 + 0.28 * h
        return max(0.10, min(0.42, round(conf, 4)))
    if status == ClaimStatus.weakened:
        conf = 0.18 + 0.52 * h - 0.03 * min(contradict, 4)
        return max(0.15, min(0.72, round(conf, 4)))
    conf = 0.38 + 0.48 * h - 0.02 * optional_open
    cap = min(max_supported, 0.85)
    if not_detected:
        cap = min(cap, max_supported - 0.10)
    return max(0.35, min(cap, round(conf, 4)))
