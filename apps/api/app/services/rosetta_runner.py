from dataclasses import dataclass
import json
import subprocess
from typing import Any

from app.services.mutations import ParsedMutation
from app.services.provenance import build_fallback_provenance, build_real_provenance


@dataclass(frozen=True)
class RosettaRunResult:
    payload: dict[str, Any]


def run_rosetta_ddg_with_runner(
    *,
    mutation_string: str,
    mutations: list[ParsedMutation],
    mutation_file: str,
    command: str | None,
    allow_fallback: bool,
) -> RosettaRunResult:
    failure_warning: str | None = None
    if command:
        completed = subprocess.run(
            command,
            input=mutation_file,
            capture_output=True,
            text=True,
            check=False,
            shell=True,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            parsed = json.loads(completed.stdout)
            ddg = float(parsed["ddg_kcal_per_mol"])
            return RosettaRunResult(
                payload={
                    "mutation_string": mutation_string,
                    "mutation_file": mutation_file,
                    "parsed_mutations": [mutation.model_dump() for mutation in mutations],
                    "ddg_kcal_per_mol": ddg,
                    "interpretation": parsed.get("interpretation")
                    or ("stabilizing" if ddg < 0 else "destabilizing_or_neutral"),
                    "runner": build_real_provenance(
                        provider="rosetta",
                        extra={
                            "exit_code": completed.returncode,
                            "command_source": "configured",
                        },
                    ),
                }
            )
        failure_warning = (
            f"Rosetta ddG runner failed with exit code {completed.returncode}: {completed.stderr}"
        ).strip()
        if not allow_fallback:
            raise RuntimeError(failure_warning)

    if not allow_fallback:
        raise RuntimeError("Rosetta ddG runner is not configured and science fallbacks are disabled")

    ddg = _fallback_ddg_for_mutation(mutation_string)
    return RosettaRunResult(
        payload={
            "mutation_string": mutation_string,
            "mutation_file": mutation_file,
            "parsed_mutations": [mutation.model_dump() for mutation in mutations],
            "ddg_kcal_per_mol": ddg,
            "interpretation": "stabilizing" if ddg < 0 else "destabilizing_or_neutral",
            "runner": build_fallback_provenance(
                provider="rosetta",
                warning=failure_warning or "Rosetta runner not configured; placeholder ddG used.",
            ),
        }
    )


def _fallback_ddg_for_mutation(mutation_string: str) -> float:
    total = sum(ord(char) for char in mutation_string)
    return round(((total % 21) - 10) / 5, 2)
