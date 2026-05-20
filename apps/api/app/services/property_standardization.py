from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class PropertyStandardizationResult:
    value_standardized: str | None
    unit_standardized: str | None
    standardization_status: str


TEMPERATURE_UNITS = {
    "c": "degC",
    "degc": "degC",
    "°c": "degC",
    "k": "K",
    "kelvin": "K",
    "f": "degF",
    "degf": "degF",
    "°f": "degF",
}

SPECIFIC_ACTIVITY_UNITS = {
    "u/mg": "U/mg",
    "u mg-1": "U/mg",
    "u/mg protein": "U/mg",
    "umol/min/mg": "U/mg",
    "μmol/min/mg": "U/mg",
}


def standardize_property_value(
    property_type: str,
    value_original: str,
    unit_original: str | None,
) -> PropertyStandardizationResult:
    value = _parse_decimal(value_original)
    if value is None:
        return PropertyStandardizationResult(None, None, "failed")

    normalized_type = property_type.strip().lower()
    normalized_unit = _normalize_unit(unit_original)

    if normalized_type in {"optimal_temperature", "opt_temperature", "temperature"}:
        return _standardize_temperature(value, normalized_unit)
    if normalized_type in {"optimal_ph", "optimal_pH".lower(), "ph", "opt_ph"}:
        return PropertyStandardizationResult(_format_decimal(value), "pH", "standardized")
    if normalized_type in {"specific_activity", "activity"}:
        return _standardize_specific_activity(value, normalized_unit)

    return PropertyStandardizationResult(None, None, "not_applicable")


def _standardize_temperature(
    value: Decimal,
    normalized_unit: str,
) -> PropertyStandardizationResult:
    unit = TEMPERATURE_UNITS.get(normalized_unit)
    if unit is None:
        return PropertyStandardizationResult(None, None, "not_applicable")
    if unit == "degC":
        standardized = value
    elif unit == "K":
        standardized = value - Decimal("273.15")
    elif unit == "degF":
        standardized = (value - Decimal("32")) * Decimal("5") / Decimal("9")
    else:
        return PropertyStandardizationResult(None, None, "not_applicable")
    return PropertyStandardizationResult(_format_decimal(standardized), "degC", "standardized")


def _standardize_specific_activity(
    value: Decimal,
    normalized_unit: str,
) -> PropertyStandardizationResult:
    unit = SPECIFIC_ACTIVITY_UNITS.get(normalized_unit)
    if unit is None:
        return PropertyStandardizationResult(None, None, "not_applicable")
    return PropertyStandardizationResult(_format_decimal(value), unit, "standardized")


def _parse_decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value.strip())
    except (InvalidOperation, ValueError):
        return None


def _normalize_unit(unit: str | None) -> str:
    return (unit or "").strip().lower().replace(" ", " ")


def _format_decimal(value: Decimal) -> str:
    normalized = value.quantize(Decimal("0.001")).normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")
