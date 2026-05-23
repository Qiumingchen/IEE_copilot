from dataclasses import dataclass, field
import re
from typing import Protocol

import httpx

from app.core.config import get_settings


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


class RealEnzymeDataClient:
    source = "europepmc"
    base_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    def fetch_opt_temperature(self, query: str, size: int = 5) -> list[ExternalPropertyDatum]:
        records = []
        for item in self._search(f"{query} optimum temperature", size=size):
            value = _extract_temperature(_article_text(item))
            if value is None:
                continue
            records.append(
                ExternalPropertyDatum(
                    property_type="optimal_temperature",
                    value_original=value,
                    unit_original="degC",
                    source=self.source,
                    evidence=_evidence_label(item),
                )
            )
        return records[:size]

    def fetch_opt_pH(self, query: str, size: int = 5) -> list[ExternalPropertyDatum]:
        records = []
        for item in self._search(f"{query} optimum pH", size=size):
            value = _extract_ph(_article_text(item))
            if value is None:
                continue
            records.append(
                ExternalPropertyDatum(
                    property_type="optimal_pH",
                    value_original=value,
                    source=self.source,
                    evidence=_evidence_label(item),
                )
            )
        return records[:size]

    def fetch_kinetic_parameters(self, query: str, size: int = 5) -> list[ExternalKineticParameter]:
        records = []
        for item in self._search(f"{query} Km kcat", size=size):
            text = _article_text(item)
            km = _extract_labeled_number(text, "km")
            kcat = _extract_labeled_number(text, "kcat")
            kcat_km = _extract_kcat_km(text)
            if km is None and kcat is None and kcat_km is None:
                continue
            records.append(
                ExternalKineticParameter(
                    km=km,
                    kcat=kcat,
                    kcat_km=kcat_km,
                    unit_original=_kinetic_unit_label(km=km, kcat=kcat, kcat_km=kcat_km),
                    source=self.source,
                    evidence=_evidence_label(item),
                )
            )
        return records[:size]

    def fetch_mutants(self, query: str, size: int = 5) -> list[ExternalMutantRecord]:
        records = []
        for item in self._search(f"{query} mutant variant mutation", size=size):
            text = _article_text(item)
            for mutation in _extract_mutation_strings(text):
                records.append(
                    ExternalMutantRecord(
                        mutation_string=mutation,
                        effect_summary=f"Real literature mention: {_sentence_containing(text, mutation)}",
                        source=self.source,
                        evidence=_evidence_label(item),
                    )
                )
                if len(records) >= size:
                    return records
        return records

    def _search(self, query: str, size: int = 5) -> list[dict]:
        try:
            response = httpx.get(
                self.base_url,
                params={
                    "query": query,
                    "format": "json",
                    "pageSize": size,
                    "resultType": "core",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception:
            return []
        return ((response.json().get("resultList") or {}).get("result") or [])[:size]


def get_enzyme_data_client() -> EnzymeDataClient:
    if get_settings().use_real_science_providers:
        return RealEnzymeDataClient()
    return MockEnzymeDataClient()


def _article_text(item: dict) -> str:
    return ". ".join(str(item.get(field) or "").strip(" .") for field in ["title", "abstractText"] if item.get(field))


def _evidence_label(item: dict) -> str:
    parts = [
        item.get("journalTitle"),
        item.get("pubYear"),
        f"doi:{item.get('doi')}" if item.get("doi") else None,
        f"pmid:{item.get('pmid')}" if item.get("pmid") else None,
    ]
    return " ".join(str(part) for part in parts if part) or "Europe PMC literature metadata"


def _extract_temperature(text: str) -> str | None:
    patterns = [
        r"optimum temperature(?:\s+(?:at|of|was))?\s*(?:is|was|at|of)?\s*(\d+(?:\.\d+)?)\s*(?:°\s*C|degrees?\s*C|degC|C)",
        r"optimal temperature(?:\s+(?:at|of|was))?\s*(?:is|was|at|of)?\s*(\d+(?:\.\d+)?)\s*(?:°\s*C|degrees?\s*C|degC|C)",
    ]
    return _first_match(text, patterns)


def _extract_ph(text: str) -> str | None:
    patterns = [
        r"optimum pH(?:\s+(?:at|of|was))?\s*(?:is|was|at|of)?\s*(\d+(?:\.\d+)?)",
        r"optimal pH(?:\s+(?:at|of|was))?\s*(?:is|was|at|of)?\s*(\d+(?:\.\d+)?)",
    ]
    return _first_match(text, patterns)


def _extract_labeled_number(text: str, label: str) -> str | None:
    return _first_match(text, [rf"\b{label}\b\s*(?:was|is|=|of)?\s*(\d+(?:\.\d+)?)"])


def _extract_kcat_km(text: str) -> str | None:
    return _first_match(
        text,
        [
            r"\bkcat\s*/\s*Km\b\s*(?:was|is|=|of)?\s*(\d+(?:\.\d+)?)",
            r"\bkcat\s+Km\b\s*(?:was|is|=|of)?\s*(\d+(?:\.\d+)?)",
        ],
    )


def _extract_mutation_strings(text: str) -> list[str]:
    seen: set[str] = set()
    mutations = []
    for match in re.finditer(r"\b[A-Z][0-9]{1,5}[A-Z]\b", text):
        mutation = match.group(0)
        if mutation in seen:
            continue
        seen.add(mutation)
        mutations.append(mutation)
    return mutations


def _sentence_containing(text: str, needle: str) -> str:
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if needle in sentence:
            return sentence.strip()
    return text[:160].strip()


def _kinetic_unit_label(*, km: str | None, kcat: str | None, kcat_km: str | None) -> str | None:
    units = []
    if km is not None:
        units.append("mM")
    if kcat is not None:
        units.append("s^-1")
    if kcat_km is not None:
        units.append("s^-1 mM^-1")
    return "; ".join(units) or None


def _first_match(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


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
