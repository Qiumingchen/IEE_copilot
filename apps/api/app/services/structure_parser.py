from dataclasses import dataclass
from math import dist
from pathlib import Path
import shlex
from typing import Any


AMINO_ACIDS = {
    "ALA": "A",
    "ARG": "R",
    "ASN": "N",
    "ASP": "D",
    "CYS": "C",
    "GLN": "Q",
    "GLU": "E",
    "GLY": "G",
    "HIS": "H",
    "ILE": "I",
    "LEU": "L",
    "LYS": "K",
    "MET": "M",
    "PHE": "F",
    "PRO": "P",
    "SER": "S",
    "THR": "T",
    "TRP": "W",
    "TYR": "Y",
    "VAL": "V",
}

WATER_CODES = {"HOH", "WAT", "DOD"}
METAL_CODES = {
    "CA",
    "CD",
    "CO",
    "CU",
    "FE",
    "K",
    "MG",
    "MN",
    "NA",
    "NI",
    "ZN",
}

CIF_MISSING_VALUES = {"?", "."}


class StructureParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedStructure:
    structure_type: str
    complex_state: str
    chain_summary: dict[str, Any]
    ligand_summary: dict[str, Any]
    ligands: list[dict[str, Any]]


def parse_structure_text(text: str, *, file_name: str) -> ParsedStructure:
    extension = Path(file_name).suffix.lower()
    if extension == ".pdb":
        atom_rows = _parse_pdb_rows(text)
        structure_type = "uploaded_pdb"
    elif extension == ".cif":
        atom_rows = _parse_cif_rows(text)
        structure_type = "uploaded_cif"
    else:
        raise StructureParseError("unsupported structure file type")

    if not atom_rows:
        raise StructureParseError("structure file does not contain atom records")

    protein_residues = _collect_protein_residues(atom_rows)
    chains = _summarize_chains(protein_residues)
    ligand_summary, ligands = _summarize_ligands(atom_rows, protein_residues)
    complex_state = "enzyme_substrate_complex" if ligand_summary["ligand_count"] > 0 else "apo"
    return ParsedStructure(
        structure_type=structure_type,
        complex_state=complex_state,
        chain_summary={
            "format": extension.lstrip("."),
            "chain_count": len(chains),
            "chains": chains,
            "preview_atoms": _build_preview_atoms(protein_residues, ligand_summary),
            "warnings": [],
        },
        ligand_summary=ligand_summary,
        ligands=ligands,
    )


def _parse_pdb_rows(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        record = line[0:6].strip()
        if record not in {"ATOM", "HETATM"}:
            continue
        rows.append(
            {
                "record": record,
                "atom_name": line[12:16].strip(),
                "residue_name": line[17:20].strip().upper(),
                "chain_id": line[21:22].strip() or "-",
                "residue_number": line[22:26].strip(),
                "insertion_code": line[26:27].strip(),
                "element": (line[76:78].strip() or line[12:16].strip()[:2]).upper(),
                "coord": _parse_pdb_coord(line),
            }
        )
    return rows


def _parse_cif_rows(text: str) -> list[dict[str, Any]]:
    loop_rows = _parse_cif_atom_site_loop_rows(text)
    if loop_rows:
        return loop_rows

    return _parse_positional_cif_rows(text)


def _parse_positional_cif_rows(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("ATOM ", "HETATM ")):
            continue
        parts = stripped.split()
        if len(parts) < 9:
            continue
        rows.append(
            {
                "record": parts[0],
                "atom_name": parts[3],
                "residue_name": parts[5].upper(),
                "chain_id": parts[6] or "-",
                "residue_number": parts[8],
                "insertion_code": "",
                "element": parts[2].upper(),
                "coord": _parse_cif_coord(parts),
            }
        )
    return rows


def _parse_cif_atom_site_loop_rows(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if lines[index].strip() != "loop_":
            index += 1
            continue

        index += 1
        columns: list[str] = []
        while index < len(lines):
            stripped = lines[index].strip()
            if not stripped.startswith("_"):
                break
            columns.append(stripped.split()[0])
            index += 1

        if not columns or not any(column.startswith("_atom_site.") for column in columns):
            continue

        column_indexes = {column: position for position, column in enumerate(columns)}
        while index < len(lines):
            stripped = lines[index].strip()
            if (
                not stripped
                or stripped == "#"
                or stripped == "loop_"
                or stripped.startswith("_")
                or stripped.startswith("data_")
            ):
                break
            parts = _split_cif_row(stripped)
            if parts:
                row = _cif_atom_site_row_from_columns(parts, column_indexes)
                if row is not None:
                    rows.append(row)
            index += 1

    return rows


def _split_cif_row(row: str) -> list[str]:
    try:
        return shlex.split(row, posix=False)
    except ValueError:
        return row.split()


def _cif_atom_site_row_from_columns(
    parts: list[str],
    column_indexes: dict[str, int],
) -> dict[str, Any] | None:
    record = _cif_value(parts, column_indexes, "_atom_site.group_PDB")
    if record not in {"ATOM", "HETATM"}:
        return None

    residue_name = _cif_value(
        parts,
        column_indexes,
        "_atom_site.label_comp_id",
        "_atom_site.auth_comp_id",
    )
    if not residue_name:
        return None

    chain_id = _cif_value(
        parts,
        column_indexes,
        "_atom_site.auth_asym_id",
        "_atom_site.label_asym_id",
        default="-",
    )
    residue_number = _cif_value(
        parts,
        column_indexes,
        "_atom_site.auth_seq_id",
        "_atom_site.label_seq_id",
    )
    if not residue_number:
        return None

    return {
        "record": record,
        "atom_name": _cif_value(
            parts,
            column_indexes,
            "_atom_site.label_atom_id",
            "_atom_site.auth_atom_id",
        ),
        "residue_name": residue_name.upper(),
        "chain_id": chain_id,
        "residue_number": residue_number,
        "insertion_code": _cif_value(parts, column_indexes, "_atom_site.pdbx_PDB_ins_code"),
        "element": _cif_value(parts, column_indexes, "_atom_site.type_symbol").upper(),
        "coord": _parse_cif_coord_from_columns(parts, column_indexes),
    }


def _cif_value(
    parts: list[str],
    column_indexes: dict[str, int],
    *column_names: str,
    default: str = "",
) -> str:
    for column_name in column_names:
        column_index = column_indexes.get(column_name)
        if column_index is None or column_index >= len(parts):
            continue
        value = parts[column_index].strip("'\"")
        if value not in CIF_MISSING_VALUES:
            return value
    return default


def _parse_pdb_coord(line: str) -> tuple[float, float, float] | None:
    try:
        return (float(line[30:38]), float(line[38:46]), float(line[46:54]))
    except ValueError:
        return None


def _parse_cif_coord(parts: list[str]) -> tuple[float, float, float] | None:
    for start in (10, 9):
        try:
            return (float(parts[start]), float(parts[start + 1]), float(parts[start + 2]))
        except (IndexError, ValueError):
            continue
    return None


def _parse_cif_coord_from_columns(
    parts: list[str],
    column_indexes: dict[str, int],
) -> tuple[float, float, float] | None:
    try:
        return (
            float(parts[column_indexes["_atom_site.Cartn_x"]]),
            float(parts[column_indexes["_atom_site.Cartn_y"]]),
            float(parts[column_indexes["_atom_site.Cartn_z"]]),
        )
    except (KeyError, IndexError, ValueError):
        return None


def _collect_protein_residues(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    residues_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        if row["record"] != "ATOM" or row["residue_name"] not in AMINO_ACIDS:
            continue
        key = (row["chain_id"], row["residue_number"], row["insertion_code"])
        if key not in residues_by_key:
            residues_by_key[key] = {
                "chain_id": row["chain_id"],
                "residue_number": row["residue_number"],
                "insertion_code": row["insertion_code"],
                "residue_name": row["residue_name"],
                "one_letter": AMINO_ACIDS[row["residue_name"]],
                "atoms": [],
                "representative_coord": None,
            }
        if row["coord"] is not None:
            residues_by_key[key]["atoms"].append(row["coord"])
            if row["atom_name"] == "CA":
                residues_by_key[key]["representative_coord"] = row["coord"]

    sequence_positions: dict[str, int] = {}
    residues: list[dict[str, Any]] = []
    for residue in residues_by_key.values():
        chain_id = residue["chain_id"]
        sequence_positions[chain_id] = sequence_positions.get(chain_id, 0) + 1
        residue["sequence_position"] = sequence_positions[chain_id]
        residues.append(residue)
    return residues


def _summarize_chains(protein_residues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chain_residues: dict[str, list[dict[str, Any]]] = {}
    for residue in protein_residues:
        chain_residues.setdefault(residue["chain_id"], []).append(residue)

    chains: list[dict[str, Any]] = []
    for chain_id, residues in sorted(chain_residues.items()):
        sequence = "".join(residue["one_letter"] for residue in residues)
        chains.append(
            {
                "chain_id": chain_id,
                "residue_count": len(residues),
                "sequence": sequence,
                "residue_numbers": [
                    f"{residue['residue_number']}{residue['insertion_code']}"
                    if residue["insertion_code"]
                    else residue["residue_number"]
                    for residue in residues
                ],
                "residues": [
                    {
                        "chain_id": residue["chain_id"],
                        "residue_number": residue["residue_number"],
                        "insertion_code": residue["insertion_code"],
                        "sequence_position": residue["sequence_position"],
                        "residue_name": residue["residue_name"],
                        "one_letter": residue["one_letter"],
                    }
                    for residue in residues
                ],
                "mapping_quality": "complete",
            }
        )
    return chains


def _summarize_ligands(
    rows: list[dict[str, Any]], protein_residues: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ligand_groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    metal_groups: dict[tuple[str, str, str], dict[str, Any]] = {}

    for row in rows:
        if row["record"] != "HETATM":
            continue
        residue_name = row["residue_name"]
        if residue_name in WATER_CODES:
            continue
        group_key = (residue_name, row["chain_id"], row["residue_number"])
        target = metal_groups if _is_metal(row) else ligand_groups
        if group_key not in target:
            target[group_key] = {
                "ligand_name": residue_name,
                "ligand_code": residue_name,
                "chain_id": row["chain_id"],
                "residue_number": row["residue_number"],
                "atom_count": 0,
                "atoms": [],
                "ligand_type": "metal_ion" if target is metal_groups else "hetero_ligand",
            }
        target[group_key]["atom_count"] += 1
        if row["coord"] is not None:
            target[group_key]["atoms"].append(row["coord"])

    distance_matrix: list[dict[str, Any]] = []
    for ligand in ligand_groups.values():
        residue_distances = _calculate_ligand_residue_distances(ligand, protein_residues)
        ligand["nearest_residues"] = {
            f"{cutoff}A": [
                residue for residue in residue_distances if residue["min_distance_angstrom"] <= cutoff
            ]
            for cutoff in (4, 6, 8)
        }
        ligand["residue_distances"] = residue_distances
        for residue_distance in residue_distances:
            distance_matrix.append(
                {
                    "ligand_code": ligand["ligand_code"],
                    "ligand_chain_id": ligand["chain_id"],
                    "ligand_residue_number": ligand["residue_number"],
                    "residue_chain_id": residue_distance["chain_id"],
                    "residue_number": residue_distance["residue_number"],
                    "insertion_code": residue_distance["insertion_code"],
                    "sequence_position": residue_distance["sequence_position"],
                    "min_distance_angstrom": residue_distance["min_distance_angstrom"],
                }
            )

    ligands = [_public_ligand(ligand) for ligand in sorted(ligand_groups.values(), key=_ligand_sort_key)]
    metal_ions = [_public_ligand(ligand) for ligand in sorted(metal_groups.values(), key=_ligand_sort_key)]
    distance_matrix.sort(
        key=lambda item: (
            item["min_distance_angstrom"],
            item["residue_chain_id"],
            item["sequence_position"],
            item["ligand_code"],
        )
    )
    return (
        {
            "ligand_count": len(ligands),
            "metal_count": len(metal_ions),
            "ligands": ligands,
            "metal_ions": metal_ions,
            "distance_matrix": distance_matrix,
        },
        ligands + metal_ions,
    )


def _calculate_ligand_residue_distances(
    ligand: dict[str, Any], protein_residues: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    distances: list[dict[str, Any]] = []
    if not ligand["atoms"]:
        return distances

    for residue in protein_residues:
        if not residue["atoms"]:
            continue
        min_distance = min(
            dist(ligand_atom, residue_atom)
            for ligand_atom in ligand["atoms"]
            for residue_atom in residue["atoms"]
        )
        distances.append(
            {
                "chain_id": residue["chain_id"],
                "residue_number": residue["residue_number"],
                "insertion_code": residue["insertion_code"],
                "sequence_position": residue["sequence_position"],
                "residue_name": residue["residue_name"],
                "one_letter": residue["one_letter"],
                "min_distance_angstrom": round(min_distance, 1),
            }
        )
    distances.sort(
        key=lambda item: (
            item["min_distance_angstrom"],
            item["chain_id"],
            item["sequence_position"],
        )
    )
    return distances


def _public_ligand(ligand: dict[str, Any]) -> dict[str, Any]:
    public_ligand = {key: value for key, value in ligand.items() if key != "atoms"}
    center = _centroid(ligand.get("atoms", []))
    if center is not None:
        public_ligand["coord_center"] = center
    return public_ligand


def _build_preview_atoms(
    protein_residues: list[dict[str, Any]],
    ligand_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    preview_atoms: list[dict[str, Any]] = []
    for residue in protein_residues:
        center = residue.get("representative_coord") or _centroid(residue.get("atoms", []))
        if center is None:
            continue
        preview_atoms.append(
            {
                "kind": "protein",
                "chain_id": residue["chain_id"],
                "residue_number": residue["residue_number"],
                "sequence_position": residue["sequence_position"],
                "label": f"{residue['one_letter']}{residue['sequence_position']}",
                "x": center[0],
                "y": center[1],
                "z": center[2],
            }
        )

    for ligand in ligand_summary.get("ligands", []):
        center = ligand.get("coord_center")
        if not _is_coord(center):
            continue
        preview_atoms.append(
            {
                "kind": "ligand",
                "chain_id": ligand["chain_id"],
                "residue_number": ligand["residue_number"],
                "sequence_position": None,
                "label": ligand["ligand_code"],
                "x": center[0],
                "y": center[1],
                "z": center[2],
            }
        )
    return preview_atoms[:500]


def _centroid(coords: list[Any]) -> tuple[float, float, float] | None:
    valid_coords = [
        coord for coord in coords
        if isinstance(coord, tuple) and len(coord) == 3
    ]
    if not valid_coords:
        return None
    return (
        round(sum(coord[0] for coord in valid_coords) / len(valid_coords), 3),
        round(sum(coord[1] for coord in valid_coords) / len(valid_coords), 3),
        round(sum(coord[2] for coord in valid_coords) / len(valid_coords), 3),
    )


def _is_coord(value: Any) -> bool:
    return (
        isinstance(value, tuple)
        and len(value) == 3
        and all(isinstance(component, float) for component in value)
    )


def _ligand_sort_key(item: dict[str, Any]) -> tuple[str, str]:
    return (item["chain_id"], item["residue_number"])


def _is_metal(row: dict[str, Any]) -> bool:
    residue_name = row["residue_name"].upper()
    element = row["element"].upper()
    return residue_name in METAL_CODES or element in METAL_CODES
