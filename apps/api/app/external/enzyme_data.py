from dataclasses import dataclass, field
import csv
from io import StringIO
import re
from typing import Protocol
from xml.etree import ElementTree

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
    reference_title: str | None = None
    journal: str | None = None
    year: int | None = None
    doi: str | None = None
    pubmed_id: str | None = None


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
    reference_title: str | None = None
    journal: str | None = None
    year: int | None = None
    doi: str | None = None
    pubmed_id: str | None = None


@dataclass(frozen=True)
class ExternalMutantRecord:
    mutation_string: str
    effect_summary: str | None = None
    property_delta: dict = field(default_factory=dict)
    substrate: str | None = None
    organism: str | None = None
    source: str = "enzyme_data_mock"
    evidence: str | None = None
    reference_title: str | None = None
    journal: str | None = None
    year: int | None = None
    doi: str | None = None
    pubmed_id: str | None = None


class EnzymeDataClient(Protocol):
    def fetch_opt_temperature(self, query: str, size: int = 5) -> list[ExternalPropertyDatum]:
        ...

    def fetch_opt_pH(self, query: str, size: int = 5) -> list[ExternalPropertyDatum]:
        ...

    def fetch_specific_activity(self, query: str, size: int = 5) -> list[ExternalPropertyDatum]:
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

    def fetch_specific_activity(self, query: str, size: int = 5) -> list[ExternalPropertyDatum]:
        return [self._profile_for(query)["specific_activity"]][:size]

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
    full_text_base_url = "https://www.ebi.ac.uk/europepmc/webservices/rest"
    pubmed_search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    pubmed_fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    openalex_works_url = "https://api.openalex.org/works"
    semantic_scholar_search_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    sabiork_entry_ids_url = "https://sabiork.h-its.org/sabioRestWebServices/searchKineticLaws/entryIDs"
    sabiork_tsv_url = "https://sabiork.h-its.org/sabioRestWebServices/kineticlawsExportTsv"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    def fetch_opt_temperature(self, query: str, size: int = 5) -> list[ExternalPropertyDatum]:
        records = []
        for item in self._search_variants(
            [
                f"{query} optimum temperature",
                f"{query} optimal temperature",
                f"{query} maximum activity temperature",
                f"{query} highest activity temperature",
            ],
            size=size,
        ):
            text = _article_text(item)
            value = _extract_temperature(text)
            if value is None:
                continue
            records.append(
                ExternalPropertyDatum(
                    property_type="optimal_temperature",
                    value_original=value,
                    unit_original="degC",
                    organism=_extract_evidence_organism(text, value),
                    source=_item_source(item),
                    evidence=_evidence_with_sentence(item, text, value),
                    **_reference_kwargs(item),
                )
            )
        return records[:size]

    def fetch_opt_pH(self, query: str, size: int = 5) -> list[ExternalPropertyDatum]:
        records = []
        for item in self._search_variants(
            [
                f"{query} optimum pH",
                f"{query} optimal pH",
                f"{query} maximum activity pH",
                f"{query} highest activity pH",
            ],
            size=size,
        ):
            text = _article_text(item)
            value = _extract_ph(text)
            if value is None:
                continue
            records.append(
                ExternalPropertyDatum(
                    property_type="optimal_pH",
                    value_original=value,
                    organism=_extract_evidence_organism(text, value),
                    source=_item_source(item),
                    evidence=_evidence_with_sentence(item, text, value),
                    **_reference_kwargs(item),
                )
            )
        return records[:size]

    def fetch_specific_activity(self, query: str, size: int = 5) -> list[ExternalPropertyDatum]:
        records = []
        for item in self._search_variants(
            [
                f"{query} specific activity",
                f"{query} enzyme activity",
                f"{query} activity U/mg",
            ],
            size=size,
        ):
            text = _article_text(item)
            value = _extract_specific_activity(text)
            if value is None:
                continue
            records.append(
                ExternalPropertyDatum(
                    property_type="specific_activity",
                    value_original=value,
                    unit_original="U/mg",
                    substrate=_extract_activity_substrate(text, value),
                    organism=_extract_evidence_organism(text, value),
                    source=_item_source(item),
                    evidence=_evidence_with_sentence(item, text, value),
                    **_reference_kwargs(item),
                )
            )
        return records[:size]

    def fetch_kinetic_parameters(self, query: str, size: int = 5) -> list[ExternalKineticParameter]:
        records = self._fetch_sabiork_kinetic_parameters(query, size=size)
        seen = {_kinetic_identity(record) for record in records}
        for item in self._search_variants(
            [
                f"{query} Km kcat",
                f"{query} kinetic parameters",
                f"{query} catalytic efficiency",
            ],
            size=size,
        ):
            text = _article_text(item)
            km = _extract_labeled_number(text, "km")
            kcat = _extract_labeled_number(text, "kcat")
            kcat_km = _extract_kcat_km(text)
            if km is None and kcat is None and kcat_km is None:
                continue
            record = ExternalKineticParameter(
                substrate=_extract_kinetic_substrate(text, km or kcat or kcat_km),
                km=km,
                kcat=kcat,
                kcat_km=kcat_km,
                unit_original=_kinetic_unit_label(km=km, kcat=kcat, kcat_km=kcat_km),
                assay_temperature=_extract_kinetic_assay_temperature(text, km or kcat or kcat_km),
                assay_pH=_extract_kinetic_assay_ph(text, km or kcat or kcat_km),
                organism=_extract_evidence_organism(text, km or kcat or kcat_km),
                source=_item_source(item),
                evidence=_evidence_with_sentence(item, text, km or kcat or kcat_km),
                **_reference_kwargs(item),
            )
            identity = _kinetic_identity(record)
            if identity in seen:
                continue
            seen.add(identity)
            records.append(record)
            if len(records) >= size:
                break
        return records[:size]

    def _fetch_sabiork_kinetic_parameters(self, query: str, size: int = 5) -> list[ExternalKineticParameter]:
        sabiork_query = _sabiork_query_for(query)
        if sabiork_query is None:
            return []
        try:
            entry_response = httpx.get(
                self.sabiork_entry_ids_url,
                params={"format": "txt", "q": sabiork_query},
                timeout=self.timeout,
            )
            entry_response.raise_for_status()
            entry_ids = _parse_sabiork_entry_ids(entry_response.text)[:size]
            if not entry_ids:
                return []
            tsv_response = httpx.get(
                self.sabiork_tsv_url,
                params={
                    "kinlawids": ",".join(entry_ids),
                    "fields[]": [
                        "EntryID",
                        "Organism",
                        "UniprotID",
                        "ECNumber",
                        "Parameter",
                        "ParameterValue",
                        "ParameterUnit",
                        "Substrate",
                        "Temperature",
                        "pH",
                        "PubMedID",
                        "Title",
                        "Year",
                    ],
                },
                timeout=self.timeout,
            )
            tsv_response.raise_for_status()
        except Exception:
            return []
        return _parse_sabiork_kinetic_tsv(tsv_response.text)[:size]

    def fetch_mutants(self, query: str, size: int = 5) -> list[ExternalMutantRecord]:
        records = []
        for item in self._search(f"{query} mutant variant mutation", size=size):
            text = _article_text(item)
            for mutation in _extract_mutation_strings(text):
                records.append(
                    ExternalMutantRecord(
                        mutation_string=mutation,
                        effect_summary=f"Real literature mention: {_sentence_containing(text, mutation)}",
                        organism=_extract_evidence_organism(text, mutation),
                        source=_item_source(item),
                        evidence=_evidence_with_sentence(item, text, mutation),
                        **_reference_kwargs(item),
                    )
                )
                if len(records) >= size:
                    return records
        return records

    def _search(self, query: str, size: int = 5) -> list[dict]:
        records = []
        seen: set[tuple] = set()
        for record in [
            *self._search_europe_pmc(query, size=size),
            *self._search_pubmed(query, size=size),
            *self._search_openalex(query, size=size),
            *self._search_semantic_scholar(query, size=size),
        ]:
            identity = _literature_candidate_identity(record)
            if identity in seen:
                continue
            seen.add(identity)
            records.append(record)
        return records

    def _search_variants(self, queries: list[str], size: int = 5) -> list[dict]:
        records = []
        seen: set[tuple] = set()
        for query in queries:
            for record in self._search(query, size=size):
                identity = _literature_candidate_identity(record)
                if identity in seen:
                    continue
                seen.add(identity)
                records.append(record)
        return records

    def _search_europe_pmc(self, query: str, size: int = 5) -> list[dict]:
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
        records = ((response.json().get("resultList") or {}).get("result") or [])[:size]
        return [self._with_europe_pmc_full_text({**record, "_source": "europepmc"}) for record in records]

    def _with_europe_pmc_full_text(self, record: dict) -> dict:
        pmcid = _europe_pmc_pmcid(record)
        if pmcid is None:
            return record
        try:
            response = httpx.get(
                f"{self.full_text_base_url}/{pmcid}/fullTextXML",
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception:
            return record
        full_text = _xml_document_text(response.text)
        return {**record, "fullText": full_text} if full_text else record

    def _search_pubmed(self, query: str, size: int = 5) -> list[dict]:
        if size <= 0:
            return []
        try:
            search_response = httpx.get(
                self.pubmed_search_url,
                params={
                    "db": "pubmed",
                    "term": query,
                    "retmode": "json",
                    "retmax": size,
                },
                timeout=self.timeout,
            )
            search_response.raise_for_status()
            pubmed_ids = ((search_response.json().get("esearchresult") or {}).get("idlist") or [])[:size]
            if not pubmed_ids:
                return []
            fetch_response = httpx.get(
                self.pubmed_fetch_url,
                params={
                    "db": "pubmed",
                    "id": ",".join(pubmed_ids),
                    "retmode": "xml",
                },
                timeout=self.timeout,
            )
            fetch_response.raise_for_status()
        except Exception:
            return []
        return _parse_pubmed_articles(fetch_response.text)[:size]

    def _search_openalex(self, query: str, size: int = 5) -> list[dict]:
        if size <= 0:
            return []
        try:
            response = httpx.get(
                self.openalex_works_url,
                params={
                    "search": query,
                    "per-page": size,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception:
            return []
        return [_openalex_work_to_record(work) for work in (response.json().get("results") or [])[:size]]

    def _search_semantic_scholar(self, query: str, size: int = 5) -> list[dict]:
        if size <= 0:
            return []
        try:
            response = httpx.get(
                self.semantic_scholar_search_url,
                params={
                    "query": query,
                    "limit": size,
                    "fields": "title,abstract,venue,year,externalIds",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception:
            return []
        return [_semantic_scholar_paper_to_record(paper) for paper in (response.json().get("data") or [])[:size]]


def get_enzyme_data_client() -> EnzymeDataClient:
    if get_settings().use_real_science_providers:
        return RealEnzymeDataClient()
    return MockEnzymeDataClient()


def _article_text(item: dict) -> str:
    return ". ".join(
        str(item.get(field) or "").strip(" .")
        for field in ["title", "abstractText", "fullText"]
        if item.get(field)
    )


def _item_source(item: dict) -> str:
    return str(item.get("_source") or "europepmc")


def _evidence_label(item: dict) -> str:
    parts = [
        item.get("journalTitle"),
        item.get("pubYear"),
        f"doi:{item.get('doi')}" if item.get("doi") else None,
        f"pmid:{item.get('pmid')}" if item.get("pmid") else None,
    ]
    source = _item_source(item)
    return " ".join(str(part) for part in parts if part) or f"{source} literature metadata"


def _evidence_with_sentence(item: dict, text: str, needle: str | None) -> str:
    label = _evidence_label(item)
    if not needle:
        return label
    sentence = _sentence_containing(text, needle)
    if not sentence:
        return label
    return f"{label} | Evidence quality: literature sentence | Evidence: {sentence}"


def _reference_kwargs(item: dict) -> dict:
    return {
        "reference_title": item.get("title"),
        "journal": item.get("journalTitle"),
        "year": _parse_year(item.get("pubYear")),
        "doi": item.get("doi"),
        "pubmed_id": item.get("pmid"),
    }


def _openalex_work_to_record(work: dict) -> dict:
    return {
        "_source": "openalex",
        "title": work.get("display_name"),
        "abstractText": _openalex_abstract_text(work.get("abstract_inverted_index")),
        "journalTitle": _openalex_source_name(work),
        "pubYear": work.get("publication_year"),
        "doi": _normalize_doi(work.get("doi")),
    }


def _semantic_scholar_paper_to_record(paper: dict) -> dict:
    external_ids = paper.get("externalIds")
    doi = external_ids.get("DOI") if isinstance(external_ids, dict) else None
    return {
        "_source": "semanticscholar",
        "title": paper.get("title"),
        "abstractText": paper.get("abstract"),
        "journalTitle": paper.get("venue"),
        "pubYear": paper.get("year"),
        "doi": _normalize_doi(doi),
    }


def _openalex_source_name(work: dict) -> str | None:
    primary_location = work.get("primary_location")
    if not isinstance(primary_location, dict):
        return None
    source = primary_location.get("source")
    if not isinstance(source, dict):
        return None
    return source.get("display_name")


def _openalex_abstract_text(abstract_inverted_index) -> str | None:
    if not isinstance(abstract_inverted_index, dict):
        return None
    tokens: list[tuple[int, str]] = []
    for word, positions in abstract_inverted_index.items():
        if not isinstance(word, str) or not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int):
                tokens.append((position, word))
    if not tokens:
        return None
    return " ".join(word for _, word in sorted(tokens))


def _normalize_doi(value) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return re.sub(r"^https?://(?:dx\.)?doi\.org/", "", normalized, flags=re.IGNORECASE)


def _literature_candidate_identity(item: dict) -> tuple:
    return (
        (item.get("doi") or "").lower(),
        item.get("pmid") or "",
        (item.get("title") or "").lower(),
    )


def _parse_year(value) -> int | None:
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return None


def _parse_pubmed_articles(xml_text: str) -> list[dict]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    records = []
    for article in root.findall(".//PubmedArticle"):
        pubmed_id = _xml_text(article, ".//MedlineCitation/PMID")
        article_title = _xml_text(article, ".//Article/ArticleTitle")
        abstract_text = " ".join(
            text.strip()
            for text in (_element_text(element) for element in article.findall(".//Article/Abstract/AbstractText"))
            if text
        )
        journal = _xml_text(article, ".//Article/Journal/Title")
        year = _xml_text(article, ".//Article/Journal/JournalIssue/PubDate/Year")
        doi = None
        for article_id in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
            if article_id.attrib.get("IdType") == "doi":
                doi = _element_text(article_id)
                break
        records.append(
            {
                "_source": "pubmed",
                "title": article_title,
                "abstractText": abstract_text,
                "journalTitle": journal,
                "pubYear": year,
                "doi": doi,
                "pmid": pubmed_id,
            }
        )
    return records


def _europe_pmc_pmcid(record: dict) -> str | None:
    candidate = record.get("pmcid")
    if isinstance(candidate, str) and candidate.strip():
        return _normalize_pmcid(candidate)
    full_text_ids = record.get("fullTextIdList")
    if isinstance(full_text_ids, dict):
        values = full_text_ids.get("fullTextId") or []
        for value in values:
            if isinstance(value, str) and value.upper().startswith("PMC"):
                return _normalize_pmcid(value)
    return None


def _normalize_pmcid(value: str) -> str:
    normalized = value.strip().replace(" ", "")
    return normalized if normalized.upper().startswith("PMC") else f"PMC{normalized}"


def _xml_document_text(xml_text: str) -> str | None:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return None
    text = " ".join(part.strip() for part in root.itertext() if part and part.strip())
    return text[:200_000] or None


def _xml_text(root: ElementTree.Element, path: str) -> str | None:
    element = root.find(path)
    return _element_text(element)


def _element_text(element: ElementTree.Element | None) -> str | None:
    if element is None:
        return None
    text = " ".join(part.strip() for part in element.itertext() if part and part.strip())
    return text or None


def _sabiork_query_for(query: str) -> str | None:
    accession = _extract_uniprot_accession(query)
    if accession:
        return f'UniProtKB_AC:"{accession}"'
    ec_number = _extract_ec_number(query)
    if ec_number:
        return f'ECNumber:"{ec_number}"'
    return None


def _extract_uniprot_accession(text: str) -> str | None:
    match = re.search(r"\b(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9])\b", text)
    return match.group(0) if match else None


def _extract_ec_number(text: str) -> str | None:
    match = re.search(r"\b\d+\.\d+\.\d+\.\d+\b", text)
    return match.group(0) if match else None


def _parse_sabiork_entry_ids(text: str) -> list[str]:
    seen: set[str] = set()
    entry_ids = []
    for match in re.finditer(r"\b\d+\b", text):
        entry_id = match.group(0)
        if entry_id in seen:
            continue
        seen.add(entry_id)
        entry_ids.append(entry_id)
    return entry_ids


def _parse_sabiork_kinetic_tsv(text: str) -> list[ExternalKineticParameter]:
    reader = csv.DictReader(StringIO(text), delimiter="\t")
    grouped: dict[tuple[str, str | None], dict] = {}
    for row in reader:
        entry_id = _row_value(row, "EntryID", "entryid")
        parameter = _row_value(row, "Parameter", "Parametertype", "parameter type")
        value = _row_value(row, "ParameterValue", "Value", "parameter value")
        if not entry_id or not parameter or not value:
            continue
        substrate = _row_value(row, "Substrate", "AssociatedSpecies", "substrate")
        key = (entry_id, substrate)
        group = grouped.setdefault(
            key,
            {
                "entry_id": entry_id,
                "substrate": substrate,
                "organism": _row_value(row, "Organism", "organism"),
                "assay_temperature": _row_value(row, "Temperature", "temperature"),
                "assay_pH": _row_value(row, "pH", "PH", "ph"),
                "reference_title": _row_value(row, "Title", "title"),
                "year": _parse_year(_row_value(row, "Year", "year")),
                "pubmed_id": _row_value(row, "PubMedID", "PubmedID", "PMID", "pubmed id"),
                "units": {},
                "km": None,
                "kcat": None,
                "kcat_km": None,
            },
        )
        parameter_key = _normalize_sabiork_parameter(parameter)
        if parameter_key is None:
            continue
        group[parameter_key] = value
        unit = _row_value(row, "ParameterUnit", "Unit", "parameter unit")
        if unit:
            group["units"][parameter_key] = unit

    records = []
    for group in grouped.values():
        if group["km"] is None and group["kcat"] is None and group["kcat_km"] is None:
            continue
        records.append(
            ExternalKineticParameter(
                substrate=group["substrate"],
                km=group["km"],
                kcat=group["kcat"],
                kcat_km=group["kcat_km"],
                unit_original=_sabiork_unit_label(group["units"]),
                assay_temperature=group["assay_temperature"],
                assay_pH=group["assay_pH"],
                organism=group["organism"],
                source="sabiork",
                evidence=_sabiork_evidence_label(group["entry_id"], group["pubmed_id"]),
                reference_title=group["reference_title"],
                year=group["year"],
                pubmed_id=group["pubmed_id"],
            )
        )
    return records


def _kinetic_identity(record: ExternalKineticParameter) -> tuple:
    return (
        (record.organism or "").lower(),
        (record.substrate or "").lower(),
        record.km,
        record.kcat,
        record.kcat_km,
        record.doi,
        record.pubmed_id,
    )


def _row_value(row: dict[str, str], *candidates: str) -> str | None:
    normalized = {_normalize_header(key): value for key, value in row.items()}
    for candidate in candidates:
        value = normalized.get(_normalize_header(candidate))
        if value and value.strip():
            return value.strip()
    return None


def _normalize_header(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _normalize_sabiork_parameter(parameter: str) -> str | None:
    normalized = re.sub(r"[^a-z0-9]+", "", parameter.lower())
    if normalized in {"km", "kms"}:
        return "km"
    if normalized == "kcat":
        return "kcat"
    if normalized in {"kcatkm", "kcatoverkm"}:
        return "kcat_km"
    return None


def _sabiork_unit_label(units: dict[str, str]) -> str | None:
    labels = []
    for key, label in [("km", "Km"), ("kcat", "kcat"), ("kcat_km", "kcat/Km")]:
        unit = units.get(key)
        if unit:
            labels.append(f"{label}:{unit}")
    return "; ".join(labels) or None


def _sabiork_evidence_label(entry_id: str, pubmed_id: str | None) -> str:
    parts = [f"SABIO-RK EntryID {entry_id}"]
    if pubmed_id:
        parts.append(f"pmid:{pubmed_id}")
    return f"{' '.join(parts)} | Evidence quality: structured kinetic database"


def _extract_temperature(text: str) -> str | None:
    unit = r"(?:\u00b0\s*C|\u2103|degrees?\s*C|deg\s*C|degC|C)"
    range_separator = r"(?:-|\u2013|\u2014|to)"
    range_value = _first_range_match(
        text,
        [
            rf"(?:optimum|optimal)\s+temperature(?:\s+(?:range|was|is))?\s*(?:was|is)?\s*between\s+(\d+(?:\.\d+)?)\s+and\s+(\d+(?:\.\d+)?)\s*{unit}",
            rf"temperature\s+(?:optimum|optimal|optima)(?:\s+(?:range|was|were))?\s*(?:was|were|is)?\s*between\s+(\d+(?:\.\d+)?)\s+and\s+(\d+(?:\.\d+)?)\s*{unit}",
            rf"(?:optimum|optimal)\s+temperature(?:\s+(?:range|at|of|was|is))?\s*(?:was|is|at|of)?\s*(\d+(?:\.\d+)?)\s*{range_separator}\s*(\d+(?:\.\d+)?)\s*{unit}",
            rf"temperature\s+(?:optimum|optimal|optima)(?:\s+(?:range|at|of|was|were))?\s*(?:was|were|is|at|of)?\s*(\d+(?:\.\d+)?)\s*{range_separator}\s*(\d+(?:\.\d+)?)\s*{unit}",
        ],
    )
    if range_value:
        return range_value
    patterns = [
        rf"(?:optimum|optimal)\s+temperature(?:\s+(?:at|of|was))?\s*(?:is|was|at|of)?\s*(\d+(?:\.\d+)?)\s*{unit}",
        rf"temperature\s+(?:optimum|optimal|optima)(?:\s+(?:at|of|was|were))?\s*(?:is|was|were|at|of)?\s*(\d+(?:\.\d+)?)\s*{unit}",
        rf"pH\s+and\s+temperature\s+optima\s+(?:were|was)\s+\d+(?:\.\d+)?\s+and\s+(\d+(?:\.\d+)?)\s*{unit}",
        rf"temperature\s+and\s+pH\s+optima\s+(?:were|was)\s+(\d+(?:\.\d+)?)\s*{unit}\s+and\s+\d+(?:\.\d+)?",
        rf"(?:optimum|optimal)\s+temperature\s+and\s+pH\s+(?:were|was)\s+(\d+(?:\.\d+)?)\s*{unit}\s+and\s+\d+(?:\.\d+)?",
        rf"(?:maximum|highest|optimum|optimal) activity(?:\s+\w+){{0,6}}\s+(?:was\s+)?(?:observed\s+)?at\s+(\d+(?:\.\d+)?)\s*{unit}",
        rf"(?:maximum|highest|optimum|optimal) activity(?:\s+\w+){{0,6}}\s+(?:was\s+)?(?:observed\s+)?at\s+pH\s*\d+(?:\.\d+)?\s+and\s+(\d+(?:\.\d+)?)\s*{unit}",
    ]
    return _first_match(text, patterns)


def _extract_ph(text: str) -> str | None:
    unit = r"(?:\u00b0\s*C|\u2103|degrees?\s*C|deg\s*C|degC|C)"
    range_separator = r"(?:-|\u2013|\u2014|to)"
    range_value = _first_range_match(
        text,
        [
            r"(?:optimum|optimal)\s+pH(?:\s+(?:range|was|is))?\s*(?:was|is)?\s*between\s+(\d+(?:\.\d+)?)\s+and\s+(\d+(?:\.\d+)?)",
            r"pH\s+(?:optimum|optimal|optima)(?:\s+(?:range|was|were))?\s*(?:was|were|is)?\s*between\s+(\d+(?:\.\d+)?)\s+and\s+(\d+(?:\.\d+)?)",
            rf"(?:optimum|optimal)\s+pH(?:\s+(?:range|at|of|was|is))?\s*(?:was|is|at|of)?\s*(\d+(?:\.\d+)?)\s*{range_separator}\s*(\d+(?:\.\d+)?)",
            rf"pH\s+(?:optimum|optimal|optima)(?:\s+(?:range|at|of|was|were))?\s*(?:was|were|is|at|of)?\s*(\d+(?:\.\d+)?)\s*{range_separator}\s*(\d+(?:\.\d+)?)",
        ],
    )
    if range_value:
        return range_value
    patterns = [
        r"optimum pH(?:\s+(?:at|of|was))?\s*(?:is|was|at|of)?\s*(\d+(?:\.\d+)?)",
        r"optimal pH(?:\s+(?:at|of|was))?\s*(?:is|was|at|of)?\s*(\d+(?:\.\d+)?)",
        r"pH\s+and\s+temperature\s+optima\s+(?:were|was)\s+(\d+(?:\.\d+)?)\s+and\s+\d+(?:\.\d+)?",
        rf"temperature\s+and\s+pH\s+optima\s+(?:were|was)\s+\d+(?:\.\d+)?\s*{unit}\s+and\s+(\d+(?:\.\d+)?)",
        rf"(?:optimum|optimal)\s+temperature\s+and\s+pH\s+(?:were|was)\s+\d+(?:\.\d+)?\s*{unit}\s+and\s+(\d+(?:\.\d+)?)",
        r"(?:maximum|highest|optimum|optimal) activity(?:\s+\w+){0,6}\s+at\s+pH\s*(\d+(?:\.\d+)?)",
        rf"(?:maximum|highest|optimum|optimal) activity(?:\s+\w+){{0,6}}\s+(?:was\s+)?(?:observed\s+)?at\s+\d+(?:\.\d+)?\s*{unit}\s+and\s+pH\s*(\d+(?:\.\d+)?)",
    ]
    return _first_match(text, patterns)


def _extract_specific_activity(text: str) -> str | None:
    unit = r"(?:U\s*/\s*mg|units?\s*/\s*mg|U\s*mg\s*[-\u2212]?1(?:\s+protein)?)"
    patterns = [
        rf"specific\s+activity(?:\s+(?:was|is|of|reached|as))?\s*(?:was|is|=|of)?\s*(\d+(?:\.\d+)?)\s*{unit}",
        rf"\b(\d+(?:\.\d+)?)\s*{unit}\s+specific\s+activity\b",
        rf"enzyme\s+activity\s+(?:was|is|=)\s*(\d+(?:\.\d+)?)\s*{unit}",
        rf"activity\s+of\s+(\d+(?:\.\d+)?)\s*{unit}",
    ]
    return _first_match(text, patterns)


def _extract_activity_substrate(text: str, value: str | None) -> str | None:
    if value is None:
        return None
    sentence = _sentence_containing(text, value)
    match = re.search(r"\btoward\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60})", sentence, flags=re.IGNORECASE)
    return _clean_substrate_name(match.group(1)) if match else None


ORGANISM_FALSE_POSITIVE_PREFIXES = {
    "Applied",
    "Food",
    "For",
    "Full",
    "Journal",
    "Maximum",
    "Mutation",
    "Real",
    "The",
}


def _extract_organism(text: str) -> str | None:
    organisms = _extract_organisms(text)
    return organisms[0] if len(organisms) == 1 else None


def _extract_organisms(text: str) -> list[str]:
    organisms = []
    for match in re.finditer(r"\b([A-Z][a-z]+)\s+([a-z][a-z-]{2,})\b", text):
        genus, species = match.groups()
        if len(genus) <= 2:
            continue
        if genus in ORGANISM_FALSE_POSITIVE_PREFIXES:
            continue
        organism = f"{genus} {species}"
        if organism not in organisms:
            organisms.append(organism)
    return organisms


def _extract_abbreviated_organism(text: str, context: str) -> str | None:
    for match in re.finditer(r"\b([A-Z])\.\s*([a-z][a-z-]{2,})\b", text):
        initial, species = match.groups()
        genus = _genus_for_initial(context, initial)
        if genus:
            return f"{genus} {species}"
    return None


def _has_abbreviated_organism(text: str) -> bool:
    return bool(re.search(r"\b[A-Z]\.\s*[a-z][a-z-]{2,}\b", text))


def _genus_for_initial(text: str, initial: str) -> str | None:
    genera = []
    for match in re.finditer(r"\b([A-Z][a-z]+)\s+[a-z][a-z-]{2,}\b", text):
        genus = match.group(1)
        if genus in ORGANISM_FALSE_POSITIVE_PREFIXES:
            continue
        if genus.startswith(initial) and genus not in genera:
            genera.append(genus)
    return genera[0] if len(genera) == 1 else None


def _extract_evidence_organism(text: str, needle: str | None) -> str | None:
    if needle:
        sentence = _sentence_containing(text, needle)
        organism = _extract_organism(sentence) or _extract_abbreviated_organism(sentence, text)
        if organism:
            return organism
        if _has_abbreviated_organism(sentence):
            return None
    source_organism = _extract_enzyme_source_organism(text)
    if source_organism:
        return source_organism
    return _extract_organism(text)


def _extract_enzyme_source_organism(text: str) -> str | None:
    organisms = []
    patterns = [
        r"\b(?:enzyme|protein|gene|sequence|transglutaminase|amylase|lipase|protease|cellulase|xylanase)\b"
        r"[^.]{0,80}?\b(?:from|of|derived\s+from|originating\s+from|isolated\s+from)\s+"
        r"([A-Z][a-z]+)\s+([a-z][a-z-]{2,})",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            genus, species = match.groups()
            if genus in ORGANISM_FALSE_POSITIVE_PREFIXES:
                continue
            organism = f"{genus} {species}"
            if organism not in organisms:
                organisms.append(organism)
    return organisms[0] if len(organisms) == 1 else None


def _extract_labeled_number(text: str, label: str) -> str | None:
    patterns = [rf"\b{label}\b\s*(?:was|is|=|of)?\s*(\d+(?:\.\d+)?)"]
    if label.lower() == "km":
        patterns.append(
            r"\bKm\s+and\s+kcat\s+values?\s+for\s+[A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?\s+"
            r"(?:were|was)\s+(\d+(?:\.\d+)?)\s*(?:mM|uM|μM)?\s+and\s+\d+(?:\.\d+)?"
        )
        patterns.append(
            r"\bKm\s+and\s+kcat\s+(?:values?\s+)?(?:were|was)\s+"
            r"(\d+(?:\.\d+)?)\s*(?:mM|uM|渭M)?\s+and\s+\d+(?:\.\d+)?"
        )
        patterns.append(
            r"\bKm\s+for\s+[A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?\s+and\s+kcat\s+(?:were|was)\s+"
            r"(\d+(?:\.\d+)?)\s*(?:mM|uM|娓璏)?\s+and\s+\d+(?:\.\d+)?"
        )
        patterns.append(
            r"\bkcat\s+and\s+Km\s+values?\s+for\s+[A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?\s+"
            r"(?:were|was)\s+\d+(?:\.\d+)?\s*(?:s-?1|s\^-1)?\s+and\s+(\d+(?:\.\d+)?)"
        )
        patterns.append(
            r"\b(?:apparent\s+)?Km\b\s+for\s+[A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?\s+of\s+(\d+(?:\.\d+)?)"
        )
    if label.lower() == "kcat":
        patterns.append(
            r"\bKm\s+for\s+[A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?\s+and\s+kcat\s+(?:were|was)\s+"
            r"\d+(?:\.\d+)?\s*(?:mM|uM|娓璏)?\s+and\s+(\d+(?:\.\d+)?)"
        )
        patterns.append(
            r"\bkcat\s+and\s+Km\s+values?\s+for\s+[A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?\s+"
            r"(?:were|was)\s+(\d+(?:\.\d+)?)\s*(?:s-?1|s\^-1)?\s+and\s+\d+(?:\.\d+)?"
        )
        patterns.append(
            r"\bKm\s+and\s+kcat\s+(?:values?\s+)?(?:were|was)\s+"
            r"\d+(?:\.\d+)?\s*(?:mM|uM|渭M)?\s+and\s+(\d+(?:\.\d+)?)"
        )
        patterns.append(
            r"\bKm\s+and\s+kcat\s+values?\s+for\s+[A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?\s+"
            r"(?:were|was)\s+\d+(?:\.\d+)?\s*(?:mM|uM|μM)?\s+and\s+(\d+(?:\.\d+)?)"
        )
    return _first_match(text, patterns)


def _extract_kcat_km(text: str) -> str | None:
    return _first_match(
        text,
        [
            r"\bkcat\s*/\s*Km\b\)?\s*(?:was|is|=|of)?\s*(\d+(?:\.\d+)?)",
            r"\bkcat\s+Km\b\s*(?:was|is|=|of)?\s*(\d+(?:\.\d+)?)",
            r"\bcatalytic\s+efficiency\b\s*(?:\([^)]*kcat\s*/\s*Km[^)]*\))?\s*(?:was|is|=|of)?\s*(\d+(?:\.\d+)?)",
            r"\bcatalytic\s+efficiency\b[^.;]*?\b(?:was|is|=|of)\s*(\d+(?:\.\d+)?)",
        ],
    )


def _extract_kinetic_substrate(text: str, value: str | None) -> str | None:
    if value is None:
        return None
    sentence = _sentence_containing(text, value)
    patterns = [
        r"\bfor\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?),\s*(?:K|k)",
        r"\btoward\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?),\s*(?:K|k)",
        r"\bKm\s+and\s+kcat\s+values?\s+for\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?)\s+(?:were|was)\b",
        r"\bkcat\s+and\s+Km\s+values?\s+for\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?)\s+(?:were|was)\b",
        r"\bKm\s+for\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?)\s+and\s+kcat\s+(?:were|was)\b",
        r"\bKm\s+and\s+kcat\s+(?:values?\s+)?(?:were|was)\b.*?\bfor\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?)(?:[.;,]|$)",
        rf"\bcatalytic\s+efficiency\b\s+toward\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{{0,60}}?)\s+(?:was|is|=|of)\s+{re.escape(value)}\b",
        rf"\b(?:apparent\s+)?Km\b\s+for\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{{0,60}}?)\s+of\s+{re.escape(value)}\s*(?:mM|uM)?",
        rf"\b(?:kcat\s*/\s*Km|catalytic\s+efficiency)\b[^.;]*?\b{re.escape(value)}\b[^.;]*?\bfor\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{{0,60}}?)(?:[.;,]|$)",
        rf"\b(?:K|k)m\b\s+(?:was|is|=|of)?\s*{re.escape(value)}\s*(?:mM|uM|µM)?\s+for\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{{0,60}}?)(?:\s+and\b|[.;,]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, sentence, flags=re.IGNORECASE)
        if match:
            return _clean_substrate_name(match.group(1))
    return None


def _extract_kinetic_assay_temperature(text: str, value: str | None) -> str | None:
    if value is None:
        return None
    sentence = _sentence_containing(text, value)
    unit = r"(?:\u00b0\s*C|\u2103|degrees?\s*C|deg\s*C|degC|C)"
    return _first_match(sentence, [rf"\bat\s+(\d+(?:\.\d+)?)\s*{unit}"])


def _extract_kinetic_assay_ph(text: str, value: str | None) -> str | None:
    if value is None:
        return None
    sentence = _sentence_containing(text, value)
    return _first_match(sentence, [r"\bpH\s*(\d+(?:\.\d+)?)"])


def _clean_substrate_name(value: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", value).strip(" .;:,")
    return cleaned or None


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
    matches = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text) if needle in sentence]
    scored_matches = sorted(
        ((sentence, _measurement_sentence_score(sentence)) for sentence in matches),
        key=lambda item: item[1],
        reverse=True,
    )
    for sentence, score in scored_matches:
        if score > 0:
            return sentence
    for sentence in matches:
        return sentence
    return text[:160].strip()


def _measurement_sentence_score(sentence: str) -> int:
    score = 0
    if re.search(r"\b(?:optimum|optimal|specific\s+activity|Km|kcat|kcat\s*/\s*Km|mutant|mutation)\b", sentence, flags=re.IGNORECASE):
        score += 2
    if re.search(r"\b(?:activity|enzyme|temperature|pH)\b", sentence, flags=re.IGNORECASE):
        score += 1
    return score


def _kinetic_unit_label(*, km: str | None, kcat: str | None, kcat_km: str | None) -> str | None:
    units = []
    if km is not None:
        units.append("mM")
    if kcat is not None:
        units.append("s^-1")
    if kcat_km is not None:
        units.append("mM^-1 s^-1")
    return "; ".join(units) or None


def _first_match(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _first_range_match(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
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
    "specific_activity": ExternalPropertyDatum(
        property_type="specific_activity",
        value_original="120",
        unit_original="U/mg",
        organism="Streptomyces mobaraensis",
        source="enzyme_data_mock",
        evidence="Mock BRENDA-style specific activity record",
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
    "specific_activity": ExternalPropertyDatum(
        property_type="specific_activity",
        value_original="18",
        unit_original="U/mg",
        organism="Streptomyces mockensis",
        source="enzyme_data_mock",
        evidence="Mock BRENDA-style AQGT specific activity record",
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
