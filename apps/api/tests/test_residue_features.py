from app.services.residue_features import build_residue_feature_records


def test_build_residue_feature_records_combines_conservation_structure_mutations_and_rosetta():
    features = build_residue_feature_records(
        sequence="MGD",
        conservation_sites=[
            {
                "query_position": 2,
                "wildtype_residue": "G",
                "shannon_entropy": 0.4,
                "wildtype_frequency": 0.8,
            }
        ],
        structure_summaries=[
            {
                "chain_summary": {
                    "chains": [
                        {
                            "residues": [
                                {
                                    "sequence_position": 2,
                                    "secondary_structure": "loop",
                                    "solvent_accessibility": 0.62,
                                }
                            ]
                        }
                    ]
                },
                "ligand_summary": {
                    "distance_matrix": [
                        {
                            "sequence_position": 2,
                            "min_distance_angstrom": 0.6,
                        }
                    ]
                },
            }
        ],
        mutation_records=[
            {
                "mutation_string": "G2A",
                "property_delta": {"optimal_temperature_delta_degC": 5},
            },
            {
                "mutation_string": "G2V",
                "property_delta": {"specific_activity_fold_change": -0.2},
            },
        ],
        rosetta_results=[
            {
                "mutation_string": "G2A",
                "ddg_kcal_per_mol": -1.2,
                "interpretation": "stabilizing",
            }
        ],
    )

    position_two = features[1]

    assert position_two.position == 2
    assert position_two.wildtype_aa == "G"
    assert position_two.conservation_score == 0.4
    assert position_two.wildtype_frequency == 0.8
    assert position_two.secondary_structure == "loop"
    assert position_two.solvent_accessibility == 0.62
    assert position_two.distance_to_ligand == 0.6
    assert position_two.reported_mutation_count == 2
    assert position_two.reported_beneficial_mutation_count == 1
    assert position_two.rosetta_ddg == {
        "best_mutation": "G2A",
        "best_ddg_kcal_per_mol": -1.2,
        "results": [
            {
                "mutation_string": "G2A",
                "ddg_kcal_per_mol": -1.2,
                "interpretation": "stabilizing",
            }
        ],
    }
    assert "distance_to_ligand" not in position_two.unavailable_features


def test_build_residue_feature_records_marks_missing_features_unavailable():
    features = build_residue_feature_records(sequence="AC")

    assert len(features) == 2
    assert features[0].position == 1
    assert features[0].wildtype_aa == "A"
    assert features[0].reported_mutation_count == 0
    assert features[0].reported_beneficial_mutation_count == 0
    assert features[0].solubility_risk == "low"
    assert set(features[0].unavailable_features) == {
        "conservation_score",
        "wildtype_frequency",
        "secondary_structure",
        "solvent_accessibility",
        "distance_to_ligand",
        "distance_to_predicted_pocket",
        "rosetta_ddg",
    }
