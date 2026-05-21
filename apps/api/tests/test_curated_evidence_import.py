from sqlalchemy import select

from app.db.models import (
    CurationStatus,
    EnzymeEntry,
    EnzymeFamily,
    EnzymeModule,
    KineticRecord,
    LiteratureReference,
    MutationRecord,
    PropertyRecord,
    User,
    UserRole,
    Visibility,
)


def _seed_enzyme(db_session):
    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="Curated microbial transglutaminase",
        organism="Streptomyces mobaraensis",
        ec_number="2.3.2.13",
        uniprot_id="P81453",
        source="curated_test",
    )
    db_session.add(enzyme)
    db_session.commit()
    return enzyme


def _auth_headers(client, email: str):
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "curated-password", "display_name": email},
    )
    assert response.status_code == 201
    token = client.post(
        "/auth/login",
        json={"email": email, "password": "curated-password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _set_user_role(db_session, email: str, role: UserRole):
    user = db_session.scalar(select(User).where(User.email == email))
    user.role = role
    db_session.commit()


def test_curator_can_import_curated_property_kinetic_and_mutation_evidence(
    client,
    db_session,
):
    email = "curated-importer@example.com"
    headers = _auth_headers(client, email)
    _set_user_role(db_session, email, UserRole.CURATOR)
    seeded_enzyme = _seed_enzyme(db_session)
    enzyme_id = seeded_enzyme.id
    csv_text = "\n".join(
        [
            "record_type,property_type,value_original,unit_original,substrate,assay_temperature,assay_pH,method,mutation_string,effect_summary,doi,reference_title,journal,year,evidence_text,source",
            "property,optimal_temperature,58,degC,casein,37,7.0,activity assay,,,10.1000/curated-mtgase,Curated MTGase paper,Biocatalysis Reports,2024,Optimum temperature reported in Table 1,curated_literature",
            "kinetic,,,,CBZ-Gln-Gly,37,7.0,HPLC,,,10.1000/curated-mtgase,Curated MTGase paper,Biocatalysis Reports,2024,Km 2.1 mM and kcat 31 s-1,curated_literature",
            "mutation,,,,casein,50,7.0,thermal assay,S2P,Improved thermostability,10.1000/curated-mtgase,Curated MTGase paper,Biocatalysis Reports,2024,S2P increased half-life,curated_literature",
        ]
    )

    response = client.post(
        f"/enzymes/{enzyme_id}/curated-evidence/import",
        headers=headers,
        json={"csv_text": csv_text},
    )

    assert response.status_code == 201
    assert response.json()["created"] == {"properties": 1, "kinetics": 1, "mutations": 1}
    assert response.json()["references"] == [
        {
            "id": response.json()["reference_ids"][0],
            "title": "Curated MTGase paper",
            "authors": None,
            "journal": "Biocatalysis Reports",
            "year": 2024,
            "doi": "10.1000/curated-mtgase",
            "pubmed_id": None,
            "source": "curated_literature",
            "provenance": {"provider": "curated_literature", "mode": "curated"},
        }
    ]

    reference = db_session.scalar(
        select(LiteratureReference).where(LiteratureReference.doi == "10.1000/curated-mtgase")
    )
    assert reference is not None
    assert reference.source == "curated_literature"
    assert reference.metadata_json["provenance"]["mode"] == "curated"

    property_record = db_session.scalar(select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == enzyme_id))
    assert property_record.reference_id == reference.id
    assert property_record.evidence_text == "Optimum temperature reported in Table 1"
    assert property_record.visibility == Visibility.PUBLIC
    assert property_record.curation_status == CurationStatus.APPROVED

    kinetic = db_session.scalar(select(KineticRecord).where(KineticRecord.enzyme_entry_id == enzyme_id))
    assert kinetic.reference_id == reference.id
    assert kinetic.substrate == "CBZ-Gln-Gly"

    mutation = db_session.scalar(select(MutationRecord).where(MutationRecord.enzyme_entry_id == enzyme_id))
    assert mutation.mutation_string == "S2P"
    assert mutation.mutation_positions == [{"wildtype": "S", "position": 2, "mutant": "P"}]
    assert mutation.reference_id == reference.id
    assert mutation.assay_condition_summary["evidence"] == "S2P increased half-life"


def test_list_enzyme_references_returns_deduplicated_curated_literature(client, db_session):
    email = "curated-references@example.com"
    headers = _auth_headers(client, email)
    _set_user_role(db_session, email, UserRole.CURATOR)
    seeded_enzyme = _seed_enzyme(db_session)
    csv_text = "\n".join(
        [
            "record_type,property_type,value_original,unit_original,substrate,mutation_string,doi,reference_title,journal,year,evidence_text,source",
            "property,optimal_temperature,58,degC,casein,,10.1000/reference-list,Reference List Paper,Biocatalysis Reports,2024,Optimum temperature reported,curated_literature",
            "mutation,,,,casein,S2P,10.1000/reference-list,Reference List Paper,Biocatalysis Reports,2024,S2P increased half-life,curated_literature",
        ]
    )
    import_response = client.post(
        f"/enzymes/{seeded_enzyme.id}/curated-evidence/import",
        headers=headers,
        json={"csv_text": csv_text},
    )
    assert import_response.status_code == 201

    response = client.get(f"/enzymes/{seeded_enzyme.id}/references", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["doi"] == "10.1000/reference-list"
    assert body[0]["title"] == "Reference List Paper"
    assert body[0]["journal"] == "Biocatalysis Reports"
    assert body[0]["year"] == 2024
    assert body[0]["source"] == "curated_literature"
    assert body[0]["provenance"]["mode"] == "curated"


def test_curator_can_preview_curated_evidence_without_writing_records(client, db_session):
    email = "curated-preview@example.com"
    headers = _auth_headers(client, email)
    _set_user_role(db_session, email, UserRole.CURATOR)
    seeded_enzyme = _seed_enzyme(db_session)
    csv_text = "\n".join(
        [
            "record_type,property_type,value_original,unit_original,substrate,mutation_string,doi,reference_title,evidence_text",
            "property,optimal_pH,7.0,pH,casein,,10.1000/preview,Preview paper,Optimum pH reported",
            "mutation,,,,casein,S2P,10.1000/preview,Preview paper,S2P increased half-life",
        ]
    )

    response = client.post(
        f"/enzymes/{seeded_enzyme.id}/curated-evidence/import-preview",
        headers=headers,
        json={"csv_text": csv_text},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["row_count"] == 2
    assert body["record_counts"] == {"properties": 1, "kinetics": 0, "mutations": 1}
    assert body["fields"] == [
        "record_type",
        "property_type",
        "value_original",
        "unit_original",
        "substrate",
        "mutation_string",
        "doi",
        "reference_title",
        "evidence_text",
    ]
    assert body["records"][0]["record_type"] == "property"
    assert body["records"][0]["summary"] == "optimal_pH 7.0 pH"
    assert body["records"][1]["record_type"] == "mutation"
    assert body["records"][1]["summary"] == "S2P"

    assert db_session.scalar(select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == seeded_enzyme.id)) is None
    assert db_session.scalar(select(MutationRecord).where(MutationRecord.enzyme_entry_id == seeded_enzyme.id)) is None
    assert db_session.scalar(select(LiteratureReference).where(LiteratureReference.doi == "10.1000/preview")) is None


def test_curated_evidence_preview_returns_row_level_validation_report(client, db_session):
    email = "curated-preview-errors@example.com"
    headers = _auth_headers(client, email)
    _set_user_role(db_session, email, UserRole.CURATOR)
    seeded_enzyme = _seed_enzyme(db_session)

    response = client.post(
        f"/enzymes/{seeded_enzyme.id}/curated-evidence/import-preview",
        headers=headers,
        json={
            "csv_text": "\n".join(
                [
                    "record_type,property_type,value_original,mutation_string",
                    "property,optimal_temperature,,",
                    "mutation,,,S2",
                    "kinetic,,,",
                ]
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["row_count"] == 3
    assert body["record_counts"] == {"properties": 0, "kinetics": 1, "mutations": 0}
    assert body["errors"] == [
        {"row_number": 2, "field": "value_original", "message": "value_original is required"},
        {"row_number": 3, "field": "mutation_string", "message": "invalid mutation format: S2"},
    ]


def test_curated_evidence_import_rejects_invalid_batch_without_partial_writes(client, db_session):
    email = "curated-import-invalid@example.com"
    headers = _auth_headers(client, email)
    _set_user_role(db_session, email, UserRole.CURATOR)
    seeded_enzyme = _seed_enzyme(db_session)

    response = client.post(
        f"/enzymes/{seeded_enzyme.id}/curated-evidence/import",
        headers=headers,
        json={
            "csv_text": "\n".join(
                [
                    "record_type,property_type,value_original,unit_original,mutation_string,doi,reference_title",
                    "property,optimal_temperature,58,degC,,10.1000/partial,Partial import paper",
                    "mutation,,,,S2,10.1000/partial,Partial import paper",
                ]
            )
        },
    )

    assert response.status_code == 422
    assert "row 3" in response.json()["error"]["message"]
    assert db_session.scalar(select(PropertyRecord).where(PropertyRecord.enzyme_entry_id == seeded_enzyme.id)) is None
    assert db_session.scalar(select(LiteratureReference).where(LiteratureReference.doi == "10.1000/partial")) is None


def test_non_curator_cannot_import_curated_evidence(client, db_session):
    headers = _auth_headers(client, "curated-denied@example.com")
    seeded_enzyme = _seed_enzyme(db_session)

    response = client.post(
        f"/enzymes/{seeded_enzyme.id}/curated-evidence/import",
        headers=headers,
        json={"csv_text": "record_type\nproperty"},
    )

    assert response.status_code == 403
