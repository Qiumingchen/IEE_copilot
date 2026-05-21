from pathlib import Path

import pytest

from app.services.mutations import parse_mutation_string
from app.services.rosetta_runner import run_rosetta_ddg_with_runner


def test_rosetta_runner_uses_fallback_when_command_missing():
    result = run_rosetta_ddg_with_runner(
        mutation_string="L10A",
        mutations=parse_mutation_string("L10A"),
        mutation_file="L 10 A",
        command=None,
        allow_fallback=True,
    )

    assert result.payload["ddg_kcal_per_mol"] == -0.6
    assert result.payload["runner"]["mode"] == "fallback"
    assert result.payload["runner"]["provider"] == "rosetta"


def test_rosetta_runner_fails_when_fallback_disabled():
    with pytest.raises(RuntimeError, match="Rosetta ddG runner is not configured"):
        run_rosetta_ddg_with_runner(
            mutation_string="L10A",
            mutations=parse_mutation_string("L10A"),
            mutation_file="L 10 A",
            command=None,
            allow_fallback=False,
        )


def test_rosetta_runner_parses_fake_runner_output(tmp_path: Path):
    script = tmp_path / "fake_rosetta.py"
    script.write_text(
        "import json\n"
        "print(json.dumps({'ddg_kcal_per_mol': -1.25, 'interpretation': 'stabilizing'}))\n",
        encoding="utf-8",
    )

    result = run_rosetta_ddg_with_runner(
        mutation_string="L10A",
        mutations=parse_mutation_string("L10A"),
        mutation_file="L 10 A",
        command=f"python {script}",
        allow_fallback=False,
    )

    assert result.payload["ddg_kcal_per_mol"] == -1.25
    assert result.payload["interpretation"] == "stabilizing"
    assert result.payload["runner"]["mode"] == "real"
    assert result.payload["runner"]["command_source"] == "configured"


def test_rosetta_runner_fallback_warning_mentions_failed_command(tmp_path: Path):
    script = tmp_path / "failing_rosetta.py"
    script.write_text(
        "import sys\n"
        "print('rosetta crashed', file=sys.stderr)\n"
        "raise SystemExit(3)\n",
        encoding="utf-8",
    )

    result = run_rosetta_ddg_with_runner(
        mutation_string="L10A",
        mutations=parse_mutation_string("L10A"),
        mutation_file="L 10 A",
        command=f"python {script}",
        allow_fallback=True,
    )

    assert result.payload["ddg_kcal_per_mol"] == -0.6
    assert result.payload["runner"]["mode"] == "fallback"
    assert "Rosetta ddG runner failed with exit code 3" in result.payload["runner"]["warning"]
    assert "rosetta crashed" in result.payload["runner"]["warning"]


def test_rosetta_runner_falls_back_when_stdout_is_not_json(tmp_path: Path):
    script = tmp_path / "invalid_json_rosetta.py"
    script.write_text("print('not-json')\n", encoding="utf-8")

    result = run_rosetta_ddg_with_runner(
        mutation_string="L10A",
        mutations=parse_mutation_string("L10A"),
        mutation_file="L 10 A",
        command=f"python {script}",
        allow_fallback=True,
    )

    assert result.payload["ddg_kcal_per_mol"] == -0.6
    assert result.payload["runner"]["mode"] == "fallback"
    assert "Rosetta ddG runner output could not be parsed" in result.payload["runner"]["warning"]


def test_rosetta_runner_falls_back_when_ddg_field_is_missing(tmp_path: Path):
    script = tmp_path / "missing_ddg_rosetta.py"
    script.write_text("import json\nprint(json.dumps({'score': -1.2}))\n", encoding="utf-8")

    result = run_rosetta_ddg_with_runner(
        mutation_string="L10A",
        mutations=parse_mutation_string("L10A"),
        mutation_file="L 10 A",
        command=f"python {script}",
        allow_fallback=True,
    )

    assert result.payload["ddg_kcal_per_mol"] == -0.6
    assert result.payload["runner"]["mode"] == "fallback"
    assert "ddg_kcal_per_mol" in result.payload["runner"]["warning"]


def test_rosetta_runner_invalid_stdout_fails_when_fallback_disabled(tmp_path: Path):
    script = tmp_path / "invalid_json_rosetta.py"
    script.write_text("print('not-json')\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="output could not be parsed"):
        run_rosetta_ddg_with_runner(
            mutation_string="L10A",
            mutations=parse_mutation_string("L10A"),
            mutation_file="L 10 A",
            command=f"python {script}",
            allow_fallback=False,
        )
