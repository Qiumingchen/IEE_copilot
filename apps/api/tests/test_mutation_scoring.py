from app.services.mutation_scoring import (
    calculate_general_score,
    generate_risk_summary,
    generate_score_components,
)
from app.services.residue_features import ResidueFeatureRecord


def test_calculate_general_score_combines_components_and_risk_summary():
    features = [
        ResidueFeatureRecord(
            position=2,
            wildtype_aa="G",
            conservation_score=0.4,
            wildtype_frequency=0.8,
            distance_to_ligand=0.6,
            reported_mutation_count=3,
            reported_beneficial_mutation_count=2,
            rosetta_ddg={
                "best_mutation": "G2A",
                "best_ddg_kcal_per_mol": -1.2,
                "results": [
                    {
                        "mutation_string": "G2A",
                        "ddg_kcal_per_mol": -1.2,
                        "interpretation": "stabilizing",
                    }
                ],
            },
            solubility_risk="low",
        )
    ]

    score = calculate_general_score("G2A", features)

    assert score.mutation_string == "G2A"
    assert score.total_score == 3.5
    assert [component.name for component in score.components] == [
        "conservation_tolerance",
        "reported_benefit",
        "structure_proximity",
        "rosetta_stability",
        "solubility",
    ]
    assert "near_ligand_site" in score.risk_summary
    assert "missing_feature_data" not in score.risk_summary


def test_generate_score_components_reports_missing_feature_penalties():
    features = [
        ResidueFeatureRecord(
            position=10,
            wildtype_aa="W",
            wildtype_frequency=0.95,
            distance_to_ligand=None,
            rosetta_ddg={
                "best_mutation": "W10A",
                "best_ddg_kcal_per_mol": 2.4,
                "results": [
                    {
                        "mutation_string": "W10A",
                        "ddg_kcal_per_mol": 2.4,
                        "interpretation": "destabilizing",
                    }
                ],
            },
            solubility_risk="medium",
            unavailable_features=["distance_to_ligand", "solvent_accessibility"],
        )
    ]

    components = generate_score_components("W10A", features)
    risks = generate_risk_summary("W10A", features, components)

    assert next(component for component in components if component.name == "conservation_tolerance").value == -0.8
    assert next(component for component in components if component.name == "rosetta_stability").value == -1.0
    assert next(component for component in components if component.name == "solubility").value == -0.25
    assert risks == [
        "highly_conserved_site",
        "destabilizing_rosetta_ddg",
        "medium_solubility_risk",
        "missing_feature_data",
    ]


def test_calculate_general_score_handles_multi_mutation_candidates():
    features = [
        ResidueFeatureRecord(position=2, wildtype_aa="G", wildtype_frequency=0.5),
        ResidueFeatureRecord(position=5, wildtype_aa="A", wildtype_frequency=0.7),
    ]

    score = calculate_general_score("G2V/A5S", features)

    assert score.total_score == 1.125
    assert score.parsed_mutations == [
        {"wildtype": "G", "position": 2, "mutant": "V"},
        {"wildtype": "A", "position": 5, "mutant": "S"},
    ]


def test_calculate_general_score_uses_only_matching_rosetta_result_for_candidate():
    features = [
        ResidueFeatureRecord(
            position=10,
            wildtype_aa="L",
            wildtype_frequency=0.4,
            rosetta_ddg={
                "best_mutation": "L10A",
                "best_ddg_kcal_per_mol": -0.8,
                "results": [
                    {
                        "mutation_string": "L10A",
                        "ddg_kcal_per_mol": -0.8,
                        "interpretation": "stabilizing",
                    }
                ],
            },
        )
    ]

    matching_score = calculate_general_score("L10A", features)
    untested_score = calculate_general_score("L10V", features)

    matching_rosetta = next(
        component for component in matching_score.components if component.name == "rosetta_stability"
    )
    untested_rosetta = next(
        component for component in untested_score.components if component.name == "rosetta_stability"
    )
    assert matching_rosetta.value == 0.4
    assert untested_rosetta.value == 0.0
