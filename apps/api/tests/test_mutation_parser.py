import pytest

from app.services.mutations import MutationParseError, parse_mutation_string, validate_mutations_against_sequence


def test_parse_mutation_string_supports_single_and_multi_point_formats():
    assert [mutation.model_dump() for mutation in parse_mutation_string("A123V")] == [
        {"wildtype": "A", "position": 123, "mutant": "V"}
    ]
    assert [mutation.model_dump() for mutation in parse_mutation_string("A123V/G145D")] == [
        {"wildtype": "A", "position": 123, "mutant": "V"},
        {"wildtype": "G", "position": 145, "mutant": "D"},
    ]
    assert [mutation.model_dump() for mutation in parse_mutation_string("A123V-G145D")] == [
        {"wildtype": "A", "position": 123, "mutant": "V"},
        {"wildtype": "G", "position": 145, "mutant": "D"},
    ]


def test_parse_mutation_string_rejects_invalid_format_with_clear_message():
    with pytest.raises(MutationParseError, match="Invalid mutation token"):
        parse_mutation_string("A12")


def test_validate_mutations_against_sequence_checks_wildtype_residue():
    mutations = parse_mutation_string("A1V/D3Y")
    assert validate_mutations_against_sequence(mutations, "ACD") is None

    with pytest.raises(MutationParseError, match="expected G at position 2 but found C"):
        validate_mutations_against_sequence(parse_mutation_string("G2A"), "ACD")
