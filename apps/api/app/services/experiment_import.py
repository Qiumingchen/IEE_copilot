import csv
from dataclasses import dataclass
from io import BytesIO, StringIO
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from app.db.models import Visibility
from app.services.mutations import (
    MutationParseError,
    normalize_mutation_string,
    parse_mutation_string,
    validate_mutations_against_sequence,
)


MEASUREMENT_COLUMNS = (
    "specific_activity",
    "relative_activity",
    "opt_temperature",
    "opt_pH",
)

ASSAY_CONTEXT_COLUMNS = (
    "substrate",
    "assay_temperature",
    "assay_pH",
)


class ExperimentImportError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedExperimentTable:
    fields: list[str]
    rows: list[dict[str, str]]


@dataclass(frozen=True)
class ValidatedExperimentRecord:
    row_number: int
    variant_name: str
    mutation_string: str | None
    sequence: str | None
    measured_property: str
    measured_value: str
    unit: str | None
    assay_condition_json: dict[str, str]
    visibility: str


@dataclass(frozen=True)
class ValidatedExperimentRows:
    records: list[ValidatedExperimentRecord]


def parse_experiment_csv(csv_text: str) -> ParsedExperimentTable:
    reader = csv.DictReader(StringIO(csv_text))
    fields = list(reader.fieldnames or [])
    rows: list[dict[str, str]] = []
    for row in reader:
        rows.append({key: (value or "").strip() for key, value in row.items() if key is not None})
    return ParsedExperimentTable(fields=fields, rows=rows)


def parse_experiment_xlsx(xlsx_bytes: bytes) -> ParsedExperimentTable:
    try:
        with ZipFile(BytesIO(xlsx_bytes)) as archive:
            shared_strings = _read_shared_strings(archive)
            sheet_xml = archive.read(_first_worksheet_path(archive))
    except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ExperimentImportError("invalid xlsx file") from exc

    matrix = _worksheet_matrix(sheet_xml, shared_strings)
    if not matrix:
        return ParsedExperimentTable(fields=[], rows=[])

    fields = [value.strip() for value in matrix[0]]
    rows = []
    for values in matrix[1:]:
        row = {
            field: (values[index].strip() if index < len(values) else "")
            for index, field in enumerate(fields)
            if field
        }
        if any(value for value in row.values()):
            rows.append(row)
    return ParsedExperimentTable(fields=fields, rows=rows)


def _first_worksheet_path(archive: ZipFile) -> str:
    sheet_names = sorted(
        name
        for name in archive.namelist()
        if name.startswith("xl/worksheets/") and name.endswith(".xml")
    )
    if not sheet_names:
        raise KeyError("worksheet not found")
    return sheet_names[0]


def _read_shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings: list[str] = []
    for item in root.findall("s:si", namespace):
        strings.append("".join(text.text or "" for text in item.findall(".//s:t", namespace)))
    return strings


def _worksheet_matrix(sheet_xml: bytes, shared_strings: list[str]) -> list[list[str]]:
    root = ElementTree.fromstring(sheet_xml)
    namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rows: list[list[str]] = []
    for row in root.findall(".//s:row", namespace):
        values: list[str] = []
        for cell in row.findall("s:c", namespace):
            column_index = _column_index(cell.attrib.get("r", ""))
            while len(values) < column_index - 1:
                values.append("")
            values.append(_cell_value(cell, shared_strings, namespace))
        rows.append(values)
    return rows


def _column_index(cell_reference: str) -> int:
    letters = "".join(character for character in cell_reference if character.isalpha()).upper()
    if not letters:
        return 1
    index = 0
    for character in letters:
        index = index * 26 + (ord(character) - ord("A") + 1)
    return index


def _cell_value(cell: ElementTree.Element, shared_strings: list[str], namespace: dict[str, str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(".//s:t", namespace))

    value_node = cell.find("s:v", namespace)
    if value_node is None or value_node.text is None:
        return ""

    value = value_node.text
    if cell_type == "s":
        try:
            return shared_strings[int(value)]
        except (ValueError, IndexError) as exc:
            raise ExperimentImportError("invalid xlsx shared string reference") from exc
    return value


def validate_experiment_rows(
    rows: list[dict[str, str]],
    engineering_sequence: str,
) -> ValidatedExperimentRows:
    records: list[ValidatedExperimentRecord] = []
    for index, row in enumerate(rows, start=2):
        records.extend(_records_for_row(row, index, engineering_sequence))
    return ValidatedExperimentRows(records=records)


def _records_for_row(
    row: dict[str, str],
    row_number: int,
    engineering_sequence: str,
) -> list[ValidatedExperimentRecord]:
    variant_name = row.get("variant_name", "").strip()
    mutation_string = _normalize_upload_mutation_string(row.get("mutation_string", ""), row_number)
    _validate_mutation_string(mutation_string, engineering_sequence, row_number)
    visibility = _normalize_visibility(row.get("visibility", ""), row_number)
    assay_condition_json = {
        column: row[column].strip()
        for column in ASSAY_CONTEXT_COLUMNS
        if row.get(column, "").strip()
    }

    records: list[ValidatedExperimentRecord] = []
    if row.get("measured_property", "").strip() or row.get("measured_value", "").strip():
        measured_property = row.get("measured_property", "").strip()
        measured_value = row.get("measured_value", "").strip()
        if not measured_property or not measured_value:
            raise ExperimentImportError(
                f"row {row_number}: measured_property and measured_value are both required"
            )
        records.append(
            _validated_record(
                row_number,
                variant_name,
                mutation_string,
                row,
                measured_property,
                measured_value,
                assay_condition_json,
                visibility,
            )
        )

    for column in MEASUREMENT_COLUMNS:
        value = row.get(column, "").strip()
        if not value:
            continue
        records.append(
            _validated_record(
                row_number,
                variant_name,
                mutation_string,
                row,
                column,
                value,
                assay_condition_json,
                visibility,
            )
        )

    if not records:
        raise ExperimentImportError(f"row {row_number}: at least one measurement is required")
    return records


def _validated_record(
    row_number: int,
    variant_name: str,
    mutation_string: str | None,
    row: dict[str, str],
    measured_property: str,
    measured_value: str,
    assay_condition_json: dict[str, str],
    visibility: str,
) -> ValidatedExperimentRecord:
    if not variant_name:
        variant_name = mutation_string or "WT"
    return ValidatedExperimentRecord(
        row_number=row_number,
        variant_name=variant_name,
        mutation_string=mutation_string,
        sequence=row.get("sequence", "").strip() or None,
        measured_property=measured_property,
        measured_value=measured_value,
        unit=row.get("unit", "").strip() or None,
        assay_condition_json=assay_condition_json,
        visibility=visibility,
    )


def _normalize_upload_mutation_string(raw_mutation_string: str, row_number: int) -> str:
    normalized = raw_mutation_string.strip().upper()
    if not normalized:
        raise ExperimentImportError(f"row {row_number}: mutation_string is required")
    if normalized == "WT":
        return "WT"
    try:
        return normalize_mutation_string(parse_mutation_string(normalized))
    except MutationParseError as exc:
        raise ExperimentImportError(f"row {row_number}: {exc}") from exc


def _validate_mutation_string(
    mutation_string: str,
    engineering_sequence: str,
    row_number: int,
) -> None:
    if mutation_string == "WT":
        return
    try:
        validate_mutations_against_sequence(parse_mutation_string(mutation_string), engineering_sequence)
    except MutationParseError as exc:
        raise ExperimentImportError(f"row {row_number}: {exc}") from exc


def _normalize_visibility(raw_visibility: str, row_number: int) -> str:
    value = raw_visibility.strip().lower() or Visibility.PRIVATE.value
    allowed = {visibility.value for visibility in Visibility}
    if value not in allowed:
        raise ExperimentImportError(f"row {row_number}: invalid visibility {raw_visibility}")
    return value
