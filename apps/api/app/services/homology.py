from dataclasses import dataclass, replace
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import shlex
import subprocess
from typing import Protocol

from app.services.similarity_matching import calculate_ungapped_similarity


MAX_UNIPROT_ENTRY_FETCH_WORKERS = 8


@dataclass(frozen=True)
class HomologSearchParameters:
    identity_min: float = 40
    identity_max: float = 95
    coverage_min: float = 70
    max_sequences: int = 25
    search_mode: str = "metadata_search"


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
    homologs, _diagnostics = collect_homologs_with_diagnostics(
        query_sequence,
        candidates,
        parameters=parameters,
    )
    return homologs


def collect_homologs_with_diagnostics(
    query_sequence: str,
    candidates: Iterable[HomologSequence],
    parameters: HomologSearchParameters | None = None,
) -> tuple[list[HomologSequence], dict[str, int]]:
    params = parameters or HomologSearchParameters()
    candidate_list = list(candidates)
    scored = [_score_homolog(query_sequence, candidate) for candidate in candidate_list]
    identity_filtered = filter_by_identity(
        scored,
        identity_min=params.identity_min,
        identity_max=params.identity_max,
    )
    coverage_filtered = filter_by_coverage(
        identity_filtered,
        coverage_min=params.coverage_min,
    )
    deduplicated = deduplicate_sequences(coverage_filtered)
    homologs = limit_max_sequences(deduplicated, max_sequences=params.max_sequences)
    diagnostics = {
        "candidate_count": len(candidate_list),
        "scored_count": len(scored),
        "passed_identity_count": len(identity_filtered),
        "filtered_identity_count": len(scored) - len(identity_filtered),
        "passed_coverage_count": len(coverage_filtered),
        "filtered_coverage_count": len(identity_filtered) - len(coverage_filtered),
        "deduplicated_count": len(deduplicated),
        "duplicate_count": len(coverage_filtered) - len(deduplicated),
        "returned_count": len(homologs),
        "max_sequences": params.max_sequences,
    }
    return homologs, diagnostics


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
    for entry in _fetch_uniprot_entries_in_hit_order(
        hits,
        uniprot_client=uniprot_client,
    ):
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


def fetch_local_fasta_similarity_candidates(
    *,
    query_sequence: str,
    fasta_path: str,
    size: int,
) -> list[HomologSequence]:
    candidates = list(_parse_homolog_fasta(Path(fasta_path)))
    scored = [_score_homolog(query_sequence, candidate) for candidate in candidates]
    return sorted(scored, key=_similarity_prefilter_sort_key, reverse=True)[:size]


def run_configured_sequence_similarity_search(
    *,
    query_sequence: str,
    fasta_path: str,
    command: str,
    size: int,
) -> list[HomologSequence]:
    fasta_records = {record.accession: record for record in _parse_homolog_fasta(Path(fasta_path))}
    completed = subprocess.run(
        _split_command(command),
        input=f">query\n{query_sequence}\n",
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"sequence similarity command failed with exit code {completed.returncode}: {completed.stderr}"
        )

    candidates: list[HomologSequence] = []
    for hit in _parse_similarity_command_hits(completed.stdout):
        record = fasta_records.get(hit["accession"])
        if record is None:
            continue
        candidates.append(
            replace(
                record,
                source="sequence_similarity_command",
                identity=hit["identity"],
                coverage=hit["coverage"],
            )
        )
    return sorted(candidates, key=_similarity_prefilter_sort_key, reverse=True)[:size]


def _fetch_uniprot_entries_in_hit_order(
    hits,
    *,
    uniprot_client: UniProtHomologClient,
):
    if not hits:
        return []
    max_workers = min(MAX_UNIPROT_ENTRY_FETCH_WORKERS, len(hits))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(lambda hit: uniprot_client.fetch_entry(hit.accession), hits))


def _parse_homolog_fasta(path: Path) -> Iterable[HomologSequence]:
    accession: str | None = None
    name = ""
    organism: str | None = None
    sequence_lines: list[str] = []

    def flush_record() -> HomologSequence | None:
        if not accession or not sequence_lines:
            return None
        return HomologSequence(
            accession=accession,
            name=name or accession,
            organism=organism,
            sequence="".join(sequence_lines),
            source="local_fasta_similarity",
        )

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(">"):
            record = flush_record()
            if record is not None:
                yield record
            accession, name, organism = _parse_fasta_header(stripped[1:].strip())
            sequence_lines = []
            continue
        if accession:
            sequence_lines.append(stripped)

    record = flush_record()
    if record is not None:
        yield record


def _parse_similarity_command_hits(output: str) -> Iterable[dict[str, float | str]]:
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        columns = stripped.split("\t")
        if len(columns) < 3:
            columns = stripped.split()
        if len(columns) < 3:
            continue
        accession = columns[0].strip()
        identity = _percentage_to_fraction(float(columns[1]))
        coverage = _percentage_to_fraction(float(columns[2]))
        if accession:
            yield {"accession": accession, "identity": identity, "coverage": coverage}


def _split_command(command: str) -> list[str]:
    return shlex.split(command, posix=os.name != "nt")


def _parse_fasta_header(header: str) -> tuple[str | None, str, str | None]:
    if not header:
        return None, "", None
    parts = header.split(maxsplit=1)
    accession = parts[0]
    description = parts[1] if len(parts) > 1 else accession
    organism = None
    if " OS=" in f" {description}":
        description, organism_part = description.split(" OS=", maxsplit=1)
        organism = organism_part.split(" OX=", maxsplit=1)[0].strip() or None
    elif description.endswith("]") and "[" in description:
        description, bracket_organism = description.rsplit("[", maxsplit=1)
        organism = bracket_organism[:-1].strip() or None
    return accession, description.strip() or accession, organism


def _search_uniprot_homolog_hits(
    *,
    enzyme_name: str,
    ec_number: str | None,
    uniprot_client: UniProtHomologClient,
    size: int,
):
    hits_by_accession = {}
    keyword = _canonical_homolog_keyword(enzyme_name)
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


def _canonical_homolog_keyword(enzyme_name: str) -> str:
    keyword = enzyme_name.strip()
    if keyword.lower() == "mock microbial transglutaminase":
        return "Microbial transglutaminase"
    return keyword


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


def _similarity_prefilter_sort_key(candidate: HomologSequence) -> tuple[float, float, str]:
    return (
        candidate.coverage or 0.0,
        candidate.identity or 0.0,
        candidate.accession,
    )
