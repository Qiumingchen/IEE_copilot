from typing import Any


NON_CONSERVATIVE_DEFAULTS = ["A", "V", "S"]


def recommend_mutation_hotspots(
    conservation_sites: list[dict[str, Any]],
    max_candidates: int = 12,
) -> list[dict[str, Any]]:
    scored_sites = []
    for site in conservation_sites:
        category = str(site.get("conservation_category") or "")
        if category == "highly_conserved":
            continue
        position = site.get("query_position")
        wildtype = str(site.get("wildtype_residue") or "").upper()
        if not isinstance(position, int) or not wildtype or wildtype == "-":
            continue

        entropy = _as_float(site.get("shannon_entropy"))
        wildtype_frequency = _as_float(site.get("wildtype_frequency"))
        score = round(entropy + (1.0 - wildtype_frequency), 3)
        scored_sites.append(
            {
                "query_position": position,
                "wildtype_residue": wildtype,
                "conservation_category": category,
                "shannon_entropy": entropy,
                "wildtype_frequency": wildtype_frequency,
                "priority_score": score,
                "suggested_mutations": _suggested_mutations(wildtype, position),
                "rationale": _rationale(category, entropy, wildtype_frequency),
            }
        )

    return sorted(
        scored_sites,
        key=lambda candidate: (candidate["priority_score"], candidate["query_position"]),
        reverse=True,
    )[:max_candidates]


def _suggested_mutations(wildtype: str, position: int) -> list[str]:
    substitutions = [residue for residue in NON_CONSERVATIVE_DEFAULTS if residue != wildtype]
    return [f"{wildtype}{position}{residue}" for residue in substitutions[:3]]


def _rationale(category: str, entropy: float, wildtype_frequency: float) -> str:
    return (
        f"{category or 'unclassified'} site with entropy {entropy:.3f} "
        f"and wildtype frequency {wildtype_frequency:.3f}; suitable for first-pass hotspot screening."
    )


def _as_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0
