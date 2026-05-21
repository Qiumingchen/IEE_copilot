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


def test_non_curator_cannot_import_curated_evidence(client, db_session):
    headers = _auth_headers(client, "curated-denied@example.com")
    seeded_enzyme = _seed_enzyme(db_session)

    response = client.post(
        f"/enzymes/{seeded_enzyme.id}/curated-evidence/import",
        headers=headers,
        json={"csv_text": "record_type\nproperty"},
    )

    assert response.status_code == 403
