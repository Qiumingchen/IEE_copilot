from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.db.models import EnzymeEntry, PropertyRecord


@dataclass(frozen=True)
class PropertyRankingItem:
    rank: int
    enzyme_entry_id: str
    enzyme_name: str
    property_record_id: str
    value_original: str
    unit_original: str | None
    value_standardized: str | None
    unit_standardized: str | None
    standardization_status: str
    substrate: str | None
    assay_temperature: str | None
    assay_pH: str | None
    method: str | None
    reference_id: str | None


@dataclass(frozen=True)
class PropertyRankingGroup:
    condition_key: dict[str, Any]
    items: list[PropertyRankingItem]


@dataclass(frozen=True)
class PropertyRankingResult:
    property_type: str
    ranking_mode: str
    items: list[PropertyRankingItem]
    groups: list[PropertyRankingGroup]
    comparison_warnings: list[str]


def build_property_ranking(
    records: list[PropertyRecord],
    enzymes_by_id: dict[str, EnzymeEntry],
    *,
    property_type: str,
    ranking_mode: str = "reported_value",
) -> PropertyRankingResult:
    matching_records = [record for record in records if record.property_type == property_type]
    rankable_records = [
        record for record in matching_records if _ranking_value(record) is not None
    ]
    if ranking_mode == "condition_grouped":
        return _build_condition_grouped_ranking(
            rankable_records,
            enzymes_by_id,
            property_type,
            _data_quality_warnings(property_type, matching_records, rankable_records),
        )
    return PropertyRankingResult(
        property_type=property_type,
        ranking_mode="reported_value",
        items=_rank_records(rankable_records, enzymes_by_id),
        groups=[],
        comparison_warnings=[
            "reported_value_ranking preserves original assay conditions",
            "cross-condition comparisons should be interpreted cautiously",
            *_data_quality_warnings(property_type, matching_records, rankable_records),
        ],
    )


def _build_condition_grouped_ranking(
    records: list[PropertyRecord],
    enzymes_by_id: dict[str, EnzymeEntry],
    property_type: str,
    data_quality_warnings: list[str],
) -> PropertyRankingResult:
    grouped: dict[tuple[Any, ...], list[PropertyRecord]] = defaultdict(list)
    for record in records:
        grouped[_condition_tuple(record)].append(record)

    groups = [
        PropertyRankingGroup(
            condition_key=_condition_key(records_in_group[0]),
            items=_rank_records(records_in_group, enzymes_by_id),
        )
        for _, records_in_group in sorted(grouped.items(), key=lambda item: item[0])
    ]
    return PropertyRankingResult(
        property_type=property_type,
        ranking_mode="condition_grouped",
        items=[],
        groups=groups,
        comparison_warnings=[
            "condition_grouped ranking does not compare records across groups",
            *data_quality_warnings,
        ],
    )


def _rank_records(
    records: list[PropertyRecord],
    enzymes_by_id: dict[str, EnzymeEntry],
) -> list[PropertyRankingItem]:
    ordered = sorted(
        records,
        key=lambda record: (
            -(_ranking_value(record) or Decimal("0")),
            record.enzyme_entry_id,
            record.id,
        ),
    )
    return [
        PropertyRankingItem(
            rank=index + 1,
            enzyme_entry_id=record.enzyme_entry_id,
            enzyme_name=enzymes_by_id[record.enzyme_entry_id].name,
            property_record_id=record.id,
            value_original=record.value_original,
            unit_original=record.unit_original,
            value_standardized=record.value_standardized,
            unit_standardized=record.unit_standardized,
            standardization_status=record.standardization_status,
            substrate=record.substrate,
            assay_temperature=record.assay_temperature,
            assay_pH=record.assay_pH,
            method=record.method,
            reference_id=record.reference_id,
        )
        for index, record in enumerate(ordered)
    ]


def _ranking_value(record: PropertyRecord) -> Decimal | None:
    raw_value = record.value_standardized or record.value_original
    try:
        return Decimal(raw_value)
    except (InvalidOperation, TypeError):
        return None


def _data_quality_warnings(
    property_type: str,
    matching_records: list[PropertyRecord],
    rankable_records: list[PropertyRecord],
) -> list[str]:
    warnings: list[str] = []
    excluded_count = len(matching_records) - len(rankable_records)
    if excluded_count:
        warnings.append(
            f"{excluded_count} {property_type} {_plural(excluded_count, 'record was', 'records were')} excluded because "
            f"{_plural(excluded_count, 'its value is', 'their values are')} not numeric"
        )

    original_value_count = sum(1 for record in rankable_records if not record.value_standardized)
    if original_value_count:
        warnings.append(
            f"{original_value_count} ranked {_plural(original_value_count, 'record uses', 'records use')} original "
            "reported values because standardization is unavailable"
        )
    return warnings


def _plural(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def _condition_tuple(record: PropertyRecord) -> tuple[Any, ...]:
    key = _condition_key(record)
    return tuple(key[item] or "" for item in ("reference_id", "substrate", "assay_temperature", "assay_pH", "unit", "method"))


def _condition_key(record: PropertyRecord) -> dict[str, Any]:
    return {
        "reference_id": record.reference_id,
        "substrate": record.substrate,
        "assay_temperature": record.assay_temperature,
        "assay_pH": record.assay_pH,
        "unit": record.unit_standardized or record.unit_original,
        "method": record.method,
    }
