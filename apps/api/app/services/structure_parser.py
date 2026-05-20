from dataclasses import dataclass
from pathlib import Path
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

    chains = _summarize_chains(atom_rows)
    ligand_summary, ligands = _summarize_ligands(atom_rows)
    complex_state = "enzyme_substrate_complex" if ligand_summary["ligand_count"] > 0 else "apo"
    return ParsedStructure(
        structure_type=structure_type,
        complex_state=complex_state,
        chain_summary={
            "format": extension.lstrip("."),
            "chain_count": len(chains),
            "chains": chains,
            "warnings": [],
        },
        ligand_summary=ligand_summary,
        ligands=ligands,
    )


def _parse_pdb_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
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
            }
        )
    return rows


def _parse_cif_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
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
            }
        )
    return rows


def _summarize_chains(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    chain_residues: dict[str, list[tuple[str, str, str]]] = {}
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        if row["record"] != "ATOM":
            continue
        residue_name = row["residue_name"]
        if residue_name not in AMINO_ACIDS:
            continue
        key = (row["chain_id"], row["residue_number"], row["insertion_code"])
        if key in seen:
            continue
        seen.add(key)
        chain_residues.setdefault(row["chain_id"], []).append(
            (row["residue_number"], row["insertion_code"], residue_name)
        )

    chains: list[dict[str, Any]] = []
    for chain_id, residues in sorted(chain_residues.items()):
        sequence = "".join(AMINO_ACIDS[residue_name] for _, _, residue_name in residues)
        chains.append(
            {
                "chain_id": chain_id,
                "residue_count": len(residues),
                "sequence": sequence,
                "residue_numbers": [
                    f"{number}{insertion_code}" if insertion_code else number
                    for number, insertion_code, _ in residues
                ],
            }
        )
    return chains


def _summarize_ligands(
    rows: list[dict[str, str]]
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
                "ligand_type": "metal_ion" if target is metal_groups else "hetero_ligand",
            }
        target[group_key]["atom_count"] += 1

    ligands = sorted(ligand_groups.values(), key=lambda item: (item["chain_id"], item["residue_number"]))
    metal_ions = sorted(metal_groups.values(), key=lambda item: (item["chain_id"], item["residue_number"]))
    return (
        {
            "ligand_count": len(ligands),
            "metal_count": len(metal_ions),
            "ligands": ligands,
            "metal_ions": metal_ions,
        },
        ligands + metal_ions,
    )


def _is_metal(row: dict[str, str]) -> bool:
    residue_name = row["residue_name"].upper()
    element = row["element"].upper()
    return residue_name in METAL_CODES or element in METAL_CODES
