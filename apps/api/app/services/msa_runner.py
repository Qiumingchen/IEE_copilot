from dataclasses import dataclass
import subprocess

from app.services.msa import MsaAlignment, MsaInputSequence, run_mock_mafft
from app.services.provenance import build_fallback_provenance, build_real_provenance


@dataclass(frozen=True)
class MsaRunResult:
    alignment: MsaAlignment
    runner: dict
    stderr: str | None = None


def run_msa_with_runner(
    sequences: list[MsaInputSequence],
    *,
    mafft_bin: str | None,
    allow_fallback: bool,
) -> MsaRunResult:
    input_fasta = "".join(f">{sequence.identifier}\n{sequence.sequence}\n" for sequence in sequences)
    if mafft_bin:
        completed = subprocess.run(
            mafft_bin,
            input=input_fasta,
            capture_output=True,
            text=True,
            check=False,
            shell=True,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            return MsaRunResult(
                alignment=MsaAlignment.from_fasta(completed.stdout),
                runner=build_real_provenance(provider="mafft", extra={"exit_code": completed.returncode}),
                stderr=completed.stderr or None,
            )
        if not allow_fallback:
            raise RuntimeError(f"MAFFT failed with exit code {completed.returncode}: {completed.stderr}")

    if not allow_fallback:
        raise RuntimeError("MAFFT executable is not configured and science fallbacks are disabled")

    return MsaRunResult(
        alignment=run_mock_mafft(sequences),
        runner=build_fallback_provenance(
            provider="mafft",
            warning="MAFFT executable not configured; mock alignment used.",
        ),
    )
