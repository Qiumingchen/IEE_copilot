from dataclasses import dataclass, replace
from collections.abc import Iterable
from typing import Protocol

from app.services.similarity_matching import calculate_ungapped_similarity


@dataclass(frozen=True)
class HomologSearchParameters:
    identity_min: float = 40
    identity_max: float = 95
    coverage_min: float = 70
    max_sequences: int = 500


@dataclass(frozen=True)
class HomologSequence:
    accession: str
    name: str
    organism: str | None
    sequence: str
    source: str
    identity: float | None = None
    coverage: float | None = None


class UniProtHomologClient(Protocol):
    source: str

    def search_by_ec(self, ec_number: str, size: int = 5): ...

    def search_by_keyword(self, keyword: str, size: int = 5): ...

    def fetch_entry(self, accession: str): ...


def collect_homologs(
    query_sequence: str,
    candidates: Iterable[HomologSequence],
    parameters: HomologSearchParameters | None = None,
) -> list[HomologSequence]:
    params = parameters or HomologSearchParameters()
    scored = [_score_homolog(query_sequence, candidate) for candidate in candidates]
    return limit_max_sequences(
        deduplicate_sequences(
            filter_by_coverage(
                filter_by_identity(
                    scored,
                    identity_min=params.identity_min,
                    identity_max=params.identity_max,
                ),
                coverage_min=params.coverage_min,
            )
        ),
        max_sequences=params.max_sequences,
    )


def fetch_uniprot_homolog_candidates(
    *,
    enzyme_name: str,
    ec_number: str | None,
    uniprot_client: UniProtHomologClient,
    size: int,
) -> list[HomologSequence]:
    hits = _search_uniprot_homolog_hits(
        enzyme_name=enzyme_name,
        ec_number=ec_number,
        uniprot_client=uniprot_client,
        size=size,
    )
    candidates: list[HomologSequence] = []
    for hit in hits:
        entry = uniprot_client.fetch_entry(hit.accession)
        sequence = getattr(entry, "mature_sequence", None) or getattr(entry, "sequence", None)
        if not sequence:
            continue
        candidates.append(
            HomologSequence(
                accession=entry.accession,
                name=entry.protein_name,
                organism=entry.organism,
                sequence=sequence,
                source=getattr(uniprot_client, "source", "uniprot"),
            )
        )
    return candidates


def _search_uniprot_homolog_hits(
    *,
    enzyme_name: str,
    ec_number: str | None,
    uniprot_client: UniProtHomologClient,
    size: int,
):
    hits_by_accession = {}
    keyword = enzyme_name.strip()
    if keyword:
        for hit in uniprot_client.search_by_keyword(keyword, size=size):
            hits_by_accession.setdefault(hit.accession, hit)
            if len(hits_by_accession) >= size:
                break

    remaining = size - len(hits_by_accession)
    if ec_number and remaining > 0:
        for hit in uniprot_client.search_by_ec(ec_number, size=remaining):
            hits_by_accession.setdefault(hit.accession, hit)
            if len(hits_by_accession) >= size:
                break

    if not hits_by_accession and ec_number:
        for hit in uniprot_client.search_by_ec(ec_number, size=size):
            hits_by_accession.setdefault(hit.accession, hit)

    return list(hits_by_accession.values())[:size]


def filter_by_identity(
    candidates: Iterable[HomologSequence],
    *,
    identity_min: float = 40,
    identity_max: float = 95,
) -> list[HomologSequence]:
    min_fraction = _percentage_to_fraction(identity_min)
    max_fraction = _percentage_to_fraction(identity_max)
    return [
        candidate
        for candidate in candidates
        if candidate.identity is not None and min_fraction <= candidate.identity <= max_fraction
    ]


def filter_by_coverage(
    candidates: Iterable[HomologSequence],
    *,
    coverage_min: float = 70,
) -> list[HomologSequence]:
    min_fraction = _percentage_to_fraction(coverage_min)
    return [
        candidate
        for candidate in candidates
        if candidate.coverage is not None and candidate.coverage >= min_fraction
    ]


def deduplicate_sequences(candidates: Iterable[HomologSequence]) -> list[HomologSequence]:
    best_by_sequence: dict[str, HomologSequence] = {}
    for candidate in candidates:
        sequence_key = _normalize_sequence(candidate.sequence)
        existing = best_by_sequence.get(sequence_key)
        if existing is None or _sort_key(candidate) > _sort_key(existing):
            best_by_sequence[sequence_key] = candidate
    return sorted(best_by_sequence.values(), key=_sort_key, reverse=True)


def limit_max_sequences(
    candidates: Iterable[HomologSequence],
    *,
    max_sequences: int = 500,
) -> list[HomologSequence]:
    return sorted(candidates, key=_sort_key, reverse=True)[:max_sequences]


def _score_homolog(query_sequence: str, candidate: HomologSequence) -> HomologSequence:
    result = calculate_ungapped_similarity(query_sequence, candidate.sequence)
    return replace(candidate, identity=result.identity, coverage=result.coverage)


def _percentage_to_fraction(value: float) -> float:
    return value / 100 if value > 1 else value


def _normalize_sequence(sequence: str) -> str:
    return sequence.upper().replace(" ", "").replace("\n", "")


def _sort_key(candidate: HomologSequence) -> tuple[float, float, str]:
    return (
        candidate.identity or 0.0,
        candidate.coverage or 0.0,
        candidate.accession,
    )
