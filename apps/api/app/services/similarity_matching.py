from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EnzymeEntry, EnzymeFamily, EnzymeModule, ProteinSequence


@dataclass(frozen=True)
class SimilarityResult:
    identity: float
    coverage: float
    aligned_length: int


@dataclass(frozen=True)
class SimilarityMatch:
    enzyme: EnzymeEntry
    identity: float
    coverage: float


def calculate_ungapped_similarity(query_sequence: str, candidate_sequence: str) -> SimilarityResult:
    query = query_sequence.upper().replace(" ", "").replace("\n", "")
    candidate = candidate_sequence.upper().replace(" ", "").replace("\n", "")
    if not query or not candidate:
        return SimilarityResult(identity=0.0, coverage=0.0, aligned_length=0)

    best_matches = 0
    best_length = 0
    min_offset = -len(candidate) + 1
    max_offset = len(query) - 1

    for offset in range(min_offset, max_offset + 1):
        query_start = max(0, offset)
        candidate_start = max(0, -offset)
        overlap = min(len(query) - query_start, len(candidate) - candidate_start)
        if overlap <= 0:
            continue

        matches = sum(
            1
            for index in range(overlap)
            if query[query_start + index] == candidate[candidate_start + index]
        )
        if matches > best_matches or (matches == best_matches and overlap > best_length):
            best_matches = matches
            best_length = overlap

    if best_length == 0:
        return SimilarityResult(identity=0.0, coverage=0.0, aligned_length=0)

    return SimilarityResult(
        identity=best_matches / best_length,
        coverage=best_length / len(query),
        aligned_length=best_length,
    )


def find_level_two_similarity_match(
    db: Session,
    *,
    module: EnzymeModule,
    query_sequence: str,
    min_identity: float = 0.4,
    min_coverage: float = 0.7,
) -> SimilarityMatch | None:
    candidates = db.execute(
        select(EnzymeEntry, ProteinSequence)
        .join(EnzymeFamily, EnzymeFamily.id == EnzymeEntry.family_id)
        .join(ProteinSequence, ProteinSequence.enzyme_entry_id == EnzymeEntry.id)
        .where(EnzymeFamily.module == module)
    ).all()

    best_match: SimilarityMatch | None = None
    for enzyme, protein_sequence in candidates:
        candidate_sequence = protein_sequence.mature_sequence or protein_sequence.sequence
        result = calculate_ungapped_similarity(query_sequence, candidate_sequence)
        if result.identity < min_identity or result.coverage < min_coverage:
            continue
        if best_match is None or (result.identity, result.coverage) > (
            best_match.identity,
            best_match.coverage,
        ):
            best_match = SimilarityMatch(
                enzyme=enzyme,
                identity=result.identity,
                coverage=result.coverage,
            )

    return best_match
