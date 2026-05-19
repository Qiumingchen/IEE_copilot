from app.external.alphafold import MockAlphaFoldClient


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
