from collections import Counter
from dataclasses import dataclass
from math import log2

from app.services.msa import MsaAlignment, MsaAlignedRecord


@dataclass(frozen=True)
class ConservationSite:
    query_position: int
    alignment_column: int
    wildtype_residue: str
    shannon_entropy: float
    wildtype_frequency: float
    conservation_category: str


@dataclass(frozen=True)
class ConservationProfile:
    sequence_count: int
    sites: list[ConservationSite]


def calculate_conservation_profile(
    alignment: MsaAlignment,
    *,
    query_identifier: str = "query",
) -> ConservationProfile:
    query = _find_query_record(alignment.records, query_identifier)
    query_position = 0
    sites: list[ConservationSite] = []

    for column_index, wildtype_residue in enumerate(query.aligned_sequence):
        if wildtype_residue == "-":
            continue

        query_position += 1
        residues = [
            record.aligned_sequence[column_index]
            for record in alignment.records
            if column_index < len(record.aligned_sequence)
        ]
        wildtype_frequency = residues.count(wildtype_residue) / len(residues) if residues else 0.0
        sites.append(
            ConservationSite(
                query_position=query_position,
                alignment_column=column_index + 1,
                wildtype_residue=wildtype_residue,
                shannon_entropy=_shannon_entropy(residues),
                wildtype_frequency=wildtype_frequency,
                conservation_category=_category_for_frequency(wildtype_frequency),
            )
        )

    return ConservationProfile(sequence_count=alignment.sequence_count, sites=sites)


def _find_query_record(
    records: list[MsaAlignedRecord],
    query_identifier: str,
) -> MsaAlignedRecord:
    for record in records:
        if record.identifier == query_identifier:
            return record
    raise ValueError(f"query sequence not found in alignment: {query_identifier}")


def _shannon_entropy(residues: list[str]) -> float:
    if not residues:
        return 0.0
    counts = Counter(residues)
    total = len(residues)
    return -sum((count / total) * log2(count / total) for count in counts.values())


def _category_for_frequency(wildtype_frequency: float) -> str:
    if wildtype_frequency >= 0.9:
        return "highly_conserved"
    if wildtype_frequency >= 0.6:
        return "moderately_conserved"
    return "variable"
