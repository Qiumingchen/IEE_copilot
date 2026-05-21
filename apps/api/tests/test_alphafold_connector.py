from app.core.config import get_settings
from app.external.alphafold import (
    MockAlphaFoldClient,
    RealAlphaFoldClient,
    get_alphafold_client,
    parse_alphafold_prediction,
)


def test_mock_alphafold_client_fetches_model_by_uniprot():
    client = MockAlphaFoldClient()

    model = client.fetch_model_by_uniprot("P12345")

    assert model.model_id == "AF-P12345-F1"
    assert model.uniprot_id == "P12345"
    assert model.confidence_summary["mean_plddt"] == 90.0


def test_mock_alphafold_client_downloads_predicted_structure():
    client = MockAlphaFoldClient()

    pdb_text = client.download_predicted_structure("AF-P12345-F1")

    assert "HEADER" in pdb_text
    assert "AF-P12345-F1" in pdb_text


def test_mock_alphafold_client_exposes_confidence_metadata():
    client = MockAlphaFoldClient()

    confidence = client.store_confidence_metadata("AF-P12345-F1")

    assert confidence == {
        "model_id": "AF-P12345-F1",
        "mean_plddt": 90.0,
        "confidence_version": "mock-v1",
    }


def test_parse_alphafold_prediction_extracts_model_metadata():
    payload = [
        {
            "entryId": "AF-P81453-F1",
            "uniprotAccession": "P81453",
            "pdbUrl": "https://alphafold.ebi.ac.uk/files/AF-P81453-F1-model_v4.pdb",
            "paeDocUrl": "https://alphafold.ebi.ac.uk/files/AF-P81453-F1-predicted_aligned_error_v4.json",
            "confidenceScore": 91.2,
        }
    ]

    model = parse_alphafold_prediction(payload)

    assert model.model_id == "AF-P81453-F1"
    assert model.uniprot_id == "P81453"
    assert model.structure_url.endswith(".pdb")
    assert model.confidence_summary["mean_plddt"] == 91.2


def test_get_alphafold_client_returns_real_client_when_enabled(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")

    assert isinstance(get_alphafold_client(), RealAlphaFoldClient)
    get_settings.cache_clear()
