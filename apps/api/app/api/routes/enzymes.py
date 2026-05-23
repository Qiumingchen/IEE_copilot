import hashlib
import re
from dataclasses import replace
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
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
from app.external.alphafold import (
    AlphaFoldModelMetadata,
    MockAlphaFoldClient,
    get_alphafold_client,
)
from app.external.enzyme_data import get_enzyme_data_client
from app.external.literature import (
    LiteratureMetadata,
    MockLiteratureClient,
    create_literature_reference,
    get_literature_client,
)
from app.external.rcsb import MockRcsbClient, RcsbStructureMetadata, get_rcsb_client
from app.external.uniprot import (
    MockUniProtClient,
    P81453_FULL_SEQUENCE,
    P81453_MATURE_SEQUENCE,
    UniProtEntry,
    get_uniprot_client,
    parse_fasta_sequence,
)
from app.schemas.enzyme import (
    EnzymeSearchRequest,
    EnzymeSearchResponse,
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


def _fetch_uniprot_entry(resolved_query) -> tuple[UniProtEntry | None, str | None, str | None, dict | None]:
    client = get_uniprot_client()
    try:
        entry, fasta, source = _fetch_uniprot_entry_with_client(resolved_query, client)
        return entry, fasta, source, _uniprot_retrieval_provenance(entry, source)
    except (httpx.HTTPError, ValueError) as exc:
        if getattr(client, "source", "uniprot").endswith("_mock"):
            raise
        fallback_client = MockUniProtClient()
        entry, fasta, source = _fetch_uniprot_entry_with_client(resolved_query, fallback_client)
        return (
            entry,
            fasta,
            source,
            build_fallback_provenance(
                provider=source,
                warning=f"UniProt provider failed; fallback mock data used. {exc}",
            )
            if entry is not None
            else None,
        )


def _fetch_uniprot_entry_with_client(resolved_query, client) -> tuple[UniProtEntry | None, str | None, str | None]:
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
        _create_alphafold_structure(
            db,
            enzyme=enzyme,
            model=model,
            source=alphafold_source,
            provenance=alphafold_provenance,
        )
    return enzyme


def _fetch_alphafold_model(uniprot_id: str) -> tuple[AlphaFoldModelMetadata, str, dict | None]:
    client = get_alphafold_client()
    source = getattr(client, "source", "alphafold")
    try:
        model = client.fetch_model_by_uniprot(uniprot_id)
        return model, source, None
    except (httpx.HTTPError, ValueError) as exc:
        if source.endswith("_mock"):
            raise
        fallback_client = MockAlphaFoldClient()
        fallback_source = getattr(fallback_client, "source", "alphafold_mock")
        model = fallback_client.fetch_model_by_uniprot(uniprot_id)
        return (
            model,
            fallback_source,
            build_fallback_provenance(
                provider=fallback_source,
                warning=f"AlphaFold provider failed; fallback mock model used. {exc}",
                extra={"source_url": model.structure_url},
            ),
        )


def _save_literature_for_enzyme(db: Session, enzyme: EnzymeEntry) -> None:
    client = get_literature_client()
    try:
        hits = client.search_by_enzyme_name(enzyme.name)
    except (httpx.HTTPError, ValueError) as exc:
        if getattr(client, "source", "crossref").endswith("_mock"):
            raise
        fallback_client = MockLiteratureClient()
        hits = [
            _with_literature_fallback_provenance(metadata, exc)
            for metadata in fallback_client.search_by_enzyme_name(enzyme.name)
        ]

    for metadata in hits:
        create_literature_reference(db, metadata)


def _with_literature_fallback_provenance(metadata: LiteratureMetadata, exc: Exception) -> LiteratureMetadata:
    metadata_json = dict(metadata.metadata)
    metadata_json["provenance"] = build_fallback_provenance(
        provider=metadata.source,
        warning=f"Literature provider failed; fallback mock metadata used. {exc}",
    )
    return replace(metadata, metadata=metadata_json)


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
                method=parameter.source,
                evidence_text=parameter.evidence,
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
        fallback_client = MockRcsbClient()
        fallback_source = getattr(fallback_client, "source", "rcsb_mock")
        metadata = fallback_client.fetch_structure_metadata(pdb_id)
        return (
            metadata,
            fallback_source,
            build_fallback_provenance(
                provider=fallback_source,
                warning=f"RCSB provider failed; fallback mock structure used. {exc}",
                extra={"source_url": f"https://www.rcsb.org/structure/{metadata.pdb_id}"},
            ),
        )


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

    def score(candidate: EnzymeEntry) -> tuple[int, int]:
        if candidate.id == primary_enzyme.id:
            return (10_000, 0)
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
        return (exact_score + term_score, 1)

    ranked = sorted(candidates, key=score, reverse=True)
    matches: list[EnzymeEntry] = []
    seen: set[str] = set()
    for candidate in [primary_enzyme, *ranked]:
        if candidate.id in seen:
            continue
        candidate_score, _ = score(candidate)
        if candidate.id != primary_enzyme.id and candidate_score <= 0:
            continue
        matches.append(candidate)
        seen.add(candidate.id)
        if len(matches) >= limit:
            break
    return matches


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
    module: EnzymeModule,
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
        enzymes = db.scalars(
            select(EnzymeEntry)
            .join(EnzymeFamily, EnzymeFamily.id == EnzymeEntry.family_id)
            .where(EnzymeFamily.module == module)
            .where(EnzymeEntry.pdb_id == pdb_id)
        ).all()
        for enzyme in enzymes:
            add_hit(enzyme, "pdb_id")

        structure_enzymes = db.scalars(
            select(EnzymeEntry)
            .join(EnzymeFamily, EnzymeFamily.id == EnzymeEntry.family_id)
            .join(StructureEntry, StructureEntry.enzyme_entry_id == EnzymeEntry.id)
            .where(EnzymeFamily.module == module)
            .where(StructureEntry.pdb_id == pdb_id)
        ).all()
        for enzyme in structure_enzymes:
            add_hit(enzyme, "pdb_id")

    if metadata.alphafold_id:
        alphafold_ids = alphafold_identifier_candidates(metadata.alphafold_id)
        enzymes = db.scalars(
            select(EnzymeEntry)
            .join(EnzymeFamily, EnzymeFamily.id == EnzymeEntry.family_id)
            .where(EnzymeFamily.module == module)
            .where(EnzymeEntry.alphafold_id.in_(alphafold_ids))
        ).all()
        for enzyme in enzymes:
            add_hit(enzyme, "alphafold_id")

        structure_rows = db.execute(
            select(EnzymeEntry, StructureEntry)
            .join(EnzymeFamily, EnzymeFamily.id == EnzymeEntry.family_id)
            .join(StructureEntry, StructureEntry.enzyme_entry_id == EnzymeEntry.id)
            .where(EnzymeFamily.module == module)
        ).all()
        for enzyme, structure in structure_rows:
            identifiers = structure.chain_summary.get("identifiers") if structure.chain_summary else None
            if not isinstance(identifiers, dict):
                continue
            structure_alphafold_id = identifiers.get("alphafold_id")
            if isinstance(structure_alphafold_id, str) and structure_alphafold_id in alphafold_ids:
                add_hit(enzyme, "alphafold_id")

    if metadata.uniprot_id:
        uniprot_id = metadata.uniprot_id.upper()
        enzymes = db.scalars(
            select(EnzymeEntry)
            .join(EnzymeFamily, EnzymeFamily.id == EnzymeEntry.family_id)
            .where(EnzymeFamily.module == module)
            .where(func.upper(EnzymeEntry.uniprot_id) == uniprot_id)
        ).all()
        for enzyme in enzymes:
            add_hit(enzyme, "uniprot_id")

        structure_rows = db.execute(
            select(EnzymeEntry, StructureEntry)
            .join(EnzymeFamily, EnzymeFamily.id == EnzymeEntry.family_id)
            .join(StructureEntry, StructureEntry.enzyme_entry_id == EnzymeEntry.id)
            .where(EnzymeFamily.module == module)
        ).all()
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
    module: EnzymeModule,
) -> list[PdbDiscoveryHit]:
    rows = db.execute(
        select(EnzymeEntry, ProteinSequence)
        .join(EnzymeFamily, EnzymeFamily.id == EnzymeEntry.family_id)
        .join(ProteinSequence, ProteinSequence.enzyme_entry_id == EnzymeEntry.id)
        .where(EnzymeFamily.module == module)
    ).all()

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
    module: EnzymeModule,
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
        key=_pdb_discovery_hit_score,
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
        if cached_enzyme is not None:
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
        entry, fasta, source, entry_provenance = _fetch_uniprot_entry(resolved)
        if entry is not None:
            retrieval_provenance = entry_provenance
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
    matches = _search_result_matches(db, primary_enzyme=enzyme, query=request.query)

    return EnzymeSearchResponse(
        enzyme=enzyme,
        matches=matches,
        job_id=job.id,
        cache_status=cache_status,
        query_kind=resolved.kind.value,
        module=module,
    )


@router.post("/discover-pdb", response_model=PdbDiscoveryResponse)
async def discover_enzyme_from_pdb(
    file: UploadFile = File(...),
    module: EnzymeModule = Form(EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE),
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
    return PdbDiscoveryResponse(
        file_name=file_name,
        metadata=metadata,
        structure_type=parsed.structure_type,
        complex_state=parsed.complex_state,
        chains=chains,
        query_chain_id=query_chain.chain_id,
        query_sequence=query_chain.sequence,
        hits=_local_pdb_discovery_hits(
            db,
            metadata=metadata,
            query_sequence=query_chain.sequence,
            module=module,
        ),
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
