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


@dataclass
class CuratedEvidencePreviewRecord:
    row_number: int
    record_type: str
    summary: str
    reference_key: str | None = None
    reference_match_mode: str | None = None
    evidence_text: str | None = None


@dataclass(frozen=True)
class ReferenceIdentity:
    key: str | None
    match_mode: str | None


@dataclass
class CuratedEvidencePreviewError:
    row_number: int
    field: str
    message: str


@dataclass
class CuratedEvidencePreviewResult:
    fields: list[str]
    row_count: int
    record_counts: dict[str, int]
    records: list[CuratedEvidencePreviewRecord]
    errors: list[CuratedEvidencePreviewError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


def preview_curated_evidence(csv_text: str) -> CuratedEvidencePreviewResult:
    rows, fields = _parse_rows_with_fields(csv_text)
    record_counts = {"properties": 0, "kinetics": 0, "mutations": 0}
    records: list[CuratedEvidencePreviewRecord] = []
    errors: list[CuratedEvidencePreviewError] = []

    for index, row in enumerate(rows, start=2):
        record_type = _value(row, "record_type").lower()
        if record_type not in {"property", "kinetic", "mutation"}:
            errors.append(
                CuratedEvidencePreviewError(
                    row_number=index,
                    field="record_type",
                    message="unsupported record_type",
                )
            )
            continue

        if record_type == "property":
            row_errors = _validate_property_row(row, index)
            errors.extend(row_errors)
            if not row_errors:
                record_counts["properties"] += 1
        elif record_type == "kinetic":
            record_counts["kinetics"] += 1
        else:
            row_errors = _validate_mutation_row(row, index)
            errors.extend(row_errors)
            if not row_errors:
                record_counts["mutations"] += 1

        if not any(error.row_number == index for error in errors):
            reference_identity = _reference_identity(row)
            records.append(
                CuratedEvidencePreviewRecord(
                    row_number=index,
                    record_type=record_type,
                    summary=_summarize_row(record_type, row),
                    reference_key=reference_identity.key,
                    reference_match_mode=reference_identity.match_mode,
                    evidence_text=_value(row, "evidence_text") or None,
                )
            )

    return CuratedEvidencePreviewResult(
        fields=fields,
        row_count=len(rows),
        record_counts=record_counts,
        records=records,
        errors=errors,
    )


def import_curated_evidence(
    db: Session,
    *,
    enzyme: EnzymeEntry,
    csv_text: str,
) -> CuratedEvidenceImportResult:
    preview = preview_curated_evidence(csv_text)
    if not preview.valid:
        raise CuratedEvidenceImportError(_format_preview_errors(preview.errors))

    rows = _parse_rows(csv_text)
    result = CuratedEvidenceImportResult()
    reference_ids: set[str] = set()

    for index, row in enumerate(rows, start=2):
        record_type = _validated_record_type(row, index)

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
    rows, _fields = _parse_rows_with_fields(csv_text)
    return rows


def _parse_rows_with_fields(csv_text: str) -> tuple[list[dict[str, str]], list[str]]:
    if not csv_text.strip():
        raise CuratedEvidenceImportError("csv_text is required")
    reader = csv.DictReader(StringIO(csv_text))
    if not reader.fieldnames or "record_type" not in reader.fieldnames:
        raise CuratedEvidenceImportError("record_type column is required")
    rows = [dict(row) for row in reader]
    if not rows:
        raise CuratedEvidenceImportError("at least one evidence row is required")
    return rows, list(reader.fieldnames)


def _validated_record_type(row: dict[str, str], row_number: int) -> str:
    record_type = _value(row, "record_type").lower()
    if record_type not in {"property", "kinetic", "mutation"}:
        raise CuratedEvidenceImportError(f"row {row_number}: unsupported record_type")
    return record_type


def _validate_property_row(row: dict[str, str], row_number: int) -> list[CuratedEvidencePreviewError]:
    errors: list[CuratedEvidencePreviewError] = []
    for field_name in ("property_type", "value_original"):
        if not _value(row, field_name):
            errors.append(
                CuratedEvidencePreviewError(
                    row_number=row_number,
                    field=field_name,
                    message=f"{field_name} is required",
                )
            )
    return errors


def _validate_mutation_row(row: dict[str, str], row_number: int) -> list[CuratedEvidencePreviewError]:
    mutation_string = _value(row, "mutation_string")
    if not mutation_string:
        return [
            CuratedEvidencePreviewError(
                row_number=row_number,
                field="mutation_string",
                message="mutation_string is required",
            )
        ]
    try:
        parse_mutation_string(mutation_string)
    except ValueError:
        return [
            CuratedEvidencePreviewError(
                row_number=row_number,
                field="mutation_string",
                message=f"invalid mutation format: {mutation_string}",
            )
        ]
    return []


def _format_preview_errors(errors: list[CuratedEvidencePreviewError]) -> str:
    return "; ".join(
        f"row {error.row_number} {error.field}: {error.message}" for error in errors
    )


def _get_or_create_reference(db: Session, row: dict[str, str]) -> LiteratureReference | None:
    doi = _normalize_doi(_value(row, "doi"))
    pubmed_id = _normalize_pubmed_id(_value(row, "pubmed_id"))
    title = _value(row, "reference_title")
    year = _int_or_none(_value(row, "year"))
    source = _value(row, "source") or "curated_literature"
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
    if title:
        normalized_title = _normalize_reference_title(title)
        candidates = db.scalars(
            select(LiteratureReference).where(
                LiteratureReference.year == year,
                LiteratureReference.source == source,
            )
        )
        for candidate in candidates:
            if _normalize_reference_title(candidate.title) == normalized_title:
                return candidate

    if not any([doi, pubmed_id, title]):
        return None

    reference = LiteratureReference(
        title=title or doi or pubmed_id or "Curated literature reference",
        authors=_value(row, "authors") or None,
        journal=_value(row, "journal") or None,
        year=year,
        doi=doi or None,
        pubmed_id=pubmed_id or None,
        source=source,
        metadata_json={
            "provenance": {
                "provider": source,
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


def _summarize_row(record_type: str, row: dict[str, str]) -> str:
    if record_type == "property":
        parts = [
            _value(row, "property_type"),
            _value(row, "value_original"),
            _value(row, "unit_original"),
        ]
        return " ".join(part for part in parts if part)
    if record_type == "kinetic":
        parts = [
            _value(row, "substrate") or "kinetic",
            _value(row, "km") and f"Km {_value(row, 'km')}",
            _value(row, "kcat") and f"kcat {_value(row, 'kcat')}",
            _value(row, "kcat_km") and f"kcat/Km {_value(row, 'kcat_km')}",
        ]
        return " ".join(part for part in parts if part)
    return _value(row, "mutation_string")


def _reference_key(row: dict[str, str]) -> str | None:
    return _reference_identity(row).key


def _reference_identity(row: dict[str, str]) -> ReferenceIdentity:
    doi = _normalize_doi(_value(row, "doi"))
    if doi:
        return ReferenceIdentity(key=doi, match_mode="doi")

    pubmed_id = _normalize_pubmed_id(_value(row, "pubmed_id"))
    if pubmed_id:
        return ReferenceIdentity(key=pubmed_id, match_mode="pubmed_id")

    title = _normalize_reference_title(_value(row, "reference_title"))
    year = str(_int_or_none(_value(row, "year")) or "")
    source = _value(row, "source") or "curated_literature"
    if title:
        return ReferenceIdentity(
            key=":".join(part for part in [title, year, source] if part),
            match_mode="title_year_source",
        )
    return ReferenceIdentity(key=None, match_mode=None)


def _normalize_doi(value: str) -> str:
    doi = value.strip().strip("'\"").lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi.removeprefix(prefix)
    return doi.strip()


def _normalize_pubmed_id(value: str) -> str:
    normalized = value.strip().strip("'\"").lower()
    for prefix in ("pmid:", "pmid", "pubmed:"):
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix)
    return "".join(character for character in normalized if character.isdigit())


def _normalize_reference_title(value: str | None) -> str:
    return " ".join((value or "").strip().strip("'\"").lower().split())


def _required(row: dict[str, str], key: str) -> str:
    value = _value(row, key)
    if not value:
        raise CuratedEvidenceImportError(f"{key} is required")
    return value


def _required_for_row(row: dict[str, str], key: str, row_number: int) -> str:
    value = _value(row, key)
    if not value:
        raise CuratedEvidenceImportError(f"row {row_number}: {key} is required")
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
