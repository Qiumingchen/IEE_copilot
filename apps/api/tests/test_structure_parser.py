from app.services.structure_parser import parse_structure_text


PDB_COMPLEX = """\
ATOM      1  N   MET A   1      11.104  13.207   9.342  1.00 20.00           N
ATOM      2  CA  MET A   1      12.560  13.407   9.142  1.00 20.00           C
ATOM      3  C   MET A   1      12.104  13.107   8.542  1.00 20.00           C
ATOM      4  N   GLY A   2      14.104  11.907   8.242  1.00 20.00           N
ATOM      5  CA  GLY A   2      15.560  11.407   8.142  1.00 20.00           C
HETATM    6  C1  AQ1 B 501      16.000  11.000   8.000  1.00 20.00           C
HETATM    7  O1  AQ1 B 501      16.200  11.200   8.200  1.00 20.00           O
HETATM    8 ZN    ZN C 601      18.000  10.000   8.000  1.00 20.00          ZN
HETATM    9  O   HOH A 701      19.000  10.000   8.000  1.00 20.00           O
END
"""


PDB_APO = """\
ATOM      1  N   ALA A   1      11.104  13.207   9.342  1.00 20.00           N
ATOM      2  CA  ALA A   1      12.560  13.407   9.142  1.00 20.00           C
END
"""


CIF_COMPLEX = """\
data_demo
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_seq_id
_atom_site.pdbx_PDB_ins_code
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
ATOM 1 N N MET A 1 ? 11.104 13.207 9.342
ATOM 2 C CA MET A 1 ? 12.560 13.407 9.142
ATOM 3 N N GLY A 2 ? 14.104 11.907 8.242
ATOM 4 C CA GLY A 2 ? 15.560 11.407 8.142
HETATM 5 C C1 AQ1 B 501 ? 16.000 11.000 8.000
HETATM 6 O O1 AQ1 B 501 ? 16.200 11.200 8.200
#
"""


def test_parse_pdb_extracts_chains_ligands_metals_and_complex_state():
    summary = parse_structure_text(PDB_COMPLEX, file_name="complex.pdb")

    assert summary.structure_type == "uploaded_pdb"
    assert summary.complex_state == "enzyme_substrate_complex"
    assert summary.chain_summary["chain_count"] == 1
    assert summary.chain_summary["chains"][0]["chain_id"] == "A"
    assert summary.chain_summary["chains"][0]["sequence"] == "MG"
    assert summary.ligand_summary["ligand_count"] == 1
    assert summary.ligand_summary["ligands"][0]["ligand_code"] == "AQ1"
    assert summary.ligand_summary["ligands"][0]["chain_id"] == "B"
    assert summary.ligand_summary["metal_ions"][0]["ligand_code"] == "ZN"
    assert summary.chain_summary["preview_atoms"] == [
        {
            "kind": "protein",
            "chain_id": "A",
            "residue_number": "1",
            "sequence_position": 1,
            "label": "M1",
            "x": 12.56,
            "y": 13.407,
            "z": 9.142,
        },
        {
            "kind": "protein",
            "chain_id": "A",
            "residue_number": "2",
            "sequence_position": 2,
            "label": "G2",
            "x": 15.56,
            "y": 11.407,
            "z": 8.142,
        },
        {
            "kind": "ligand",
            "chain_id": "B",
            "residue_number": "501",
            "sequence_position": None,
            "label": "AQ1",
            "x": 16.1,
            "y": 11.1,
            "z": 8.1,
        },
    ]


def test_parse_pdb_maps_pdb_residues_to_sequence_positions():
    summary = parse_structure_text(PDB_COMPLEX, file_name="complex.pdb")

    residues = summary.chain_summary["chains"][0]["residues"]

    assert residues == [
        {
            "chain_id": "A",
            "residue_number": "1",
            "insertion_code": "",
            "sequence_position": 1,
            "residue_name": "MET",
            "one_letter": "M",
        },
        {
            "chain_id": "A",
            "residue_number": "2",
            "insertion_code": "",
            "sequence_position": 2,
            "residue_name": "GLY",
            "one_letter": "G",
        },
    ]
    assert summary.chain_summary["chains"][0]["mapping_quality"] == "complete"


def test_parse_pdb_reports_ligand_neighbor_residues_by_cutoff():
    summary = parse_structure_text(PDB_COMPLEX, file_name="complex.pdb")

    ligand = summary.ligand_summary["ligands"][0]

    assert ligand["nearest_residues"]["4A"] == [
        {
            "chain_id": "A",
            "residue_number": "2",
            "insertion_code": "",
            "sequence_position": 2,
            "residue_name": "GLY",
            "one_letter": "G",
            "min_distance_angstrom": 0.6,
        }
    ]
    assert [residue["sequence_position"] for residue in ligand["nearest_residues"]["6A"]] == [2, 1]
    assert [residue["sequence_position"] for residue in ligand["nearest_residues"]["8A"]] == [2, 1]
    assert summary.ligand_summary["distance_matrix"][0] == {
        "ligand_code": "AQ1",
        "ligand_chain_id": "B",
        "ligand_residue_number": "501",
        "residue_chain_id": "A",
        "residue_number": "2",
        "insertion_code": "",
        "sequence_position": 2,
        "min_distance_angstrom": 0.6,
    }


def test_parse_pdb_classifies_without_hetero_ligands_as_apo():
    summary = parse_structure_text(PDB_APO, file_name="apo.pdb")

    assert summary.complex_state == "apo"
    assert summary.ligand_summary["ligand_count"] == 0


def test_parse_cif_atom_site_loop_extracts_chains_ligands_and_distances():
    summary = parse_structure_text(CIF_COMPLEX, file_name="complex.cif")

    assert summary.structure_type == "uploaded_cif"
    assert summary.complex_state == "enzyme_substrate_complex"
    assert summary.chain_summary["chains"][0]["chain_id"] == "A"
    assert summary.chain_summary["chains"][0]["sequence"] == "MG"
    assert summary.ligand_summary["ligands"][0]["ligand_code"] == "AQ1"
    assert summary.ligand_summary["ligands"][0]["chain_id"] == "B"
    assert summary.ligand_summary["distance_matrix"][0]["sequence_position"] == 2
    assert summary.chain_summary["preview_atoms"] == [
        {
            "kind": "protein",
            "chain_id": "A",
            "residue_number": "1",
            "sequence_position": 1,
            "label": "M1",
            "x": 12.56,
            "y": 13.407,
            "z": 9.142,
        },
        {
            "kind": "protein",
            "chain_id": "A",
            "residue_number": "2",
            "sequence_position": 2,
            "label": "G2",
            "x": 15.56,
            "y": 11.407,
            "z": 8.142,
        },
        {
            "kind": "ligand",
            "chain_id": "B",
            "residue_number": "501",
            "sequence_position": None,
            "label": "AQ1",
            "x": 16.1,
            "y": 11.1,
            "z": 8.1,
        },
    ]
