import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path("scripts/similarity/sequence_similarity_wrapper.py")
QUERY_FASTA = ">query\nACDEFGHIKL\n"


def test_sequence_similarity_wrapper_local_backend_outputs_tabular_hits(tmp_path: Path):
    database = tmp_path / "homologs.fasta"
    database.write_text(
        "\n".join(
            [
                ">EXACT exact match",
                "ACDEFGHIKL",
                ">NEAR near homolog",
                "ACDEFGHIVL",
                ">DISTANT distant protein",
                "VVVVVVVVVV",
            ]
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--backend",
            "local",
            "--database",
            str(database),
            "--limit",
            "2",
        ],
        input=QUERY_FASTA,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout.splitlines() == [
        "EXACT\t100.0\t100.0",
        "NEAR\t90.0\t100.0",
    ]


def test_sequence_similarity_wrapper_reports_missing_mmseqs(tmp_path: Path, monkeypatch):
    database = tmp_path / "homologs.fasta"
    database.write_text(">NEAR\nACDEFGHIVL\n", encoding="utf-8")
    monkeypatch.setenv("PATH", "")

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--backend",
            "mmseqs",
            "--database",
            str(database),
        ],
        input=QUERY_FASTA,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "mmseqs executable not found" in completed.stderr
