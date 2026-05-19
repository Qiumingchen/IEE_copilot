import hashlib
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import current_user
from app.db.models import (
    AnalysisJob,
    EnzymeEntry,
    EnzymeFamily,
    EnzymeModule,
    JobStatus,
    KineticRecord,
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
from app.external.uniprot import UniProtEntry, get_uniprot_client, parse_fasta_sequence
from app.schemas.enzyme import EnzymeSearchRequest, EnzymeSearchResponse, EnzymeSummary
from app.services.cache import (
    find_fresh_search_cache,
    find_fresh_uniprot_hit,
    find_search_cache,
    is_fresh,
    stale_data_modules,
)
from app.services.exact_matching import find_level_one_exact_match
from app.services.query_resolver import QueryKind, resolve_query
from app.services.similarity_matching import find_level_two_similarity_match
from worker.jobs import run_placeholder_analysis


router = APIRouter(prefix="/enzymes", tags=["enzymes"])

SEED_MTGASE_SEQUENCE = (
    "AEAKLLNDTLLAIGGQDPVKAQVLSVSGGDAKQAGVYAVTQGNGDKVTVEQSNNGTVVQSPY"
    "GAGDTVTYNGQTVTTVNAGYTVTVDKNGKTYVTLTDDKNGKTYVSVTGGDAKQAGVYAVTQG"
)

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
    return SEED_MTGASE_SEQUENCE


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
        return

    sequence = _seed_sequence_for_module(module)
    db.add(
        ProteinSequence(
            enzyme_entry_id=enzyme.id,
            sequence=sequence,
            mature_sequence=sequence
            if module == EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE
            else None,
            is_engineering_target=True,
            source="seed",
            checksum=hashlib.sha256(sequence.encode("utf-8")).hexdigest(),
        )
    )


def _fetch_uniprot_entry(resolved_query) -> tuple[UniProtEntry | None, str | None, str | None]:
    client = get_uniprot_client()
    if resolved_query.kind == QueryKind.UNIPROT:
        entry = client.fetch_entry(resolved_query.normalized_query)
        return entry, client.fetch_fasta(entry.accession), getattr(client, "source", "uniprot")

    hits = []
    if resolved_query.kind == QueryKind.EC:
        hits = client.search_by_ec(resolved_query.normalized_query)
    elif resolved_query.kind == QueryKind.KEYWORD:
        hits = client.search_by_keyword(resolved_query.normalized_query)

    if not hits:
        return None, None, None

    entry = client.fetch_entry(hits[0].accession)
    return entry, client.fetch_fasta(entry.accession), getattr(client, "source", "uniprot")


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
        db.add(
            ProteinSequence(
                enzyme_entry_id=enzyme.id,
                sequence=sequence,
                mature_sequence=sequence,
                is_engineering_target=True,
                source=source or "uniprot",
                checksum=hashlib.sha256(sequence.encode("utf-8")).hexdigest(),
            )
        )

    alphafold_id = entry.cross_references.get("AlphaFoldDB")
    if alphafold_id:
        alphafold_client = get_alphafold_client()
        model = alphafold_client.fetch_model_by_uniprot(entry.accession)
        _create_alphafold_structure(
            db,
            enzyme=enzyme,
            model=model,
            source=getattr(alphafold_client, "source", "alphafold"),
        )
    return enzyme


def _save_literature_for_enzyme(db: Session, enzyme: EnzymeEntry) -> None:
    client = get_literature_client()
    for metadata in client.search_by_enzyme_name(enzyme.name):
        create_literature_reference(db, metadata)


def _save_external_enzyme_data(db: Session, enzyme: EnzymeEntry) -> None:
    client = get_enzyme_data_client()
    query = enzyme.name

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
                method=f"{parameter.source}: {parameter.evidence}" if parameter.evidence else parameter.source,
            )
        )

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


def _create_alphafold_structure(
    db: Session,
    *,
    enzyme: EnzymeEntry,
    model: AlphaFoldModelMetadata,
    source: str,
) -> StructureEntry:
    now = datetime.utcnow()
    structure = StructureEntry(
        enzyme_entry_id=enzyme.id,
        structure_type="alphafold",
        complex_state="predicted",
        pdb_id=None,
        chain_summary={
            "model_id": model.model_id,
            "uniprot_id": model.uniprot_id,
            "structure_url": model.structure_url,
            "confidence_url": model.confidence_url,
            "confidence_summary": model.confidence_summary,
        },
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
    db.add(
        StructureEntry(
            enzyme_entry_id=enzyme.id,
            structure_type="pdb",
            complex_state="unknown",
            pdb_id=metadata.pdb_id,
            chain_summary=metadata.chain_summary,
            ligand_summary=metadata.ligand_summary,
            source=source or "rcsb",
            created_at=now,
            updated_at=now,
        )
    )
    return enzyme


def _search_cache_payload(enzyme: EnzymeEntry, job: AnalysisJob) -> dict[str, str]:
    return {
        "enzyme_entry_id": enzyme.id,
        "job_id": job.id,
    }


def _upsert_search_cache(
    db: Session,
    *,
    query: str,
    normalized_query: str,
    query_kind: str,
    module: EnzymeModule,
    enzyme: EnzymeEntry,
    job: AnalysisJob,
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
                payload_json=_search_cache_payload(enzyme, job),
                source=enzyme.source,
                last_refreshed_at=now,
                updated_at=now,
            )
        )
        return

    record.query = query
    record.enzyme_entry_id = enzyme.id
    record.payload_json = _search_cache_payload(enzyme, job)
    record.source = enzyme.source
    record.last_refreshed_at = now
    record.updated_at = now


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

    enzyme: EnzymeEntry | None = None
    fresh_cache = find_fresh_search_cache(
        db,
        normalized_query=resolved.normalized_query,
        query_kind=resolved.kind.value,
        module=module,
    )
    if fresh_cache and fresh_cache.enzyme_entry_id:
        cached_enzyme = db.get(EnzymeEntry, fresh_cache.enzyme_entry_id)
        if cached_enzyme is not None:
            enzyme = cached_enzyme
            cache_status = "hit"

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
        if exact_match is not None:
            enzyme = exact_match
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
        rcsb_client = get_rcsb_client()
        metadata = rcsb_client.fetch_structure_metadata(resolved.normalized_query)
        enzyme = _create_enzyme_from_rcsb_metadata(
            db,
            family=family,
            metadata=metadata,
            source=getattr(rcsb_client, "source", "rcsb"),
        )
        cache_status = "miss_refreshed"

    if enzyme is None and resolved.kind in {QueryKind.UNIPROT, QueryKind.EC, QueryKind.KEYWORD}:
        entry, fasta, source = _fetch_uniprot_entry(resolved)
        if entry is not None:
            enzyme = _create_enzyme_from_uniprot_entry(
                db,
                family=family,
                entry=entry,
                fasta=fasta,
                source=source,
            )
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
        job_type="family_profile_placeholder",
        status=JobStatus.QUEUED,
        parameters_json={
            "query": request.query,
            "normalized_query": resolved.normalized_query,
            "query_kind": resolved.kind.value,
            "module": module.value,
            "refresh_modules": refresh_modules,
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
    )
    db.commit()
    db.refresh(enzyme)
    db.refresh(job)
    run_placeholder_analysis.delay(job.id)

    return EnzymeSearchResponse(
        enzyme=enzyme,
        job_id=job.id,
        cache_status=cache_status,
        query_kind=resolved.kind.value,
        module=module,
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
