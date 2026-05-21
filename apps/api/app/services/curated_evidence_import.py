import csv
from dataclasses import dataclass, field
from io import StringIO
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    CurationStatus,
    EnzymeEntry,
    KineticRecord,
    LiteratureReference,
    MutationRecord,
    PropertyRecord,
    Visibility,
)
from app.services.mutations import parse_mutation_string
from app.services.property_standardization import standardize_property_value


class CuratedEvidenceImportError(ValueError):
    pass


@dataclass
class CuratedEvidenceImportResult:
    created: dict[str, int] = field(
        default_factory=lambda: {"properties": 0, "kinetics": 0, "mutations": 0}
    )
    reference_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def import_curated_evidence(
    db: Session,
    *,
    enzyme: EnzymeEntry,
    csv_text: str,
) -> CuratedEvidenceImportResult:
    rows = _parse_rows(csv_text)
    result = CuratedEvidenceImportResult()
    reference_ids: set[str] = set()

    for index, row in enumerate(rows, start=2):
        record_type = _value(row, "record_type").lower()
        if record_type not in {"property", "kinetic", "mutation"}:
            raise CuratedEvidenceImportError(f"row {index}: unsupported record_type")

        reference = _get_or_create_reference(db, row)
        if reference is not None:
            reference_ids.add(reference.id)

        if record_type == "property":
            _create_property(db, enzyme, row, reference)
            result.created["properties"] += 1
        elif record_type == "kinetic":
            _create_kinetic(db, enzyme, row, reference)
            result.created["kinetics"] += 1
        else:
            _create_mutation(db, enzyme, row, reference)
            result.created["mutations"] += 1

    result.reference_ids = sorted(reference_ids)
    return result


def _parse_rows(csv_text: str) -> list[dict[str, str]]:
    if not csv_text.strip():
        raise CuratedEvidenceImportError("csv_text is required")
    reader = csv.DictReader(StringIO(csv_text))
    if not reader.fieldnames or "record_type" not in reader.fieldnames:
        raise CuratedEvidenceImportError("record_type column is required")
    rows = [dict(row) for row in reader]
    if not rows:
        raise CuratedEvidenceImportError("at least one evidence row is required")
    return rows


def _get_or_create_reference(db: Session, row: dict[str, str]) -> LiteratureReference | None:
    doi = _value(row, "doi")
    pubmed_id = _value(row, "pubmed_id")
    if doi:
        existing = db.scalar(select(LiteratureReference).where(LiteratureReference.doi == doi))
        if existing is not None:
            return existing
    if pubmed_id:
        existing = db.scalar(
            select(LiteratureReference).where(LiteratureReference.pubmed_id == pubmed_id)
        )
        if existing is not None:
            return existing

    title = _value(row, "reference_title")
    if not any([doi, pubmed_id, title]):
        return None

    reference = LiteratureReference(
        title=title or doi or pubmed_id or "Curated literature reference",
        authors=_value(row, "authors") or None,
        journal=_value(row, "journal") or None,
        year=_int_or_none(_value(row, "year")),
        doi=doi or None,
        pubmed_id=pubmed_id or None,
        source=_value(row, "source") or "curated_literature",
        metadata_json={
            "provenance": {
                "provider": _value(row, "source") or "curated_literature",
                "mode": "curated",
            }
        },
    )
    db.add(reference)
    db.flush()
    return reference


def _create_property(
    db: Session,
    enzyme: EnzymeEntry,
    row: dict[str, str],
    reference: LiteratureReference | None,
) -> None:
    property_type = _required(row, "property_type")
    value_original = _required(row, "value_original")
    unit_original = _value(row, "unit_original") or None
    standardized = standardize_property_value(property_type, value_original, unit_original)
    db.add(
        PropertyRecord(
            enzyme_entry_id=enzyme.id,
            property_type=property_type,
            value_original=value_original,
            unit_original=unit_original,
            value_standardized=standardized.value_standardized,
            unit_standardized=standardized.unit_standardized,
            standardization_status=standardized.standardization_status,
            substrate=_value(row, "substrate") or None,
            assay_temperature=_value(row, "assay_temperature") or None,
            assay_pH=_value(row, "assay_pH") or None,
            buffer=_value(row, "buffer") or None,
            method=_value(row, "method") or None,
            reference_id=reference.id if reference else None,
            evidence_text=_value(row, "evidence_text") or None,
            visibility=Visibility.PUBLIC,
            curation_status=CurationStatus.APPROVED,
        )
    )


def _create_kinetic(
    db: Session,
    enzyme: EnzymeEntry,
    row: dict[str, str],
    reference: LiteratureReference | None,
) -> None:
    db.add(
        KineticRecord(
            enzyme_entry_id=enzyme.id,
            substrate=_value(row, "substrate") or None,
            km=_value(row, "km") or None,
            kcat=_value(row, "kcat") or None,
            kcat_km=_value(row, "kcat_km") or None,
            unit_original=_value(row, "unit_original") or None,
            assay_temperature=_value(row, "assay_temperature") or None,
            assay_pH=_value(row, "assay_pH") or None,
            method=_value(row, "method") or None,
            reference_id=reference.id if reference else None,
            visibility=Visibility.PUBLIC,
            curation_status=CurationStatus.APPROVED,
        )
    )


def _create_mutation(
    db: Session,
    enzyme: EnzymeEntry,
    row: dict[str, str],
    reference: LiteratureReference | None,
) -> None:
    mutation_string = _required(row, "mutation_string")
    parsed_mutations = parse_mutation_string(mutation_string)
    db.add(
        MutationRecord(
            enzyme_entry_id=enzyme.id,
            mutation_string="/".join(
                f"{mutation.wildtype}{mutation.position}{mutation.mutant}"
                for mutation in parsed_mutations
            ),
            mutation_positions=[mutation.model_dump() for mutation in parsed_mutations],
            effect_summary=_value(row, "effect_summary") or None,
            property_delta=_property_delta(row),
            substrate=_value(row, "substrate") or None,
            assay_condition_summary={
                key: value
                for key, value in {
                    "source": _value(row, "source") or "curated_literature",
                    "evidence": _value(row, "evidence_text") or None,
                    "assay_temperature": _value(row, "assay_temperature") or None,
                    "assay_pH": _value(row, "assay_pH") or None,
                    "method": _value(row, "method") or None,
                }.items()
                if value
            },
            reference_id=reference.id if reference else None,
            is_user_uploaded=False,
            visibility=Visibility.PUBLIC,
            curation_status=CurationStatus.APPROVED,
        )
    )


def _property_delta(row: dict[str, str]) -> dict[str, Any] | None:
    key = _value(row, "property_delta_key")
    value = _value(row, "property_delta_value")
    return {key: value} if key and value else None


def _required(row: dict[str, str], key: str) -> str:
    value = _value(row, key)
    if not value:
        raise CuratedEvidenceImportError(f"{key} is required")
    return value


def _value(row: dict[str, str], key: str) -> str:
    value = row.get(key)
    return value.strip().strip("'\"") if value is not None else ""


def _int_or_none(value: str) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None
