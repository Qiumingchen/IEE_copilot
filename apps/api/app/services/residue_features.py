from dataclasses import dataclass, field
from typing import Any

from app.services.mutations import MutationParseError, parse_mutation_string


@dataclass(frozen=True)
class ResidueFeatureRecord:
    position: int
    wildtype_aa: str
    conservation_score: float | None = None
    wildtype_frequency: float | None = None
    secondary_structure: str | None = None
    solvent_accessibility: float | None = None
    distance_to_ligand: float | None = None
    distance_to_predicted_pocket: float | None = None
    reported_mutation_count: int = 0
    reported_beneficial_mutation_count: int = 0
    rosetta_ddg: dict[str, Any] | None = None
    solubility_risk: str = "low"
    unavailable_features: list[str] = field(default_factory=list)


def build_residue_feature_records(
    sequence: str,
    *,
    conservation_sites: list[dict[str, Any]] | None = None,
    structure_summaries: list[dict[str, Any]] | None = None,
    mutation_records: list[dict[str, Any]] | None = None,
    rosetta_results: list[dict[str, Any]] | None = None,
    predicted_pocket_distances: dict[int, float] | None = None,
) -> list[ResidueFeatureRecord]:
    normalized_sequence = "".join(sequence.split()).upper()
    conservation_by_position = _conservation_by_position(conservation_sites or [])
    structure_by_position = _structure_features_by_position(structure_summaries or [])
    mutation_counts = _mutation_counts_by_position(mutation_records or [])
    rosetta_by_position = _rosetta_by_position(rosetta_results or [])
    predicted_pocket_distances = predicted_pocket_distances or {}

    features: list[ResidueFeatureRecord] = []
    for index, wildtype in enumerate(normalized_sequence, start=1):
        conservation = conservation_by_position.get(index, {})
        structure = structure_by_position.get(index, {})
        mutation_count, beneficial_count = mutation_counts.get(index, (0, 0))
        rosetta = rosetta_by_position.get(index)
        distance_to_predicted_pocket = predicted_pocket_distances.get(index)
        record = ResidueFeatureRecord(
            position=index,
            wildtype_aa=wildtype,
            conservation_score=_as_float_or_none(conservation.get("conservation_score")),
            wildtype_frequency=_as_float_or_none(conservation.get("wildtype_frequency")),
            secondary_structure=_as_string_or_none(structure.get("secondary_structure")),
            solvent_accessibility=_as_float_or_none(structure.get("solvent_accessibility")),
            distance_to_ligand=_as_float_or_none(structure.get("distance_to_ligand")),
            distance_to_predicted_pocket=distance_to_predicted_pocket,
            reported_mutation_count=mutation_count,
            reported_beneficial_mutation_count=beneficial_count,
            rosetta_ddg=rosetta,
            solubility_risk=_solubility_risk(wildtype),
        )
        features.append(
            ResidueFeatureRecord(
                **{
                    **record.__dict__,
                    "unavailable_features": _unavailable_features(record),
                }
            )
        )

    return features


def _conservation_by_position(sites: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for site in sites:
        position = _as_int_or_none(site.get("query_position"))
        if position is None:
            continue
        indexed[position] = {
            "conservation_score": site.get("shannon_entropy"),
            "wildtype_frequency": site.get("wildtype_frequency"),
        }
    return indexed


def _structure_features_by_position(structures: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    features: dict[int, dict[str, Any]] = {}
    for structure in structures:
        for residue in _structure_residues(structure.get("chain_summary")):
            position = _as_int_or_none(residue.get("sequence_position"))
            if position is None:
                continue
            position_features = features.setdefault(position, {})
            if "secondary_structure" in residue:
                position_features["secondary_structure"] = residue.get("secondary_structure")
            if "solvent_accessibility" in residue:
                position_features["solvent_accessibility"] = residue.get("solvent_accessibility")

        for distance in _distance_matrix(structure.get("ligand_summary")):
            position = _as_int_or_none(distance.get("sequence_position"))
            ligand_distance = _as_float_or_none(distance.get("min_distance_angstrom"))
            if position is None or ligand_distance is None:
                continue
            position_features = features.setdefault(position, {})
            current_distance = _as_float_or_none(position_features.get("distance_to_ligand"))
            if current_distance is None or ligand_distance < current_distance:
                position_features["distance_to_ligand"] = ligand_distance
    return features


def _structure_residues(chain_summary: Any) -> list[dict[str, Any]]:
    if not isinstance(chain_summary, dict):
        return []
    residues: list[dict[str, Any]] = []
    for chain in chain_summary.get("chains", []):
        if isinstance(chain, dict) and isinstance(chain.get("residues"), list):
            residues.extend([residue for residue in chain["residues"] if isinstance(residue, dict)])
    return residues


def _distance_matrix(ligand_summary: Any) -> list[dict[str, Any]]:
    if not isinstance(ligand_summary, dict) or not isinstance(ligand_summary.get("distance_matrix"), list):
        return []
    return [entry for entry in ligand_summary["distance_matrix"] if isinstance(entry, dict)]


def _mutation_counts_by_position(records: list[dict[str, Any]]) -> dict[int, tuple[int, int]]:
    counts: dict[int, tuple[int, int]] = {}
    for record in records:
        positions = _positions_from_mutation_record(record)
        is_beneficial = _has_beneficial_property_delta(record.get("property_delta"))
        for position in positions:
            current_count, current_beneficial = counts.get(position, (0, 0))
            counts[position] = (
                current_count + 1,
                current_beneficial + (1 if is_beneficial else 0),
            )
    return counts


def _positions_from_mutation_record(record: dict[str, Any]) -> list[int]:
    positions: list[int] = []
    mutation_positions = record.get("mutation_positions")
    if isinstance(mutation_positions, list):
        positions.extend(
            position
            for position in (_as_int_or_none(item.get("position")) for item in mutation_positions if isinstance(item, dict))
            if position is not None
        )
    if positions:
        return positions

    try:
        return [
            mutation.position
            for mutation in parse_mutation_string(str(record.get("mutation_string") or ""))
        ]
    except MutationParseError:
        return []


def _has_beneficial_property_delta(delta: Any) -> bool:
    if not isinstance(delta, dict):
        return False
    return any(_is_positive_delta(value) for value in delta.values())


def _is_positive_delta(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value > 0
    try:
        return float(str(value)) > 0
    except (TypeError, ValueError):
        return str(value).lower() in {"improved", "beneficial", "increase", "increased"}


def _rosetta_by_position(results: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    by_position: dict[int, list[dict[str, Any]]] = {}
    for result in results:
        mutation_string = str(result.get("mutation_string") or "")
        try:
            mutations = parse_mutation_string(mutation_string)
        except MutationParseError:
            continue
        ddg = _as_float_or_none(result.get("ddg_kcal_per_mol"))
        if ddg is None:
            continue
        for mutation in mutations:
            by_position.setdefault(mutation.position, []).append(
                {
                    "mutation_string": mutation_string.upper(),
                    "ddg_kcal_per_mol": ddg,
                    "interpretation": result.get("interpretation"),
                }
            )

    return {
        position: _rosetta_summary(results_for_position)
        for position, results_for_position in by_position.items()
    }


def _rosetta_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    sorted_results = sorted(results, key=lambda result: result["ddg_kcal_per_mol"])
    best = sorted_results[0]
    return {
        "best_mutation": best["mutation_string"],
        "best_ddg_kcal_per_mol": best["ddg_kcal_per_mol"],
        "results": sorted_results,
    }


def _solubility_risk(wildtype: str) -> str:
    if wildtype in {"C", "F", "I", "L", "M", "V", "W", "Y"}:
        return "medium"
    return "low"


def _unavailable_features(record: ResidueFeatureRecord) -> list[str]:
    unavailable = []
    for field_name in (
        "conservation_score",
        "wildtype_frequency",
        "secondary_structure",
        "solvent_accessibility",
        "distance_to_ligand",
        "distance_to_predicted_pocket",
        "rosetta_ddg",
    ):
        if getattr(record, field_name) is None:
            unavailable.append(field_name)
    return unavailable


def _as_int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _as_float_or_none(value: Any) -> float | None:
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


def _as_string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None
