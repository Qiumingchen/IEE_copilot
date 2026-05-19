import pytest

from app.services.conservation import calculate_conservation_profile
from app.services.msa import MsaAlignedRecord, MsaAlignment


def test_calculate_conservation_profile_scores_query_positions():
    alignment = MsaAlignment(
        records=[
            MsaAlignedRecord(identifier="query", aligned_sequence="ACD"),
            MsaAlignedRecord(identifier="homolog_1", aligned_sequence="ACD"),
            MsaAlignedRecord(identifier="homolog_2", aligned_sequence="ACE"),
            MsaAlignedRecord(identifier="homolog_3", aligned_sequence="A-D"),
        ]
    )

    profile = calculate_conservation_profile(alignment, query_identifier="query")

    assert profile.sequence_count == 4
    assert [site.query_position for site in profile.sites] == [1, 2, 3]
    assert [site.wildtype_residue for site in profile.sites] == ["A", "C", "D"]
    assert profile.sites[0].shannon_entropy == 0.0
    assert profile.sites[0].wildtype_frequency == 1.0
    assert profile.sites[0].conservation_category == "highly_conserved"
    assert profile.sites[1].shannon_entropy == pytest.approx(0.811, abs=0.001)
    assert profile.sites[1].wildtype_frequency == 0.75
    assert profile.sites[1].conservation_category == "moderately_conserved"
    assert profile.sites[2].shannon_entropy == pytest.approx(0.811, abs=0.001)
    assert profile.sites[2].wildtype_frequency == 0.75


def test_calculate_conservation_profile_skips_query_gap_columns():
    alignment = MsaAlignment(
        records=[
            MsaAlignedRecord(identifier="query", aligned_sequence="A-C"),
            MsaAlignedRecord(identifier="homolog_1", aligned_sequence="ATC"),
            MsaAlignedRecord(identifier="homolog_2", aligned_sequence="AGC"),
        ]
    )

    profile = calculate_conservation_profile(alignment, query_identifier="query")

    assert [site.alignment_column for site in profile.sites] == [1, 3]
    assert [site.query_position for site in profile.sites] == [1, 2]
    assert [site.wildtype_residue for site in profile.sites] == ["A", "C"]


def test_calculate_conservation_profile_marks_variable_sites():
    alignment = MsaAlignment(
        records=[
            MsaAlignedRecord(identifier="query", aligned_sequence="A"),
            MsaAlignedRecord(identifier="homolog_1", aligned_sequence="C"),
            MsaAlignedRecord(identifier="homolog_2", aligned_sequence="D"),
            MsaAlignedRecord(identifier="homolog_3", aligned_sequence="E"),
        ]
    )

    profile = calculate_conservation_profile(alignment, query_identifier="query")

    assert profile.sites[0].wildtype_frequency == 0.25
    assert profile.sites[0].conservation_category == "variable"


def test_calculate_conservation_profile_requires_query_record():
    alignment = MsaAlignment(records=[MsaAlignedRecord(identifier="other", aligned_sequence="ACD")])

    with pytest.raises(ValueError, match="query sequence not found"):
        calculate_conservation_profile(alignment, query_identifier="query")
