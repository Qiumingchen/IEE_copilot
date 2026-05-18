from sqlalchemy import select

from app.db.models import EnzymeEntry, EnzymeFamily, EnzymeModule


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


def test_enzyme_domain_records_require_authentication(client, db_session):
    enzyme_id = _enzyme_id(db_session)

    response = client.get(f"/enzymes/{enzyme_id}/properties")

    assert response.status_code == 401


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
