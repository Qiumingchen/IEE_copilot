from pathlib import Path

from app.core.config import Settings


def test_default_settings_use_real_science_without_fallbacks(monkeypatch):
    monkeypatch.delenv("USE_REAL_SCIENCE_PROVIDERS", raising=False)
    monkeypatch.delenv("ALLOW_SCIENCE_FALLBACKS", raising=False)

    settings = Settings(_env_file=None)

    assert settings.use_real_science_providers is True
    assert settings.allow_science_fallbacks is False


def test_env_example_uses_real_science_without_fallbacks():
    env_example = Path(".env.example")
    assert env_example.exists()

    content = env_example.read_text(encoding="utf-8")

    assert "USE_REAL_SCIENCE_PROVIDERS=true" in content
    assert "ALLOW_SCIENCE_FALLBACKS=false" in content


def test_env_example_configures_local_sequence_similarity_demo():
    env_example = Path(".env.example")
    assert env_example.exists()

    content = env_example.read_text(encoding="utf-8")

    assert "SEQUENCE_SIMILARITY_FASTA_PATH=/app/data/demo/homologs.fasta" in content
    assert (
        "SEQUENCE_SIMILARITY_COMMAND=python scripts/similarity/sequence_similarity_wrapper.py "
        "--backend local --database /app/data/demo/homologs.fasta"
    ) in content


def test_demo_homolog_fasta_contains_mtgase_like_sequences():
    fasta_path = Path("data/demo/homologs.fasta")
    assert fasta_path.exists()

    content = fasta_path.read_text(encoding="utf-8")

    assert ">MTGASE_DEMO_90" in content
    assert ">MTGASE_DEMO_80" in content
    assert "ACDEFGHIVL" in content


def test_demo_data_is_included_in_api_and_worker_images():
    api_dockerfile = Path("apps/api/Dockerfile").read_text(encoding="utf-8")
    worker_dockerfile = Path("apps/worker/Dockerfile").read_text(encoding="utf-8")
    dockerignore = Path(".dockerignore").read_text(encoding="utf-8")

    assert "COPY data /app/data" in api_dockerfile
    assert "COPY data /app/data" in worker_dockerfile
    assert "!data/demo/**" in dockerignore
