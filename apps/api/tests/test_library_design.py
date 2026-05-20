from app.services.library_design import design_mutation_library


def test_design_mutation_library_generates_ranked_combinations_and_plate_controls():
    recommendation_candidates = [
        {
            "query_position": 10,
            "wildtype_residue": "L",
            "conservation_category": "variable",
            "priority_score": 1.8,
            "suggested_mutations": ["L10A", "L10V"],
            "rationale": "variable site",
        },
        {
            "query_position": 12,
            "wildtype_residue": "F",
            "conservation_category": "moderately_conserved",
            "priority_score": 1.2,
            "suggested_mutations": ["F12A"],
            "rationale": "moderately conserved site",
        },
        {
            "query_position": 10,
            "wildtype_residue": "L",
            "conservation_category": "variable",
            "priority_score": 1.7,
            "suggested_mutations": ["L10S"],
            "rationale": "same position alternative",
        },
    ]
    rosetta_results = [
        {
            "mutation_string": "L10A",
            "ddg_kcal_per_mol": -0.6,
            "interpretation": "stabilizing",
        },
        {
            "mutation_string": "F12A",
            "ddg_kcal_per_mol": 1.4,
            "interpretation": "destabilizing_or_neutral",
        },
    ]

    library = design_mutation_library(
        recommendation_candidates,
        rosetta_results,
        library_size=6,
        max_order=2,
        plate_format=96,
    )

    assert library["library_size"] == 6
    assert library["plate_format"] == 96
    assert [well["role"] for well in library["plate_layout"][:2]] == ["wt_control", "blank_control"]
    assert library["plate_layout"][0]["well"] == "A1"
    assert library["plate_layout"][1]["well"] == "A2"
    assert "L10A/F12A" in [variant["mutation_string"] for variant in library["variants"]]
    assert "L10A/L10V" not in [variant["mutation_string"] for variant in library["variants"]]

    combined_variant = next(
        variant for variant in library["variants"] if variant["mutation_string"] == "L10A/F12A"
    )
    assert combined_variant["order"] == 2
    assert "ddg_destabilizing_member" in combined_variant["risk_flags"]
    assert any("stabilizing Rosetta ddG" in reason for reason in combined_variant["reasons"])
    assert library["csv_text"].splitlines()[0] == "well,variant_id,mutation_string,role,score,risk_flags"


def test_design_mutation_library_supports_384_well_layout():
    library = design_mutation_library(
        [
            {
                "query_position": 5,
                "wildtype_residue": "A",
                "conservation_category": "variable",
                "priority_score": 1.5,
                "suggested_mutations": ["A5V"],
            }
        ],
        [],
        library_size=1,
        max_order=1,
        plate_format=384,
    )

    assert library["plate_layout"][0]["well"] == "A1"
    assert library["plate_layout"][1]["well"] == "A2"
    assert library["plate_layout"][2]["well"] == "A3"
    assert library["plate_layout"][2]["mutation_string"] == "A5V"
