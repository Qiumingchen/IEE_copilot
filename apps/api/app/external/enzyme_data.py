from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ExternalPropertyDatum:
    property_type: str
    value_original: str
    unit_original: str | None = None
    substrate: str | None = None
    assay_temperature: str | None = None
    assay_pH: str | None = None
    organism: str | None = None
    source: str = "enzyme_data_mock"
    evidence: str | None = None


@dataclass(frozen=True)
class ExternalKineticParameter:
    substrate: str | None = None
    km: str | None = None
    kcat: str | None = None
    kcat_km: str | None = None
    unit_original: str | None = None
    assay_temperature: str | None = None
    assay_pH: str | None = None
    organism: str | None = None
    source: str = "enzyme_data_mock"
    evidence: str | None = None


@dataclass(frozen=True)
class ExternalMutantRecord:
    mutation_string: str
    effect_summary: str | None = None
    property_delta: dict = field(default_factory=dict)
    substrate: str | None = None
    organism: str | None = None
    source: str = "enzyme_data_mock"
    evidence: str | None = None


class EnzymeDataClient(Protocol):
    def fetch_opt_temperature(self, query: str, size: int = 5) -> list[ExternalPropertyDatum]:
        ...

    def fetch_opt_pH(self, query: str, size: int = 5) -> list[ExternalPropertyDatum]:
        ...

    def fetch_kinetic_parameters(self, query: str, size: int = 5) -> list[ExternalKineticParameter]:
        ...

    def fetch_mutants(self, query: str, size: int = 5) -> list[ExternalMutantRecord]:
        ...


class MockEnzymeDataClient:
    source = "enzyme_data_mock"

    def fetch_opt_temperature(self, query: str, size: int = 5) -> list[ExternalPropertyDatum]:
        return [self._profile_for(query)["optimal_temperature"]][:size]

    def fetch_opt_pH(self, query: str, size: int = 5) -> list[ExternalPropertyDatum]:
        return [self._profile_for(query)["optimal_pH"]][:size]

    def fetch_kinetic_parameters(self, query: str, size: int = 5) -> list[ExternalKineticParameter]:
        return [self._profile_for(query)["kinetic"]][:size]

    def fetch_mutants(self, query: str, size: int = 5) -> list[ExternalMutantRecord]:
        return [self._profile_for(query)["mutant"]][:size]

    def _profile_for(self, query: str) -> dict:
        lowered = query.lower()
        if "anthraquinone" in lowered or "glycosyltransferase" in lowered:
            return AQGT_PROFILE
        return MTGASE_PROFILE


def get_enzyme_data_client() -> EnzymeDataClient:
    return MockEnzymeDataClient()


MTGASE_PROFILE = {
    "optimal_temperature": ExternalPropertyDatum(
        property_type="optimal_temperature",
        value_original="55",
        unit_original="degC",
        organism="Streptomyces mobaraensis",
        source="enzyme_data_mock",
        evidence="Mock BRENDA-style optimal temperature record",
    ),
    "optimal_pH": ExternalPropertyDatum(
        property_type="optimal_pH",
        value_original="7.0",
        organism="Streptomyces mobaraensis",
        source="enzyme_data_mock",
        evidence="Mock BRENDA-style optimal pH record",
    ),
    "kinetic": ExternalKineticParameter(
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
    ),
    "mutant": ExternalMutantRecord(
        mutation_string="S2P",
        effect_summary="Mock thermostability improvement",
        property_delta={"optimal_temperature_delta_degC": 5},
        organism="Streptomyces mobaraensis",
        source="enzyme_data_mock",
        evidence="Mock mutant data record",
    ),
}

AQGT_PROFILE = {
    "optimal_temperature": ExternalPropertyDatum(
        property_type="optimal_temperature",
        value_original="35",
        unit_original="degC",
        organism="Streptomyces mockensis",
        source="enzyme_data_mock",
        evidence="Mock BRENDA-style AQGT optimal temperature record",
    ),
    "optimal_pH": ExternalPropertyDatum(
        property_type="optimal_pH",
        value_original="7.5",
        organism="Streptomyces mockensis",
        source="enzyme_data_mock",
        evidence="Mock BRENDA-style AQGT optimal pH record",
    ),
    "kinetic": ExternalKineticParameter(
        substrate="anthraquinone substrate 1",
        km="0.8",
        kcat="12.0",
        kcat_km=None,
        unit_original="mM; s^-1",
        assay_temperature="30",
        assay_pH="7.5",
        organism="Streptomyces mockensis",
        source="enzyme_data_mock",
        evidence="Mock SABIO-RK-style AQGT kinetic parameter record",
    ),
    "mutant": ExternalMutantRecord(
        mutation_string="W141F",
        effect_summary="Mock substrate selectivity shift",
        property_delta={"specific_activity_fold_change": 1.8},
        substrate="anthraquinone substrate 1",
        organism="Streptomyces mockensis",
        source="enzyme_data_mock",
        evidence="Mock AQGT mutant data record",
    ),
}
