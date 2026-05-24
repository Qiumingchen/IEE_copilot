from app.external.enzyme_data import (
    ExternalKineticParameter,
    ExternalMutantRecord,
    ExternalPropertyDatum,
    MockEnzymeDataClient,
    RealEnzymeDataClient,
    get_enzyme_data_client,
)


def test_mock_enzyme_data_client_fetches_opt_temperature():
    client = MockEnzymeDataClient()

    records = client.fetch_opt_temperature("microbial transglutaminase")

    assert records == [
        ExternalPropertyDatum(
            property_type="optimal_temperature",
            value_original="55",
            unit_original="degC",
            substrate=None,
            organism="Streptomyces mobaraensis",
            source="enzyme_data_mock",
            evidence="Mock BRENDA-style optimal temperature record",
        )
    ]


def test_mock_enzyme_data_client_fetches_opt_ph_for_anthraquinone_glycosyltransferase():
    client = MockEnzymeDataClient()

    records = client.fetch_opt_pH("anthraquinone glycosyltransferase")

    assert records[0].property_type == "optimal_pH"
    assert records[0].value_original == "7.5"
    assert records[0].organism == "Streptomyces mockensis"


def test_mock_enzyme_data_client_fetches_kinetic_parameters():
    client = MockEnzymeDataClient()

    records = client.fetch_kinetic_parameters("microbial transglutaminase")

    assert records == [
        ExternalKineticParameter(
            substrate="CBZ-Gln-Gly",
            km="2.1",
            kcat="31.0",
            kcat_km=None,
            unit_original="mM; s^-1",
            assay_temperature="45",
            assay_pH="7.0",
            organism="Streptomyces mobaraensis",
            source="enzyme_data_mock",
            evidence="Mock SABIO-RK-style kinetic parameter record",
        )
    ]


def test_mock_enzyme_data_client_fetches_mutants():
    client = MockEnzymeDataClient()

    records = client.fetch_mutants("microbial transglutaminase")

    assert records == [
        ExternalMutantRecord(
            mutation_string="S2P",
            effect_summary="Mock thermostability improvement",
            property_delta={"optimal_temperature_delta_degC": 5},
            substrate=None,
            organism="Streptomyces mobaraensis",
            source="enzyme_data_mock",
            evidence="Mock mutant data record",
        )
    ]


def test_get_enzyme_data_client_returns_replaceable_mock_adapter():
    client = get_enzyme_data_client()

    assert isinstance(client, MockEnzymeDataClient)


def test_real_enzyme_data_client_extracts_property_data_from_europe_pmc(monkeypatch):
    captured_queries = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Characterization of a food enzyme",
                            "abstractText": (
                                "The purified enzyme showed optimum temperature at 72 °C "
                                "and optimum pH 6.5 during starch hydrolysis."
                            ),
                            "journalTitle": "Applied Enzymology",
                            "pubYear": "2025",
                            "doi": "10.1000/real-enzyme",
                            "pmid": "12345678",
                        }
                    ]
                }
            }

    def fake_get(url, params, timeout):
        captured_queries.append((url, params, timeout))
        return Response()

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)

    client = RealEnzymeDataClient(timeout=3)

    temperatures = client.fetch_opt_temperature("alpha amylase")
    ph_values = client.fetch_opt_pH("alpha amylase")

    assert captured_queries[0][0] == "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    assert "alpha amylase optimum temperature" in captured_queries[0][1]["query"]
    assert "alpha amylase optimum pH" in captured_queries[1][1]["query"]
    assert temperatures == [
        ExternalPropertyDatum(
            property_type="optimal_temperature",
            value_original="72",
            unit_original="degC",
            organism=None,
            source="europepmc",
            evidence="Applied Enzymology 2025 doi:10.1000/real-enzyme pmid:12345678",
            reference_title="Characterization of a food enzyme",
            journal="Applied Enzymology",
            year=2025,
            doi="10.1000/real-enzyme",
            pubmed_id="12345678",
        )
    ]
    assert ph_values[0].property_type == "optimal_pH"
    assert ph_values[0].value_original == "6.5"
    assert ph_values[0].source == "europepmc"


def test_real_enzyme_data_client_extracts_common_optimum_ph_temperature_phrasing(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Characterization of microbial transglutaminase",
                            "abstractText": (
                                "The pH and temperature optima were 7.0 and 55 °C, "
                                "respectively. Maximum activity was observed at pH 7.0."
                            ),
                            "journalTitle": "Applied Food Enzymes",
                            "pubYear": "2023",
                            "doi": "10.1000/real-optima",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("microbial transglutaminase")
    ph_values = client.fetch_opt_pH("microbial transglutaminase")

    assert temperatures[0].value_original == "55"
    assert temperatures[0].unit_original == "degC"
    assert ph_values[0].value_original == "7.0"


def test_real_enzyme_data_client_extracts_kinetics_and_mutants_from_europe_pmc(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Mutation and kinetic analysis of a food enzyme",
                            "abstractText": (
                                "Variant A123V improved thermostability. For maltose, "
                                "Km was 1.8 mM and kcat was 42 s-1."
                            ),
                            "journalTitle": "Food Biocatalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/kinetic-mutant",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("amylase")
    mutants = client.fetch_mutants("amylase")

    assert kinetics == [
        ExternalKineticParameter(
            substrate=None,
            km="1.8",
            kcat="42",
            kcat_km=None,
            unit_original="mM; s^-1",
            organism=None,
            source="europepmc",
            evidence="Food Biocatalysis 2024 doi:10.1000/kinetic-mutant",
            reference_title="Mutation and kinetic analysis of a food enzyme",
            journal="Food Biocatalysis",
            year=2024,
            doi="10.1000/kinetic-mutant",
        )
    ]
    assert mutants == [
        ExternalMutantRecord(
            mutation_string="A123V",
            effect_summary="Real literature mention: Variant A123V improved thermostability.",
            property_delta={},
            substrate=None,
            organism=None,
            source="europepmc",
            evidence="Food Biocatalysis 2024 doi:10.1000/kinetic-mutant",
            reference_title="Mutation and kinetic analysis of a food enzyme",
            journal="Food Biocatalysis",
            year=2024,
            doi="10.1000/kinetic-mutant",
        )
    ]


def test_get_enzyme_data_client_uses_real_adapter_when_enabled(monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        client = get_enzyme_data_client()
        assert isinstance(client, RealEnzymeDataClient)
    finally:
        get_settings.cache_clear()


def test_real_enzyme_data_client_returns_empty_records_when_provider_fails(monkeypatch):
    def fake_get(*args, **kwargs):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    assert client.fetch_opt_temperature("alpha amylase") == []
    assert client.fetch_opt_pH("alpha amylase") == []
    assert client.fetch_kinetic_parameters("alpha amylase") == []
    assert client.fetch_mutants("alpha amylase") == []
