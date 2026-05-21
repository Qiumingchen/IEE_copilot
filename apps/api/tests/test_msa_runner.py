from pathlib import Path

import pytest

from app.services.msa import MsaInputSequence
from app.services.msa_runner import run_msa_with_runner


def test_run_msa_with_runner_uses_fallback_when_mafft_missing():
    result = run_msa_with_runner(
        [MsaInputSequence(identifier="query", sequence="ACD")],
        mafft_bin=None,
        allow_fallback=True,
    )

    assert result.alignment.to_fasta() == ">query\nACD\n"
    assert result.runner["provider"] == "mafft"
    assert result.runner["mode"] == "fallback"
    assert "warning" in result.runner


def test_run_msa_with_runner_fails_when_fallback_disabled():
    with pytest.raises(RuntimeError, match="MAFFT executable is not configured"):
        run_msa_with_runner(
            [MsaInputSequence(identifier="query", sequence="ACD")],
            mafft_bin=None,
            allow_fallback=False,
        )


def test_run_msa_with_runner_uses_fake_mafft_executable(tmp_path: Path):
    script = tmp_path / "fake_mafft.py"
    script.write_text(
        "import sys\n"
        "data = sys.stdin.read()\n"
        "print(data.strip())\n",
        encoding="utf-8",
    )

    result = run_msa_with_runner(
        [MsaInputSequence(identifier="query", sequence="ACD")],
        mafft_bin=f"python {script}",
        allow_fallback=False,
    )

    assert result.alignment.to_fasta() == ">query\nACD\n"
    assert result.runner["mode"] == "real"
