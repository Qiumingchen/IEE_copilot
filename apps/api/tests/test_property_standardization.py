from app.services.property_standardization import standardize_property_value


def test_standardize_temperature_units_to_degc():
    result = standardize_property_value("optimal_temperature", "328.15", "K")

    assert result.value_standardized == "55"
    assert result.unit_standardized == "degC"
    assert result.standardization_status == "standardized"


def test_standardize_ph_without_forcing_unit_conversion():
    result = standardize_property_value("optimal_pH", "7.5", None)

    assert result.value_standardized == "7.5"
    assert result.unit_standardized == "pH"
    assert result.standardization_status == "standardized"


def test_standardize_specific_activity_preserves_supported_units():
    result = standardize_property_value("specific_activity", "120.5", "U/mg")

    assert result.value_standardized == "120.5"
    assert result.unit_standardized == "U/mg"
    assert result.standardization_status == "standardized"


def test_standardize_unknown_unit_is_not_applicable():
    result = standardize_property_value("specific_activity", "120.5", "kat/kg")

    assert result.value_standardized is None
    assert result.unit_standardized is None
    assert result.standardization_status == "not_applicable"


def test_standardize_invalid_numeric_value_fails_cleanly():
    result = standardize_property_value("optimal_temperature", "about 55", "degC")

    assert result.value_standardized is None
    assert result.unit_standardized is None
    assert result.standardization_status == "failed"
