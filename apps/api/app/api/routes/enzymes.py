import hashlib
import re
from collections.abc import Iterable
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.routes.auth import current_user
from app.core.config import get_settings
from app.db.models import (
    AnalysisJob,
    EnzymeEntry,
    EnzymeFamily,
    EnzymeModule,
    ExpressionRecord,
    JobStatus,
    KineticRecord,
    LiteratureReference,
    MutationRecord,
    Project,
    ProteinSequence,
    PropertyRecord,
    SearchCacheRecord,
    StructureEntry,
    User,
)
from app.db.session import get_db
from app.external.alphafold import AlphaFoldModelMetadata, get_alphafold_client
from app.external.enzyme_data import get_enzyme_data_client
from app.external.literature import LiteratureMetadata, create_literature_reference, get_literature_client
from app.external.rcsb import RcsbStructureMetadata, get_rcsb_client
from app.external.uniprot import (
    P81453_FULL_SEQUENCE,
    P81453_MATURE_SEQUENCE,
    UniProtEntry,
    get_uniprot_client,
    parse_fasta_sequence,
)
from app.schemas.enzyme import (
    EnzymeRecordCounts,
    EnzymeSearchRequest,
    EnzymeSearchResponse,
    EnzymeRealDataRefreshResponse,
    EnzymeSummary,
    PdbDiscoveryChain,
    PdbDiscoveryHit,
    PdbDiscoveryMetadata,
    PdbDiscoveryResponse,
)
from app.schemas.job import JobResponse
from app.services.cache import (
    find_fresh_search_cache,
    find_fresh_uniprot_hit,
    find_search_cache,
    is_fresh,
    stale_data_modules,
)
from app.services.exact_matching import find_level_one_exact_match
from app.services.query_resolver import QueryKind, resolve_query
from app.services.provenance import build_fallback_provenance, build_real_provenance
from app.services.similarity_matching import calculate_ungapped_similarity, find_level_two_similarity_match
from app.services.structure_identifiers import (
    alphafold_identifier_candidates,
    extract_structure_database_identifiers,
)
from app.services.structure_parser import StructureParseError, parse_structure_text
from worker.jobs import run_homology_collection, run_real_data_refresh


router = APIRouter(prefix="/enzymes", tags=["enzymes"])

FAMILY_NAMES = {
    EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE: "Mature microbial transglutaminases",
    EnzymeModule.ANTHRAQUINONE_GLYCOSYLTRANSFERASE: "Anthraquinone glycosyltransferases",
}


def _module_for_search(
    db: Session,
    request: EnzymeSearchRequest,
    module_hint: EnzymeModule | None,
    user: User,
) -> EnzymeModule:
    if request.project_id is None:
        return module_hint or EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE

    project = db.get(Project, request.project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    if project.owner_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    return project.target_enzyme_module or module_hint or EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE


def _ensure_family(db: Session, module: EnzymeModule) -> EnzymeFamily:
    family = db.scalar(
        select(EnzymeFamily).where(
            EnzymeFamily.module == module,
            EnzymeFamily.name == FAMILY_NAMES[module],
        )
    )
    if family is not None:
        return family

    family = EnzymeFamily(
        module=module,
        name=FAMILY_NAMES[module],
        description=None,
        last_refreshed_at=datetime.utcnow(),
    )
    db.add(family)
    db.flush()
    return family


def _ensure_uniprot_entry_family(db: Session, module: EnzymeModule, entry: UniProtEntry) -> EnzymeFamily:
    family_name = _uniprot_entry_family_name(entry)
    existing = db.scalar(select(EnzymeFamily).where(func.lower(EnzymeFamily.name) == family_name.lower()))
    if existing is not None:
        return existing

    family = EnzymeFamily(
        module=module,
        name=family_name,
        description=_uniprot_entry_family_description(entry),
        last_refreshed_at=datetime.utcnow(),
    )
    db.add(family)
    db.flush()
    return family


def _uniprot_entry_family_name(entry: UniProtEntry) -> str:
    return " ".join((entry.protein_name or "").split()) or "Unclassified enzyme family"


def _uniprot_entry_family_description(entry: UniProtEntry) -> str | None:
    parts = [
        f"EC {entry.ec_number}" if entry.ec_number else None,
        "Family inferred from UniProt search result.",
    ]
    return " ".join(part for part in parts if part)


def _seed_sequence_for_module(module: EnzymeModule) -> str:
    if module == EnzymeModule.ANTHRAQUINONE_GLYCOSYLTRANSFERASE:
        return "MSTGTSVTPAPATTPAQPGDDVLLVGTGGTYAGALAARLGADAVVVADLPGDPARAARALAEAG"
    return P81453_FULL_SEQUENCE


def _seed_mature_sequence_for_module(module: EnzymeModule) -> str | None:
    if module == EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE:
        return P81453_MATURE_SEQUENCE
    return None


def _find_seed_entry(
    db: Session,
    family_id: str,
    name: str,
    source: str,
    uniprot_id: str | None,
) -> EnzymeEntry | None:
    if uniprot_id is not None:
        return db.scalar(select(EnzymeEntry).where(EnzymeEntry.uniprot_id == uniprot_id))
    return db.scalar(
        select(EnzymeEntry).where(
            EnzymeEntry.family_id == family_id,
            EnzymeEntry.name == name,
            EnzymeEntry.source == source,
        )
    )


def _ensure_protein_sequence(
    db: Session,
    enzyme: EnzymeEntry,
    module: EnzymeModule,
) -> None:
    existing_sequence = db.scalar(
        select(ProteinSequence).where(ProteinSequence.enzyme_entry_id == enzyme.id)
    )
    if existing_sequence is not None:
        sequence = _seed_sequence_for_module(module)
        mature_sequence = _seed_mature_sequence_for_module(module)
        if (
            _should_repair_mtgase_seed_sequence(enzyme, existing_sequence, module)
            and module == EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE
            and existing_sequence.mature_sequence != mature_sequence
        ):
            existing_sequence.sequence = sequence
            existing_sequence.mature_sequence = mature_sequence
            existing_sequence.is_engineering_target = True
            existing_sequence.source = "seed"
            existing_sequence.checksum = hashlib.sha256((mature_sequence or sequence).encode("utf-8")).hexdigest()
        return

    sequence = _seed_sequence_for_module(module)
    mature_sequence = _seed_mature_sequence_for_module(module)
    db.add(
        ProteinSequence(
            enzyme_entry_id=enzyme.id,
            sequence=sequence,
            mature_sequence=mature_sequence,
            is_engineering_target=True,
            source="seed",
            checksum=hashlib.sha256((mature_sequence or sequence).encode("utf-8")).hexdigest(),
        )
    )


def _should_repair_mtgase_seed_sequence(
    enzyme: EnzymeEntry,
    protein_sequence: ProteinSequence,
    module: EnzymeModule,
) -> bool:
    if module != EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE:
        return False
    if protein_sequence.source == "seed":
        return True
    return bool(enzyme.uniprot_id and enzyme.uniprot_id.upper().startswith("MOCK"))


def _fetch_uniprot_entries(
    resolved_query,
    *,
    limit: int,
    organism: str | None = None,
    include_details: bool = True,
) -> list[tuple[UniProtEntry, str | None, str | None, dict | None]]:
    client = get_uniprot_client()
    try:
        entries = _fetch_uniprot_entries_with_client(
            resolved_query,
            client,
            limit=limit,
            organism=organism,
            include_details=include_details,
        )
    except (httpx.HTTPError, ValueError) as exc:
        if getattr(client, "source", "uniprot").endswith("_mock"):
            raise
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"UniProt provider unavailable; no mock enzyme record was created. {exc}",
        ) from exc
    return [
        (entry, fasta, source, _uniprot_retrieval_provenance(entry, source))
        for entry, fasta, source in entries
        if entry is not None
    ]


def _fetch_uniprot_entries_with_client(
    resolved_query,
    client,
    *,
    limit: int,
    organism: str | None = None,
    include_details: bool = True,
) -> list[tuple[UniProtEntry, str | None, str | None]]:
    source = getattr(client, "source", "uniprot")

    def _entry_from_hit(hit) -> UniProtEntry:
        return UniProtEntry(
            accession=hit.accession,
            protein_name=hit.protein_name,
            organism=hit.organism,
            ec_number=hit.ec_number,
            reviewed=False,
            cross_references={"UniProtKB": hit.accession},
        )

    if resolved_query.kind == QueryKind.UNIPROT:
        entry = client.fetch_entry(resolved_query.normalized_query)
        return [(entry, client.fetch_fasta(entry.accession), source)]
    if resolved_query.kind == QueryKind.ALPHAFOLD:
        accession = _uniprot_accession_from_alphafold_id(resolved_query.normalized_query)
        if accession is None:
            return []
        entry = client.fetch_entry(accession)
        return [(entry, client.fetch_fasta(entry.accession), source)]

    hits = []
    if resolved_query.kind == QueryKind.EC:
        if organism:
            hits = client.search_by_keyword(
                _uniprot_query_with_organism(f"ec:{resolved_query.normalized_query}", organism),
                size=limit,
            )
        else:
            hits = client.search_by_ec(resolved_query.normalized_query, size=limit)
    elif resolved_query.kind == QueryKind.KEYWORD:
        hits = client.search_by_keyword(
            _uniprot_query_with_organism(resolved_query.normalized_query, organism),
            size=limit,
        )

    entries: list[tuple[UniProtEntry, str | None, str | None]] = []
    seen_accessions: set[str] = set()
    for index, hit in enumerate(hits[:limit]):
        if hit.accession in seen_accessions:
            continue
        seen_accessions.add(hit.accession)
        if include_details and index == 0:
            entry = client.fetch_entry(hit.accession)
            entries.append((entry, client.fetch_fasta(entry.accession), source))
            continue
        entries.append((_entry_from_hit(hit), None, source))
    return entries


def _uniprot_accession_from_alphafold_id(alphafold_id: str) -> str | None:
    match = re.fullmatch(r"AF-([A-Z0-9]+)-F\d+", alphafold_id.upper())
    return match.group(1) if match else None


def _normalize_source_organism(organism: str | None) -> str | None:
    normalized = " ".join((organism or "").split())
    return normalized or None


def _uniprot_query_with_organism(query: str, organism: str | None) -> str:
    normalized_organism = _normalize_source_organism(organism)
    if normalized_organism is None:
        return query
    escaped_organism = normalized_organism.replace('"', "")
    return f'{query} AND organism_name:"{escaped_organism}"'


def _uniprot_retrieval_provenance(entry: UniProtEntry | None, source: str | None) -> dict | None:
    if entry is None:
        return None
    provenance = entry.cross_references.get("provenance")
    if isinstance(provenance, dict):
        return provenance
    provider = source or "uniprot"
    if provider.endswith("_mock"):
        return build_fallback_provenance(
            provider=provider,
            warning="UniProt record came from a configured fallback client.",
            extra={"accession": entry.accession},
        )
    return build_real_provenance(
        provider=provider,
        source_url=f"https://rest.uniprot.org/uniprotkb/{entry.accession}.json",
    )


def _first_cross_reference_id(cross_references: dict, key: str) -> str | None:
    value = cross_references.get(key)
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
            if isinstance(item, dict):
                candidate = item.get("id") or item.get("value")
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
    return None


def _create_enzyme_from_uniprot_entry(
    db: Session,
    *,
    family: EnzymeFamily,
    entry: UniProtEntry,
    fasta: str | None,
    source: str | None,
) -> EnzymeEntry:
    now = datetime.utcnow()
    sequence = entry.sequence or parse_fasta_sequence(fasta or "")
    pdb_id = _first_cross_reference_id(entry.cross_references, "PDB")
    enzyme = EnzymeEntry(
        family_id=family.id,
        name=entry.protein_name,
        organism=entry.organism,
        ec_number=entry.ec_number,
        uniprot_id=entry.accession,
        uniprot_reviewed=entry.reviewed,
        pdb_id=pdb_id,
        alphafold_id=entry.cross_references.get("AlphaFoldDB"),
        source=source or "uniprot",
        last_refreshed_at=now,
    )
    db.add(enzyme)
    db.flush()

    if sequence:
        mature_sequence = entry.mature_sequence or sequence
        db.add(
            ProteinSequence(
                enzyme_entry_id=enzyme.id,
                sequence=sequence,
                mature_sequence=mature_sequence,
                is_engineering_target=True,
                source=source or "uniprot",
                checksum=hashlib.sha256(mature_sequence.encode("utf-8")).hexdigest(),
            )
        )

    alphafold_id = entry.cross_references.get("AlphaFoldDB")
    if alphafold_id:
        model, alphafold_source, alphafold_provenance = _fetch_alphafold_model(entry.accession)
        if model is not None:
            _create_alphafold_structure(
                db,
                enzyme=enzyme,
                model=model,
                source=alphafold_source,
                provenance=alphafold_provenance,
            )
    if pdb_id:
        _save_rcsb_structure_for_enzyme(db, enzyme, pdb_id=pdb_id)
    return enzyme


def _upsert_enzyme_from_uniprot_entry(
    db: Session,
    *,
    family: EnzymeFamily,
    entry: UniProtEntry,
    fasta: str | None,
    source: str | None,
) -> EnzymeEntry:
    enzyme = db.scalar(select(EnzymeEntry).where(EnzymeEntry.uniprot_id == entry.accession))
    if enzyme is None:
        return _create_enzyme_from_uniprot_entry(
            db,
            family=family,
            entry=entry,
            fasta=fasta,
            source=source,
        )

    now = datetime.utcnow()
    enzyme.family_id = family.id
    enzyme.name = entry.protein_name
    enzyme.organism = entry.organism
    enzyme.ec_number = entry.ec_number
    enzyme.uniprot_reviewed = entry.reviewed
    enzyme.pdb_id = _first_cross_reference_id(entry.cross_references, "PDB")
    enzyme.alphafold_id = entry.cross_references.get("AlphaFoldDB")
    enzyme.source = source or "uniprot"
    enzyme.last_refreshed_at = now
    enzyme.updated_at = now

    sequence = entry.sequence or parse_fasta_sequence(fasta or "")
    mature_sequence = entry.mature_sequence or sequence
    if sequence and mature_sequence:
        protein_sequence = db.scalar(
            select(ProteinSequence).where(ProteinSequence.enzyme_entry_id == enzyme.id)
        )
        checksum = hashlib.sha256(mature_sequence.encode("utf-8")).hexdigest()
        if protein_sequence is None:
            db.add(
                ProteinSequence(
                    enzyme_entry_id=enzyme.id,
                    sequence=sequence,
                    mature_sequence=mature_sequence,
                    is_engineering_target=True,
                    source=source or "uniprot",
                    checksum=checksum,
                )
            )
        else:
            protein_sequence.sequence = sequence
            protein_sequence.mature_sequence = mature_sequence
            protein_sequence.is_engineering_target = True
            protein_sequence.source = source or "uniprot"
            protein_sequence.checksum = checksum
    if enzyme.pdb_id:
        _save_rcsb_structure_for_enzyme(db, enzyme, pdb_id=enzyme.pdb_id)
    return enzyme


def _fetch_alphafold_model(uniprot_id: str) -> tuple[AlphaFoldModelMetadata | None, str, dict | None]:
    client = get_alphafold_client()
    source = getattr(client, "source", "alphafold")
    try:
        model = client.fetch_model_by_uniprot(uniprot_id)
        return model, source, None
    except (httpx.HTTPError, ValueError) as exc:
        if source.endswith("_mock"):
            raise
        return None, source, build_real_provenance(
            provider=source,
            source_url=f"https://alphafold.ebi.ac.uk/search/text/{uniprot_id}",
            extra={"warning": f"AlphaFold provider failed; no mock model used. {exc}"},
        )


def _save_literature_for_enzyme(
    db: Session,
    enzyme: EnzymeEntry,
    *,
    require_real: bool = False,
    skip_mock: bool = False,
) -> tuple[int, list[str], list[str]]:
    client = get_literature_client()
    source = getattr(client, "source", "literature")
    if require_real:
        _raise_if_mock_provider(source, "literature")
    if skip_mock and _is_mock_or_seed_source(source):
        return 0, [source], [f"Literature provider is configured as {source}; mock references were skipped."]
    try:
        hits = client.search_by_enzyme_name(enzyme.name)
    except (httpx.HTTPError, ValueError) as exc:
        if source.endswith("_mock"):
            raise
        if require_real:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Literature provider unavailable; no mock references were used. {exc}",
            ) from exc
        return 0, [source], [f"Literature provider unavailable: {exc}"]

    created = 0
    for metadata in hits:
        existed = _literature_reference_exists(db, metadata.doi, metadata.pubmed_id)
        create_literature_reference(db, metadata)
        if not existed:
            created += 1
    return created, [source], []


def _save_external_enzyme_data(
    db: Session,
    enzyme: EnzymeEntry,
    *,
    require_real: bool = False,
    skip_mock: bool = False,
) -> tuple[dict[str, int], list[str], list[str]]:
    client = get_enzyme_data_client()
    source = getattr(client, "source", "enzyme_data")
    if require_real:
        _raise_if_mock_provider(source, "enzyme data")
    query = enzyme.name
    created = {"references": 0, "properties": 0, "kinetics": 0, "mutations": 0}
    if skip_mock and _is_mock_or_seed_source(source):
        return created, [source], [f"Enzyme data provider is configured as {source}; mock records were skipped."]

    fetch_size = get_settings().enzyme_data_provider_fetch_size
    property_data = []
    kinetic_parameters = []
    mutant_records = []
    for query_variant in _external_enzyme_data_queries(enzyme):
        property_data.extend(client.fetch_opt_temperature(query_variant, size=fetch_size))
        property_data.extend(client.fetch_opt_pH(query_variant, size=fetch_size))
        fetch_specific_activity = getattr(client, "fetch_specific_activity", None)
        if callable(fetch_specific_activity):
            property_data.extend(fetch_specific_activity(query_variant, size=fetch_size))
        kinetic_parameters.extend(client.fetch_kinetic_parameters(query_variant, size=fetch_size))
        mutant_records.extend(client.fetch_mutants(query_variant, size=fetch_size))

    data_sources = {source}
    warnings = []
    seen_property_data: set[tuple] = set()
    for datum in property_data:
        data_sources.add(getattr(datum, "source", None) or source)
        target_enzyme = _target_enzyme_for_external_datum(db, enzyme, datum)
        if target_enzyme is None:
            warnings.append(_external_datum_mismatch_warning(enzyme, datum))
            continue
        data_key = (
            target_enzyme.id,
            datum.property_type,
            datum.value_original,
            datum.unit_original,
            datum.substrate,
            datum.organism,
            datum.doi,
            datum.pubmed_id,
        )
        if data_key in seen_property_data:
            continue
        seen_property_data.add(data_key)
        reference, reference_created = _create_reference_for_external_datum(db, datum)
        if reference_created:
            created["references"] += 1
        existing = db.scalar(
            select(PropertyRecord).where(
                PropertyRecord.enzyme_entry_id == target_enzyme.id,
                PropertyRecord.property_type == datum.property_type,
                PropertyRecord.value_original == datum.value_original,
                PropertyRecord.unit_original == datum.unit_original,
                PropertyRecord.substrate == datum.substrate,
            )
        )
        if existing is not None:
            _backfill_external_reference(existing, reference, datum.evidence)
            continue
        db.add(
            PropertyRecord(
                enzyme_entry_id=target_enzyme.id,
                property_type=datum.property_type,
                value_original=datum.value_original,
                unit_original=datum.unit_original,
                substrate=datum.substrate,
                assay_temperature=datum.assay_temperature,
                assay_pH=datum.assay_pH,
                method=datum.source,
                reference_id=reference.id if reference else None,
                evidence_text=datum.evidence,
            )
        )
        created["properties"] += 1

    seen_kinetic_data: set[tuple] = set()
    for parameter in kinetic_parameters:
        data_sources.add(getattr(parameter, "source", None) or source)
        target_enzyme = _target_enzyme_for_external_datum(db, enzyme, parameter)
        if target_enzyme is None:
            warnings.append(_external_datum_mismatch_warning(enzyme, parameter))
            continue
        data_key = (
            target_enzyme.id,
            parameter.substrate,
            parameter.km,
            parameter.kcat,
            parameter.kcat_km,
            parameter.unit_original,
            parameter.organism,
            parameter.doi,
            parameter.pubmed_id,
        )
        if data_key in seen_kinetic_data:
            continue
        seen_kinetic_data.add(data_key)
        reference, reference_created = _create_reference_for_external_datum(db, parameter)
        if reference_created:
            created["references"] += 1
        existing = db.scalar(
            select(KineticRecord).where(
                KineticRecord.enzyme_entry_id == target_enzyme.id,
                KineticRecord.substrate == parameter.substrate,
                KineticRecord.km == parameter.km,
                KineticRecord.kcat == parameter.kcat,
                KineticRecord.kcat_km == parameter.kcat_km,
                KineticRecord.unit_original == parameter.unit_original,
            )
        )
        if existing is not None:
            _backfill_external_reference(existing, reference, parameter.evidence)
            continue
        db.add(
            KineticRecord(
                enzyme_entry_id=target_enzyme.id,
                substrate=parameter.substrate,
                km=parameter.km,
                kcat=parameter.kcat,
                kcat_km=parameter.kcat_km,
                unit_original=parameter.unit_original,
                assay_temperature=parameter.assay_temperature,
                assay_pH=parameter.assay_pH,
                method=parameter.source,
                reference_id=reference.id if reference else None,
                evidence_text=parameter.evidence,
            )
        )
        created["kinetics"] += 1

    seen_mutant_data: set[tuple] = set()
    for mutant in mutant_records:
        data_sources.add(getattr(mutant, "source", None) or source)
        target_enzyme = _target_enzyme_for_external_datum(db, enzyme, mutant)
        if target_enzyme is None:
            warnings.append(_external_datum_mismatch_warning(enzyme, mutant))
            continue
        data_key = (
            target_enzyme.id,
            mutant.mutation_string,
            mutant.substrate,
            mutant.organism,
            mutant.doi,
            mutant.pubmed_id,
        )
        if data_key in seen_mutant_data:
            continue
        seen_mutant_data.add(data_key)
        reference, reference_created = _create_reference_for_external_datum(db, mutant)
        if reference_created:
            created["references"] += 1
        existing = _find_existing_external_mutation(db, target_enzyme, mutant)
        if existing is not None:
            _backfill_external_reference(existing, reference, mutant.evidence)
            continue
        db.add(
            MutationRecord(
                enzyme_entry_id=target_enzyme.id,
                mutation_string=mutant.mutation_string,
                effect_summary=mutant.effect_summary,
                property_delta=mutant.property_delta,
                substrate=mutant.substrate,
                assay_condition_summary={
                    "source": mutant.source,
                    "evidence": mutant.evidence,
                    "organism": mutant.organism,
                },
                reference_id=reference.id if reference else None,
            )
        )
        created["mutations"] += 1
    return created, _unique_strings([item for item in data_sources if item]), _unique_strings(warnings)


def _external_enzyme_data_queries(enzyme: EnzymeEntry) -> list[str]:
    queries = []
    organism = _normalize_source_organism(enzyme.organism)
    if organism and enzyme.uniprot_id:
        queries.append(f"{enzyme.name} {organism} {enzyme.uniprot_id}")
    if organism:
        queries.append(f"{enzyme.name} {organism}")
    if enzyme.uniprot_id and not organism:
        queries.append(f"{enzyme.name} {enzyme.uniprot_id}")
    if not organism:
        queries.append(enzyme.name)
    return _unique_strings(queries)


def _target_enzyme_for_external_datum(db: Session, enzyme: EnzymeEntry, datum) -> EnzymeEntry | None:
    organism = _normalize_source_organism(getattr(datum, "organism", None))
    if organism is None:
        if _external_datum_needs_explicit_organism(datum):
            return None
        return enzyme
    if _enzyme_matches_organism(enzyme, organism):
        return enzyme
    family_entries = db.scalars(
        select(EnzymeEntry).where(
            EnzymeEntry.family_id == enzyme.family_id,
            EnzymeEntry.id != enzyme.id,
        )
    ).all()
    for candidate in family_entries:
        if _enzyme_matches_organism(candidate, organism):
            return candidate
    return None


def _external_datum_needs_explicit_organism(datum) -> bool:
    return (getattr(datum, "source", "") or "").lower() in {
        "europepmc",
        "openalex",
        "pubmed",
        "semanticscholar",
    }


def _external_datum_mismatch_warning(enzyme: EnzymeEntry, datum) -> str:
    organism = getattr(datum, "organism", None) or "unknown organism"
    if organism == "unknown organism" and _external_datum_needs_explicit_organism(datum):
        return (
            "Skipped external literature record because no organism was extracted; "
            f"it was not attached to {enzyme.organism or enzyme.name}."
        )
    return (
        f"Skipped external record for {organism}; it did not match "
        f"{enzyme.organism or enzyme.name} or another local family entry."
    )


def _backfill_external_reference(record, reference: LiteratureReference | None, evidence: str | None) -> None:
    if reference is not None and getattr(record, "reference_id", None) is None:
        record.reference_id = reference.id
    if evidence and hasattr(record, "evidence_text") and getattr(record, "evidence_text", None) is None:
        record.evidence_text = evidence
    if evidence and isinstance(record, MutationRecord):
        summary = dict(record.assay_condition_summary or {})
        summary.setdefault("evidence", evidence)
        record.assay_condition_summary = summary


def _find_existing_external_mutation(db: Session, enzyme: EnzymeEntry, mutant) -> MutationRecord | None:
    candidates = db.scalars(
        select(MutationRecord).where(
            MutationRecord.enzyme_entry_id == enzyme.id,
            MutationRecord.mutation_string == mutant.mutation_string,
            MutationRecord.substrate == mutant.substrate,
        )
    ).all()
    target_delta = _normalized_mutation_property_delta(mutant.property_delta)
    for candidate in candidates:
        if _normalized_mutation_property_delta(candidate.property_delta) == target_delta:
            return candidate
    return None


def _normalized_mutation_property_delta(value) -> dict:
    return value if isinstance(value, dict) and value else {}


def _create_reference_for_external_datum(db: Session, datum) -> tuple[LiteratureReference | None, bool]:
    if not any(
        getattr(datum, field, None)
        for field in ("reference_title", "doi", "pubmed_id", "journal", "year")
    ):
        return None, False
    doi = _normalize_external_doi(getattr(datum, "doi", None))
    existing_reference = _find_literature_reference(
        db,
        doi,
        getattr(datum, "pubmed_id", None),
    )
    if existing_reference is not None:
        return existing_reference, False
    title = getattr(datum, "reference_title", None) or getattr(datum, "evidence", None) or "External enzyme data evidence"
    metadata = LiteratureMetadata(
        title=title,
        journal=getattr(datum, "journal", None),
        year=getattr(datum, "year", None),
        doi=doi,
        pubmed_id=_normalize_external_pubmed_id(getattr(datum, "pubmed_id", None)),
        abstract=getattr(datum, "evidence", None),
        source=getattr(datum, "source", None) or "external_enzyme_data",
        metadata={"topics": ["enzyme_data"]},
    )
    reference = create_literature_reference(db, metadata)
    return reference, True


def _save_alphafold_structure_for_enzyme(
    db: Session,
    enzyme: EnzymeEntry,
    *,
    require_real: bool = False,
) -> tuple[int, list[str], list[str]]:
    if not enzyme.uniprot_id or not enzyme.alphafold_id:
        return 0, [], []
    existing = db.scalar(
        select(StructureEntry).where(
            StructureEntry.enzyme_entry_id == enzyme.id,
            StructureEntry.structure_type == "alphafold",
        )
    )
    if existing is not None:
        return 0, [], []

    client = get_alphafold_client()
    source = getattr(client, "source", "alphafold")
    if require_real:
        _raise_if_mock_provider(source, "AlphaFold")
    try:
        model = client.fetch_model_by_uniprot(enzyme.uniprot_id)
    except (httpx.HTTPError, ValueError) as exc:
        if source.endswith("_mock"):
            raise
        if require_real:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"AlphaFold provider unavailable; no mock structure was used. {exc}",
            ) from exc
        return 0, [source], [f"AlphaFold provider unavailable: {exc}"]

    _create_alphafold_structure(
        db,
        enzyme=enzyme,
        model=model,
        source=source,
        provenance=build_real_provenance(provider=source, source_url=model.structure_url),
    )
    enzyme.alphafold_id = model.model_id
    return 1, [source], []


def _literature_reference_exists(db: Session, doi: str | None, pubmed_id: str | None) -> bool:
    return _find_literature_reference(db, doi, pubmed_id) is not None


def _find_literature_reference(db: Session, doi: str | None, pubmed_id: str | None) -> LiteratureReference | None:
    doi = _normalize_external_doi(doi)
    pubmed_id = _normalize_external_pubmed_id(pubmed_id)
    if doi:
        reference = db.scalar(
            select(LiteratureReference).where(func.lower(LiteratureReference.doi).in_(_doi_lookup_values(doi)))
        )
        if reference is not None:
            reference.doi = doi
            return reference
    if pubmed_id:
        reference = db.scalar(
            select(LiteratureReference).where(
                func.lower(LiteratureReference.pubmed_id).in_(_pubmed_lookup_values(pubmed_id))
            )
        )
        if reference is not None:
            reference.pubmed_id = pubmed_id
        return reference
    return None


def _doi_lookup_values(doi: str) -> list[str]:
    return [doi, f"https://doi.org/{doi}", f"http://doi.org/{doi}", f"https://dx.doi.org/{doi}"]


def _normalize_external_doi(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    normalized = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"^doi:\s*", "", normalized, flags=re.IGNORECASE)
    return normalized.lower()


def _normalize_external_pubmed_id(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"\d+", value)
    return match.group(0) if match else None


def _pubmed_lookup_values(pubmed_id: str) -> list[str]:
    return [
        pubmed_id,
        f"PMID:{pubmed_id}",
        f"PMID: {pubmed_id}",
        f"pmid:{pubmed_id}",
        f"pmid: {pubmed_id}",
        f"PubMed:{pubmed_id}",
        f"PubMed: {pubmed_id}",
        f"pubmed:{pubmed_id}",
        f"pubmed: {pubmed_id}",
    ]


def _raise_if_mock_provider(source: str | None, provider_label: str) -> None:
    if not _is_mock_or_seed_source(source):
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"{provider_label} provider is configured as {source}; real-data refresh will not use mock data.",
    )


def _create_alphafold_structure(
    db: Session,
    *,
    enzyme: EnzymeEntry,
    model: AlphaFoldModelMetadata,
    source: str,
    provenance: dict | None = None,
) -> StructureEntry:
    now = datetime.utcnow()
    chain_summary = {
        "model_id": model.model_id,
        "uniprot_id": model.uniprot_id,
        "structure_url": model.structure_url,
        "confidence_url": model.confidence_url,
        "confidence_summary": model.confidence_summary,
        "provenance": provenance or _provider_provenance(
            provider=source,
            source_url=model.structure_url,
            fallback_warning="AlphaFold model came from a configured fallback client.",
        ),
    }
    structure = StructureEntry(
        enzyme_entry_id=enzyme.id,
        structure_type="alphafold",
        complex_state="predicted",
        pdb_id=None,
        chain_summary=chain_summary,
        ligand_summary={"ligands": []},
        source=source,
        created_at=now,
        updated_at=now,
    )
    db.add(structure)
    return structure


def _save_rcsb_structure_for_enzyme(
    db: Session,
    enzyme: EnzymeEntry,
    *,
    pdb_id: str,
    require_real: bool = False,
) -> tuple[int, list[str], list[str]]:
    normalized_pdb_id = pdb_id.upper()
    enzyme.pdb_id = normalized_pdb_id
    existing = db.scalar(
        select(StructureEntry).where(
            StructureEntry.enzyme_entry_id == enzyme.id,
            StructureEntry.pdb_id == normalized_pdb_id,
        )
    )
    if existing is not None:
        return 0, [], []

    client = get_rcsb_client()
    source = getattr(client, "source", "rcsb")
    if require_real:
        _raise_if_mock_provider(source, "RCSB")
    try:
        metadata = client.fetch_structure_metadata(normalized_pdb_id)
    except (httpx.HTTPError, ValueError) as exc:
        if source.endswith("_mock"):
            raise
        if require_real:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"RCSB provider unavailable; no mock structure was used. {exc}",
            ) from exc
        return 0, [source], [f"RCSB provider unavailable: {exc}"]

    now = datetime.utcnow()
    chain_summary = dict(metadata.chain_summary)
    chain_summary["provenance"] = _provider_provenance(
        provider=source,
        source_url=f"https://www.rcsb.org/structure/{normalized_pdb_id}",
        fallback_warning="RCSB structure metadata came from a configured fallback client.",
    )
    structure = StructureEntry(
        enzyme_entry_id=enzyme.id,
        structure_type="pdb",
        complex_state="unknown",
        pdb_id=normalized_pdb_id,
        chain_summary=chain_summary,
        ligand_summary=metadata.ligand_summary,
        source=source,
        created_at=now,
        updated_at=now,
    )
    db.add(structure)
    return 1, [source], []


def _create_enzyme_from_rcsb_metadata(
    db: Session,
    *,
    family: EnzymeFamily,
    metadata: RcsbStructureMetadata,
    source: str | None,
    provenance: dict | None = None,
) -> EnzymeEntry:
    now = datetime.utcnow()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name=metadata.title,
        organism=metadata.organism,
        uniprot_id=metadata.uniprot_id,
        pdb_id=metadata.pdb_id,
        source=source or "rcsb",
        last_refreshed_at=now,
    )
    db.add(enzyme)
    db.flush()
    chain_summary = dict(metadata.chain_summary)
    chain_summary["provenance"] = provenance or _provider_provenance(
        provider=source or "rcsb",
        source_url=f"https://www.rcsb.org/structure/{metadata.pdb_id}",
        fallback_warning="RCSB structure metadata came from a configured fallback client.",
    )
    db.add(
        StructureEntry(
            enzyme_entry_id=enzyme.id,
            structure_type="pdb",
            complex_state="unknown",
            pdb_id=metadata.pdb_id,
            chain_summary=chain_summary,
            ligand_summary=metadata.ligand_summary,
            source=source or "rcsb",
            created_at=now,
            updated_at=now,
        )
    )
    return enzyme


def _fetch_rcsb_metadata(pdb_id: str) -> tuple[RcsbStructureMetadata, str, dict | None]:
    client = get_rcsb_client()
    source = getattr(client, "source", "rcsb")
    try:
        return client.fetch_structure_metadata(pdb_id), source, None
    except (httpx.HTTPError, ValueError) as exc:
        if source.endswith("_mock"):
            raise
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"RCSB provider unavailable; no mock structure record was created. {exc}",
        ) from exc


def _provider_provenance(*, provider: str, source_url: str | None, fallback_warning: str) -> dict:
    if provider.endswith("_mock"):
        return build_fallback_provenance(
            provider=provider,
            warning=fallback_warning,
            extra={"source_url": source_url} if source_url else None,
        )
    return build_real_provenance(provider=provider, source_url=source_url)


def _search_cache_payload(
    enzyme: EnzymeEntry,
    job: AnalysisJob,
    retrieval_provenance: dict | None = None,
) -> dict:
    payload = {
        "enzyme_entry_id": enzyme.id,
        "job_id": job.id,
    }
    if retrieval_provenance is not None:
        payload["retrieval_provenance"] = retrieval_provenance
    return payload


def _search_cache_normalized_query(normalized_query: str, organism: str | None) -> str:
    normalized_organism = _normalize_source_organism(organism)
    if normalized_organism is None:
        return normalized_query
    return f"{normalized_query} | organism:{normalized_organism.lower()}"


def _upsert_search_cache(
    db: Session,
    *,
    query: str,
    normalized_query: str,
    query_kind: str,
    module: EnzymeModule,
    enzyme: EnzymeEntry,
    job: AnalysisJob,
    retrieval_provenance: dict | None = None,
) -> None:
    now = datetime.utcnow()
    record = find_search_cache(db, normalized_query, query_kind, module)
    if record is None:
        db.add(
            SearchCacheRecord(
                query=query,
                normalized_query=normalized_query,
                query_kind=query_kind,
                module=module,
                enzyme_entry_id=enzyme.id,
                payload_json=_search_cache_payload(enzyme, job, retrieval_provenance),
                source=enzyme.source,
                last_refreshed_at=now,
                updated_at=now,
            )
        )
        return

    record.query = query
    record.enzyme_entry_id = enzyme.id
    record.payload_json = _search_cache_payload(enzyme, job, retrieval_provenance)
    record.source = enzyme.source
    record.last_refreshed_at = now
    record.updated_at = now


def _search_result_matches(
    db: Session,
    *,
    primary_enzyme: EnzymeEntry,
    query: str,
    organism: str | None = None,
    limit: int = 12,
) -> list[EnzymeEntry]:
    query_terms = [term for term in query.lower().replace("_", " ").split() if term]
    candidates = list(
        db.scalars(
            select(EnzymeEntry)
            .where(EnzymeEntry.family_id == primary_enzyme.family_id)
            .order_by(EnzymeEntry.updated_at.desc(), EnzymeEntry.created_at.desc())
            .limit(100)
        )
    )
    if get_settings().use_real_science_providers:
        candidates = [candidate for candidate in candidates if not _is_mock_or_seed_source(candidate.source)]
    candidates = [candidate for candidate in candidates if _enzyme_matches_organism(candidate, organism)]

    def score(candidate: EnzymeEntry) -> tuple[int, int, int]:
        haystack = " ".join(
            [
                candidate.name or "",
                candidate.organism or "",
                candidate.ec_number or "",
                candidate.uniprot_id or "",
                candidate.pdb_id or "",
                candidate.source or "",
            ]
        ).lower()
        term_score = sum(1 for term in query_terms if term in haystack)
        exact_score = 5 if query.lower() in haystack else 0
        same_ec_score = (
            3
            if primary_enzyme.ec_number
            and candidate.ec_number
            and candidate.ec_number == primary_enzyme.ec_number
            else 0
        )
        primary_score = 20 if candidate.id == primary_enzyme.id else 0
        return (primary_score + exact_score + same_ec_score + term_score, 1, 0)

    scientific_ranks = _enzyme_scientific_rankings(db, candidates)
    ranked = sorted(
        candidates,
        key=lambda candidate: (*score(candidate), scientific_ranks.get(candidate.id, (0, 0.0, 0.0))),
        reverse=True,
    )
    matches: list[EnzymeEntry] = []
    seen: set[str] = set()
    for candidate in ranked:
        if candidate.id in seen:
            continue
        candidate_score, _, _ = score(candidate)
        if candidate.id != primary_enzyme.id and candidate_score <= 0:
            continue
        matches.append(candidate)
        seen.add(candidate.id)
        if len(matches) >= limit:
            break
    return matches


def _backfill_sparse_uniprot_search_results(
    db: Session,
    *,
    primary_enzyme: EnzymeEntry,
    resolved_query,
    query: str,
    module: EnzymeModule,
    organism: str | None,
    limit: int,
) -> None:
    if not get_settings().use_real_science_providers:
        return
    if resolved_query.kind not in {QueryKind.EC, QueryKind.KEYWORD}:
        return
    existing_matches = _search_result_matches(
        db,
        primary_enzyme=primary_enzyme,
        query=query,
        organism=organism,
        limit=limit,
    )
    if len(existing_matches) >= limit:
        return

    try:
        fetched_entries = _fetch_uniprot_entries(
            resolved_query,
            limit=limit,
            organism=organism,
            include_details=False,
        )
    except HTTPException:
        return

    uniprot_family: EnzymeFamily | None = None
    for entry, fasta, source, _entry_provenance in fetched_entries:
        if uniprot_family is None:
            uniprot_family = _ensure_uniprot_entry_family(db, module, entry)
        _upsert_enzyme_from_uniprot_entry(
            db,
            family=uniprot_family,
            entry=entry,
            fasta=fasta,
            source=source,
        )


def _find_local_keyword_match(
    db: Session,
    *,
    module: EnzymeModule,
    query: str,
    organism: str | None = None,
) -> EnzymeEntry | None:
    query_terms = [term for term in query.lower().replace("_", " ").split() if term]
    if not query_terms:
        return None

    enzyme_query = (
        select(EnzymeEntry)
        .join(EnzymeFamily, EnzymeFamily.id == EnzymeEntry.family_id)
        .where(EnzymeFamily.module == module)
        .order_by(EnzymeEntry.updated_at.desc(), EnzymeEntry.created_at.desc())
        .limit(200)
    )
    candidates = list(db.scalars(enzyme_query))
    if get_settings().use_real_science_providers:
        candidates = [candidate for candidate in candidates if not _is_mock_or_seed_source(candidate.source)]
    candidates = [candidate for candidate in candidates if _enzyme_matches_organism(candidate, organism)]

    if not candidates:
        return None

    normalized_query = query.lower().strip()
    scientific_ranks = _enzyme_scientific_rankings(db, candidates)

    def score(candidate: EnzymeEntry) -> tuple[int, int, tuple[int, float, float]]:
        haystack = " ".join(
            [
                candidate.name or "",
                candidate.organism or "",
                candidate.ec_number or "",
                candidate.uniprot_id or "",
                candidate.pdb_id or "",
                candidate.alphafold_id or "",
            ]
        ).lower()
        if not haystack:
            return (0, 0, (0, 0.0, 0.0))
        exact_score = 10 if normalized_query in haystack else 0
        term_score = sum(1 for term in query_terms if term in haystack)
        return (exact_score, term_score, scientific_ranks.get(candidate.id, (0, 0.0, 0.0)))

    ranked = sorted(candidates, key=score, reverse=True)
    best = ranked[0]
    exact_score, term_score, _ = score(best)
    if exact_score <= 0 and term_score <= 0:
        return None
    return best


def _enzyme_matches_organism(enzyme: EnzymeEntry, organism: str | None) -> bool:
    normalized_organism = _normalize_source_organism(organism)
    if normalized_organism is None:
        return True
    enzyme_organism = _normalize_source_organism(enzyme.organism)
    if enzyme_organism is None:
        return False
    return _organism_names_match(enzyme_organism, normalized_organism)


def _organism_names_match(left: str, right: str) -> bool:
    left_lower = left.lower()
    right_lower = right.lower()
    left_species = _organism_species_name(left_lower)
    right_species = _organism_species_name(right_lower)
    if left_species is None or right_species is None:
        return left_lower == right_lower
    if left_lower in right_lower or right_lower in left_lower:
        return True
    if left_species == right_species:
        return True
    left_abbreviation = _organism_species_abbreviation_key(left_lower)
    right_abbreviation = _organism_species_abbreviation_key(right_lower)
    return left_abbreviation is not None and left_abbreviation == right_abbreviation


def _organism_species_name(value: str) -> str | None:
    parts = value.replace(".", "").split()
    if len(parts) < 2:
        return None
    if parts[1] in {"sp", "spp", "species", "strain"}:
        return None
    return " ".join(parts[:2])


def _organism_species_abbreviation_key(value: str) -> str | None:
    species_name = _organism_species_name(value)
    if species_name is None:
        return None
    genus, species = species_name.split()[:2]
    return f"{genus[:1]} {species}"


FAMILY_MATCH_STOP_WORDS = {
    "chain",
    "class",
    "enzyme",
    "family",
    "fragment",
    "isoform",
    "mature",
    "microbial",
    "probable",
    "protein",
    "putative",
    "subunit",
    "uncharacterized",
}


def _related_family_entries(
    db: Session,
    primary: EnzymeEntry,
    entries: list[EnzymeEntry],
) -> list[EnzymeEntry]:
    if not get_settings().use_real_science_providers:
        return entries
    family = db.get(EnzymeFamily, primary.family_id)
    family_names = [family.name if family is not None else None]
    if family is not None:
        family_names.append(FAMILY_NAMES.get(family.module))
    return [entry for entry in entries if _is_related_family_entry(primary, entry, family_names)]


def _is_related_family_entry(
    primary: EnzymeEntry,
    candidate: EnzymeEntry,
    family_names: list[str | None],
) -> bool:
    if candidate.id == primary.id:
        return True
    if _is_mock_or_seed_source(candidate.source):
        return False
    if primary.ec_number and candidate.ec_number and primary.ec_number == candidate.ec_number:
        return True

    primary_tokens = _family_match_tokens(primary.name, *family_names)
    candidate_tokens = _family_match_tokens(candidate.name)
    return bool(primary_tokens & candidate_tokens)


def _family_match_tokens(*values: str | None) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        if not value:
            continue
        for token in re.split(r"[^a-zA-Z0-9]+", value.lower()):
            normalized = _normalize_family_match_token(token)
            if normalized:
                tokens.add(normalized)
    return tokens


def _normalize_family_match_token(token: str) -> str | None:
    if len(token) < 5 or token in FAMILY_MATCH_STOP_WORDS:
        return None
    if token.endswith("ies") and len(token) > 5:
        token = f"{token[:-3]}y"
    elif token.endswith("s") and len(token) > 5:
        token = token[:-1]
    if token in FAMILY_MATCH_STOP_WORDS:
        return None
    return token


def _enzyme_scientific_rankings(
    db: Session,
    enzymes: list[EnzymeEntry],
) -> dict[str, tuple[int, float, float]]:
    enzyme_ids = [enzyme.id for enzyme in enzymes]
    if not enzyme_ids:
        return {}

    optimal_temperatures = _max_numeric_property_by_enzyme(db, enzyme_ids, "optimal_temperature")
    specific_activities = _max_numeric_property_by_enzyme(db, enzyme_ids, "specific_activity")
    return {
        enzyme.id: (
            _uniprot_review_priority(enzyme),
            optimal_temperatures.get(enzyme.id, 0.0),
            specific_activities.get(enzyme.id, 0.0),
        )
        for enzyme in enzymes
    }


def _enzyme_summaries(db: Session, enzymes: list[EnzymeEntry]) -> list[EnzymeSummary]:
    scientific_ranks = _enzyme_scientific_rankings(db, enzymes)
    record_counts = _enzyme_record_counts(db, [enzyme.id for enzyme in enzymes])
    family_names = _enzyme_family_names(db, [enzyme.family_id for enzyme in enzymes])
    return [
        EnzymeSummary(
            id=enzyme.id,
            family_id=enzyme.family_id,
            family_name=family_names.get(enzyme.family_id),
            name=enzyme.name,
            organism=enzyme.organism,
            ec_number=enzyme.ec_number,
            uniprot_id=enzyme.uniprot_id,
            pdb_id=enzyme.pdb_id,
            alphafold_id=enzyme.alphafold_id,
            source=enzyme.source,
            uniprot_reviewed=bool(scientific_ranks.get(enzyme.id, (0, 0.0, 0.0))[0]),
            optimal_temperature=_none_if_zero(scientific_ranks.get(enzyme.id, (0, 0.0, 0.0))[1]),
            specific_activity=_none_if_zero(scientific_ranks.get(enzyme.id, (0, 0.0, 0.0))[2]),
            record_counts=record_counts.get(enzyme.id, EnzymeRecordCounts()),
        )
        for enzyme in enzymes
    ]


def _enzyme_summary(db: Session, enzyme: EnzymeEntry) -> EnzymeSummary:
    return _enzyme_summaries(db, [enzyme])[0]


def _enzyme_family_names(db: Session, family_ids: list[str]) -> dict[str, str]:
    unique_family_ids = list({family_id for family_id in family_ids if family_id})
    if not unique_family_ids:
        return {}
    rows = db.execute(
        select(EnzymeFamily.id, EnzymeFamily.name).where(EnzymeFamily.id.in_(unique_family_ids))
    ).all()
    return {family_id: family_name for family_id, family_name in rows}


def _enzyme_record_counts(db: Session, enzyme_ids: list[str]) -> dict[str, EnzymeRecordCounts]:
    if not enzyme_ids:
        return {}

    counts = {enzyme_id: EnzymeRecordCounts() for enzyme_id in enzyme_ids}
    count_specs = [
        ("properties", PropertyRecord, _non_mock_text_filter(PropertyRecord.method)),
        ("kinetics", KineticRecord, _non_mock_text_filter(KineticRecord.method)),
        ("structures", StructureEntry, _non_mock_text_filter(StructureEntry.source)),
        ("expression", ExpressionRecord, None),
    ]
    for field_name, model, real_filter in count_specs:
        statement = select(model.enzyme_entry_id, func.count(model.id)).where(model.enzyme_entry_id.in_(enzyme_ids))
        if get_settings().use_real_science_providers and real_filter is not None:
            statement = statement.where(real_filter)
        rows = db.execute(statement.group_by(model.enzyme_entry_id)).all()
        for enzyme_id, count in rows:
            setattr(counts[enzyme_id], field_name, count)

    if get_settings().use_real_science_providers:
        mutation_rows = db.execute(
            select(MutationRecord.enzyme_entry_id, MutationRecord.assay_condition_summary).where(
                MutationRecord.enzyme_entry_id.in_(enzyme_ids)
            )
        ).all()
        mutation_counts: dict[str, int] = {}
        for enzyme_id, assay_condition_summary in mutation_rows:
            source = None
            if isinstance(assay_condition_summary, dict):
                source = assay_condition_summary.get("source")
            if _is_mock_like_source(source):
                continue
            mutation_counts[enzyme_id] = mutation_counts.get(enzyme_id, 0) + 1
        for enzyme_id, count in mutation_counts.items():
            counts[enzyme_id].mutations = count
    else:
        rows = db.execute(
            select(MutationRecord.enzyme_entry_id, func.count(MutationRecord.id))
            .where(MutationRecord.enzyme_entry_id.in_(enzyme_ids))
            .group_by(MutationRecord.enzyme_entry_id)
        ).all()
        for enzyme_id, count in rows:
            counts[enzyme_id].mutations = count
    return counts


def _none_if_zero(value: float) -> float | None:
    return value if value != 0.0 else None


def _uniprot_review_priority(enzyme: EnzymeEntry) -> int:
    if not enzyme.uniprot_id:
        return 0
    if enzyme.uniprot_reviewed:
        return 1
    return 0


def _max_numeric_property_by_enzyme(
    db: Session,
    enzyme_ids: list[str],
    property_type: str,
) -> dict[str, float]:
    rows = db.scalars(
        select(PropertyRecord).where(
            PropertyRecord.enzyme_entry_id.in_(enzyme_ids),
            PropertyRecord.property_type == property_type,
            *(
                [_non_mock_text_filter(PropertyRecord.method)]
                if get_settings().use_real_science_providers
                else []
            ),
        )
    ).all()
    values: dict[str, float] = {}
    for row in rows:
        value = _parse_numeric_property(row.value_standardized) or _parse_numeric_property(row.value_original)
        if value is None:
            continue
        values[row.enzyme_entry_id] = max(values.get(row.enzyme_entry_id, float("-inf")), value)
    return values


def _parse_numeric_property(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    if not match:
        return None
    return float(match.group(0))


def _is_mock_or_seed_source(source: str | None) -> bool:
    value = (source or "").lower()
    return value == "seed" or value.endswith("_mock")


def _is_mock_like_source(source: str | None) -> bool:
    value = (source or "").lower()
    return value == "seed" or value.endswith("_mock") or "_mock" in value


def _non_mock_text_filter(column):
    return or_(column.is_(None), ~func.lower(column).contains("_mock"))


def _extract_pdb_metadata(text: str, *, file_name: str) -> PdbDiscoveryMetadata:
    title_parts: list[str] = []
    compnd_parts: list[str] = []
    source_parts: list[str] = []
    identifiers = extract_structure_database_identifiers(text, file_name=file_name)

    for line in text.splitlines():
        record = line[0:6].strip().upper()
        if record == "TITLE":
            title_parts.append(line[10:].strip())
        elif record == "COMPND":
            compnd_parts.append(line[10:].strip())
        elif record == "SOURCE":
            source_parts.append(line[10:].strip())

    compnd_text = " ".join(compnd_parts)
    source_text = " ".join(source_parts)
    return PdbDiscoveryMetadata(
        pdb_id=identifiers.get("pdb_id"),
        title=" ".join(title_parts) or None,
        enzyme_name=_extract_pdb_semicolon_field(compnd_text, "MOLECULE"),
        organism=_extract_pdb_semicolon_field(source_text, "ORGANISM_SCIENTIFIC"),
        uniprot_id=identifiers.get("uniprot_id"),
        alphafold_id=identifiers.get("alphafold_id"),
    )


def _extract_pdb_semicolon_field(text: str, field_name: str) -> str | None:
    match = re.search(rf"{re.escape(field_name)}\s*:\s*([^;]+)", text, flags=re.IGNORECASE)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def _discovery_chains(chain_summary: dict) -> list[PdbDiscoveryChain]:
    chains = chain_summary.get("chains", [])
    if not isinstance(chains, list):
        return []
    return [
        PdbDiscoveryChain(
            chain_id=str(chain.get("chain_id") or "-"),
            sequence=str(chain.get("sequence") or ""),
            residue_count=int(chain.get("residue_count") or 0),
            mapping_quality=str(chain.get("mapping_quality") or "") or None,
        )
        for chain in chains
        if isinstance(chain, dict) and str(chain.get("sequence") or "")
    ]


def _identifier_pdb_discovery_hits(
    db: Session,
    *,
    metadata: PdbDiscoveryMetadata,
    query_sequence: str,
    module: EnzymeModule | None = None,
) -> list[PdbDiscoveryHit]:
    hits_by_enzyme_id: dict[str, PdbDiscoveryHit] = {}

    def add_hit(enzyme: EnzymeEntry, evidence: str) -> None:
        hit = PdbDiscoveryHit(
            enzyme=enzyme,
            identity=1.0,
            coverage=1.0,
            aligned_length=len(query_sequence),
            evidence=[evidence, "local_database"],
            confidence="exact",
        )
        existing_hit = hits_by_enzyme_id.get(enzyme.id)
        if existing_hit is None or _pdb_discovery_hit_score(hit) > _pdb_discovery_hit_score(existing_hit):
            hits_by_enzyme_id[enzyme.id] = hit

    if metadata.pdb_id:
        pdb_id = metadata.pdb_id.upper()
        enzyme_query = (
            select(EnzymeEntry)
            .join(EnzymeFamily, EnzymeFamily.id == EnzymeEntry.family_id)
            .where(EnzymeEntry.pdb_id == pdb_id)
        )
        if module is not None:
            enzyme_query = enzyme_query.where(EnzymeFamily.module == module)
        enzymes = db.scalars(enzyme_query).all()
        for enzyme in enzymes:
            add_hit(enzyme, "pdb_id")

        structure_query = (
            select(EnzymeEntry)
            .join(EnzymeFamily, EnzymeFamily.id == EnzymeEntry.family_id)
            .join(StructureEntry, StructureEntry.enzyme_entry_id == EnzymeEntry.id)
            .where(StructureEntry.pdb_id == pdb_id)
        )
        if module is not None:
            structure_query = structure_query.where(EnzymeFamily.module == module)
        structure_enzymes = db.scalars(structure_query).all()
        for enzyme in structure_enzymes:
            add_hit(enzyme, "pdb_id")

    if metadata.alphafold_id:
        alphafold_ids = alphafold_identifier_candidates(metadata.alphafold_id)
        enzyme_query = (
            select(EnzymeEntry)
            .join(EnzymeFamily, EnzymeFamily.id == EnzymeEntry.family_id)
            .where(EnzymeEntry.alphafold_id.in_(alphafold_ids))
        )
        if module is not None:
            enzyme_query = enzyme_query.where(EnzymeFamily.module == module)
        enzymes = db.scalars(enzyme_query).all()
        for enzyme in enzymes:
            add_hit(enzyme, "alphafold_id")

        structure_query = (
            select(EnzymeEntry, StructureEntry)
            .join(EnzymeFamily, EnzymeFamily.id == EnzymeEntry.family_id)
            .join(StructureEntry, StructureEntry.enzyme_entry_id == EnzymeEntry.id)
        )
        if module is not None:
            structure_query = structure_query.where(EnzymeFamily.module == module)
        structure_rows = db.execute(structure_query).all()
        for enzyme, structure in structure_rows:
            identifiers = structure.chain_summary.get("identifiers") if structure.chain_summary else None
            if not isinstance(identifiers, dict):
                continue
            structure_alphafold_id = identifiers.get("alphafold_id")
            if isinstance(structure_alphafold_id, str) and structure_alphafold_id in alphafold_ids:
                add_hit(enzyme, "alphafold_id")

    if metadata.uniprot_id:
        uniprot_id = metadata.uniprot_id.upper()
        enzyme_query = (
            select(EnzymeEntry)
            .join(EnzymeFamily, EnzymeFamily.id == EnzymeEntry.family_id)
            .where(func.upper(EnzymeEntry.uniprot_id) == uniprot_id)
        )
        if module is not None:
            enzyme_query = enzyme_query.where(EnzymeFamily.module == module)
        enzymes = db.scalars(enzyme_query).all()
        for enzyme in enzymes:
            add_hit(enzyme, "uniprot_id")

        structure_query = (
            select(EnzymeEntry, StructureEntry)
            .join(EnzymeFamily, EnzymeFamily.id == EnzymeEntry.family_id)
            .join(StructureEntry, StructureEntry.enzyme_entry_id == EnzymeEntry.id)
        )
        if module is not None:
            structure_query = structure_query.where(EnzymeFamily.module == module)
        structure_rows = db.execute(structure_query).all()
        for enzyme, structure in structure_rows:
            identifiers = structure.chain_summary.get("identifiers") if structure.chain_summary else None
            if not isinstance(identifiers, dict):
                continue
            structure_uniprot_id = identifiers.get("uniprot_id")
            if isinstance(structure_uniprot_id, str) and structure_uniprot_id.upper() == uniprot_id:
                add_hit(enzyme, "uniprot_id")

    return list(hits_by_enzyme_id.values())


def _sequence_pdb_discovery_hits(
    db: Session,
    *,
    query_sequence: str,
    module: EnzymeModule | None = None,
) -> list[PdbDiscoveryHit]:
    query = (
        select(EnzymeEntry, ProteinSequence)
        .join(EnzymeFamily, EnzymeFamily.id == EnzymeEntry.family_id)
        .join(ProteinSequence, ProteinSequence.enzyme_entry_id == EnzymeEntry.id)
    )
    if module is not None:
        query = query.where(EnzymeFamily.module == module)
    rows = db.execute(query).all()

    hits_by_enzyme_id: dict[str, PdbDiscoveryHit] = {}
    for enzyme, protein_sequence in rows:
        candidate_sequence = protein_sequence.mature_sequence or protein_sequence.sequence
        similarity = calculate_ungapped_similarity(query_sequence, candidate_sequence)
        if similarity.identity < 0.4 or similarity.coverage < 0.7:
            continue
        confidence = "high" if similarity.identity >= 0.8 and similarity.coverage >= 0.8 else "medium"
        hit = PdbDiscoveryHit(
            enzyme=enzyme,
            identity=round(similarity.identity, 4),
            coverage=round(similarity.coverage, 4),
            aligned_length=similarity.aligned_length,
            evidence=["sequence_similarity", "local_database"],
            confidence=confidence,
        )
        existing_hit = hits_by_enzyme_id.get(enzyme.id)
        if existing_hit is None or _pdb_discovery_hit_score(hit) > _pdb_discovery_hit_score(existing_hit):
            hits_by_enzyme_id[enzyme.id] = hit

    hits = sorted(
        hits_by_enzyme_id.values(),
        key=_pdb_discovery_hit_score,
        reverse=True,
    )
    return hits


def _local_pdb_discovery_hits(
    db: Session,
    *,
    metadata: PdbDiscoveryMetadata,
    query_sequence: str,
    module: EnzymeModule | None = None,
    limit: int = 12,
) -> list[PdbDiscoveryHit]:
    hits_by_enzyme_id: dict[str, PdbDiscoveryHit] = {}
    for hit in [
        *_identifier_pdb_discovery_hits(
            db,
            metadata=metadata,
            query_sequence=query_sequence,
            module=module,
        ),
        *_sequence_pdb_discovery_hits(db, query_sequence=query_sequence, module=module),
    ]:
        existing_hit = hits_by_enzyme_id.get(hit.enzyme.id)
        if existing_hit is None:
            hits_by_enzyme_id[hit.enzyme.id] = hit
        else:
            hits_by_enzyme_id[hit.enzyme.id] = _merge_pdb_discovery_hits(existing_hit, hit)

    hits = sorted(
        hits_by_enzyme_id.values(),
        key=_pdb_discovery_hit_rank(db, hits_by_enzyme_id.values()),
        reverse=True,
    )
    return hits[:limit]


def _merge_pdb_discovery_hits(existing: PdbDiscoveryHit, incoming: PdbDiscoveryHit) -> PdbDiscoveryHit:
    sequence_hit = _best_sequence_pdb_discovery_hit(existing, incoming)
    metric_hit = sequence_hit or max([existing, incoming], key=_pdb_discovery_hit_score)
    confidence = max(
        [existing.confidence, incoming.confidence],
        key=lambda value: {"exact": 3, "high": 2, "medium": 1}.get(value, 0),
    )
    evidence = [
        evidence
        for evidence in ["pdb_id", "alphafold_id", "uniprot_id", "sequence_similarity", "local_database"]
        if evidence in {*existing.evidence, *incoming.evidence}
    ]
    return PdbDiscoveryHit(
        enzyme=metric_hit.enzyme,
        identity=metric_hit.identity,
        coverage=metric_hit.coverage,
        aligned_length=metric_hit.aligned_length,
        evidence=evidence,
        confidence=confidence,
    )


def _best_sequence_pdb_discovery_hit(*hits: PdbDiscoveryHit) -> PdbDiscoveryHit | None:
    sequence_hits = [hit for hit in hits if "sequence_similarity" in hit.evidence]
    if not sequence_hits:
        return None
    return max(sequence_hits, key=lambda hit: (hit.identity, hit.coverage, hit.aligned_length))


def _pdb_discovery_hit_score(hit: PdbDiscoveryHit) -> tuple[int, float, float, int]:
    confidence_rank = {"exact": 3, "high": 2, "medium": 1}.get(hit.confidence, 0)
    return (confidence_rank, hit.identity, hit.coverage, hit.aligned_length)


def _pdb_discovery_hit_rank(
    db: Session,
    hits: Iterable[PdbDiscoveryHit],
):
    scientific_ranks = _enzyme_scientific_rankings(db, [hit.enzyme for hit in hits])

    def rank(hit: PdbDiscoveryHit) -> tuple[int, float, float, int, tuple[int, float, float]]:
        return (*_pdb_discovery_hit_score(hit), scientific_ranks.get(hit.enzyme.id, (0, 0.0, 0.0)))

    return rank


def _enriched_pdb_discovery_hits(db: Session, hits: list[PdbDiscoveryHit]) -> list[PdbDiscoveryHit]:
    summaries = {summary.id: summary for summary in _enzyme_summaries(db, [hit.enzyme for hit in hits])}
    return [
        PdbDiscoveryHit(
            enzyme=summaries[hit.enzyme.id],
            identity=hit.identity,
            coverage=hit.coverage,
            aligned_length=hit.aligned_length,
            evidence=hit.evidence,
            confidence=hit.confidence,
        )
        for hit in hits
    ]


@router.post("/search", response_model=EnzymeSearchResponse)
def search_enzymes(
    request: EnzymeSearchRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EnzymeSearchResponse:
    settings = get_settings()
    resolved = resolve_query(request.query)
    source_organism = _normalize_source_organism(request.organism)
    cache_normalized_query = _search_cache_normalized_query(resolved.normalized_query, source_organism)
    module = _module_for_search(db, request, resolved.module_hint, user)
    family = _ensure_family(db, module)
    cache_status = "miss_refreshed"
    retrieval_provenance: dict | None = None

    enzyme: EnzymeEntry | None = None
    fresh_cache = find_fresh_search_cache(
        db,
        normalized_query=cache_normalized_query,
        query_kind=resolved.kind.value,
        module=module,
    )
    if fresh_cache and fresh_cache.enzyme_entry_id:
        cached_enzyme = db.get(EnzymeEntry, fresh_cache.enzyme_entry_id)
        if (
            cached_enzyme is not None
            and not (
                settings.use_real_science_providers
                and _is_mock_or_seed_source(cached_enzyme.source)
            )
        ):
            enzyme = cached_enzyme
            cache_status = "hit"
            if isinstance(fresh_cache.payload_json, dict):
                cached_provenance = fresh_cache.payload_json.get("retrieval_provenance")
                if isinstance(cached_provenance, dict):
                    retrieval_provenance = cached_provenance

    if resolved.kind == QueryKind.UNIPROT:
        if enzyme is None:
            enzyme = find_fresh_uniprot_hit(db, resolved.normalized_query)
            if enzyme is not None:
                cache_status = "hit"
        if enzyme is None:
            stale_entry = db.scalar(
                select(EnzymeEntry).where(EnzymeEntry.uniprot_id == resolved.normalized_query)
            )
            if stale_entry is not None and not is_fresh(stale_entry.last_refreshed_at):
                enzyme = stale_entry
                enzyme.last_refreshed_at = datetime.utcnow()
                cache_status = "stale_refreshed"

    if enzyme is None:
        exact_match = find_level_one_exact_match(
            db,
            query_kind=resolved.kind,
            normalized_query=resolved.normalized_query,
        )
        if (
            exact_match is not None
            and not (
                settings.use_real_science_providers
                and _is_mock_or_seed_source(exact_match.source)
            )
        ):
            enzyme = exact_match
            if is_fresh(enzyme.last_refreshed_at):
                cache_status = "hit"
            else:
                enzyme.last_refreshed_at = datetime.utcnow()
                cache_status = "stale_refreshed"

    if enzyme is None and resolved.kind == QueryKind.KEYWORD:
        keyword_match = _find_local_keyword_match(
            db,
            module=module,
            query=request.query,
            organism=source_organism,
        )
        if keyword_match is not None:
            enzyme = keyword_match
            if is_fresh(enzyme.last_refreshed_at):
                cache_status = "hit"
            else:
                enzyme.last_refreshed_at = datetime.utcnow()
                cache_status = "stale_refreshed"

    if enzyme is None and resolved.kind == QueryKind.SEQUENCE:
        similarity_match = find_level_two_similarity_match(
            db,
            module=module,
            query_sequence=resolved.normalized_query,
        )
        if similarity_match is not None:
            enzyme = similarity_match.enzyme
            if is_fresh(enzyme.last_refreshed_at):
                cache_status = "hit"
            else:
                enzyme.last_refreshed_at = datetime.utcnow()
                cache_status = "stale_refreshed"

    if enzyme is None and resolved.kind == QueryKind.PDB:
        metadata, rcsb_source, rcsb_provenance = _fetch_rcsb_metadata(resolved.normalized_query)
        enzyme = _create_enzyme_from_rcsb_metadata(
            db,
            family=family,
            metadata=metadata,
            source=rcsb_source,
            provenance=rcsb_provenance,
        )
        cache_status = "miss_refreshed"

    if enzyme is None and resolved.kind in {QueryKind.UNIPROT, QueryKind.ALPHAFOLD, QueryKind.EC, QueryKind.KEYWORD}:
        uniprot_family: EnzymeFamily | None = None
        for entry, fasta, source, entry_provenance in _fetch_uniprot_entries(
            resolved,
            limit=request.result_limit,
            organism=source_organism,
            include_details=(not settings.use_real_science_providers)
            or resolved.kind in {QueryKind.UNIPROT, QueryKind.ALPHAFOLD},
        ):
            if uniprot_family is None:
                uniprot_family = _ensure_uniprot_entry_family(db, module, entry)
            created_enzyme = _upsert_enzyme_from_uniprot_entry(
                db,
                family=uniprot_family,
                entry=entry,
                fasta=fasta,
                source=source,
            )
            if enzyme is None:
                retrieval_provenance = entry_provenance
                enzyme = created_enzyme
        if enzyme is not None and not get_settings().use_real_science_providers:
            _save_literature_for_enzyme(
                db,
                enzyme,
                skip_mock=False,
            )
            cache_status = "miss_refreshed"

    stale_cache = find_search_cache(
        db,
        normalized_query=cache_normalized_query,
        query_kind=resolved.kind.value,
        module=module,
    )
    if enzyme is None and stale_cache is not None and not is_fresh(stale_cache.last_refreshed_at):
        cache_status = "stale_refreshed"
    elif enzyme is not None and stale_cache is not None and not is_fresh(stale_cache.last_refreshed_at):
        cache_status = "stale_refreshed"

    if enzyme is None and settings.use_real_science_providers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No real enzyme record found for this query; no seed or mock record was created.",
        )

    if enzyme is not None and resolved.kind in {QueryKind.EC, QueryKind.KEYWORD} and settings.use_real_science_providers:
        _backfill_sparse_uniprot_search_results(
            db,
            primary_enzyme=enzyme,
            resolved_query=resolved,
            query=request.query,
            module=module,
            organism=source_organism,
            limit=request.result_limit,
        )

    seed_name = (
        "Microbial transglutaminase"
        if module == EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE
        else "Anthraquinone glycosyltransferase"
    )
    if resolved.kind == QueryKind.UNIPROT:
        seed_name = f"{seed_name} {resolved.normalized_query}"

    if enzyme is None:
        enzyme = _find_seed_entry(
            db=db,
            family_id=family.id,
            name=seed_name,
            source="seed",
            uniprot_id=resolved.normalized_query if resolved.kind == QueryKind.UNIPROT else None,
        )

    if enzyme is None:
        enzyme = EnzymeEntry(
            family_id=family.id,
            name=seed_name,
            organism="Streptomyces mobaraensis"
            if module == EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE
            else None,
            ec_number="2.3.2.13"
            if module == EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE
            else None,
            uniprot_id=resolved.normalized_query if resolved.kind == QueryKind.UNIPROT else None,
            source="seed",
            last_refreshed_at=datetime.utcnow(),
        )
        db.add(enzyme)
        db.flush()

    if not settings.use_real_science_providers:
        _ensure_protein_sequence(db, enzyme, module)
        db.flush()
        _save_external_enzyme_data(
            db,
            enzyme,
            skip_mock=False,
        )
        db.flush()
    refresh_modules = stale_data_modules(db, enzyme.id)

    job = AnalysisJob(
        project_id=request.project_id,
        enzyme_entry_id=enzyme.id,
        job_type="homolog_collection",
        status=JobStatus.QUEUED,
        parameters_json={
            "query": request.query,
            "normalized_query": resolved.normalized_query,
            "query_kind": resolved.kind.value,
            "module": module.value,
            **({"organism": source_organism} if source_organism else {}),
            "refresh_modules": refresh_modules,
            **({"retrieval_provenance": retrieval_provenance} if retrieval_provenance else {}),
        },
        created_by=user.id,
    )
    db.add(job)
    db.flush()
    _upsert_search_cache(
        db,
        query=request.query,
        normalized_query=cache_normalized_query,
        query_kind=resolved.kind.value,
        module=module,
        enzyme=enzyme,
        job=job,
        retrieval_provenance=retrieval_provenance,
    )
    db.commit()
    db.refresh(enzyme)
    db.refresh(job)
    run_homology_collection.delay(job.id)
    matches = _search_result_matches(
        db,
        primary_enzyme=enzyme,
        query=request.query,
        organism=source_organism,
        limit=request.result_limit,
    )

    return EnzymeSearchResponse(
        enzyme=_enzyme_summary(db, enzyme),
        matches=_enzyme_summaries(db, matches),
        job_id=job.id,
        cache_status=cache_status,
        query_kind=resolved.kind.value,
        module=module,
        retrieval_provenance=retrieval_provenance,
    )


@router.post("/discover-pdb", response_model=PdbDiscoveryResponse)
async def discover_enzyme_from_pdb(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> PdbDiscoveryResponse:
    file_name = file.filename or "structure.pdb"
    if not file_name.lower().endswith((".pdb", ".cif", ".mmcif")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="only .pdb, .cif, and .mmcif structure files are supported",
        )
    content = await file.read()
    try:
        text = content.decode("utf-8")
        parsed = parse_structure_text(text, file_name=file_name)
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="structure file must be UTF-8 text",
        ) from exc
    except StructureParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    chains = _discovery_chains(parsed.chain_summary)
    if not chains:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="uploaded structure does not contain a protein sequence",
        )
    query_chain = max(chains, key=lambda chain: chain.residue_count)
    metadata = _extract_pdb_metadata(text, file_name=file_name)
    hits = _local_pdb_discovery_hits(
        db,
        metadata=metadata,
        query_sequence=query_chain.sequence,
    )
    return PdbDiscoveryResponse(
        file_name=file_name,
        metadata=metadata,
        structure_type=parsed.structure_type,
        complex_state=parsed.complex_state,
        chains=chains,
        query_chain_id=query_chain.chain_id,
        query_sequence=query_chain.sequence,
        hits=_enriched_pdb_discovery_hits(db, hits),
    )


@router.post("/{enzyme_id}/real-data/refresh", response_model=EnzymeRealDataRefreshResponse)
def refresh_enzyme_real_data(
    enzyme_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EnzymeRealDataRefreshResponse:
    enzyme = db.get(EnzymeEntry, enzyme_id)
    if enzyme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="enzyme not found")

    created = {"references": 0, "properties": 0, "kinetics": 0, "mutations": 0, "structures": 0}
    sources: list[str] = []
    warnings: list[str] = []
    _refresh_real_data_for_enzyme(db, enzyme, created=created, sources=sources, warnings=warnings)

    db.commit()
    db.refresh(enzyme)

    return EnzymeRealDataRefreshResponse(
        enzyme=_enzyme_summary(db, enzyme),
        created=created,
        sources=_unique_strings(sources),
        warnings=warnings,
    )


@router.post("/{enzyme_id}/real-data/refresh-job", response_model=JobResponse)
def enqueue_enzyme_real_data_refresh(
    enzyme_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AnalysisJob:
    return _enqueue_real_data_refresh_job(db, enzyme_id=enzyme_id, user=user, scope="enzyme")


@router.post("/{enzyme_id}/family-real-data/refresh", response_model=EnzymeRealDataRefreshResponse)
def refresh_enzyme_family_real_data(
    enzyme_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EnzymeRealDataRefreshResponse:
    enzyme = db.get(EnzymeEntry, enzyme_id)
    if enzyme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="enzyme not found")

    created = {"references": 0, "properties": 0, "kinetics": 0, "mutations": 0, "structures": 0}
    sources: list[str] = []
    warnings: list[str] = []
    family_entries = list(
        db.scalars(select(EnzymeEntry).where(EnzymeEntry.family_id == enzyme.family_id))
    )
    family_entries = _related_family_entries(db, enzyme, family_entries)
    for family_enzyme in family_entries:
        _refresh_real_data_for_enzyme(db, family_enzyme, created=created, sources=sources, warnings=warnings)

    db.commit()
    db.refresh(enzyme)

    return EnzymeRealDataRefreshResponse(
        enzyme=_enzyme_summary(db, enzyme),
        created=created,
        sources=_unique_strings(sources),
        warnings=warnings,
    )


@router.post("/{enzyme_id}/family-real-data/refresh-job", response_model=JobResponse)
def enqueue_enzyme_family_real_data_refresh(
    enzyme_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> AnalysisJob:
    return _enqueue_real_data_refresh_job(db, enzyme_id=enzyme_id, user=user, scope="family")


def _enqueue_real_data_refresh_job(db: Session, *, enzyme_id: str, user: User, scope: str) -> AnalysisJob:
    enzyme = db.get(EnzymeEntry, enzyme_id)
    if enzyme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="enzyme not found")

    job = AnalysisJob(
        project_id=None,
        enzyme_entry_id=enzyme.id,
        job_type="real_data_refresh",
        status=JobStatus.QUEUED,
        parameters_json={"scope": scope},
        created_by=user.id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    run_real_data_refresh.delay(job.id)
    return job


def _refresh_real_data_for_enzyme(
    db: Session,
    enzyme: EnzymeEntry,
    *,
    created: dict[str, int],
    sources: list[str],
    warnings: list[str],
) -> None:
    reference_count, reference_sources, reference_warnings = _save_literature_for_enzyme(
        db,
        enzyme,
        require_real=True,
    )
    created["references"] += reference_count
    sources.extend(reference_sources)
    warnings.extend(reference_warnings)

    data_counts, data_sources, data_warnings = _save_external_enzyme_data(
        db,
        enzyme,
        require_real=True,
    )
    for key, count in data_counts.items():
        created[key] = created.get(key, 0) + count
    sources.extend(data_sources)
    warnings.extend(data_warnings)

    structure_count, structure_sources, structure_warnings = _save_alphafold_structure_for_enzyme(
        db,
        enzyme,
        require_real=True,
    )
    created["structures"] = created.get("structures", 0) + structure_count
    sources.extend(structure_sources)
    warnings.extend(structure_warnings)

    if enzyme.pdb_id:
        rcsb_structure_count, rcsb_sources, rcsb_warnings = _save_rcsb_structure_for_enzyme(
            db,
            enzyme,
            pdb_id=enzyme.pdb_id,
            require_real=True,
        )
        created["structures"] = created.get("structures", 0) + rcsb_structure_count
        sources.extend(rcsb_sources)
        warnings.extend(rcsb_warnings)

    enzyme.last_refreshed_at = datetime.utcnow()


@router.get("/{enzyme_id}", response_model=EnzymeSummary)
def get_enzyme(
    enzyme_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EnzymeSummary:
    enzyme = db.get(EnzymeEntry, enzyme_id)
    if enzyme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="enzyme not found")
    return _enzyme_summary(db, enzyme)


@router.get("/{enzyme_id}/family-entries", response_model=list[EnzymeSummary])
def list_enzyme_family_entries(
    enzyme_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[EnzymeSummary]:
    enzyme = db.get(EnzymeEntry, enzyme_id)
    if enzyme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="enzyme not found")
    entries = list(
        db.scalars(
            select(EnzymeEntry)
            .where(EnzymeEntry.family_id == enzyme.family_id)
            .order_by(EnzymeEntry.name.asc(), EnzymeEntry.organism.asc())
        )
    )
    entries = _related_family_entries(db, enzyme, entries)
    return _enzyme_summaries(db, entries)


def _unique_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
