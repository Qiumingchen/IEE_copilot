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
    Project,
    ProteinSequence,
    User,
)
from app.db.session import get_db
from app.schemas.enzyme import EnzymeSearchRequest, EnzymeSearchResponse, EnzymeSummary
from app.services.cache import find_fresh_uniprot_hit, is_fresh
from app.services.query_resolver import QueryKind, resolve_query


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
    if resolved.kind == QueryKind.UNIPROT:
        enzyme = find_fresh_uniprot_hit(db, resolved.normalized_query)
        if enzyme is not None:
            cache_status = "hit"
        else:
            stale_entry = db.scalar(
                select(EnzymeEntry).where(EnzymeEntry.uniprot_id == resolved.normalized_query)
            )
            if stale_entry is not None and not is_fresh(stale_entry.last_refreshed_at):
                enzyme = stale_entry
                enzyme.last_refreshed_at = datetime.utcnow()
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
        },
        created_by=user.id,
    )
    db.add(job)
    db.commit()
    db.refresh(enzyme)
    db.refresh(job)

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
