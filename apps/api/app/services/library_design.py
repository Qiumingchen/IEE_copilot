from itertools import combinations
from typing import Any

from app.services.mutations import ParsedMutation, parse_mutation_string


SUPPORTED_PLATE_FORMATS = {24, 48, 96, 384}


def design_mutation_library(
    recommendation_candidates: list[dict[str, Any]],
    rosetta_results: list[dict[str, Any]],
    library_size: int = 24,
    max_order: int = 2,
    plate_format: int = 96,
) -> dict[str, Any]:
    if plate_format not in SUPPORTED_PLATE_FORMATS:
        raise ValueError(f"unsupported plate format: {plate_format}")
    if library_size < 1:
        raise ValueError("library_size must be at least 1")
    if max_order < 1:
        raise ValueError("max_order must be at least 1")

    single_mutations = _single_mutations_from_recommendations(recommendation_candidates, rosetta_results)
    variants = _rank_variants(_generate_variants(single_mutations, max_order=max_order))[:library_size]
    plate_layout = generate_plate_layout(variants, plate_format=plate_format)

    return {
        "library_size": library_size,
        "plate_format": plate_format,
        "variant_count": len(variants),
        "variants": variants,
        "plate_layout": plate_layout,
        "csv_text": _plate_layout_csv(plate_layout),
    }


def generate_plate_layout(variants: list[dict[str, Any]], plate_format: int = 96) -> list[dict[str, Any]]:
    wells = _well_names(plate_format)
    rows = [
        {
            "well": wells[0],
            "variant_id": "WT",
            "mutation_string": "WT",
            "role": "wt_control",
            "score": None,
            "risk_flags": [],
        },
        {
            "well": wells[1],
            "variant_id": "BLANK",
            "mutation_string": "",
            "role": "blank_control",
            "score": None,
            "risk_flags": [],
        },
    ]

    for index, variant in enumerate(variants, start=2):
        if index >= len(wells):
            break
        rows.append(
            {
                "well": wells[index],
                "variant_id": variant["variant_id"],
                "mutation_string": variant["mutation_string"],
                "role": "variant",
                "score": variant["score"],
                "risk_flags": variant["risk_flags"],
            }
        )
    return rows


def _single_mutations_from_recommendations(
    recommendation_candidates: list[dict[str, Any]],
    rosetta_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rosetta_by_mutation = {
        str(result.get("mutation_string") or "").upper(): result
        for result in rosetta_results
        if result.get("mutation_string")
    }
    single_mutations: dict[str, dict[str, Any]] = {}

    for candidate in recommendation_candidates:
        priority_score = _as_float(candidate.get("priority_score"))
        category = str(candidate.get("conservation_category") or "unclassified")
        rationale = str(candidate.get("rationale") or "")
        for suggestion in _suggestions_for_candidate(candidate):
            mutation_string = suggestion["mutation_string"]
            normalized = str(mutation_string).strip().upper()
            if not normalized or normalized in single_mutations:
                continue
            mutations = parse_mutation_string(normalized)
            if len(mutations) != 1:
                continue
            rosetta = rosetta_by_mutation.get(normalized, {})
            scored_total = _as_float_or_none(suggestion.get("total_score"))
            single_mutations[normalized] = {
                "mutation_string": normalized,
                "mutations": mutations,
                "priority_score": scored_total if scored_total is not None else priority_score,
                "recommendation_score": scored_total,
                "conservation_category": category,
                "rationale": rationale,
                "risk_summary": suggestion.get("risk_summary") or [],
                "score_components": suggestion.get("components") or [],
                "ddg_kcal_per_mol": rosetta.get("ddg_kcal_per_mol"),
                "interpretation": rosetta.get("interpretation"),
            }

    return list(single_mutations.values())


def _generate_variants(single_mutations: list[dict[str, Any]], max_order: int) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    capped_order = min(max_order, len(single_mutations))
    for order in range(1, capped_order + 1):
        for members in combinations(single_mutations, order):
            if _has_same_position_conflict(members):
                continue
            variants.append(_score_variant(list(members)))
    return variants


def _score_variant(members: list[dict[str, Any]]) -> dict[str, Any]:
    mutations = [mutation for member in members for mutation in member["mutations"]]
    mutation_string = "/".join(member["mutation_string"] for member in members)
    base_score = sum(member["priority_score"] for member in members)
    score = base_score
    reasons = [f"{member['mutation_string']} from {member['conservation_category']} hotspot" for member in members]
    risk_flags: list[str] = []
    member_scores = []

    for member in members:
        recommendation_score = _as_float_or_none(member.get("recommendation_score"))
        if recommendation_score is not None:
            member_scores.append(
                {
                    "mutation_string": member["mutation_string"],
                    "total_score": recommendation_score,
                }
            )
            reasons.append(f"{member['mutation_string']} from scored recommendation {recommendation_score:.2f}")
        risk_flags.extend(str(risk) for risk in member.get("risk_summary", []) if risk)

    legacy_ddg_values = [
        _as_float_or_none(member.get("ddg_kcal_per_mol"))
        for member in members
        if member.get("recommendation_score") is None
    ]
    for ddg in [value for value in legacy_ddg_values if value is not None]:
        if ddg < 0:
            score += min(abs(ddg) * 0.5, 1.0)
            reasons.append(f"member has stabilizing Rosetta ddG {ddg:.2f} kcal/mol")
        elif ddg >= 1.0:
            score -= min(ddg * 0.5, 1.5)
            risk_flags.append("ddg_destabilizing_member")

    categories = {str(member["conservation_category"]) for member in members}
    if "variable" in categories and "moderately_conserved" in categories:
        score += 0.25
        reasons.append("combines variable and moderately conserved sites for complementary exploration")

    if _has_nearby_position_conflict(mutations):
        score -= 0.3
        risk_flags.append("nearby_positions")

    if len([category for category in categories if category == "highly_conserved"]) > 0:
        score -= 1.0
        risk_flags.append("highly_conserved_member")

    return {
        "variant_id": f"VAR-{mutation_string.replace('/', '-')}",
        "mutation_string": mutation_string,
        "order": len(members),
        "score": round(score, 3),
        "reasons": reasons,
        "risk_flags": sorted(set(risk_flags)),
        "mutations": [mutation.model_dump() for mutation in mutations],
        "member_scores": member_scores,
    }


def _rank_variants(variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(variants, key=lambda variant: (variant["score"], -variant["order"]), reverse=True)


def _has_same_position_conflict(members: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> bool:
    positions = [mutation.position for member in members for mutation in member["mutations"]]
    return len(positions) != len(set(positions))


def _has_nearby_position_conflict(mutations: list[ParsedMutation]) -> bool:
    positions = sorted(mutation.position for mutation in mutations)
    return any(right - left <= 3 for left, right in zip(positions, positions[1:]))


def _well_names(plate_format: int) -> list[str]:
    if plate_format == 384:
        rows = "ABCDEFGHIJKLMNOP"
        columns = range(1, 25)
    else:
        rows = "ABCDEFGH"
        columns = range(1, 13)
    return [f"{row}{column}" for row in rows for column in columns][:plate_format]


def _plate_layout_csv(plate_layout: list[dict[str, Any]]) -> str:
    lines = ["well,variant_id,mutation_string,role,score,risk_flags"]
    for row in plate_layout:
        lines.append(
            ",".join(
                [
                    str(row["well"]),
                    str(row["variant_id"]),
                    str(row["mutation_string"]),
                    str(row["role"]),
                    "" if row["score"] is None else str(row["score"]),
                    "|".join(row["risk_flags"]),
                ]
            )
        )
    return "\n".join(lines)


def _suggestions_for_candidate(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    scored_suggestions = candidate.get("scored_suggestions")
    if isinstance(scored_suggestions, list) and scored_suggestions:
        return [
            suggestion
            for suggestion in scored_suggestions
            if isinstance(suggestion, dict) and suggestion.get("mutation_string")
        ]
    return [
        {"mutation_string": mutation_string}
        for mutation_string in candidate.get("suggested_mutations", [])
    ]


def _as_float(value: Any) -> float:
    parsed = _as_float_or_none(value)
    return parsed if parsed is not None else 0.0


def _as_float_or_none(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
