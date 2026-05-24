import hashlib
import re
from collections.abc import Iterable
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.auth import current_user
from app.core.config import get_settings
from app.db.models import (
    AnalysisJob,
    EnzymeEntry,
    EnzymeFamily,
    EnzymeModule,
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
from app.external.literature import create_literature_reference, get_literature_client
from app.external.rcsb import RcsbStructureMetadata, get_rcsb_client
from app.external.uniprot import (
    P81453_FULL_SEQUENCE,
    P81453_MATURE_SEQUENCE,
    UniProtEntry,
    get_uniprot_client,
    parse_fasta_sequence,
)
from app.schemas.enzyme import (
    EnzymeSearchRequest,
    EnzymeSearchResponse,
    EnzymeRealDataRefreshResponse,
    EnzymeSummary,
    PdbDiscoveryChain,
    PdbDiscoveryHit,
    PdbDiscoveryMetadata,
    PdbDiscoveryResponse,
)
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
from worker.jobs import run_placeholder_analysis


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
    family = db.scalar(select(EnzymeFamily).where(EnzymeFamily.module == module))
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
) -> list[tuple[UniProtEntry, str | None, str | None, dict | None]]:
    client = get_uniprot_client()
    try:
        entries = _fetch_uniprot_entries_with_client(resolved_query, client, limit=limit)
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
) -> list[tuple[UniProtEntry, str | None, str | None]]:
    source = getattr(client, "source", "uniprot")
    if resolved_query.kind == QueryKind.UNIPROT:
        entry = client.fetch_entry(resolved_query.normalized_query)
        return [(entry, client.fetch_fasta(entry.accession), source)]

    hits = []
    if resolved_query.kind == QueryKind.EC:
        hits = client.search_by_ec(resolved_query.normalized_query, size=limit)
    elif resolved_query.kind == QueryKind.KEYWORD:
        hits = client.search_by_keyword(resolved_query.normalized_query, size=limit)

    entries: list[tuple[UniProtEntry, str | None, str | None]] = []
    seen_accessions: set[str] = set()
    for hit in hits[:limit]:
        if hit.accession in seen_accessions:
            continue
        seen_accessions.add(hit.accession)
        entry = client.fetch_entry(hit.accession)
        entries.append((entry, client.fetch_fasta(entry.accession), source))
    return entries


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
    enzyme = EnzymeEntry(
        family_id=family.id,
        name=entry.protein_name,
        organism=entry.organism,
        ec_number=entry.ec_number,
        uniprot_id=entry.accession,
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
) -> tuple[int, list[str], list[str]]:
    client = get_literature_client()
    source = getattr(client, "source", "literature")
    if require_real:
        _raise_if_mock_provider(source, "literature")
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
) -> tuple[dict[str, int], list[str], list[str]]:
    client = get_enzyme_data_client()
    source = getattr(client, "source", "enzyme_data")
    if require_real:
        _raise_if_mock_provider(source, "enzyme data")
    query = enzyme.name
    created = {"properties": 0, "kinetics": 0, "mutations": 0}

    property_data = [
        *client.fetch_opt_temperature(query),
        *client.fetch_opt_pH(query),
    ]
    for datum in property_data:
        existing = db.scalar(
            select(PropertyRecord).where(
                PropertyRecord.enzyme_entry_id == enzyme.id,
                PropertyRecord.property_type == datum.property_type,
                PropertyRecord.value_original == datum.value_original,
                PropertyRecord.substrate == datum.substrate,
            )
        )
        if existing is not None:
            continue
        db.add(
            PropertyRecord(
                enzyme_entry_id=enzyme.id,
                property_type=datum.property_type,
                value_original=datum.value_original,
                unit_original=datum.unit_original,
                substrate=datum.substrate,
                assay_temperature=datum.assay_temperature,
                assay_pH=datum.assay_pH,
                method=datum.source,
                evidence_text=datum.evidence,
            )
        )
        created["properties"] += 1

    for parameter in client.fetch_kinetic_parameters(query):
        existing = db.scalar(
            select(KineticRecord).where(
                KineticRecord.enzyme_entry_id == enzyme.id,
                KineticRecord.substrate == parameter.substrate,
                KineticRecord.km == parameter.km,
                KineticRecord.kcat == parameter.kcat,
                KineticRecord.kcat_km == parameter.kcat_km,
            )
        )
        if existing is not None:
            continue
        db.add(
            KineticRecord(
                enzyme_entry_id=enzyme.id,
                substrate=parameter.substrate,
                km=parameter.km,
                kcat=parameter.kcat,
                kcat_km=parameter.kcat_km,
                unit_original=parameter.unit_original,
                assay_temperature=parameter.assay_temperature,
                assay_pH=parameter.assay_pH,
                method=parameter.source,
                evidence_text=parameter.evidence,
            )
        )
        created["kinetics"] += 1

    for mutant in client.fetch_mutants(query):
        existing = db.scalar(
            select(MutationRecord).where(
                MutationRecord.enzyme_entry_id == enzyme.id,
                MutationRecord.mutation_string == mutant.mutation_string,
            )
        )
        if existing is not None:
            continue
        db.add(
            MutationRecord(
                enzyme_entry_id=enzyme.id,
                mutation_string=mutant.mutation_string,
                effect_summary=mutant.effect_summary,
                property_delta=mutant.property_delta,
                substrate=mutant.substrate,
                assay_condition_summary={
                    "source": mutant.source,
                    "evidence": mutant.evidence,
                    "organism": mutant.organism,
                },
            )
        )
        created["mutations"] += 1
    return created, [source], []


def _literature_reference_exists(db: Session, doi: str | None, pubmed_id: str | None) -> bool:
    if doi:
        return db.scalar(select(LiteratureReference).where(LiteratureReference.doi == doi)) is not None
    if pubmed_id:
        return db.scalar(select(LiteratureReference).where(LiteratureReference.pubmed_id == pubmed_id)) is not None
    return False


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
        primary_score = 20 if candidate.id == primary_enzyme.id else 0
        return (primary_score + exact_score + term_score, 1, 0)

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


def _find_local_keyword_match(
    db: Session,
    *,
    module: EnzymeModule,
    query: str,
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
    return [
        EnzymeSummary(
            id=enzyme.id,
            family_id=enzyme.family_id,
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
        )
        for enzyme in enzymes
    ]


def _enzyme_summary(db: Session, enzyme: EnzymeEntry) -> EnzymeSummary:
    return _enzyme_summaries(db, [enzyme])[0]


def _none_if_zero(value: float) -> float | None:
    return value if value != 0.0 else None


def _uniprot_review_priority(enzyme: EnzymeEntry) -> int:
    source = (enzyme.source or "").lower()
    if not enzyme.uniprot_id:
        return 0
    if source == "uniprot" or "reviewed" in source or "swiss" in source:
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
    resolved = resolve_query(request.query)
    module = _module_for_search(db, request, resolved.module_hint, user)
    family = _ensure_family(db, module)
    cache_status = "miss_refreshed"
    retrieval_provenance: dict | None = None

    enzyme: EnzymeEntry | None = None
    fresh_cache = find_fresh_search_cache(
        db,
        normalized_query=resolved.normalized_query,
        query_kind=resolved.kind.value,
        module=module,
    )
    if fresh_cache and fresh_cache.enzyme_entry_id:
        cached_enzyme = db.get(EnzymeEntry, fresh_cache.enzyme_entry_id)
        if (
            cached_enzyme is not None
            and not (
                get_settings().use_real_science_providers
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
                get_settings().use_real_science_providers
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
        keyword_match = _find_local_keyword_match(db, module=module, query=request.query)
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

    if enzyme is None and resolved.kind in {QueryKind.UNIPROT, QueryKind.EC, QueryKind.KEYWORD}:
        for entry, fasta, source, entry_provenance in _fetch_uniprot_entries(
            resolved,
            limit=request.result_limit,
        ):
            created_enzyme = _upsert_enzyme_from_uniprot_entry(
                db,
                family=family,
                entry=entry,
                fasta=fasta,
                source=source,
            )
            if enzyme is None:
                retrieval_provenance = entry_provenance
                enzyme = created_enzyme
        if enzyme is not None:
            _save_literature_for_enzyme(db, enzyme)
            cache_status = "miss_refreshed"

    stale_cache = find_search_cache(
        db,
        normalized_query=resolved.normalized_query,
        query_kind=resolved.kind.value,
        module=module,
    )
    if enzyme is None and stale_cache is not None and not is_fresh(stale_cache.last_refreshed_at):
        cache_status = "stale_refreshed"
    elif enzyme is not None and stale_cache is not None and not is_fresh(stale_cache.last_refreshed_at):
        cache_status = "stale_refreshed"

    if enzyme is None and get_settings().use_real_science_providers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No real enzyme record found for this query; no seed or mock record was created.",
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

    _ensure_protein_sequence(db, enzyme, module)
    db.flush()
    _save_external_enzyme_data(db, enzyme)
    db.flush()
    refresh_modules = stale_data_modules(db, enzyme.id)

    job = AnalysisJob(
        project_id=request.project_id,
        enzyme_entry_id=enzyme.id,
        job_type="family_profile_summary",
        status=JobStatus.QUEUED,
        parameters_json={
            "query": request.query,
            "normalized_query": resolved.normalized_query,
            "query_kind": resolved.kind.value,
            "module": module.value,
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
        normalized_query=resolved.normalized_query,
        query_kind=resolved.kind.value,
        module=module,
        enzyme=enzyme,
        job=job,
        retrieval_provenance=retrieval_provenance,
    )
    db.commit()
    db.refresh(enzyme)
    db.refresh(job)
    run_placeholder_analysis.delay(job.id)
    matches = _search_result_matches(
        db,
        primary_enzyme=enzyme,
        query=request.query,
        limit=request.result_limit,
    )

    return EnzymeSearchResponse(
        enzyme=_enzyme_summary(db, enzyme),
        matches=_enzyme_summaries(db, matches),
        job_id=job.id,
        cache_status=cache_status,
        query_kind=resolved.kind.value,
        module=module,
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

    reference_count, reference_sources, reference_warnings = _save_literature_for_enzyme(
        db,
        enzyme,
        require_real=True,
    )
    created["references"] = reference_count
    sources.extend(reference_sources)
    warnings.extend(reference_warnings)

    data_counts, data_sources, data_warnings = _save_external_enzyme_data(
        db,
        enzyme,
        require_real=True,
    )
    created.update(data_counts)
    sources.extend(data_sources)
    warnings.extend(data_warnings)

    enzyme.last_refreshed_at = datetime.utcnow()
    db.commit()
    db.refresh(enzyme)

    return EnzymeRealDataRefreshResponse(
        enzyme=_enzyme_summary(db, enzyme),
        created=created,
        sources=_unique_strings(sources),
        warnings=warnings,
    )


@router.get("/{enzyme_id}", response_model=EnzymeSummary)
def get_enzyme(
    enzyme_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EnzymeEntry:
    enzyme = db.get(EnzymeEntry, enzyme_id)
    if enzyme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="enzyme not found")
    return enzyme


def _unique_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
