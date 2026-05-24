from app.db.models import EnzymeModule
from app.services.query_resolver import QueryKind, resolve_query


def test_resolve_uniprot_accession():
    resolved = resolve_query("P81453")

    assert resolved.kind == QueryKind.UNIPROT
    assert resolved.normalized_query == "P81453"


def test_resolve_ten_character_uniprot_accession():
    resolved = resolve_query("A0A024RBG1")

    assert resolved.kind == QueryKind.UNIPROT
    assert resolved.normalized_query == "A0A024RBG1"


def test_resolve_pdb_id():
    resolved = resolve_query("1IU4")

    assert resolved.kind == QueryKind.PDB
    assert resolved.normalized_query == "1IU4"


def test_resolve_alphafold_id():
    resolved = resolve_query("af-p81453-f1")

    assert resolved.kind == QueryKind.ALPHAFOLD
    assert resolved.normalized_query == "AF-P81453-F1"


def test_resolve_ec_number():
    resolved = resolve_query("2.3.2.13")

    assert resolved.kind == QueryKind.EC
    assert resolved.normalized_query == "2.3.2.13"


def test_resolve_amino_acid_sequence():
    resolved = resolve_query("AEAKLLNDTLLAIGGQDPVKAQVLSVSGGDAKQAGVYAVTQGNGDKVTVEQSNNG")

    assert resolved.kind == QueryKind.SEQUENCE
    assert resolved.normalized_query == "AEAKLLNDTLLAIGGQDPVKAQVLSVSGGDAKQAGVYAVTQGNGDKVTVEQSNNG"


def test_detect_mtgase_module_from_keyword():
    resolved = resolve_query("microbial transglutaminase")

    assert resolved.module_hint == EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE


def test_detect_anthraquinone_module_from_keyword():
    resolved = resolve_query("anthraquinone glycosyltransferase")

    assert resolved.module_hint == EnzymeModule.ANTHRAQUINONE_GLYCOSYLTRANSFERASE
