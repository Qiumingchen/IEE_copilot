from app.services.structure_parser import parse_structure_text


PDB_COMPLEX = """\
ATOM      1  N   MET A   1      11.104  13.207   9.342  1.00 20.00           N
ATOM      2  CA  MET A   1      12.560  13.407   9.142  1.00 20.00           C
ATOM      3  C   MET A   1      13.104  12.107   8.542  1.00 20.00           C
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


def test_parse_pdb_classifies_without_hetero_ligands_as_apo():
    summary = parse_structure_text(PDB_APO, file_name="apo.pdb")

    assert summary.complex_state == "apo"
    assert summary.ligand_summary["ligand_count"] == 0
