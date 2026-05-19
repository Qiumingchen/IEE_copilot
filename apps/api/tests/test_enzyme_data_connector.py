from app.external.enzyme_data import (
    ExternalKineticParameter,
    ExternalMutantRecord,
    ExternalPropertyDatum,
    MockEnzymeDataClient,
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
