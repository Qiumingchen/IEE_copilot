from dataclasses import dataclass

from app.db.models import EnzymeModule
from app.services.mutations import ParsedMutation, parse_mutation_string
from app.services.residue_features import ResidueFeatureRecord


@dataclass(frozen=True)
class ScoreComponent:
    name: str
    value: float
    weight: float
    contribution: float
    rationale: str


@dataclass(frozen=True)
class MutationScore:
    mutation_string: str
    total_score: float
    components: list[ScoreComponent]
    risk_summary: list[str]
    parsed_mutations: list[dict]


def calculate_general_score(
    mutation_string: str,
    residue_features: list[ResidueFeatureRecord],
) -> MutationScore:
    parsed_mutations = parse_mutation_string(mutation_string)
    components = generate_score_components(mutation_string, residue_features)
    total_score = round(sum(component.contribution for component in components), 3)
    return MutationScore(
        mutation_string="/".join(
            f"{mutation.wildtype}{mutation.position}{mutation.mutant}"
            for mutation in parsed_mutations
        ),
        total_score=total_score,
        components=components,
        risk_summary=generate_risk_summary(mutation_string, residue_features, components),
        parsed_mutations=[mutation.model_dump() for mutation in parsed_mutations],
    )


def calculate_module_specific_score(
    mutation_string: str,
    residue_features: list[ResidueFeatureRecord],
    module: EnzymeModule,
) -> MutationScore:
    general_score = calculate_general_score(mutation_string, residue_features)
    parsed_mutations = parse_mutation_string(mutation_string)
    features = _features_for_mutations(parsed_mutations, residue_features)
    module_components = _module_components(module, parsed_mutations, features)
    components = [*general_score.components, *module_components]
    risk_summary = _dedupe(
        [
            *general_score.risk_summary,
            *_module_risks(module, features),
        ]
    )
    return MutationScore(
        mutation_string=general_score.mutation_string,
        total_score=round(sum(component.contribution for component in components), 3),
        components=components,
        risk_summary=risk_summary,
        parsed_mutations=general_score.parsed_mutations,
    )


def generate_score_components(
    mutation_string: str,
    residue_features: list[ResidueFeatureRecord],
) -> list[ScoreComponent]:
    parsed_mutations = parse_mutation_string(mutation_string)
    features_by_position = {feature.position: feature for feature in residue_features}
    features = [features_by_position.get(mutation.position) for mutation in parsed_mutations]

    return [
        _component(
            "conservation_tolerance",
            _mean(_conservation_value(feature) for feature in features),
            1.5,
            "prefers variable or moderately conserved positions over highly conserved positions",
        ),
        _component(
            "reported_benefit",
            _mean(_reported_benefit_value(feature) for feature in features),
            1.2,
            "uses reported beneficial mutation ratio at the same residue",
        ),
        _component(
            "structure_proximity",
            _mean(_structure_proximity_value(feature) for feature in features),
            1.0,
            "gives modest priority to residues close to ligand or pocket evidence",
        ),
        _component(
            "rosetta_stability",
            _mean(_rosetta_value(mutation, feature) for mutation, feature in zip(parsed_mutations, features)),
            2.0,
            "uses Rosetta ddG when available, rewarding stabilizing predictions",
        ),
        _component(
            "solubility",
            _mean(_solubility_value(feature) for feature in features),
            0.5,
            "penalizes residues with elevated first-pass solubility risk",
        ),
    ]


def generate_risk_summary(
    mutation_string: str,
    residue_features: list[ResidueFeatureRecord],
    components: list[ScoreComponent] | None = None,
) -> list[str]:
    parsed_mutations = parse_mutation_string(mutation_string)
    features_by_position = {feature.position: feature for feature in residue_features}
    features = [features_by_position.get(mutation.position) for mutation in parsed_mutations]
    risks: list[str] = []

    if any(feature and feature.wildtype_frequency is not None and feature.wildtype_frequency >= 0.9 for feature in features):
        risks.append("highly_conserved_site")
    if any(feature and feature.distance_to_ligand is not None and feature.distance_to_ligand <= 4.0 for feature in features):
        risks.append("near_ligand_site")
    if any(_rosetta_value(mutation, feature) <= -1.0 for mutation, feature in zip(parsed_mutations, features)):
        risks.append("destabilizing_rosetta_ddg")
    if any(feature and feature.solubility_risk == "medium" for feature in features):
        risks.append("medium_solubility_risk")
    if any(feature is None or feature.unavailable_features for feature in features):
        risks.append("missing_feature_data")

    return risks


def _features_for_mutations(
    parsed_mutations: list[ParsedMutation],
    residue_features: list[ResidueFeatureRecord],
) -> list[ResidueFeatureRecord | None]:
    features_by_position = {feature.position: feature for feature in residue_features}
    return [features_by_position.get(mutation.position) for mutation in parsed_mutations]


def _module_components(
    module: EnzymeModule,
    parsed_mutations: list[ParsedMutation],
    features: list[ResidueFeatureRecord | None],
) -> list[ScoreComponent]:
    if module == EnzymeModule.ANTHRAQUINONE_GLYCOSYLTRANSFERASE:
        return [
            _component(
                "anthraquinone_binding_region_score",
                _mean(_anthraquinone_binding_value(feature) for feature in features),
                1.4,
                "prioritizes residues close to anthraquinone-like ligand evidence in complex structures",
            ),
            _component(
                "UDP_sugar_region_score",
                _mean(_udp_sugar_region_value(feature) for feature in features),
                0.8,
                "uses predicted pocket proximity as a low-confidence proxy for donor-sugar region effects",
            ),
            _component(
                "product_selectivity_score",
                _mean(_product_selectivity_value(feature) for feature in features),
                1.0,
                "favours variable ligand-proximal residues that may tune regioselectivity or substrate scope",
            ),
            _component(
                "activity_score",
                _mean(_reported_benefit_value(feature) for feature in features),
                0.9,
                "uses reported beneficial mutation evidence as a first-pass activity prior",
            ),
            _component(
                "solubility_score",
                _mean(_module_solubility_value(feature) for feature in features),
                0.5,
                "keeps expression risk visible for glycosyltransferase engineering",
            ),
            _component(
                "stability_score",
                _mean(_rosetta_value(mutation, feature) for mutation, feature in zip(parsed_mutations, features)),
                0.9,
                "adds stabilizing Rosetta evidence without replacing activity and selectivity priorities",
            ),
        ]
    if module == EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE:
        return [
            _component(
                "thermostability_score",
                _mean(_rosetta_value(mutation, feature) for mutation, feature in zip(parsed_mutations, features)),
                1.5,
                "prioritizes stabilizing ddG evidence for mature microbial transglutaminase variants",
            ),
            _component(
                "opt_temperature_score",
                _mean(_reported_benefit_value(feature) for feature in features),
                0.9,
                "uses reported beneficial mutation evidence as a proxy for improved operating temperature",
            ),
            _component(
                "opt_pH_score",
                _mean(_surface_accessible_value(feature) for feature in features),
                0.5,
                "gives modest priority to surface-accessible positions that may tune pH response",
            ),
            _component(
                "activity_retention_score",
                _mean(_activity_retention_value(feature) for feature in features),
                1.0,
                "penalizes highly conserved positions to preserve mature-enzyme catalytic function",
            ),
            _component(
                "surface_charge_score",
                _mean(_surface_accessible_value(feature) for feature in features),
                0.6,
                "captures surface engineering opportunities for soluble mature enzyme behaviour",
            ),
            _component(
                "solubility_score",
                _mean(_module_solubility_value(feature) for feature in features),
                0.6,
                "keeps soluble-expression risk explicit for mTGase candidates",
            ),
        ]
    return []


def _module_risks(module: EnzymeModule, features: list[ResidueFeatureRecord | None]) -> list[str]:
    if module == EnzymeModule.ANTHRAQUINONE_GLYCOSYLTRANSFERASE:
        if any(feature and feature.distance_to_ligand is not None for feature in features):
            return ["anthraquinone_complex_distance_used"]
        return ["low_confidence_without_substrate_complex"]
    if module == EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE:
        return ["mature_enzyme_only"]
    return []


def _anthraquinone_binding_value(feature: ResidueFeatureRecord | None) -> float:
    if feature is None or feature.distance_to_ligand is None:
        return 0.0
    if feature.distance_to_ligand <= 4.0:
        return 1.0
    if feature.distance_to_ligand <= 8.0:
        return 0.45
    return 0.0


def _udp_sugar_region_value(feature: ResidueFeatureRecord | None) -> float:
    if feature is None or feature.distance_to_predicted_pocket is None:
        return 0.0
    if feature.distance_to_predicted_pocket <= 6.0:
        return 0.7
    if feature.distance_to_predicted_pocket <= 10.0:
        return 0.3
    return 0.0


def _product_selectivity_value(feature: ResidueFeatureRecord | None) -> float:
    if feature is None or feature.distance_to_ligand is None:
        return 0.0
    if feature.distance_to_ligand > 8.0:
        return 0.0
    if feature.wildtype_frequency is not None and feature.wildtype_frequency < 0.6:
        return 0.8
    return 0.3


def _surface_accessible_value(feature: ResidueFeatureRecord | None) -> float:
    if feature is None or feature.solvent_accessibility is None:
        return 0.0
    if feature.solvent_accessibility >= 0.6:
        return 0.6
    if feature.solvent_accessibility >= 0.3:
        return 0.25
    return 0.0


def _activity_retention_value(feature: ResidueFeatureRecord | None) -> float:
    if feature is None or feature.wildtype_frequency is None:
        return 0.0
    if feature.wildtype_frequency >= 0.9:
        return -0.7
    if feature.wildtype_frequency >= 0.6:
        return 0.4
    return 0.7


def _module_solubility_value(feature: ResidueFeatureRecord | None) -> float:
    if feature is None:
        return 0.0
    if feature.solubility_risk == "low":
        return 0.25
    if feature.solubility_risk == "medium":
        return -0.15
    if feature.solubility_risk == "high":
        return -0.5
    return 0.0


def _dedupe(values: list[str]) -> list[str]:
    deduped = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped


def _component(name: str, value: float, weight: float, rationale: str) -> ScoreComponent:
    rounded_value = round(value, 3)
    return ScoreComponent(
        name=name,
        value=rounded_value,
        weight=weight,
        contribution=round(rounded_value * weight, 3),
        rationale=rationale,
    )


def _conservation_value(feature: ResidueFeatureRecord | None) -> float:
    if feature is None or feature.wildtype_frequency is None:
        return 0.0
    if feature.wildtype_frequency >= 0.9:
        return -0.8
    if feature.wildtype_frequency >= 0.6:
        return 0.5
    return 1.0


def _reported_benefit_value(feature: ResidueFeatureRecord | None) -> float:
    if feature is None or feature.reported_mutation_count == 0:
        return 0.0
    return min(feature.reported_beneficial_mutation_count / feature.reported_mutation_count, 1.0)


def _structure_proximity_value(feature: ResidueFeatureRecord | None) -> float:
    if feature is None:
        return 0.0
    distance = feature.distance_to_ligand or feature.distance_to_predicted_pocket
    if distance is None:
        return 0.0
    if distance <= 4.0:
        return 0.75
    if distance <= 8.0:
        return 0.35
    return 0.0


def _rosetta_value(mutation: ParsedMutation, feature: ResidueFeatureRecord | None) -> float:
    if feature is None or not feature.rosetta_ddg:
        return 0.0
    target = f"{mutation.wildtype}{mutation.position}{mutation.mutant}".upper()
    results = feature.rosetta_ddg.get("results")
    matching = None
    if isinstance(results, list):
        for result in results:
            if isinstance(result, dict) and str(result.get("mutation_string") or "").upper() == target:
                matching = result
                break
    ddg = _as_float(matching.get("ddg_kcal_per_mol") if matching else None)
    if ddg is None:
        return 0.0
    if ddg < 0:
        return min(abs(ddg) / 2.0, 1.0)
    if ddg >= 1.0:
        return -1.0
    return 0.0


def _solubility_value(feature: ResidueFeatureRecord | None) -> float:
    if feature is None:
        return 0.0
    if feature.solubility_risk == "medium":
        return -0.25
    if feature.solubility_risk == "high":
        return -0.75
    return 0.0


def _mean(values) -> float:
    parsed = list(values)
    if not parsed:
        return 0.0
    return sum(parsed) / len(parsed)


def _as_float(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
