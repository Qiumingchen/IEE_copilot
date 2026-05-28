from dataclasses import dataclass, field
import csv
from io import StringIO
import re
from typing import Callable, Protocol
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
    method: str | None = None
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
    method: str | None = None
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
    assay_temperature: str | None = None
    assay_pH: str | None = None
    method: str | None = None
    organism: str | None = None
    source: str = "enzyme_data_mock"
    evidence: str | None = None
    reference_title: str | None = None
    journal: str | None = None
    year: int | None = None
    doi: str | None = None
    pubmed_id: str | None = None


@dataclass(frozen=True)
class ExternalLiteratureDatum:
    organism: str | None = None
    source: str = "external_enzyme_data"
    evidence: str | None = None
    reference_title: str | None = None
    journal: str | None = None
    year: int | None = None
    doi: str | None = None
    pubmed_id: str | None = None


@dataclass(frozen=True)
class ExternalEnzymeDataBatch:
    property_data: list[ExternalPropertyDatum] = field(default_factory=list)
    kinetic_parameters: list[ExternalKineticParameter] = field(default_factory=list)
    mutant_records: list[ExternalMutantRecord] = field(default_factory=list)
    literature_references: list[ExternalLiteratureDatum] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


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
        self._europe_pmc_full_text_cache: dict[str, str | None] = {}
        self._literature_search_cache: dict[tuple[str, str, int], list[dict]] = {}
        self._sabiork_kinetic_cache: dict[tuple[str, int], list[ExternalKineticParameter]] = {}

    def fetch_opt_temperature(self, query: str, size: int = 5) -> list[ExternalPropertyDatum]:
        records = []
        for item in self._search_variants(
            [
                f"{query} optimum temperature",
                f"{query} optimal temperature",
                f"{query} optimum activity temperature",
                f"{query} optimal activity temperature",
                f"{query} maximum activity temperature",
                f"{query} highest activity temperature",
            ],
            size=size,
        ):
            text = self._article_text_for_extraction(item, _extract_temperature)
            value = _extract_temperature(text)
            if value is None:
                continue
            records.append(
                ExternalPropertyDatum(
                    property_type="optimal_temperature",
                    value_original=value,
                    unit_original="degC",
                    assay_pH=_extract_assay_ph(text, value),
                    method=_extract_assay_method(text, value),
                    organism=_extract_evidence_organism(text, value),
                    source=_item_source(item),
                    evidence=_evidence_with_sentence(item, text, value),
                    **_reference_kwargs(item),
                )
            )
            if len(records) >= size:
                return records
        return records

    def fetch_opt_pH(self, query: str, size: int = 5) -> list[ExternalPropertyDatum]:
        records = []
        for item in self._search_variants(
            [
                f"{query} optimum pH",
                f"{query} optimal pH",
                f"{query} optimum activity pH",
                f"{query} optimal activity pH",
                f"{query} maximum activity pH",
                f"{query} highest activity pH",
            ],
            size=size,
        ):
            text = self._article_text_for_extraction(item, _extract_ph)
            value = _extract_ph(text)
            if value is None:
                continue
            records.append(
                ExternalPropertyDatum(
                    property_type="optimal_pH",
                    value_original=value,
                    assay_temperature=_extract_assay_temperature(text, value),
                    method=_extract_assay_method(text, value),
                    organism=_extract_evidence_organism(text, value),
                    source=_item_source(item),
                    evidence=_evidence_with_sentence(item, text, value),
                    **_reference_kwargs(item),
                )
            )
            if len(records) >= size:
                return records
        return records

    def fetch_specific_activity(self, query: str, size: int = 5) -> list[ExternalPropertyDatum]:
        records = []
        for item in self._search_variants(
            [
                f"{query} specific activity",
                f"{query} enzyme activity",
                f"{query} activity U/mg",
                f"{query} activity U mg-1",
                f"{query} activity units/mg",
                f"{query} activity IU/mg",
                f"{query} activity IU mg-1",
                f"{query} activity U/mL",
            ],
            size=size,
        ):
            text = _article_text(item)
            value = _extract_specific_activity(text)
            property_type = "specific_activity"
            unit_original = "U/mg"
            if value is None:
                value = _extract_volumetric_activity(text)
                property_type = "activity"
                unit_original = "U/mL"
            if value is None and _item_source(item) == "europepmc":
                text = _article_text(self._with_europe_pmc_full_text(item))
                value = _extract_specific_activity(text)
                property_type = "specific_activity"
                unit_original = "U/mg"
                if value is None:
                    value = _extract_volumetric_activity(text)
                    property_type = "activity"
                    unit_original = "U/mL"
            if value is None:
                continue
            records.append(
                ExternalPropertyDatum(
                    property_type=property_type,
                    value_original=value,
                    unit_original=unit_original,
                    substrate=_extract_activity_substrate(text, value),
                    assay_temperature=_extract_assay_temperature(text, value),
                    assay_pH=_extract_assay_ph(text, value),
                    method=_extract_assay_method(text, value),
                    organism=_extract_evidence_organism(text, value),
                    source=_item_source(item),
                    evidence=_evidence_with_sentence(item, text, value),
                    **_reference_kwargs(item),
                )
            )
            if len(records) >= size:
                return records
        return records

    def fetch_kinetic_parameters(self, query: str, size: int = 5) -> list[ExternalKineticParameter]:
        records = self._fetch_sabiork_kinetic_parameters(query, size=size)
        if len(records) >= size:
            return records[:size]
        seen = {_kinetic_identity(record) for record in records}
        for item in self._search_variants(
            [
                f"{query} Km kcat",
                f"{query} kinetic parameters",
                f"{query} Michaelis constant",
                f"{query} Michaelis-Menten constant",
                f"{query} catalytic efficiency",
                f"{query} kcat/Km",
                f"{query} turnover number",
                f"{query} catalytic constant",
                f"{query} specificity constant",
            ],
            size=size,
        ):
            text = self._article_text_for_extraction(item, _extract_kinetic_value)
            km = _extract_labeled_number(text, "km")
            kcat = _extract_labeled_number(text, "kcat")
            kcat_km = _extract_kcat_km(text)
            if km == kcat_km:
                km = None
            if km is None and kcat is None and kcat_km is None:
                continue
            record = ExternalKineticParameter(
                substrate=_extract_kinetic_substrate(text, km or kcat or kcat_km),
                km=km,
                kcat=kcat,
                kcat_km=kcat_km,
                unit_original=_kinetic_unit_label(
                    km=km,
                    km_unit=_extract_km_unit(text, km),
                    kcat=kcat,
                    kcat_km=kcat_km,
                    kcat_km_unit=_extract_kcat_km_unit(text, kcat_km),
                ),
                assay_temperature=_extract_kinetic_assay_temperature(text, km or kcat or kcat_km),
                assay_pH=_extract_kinetic_assay_ph(text, km or kcat or kcat_km),
                method=_extract_assay_method(text, km or kcat or kcat_km),
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
                return records
        return records

    def _fetch_sabiork_kinetic_parameters(self, query: str, size: int = 5) -> list[ExternalKineticParameter]:
        sabiork_query = _sabiork_query_for(query)
        if sabiork_query is None:
            return []
        cache_key = (sabiork_query, size)
        if cache_key in self._sabiork_kinetic_cache:
            return self._sabiork_kinetic_cache[cache_key]
        try:
            entry_response = httpx.get(
                self.sabiork_entry_ids_url,
                params={"format": "txt", "q": sabiork_query},
                timeout=self.timeout,
            )
            entry_response.raise_for_status()
            entry_ids = _parse_sabiork_entry_ids(entry_response.text)[:size]
            if not entry_ids:
                self._sabiork_kinetic_cache[cache_key] = []
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
            self._sabiork_kinetic_cache[cache_key] = []
            return []
        records = _parse_sabiork_kinetic_tsv(tsv_response.text)[:size]
        self._sabiork_kinetic_cache[cache_key] = records
        return records

    def fetch_mutants(self, query: str, size: int = 5) -> list[ExternalMutantRecord]:
        records = []
        for item in self._search_variants(
            [
                f"{query} mutant variant mutation",
                f"{query} site-directed mutagenesis",
                f"{query} engineered variant",
            ],
            size=size,
        ):
            text = self._article_text_for_extraction(item, _extract_first_mutation_string)
            for mutation in _extract_mutation_strings(text):
                sentence = _sentence_containing(text, mutation)
                records.append(
                    ExternalMutantRecord(
                        mutation_string=mutation,
                        effect_summary=f"Real literature mention: {sentence}",
                        property_delta=_extract_mutant_property_delta(sentence),
                        substrate=_extract_activity_substrate(sentence, _extract_fold_change(sentence)),
                        assay_temperature=_extract_assay_temperature(text, mutation),
                        assay_pH=_extract_assay_ph(text, mutation),
                        method=_extract_assay_method(text, mutation),
                        organism=_extract_evidence_organism(text, mutation),
                        source=_item_source(item),
                        evidence=_evidence_with_sentence(item, text, mutation),
                        **_reference_kwargs(item),
                    )
                )
                if len(records) >= size:
                    return records
        return records

    def fetch_enzyme_records(
        self,
        query: str,
        size: int = 5,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> ExternalEnzymeDataBatch:
        candidate_limit = _literature_candidate_limit(size)
        candidates = list(self._search_relevant_literature(query, size=size))
        candidate_states = _initial_candidate_paper_states(candidates, query)
        sources = _unique_strings(_item_source(item) for item in candidates)
        _emit_progress(
            progress_callback,
            {
                "stage": "candidate literature search",
                "candidate_articles": len(candidates),
                "candidate_papers": _candidate_paper_summaries(candidates, candidate_states),
                "articles_scanned": 0,
                "filtered_articles": 0,
                "relevant_articles": 0,
                "found_records": 0,
            },
        )

        property_data: list[ExternalPropertyDatum] = []
        kinetic_parameters: list[ExternalKineticParameter] = self._fetch_sabiork_kinetic_parameters(query, size=size)
        mutant_records: list[ExternalMutantRecord] = []
        literature_references: list[ExternalLiteratureDatum] = []
        seen_properties: set[tuple] = set()
        seen_kinetics = {_kinetic_identity(record) for record in kinetic_parameters}
        seen_mutants: set[tuple] = set()
        seen_literature: set[tuple] = set()
        articles_scanned = 0
        filtered_articles = 0

        for item in candidates:
            articles_scanned += 1
            if not _is_relevant_enzyme_article(item, query):
                filtered_articles += 1
                _update_candidate_paper_state(
                    candidate_states,
                    item,
                    decision="filtered",
                    reason="failed enzyme/source relevance filter",
                    extracted_fields=[],
                )
                _emit_progress(
                    progress_callback,
                    {
                        "stage": "filtering candidate literature",
                        "candidate_articles": len(candidates),
                        "candidate_papers": _candidate_paper_summaries(candidates, candidate_states),
                        "articles_scanned": articles_scanned,
                        "filtered_articles": filtered_articles,
                        "relevant_articles": articles_scanned - filtered_articles,
                        "found_records": len(property_data) + len(kinetic_parameters) + len(mutant_records),
                    },
                )
                continue

            text = self._article_text_for_batch_extraction(item)
            literature_datum = _literature_datum_from_article(item, text)
            literature_identity = (literature_datum.doi, literature_datum.pubmed_id, literature_datum.reference_title)
            if any(literature_identity) and literature_identity not in seen_literature:
                seen_literature.add(literature_identity)
                literature_references.append(literature_datum)

            item_property_data = _extract_property_data_from_article(item, text)
            item_kinetics = _extract_kinetic_parameters_from_article(item, text)
            item_mutants = _extract_mutant_records_from_article(item, text)
            extracted_fields = _extracted_field_names(item_property_data, item_kinetics, item_mutants)

            for datum in item_property_data:
                identity = (
                    datum.property_type,
                    datum.value_original,
                    datum.unit_original,
                    datum.substrate,
                    datum.doi,
                    datum.pubmed_id,
                )
                if identity in seen_properties:
                    continue
                seen_properties.add(identity)
                property_data.append(datum)

            for kinetic in item_kinetics:
                kinetic_identity = _kinetic_identity(kinetic)
                if kinetic_identity not in seen_kinetics:
                    seen_kinetics.add(kinetic_identity)
                    kinetic_parameters.append(kinetic)

            for mutant in item_mutants:
                mutant_identity = (mutant.mutation_string, mutant.substrate, mutant.doi, mutant.pubmed_id)
                if mutant_identity in seen_mutants:
                    continue
                seen_mutants.add(mutant_identity)
                mutant_records.append(mutant)

            _update_candidate_paper_state(
                candidate_states,
                item,
                decision="extracted" if extracted_fields else "linked_reference",
                reason=(
                    "passed relevance filter and produced extractable records"
                    if extracted_fields
                    else "passed relevance filter but no target values were extracted"
                ),
                extracted_fields=extracted_fields,
            )

            _emit_progress(
                progress_callback,
                {
                    "stage": "extracting candidate literature",
                    "candidate_articles": len(candidates),
                    "candidate_papers": _candidate_paper_summaries(candidates, candidate_states),
                    "articles_scanned": articles_scanned,
                    "filtered_articles": filtered_articles,
                    "relevant_articles": articles_scanned - filtered_articles,
                    "found_records": len(property_data) + len(kinetic_parameters) + len(mutant_records),
                },
            )

            if (
                len(property_data) >= size
                and len(kinetic_parameters) >= size
                and len(mutant_records) >= size
                and len(literature_references) >= candidate_limit
            ):
                break

        return ExternalEnzymeDataBatch(
            property_data=property_data[:size],
            kinetic_parameters=kinetic_parameters[:size],
            mutant_records=mutant_records[:size],
            literature_references=literature_references[:candidate_limit],
            sources=sources,
        )

    def _article_text_for_extraction(self, item: dict, extractor) -> str:
        text = _article_text(item)
        if extractor(text) is not None or _item_source(item) != "europepmc":
            return text
        return _article_text(self._with_europe_pmc_full_text(item))

    def _article_text_for_batch_extraction(self, item: dict) -> str:
        text = _article_text(item)
        if _article_has_extractable_enzyme_data(text) or _item_source(item) != "europepmc":
            return text
        return _article_text(self._with_europe_pmc_full_text(item))

    def _search_relevant_literature(self, query: str, size: int = 5):
        seen: set[tuple] = set()
        yielded = 0
        candidate_limit = _literature_candidate_limit(size)
        discovery_queries = _literature_discovery_queries(query)
        per_query_limit = max(size, candidate_limit // 3)
        for discovery_query in discovery_queries:
            query_yielded = 0
            scored_records = sorted(
                (
                    (_literature_relevance_score(record, query), record)
                    for record in self._search(discovery_query, size=candidate_limit)
                ),
                key=lambda item: item[0],
                reverse=True,
            )
            for score, record in scored_records:
                if score <= 0:
                    continue
                identity = _literature_candidate_identity(record)
                if identity in seen:
                    continue
                seen.add(identity)
                yield record
                yielded += 1
                query_yielded += 1
                if yielded >= candidate_limit:
                    return
                if query_yielded >= per_query_limit:
                    break

    def _search(self, query: str, size: int = 5):
        if size <= 0:
            return
        seen: set[tuple] = set()
        for provider_name, search_provider in (
            ("europepmc", self._search_europe_pmc),
            ("pubmed", self._search_pubmed),
            ("openalex", self._search_openalex),
            ("semanticscholar", self._search_semantic_scholar),
        ):
            cache_key = (provider_name, query, size)
            if cache_key not in self._literature_search_cache:
                self._literature_search_cache[cache_key] = search_provider(query, size=size)
            for record in self._literature_search_cache[cache_key]:
                if _is_secondary_literature_record(record):
                    continue
                identity = _literature_candidate_identity(record)
                if identity in seen:
                    continue
                seen.add(identity)
                yield record

    def _search_variants(self, queries: list[str], size: int = 5):
        seen: set[tuple] = set()
        for query in queries:
            for record in self._search(query, size=size):
                identity = _literature_candidate_identity(record)
                if identity in seen:
                    continue
                seen.add(identity)
                yield record

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
        return [{**record, "_source": "europepmc"} for record in records]

    def _with_europe_pmc_full_text(self, record: dict) -> dict:
        pmcid = _europe_pmc_pmcid(record)
        if pmcid is None:
            return record
        if pmcid in self._europe_pmc_full_text_cache:
            full_text = self._europe_pmc_full_text_cache[pmcid]
            return {**record, "fullText": full_text} if full_text else record
        try:
            response = httpx.get(
                f"{self.full_text_base_url}/{pmcid}/fullTextXML",
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception:
            self._europe_pmc_full_text_cache[pmcid] = None
            return record
        full_text = _xml_document_text(response.text)
        self._europe_pmc_full_text_cache[pmcid] = full_text
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


def _extract_property_data_from_article(item: dict, text: str) -> list[ExternalPropertyDatum]:
    records: list[ExternalPropertyDatum] = []
    records.extend(_extract_comparative_property_data_from_article(item, text))
    reaction_scope = _extract_substrate_reaction_scope(text)
    if reaction_scope is not None:
        records.append(
            ExternalPropertyDatum(
                property_type="substrate_reaction_scope",
                value_original=reaction_scope,
                organism=_extract_evidence_organism(text, reaction_scope),
                source=_item_source(item),
                evidence=_evidence_with_sentence(item, text, reaction_scope),
                **_reference_kwargs(item),
            )
        )
    temperature = _extract_temperature(text)
    if temperature is not None and not any(record.property_type == "optimal_temperature" for record in records):
        records.append(
            ExternalPropertyDatum(
                property_type="optimal_temperature",
                value_original=temperature,
                unit_original="degC",
                assay_pH=_extract_assay_ph(text, temperature),
                organism=_extract_evidence_organism(text, temperature),
                source=_item_source(item),
                evidence=_evidence_with_sentence(item, text, temperature),
                method=_extract_assay_method(text, temperature),
                **_reference_kwargs(item),
            )
        )
    ph_value = _extract_ph(text)
    if ph_value is not None:
        records.append(
            ExternalPropertyDatum(
                property_type="optimal_pH",
                value_original=ph_value,
                assay_temperature=_extract_assay_temperature(text, ph_value),
                organism=_extract_evidence_organism(text, ph_value),
                source=_item_source(item),
                evidence=_evidence_with_sentence(item, text, ph_value),
                method=_extract_assay_method(text, ph_value),
                **_reference_kwargs(item),
            )
        )
    activity = _extract_specific_activity(text)
    property_type = "specific_activity"
    unit_original = "U/mg"
    if activity is None:
        activity = _extract_volumetric_activity(text)
        property_type = "activity"
        unit_original = "U/mL"
    if activity is not None and not any(record.property_type == property_type for record in records):
        records.append(
            ExternalPropertyDatum(
                property_type=property_type,
                value_original=activity,
                unit_original=unit_original,
                substrate=_extract_activity_substrate(text, activity),
                assay_temperature=_extract_assay_temperature(text, activity),
                assay_pH=_extract_assay_ph(text, activity),
                organism=_extract_evidence_organism(text, activity),
                source=_item_source(item),
                evidence=_evidence_with_sentence(item, text, activity),
                method=_extract_assay_method(text, activity),
                **_reference_kwargs(item),
            )
        )
    return records


def _extract_substrate_reaction_scope(text: str) -> str | None:
    normalized_text = _normalize_greek_letters(text)
    match = re.search(
        r"\b((?:epimerizes?|isomerizes?|hydroly[sz]es?|glycosylates?|transglycosylates?)"
        r"(?:\s+and\s+(?:epimerizes?|isomerizes?|hydroly[sz]es?|glycosylates?|transglycosylates?))*"
        r"\s+[A-Za-z0-9alpha-beta,\- ]{3,120}?(?:oligosaccharides?|saccharides?|substrates?|glycosides?))\b",
        normalized_text,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    return _clean_substrate_name(match.group(1))


def _normalize_greek_letters(text: str) -> str:
    return (
        text.replace("\u03b1", "alpha")
        .replace("\u0391", "alpha")
        .replace("\u03b2", "beta")
        .replace("\u0392", "beta")
    )


def _extract_comparative_property_data_from_article(item: dict, text: str) -> list[ExternalPropertyDatum]:
    records: list[ExternalPropertyDatum] = []
    organism = r"([A-Z][a-z]+)\s+([a-z][a-z-]{2,})"
    prefix = rf"\b{organism}\s+and\s+{organism}\s+enzymes?\s+showed\s+"
    temperature_unit = r"(?:\u00b0\s*C|\u2103|degrees?\s*C|deg\s*C|degC|C)"
    activity_unit = (
        r"(?:(?:U|IU)\s*/\s*mg|units?\s*/\s*mg|"
        r"(?:U|IU|units?)\s+per\s+mg(?:\s+protein)?|"
        r"(?:U|IU)\s*mg\s*[-\u2212]?1(?:\s+protein)?)"
    )
    comparative_patterns = [
        (
            "optimal_temperature",
            "degC",
            None,
            prefix
            + rf"(?:an?\s+)?(?:optimum|optimal)\s+temperature\s+at\s+"
            rf"(\d+(?:\.\d+)?)\s*{temperature_unit}\s+and\s+(\d+(?:\.\d+)?)\s*{temperature_unit},?\s+respectively",
        ),
        (
            "optimal_pH",
            None,
            None,
            prefix
            + r"(?:an?\s+)?(?:optimum|optimal)\s+pH\s+at\s+"
            r"(\d+(?:\.\d+)?)\s+and\s+(\d+(?:\.\d+)?),?\s+respectively",
        ),
        (
            "specific_activity",
            "U/mg",
            "starch",
            prefix
            + rf"specific\s+activities\s+of\s+(\d+(?:\.\d+)?)\s*{activity_unit}\s+and\s+"
            rf"(\d+(?:\.\d+)?)\s*{activity_unit}\s+toward\s+starch,?\s+respectively",
        ),
    ]
    for property_type, unit_original, substrate, pattern in comparative_patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            records.extend(
                _comparative_property_records_from_match(
                    item,
                    text,
                    match,
                    property_type=property_type,
                    unit_original=unit_original,
                    substrate=substrate,
                )
            )
    contrast_temperature_pattern = (
        rf"\b(?:the\s+)?{organism}\s+enzymes?\s+had\s+an?\s+(?:optimum|optimal)\s+temperature\s+of\s+"
        rf"(\d+(?:\.\d+)?)\s*{temperature_unit},?\s+(?:whereas|while)\s+(?:the\s+)?"
        rf"{organism}\s+enzymes?\s+had\s+an?\s+(?:optimum|optimal)\s+temperature\s+of\s+"
        rf"(\d+(?:\.\d+)?)\s*{temperature_unit}"
    )
    for match in re.finditer(contrast_temperature_pattern, text, flags=re.IGNORECASE):
        records.extend(
            _contrast_property_records_from_match(
                item,
                text,
                match,
                property_type="optimal_temperature",
                unit_original="degC",
                substrate=None,
            )
        )
    contrast_ph_pattern = (
        rf"\b(?:the\s+)?{organism}\s+enzymes?\s+had\s+an?\s+(?:optimum|optimal)\s+pH\s+of\s+"
        r"(\d+(?:\.\d+)?),?\s+(?:whereas|while)\s+(?:the\s+)?"
        rf"{organism}\s+enzymes?\s+had\s+an?\s+(?:optimum|optimal)\s+pH\s+of\s+"
        r"(\d+(?:\.\d+)?)"
    )
    for match in re.finditer(contrast_ph_pattern, text, flags=re.IGNORECASE):
        records.extend(
            _contrast_property_records_from_match(
                item,
                text,
                match,
                property_type="optimal_pH",
                unit_original=None,
                substrate=None,
            )
        )
    contrast_activity_pattern = (
        rf"\b(?:the\s+)?{organism}\s+enzymes?\s+had\s+a\s+specific\s+activity\s+of\s+"
        rf"(\d+(?:\.\d+)?)\s*{activity_unit}\s+toward\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{{0,60}}?),?\s+"
        rf"(?:whereas|while)\s+(?:the\s+)?{organism}\s+enzymes?\s+had\s+a\s+specific\s+activity\s+of\s+"
        rf"(\d+(?:\.\d+)?)\s*{activity_unit}\s+toward\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{{0,60}}?)(?:[.;,]|$)"
    )
    for match in re.finditer(contrast_activity_pattern, text, flags=re.IGNORECASE):
        first_organism = f"{match.group(1)} {match.group(2)}"
        second_organism = f"{match.group(5)} {match.group(6)}"
        records.extend(
            [
                ExternalPropertyDatum(
                    property_type="specific_activity",
                    value_original=match.group(3),
                    unit_original="U/mg",
                    substrate=_clean_substrate_name(match.group(4)),
                    organism=first_organism,
                    source=_item_source(item),
                    evidence=_evidence_with_sentence(item, text, match.group(3)),
                    method=_extract_assay_method(text, match.group(3)),
                    **_reference_kwargs(item),
                ),
                ExternalPropertyDatum(
                    property_type="specific_activity",
                    value_original=match.group(7),
                    unit_original="U/mg",
                    substrate=_clean_substrate_name(match.group(8)),
                    organism=second_organism,
                    source=_item_source(item),
                    evidence=_evidence_with_sentence(item, text, match.group(7)),
                    method=_extract_assay_method(text, match.group(7)),
                    **_reference_kwargs(item),
                ),
            ]
        )
    return records


def _comparative_property_records_from_match(
    item: dict,
    text: str,
    match: re.Match,
    *,
    property_type: str,
    unit_original: str | None,
    substrate: str | None,
) -> list[ExternalPropertyDatum]:
    sentence = _sentence_containing(text, match.group(5))
    records = []
    first_organism = f"{match.group(1)} {match.group(2)}"
    second_organism = f"{match.group(3)} {match.group(4)}"
    for organism_name, value in ((first_organism, match.group(5)), (second_organism, match.group(6))):
        records.append(
            ExternalPropertyDatum(
                property_type=property_type,
                value_original=value,
                unit_original=unit_original,
                substrate=substrate,
                organism=organism_name,
                source=_item_source(item),
                evidence=_evidence_with_sentence(item, text, value if value in sentence else match.group(5)),
                method=_extract_assay_method(text, value),
                **_reference_kwargs(item),
            )
        )
    return records


def _contrast_property_records_from_match(
    item: dict,
    text: str,
    match: re.Match,
    *,
    property_type: str,
    unit_original: str | None,
    substrate: str | None,
) -> list[ExternalPropertyDatum]:
    first_organism = f"{match.group(1)} {match.group(2)}"
    second_organism = f"{match.group(4)} {match.group(5)}"
    return [
        ExternalPropertyDatum(
            property_type=property_type,
            value_original=value,
            unit_original=unit_original,
            substrate=substrate,
            organism=organism_name,
            source=_item_source(item),
            evidence=_evidence_with_sentence(item, text, value),
            method=_extract_assay_method(text, value),
            **_reference_kwargs(item),
        )
        for organism_name, value in ((first_organism, match.group(3)), (second_organism, match.group(6)))
    ]


def _extract_kinetic_parameter_from_article(item: dict, text: str) -> ExternalKineticParameter | None:
    km = _extract_labeled_number(text, "km")
    kcat = _extract_labeled_number(text, "kcat")
    kcat_km = _extract_kcat_km(text)
    if km == kcat_km:
        km = None
    if km is None and kcat is None and kcat_km is None:
        return None
    value = km or kcat or kcat_km
    return ExternalKineticParameter(
        substrate=_extract_kinetic_substrate(text, value),
        km=km,
        kcat=kcat,
        kcat_km=kcat_km,
        unit_original=_kinetic_unit_label(
            km=km,
            km_unit=_extract_km_unit(text, km),
            kcat=kcat,
            kcat_km=kcat_km,
            kcat_km_unit=_extract_kcat_km_unit(text, kcat_km),
        ),
        assay_temperature=_extract_kinetic_assay_temperature(text, value),
        assay_pH=_extract_kinetic_assay_ph(text, value),
        method=_extract_assay_method(text, value),
        organism=_extract_evidence_organism(text, value),
        source=_item_source(item),
        evidence=_evidence_with_sentence(item, text, value),
        **_reference_kwargs(item),
    )


def _extract_kinetic_parameters_from_article(item: dict, text: str) -> list[ExternalKineticParameter]:
    comparative_records = _extract_comparative_kinetic_parameters_from_article(item, text)
    if comparative_records:
        return comparative_records
    kinetic = _extract_kinetic_parameter_from_article(item, text)
    return [kinetic] if kinetic is not None else []


def _extract_comparative_kinetic_parameters_from_article(item: dict, text: str) -> list[ExternalKineticParameter]:
    organism = r"([A-Z][a-z]+)\s+([a-z][a-z-]{2,})"
    pattern = (
        rf"\b{organism}\s+and\s+{organism}\s+enzymes?\s+showed\s+"
        r"Km\s+values\s+for\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?)\s+of\s+"
        r"(\d+(?:\.\d+)?)\s*(mM|uM|渭M)\s+and\s+(\d+(?:\.\d+)?)\s*(mM|uM|渭M),?\s+respectively,?\s+"
        r"and\s+kcat\s+values\s+of\s+(\d+(?:\.\d+)?)\s*(?:s-?1|s\^-1)\s+and\s+"
        r"(\d+(?:\.\d+)?)\s*(?:s-?1|s\^-1),?\s+respectively"
    )
    records: list[ExternalKineticParameter] = []
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        first_organism = f"{match.group(1)} {match.group(2)}"
        second_organism = f"{match.group(3)} {match.group(4)}"
        substrate = _clean_substrate_name(match.group(5))
        first_km = match.group(6)
        first_km_unit = _normalize_km_unit(match.group(7))
        second_km = match.group(8)
        second_km_unit = _normalize_km_unit(match.group(9))
        first_kcat = match.group(10)
        second_kcat = match.group(11)
        for organism_name, km, km_unit, kcat in (
            (first_organism, first_km, first_km_unit, first_kcat),
            (second_organism, second_km, second_km_unit, second_kcat),
        ):
            records.append(
                ExternalKineticParameter(
                    substrate=substrate,
                    km=km,
                    kcat=kcat,
                    kcat_km=None,
                    unit_original=f"{km_unit}; s^-1",
                    organism=organism_name,
                    source=_item_source(item),
                    evidence=_evidence_with_sentence(item, text, km),
                    method=_extract_assay_method(text, km),
                    **_reference_kwargs(item),
                )
            )
    kcat_km_pattern = (
        rf"\b{organism}\s+and\s+{organism}\s+enzymes?\s+showed\s+"
        r"kcat\s*/\s*Km\s+values\s+for\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?)\s+of\s+"
        r"(\d+(?:\.\d+)?)\s*(?:mM|M)\s*[-\^]?\s*1\s*s\s*[-\^]?\s*1\s+and\s+"
        r"(\d+(?:\.\d+)?)\s*(?:mM|M)\s*[-\^]?\s*1\s*s\s*[-\^]?\s*1,?\s+respectively"
    )
    for match in re.finditer(kcat_km_pattern, text, flags=re.IGNORECASE):
        first_organism = f"{match.group(1)} {match.group(2)}"
        second_organism = f"{match.group(3)} {match.group(4)}"
        substrate = _clean_substrate_name(match.group(5))
        first_kcat_km = match.group(6)
        second_kcat_km = match.group(7)
        for organism_name, kcat_km in (
            (first_organism, first_kcat_km),
            (second_organism, second_kcat_km),
        ):
            records.append(
                ExternalKineticParameter(
                    substrate=substrate,
                    km=None,
                    kcat=None,
                    kcat_km=kcat_km,
                    unit_original=_extract_kcat_km_unit(text, kcat_km),
                    organism=organism_name,
                    source=_item_source(item),
                    evidence=_evidence_with_sentence(item, text, kcat_km),
                    method=_extract_assay_method(text, kcat_km),
                    **_reference_kwargs(item),
                )
            )
    return records


def _extract_mutant_records_from_article(item: dict, text: str) -> list[ExternalMutantRecord]:
    records = []
    for mutation in _extract_mutation_strings(text):
        sentence = _sentence_containing(text, mutation)
        records.append(
            ExternalMutantRecord(
                mutation_string=mutation,
                effect_summary=f"Real literature mention: {sentence}",
                property_delta=_extract_mutant_property_delta(sentence),
                substrate=_extract_activity_substrate(sentence, _extract_fold_change(sentence)),
                assay_temperature=_extract_assay_temperature(text, mutation),
                assay_pH=_extract_assay_ph(text, mutation),
                method=_extract_assay_method(text, mutation),
                organism=_extract_evidence_organism(text, mutation),
                source=_item_source(item),
                evidence=_evidence_with_sentence(item, text, mutation),
                **_reference_kwargs(item),
            )
        )
    return records


def _literature_datum_from_article(item: dict, text: str) -> ExternalLiteratureDatum:
    return ExternalLiteratureDatum(
        organism=_extract_evidence_organism(text, None),
        source=_item_source(item),
        evidence=_evidence_label(item),
        **_reference_kwargs(item),
    )


def _literature_candidate_limit(size: int) -> int:
    return min(max(size * 6, 18), 30)


TARGET_EXTRACTION_FIELDS = [
    "optimal_temperature",
    "optimal_pH",
    "specific_activity",
    "kinetic_parameters",
    "mutants",
]


def _initial_candidate_paper_states(items: list[dict], query: str) -> dict[tuple, dict]:
    return {
        _literature_candidate_identity(item): {
            "relevance_score": _literature_relevance_score(item, query),
            "decision": "candidate",
            "reason": "found by high-recall literature search",
            "extracted_fields": [],
            "missing_fields": TARGET_EXTRACTION_FIELDS.copy(),
            "extraction_notes": [],
        }
        for item in items
    }


def _update_candidate_paper_state(
    states: dict[tuple, dict],
    item: dict,
    *,
    decision: str,
    reason: str,
    extracted_fields: list[str],
) -> None:
    key = _literature_candidate_identity(item)
    state = states.setdefault(
        key,
        {
            "relevance_score": 0,
            "decision": "candidate",
            "reason": "found by high-recall literature search",
            "extracted_fields": [],
            "missing_fields": TARGET_EXTRACTION_FIELDS.copy(),
            "extraction_notes": [],
        },
    )
    state["decision"] = decision
    state["reason"] = reason
    state["extracted_fields"] = extracted_fields
    missing_fields = _missing_field_names(extracted_fields)
    state["missing_fields"] = missing_fields
    state["extraction_notes"] = _candidate_extraction_notes(decision, missing_fields)


def _extracted_field_names(
    property_data: list[ExternalPropertyDatum],
    kinetic_parameters: list[ExternalKineticParameter],
    mutant_records: list[ExternalMutantRecord],
) -> list[str]:
    names: list[str] = []
    names.extend(record.property_type for record in property_data)
    if kinetic_parameters:
        names.append("kinetic_parameters")
    if mutant_records:
        names.append("mutants")
    return _unique_strings(names)


def _missing_field_names(extracted_fields: list[str]) -> list[str]:
    extracted = set(extracted_fields)
    return [field_name for field_name in TARGET_EXTRACTION_FIELDS if field_name not in extracted]


def _candidate_extraction_notes(decision: str, missing_fields: list[str]) -> list[str]:
    if decision == "filtered":
        return ["not scanned for extraction after relevance filter"]
    if not missing_fields:
        return []
    if decision == "linked_reference":
        return ["no target property/kinetic/mutant values extracted"]
    if decision == "extracted":
        return [f"missing {', '.join(missing_fields)}"]
    return []


def _candidate_paper_summaries(items: list[dict], states: dict[tuple, dict] | None = None) -> list[dict]:
    summaries = []
    for item in items:
        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        summary = {
            "title": title.strip(),
            "source": _item_source(item),
            "year": _parse_year(item.get("pubYear")),
            "doi": _normalize_doi(item.get("doi")),
            "pubmed_id": _normalize_pubmed_id(item.get("pmid")),
        }
        if states is not None:
            state = states.get(_literature_candidate_identity(item), {})
            summary.update(
                {
                    "relevance_score": state.get("relevance_score", 0),
                    "decision": state.get("decision", "candidate"),
                    "reason": state.get("reason", "found by high-recall literature search"),
                    "extracted_fields": list(state.get("extracted_fields") or []),
                    "missing_fields": list(state.get("missing_fields") or []),
                    "extraction_notes": list(state.get("extraction_notes") or []),
                }
            )
        summaries.append(summary)
    return summaries


def _article_has_extractable_enzyme_data(text: str) -> bool:
    return any(
        extractor(text) is not None
        for extractor in (
            _extract_temperature,
            _extract_ph,
            _extract_specific_activity,
            _extract_volumetric_activity,
            _extract_kinetic_value,
            _extract_first_mutation_string,
            _extract_substrate_reaction_scope,
        )
    )


def _is_relevant_enzyme_article(item: dict, query: str) -> bool:
    terms = _query_relevance_terms(query)
    if not terms:
        return True
    text = _article_text(item).lower()
    matches = sum(1 for term in terms if term in text)
    return matches >= min(2, len(terms))


def _literature_relevance_score(item: dict, query: str) -> int:
    text = _article_text(item).lower()
    title = str(item.get("title") or "").lower()
    cleaned = _clean_literature_query(query)
    without_accessions = _strip_accession_like_terms(cleaned)
    enzyme_name, organism = _split_enzyme_organism_query(without_accessions)
    score = 0

    if without_accessions and without_accessions.lower() in text:
        score += 8
    if enzyme_name and organism:
        enzyme_lower = enzyme_name.lower()
        organism_lower = organism.lower()
        if enzyme_lower in title:
            score += 5
        elif enzyme_lower in text:
            score += 3
        if organism_lower in title:
            score += 5
        elif organism_lower in text:
            score += 3
        if f"{enzyme_lower} from {organism_lower}" in text or f"{organism_lower} {enzyme_lower}" in text:
            score += 8
        abbreviated = _abbreviated_organism_pattern(organism)
        if abbreviated and re.search(abbreviated, text, flags=re.IGNORECASE):
            score += 3

    terms = _query_relevance_terms(query)
    score += sum(1 for term in terms if term in text)
    if _article_has_extractable_enzyme_data(text):
        score += 2
    if _is_secondary_literature_record(item):
        score -= 10
    return score


def _query_relevance_terms(query: str) -> list[str]:
    stopwords = {
        "activity",
        "characterization",
        "enzyme",
        "enzymes",
        "food",
        "kinetic",
        "kinetics",
        "protein",
        "proteins",
    }
    terms = []
    for token in re.findall(r"[a-z0-9]+", query.lower()):
        if len(token) < 3 or token in stopwords:
            continue
        terms.append(token)
    return _unique_strings(terms)


def _literature_discovery_queries(query: str) -> list[str]:
    cleaned = _clean_literature_query(query)
    without_accessions = _strip_accession_like_terms(cleaned)
    enzyme_name, organism = _split_enzyme_organism_query(without_accessions)
    strain = _extract_strain_suffix_after_organism(without_accessions, organism)
    organism_with_strain = f"{organism} {strain}" if organism and strain else None
    abbreviated_organism = _abbreviated_organism_name(organism)
    abbreviated_organism_with_strain = (
        f"{abbreviated_organism} {strain}" if abbreviated_organism and strain else None
    )
    enzyme_aliases = _enzyme_name_query_aliases(enzyme_name)
    is_specific_enzyme = bool(enzyme_name and _is_specific_enzyme_name(enzyme_name))
    queries = [
        cleaned,
        without_accessions,
        f"{enzyme_name} from {organism}" if enzyme_name and organism else None,
        f"{organism} {enzyme_name}" if enzyme_name and organism else None,
        f"{enzyme_name} from {organism_with_strain}" if enzyme_name and organism_with_strain else None,
        f"{organism_with_strain} {enzyme_name}" if enzyme_name and organism_with_strain else None,
        f"{without_accessions} characterization" if without_accessions else None,
        f"{without_accessions} biochemical characterization" if without_accessions else None,
        f"{without_accessions} purification expression" if without_accessions else None,
        *(f"{alias} from {organism}" for alias in enzyme_aliases if organism),
        f"recombinant {enzyme_name} from {organism}" if enzyme_name and organism and is_specific_enzyme else None,
        f"characterization of recombinant {enzyme_name} from {organism}" if enzyme_name and organism and is_specific_enzyme else None,
        f"characterization of a recombinant {enzyme_name} from {organism}" if enzyme_name and organism and is_specific_enzyme else None,
        f"purification of {enzyme_name} from {organism}" if enzyme_name and organism and is_specific_enzyme else None,
        f"crystallographic analysis of {enzyme_name} from {organism}" if enzyme_name and organism and is_specific_enzyme else None,
        f"{enzyme_name} from {abbreviated_organism}" if enzyme_name and abbreviated_organism else None,
        f"{abbreviated_organism} {enzyme_name}" if enzyme_name and abbreviated_organism else None,
        (
            f"{enzyme_name} from {abbreviated_organism_with_strain}"
            if enzyme_name and abbreviated_organism_with_strain
            else None
        ),
        (
            f"{abbreviated_organism_with_strain} {enzyme_name}"
            if enzyme_name and abbreviated_organism_with_strain
            else None
        ),
    ]
    return _unique_strings(query for query in queries if query)


def _clean_literature_query(query: str) -> str:
    return re.sub(r"\s+", " ", query).strip()


def _strip_accession_like_terms(query: str) -> str:
    tokens = query.split()
    kept = [token for token in tokens if not _looks_like_database_accession(token)]
    return " ".join(kept).strip()


def _split_enzyme_organism_query(query: str) -> tuple[str | None, str | None]:
    match = re.search(r"\b([A-Z][a-z]+)\s+([a-z][a-z-]+)\b", query)
    if match is None:
        return None, None
    organism = f"{match.group(1)} {match.group(2)}"
    trailing = query[match.end() :].strip()
    strain = _extract_strain_suffix(trailing)
    if strain:
        trailing = trailing[len(strain) :].strip()
    enzyme_name = " ".join((query[: match.start()] + " " + trailing).split())
    return enzyme_name or None, organism


def _extract_strain_suffix_after_organism(query: str, organism: str | None) -> str | None:
    if not organism:
        return None
    match = re.search(rf"\b{re.escape(organism)}\b(?P<trailing>.*)$", query)
    if not match:
        return None
    return _extract_strain_suffix(match.group("trailing").strip())


def _extract_strain_suffix(value: str) -> str | None:
    match = re.match(
        r"(?:(?:strain|str\.)\s+)?"
        r"((?:DSM|ATCC|KCTC|JCM|NBRC|IFO|CGMCC|CIP)\s*\d+[A-Za-z0-9-]*)\b",
        value,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip()


def _enzyme_name_query_aliases(enzyme_name: str | None) -> list[str]:
    if not enzyme_name:
        return []
    aliases = []
    without_numeric_prefixes = re.sub(r"\b\d+\s*-\s*", "", enzyme_name)
    if without_numeric_prefixes != enzyme_name:
        aliases.append(without_numeric_prefixes)
    return _unique_strings(aliases)


def _is_specific_enzyme_name(enzyme_name: str) -> bool:
    return bool(re.search(r"\b[A-Za-z0-9-]*ase\b", enzyme_name, flags=re.IGNORECASE))


def _abbreviated_organism_pattern(organism: str) -> str | None:
    parts = organism.split()
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None
    return rf"\b{re.escape(parts[0][0])}\.\s*{re.escape(parts[1])}\b"


def _abbreviated_organism_name(organism: str | None) -> str | None:
    if not organism:
        return None
    parts = organism.split()
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None
    return f"{parts[0][0]}. {parts[1]}"


def _looks_like_database_accession(token: str) -> bool:
    normalized = re.sub(r"[^A-Za-z0-9]", "", token)
    if len(normalized) < 5:
        return False
    if normalized != normalized.upper():
        return False
    return bool(re.fullmatch(r"(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9]{5,12}", normalized))


def _emit_progress(progress_callback: Callable[[dict], None] | None, payload: dict) -> None:
    if progress_callback is not None:
        progress_callback(payload)


def _unique_strings(values) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _extract_kinetic_value(text: str) -> str | None:
    km = _extract_labeled_number(text, "km")
    kcat = _extract_labeled_number(text, "kcat")
    kcat_km = _extract_kcat_km(text)
    if km == kcat_km:
        km = None
    return km or kcat or kcat_km


def _extract_first_mutation_string(text: str) -> str | None:
    return next(iter(_extract_mutation_strings(text)), None)


def _item_source(item: dict) -> str:
    return str(item.get("_source") or "europepmc")


def _evidence_label(item: dict) -> str:
    doi = _normalize_doi(item.get("doi"))
    pmid = _normalize_pubmed_id(item.get("pmid"))
    parts = [
        item.get("journalTitle"),
        item.get("pubYear"),
        f"doi:{doi}" if doi else None,
        f"pmid:{pmid}" if pmid else None,
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


def _extract_assay_method(text: str, needle: str | None) -> str | None:
    sentence = _sentence_containing(text, needle) if needle else text
    if not sentence:
        return None
    patterns = [
        r"\b(?:using|with)\s+(?:the\s+)?((?:HPLC|UPLC|LC-MS|GC)\b)",
        r"\b(?:using|with)\s+(?:the\s+)?([A-Za-z0-9][A-Za-z0-9+\- ]{1,70}?\b(?:assay|method|analysis|chromatography))\b",
        r"\b(?:determined|measured|assayed|analy[sz]ed)\s+(?:by|using|with)\s+(?:the\s+)?((?:HPLC|UPLC|LC-MS|GC)|[A-Za-z0-9][A-Za-z0-9+\- ]{0,70}?\b(?:assay|method|analysis|chromatography))\b",
        r"\bin\s+(?:a|an|the)\s+([A-Za-z0-9+\- ]{2,70}?\bassay)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, sentence, flags=re.IGNORECASE)
        if not match:
            continue
        method = re.sub(r"\s+", " ", match.group(1)).strip(" .;,")
        method = re.sub(r"\b(?:was|were|is|and|at|pH)\b.*$", "", method, flags=re.IGNORECASE).strip(" .;,")
        if method:
            return method
    return None


def _reference_kwargs(item: dict) -> dict:
    return {
        "reference_title": item.get("title"),
        "journal": item.get("journalTitle"),
        "year": _parse_year(item.get("pubYear")),
        "doi": _normalize_doi(item.get("doi")),
        "pubmed_id": _normalize_pubmed_id(item.get("pmid")),
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
    normalized = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"^doi:\s*", "", normalized, flags=re.IGNORECASE)
    normalized = normalized.rstrip(".,;")
    return normalized.lower()


def _normalize_pubmed_id(value) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"\d+", value)
    return match.group(0) if match else None


def _literature_candidate_identity(item: dict) -> tuple:
    return (
        (_normalize_doi(item.get("doi")) or "").lower(),
        _normalize_pubmed_id(item.get("pmid")) or "",
        (item.get("title") or "").lower(),
    )


def _is_secondary_literature_record(item: dict) -> bool:
    title = str(item.get("title") or "").lower()
    publication_type = str(item.get("pubType") or item.get("publicationType") or item.get("type") or "").lower()
    text = f"{title} {publication_type}"
    return bool(
        re.search(r"\b(?:review|systematic review|meta[- ]analysis|meta analysis)\b", text)
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
                "pubmed_id": _normalize_pubmed_id(_row_value(row, "PubMedID", "PubmedID", "PMID", "pubmed id")),
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
        rf"(?:optimum|optimal)\s+pH\s+and\s+temperature\s+(?:were|was)\s+\d+(?:\.\d+)?\s+and\s+(\d+(?:\.\d+)?)\s*{unit}",
        rf"temperature\s+and\s+pH\s+optima\s+(?:were|was)\s+(\d+(?:\.\d+)?)\s*{unit}\s+and\s+\d+(?:\.\d+)?",
        rf"(?:optimum|optimal)\s+temperature\s+and\s+pH\s+(?:were|was)\s+(\d+(?:\.\d+)?)\s*{unit}\s+and\s+\d+(?:\.\d+)?",
        rf"(?:maximum|highest|optimum|optimal) activity(?:\s+\w+){{0,6}}\s+(?:was\s+)?(?:observed\s+)?at\s+(\d+(?:\.\d+)?)\s*{unit}",
        rf"(?:maximum|highest|optimum|optimal) activity(?:\s+\w+){{0,6}}\s+(?:was\s+)?(?:observed\s+)?at\s+pH\s*\d+(?:\.\d+)?\s+and\s+(\d+(?:\.\d+)?)\s*{unit}",
        rf"(?:maximum|highest|optimum|optimal) activity(?:\s+\w+){{0,8}}\s+(?:at|under)\s+pH\s*\d+(?:\.\d+)?\s+and\s+temperature\s+(\d+(?:\.\d+)?)\s*{unit}",
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
        rf"(?:optimum|optimal)\s+pH\s+and\s+temperature\s+(?:were|was)\s+(\d+(?:\.\d+)?)\s+and\s+\d+(?:\.\d+)?\s*{unit}",
        rf"temperature\s+and\s+pH\s+optima\s+(?:were|was)\s+\d+(?:\.\d+)?\s*{unit}\s+and\s+(\d+(?:\.\d+)?)",
        rf"(?:optimum|optimal)\s+temperature\s+and\s+pH\s+(?:were|was)\s+\d+(?:\.\d+)?\s*{unit}\s+and\s+(\d+(?:\.\d+)?)",
        r"(?:maximum|highest|optimum|optimal) activity(?:\s+\w+){0,6}\s+at\s+pH\s*(\d+(?:\.\d+)?)",
        r"(?:maximum|highest|optimum|optimal) activity(?:\s+\w+){0,8}\s+(?:at|under)\s+pH\s*(\d+(?:\.\d+)?)\s+and\s+temperature\b",
        rf"(?:maximum|highest|optimum|optimal) activity(?:\s+\w+){{0,6}}\s+(?:was\s+)?(?:observed\s+)?at\s+\d+(?:\.\d+)?\s*{unit}\s+and\s+pH\s*(\d+(?:\.\d+)?)",
    ]
    return _first_match(text, patterns)


def _extract_specific_activity(text: str) -> str | None:
    unit = (
        r"(?:(?:U|IU)\s*/\s*mg|units?\s*/\s*mg|"
        r"(?:U|IU|units?)\s+per\s+mg(?:\s+protein)?|"
        r"(?:U|IU)\s*mg\s*[-\u2212]?1(?:\s+protein)?)"
    )
    patterns = [
        rf"specific\s+activity\s+toward\s+[A-Za-z0-9][A-Za-z0-9+\-()/ ]{{0,60}}?\s+(?:was|is|=)\s*(\d+(?:\.\d+)?)\s*{unit}",
        rf"specific\s+activity(?:\s+(?:was|is|of|reached|as))?\s*(?:was|is|=|of)?\s*(\d+(?:\.\d+)?)\s*{unit}",
        rf"\b(\d+(?:\.\d+)?)\s*{unit}\s+specific\s+activity\b",
        rf"enzyme\s+activity\s+(?:was|is|=)\s*(\d+(?:\.\d+)?)\s*{unit}",
        rf"activity\s+of\s+(\d+(?:\.\d+)?)\s*{unit}",
    ]
    return _first_match(text, patterns)


def _extract_volumetric_activity(text: str) -> str | None:
    unit = r"(?:U\s*/\s*mL|units?\s*/\s*mL|(?:U|units?)\s+per\s+mL|U\s*mL\s*[-\u2212]?1)"
    patterns = [
        rf"enzyme\s+activity\s+(?:was|is|=|of)?\s*(\d+(?:\.\d+)?)\s*{unit}",
        rf"activity\s+of\s+(\d+(?:\.\d+)?)\s*{unit}",
        rf"\b(\d+(?:\.\d+)?)\s*{unit}\s+enzyme\s+activity\b",
    ]
    return _first_match(text, patterns)


def _extract_activity_substrate(text: str, value: str | None) -> str | None:
    if value is None:
        return None
    sentence = _sentence_containing(text, value)
    match = re.search(
        r"\btoward\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?)(?:\s+(?:was|is|=)|[.;,]|$)",
        sentence,
        flags=re.IGNORECASE,
    )
    return _clean_substrate_name(match.group(1)) if match else None


ORGANISM_FALSE_POSITIVE_PREFIXES = {
    "Applied",
    "Food",
    "For",
    "Full",
    "Journal",
    "Kinetic",
    "Maximum",
    "Michaelis",
    "Menten",
    "Mutation",
    "Amylase",
    "Catalytic",
    "Cellulase",
    "Direct",
    "Lipase",
    "Protease",
    "Optimum",
    "Real",
    "The",
    "Transglutaminase",
    "Xylanase",
}


ORGANISM_FALSE_POSITIVE_SPECIES = {
    "activity",
    "analysis",
    "assay",
    "data",
    "kinetic",
    "method",
    "optimum",
    "parameters",
    "profile",
    "report",
    "temperature",
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
        if species in ORGANISM_FALSE_POSITIVE_SPECIES:
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
    source_organism = _extract_enzyme_source_organism(text)
    if needle:
        sentence = _sentence_containing(text, needle)
        organism = _extract_organism(sentence) or _extract_abbreviated_organism(sentence, text)
        if organism and source_organism and _is_expression_host_sentence(sentence):
            return source_organism
        if organism:
            return organism
        if _has_abbreviated_organism(sentence):
            return None
    if source_organism:
        return source_organism
    return _extract_organism(text)


def _is_expression_host_sentence(text: str) -> bool:
    return bool(re.search(r"\b(?:expressed|expression|recombinant|host)\b", text, flags=re.IGNORECASE))


def _extract_enzyme_source_organism(text: str) -> str | None:
    organisms = []
    patterns = [
        r"\b(?:enzyme|protein|gene|sequence|[A-Za-z0-9-]*ase)\b"
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
    patterns = [
        rf"\b{label}\b\s*(?:was|is|=|of)?\s*(\d+(?:\.\d+)?)",
        rf"\b{label}\s+value\b\s*(?:was|is|=|of)?\s*(\d+(?:\.\d+)?)",
        rf"(?<!and\s)\b{label}\s+values\b\s*(?:were|was|is|=|of)?\s*(\d+(?:\.\d+)?)",
    ]
    if label.lower() == "km":
        michaelis_label = r"Michaelis(?:-Menten)?\s+constant"
        patterns.append(rf"\b{michaelis_label}\b\s*(?:was|is|=|of)?\s*(\d+(?:\.\d+)?)")
        patterns.append(rf"\b{michaelis_label}\b[^.;]*?\b(?:was|is|=|of)\s*(\d+(?:\.\d+)?)")
        patterns.append(
            r"\bKm\s+value\s+for\s+[A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?\s+"
            r"(?:were|was|is|=)\s+(\d+(?:\.\d+)?)"
        )
        patterns.append(
            r"(?<!and\s)\bKm\s+values\s+for\s+[A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?\s+"
            r"(?:were|was|is|=)\s+(\d+(?:\.\d+)?)"
        )
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
            r"\bKm,\s*kcat,\s+and\s+kcat\s*/\s*Km\s+values?\s+(?:were|was)\s+"
            r"\d+(?:\.\d+)?\s*(?:mM|uM|渭M)?\s*,\s*(\d+(?:\.\d+)?)\s*(?:s-?1|s\^-1)"
        )
        patterns.append(r"\bturnover\s+number\b\s*(?:was|is|=|of)?\s*(\d+(?:\.\d+)?)")
        patterns.append(r"\bcatalytic\s+constant\b\s*(?:was|is|=|of)?\s*(\d+(?:\.\d+)?)")
        patterns.append(r"\bcatalytic\s+constant\b[^.;]*?\b(?:was|is|=|of)\s*(\d+(?:\.\d+)?)")
        patterns.append(
            r"\bkcat\s+value\s+for\s+[A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?\s+"
            r"(?:were|was|is|=)\s+(\d+(?:\.\d+)?)"
        )
        patterns.append(
            r"(?<!and\s)\bkcat\s+values\s+for\s+[A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?\s+"
            r"(?:were|was|is|=)\s+(\d+(?:\.\d+)?)"
        )
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
            r"\bKm,\s*kcat,\s+and\s+kcat\s*/\s*Km\s+values?\s+(?:were|was)\s+"
            r"\d+(?:\.\d+)?\s*(?:mM|uM|渭M)?\s*,\s*\d+(?:\.\d+)?\s*(?:s-?1|s\^-1)\s*,\s*"
            r"(?:and\s+)?(\d+(?:\.\d+)?)\s*(?:mM|M)\s*[-\^]?\s*1\s*s\s*[-\^]?\s*1",
            r"\bkcat\s*/\s*Km\b\)?\s*(?:was|is|=|of)?\s*(\d+(?:\.\d+)?)",
            r"\bkcat\s+Km\b\s*(?:was|is|=|of)?\s*(\d+(?:\.\d+)?)",
            r"\bcatalytic\s+efficiency\b\s*(?:\([^)]*kcat\s*/\s*Km[^)]*\))?\s*(?:was|is|=|of)?\s*(\d+(?:\.\d+)?)",
            r"\bcatalytic\s+efficiency\b[^.;]*?\b(?:was|is|=|of)\s*(\d+(?:\.\d+)?)",
            r"\bspecificity\s+constant\b\s*(?:was|is|=|of)?\s*(\d+(?:\.\d+)?)",
            r"\bspecificity\s+constant\b[^.;]*?\b(?:was|is|=|of)\s*(\d+(?:\.\d+)?)",
        ],
    )


def _extract_kinetic_substrate(text: str, value: str | None) -> str | None:
    if value is None:
        return None
    sentence = _sentence_containing(text, value)
    patterns = [
        r"\bfor\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?),\s*(?:K|k)",
        r"\bfor\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?),\s+[^.;]*?\b(?:K|k)m\b",
        r"\btoward\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?),\s*(?:K|k)",
        r"\bkinetic\s+parameters?\s+for\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?)\s+(?:were|was|are|is)\s+(?:K|k)m\b",
        r"\bKm\s+and\s+kcat\s+values?\s+for\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?)\s+(?:were|was)\b",
        r"\bkcat\s+and\s+Km\s+values?\s+for\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?)\s+(?:were|was)\b",
        r"\bKm\s+for\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?)\s+and\s+kcat\s+(?:were|was)\b",
        r"\bKm\s+and\s+kcat\s+(?:values?\s+)?(?:were|was)\b.*?\bfor\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?)(?:[.;,]|$)",
        r"\b(?:K|k)m\s+value\s+for\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?)\s+(?:were|was|is|=)\b",
        r"(?<!and\s)\b(?:K|k)m\s+values\s+for\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?)\s+(?:were|was|is|=)\b",
        r"\bkcat\s+value\s+for\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?)\s+(?:were|was|is|=)\b",
        r"(?<!and\s)\bkcat\s+values\s+for\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{0,60}?)\s+(?:were|was|is|=)\b",
        rf"\bturnover\s+number\b[^.;]*?\b{re.escape(value)}\b[^.;]*?\bfor\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{{0,60}}?)(?:[.;,]|$)",
        rf"\bcatalytic\s+constant\b[^.;]*?\b{re.escape(value)}\b[^.;]*?\bfor\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{{0,60}}?)(?:\s+at\b|[.;,]|$)",
        rf"\bMichaelis(?:-Menten)?\s+constant\b[^.;]*?\b{re.escape(value)}\b[^.;]*?\b(?:for|toward)\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{{0,60}}?)(?:\s+at\b|[.;,]|$)",
        rf"\bcatalytic\s+efficiency\b\s+toward\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{{0,60}}?)\s+(?:was|is|=|of)\s+{re.escape(value)}\b",
        rf"\b(?:apparent\s+)?Km\b\s+for\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{{0,60}}?)\s+of\s+{re.escape(value)}\s*(?:mM|uM)?",
        rf"\b(?:kcat\s*/\s*Km|catalytic\s+efficiency|specificity\s+constant)\b[^.;]*?\b{re.escape(value)}\b[^.;]*?\bfor\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{{0,60}}?)(?:[.;,]|$)",
        rf"\b(?:K|k)m\b\s+(?:was|is|=|of)?\s*{re.escape(value)}\s*(?:mM|uM|µM)?\s+for\s+([A-Za-z0-9][A-Za-z0-9+\-()/ ]{{0,60}}?)(?:\s+and\b|[.;,]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, sentence, flags=re.IGNORECASE)
        if match:
            return _clean_substrate_name(match.group(1))
    return None


def _extract_kinetic_assay_temperature(text: str, value: str | None) -> str | None:
    return _extract_assay_temperature(text, value)


def _extract_kinetic_assay_ph(text: str, value: str | None) -> str | None:
    return _extract_assay_ph(text, value)


def _extract_assay_temperature(text: str, value: str | None) -> str | None:
    if value is None:
        return None
    sentence = _sentence_containing(text, value)
    unit = r"(?:\u00b0\s*C|\u2103|degrees?\s*C|deg\s*C|degC|C)"
    return _first_match(
        sentence,
        [
            rf"\bpH\s+and\s+temperature\s+(?:optima\s+)?(?:were|was)\s+\d+(?:\.\d+)?\s+and\s+(\d+(?:\.\d+)?)\s*{unit}",
            rf"\btemperature\s+and\s+pH\s+(?:optima\s+)?(?:were|was)\s+(\d+(?:\.\d+)?)\s*{unit}\s+and\s+\d+(?:\.\d+)?",
            rf"\bat\s+pH\s*\d+(?:\.\d+)?\s+and\s+(\d+(?:\.\d+)?)\s*{unit}",
            rf"\bat\s+(\d+(?:\.\d+)?)\s*{unit}",
            rf"\btemperature\s+(?:of\s+)?(\d+(?:\.\d+)?)\s*{unit}",
        ],
    )


def _extract_assay_ph(text: str, value: str | None) -> str | None:
    if value is None:
        return None
    sentence = _sentence_containing(text, value)
    return _first_match(
        sentence,
        [
            r"\bpH\s+and\s+temperature\s+(?:optima\s+)?(?:were|was)\s+(\d+(?:\.\d+)?)\s+and\s+\d+(?:\.\d+)?",
            r"\btemperature\s+and\s+pH\s+(?:optima\s+)?(?:were|was)\s+\d+(?:\.\d+)?\s*(?:\u00b0\s*C|\u2103|degrees?\s*C|deg\s*C|degC|C)\s+and\s+(\d+(?:\.\d+)?)",
            r"\bpH\s*(\d+(?:\.\d+)?)",
        ],
    )


def _extract_km_unit(text: str, value: str | None) -> str:
    if value is None:
        return "mM"
    sentence = _sentence_containing(text, value)
    match = re.search(rf"\b{re.escape(value)}\s*(mM|uM|µM|μM)\b", sentence, flags=re.IGNORECASE)
    if not match:
        return "mM"
    unit = match.group(1)
    return "uM" if unit.lower() in {"um", "µm", "μm"} else "mM"


def _normalize_km_unit(unit: str | None) -> str:
    return "uM" if (unit or "").lower() in {"um", "碌m", "渭m"} else "mM"


def _extract_kcat_km_unit(text: str, value: str | None) -> str:
    if value is None:
        return "mM^-1 s^-1"
    sentence = _sentence_containing(text, value)
    match = re.search(
        rf"\b{re.escape(value)}\s*(mM|M)\s*[-\^]?\s*1\s*s\s*[-\^]?\s*1\b",
        sentence,
        flags=re.IGNORECASE,
    )
    if not match:
        return "mM^-1 s^-1"
    unit = match.group(1)
    return "M^-1 s^-1" if unit == "M" else "mM^-1 s^-1"


def _clean_substrate_name(value: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", value).strip(" .;:,")
    return cleaned or None


def _extract_mutation_strings(text: str) -> list[str]:
    seen: set[str] = set()
    mutations = []
    combined_spans: list[tuple[int, int]] = []
    mutation_pattern = r"[A-Z][0-9]{1,5}[A-Z]"
    combined_pattern = rf"\b{mutation_pattern}(?:[\/+]{mutation_pattern})+\b"
    for match in re.finditer(combined_pattern, text):
        mutation = match.group(0)
        seen.add(mutation)
        mutations.append(mutation)
        combined_spans.append(match.span())
    for match in re.finditer(rf"\b{mutation_pattern}\b", text):
        if any(start <= match.start() and match.end() <= end for start, end in combined_spans):
            continue
        mutation = match.group(0)
        if mutation in seen:
            continue
        seen.add(mutation)
        mutations.append(mutation)
    return mutations


def _extract_fold_change(text: str) -> str | None:
    return _first_match(text, [r"\b(\d+(?:\.\d+)?)\s*[- ]?fold\b"])


def _extract_mutant_property_delta(sentence: str) -> dict:
    fold_change = _extract_fold_change(sentence)
    if not fold_change:
        return {}
    signed_fold_change = _signed_fold_change(sentence, fold_change)
    if re.search(r"\b(?:specific\s+activity|enzyme\s+activity|activity)\b", sentence, flags=re.IGNORECASE):
        return {"specific_activity_fold_change": signed_fold_change}
    if re.search(r"\b(?:thermostability|thermal\s+stability|stability)\b", sentence, flags=re.IGNORECASE):
        return {"thermostability_fold_change": signed_fold_change}
    return {}


def _signed_fold_change(sentence: str, fold_change: str) -> float:
    value = float(fold_change)
    if re.search(r"\b(?:lower|reduced|decreased|decrease|loss|lost)\b", sentence, flags=re.IGNORECASE):
        return -value
    return value


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


def _kinetic_unit_label(
    *,
    km: str | None,
    km_unit: str = "mM",
    kcat: str | None,
    kcat_km: str | None,
    kcat_km_unit: str = "mM^-1 s^-1",
) -> str | None:
    units = []
    if km is not None:
        units.append(km_unit)
    if kcat is not None:
        units.append("s^-1")
    if kcat_km is not None:
        units.append(kcat_km_unit)
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
