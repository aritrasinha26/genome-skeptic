from __future__ import annotations

import re

from genome_skeptic.io_utils import iter_fasta_records
from genome_skeptic.models import CatalyticResidue, QueryDomain, TargetProfile, TargetType
from genome_skeptic.tools.gene_search import is_nucleotide, translate_frame


def parse_header_profile(query_id: str, header: str, sequence: str) -> TargetProfile:
    profile = TargetProfile(query_id=query_id, sequence=sequence)
    rest = header[len(query_id):].strip() if header.startswith(query_id) else header
    fields = dict(re.findall(r"(\w+)=([^\s]+)", rest))
    if "target_type" in fields:
        raw = fields["target_type"].strip().lower()
        try:
            profile.target_type = TargetType(raw)
        except ValueError as exc:
            raise ValueError(f"Unknown target_type {raw!r}; expected exact_allele, gene_orthologue, or protein_family") from exc
    if "length_aa" in fields:
        try:
            profile.expected_length_aa = int(fields["length_aa"])
        except ValueError:
            pass
    if "taxonomy" in fields:
        profile.expected_taxonomy = fields["taxonomy"]
    if "family" in fields:
        profile.family_id = fields["family"]
    if "neighbors" in fields:
        profile.expected_neighbors = [n for n in fields["neighbors"].split(",") if n]
    if "domains" in fields:
        domains = []
        for i, chunk in enumerate(fields["domains"].split(","), start=1):
            if "-" not in chunk:
                continue
            a, b = chunk.split("-", 1)
            try:
                start, end = int(a) - 1, int(b)
            except ValueError:
                continue
            domains.append(QueryDomain(name=f"d{i}", start=max(0, start), end=end))
        profile.domains = domains
    if "catalytic" in fields:
        residues = []
        for chunk in fields["catalytic"].split(","):
            m = re.fullmatch(r"(\d+)([A-Za-z])", chunk)
            if not m:
                continue
            residues.append(CatalyticResidue(position=int(m.group(1)) - 1, residue=m.group(2).upper()))
        profile.catalytic_residues = residues
    if profile.expected_length_aa is None:
        if is_nucleotide(sequence):
            aa = max((translate_frame(sequence.upper(), f) for f in range(3)), key=len)
            profile.expected_length_aa = len(aa.split("*")[0]) if aa else None
        else:
            profile.expected_length_aa = len(sequence)
    return profile


def load_target_profiles(path: str) -> list[TargetProfile]:
    return [parse_header_profile(qid, header, seq) for qid, header, seq in iter_fasta_records(path)]
