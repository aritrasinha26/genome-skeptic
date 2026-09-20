"""Load curated gene_orthologue families. Sequences are never invented."""
from __future__ import annotations

from pathlib import Path

import yaml

from genome_skeptic.io_utils import read_fasta
from genome_skeptic.isolation import assert_agent_accessible
from genome_skeptic.models import FamilyMember, TargetFamily, TargetProfile


def default_family_roots() -> list[Path]:
    here = Path(__file__).resolve().parent
    return [
        here / "data" / "target_families",
        here.parents[1] / "data" / "target_families",
    ]


def family_root(explicit: str | Path | None = None) -> Path | None:
    if explicit:
        p = Path(explicit)
        assert_agent_accessible(p)
        return p if p.exists() else None
    for cand in default_family_roots():
        if cand.exists():
            assert_agent_accessible(cand)
            return cand
    return None


def _load_index(root: Path) -> dict[str, str]:
    path = root / "index.yaml"
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    aliases = raw.get("aliases") or {}
    return {str(k): str(v) for k, v in aliases.items()}


def canonical_family_id(name: str | None, root: Path | None = None) -> str | None:
    if not name:
        return None
    aliases = _load_index(root) if root else {}
    return aliases.get(name, name)


def load_family(family_id: str, root: Path | None = None) -> TargetFamily | None:
    root = root or family_root()
    if root is None or not family_id:
        return None
    fid = canonical_family_id(family_id, root) or family_id
    d = root / fid
    yaml_path = d / "family.yaml"
    faa = d / "members.faa"
    if not yaml_path.exists():
        return None
    assert_agent_accessible(yaml_path)
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    seqs = dict(read_fasta(faa)) if faa.exists() else {}
    forbidden = {str(x) for x in (raw.get("forbidden_protein_ids") or [])}
    members: list[FamilyMember] = []
    for rec in raw.get("members") or []:
        pid = str(rec.get("protein_id") or "")
        if not pid or pid in forbidden:
            continue
        seq = seqs.get(pid, "")
        members.append(
            FamilyMember(
                protein_id=pid,
                species=str(rec.get("species") or ""),
                gene_id=rec.get("gene_id"),
                locus_tag=rec.get("locus_tag"),
                length_aa=int(rec.get("length_aa") or len(seq) or 0),
                sequence=seq,
                fusion_or_split=str(rec.get("fusion_or_split") or "canonical"),
            )
        )
    return TargetFamily(
        family_id=str(raw.get("family_id") or fid),
        display_name=str(raw.get("display_name") or fid),
        members=members,
        domain_architecture=list(raw.get("domain_architecture") or []),
        known_fusion_or_split=list(raw.get("known_fusion_or_split") or []),
        partner_families=list(raw.get("partner_families") or []),
        msa_provenance=dict(raw.get("msa_provenance") or {}),
        hmm_provenance=dict(raw.get("hmm_provenance") or {}),
        phylo_provenance=dict(raw.get("phylo_provenance") or {}),
        forbidden_protein_ids=list(raw.get("forbidden_protein_ids") or []),
        competing_families=list(raw.get("competing_families") or []),
        family_class=str(raw.get("family_class") or ""),
    )


def list_family_ids(root: Path | None = None) -> list[str]:
    root = root or family_root()
    if root is None or not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "family.yaml").exists())


def families_sharing_class(family: TargetFamily, root: Path | None = None) -> list[str]:
    """Other curated families with the same family_class. Not a gene-specific rule."""
    if not family.family_class:
        return []
    out = []
    for fid in list_family_ids(root):
        if fid == family.family_id:
            continue
        other = load_family(fid, root)
        if other and other.family_class == family.family_class:
            out.append(fid)
    return out


def family_paths(family_id: str, root: Path | None = None) -> dict[str, Path]:
    root = root or family_root() or Path(".")
    fid = canonical_family_id(family_id, root) or family_id
    d = root / fid
    return {
        "dir": d,
        "yaml": d / "family.yaml",
        "members": d / "members.faa",
        "alignment": d / "members.aln.faa",
        "hmm": d / "family.hmm",
    }


def resolve_family_for_profile(profile: TargetProfile, root: Path | None = None) -> TargetFamily | None:
    """Attach a curated family when a family_id or known alias is available."""
    if profile.family is not None:
        return profile.family
    root = root or family_root()
    name = profile.family_id or profile.query_id
    family = load_family(name, root)
    if family is not None:
        profile.family = family
        profile.family_id = family.family_id
    return family


def _nw(a: str, b: str, match: int = 1, mismatch: int = -1, gap: int = -1) -> tuple[str, str]:
    n, m = len(a), len(b)
    score = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        score[i][0] = i * gap
    for j in range(1, m + 1):
        score[0][j] = j * gap
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            diag = score[i - 1][j - 1] + (match if a[i - 1] == b[j - 1] else mismatch)
            score[i][j] = max(diag, score[i - 1][j] + gap, score[i][j - 1] + gap)
    i, j = n, m
    oa, ob = [], []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and score[i][j] == score[i - 1][j - 1] + (match if a[i - 1] == b[j - 1] else mismatch):
            oa.append(a[i - 1])
            ob.append(b[j - 1])
            i -= 1
            j -= 1
        elif i > 0 and score[i][j] == score[i - 1][j] + gap:
            oa.append(a[i - 1])
            ob.append("-")
            i -= 1
        else:
            oa.append("-")
            ob.append(b[j - 1] if j > 0 else "-")
            j = max(0, j - 1)
    return "".join(reversed(oa)), "".join(reversed(ob))


def build_star_msa(records: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Star alignment seeded on the first sequence. Used only to feed hmmbuild."""
    if not records:
        return []
    seed_id, seed = records[0]
    aligned = [(seed_id, seed)]
    for pid, seq in records[1:]:
        a_seed, a_other = _nw(seed, seq)
        grown = []
        for rid, rseq in aligned:
            out = []
            si = 0
            for ch in a_seed:
                if ch == "-":
                    out.append("-")
                else:
                    out.append(rseq[si] if si < len(rseq) else "-")
                    si += 1
            grown.append((rid, "".join(out)))
        aligned = grown
        aligned.append((pid, a_other))
        seed = aligned[0][1]
    width = max(len(s) for _, s in aligned)
    return [(i, s.ljust(width, "-")) for i, s in aligned]

