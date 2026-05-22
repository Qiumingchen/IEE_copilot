from sqlalchemy import select

from app.db.models import (
    AnalysisArtifact,
    AnalysisJob,
    EnzymeEntry,
    EnzymeFamily,
    EnzymeModule,
    JobStatus,
    KineticRecord,
    LiteratureReference,
    MutationRecord,
    ProteinSequence,
    PropertyRecord,
    StructureEntry,
    Visibility,
)


PDB_COMPLEX_UPLOAD = """\
ATOM      1  N   MET A   1      11.104  13.207   9.342  1.00 20.00           N
ATOM      2  CA  MET A   1      12.560  13.407   9.142  1.00 20.00           C
ATOM      3  N   GLY A   2      14.104  11.907   8.242  1.00 20.00           N
ATOM      4  CA  GLY A   2      15.560  11.407   8.142  1.00 20.00           C
HETATM    5  C1  AQ1 B 501      16.000  11.000   8.000  1.00 20.00           C
HETATM    6 ZN    ZN C 601      18.000  10.000   8.000  1.00 20.00          ZN
END
"""


CIF_COMPLEX_UPLOAD = """\
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
#
"""


def _auth_headers(client) -> dict[str, str]:
    client.post(
        "/auth/register",
        json={
            "email": "records@example.com",
            "password": "records-password",
            "display_name": "Records Engineer",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "records@example.com", "password": "records-password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _enzyme_id(db_session) -> str:
    family = EnzymeFamily(
        module=EnzymeModule.ANTHRAQUINONE_GLYCOSYLTRANSFERASE,
        name="Anthraquinone glycosyltransferases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="UGT example",
        organism="Streptomyces sp.",
        source="test",
    )
    db_session.add(enzyme)
    db_session.commit()
    return enzyme.id


def test_create_and_list_enzyme_domain_records(client, db_session):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)

    substrate_response = client.post(
        f"/enzymes/{enzyme_id}/substrates",
        headers=headers,
        json={
            "name": "anthraquinone substrate 1",
            "substrate_class": "anthraquinone",
            "smiles": "O=C1C=CC2=CC=CC=C2C1=O",
        },
    )
    assert substrate_response.status_code == 201
    substrate_id = substrate_response.json()["id"]

    structure_response = client.post(
        f"/enzymes/{enzyme_id}/structures",
        headers=headers,
        json={
            "structure_type": "uploaded_pdb",
            "complex_state": "enzyme_substrate_complex",
            "source": "user_upload",
            "ligands": [
                {
                    "ligand_name": "anthraquinone substrate 1",
                    "ligand_code": "AQ1",
                    "ligand_type": "substrate",
                    "chain_id": "A",
                    "residue_number": "501",
                    "smiles": "O=C1C=CC2=CC=CC=C2C1=O",
                }
            ],
        },
    )
    assert structure_response.status_code == 201
    assert structure_response.json()["ligands"][0]["ligand_code"] == "AQ1"

    property_response = client.post(
        f"/enzymes/{enzyme_id}/properties",
        headers=headers,
        json={
            "property_type": "optimal_temperature",
            "value_original": "55",
            "unit_original": "degC",
            "substrate": "anthraquinone substrate 1",
            "assay_temperature": "55",
            "assay_pH": "7.5",
        },
    )
    assert property_response.status_code == 201
    assert property_response.json()["property_type"] == "optimal_temperature"

    kinetic_response = client.post(
        f"/enzymes/{enzyme_id}/kinetics",
        headers=headers,
        json={
            "substrate": "anthraquinone substrate 1",
            "km": "1.8",
            "kcat": "24.2",
            "unit_original": "mM; s^-1",
            "assay_temperature": "45",
            "assay_pH": "7.5",
        },
    )
    assert kinetic_response.status_code == 201
    assert kinetic_response.json()["kcat"] == "24.2"

    expression_response = client.post(
        f"/enzymes/{enzyme_id}/expression",
        headers=headers,
        json={
            "expression_host": "E. coli BL21(DE3)",
            "vector": "pET-28a",
            "expression_level_original": "48",
            "expression_level_standardized": "48",
            "soluble_expression": "high",
            "unit_original": "mg/L",
            "unit_standardized": "mg/L",
            "condition": {
                "substrate_entry_id": substrate_id,
                "assay_temperature": "30",
                "assay_pH": "7.0",
                "buffer": "Tris-HCl",
                "method": "shake flask expression",
            },
        },
    )
    assert expression_response.status_code == 201
    assert expression_response.json()["condition"]["substrate_entry_id"] == substrate_id

    list_substrates = client.get(f"/enzymes/{enzyme_id}/substrates", headers=headers)
    list_structures = client.get(f"/enzymes/{enzyme_id}/structures", headers=headers)
    list_properties = client.get(f"/enzymes/{enzyme_id}/properties", headers=headers)
    list_kinetics = client.get(f"/enzymes/{enzyme_id}/kinetics", headers=headers)
    list_expression = client.get(f"/enzymes/{enzyme_id}/expression", headers=headers)

    assert [item["name"] for item in list_substrates.json()] == ["anthraquinone substrate 1"]
    assert list_structures.json()[0]["ligands"][0]["ligand_type"] == "substrate"
    assert list_properties.json()[0]["value_original"] == "55"
    assert list_kinetics.json()[0]["km"] == "1.8"
    assert list_expression.json()[0]["condition"]["method"] == "shake flask expression"


def test_list_evidence_records_embed_literature_reference(client, db_session):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    reference = LiteratureReference(
        title="Traceable MTGase evidence",
        journal="Biocatalysis Reports",
        year=2024,
        doi="10.1000/traceable",
        source="curated_literature",
        metadata_json={"provenance": {"provider": "curated_literature", "mode": "curated"}},
    )
    db_session.add(reference)
    db_session.flush()
    db_session.add_all(
        [
            PropertyRecord(
                enzyme_entry_id=enzyme_id,
                property_type="optimal_temperature",
                value_original="58",
                unit_original="degC",
                reference_id=reference.id,
                evidence_text="Optimum temperature reported in Table 1",
                visibility=Visibility.PUBLIC,
            ),
            KineticRecord(
                enzyme_entry_id=enzyme_id,
                substrate="casein",
                km="2.1",
                kcat="31",
                reference_id=reference.id,
                visibility=Visibility.PUBLIC,
            ),
            MutationRecord(
                enzyme_entry_id=enzyme_id,
                mutation_string="S2P",
                mutation_positions=[{"wildtype": "S", "position": 2, "mutant": "P"}],
                effect_summary="Improved thermostability",
                reference_id=reference.id,
                visibility=Visibility.PUBLIC,
            ),
        ]
    )
    db_session.commit()

    properties = client.get(f"/enzymes/{enzyme_id}/properties", headers=headers).json()
    kinetics = client.get(f"/enzymes/{enzyme_id}/kinetics", headers=headers).json()
    mutations = client.get(f"/enzymes/{enzyme_id}/mutations", headers=headers).json()

    assert properties[0]["reference"]["doi"] == "10.1000/traceable"
    assert properties[0]["reference"]["title"] == "Traceable MTGase evidence"
    assert properties[0]["reference"]["provenance"] == {
        "provider": "curated_literature",
        "mode": "curated",
    }
    assert kinetics[0]["reference"]["doi"] == "10.1000/traceable"
    assert mutations[0]["reference"]["doi"] == "10.1000/traceable"


def test_upload_structure_file_saves_artifact_and_parsed_structure(client, db_session, monkeypatch):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)

    def fake_store_structure_file(*, file_name, content, content_type):
        assert file_name == "complex.pdb"
        assert b"AQ1" in content
        assert content_type == "chemical/x-pdb"
        return {
            "bucket": "iee-artifacts",
            "object_key": "structures/test/complex.pdb",
            "checksum": "checksum",
            "content_type": content_type,
            "size_bytes": len(content),
        }

    monkeypatch.setattr(
        "app.api.routes.enzyme_records.store_structure_file",
        fake_store_structure_file,
    )

    response = client.post(
        f"/enzymes/{enzyme_id}/structures/upload",
        headers=headers,
        files={
            "file": (
                "complex.pdb",
                PDB_COMPLEX_UPLOAD.encode(),
                "chemical/x-pdb",
            )
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["structure_type"] == "uploaded_pdb"
    assert body["complex_state"] == "enzyme_substrate_complex"
    assert body["artifact"]["object_key"] == "structures/test/complex.pdb"
    assert body["chain_summary"]["chains"][0]["sequence"] == "MG"
    assert body["ligand_summary"]["ligands"][0]["ligand_code"] == "AQ1"
    assert body["ligand_summary"]["metal_ions"][0]["ligand_code"] == "ZN"
    assert body["ligands"][0]["ligand_code"] == "AQ1"


def test_upload_cif_structure_file_saves_artifact_and_parsed_structure(client, db_session, monkeypatch):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)

    def fake_store_structure_file(*, file_name, content, content_type):
        assert file_name == "complex.cif"
        assert b"_atom_site.group_PDB" in content
        assert content_type == "chemical/x-cif"
        return {
            "bucket": "iee-artifacts",
            "object_key": "structures/test/complex.cif",
            "checksum": "checksum-cif",
            "content_type": content_type,
            "size_bytes": len(content),
        }

    monkeypatch.setattr(
        "app.api.routes.enzyme_records.store_structure_file",
        fake_store_structure_file,
    )

    response = client.post(
        f"/enzymes/{enzyme_id}/structures/upload",
        headers=headers,
        files={
            "file": (
                "complex.cif",
                CIF_COMPLEX_UPLOAD.encode(),
                "chemical/x-cif",
            )
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["structure_type"] == "uploaded_cif"
    assert body["complex_state"] == "enzyme_substrate_complex"
    assert body["artifact"]["object_key"] == "structures/test/complex.cif"
    assert body["chain_summary"]["format"] == "cif"
    assert body["chain_summary"]["chains"][0]["sequence"] == "MG"
    assert body["ligand_summary"]["ligands"][0]["ligand_code"] == "AQ1"


def test_download_structure_file_returns_stored_artifact(client, db_session, monkeypatch):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    artifact = AnalysisArtifact(
        enzyme_entry_id=enzyme_id,
        artifact_type="structure_file",
        bucket="iee-artifacts",
        object_key="structures/test/complex.pdb",
        checksum="checksum",
        content_type="chemical/x-pdb",
        size_bytes=len(PDB_COMPLEX_UPLOAD.encode()),
    )
    db_session.add(artifact)
    db_session.flush()
    structure = StructureEntry(
        enzyme_entry_id=enzyme_id,
        structure_type="uploaded_pdb",
        complex_state="enzyme_substrate_complex",
        source="user_upload",
        artifact_id=artifact.id,
    )
    db_session.add(structure)
    db_session.commit()

    def fake_read_structure_file(*, object_key):
        assert object_key == "structures/test/complex.pdb"
        return PDB_COMPLEX_UPLOAD.encode()

    monkeypatch.setattr(
        "app.api.routes.enzyme_records.read_structure_file",
        fake_read_structure_file,
    )

    response = client.get(
        f"/enzymes/{enzyme_id}/structures/{structure.id}/file",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.content == PDB_COMPLEX_UPLOAD.encode()
    assert response.headers["content-type"] == "chemical/x-pdb"
    assert response.headers["content-disposition"] == 'attachment; filename="complex.pdb"'


def test_enzyme_domain_records_require_authentication(client, db_session):
    enzyme_id = _enzyme_id(db_session)

    response = client.get(f"/enzymes/{enzyme_id}/properties")

    assert response.status_code == 401


def test_list_analysis_artifacts_returns_epic_four_artifacts_with_job_status(client, db_session):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    job = AnalysisJob(
        enzyme_entry_id=enzyme_id,
        job_type="msa",
        status=JobStatus.FINISHED,
        result_summary_json={"sequence_count": 3},
    )
    db_session.add(job)
    db_session.flush()
    db_session.add_all(
        [
            AnalysisArtifact(
                enzyme_entry_id=enzyme_id,
                job_id=job.id,
                artifact_type="homolog_sequences",
                bucket="iee-artifacts",
                object_key=f"analysis-jobs/{job.id}/homolog-sequences.json",
                content_type="application/json",
                size_bytes=128,
            ),
            AnalysisArtifact(
                enzyme_entry_id=enzyme_id,
                job_id=job.id,
                artifact_type="msa",
                bucket="iee-artifacts",
                object_key=f"analysis-jobs/{job.id}/msa.fasta",
                content_type="text/x-fasta",
                size_bytes=256,
            ),
            AnalysisArtifact(
                enzyme_entry_id=enzyme_id,
                job_id=job.id,
                artifact_type="family_profile_summary",
                bucket="iee-artifacts",
                object_key=f"analysis-jobs/{job.id}/family-profile-summary.json",
                content_type="application/json",
                size_bytes=64,
            ),
        ]
    )
    db_session.commit()

    response = client.get(f"/enzymes/{enzyme_id}/analysis-artifacts", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert [item["artifact_type"] for item in body] == ["homolog_sequences", "msa"]
    assert body[0]["job_status"] == "finished"
    assert body[0]["result_summary_json"] == {"sequence_count": 3}
    assert body[1]["object_key"].endswith("/msa.fasta")


def test_get_analysis_artifact_content_returns_worker_payload(client, db_session):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    job = AnalysisJob(
        enzyme_entry_id=enzyme_id,
        job_type="msa",
        status=JobStatus.FINISHED,
        result_summary_json={
            "artifact_type": "msa",
            "msa_fasta": ">query\nACD\n>homolog_1\nACE",
            "runner": {
                "provider": "mafft",
                "mode": "fallback",
                "warning": "MAFFT executable not configured; mock alignment used.",
            },
        },
    )
    db_session.add(job)
    db_session.flush()
    artifact = AnalysisArtifact(
        enzyme_entry_id=enzyme_id,
        job_id=job.id,
        artifact_type="msa",
        bucket="iee-artifacts",
        object_key=f"analysis-jobs/{job.id}/msa.fasta",
        content_type="text/x-fasta",
        size_bytes=26,
    )
    db_session.add(artifact)
    db_session.commit()

    response = client.get(
        f"/enzymes/{enzyme_id}/analysis-artifacts/{artifact.id}/content",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["artifact_id"] == artifact.id
    assert body["artifact_type"] == "msa"
    assert body["content_type"] == "text/x-fasta"
    assert body["content_text"] == ">query\nACD\n>homolog_1\nACE"
    assert body["content_json"]["runner"]["provider"] == "mafft"
    assert body["content_json"]["runner"]["mode"] == "fallback"


def test_get_rosetta_artifact_content_returns_input_preparation_payload(client, db_session):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    job = AnalysisJob(
        enzyme_entry_id=enzyme_id,
        job_type="rosetta_ddg",
        status=JobStatus.FINISHED,
        result_summary_json={
            "artifact_type": "rosetta_ddg",
            "mutation_string": "L10A",
            "mutation_file": "L 10 A",
            "parsed_mutations": [{"wildtype": "L", "position": 10, "mutant": "A"}],
            "ddg_kcal_per_mol": -0.6,
            "interpretation": "stabilizing",
            "structure_id": "structure-1",
            "runner": {
                "provider": "rosetta",
                "mode": "fallback",
                "warning": "Rosetta runner not configured; placeholder ddG used.",
            },
        },
    )
    db_session.add(job)
    db_session.flush()
    artifact = AnalysisArtifact(
        enzyme_entry_id=enzyme_id,
        job_id=job.id,
        artifact_type="rosetta_ddg",
        bucket="iee-artifacts",
        object_key=f"analysis-jobs/{job.id}/rosetta-ddg.json",
        content_type="application/json",
        size_bytes=128,
    )
    db_session.add(artifact)
    db_session.commit()

    response = client.get(
        f"/enzymes/{enzyme_id}/analysis-artifacts/{artifact.id}/content",
        headers=headers,
    )

    assert response.status_code == 200
    content_json = response.json()["content_json"]
    assert content_json["mutation_string"] == "L10A"
    assert content_json["mutation_file"] == "L 10 A"
    assert content_json["parsed_mutations"] == [{"wildtype": "L", "position": 10, "mutant": "A"}]
    assert content_json["runner"]["provider"] == "rosetta"
    assert content_json["runner"]["mode"] == "fallback"


def test_get_mutation_recommendation_artifact_content_returns_structure_context(client, db_session):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    job = AnalysisJob(
        enzyme_entry_id=enzyme_id,
        job_type="mutation_recommendation",
        status=JobStatus.FINISHED,
        result_summary_json={
            "artifact_type": "mutation_recommendations",
            "candidate_count": 1,
            "structure_id": "structure-selected",
            "candidates": [
                {
                    "query_position": 10,
                    "wildtype_residue": "L",
                    "conservation_category": "variable",
                    "priority_score": 1.8,
                    "suggested_mutations": ["L10A"],
                }
            ],
        },
    )
    db_session.add(job)
    db_session.flush()
    artifact = AnalysisArtifact(
        enzyme_entry_id=enzyme_id,
        job_id=job.id,
        artifact_type="mutation_recommendations",
        bucket="iee-artifacts",
        object_key=f"analysis-jobs/{job.id}/mutation-recommendations.json",
        content_type="application/json",
        size_bytes=128,
    )
    db_session.add(artifact)
    db_session.commit()

    response = client.get(
        f"/enzymes/{enzyme_id}/analysis-artifacts/{artifact.id}/content",
        headers=headers,
    )

    assert response.status_code == 200
    content_json = response.json()["content_json"]
    assert content_json["structure_id"] == "structure-selected"
    assert content_json["candidates"][0]["suggested_mutations"] == ["L10A"]


def test_get_mutation_library_artifact_content_returns_library_payload(client, db_session):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    job = AnalysisJob(
        enzyme_entry_id=enzyme_id,
        job_type="library_design",
        status=JobStatus.FINISHED,
        result_summary_json={
            "artifact_type": "mutation_library",
            "library_size": 24,
            "plate_format": 96,
            "variant_count": 1,
            "variants": [
                {
                    "variant_id": "VAR-L10A-F12A",
                    "mutation_string": "L10A/F12A",
                    "order": 2,
                    "score": 2.1,
                    "risk_flags": ["ddg_destabilizing_member"],
                    "reasons": ["test reason"],
                }
            ],
            "plate_layout": [
                {
                    "well": "A1",
                    "variant_id": "WT",
                    "mutation_string": "WT",
                    "role": "wt_control",
                    "score": None,
                    "risk_flags": [],
                }
            ],
            "csv_text": "well,variant_id,mutation_string,role,score,risk_flags",
        },
    )
    db_session.add(job)
    db_session.flush()
    artifact = AnalysisArtifact(
        enzyme_entry_id=enzyme_id,
        job_id=job.id,
        artifact_type="mutation_library",
        bucket="iee-artifacts",
        object_key=f"analysis-jobs/{job.id}/mutation-library.json",
        content_type="application/json",
        size_bytes=512,
    )
    db_session.add(artifact)
    db_session.commit()

    response = client.get(
        f"/enzymes/{enzyme_id}/analysis-artifacts/{artifact.id}/content",
        headers=headers,
    )

    assert response.status_code == 200
    content_json = response.json()["content_json"]
    assert content_json["library_size"] == 24
    assert content_json["variants"][0]["mutation_string"] == "L10A/F12A"
    assert content_json["plate_layout"][0]["role"] == "wt_control"
    assert content_json["csv_text"].startswith("well,variant_id")


def test_create_analysis_job_queues_selected_worker_task(client, db_session, monkeypatch):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme_id,
            sequence="ACDEFGHIKLMNPQRSTVWY",
            mature_sequence="ACDEFGHIKLMNPQRSTVWY",
            source="test",
            checksum="analysis-job-sequence",
        )
    )
    db_session.commit()
    enqueued_job_ids = []

    class MsaTask:
        @staticmethod
        def delay(job_id):
            enqueued_job_ids.append(job_id)

    monkeypatch.setattr(
        "app.api.routes.enzyme_records.run_msa",
        MsaTask,
        raising=False,
    )

    response = client.post(
        f"/enzymes/{enzyme_id}/analysis-jobs",
        headers=headers,
        json={"job_type": "msa"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["enzyme_entry_id"] == enzyme_id
    assert body["job_type"] == "msa"
    assert body["status"] == "queued"
    assert body["parameters_json"]["requested_from"] == "enzyme_analysis_page"
    assert enqueued_job_ids == [body["id"]]

    job = db_session.get(AnalysisJob, body["id"])
    assert job is not None
    assert job.created_by is not None


def test_create_homolog_job_accepts_search_mode_and_sequence_count(client, db_session, monkeypatch):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme_id,
            sequence="ACDEFGHIKLMNPQRSTVWY",
            mature_sequence="ACDEFGHIKLMNPQRSTVWY",
            source="test",
            checksum="homolog-options-sequence",
        )
    )
    db_session.commit()
    enqueued_job_ids = []

    class HomologyTask:
        @staticmethod
        def delay(job_id):
            enqueued_job_ids.append(job_id)

    monkeypatch.setattr(
        "app.api.routes.enzyme_records.run_homology_collection",
        HomologyTask,
        raising=False,
    )

    response = client.post(
        f"/enzymes/{enzyme_id}/analysis-jobs",
        headers=headers,
        json={
            "job_type": "homolog_collection",
            "parameters_json": {
                "search_mode": "sequence_similarity",
                "max_sequences": 25,
            },
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["parameters_json"]["search_mode"] == "sequence_similarity"
    assert body["parameters_json"]["max_sequences"] == 25
    assert body["parameters_json"]["identity_min"] == 40
    assert body["parameters_json"]["identity_max"] == 95
    assert body["parameters_json"]["coverage_min"] == 70
    assert enqueued_job_ids == [body["id"]]


def test_create_msa_job_uses_latest_homolog_sequence_artifact(client, db_session, monkeypatch):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme_id,
            sequence="ACDEFGHIKLMNPQRSTVWY",
            mature_sequence="ACDEFGHIKLMNPQRSTVWY",
            source="test",
            checksum="msa-homolog-sequence",
        )
    )
    homolog_job = AnalysisJob(
        enzyme_entry_id=enzyme_id,
        job_type="homolog_collection",
        status=JobStatus.FINISHED,
        result_summary_json={
            "homologs": [
                {
                    "accession": "HOMOLOG_A",
                    "organism": "Bacillus subtilis",
                    "sequence": "ACDEFGHIKLMNPQRSTVWY",
                    "identity": 0.91,
                    "coverage": 1.0,
                },
                {
                    "accession": "HOMOLOG_B",
                    "organism": "Streptomyces coelicolor",
                    "sequence": "ACDEYGHIKLMNPQRSTVWY",
                    "identity": 0.84,
                    "coverage": 1.0,
                },
            ]
        },
    )
    db_session.add(homolog_job)
    db_session.flush()
    db_session.add(
        AnalysisArtifact(
            enzyme_entry_id=enzyme_id,
            job_id=homolog_job.id,
            artifact_type="homolog_sequences",
            bucket="iee-artifacts",
            object_key=f"analysis-jobs/{homolog_job.id}/homolog-sequences.json",
            content_type="application/json",
            size_bytes=512,
        )
    )
    db_session.commit()

    class MsaTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzyme_records.run_msa",
        MsaTask,
        raising=False,
    )

    response = client.post(
        f"/enzymes/{enzyme_id}/analysis-jobs",
        headers=headers,
        json={"job_type": "msa"},
    )

    assert response.status_code == 201
    parameters = response.json()["parameters_json"]
    assert [item["identifier"] for item in parameters["homologs"]] == ["HOMOLOG_A", "HOMOLOG_B"]
    assert [item["sequence"] for item in parameters["homologs"]] == [
        "ACDEFGHIKLMNPQRSTVWY",
        "ACDEYGHIKLMNPQRSTVWY",
    ]


def test_create_msa_job_uses_selected_homolog_sequence_artifact(client, db_session, monkeypatch):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme_id,
            sequence="ACDEFGHIKLMNPQRSTVWY",
            mature_sequence="ACDEFGHIKLMNPQRSTVWY",
            source="test",
            checksum="selected-msa-homolog-sequence",
        )
    )
    older_job = AnalysisJob(
        enzyme_entry_id=enzyme_id,
        job_type="homolog_collection",
        status=JobStatus.FINISHED,
        result_summary_json={
            "homologs": [
                {
                    "accession": "OLDER_HOMOLOG",
                    "organism": "Bacillus subtilis",
                    "sequence": "ACDEFGHIKLMNPQRSTVWY",
                }
            ]
        },
    )
    newer_job = AnalysisJob(
        enzyme_entry_id=enzyme_id,
        job_type="homolog_collection",
        status=JobStatus.FINISHED,
        result_summary_json={
            "homologs": [
                {
                    "accession": "NEWER_HOMOLOG",
                    "organism": "Streptomyces coelicolor",
                    "sequence": "ACDEYGHIKLMNPQRSTVWY",
                }
            ]
        },
    )
    db_session.add_all([older_job, newer_job])
    db_session.flush()
    older_artifact = AnalysisArtifact(
        enzyme_entry_id=enzyme_id,
        job_id=older_job.id,
        artifact_type="homolog_sequences",
        bucket="iee-artifacts",
        object_key=f"analysis-jobs/{older_job.id}/homolog-sequences.json",
        content_type="application/json",
        size_bytes=512,
    )
    db_session.add(older_artifact)
    db_session.add(
        AnalysisArtifact(
            enzyme_entry_id=enzyme_id,
            job_id=newer_job.id,
            artifact_type="homolog_sequences",
            bucket="iee-artifacts",
            object_key=f"analysis-jobs/{newer_job.id}/homolog-sequences.json",
            content_type="application/json",
            size_bytes=512,
        )
    )
    db_session.commit()

    class MsaTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr("app.api.routes.enzyme_records.run_msa", MsaTask, raising=False)

    response = client.post(
        f"/enzymes/{enzyme_id}/analysis-jobs",
        headers=headers,
        json={
            "job_type": "msa",
            "parameters_json": {"homolog_artifact_id": older_artifact.id},
        },
    )

    assert response.status_code == 201
    parameters = response.json()["parameters_json"]
    assert [item["identifier"] for item in parameters["homologs"]] == ["OLDER_HOMOLOG"]
    assert parameters["homolog_source"]["artifact_id"] == older_artifact.id


def test_create_msa_job_uses_custom_fasta_sequences(client, db_session, monkeypatch):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme_id,
            sequence="ACDEFGHIKLMNPQRSTVWY",
            mature_sequence="ACDEFGHIKLMNPQRSTVWY",
            source="test",
            checksum="custom-fasta-msa-sequence",
        )
    )
    db_session.commit()

    class MsaTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr("app.api.routes.enzyme_records.run_msa", MsaTask, raising=False)

    response = client.post(
        f"/enzymes/{enzyme_id}/analysis-jobs",
        headers=headers,
        json={
            "job_type": "msa",
            "parameters_json": {
                "custom_fasta": ">user_a\nACDEFGHIKL\n>user_b custom note\nACDEYGHIKL\n"
            },
        },
    )

    assert response.status_code == 201
    parameters = response.json()["parameters_json"]
    assert parameters["homolog_source"]["type"] == "custom_fasta"
    assert parameters["homologs"] == [
        {"identifier": "user_a", "sequence": "ACDEFGHIKL"},
        {"identifier": "user_b", "sequence": "ACDEYGHIKL"},
    ]


def test_create_conservation_job_uses_latest_msa_artifact(client, db_session, monkeypatch):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme_id,
            sequence="ACDEFGHIKL",
            mature_sequence="ACDEFGHIKL",
            source="test",
            checksum="conservation-msa-sequence",
        )
    )
    msa_job = AnalysisJob(
        enzyme_entry_id=enzyme_id,
        job_type="msa",
        status=JobStatus.FINISHED,
        result_summary_json={
            "msa_fasta": ">query\nACDEFGHIKL\n>HOMOLOG_A\nACDEFGHIVL\n",
        },
    )
    db_session.add(msa_job)
    db_session.flush()
    db_session.add(
        AnalysisArtifact(
            enzyme_entry_id=enzyme_id,
            job_id=msa_job.id,
            artifact_type="msa",
            bucket="iee-artifacts",
            object_key=f"analysis-jobs/{msa_job.id}/msa.fasta",
            content_type="text/x-fasta",
            size_bytes=64,
        )
    )
    db_session.commit()

    class ConservationTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzyme_records.run_conservation_profile",
        ConservationTask,
        raising=False,
    )

    response = client.post(
        f"/enzymes/{enzyme_id}/analysis-jobs",
        headers=headers,
        json={"job_type": "conservation_profile"},
    )

    assert response.status_code == 201
    parameters = response.json()["parameters_json"]
    assert parameters["aligned_records"] == [
        {"identifier": "query", "aligned_sequence": "ACDEFGHIKL"},
        {"identifier": "HOMOLOG_A", "aligned_sequence": "ACDEFGHIVL"},
    ]


def test_create_conservation_job_uses_selected_msa_artifact(client, db_session, monkeypatch):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme_id,
            sequence="ACDEFGHIKL",
            mature_sequence="ACDEFGHIKL",
            source="test",
            checksum="selected-conservation-msa-sequence",
        )
    )
    older_job = AnalysisJob(
        enzyme_entry_id=enzyme_id,
        job_type="msa",
        status=JobStatus.FINISHED,
        result_summary_json={
            "msa_fasta": ">query\nACDEFGHIKL\n>OLDER\nACDEFGHIVL\n",
        },
    )
    newer_job = AnalysisJob(
        enzyme_entry_id=enzyme_id,
        job_type="msa",
        status=JobStatus.FINISHED,
        result_summary_json={
            "msa_fasta": ">query\nACDEFGHIKL\n>NEWER\nACDEYGHIKL\n",
        },
    )
    db_session.add_all([older_job, newer_job])
    db_session.flush()
    older_artifact = AnalysisArtifact(
        enzyme_entry_id=enzyme_id,
        job_id=older_job.id,
        artifact_type="msa",
        bucket="iee-artifacts",
        object_key=f"analysis-jobs/{older_job.id}/msa.fasta",
        content_type="text/x-fasta",
        size_bytes=64,
    )
    db_session.add(older_artifact)
    db_session.add(
        AnalysisArtifact(
            enzyme_entry_id=enzyme_id,
            job_id=newer_job.id,
            artifact_type="msa",
            bucket="iee-artifacts",
            object_key=f"analysis-jobs/{newer_job.id}/msa.fasta",
            content_type="text/x-fasta",
            size_bytes=64,
        )
    )
    db_session.commit()

    class ConservationTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzyme_records.run_conservation_profile",
        ConservationTask,
        raising=False,
    )

    response = client.post(
        f"/enzymes/{enzyme_id}/analysis-jobs",
        headers=headers,
        json={
            "job_type": "conservation_profile",
            "parameters_json": {"msa_artifact_id": older_artifact.id},
        },
    )

    assert response.status_code == 201
    parameters = response.json()["parameters_json"]
    assert parameters["aligned_records"] == [
        {"identifier": "query", "aligned_sequence": "ACDEFGHIKL"},
        {"identifier": "OLDER", "aligned_sequence": "ACDEFGHIVL"},
    ]
    assert parameters["msa_source"]["artifact_id"] == older_artifact.id


def test_create_mutation_recommendation_job_uses_latest_conservation_artifact(
    client,
    db_session,
    monkeypatch,
):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme_id,
            sequence="ACDEFGHIKL",
            mature_sequence="ACDEFGHIKL",
            source="test",
            checksum="mutation-recommendation-sequence",
        )
    )
    conservation_job = AnalysisJob(
        enzyme_entry_id=enzyme_id,
        job_type="conservation_profile",
        status=JobStatus.FINISHED,
        result_summary_json={
            "sites": [
                {
                    "query_position": 1,
                    "wildtype_residue": "A",
                    "shannon_entropy": 0.0,
                    "wildtype_frequency": 1.0,
                    "conservation_category": "highly_conserved",
                },
                {
                    "query_position": 8,
                    "wildtype_residue": "I",
                    "shannon_entropy": 0.918,
                    "wildtype_frequency": 0.667,
                    "conservation_category": "moderately_conserved",
                },
            ]
        },
    )
    db_session.add(conservation_job)
    db_session.flush()
    rosetta_job = AnalysisJob(
        enzyme_entry_id=enzyme_id,
        job_type="rosetta_ddg",
        status=JobStatus.FINISHED,
        result_summary_json={
            "mutation_string": "I8A",
            "ddg_kcal_per_mol": -0.4,
            "interpretation": "stabilizing",
        },
    )
    db_session.add(rosetta_job)
    db_session.flush()
    db_session.add(
        MutationRecord(
            enzyme_entry_id=enzyme_id,
            mutation_string="I8A",
            property_delta={"optimal_temperature_delta_degC": 3},
            visibility=Visibility.PUBLIC,
        )
    )
    db_session.add(
        StructureEntry(
            enzyme_entry_id=enzyme_id,
            structure_type="uploaded_pdb",
            complex_state="enzyme_substrate_complex",
            source="test",
            chain_summary={
                "chains": [
                    {
                        "chain_id": "A",
                        "residues": [
                            {
                                "sequence_position": 8,
                                "secondary_structure": "loop",
                                "solvent_accessibility": 0.62,
                            }
                        ],
                    }
                ]
            },
            ligand_summary={
                "distance_matrix": [
                    {"sequence_position": 8, "min_distance_angstrom": 3.2}
                ]
            },
        )
    )
    db_session.add(
        AnalysisArtifact(
            enzyme_entry_id=enzyme_id,
            job_id=conservation_job.id,
            artifact_type="conservation_profile",
            bucket="iee-artifacts",
            object_key=f"analysis-jobs/{conservation_job.id}/conservation-profile.json",
            content_type="application/json",
            size_bytes=256,
        )
    )
    db_session.add(
        AnalysisArtifact(
            enzyme_entry_id=enzyme_id,
            job_id=rosetta_job.id,
            artifact_type="rosetta_ddg",
            bucket="iee-artifacts",
            object_key=f"analysis-jobs/{rosetta_job.id}/rosetta-ddg.json",
            content_type="application/json",
            size_bytes=128,
        )
    )
    db_session.commit()

    class MutationRecommendationTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzyme_records.run_mutation_recommendation",
        MutationRecommendationTask,
        raising=False,
    )

    response = client.post(
        f"/enzymes/{enzyme_id}/analysis-jobs",
        headers=headers,
        json={"job_type": "mutation_recommendation"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["job_type"] == "mutation_recommendation"
    assert body["parameters_json"]["conservation_sites"] == conservation_job.result_summary_json["sites"]
    assert body["parameters_json"]["rosetta_results"] == [rosetta_job.result_summary_json]
    assert body["parameters_json"]["mutation_records"][0]["mutation_string"] == "I8A"
    assert body["parameters_json"]["structure_summaries"][0]["ligand_summary"]["distance_matrix"][0][
        "min_distance_angstrom"
    ] == 3.2


def test_create_mutation_recommendation_job_uses_selected_structure(client, db_session, monkeypatch):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme_id,
            sequence="ACDEFGHIKL",
            mature_sequence="ACDEFGHIKL",
            source="test",
            checksum="selected-structure-recommendation-sequence",
        )
    )
    selected_structure = StructureEntry(
        enzyme_entry_id=enzyme_id,
        structure_type="uploaded_pdb",
        complex_state="enzyme_substrate_complex",
        source="test",
        ligand_summary={"distance_matrix": [{"sequence_position": 8, "min_distance_angstrom": 3.2}]},
    )
    ignored_structure = StructureEntry(
        enzyme_entry_id=enzyme_id,
        structure_type="uploaded_pdb",
        complex_state="apo",
        source="test",
        ligand_summary={"distance_matrix": [{"sequence_position": 1, "min_distance_angstrom": 8.8}]},
    )
    db_session.add_all([selected_structure, ignored_structure])
    db_session.commit()

    class MutationRecommendationTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzyme_records.run_mutation_recommendation",
        MutationRecommendationTask,
        raising=False,
    )

    response = client.post(
        f"/enzymes/{enzyme_id}/analysis-jobs",
        headers=headers,
        json={
            "job_type": "mutation_recommendation",
            "parameters_json": {"structure_id": selected_structure.id},
        },
    )

    assert response.status_code == 201
    summaries = response.json()["parameters_json"]["structure_summaries"]
    assert [summary["id"] for summary in summaries] == [selected_structure.id]
    assert summaries[0]["ligand_summary"]["distance_matrix"][0]["min_distance_angstrom"] == 3.2


def test_create_mutation_recommendation_job_rejects_structure_from_other_enzyme(client, db_session, monkeypatch):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    family_id = db_session.get(EnzymeEntry, enzyme_id).family_id
    other_enzyme = EnzymeEntry(
        family_id=family_id,
        name="Other recommendation target",
        organism="Other Streptomyces sp.",
        source="test",
    )
    db_session.add(other_enzyme)
    db_session.flush()
    foreign_structure = StructureEntry(
        enzyme_entry_id=other_enzyme.id,
        structure_type="uploaded_pdb",
        complex_state="enzyme_substrate_complex",
        source="test",
    )
    db_session.add_all(
        [
            ProteinSequence(
                enzyme_entry_id=enzyme_id,
                sequence="ACDEFGHIKL",
                mature_sequence="ACDEFGHIKL",
                source="test",
                checksum="foreign-structure-recommendation-sequence",
            ),
            foreign_structure,
        ]
    )
    db_session.commit()

    class MutationRecommendationTask:
        @staticmethod
        def delay(job_id):
            raise AssertionError(f"invalid structure should not enqueue job {job_id}")

    monkeypatch.setattr(
        "app.api.routes.enzyme_records.run_mutation_recommendation",
        MutationRecommendationTask,
        raising=False,
    )

    response = client.post(
        f"/enzymes/{enzyme_id}/analysis-jobs",
        headers=headers,
        json={
            "job_type": "mutation_recommendation",
            "parameters_json": {"structure_id": foreign_structure.id},
        },
    )

    assert response.status_code == 422
    assert "structure_id does not belong to this enzyme" in response.json()["error"]["message"]


def test_create_mutation_recommendation_job_uses_selected_conservation_artifact(
    client,
    db_session,
    monkeypatch,
):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme_id,
            sequence="ACDEFGHIKL",
            mature_sequence="ACDEFGHIKL",
            source="test",
            checksum="selected-mutation-recommendation-sequence",
        )
    )
    older_job = AnalysisJob(
        enzyme_entry_id=enzyme_id,
        job_type="conservation_profile",
        status=JobStatus.FINISHED,
        result_summary_json={
            "sites": [
                {
                    "query_position": 2,
                    "wildtype_residue": "C",
                    "shannon_entropy": 0.2,
                    "wildtype_frequency": 0.9,
                    "conservation_category": "highly_conserved",
                }
            ]
        },
    )
    newer_job = AnalysisJob(
        enzyme_entry_id=enzyme_id,
        job_type="conservation_profile",
        status=JobStatus.FINISHED,
        result_summary_json={
            "sites": [
                {
                    "query_position": 8,
                    "wildtype_residue": "I",
                    "shannon_entropy": 0.918,
                    "wildtype_frequency": 0.667,
                    "conservation_category": "moderately_conserved",
                }
            ]
        },
    )
    db_session.add_all([older_job, newer_job])
    db_session.flush()
    older_artifact = AnalysisArtifact(
        enzyme_entry_id=enzyme_id,
        job_id=older_job.id,
        artifact_type="conservation_profile",
        bucket="iee-artifacts",
        object_key=f"analysis-jobs/{older_job.id}/conservation-profile.json",
        content_type="application/json",
        size_bytes=256,
    )
    db_session.add(older_artifact)
    db_session.add(
        AnalysisArtifact(
            enzyme_entry_id=enzyme_id,
            job_id=newer_job.id,
            artifact_type="conservation_profile",
            bucket="iee-artifacts",
            object_key=f"analysis-jobs/{newer_job.id}/conservation-profile.json",
            content_type="application/json",
            size_bytes=256,
        )
    )
    db_session.commit()

    class MutationRecommendationTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzyme_records.run_mutation_recommendation",
        MutationRecommendationTask,
        raising=False,
    )

    response = client.post(
        f"/enzymes/{enzyme_id}/analysis-jobs",
        headers=headers,
        json={
            "job_type": "mutation_recommendation",
            "parameters_json": {"conservation_artifact_id": older_artifact.id},
        },
    )

    assert response.status_code == 201
    parameters = response.json()["parameters_json"]
    assert parameters["conservation_sites"] == older_job.result_summary_json["sites"]
    assert parameters["conservation_source"]["artifact_id"] == older_artifact.id


def test_create_rosetta_ddg_job_accepts_mutation_parameters(client, db_session, monkeypatch):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    structure = StructureEntry(
        enzyme_entry_id=enzyme_id,
        structure_type="uploaded_pdb",
        complex_state="apo",
        source="test",
    )
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme_id,
            sequence="ACDEFGHIKL",
            mature_sequence="ACDEFGHIKL",
            source="test",
            checksum="rosetta-ddg-sequence",
        )
    )
    db_session.add(structure)
    db_session.commit()
    enqueued_job_ids = []

    class RosettaTask:
        @staticmethod
        def delay(job_id):
            enqueued_job_ids.append(job_id)

    monkeypatch.setattr(
        "app.api.routes.enzyme_records.run_rosetta_ddg",
        RosettaTask,
        raising=False,
    )

    response = client.post(
        f"/enzymes/{enzyme_id}/analysis-jobs",
        headers=headers,
        json={
            "job_type": "rosetta_ddg",
            "parameters_json": {
                "mutation_string": "L10A",
                "structure_id": structure.id,
            },
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["job_type"] == "rosetta_ddg"
    assert body["parameters_json"]["mutation_string"] == "L10A"
    assert body["parameters_json"]["structure_id"] == structure.id
    assert body["parameters_json"]["requested_from"] == "enzyme_analysis_page"
    assert enqueued_job_ids == [body["id"]]


def test_create_rosetta_ddg_job_rejects_structure_from_other_enzyme(client, db_session, monkeypatch):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    family_id = db_session.get(EnzymeEntry, enzyme_id).family_id
    other_enzyme = EnzymeEntry(
        family_id=family_id,
        name="Other UGT example",
        organism="Other Streptomyces sp.",
        source="test",
    )
    db_session.add(other_enzyme)
    db_session.flush()
    foreign_structure = StructureEntry(
        enzyme_entry_id=other_enzyme.id,
        structure_type="uploaded_pdb",
        complex_state="apo",
        source="test",
    )
    db_session.add_all(
        [
            ProteinSequence(
                enzyme_entry_id=enzyme_id,
                sequence="ACDEFGHIKL",
                mature_sequence="ACDEFGHIKL",
                source="test",
                checksum="rosetta-ddg-foreign-structure-sequence",
            ),
            foreign_structure,
        ]
    )
    db_session.commit()

    class RosettaTask:
        @staticmethod
        def delay(job_id):
            raise AssertionError(f"invalid structure should not enqueue job {job_id}")

    monkeypatch.setattr(
        "app.api.routes.enzyme_records.run_rosetta_ddg",
        RosettaTask,
        raising=False,
    )

    response = client.post(
        f"/enzymes/{enzyme_id}/analysis-jobs",
        headers=headers,
        json={
            "job_type": "rosetta_ddg",
            "parameters_json": {
                "mutation_string": "L10A",
                "structure_id": foreign_structure.id,
            },
        },
    )

    assert response.status_code == 422
    assert "structure_id does not belong to this enzyme" in response.json()["error"]["message"]


def test_create_rosetta_ddg_job_rejects_wildtype_mismatch(client, db_session, monkeypatch):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme_id,
            sequence="ACDEFGHIKL",
            mature_sequence="ACDEFGHIKL",
            source="test",
            checksum="rosetta-ddg-mismatch-sequence",
        )
    )
    db_session.commit()

    class RosettaTask:
        @staticmethod
        def delay(job_id):
            raise AssertionError(f"invalid mutation should not enqueue job {job_id}")

    monkeypatch.setattr(
        "app.api.routes.enzyme_records.run_rosetta_ddg",
        RosettaTask,
        raising=False,
    )

    response = client.post(
        f"/enzymes/{enzyme_id}/analysis-jobs",
        headers=headers,
        json={
            "job_type": "rosetta_ddg",
            "parameters_json": {"mutation_string": "G2A"},
        },
    )

    assert response.status_code == 422
    assert "expected G at position 2 but found C" in response.json()["error"]["message"]


def test_create_library_design_job_uses_latest_recommendation_and_rosetta_artifacts(
    client,
    db_session,
    monkeypatch,
):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme_id,
            sequence="ACDEFGHIKL",
            mature_sequence="ACDEFGHIKL",
            source="test",
            checksum="library-design-sequence",
        )
    )
    recommendation_job = AnalysisJob(
        enzyme_entry_id=enzyme_id,
        job_type="mutation_recommendation",
        status=JobStatus.FINISHED,
        result_summary_json={
            "candidates": [
                {
                    "query_position": 10,
                    "wildtype_residue": "L",
                    "conservation_category": "variable",
                    "priority_score": 1.8,
                    "suggested_mutations": ["L10A"],
                    "rationale": "variable site",
                }
            ]
        },
    )
    rosetta_job = AnalysisJob(
        enzyme_entry_id=enzyme_id,
        job_type="rosetta_ddg",
        status=JobStatus.FINISHED,
        result_summary_json={
            "mutation_string": "L10A",
            "ddg_kcal_per_mol": -0.6,
            "interpretation": "stabilizing",
        },
    )
    db_session.add_all([recommendation_job, rosetta_job])
    db_session.flush()
    db_session.add_all(
        [
            AnalysisArtifact(
                enzyme_entry_id=enzyme_id,
                job_id=recommendation_job.id,
                artifact_type="mutation_recommendations",
                bucket="iee-artifacts",
                object_key=f"analysis-jobs/{recommendation_job.id}/mutation-recommendations.json",
                content_type="application/json",
                size_bytes=256,
            ),
            AnalysisArtifact(
                enzyme_entry_id=enzyme_id,
                job_id=rosetta_job.id,
                artifact_type="rosetta_ddg",
                bucket="iee-artifacts",
                object_key=f"analysis-jobs/{rosetta_job.id}/rosetta-ddg.json",
                content_type="application/json",
                size_bytes=128,
            ),
        ]
    )
    db_session.commit()
    enqueued_job_ids = []

    class LibraryDesignTask:
        @staticmethod
        def delay(job_id):
            enqueued_job_ids.append(job_id)

    monkeypatch.setattr(
        "app.api.routes.enzyme_records.run_library_design",
        LibraryDesignTask,
        raising=False,
    )

    response = client.post(
        f"/enzymes/{enzyme_id}/analysis-jobs",
        headers=headers,
        json={
            "job_type": "library_design",
            "parameters_json": {"library_size": 48, "plate_format": 384},
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["job_type"] == "library_design"
    assert body["parameters_json"]["library_size"] == 48
    assert body["parameters_json"]["plate_format"] == 384
    assert body["parameters_json"]["recommendation_candidates"] == recommendation_job.result_summary_json["candidates"]
    assert body["parameters_json"]["rosetta_results"] == [rosetta_job.result_summary_json]
    assert enqueued_job_ids == [body["id"]]


def test_create_library_design_job_uses_selected_recommendation_artifact(
    client,
    db_session,
    monkeypatch,
):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme_id,
            sequence="ACDEFGHIKL",
            mature_sequence="ACDEFGHIKL",
            source="test",
            checksum="selected-library-design-sequence",
        )
    )
    older_job = AnalysisJob(
        enzyme_entry_id=enzyme_id,
        job_type="mutation_recommendation",
        status=JobStatus.FINISHED,
        result_summary_json={
            "candidates": [
                {
                    "query_position": 2,
                    "wildtype_residue": "C",
                    "conservation_category": "highly_conserved",
                    "priority_score": 1.1,
                    "suggested_mutations": ["C2A"],
                    "rationale": "selected older recommendation",
                }
            ]
        },
    )
    newer_job = AnalysisJob(
        enzyme_entry_id=enzyme_id,
        job_type="mutation_recommendation",
        status=JobStatus.FINISHED,
        result_summary_json={
            "candidates": [
                {
                    "query_position": 10,
                    "wildtype_residue": "L",
                    "conservation_category": "variable",
                    "priority_score": 1.8,
                    "suggested_mutations": ["L10A"],
                    "rationale": "newer recommendation",
                }
            ]
        },
    )
    db_session.add_all([older_job, newer_job])
    db_session.flush()
    older_artifact = AnalysisArtifact(
        enzyme_entry_id=enzyme_id,
        job_id=older_job.id,
        artifact_type="mutation_recommendations",
        bucket="iee-artifacts",
        object_key=f"analysis-jobs/{older_job.id}/mutation-recommendations.json",
        content_type="application/json",
        size_bytes=256,
    )
    db_session.add(older_artifact)
    db_session.add(
        AnalysisArtifact(
            enzyme_entry_id=enzyme_id,
            job_id=newer_job.id,
            artifact_type="mutation_recommendations",
            bucket="iee-artifacts",
            object_key=f"analysis-jobs/{newer_job.id}/mutation-recommendations.json",
            content_type="application/json",
            size_bytes=256,
        )
    )
    db_session.commit()

    class LibraryDesignTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzyme_records.run_library_design",
        LibraryDesignTask,
        raising=False,
    )

    response = client.post(
        f"/enzymes/{enzyme_id}/analysis-jobs",
        headers=headers,
        json={
            "job_type": "library_design",
            "parameters_json": {"recommendation_artifact_id": older_artifact.id},
        },
    )

    assert response.status_code == 201
    parameters = response.json()["parameters_json"]
    assert parameters["recommendation_candidates"] == older_job.result_summary_json["candidates"]
    assert parameters["recommendation_source"]["artifact_id"] == older_artifact.id


def test_create_analysis_job_rejects_unsupported_job_type(client, db_session):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)

    response = client.post(
        f"/enzymes/{enzyme_id}/analysis-jobs",
        headers=headers,
        json={"job_type": "mmpbsa"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "unsupported analysis job type"


def test_list_mutations_filters_by_position_property_source_and_visibility(client, db_session):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session)
    db_session.add_all(
        [
            MutationRecord(
                enzyme_entry_id=enzyme_id,
                mutation_string="L10A",
                effect_summary="Improved thermostability",
                property_delta={"optimal_temperature_delta_degC": 5},
                substrate="casein",
                assay_condition_summary={"source": "literature", "evidence": "PMID:1"},
                visibility=Visibility.PUBLIC,
            ),
            MutationRecord(
                enzyme_entry_id=enzyme_id,
                mutation_string="F12A",
                effect_summary="Reduced activity",
                property_delta={"specific_activity_fold_change": -0.4},
                assay_condition_summary={"source": "literature", "evidence": "PMID:2"},
                visibility=Visibility.PUBLIC,
            ),
            MutationRecord(
                enzyme_entry_id=enzyme_id,
                mutation_string="L10V",
                effect_summary="Private candidate",
                property_delta={"optimal_temperature_delta_degC": 2},
                assay_condition_summary={"source": "user_upload", "evidence": "internal"},
                visibility=Visibility.PRIVATE,
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        (
            f"/enzymes/{enzyme_id}/mutations"
            "?position=10&property_delta_key=optimal_temperature_delta_degC"
            "&beneficial_only=true&source=literature"
        ),
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert [record["mutation_string"] for record in body] == ["L10A"]
    assert body[0]["mutation_positions"] == [
        {"wildtype": "L", "position": 10, "mutant": "A"}
    ]
    assert body[0]["assay_condition_summary"]["evidence"] == "PMID:1"

    private_response = client.get(
        f"/enzymes/{enzyme_id}/mutations?visibility=private",
        headers=headers,
    )

    assert private_response.status_code == 200
    assert [record["mutation_string"] for record in private_response.json()] == ["L10V"]


def test_create_enzyme_domain_record_returns_404_for_missing_enzyme(client, db_session):
    headers = _auth_headers(client)

    response = client.post(
        "/enzymes/missing-enzyme/properties",
        headers=headers,
        json={"property_type": "optimal_pH", "value_original": "7.5"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "enzyme not found"
    assert db_session.scalar(select(EnzymeEntry).where(EnzymeEntry.id == "missing-enzyme")) is None
