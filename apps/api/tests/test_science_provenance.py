from app.services.provenance import build_fallback_provenance, build_real_provenance


def test_build_real_provenance_records_provider_mode_and_url():
    provenance = build_real_provenance(
        provider="uniprot",
        source_url="https://rest.uniprot.org/uniprotkb/P81453",
        version="api-v1",
    )

    assert provenance["provider"] == "uniprot"
    assert provenance["mode"] == "real"
    assert provenance["source_url"] == "https://rest.uniprot.org/uniprotkb/P81453"
    assert provenance["version"] == "api-v1"
    assert provenance["retrieved_at"].endswith("Z")


def test_build_fallback_provenance_records_warning():
    provenance = build_fallback_provenance(
        provider="mafft",
        warning="MAFFT executable not configured; mock alignment used.",
    )

    assert provenance["provider"] == "mafft"
    assert provenance["mode"] == "fallback"
    assert provenance["warning"] == "MAFFT executable not configured; mock alignment used."
    assert provenance["retrieved_at"].endswith("Z")
