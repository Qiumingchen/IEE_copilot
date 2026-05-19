from dataclasses import dataclass, replace
from collections.abc import Iterable

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
