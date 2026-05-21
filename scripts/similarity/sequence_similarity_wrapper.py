"""Sequence similarity wrapper for IEE-Copilot homolog collection.

The worker sends query FASTA on stdin and expects tabular stdout:

    accession<TAB>identity_percent<TAB>coverage_percent

This script provides a stable command boundary for local smoke tests, MMseqs2,
and BLASTP. The local backend is not a replacement for BLAST/MMseqs2; it is a
small deterministic scanner for development and installation checks.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FastaRecord:
    accession: str
    sequence: str


@dataclass(frozen=True)
class SimilarityHit:
    accession: str
    identity_percent: float
    coverage_percent: float


def main() -> int:
    parser = argparse.ArgumentParser(description="Run sequence similarity and normalize hits.")
    parser.add_argument("--backend", choices=["local", "mmseqs", "blastp"], required=True)
    parser.add_argument("--database", required=True, help="FASTA path for local/MMseqs or BLAST db prefix.")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    query_fasta = sys.stdin.read()
    try:
        if args.backend == "local":
            hits = run_local_backend(query_fasta, Path(args.database), args.limit)
        elif args.backend == "mmseqs":
            hits = run_mmseqs_backend(query_fasta, Path(args.database), args.limit)
        else:
            hits = run_blastp_backend(query_fasta, args.database, args.limit)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    for hit in hits:
        print(f"{hit.accession}\t{hit.identity_percent:.1f}\t{hit.coverage_percent:.1f}")
    return 0


def run_local_backend(query_fasta: str, database_path: Path, limit: int) -> list[SimilarityHit]:
    query = parse_fasta_text(query_fasta)
    if not query:
        raise RuntimeError("query FASTA is empty")
    if not database_path.exists():
        raise RuntimeError(f"database FASTA not found: {database_path}")

    query_sequence = query[0].sequence
    hits = [
        calculate_ungapped_similarity(query_sequence, record)
        for record in parse_fasta_text(database_path.read_text(encoding="utf-8"))
    ]
    return sorted(
        hits,
        key=lambda hit: (hit.coverage_percent, hit.identity_percent, hit.accession),
        reverse=True,
    )[:limit]


def run_mmseqs_backend(query_fasta: str, database_path: Path, limit: int) -> list[SimilarityHit]:
    if shutil.which("mmseqs") is None:
        raise RuntimeError("mmseqs executable not found on PATH")
    if not database_path.exists():
        raise RuntimeError(f"MMseqs target FASTA not found: {database_path}")

    with tempfile.TemporaryDirectory(prefix="iee-mmseqs-") as tmp:
        tmp_path = Path(tmp)
        query_fasta_path = tmp_path / "query.fasta"
        query_fasta_path.write_text(query_fasta, encoding="utf-8")
        query_db = tmp_path / "query_db"
        target_db = tmp_path / "target_db"
        result_db = tmp_path / "result_db"
        result_tsv = tmp_path / "result.tsv"

        run_command(["mmseqs", "createdb", str(query_fasta_path), str(query_db)])
        run_command(["mmseqs", "createdb", str(database_path), str(target_db)])
        run_command(["mmseqs", "search", str(query_db), str(target_db), str(result_db), str(tmp_path)])
        run_command(
            [
                "mmseqs",
                "convertalis",
                str(query_db),
                str(target_db),
                str(result_db),
                str(result_tsv),
                "--format-output",
                "target,pident,qcov",
            ]
        )
        return parse_similarity_table(result_tsv.read_text(encoding="utf-8"))[:limit]


def run_blastp_backend(query_fasta: str, database: str, limit: int) -> list[SimilarityHit]:
    if shutil.which("blastp") is None:
        raise RuntimeError("blastp executable not found on PATH")
    completed = subprocess.run(
        [
            "blastp",
            "-query",
            "-",
            "-db",
            database,
            "-outfmt",
            "6 sseqid pident qcovs",
            "-max_target_seqs",
            str(limit),
        ],
        input=query_fasta,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"blastp failed with exit code {completed.returncode}: {completed.stderr}")
    return parse_similarity_table(completed.stdout)[:limit]


def run_command(command: list[str]) -> None:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"{command[0]} failed with exit code {completed.returncode}: {completed.stderr}"
        )


def parse_similarity_table(text: str) -> list[SimilarityHit]:
    hits = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        columns = stripped.split("\t")
        if len(columns) < 3:
            columns = stripped.split()
        if len(columns) < 3:
            continue
        hits.append(
            SimilarityHit(
                accession=columns[0],
                identity_percent=float(columns[1]),
                coverage_percent=float(columns[2]),
            )
        )
    return hits


def parse_fasta_text(text: str) -> list[FastaRecord]:
    records: list[FastaRecord] = []
    accession: str | None = None
    sequence_lines: list[str] = []

    def flush() -> None:
        if accession and sequence_lines:
            records.append(FastaRecord(accession=accession, sequence="".join(sequence_lines)))

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(">"):
            flush()
            accession = stripped[1:].split()[0]
            sequence_lines = []
        else:
            sequence_lines.append(stripped)
    flush()
    return records


def calculate_ungapped_similarity(query_sequence: str, record: FastaRecord) -> SimilarityHit:
    query = normalize_sequence(query_sequence)
    target = normalize_sequence(record.sequence)
    if not query or not target:
        return SimilarityHit(record.accession, 0.0, 0.0)
    comparable = min(len(query), len(target))
    matches = sum(1 for index in range(comparable) if query[index] == target[index])
    identity = (matches / comparable) * 100 if comparable else 0.0
    coverage = (comparable / len(query)) * 100
    return SimilarityHit(record.accession, round(identity, 3), round(coverage, 3))


def normalize_sequence(sequence: str) -> str:
    return "".join(sequence.upper().split())


if __name__ == "__main__":
    raise SystemExit(main())
