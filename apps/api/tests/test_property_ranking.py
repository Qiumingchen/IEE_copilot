from app.db.models import PropertyRecord


def test_property_ranking_returns_reported_values_with_warnings(client, db_session):
    headers = _auth_headers(client)
    enzyme_a = _enzyme_id(db_session, "UGT A")
    enzyme_b = _enzyme_id(db_session, "UGT B")
    db_session.add_all(
        [
            PropertyRecord(
                enzyme_entry_id=enzyme_a,
                property_type="specific_activity",
                value_original="120",
                unit_original="U/mg",
                value_standardized="120",
                unit_standardized="U/mg",
                standardization_status="standardized",
                substrate="AQ1",
                assay_temperature="40",
                assay_pH="7.5",
                method="HPLC",
                reference_id="PMID1",
            ),
            PropertyRecord(
                enzyme_entry_id=enzyme_b,
                property_type="specific_activity",
                value_original="80",
                unit_original="U/mg",
                value_standardized="80",
                unit_standardized="U/mg",
                standardization_status="standardized",
                substrate="AQ2",
                assay_temperature="35",
                assay_pH="8.0",
                method="HPLC",
                reference_id="PMID2",
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        f"/enzymes/{enzyme_a}/property-rankings?property_type=specific_activity",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["property_type"] == "specific_activity"
    assert body["ranking_mode"] == "reported_value"
    assert [item["rank"] for item in body["items"]] == [1, 2]
    assert [item["value_standardized"] for item in body["items"]] == ["120", "80"]
    assert body["items"][0]["enzyme_entry_id"] == enzyme_a
    assert "reported_value_ranking preserves original assay conditions" in body["comparison_warnings"]


def test_property_ranking_groups_same_conditions(client, db_session):
    headers = _auth_headers(client)
    enzyme_a = _enzyme_id(db_session, "UGT A")
    enzyme_b = _enzyme_id(db_session, "UGT B")
    enzyme_c = _enzyme_id(db_session, "UGT C")
    db_session.add_all(
        [
            PropertyRecord(
                enzyme_entry_id=enzyme_a,
                property_type="specific_activity",
                value_original="120",
                unit_original="U/mg",
                value_standardized="120",
                unit_standardized="U/mg",
                standardization_status="standardized",
                substrate="AQ1",
                assay_temperature="40",
                assay_pH="7.5",
                method="HPLC",
                reference_id="PMID1",
            ),
            PropertyRecord(
                enzyme_entry_id=enzyme_b,
                property_type="specific_activity",
                value_original="80",
                unit_original="U/mg",
                value_standardized="80",
                unit_standardized="U/mg",
                standardization_status="standardized",
                substrate="AQ1",
                assay_temperature="40",
                assay_pH="7.5",
                method="HPLC",
                reference_id="PMID1",
            ),
            PropertyRecord(
                enzyme_entry_id=enzyme_c,
                property_type="specific_activity",
                value_original="200",
                unit_original="U/mg",
                value_standardized="200",
                unit_standardized="U/mg",
                standardization_status="standardized",
                substrate="AQ2",
                assay_temperature="35",
                assay_pH="8.0",
                method="HPLC",
                reference_id="PMID2",
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        f"/enzymes/{enzyme_a}/property-rankings?property_type=specific_activity&ranking_mode=condition_grouped",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ranking_mode"] == "condition_grouped"
    assert len(body["groups"]) == 2
    first_group = body["groups"][0]
    assert first_group["condition_key"]["substrate"] == "AQ1"
    assert [item["rank"] for item in first_group["items"]] == [1, 2]
    assert [item["enzyme_entry_id"] for item in first_group["items"]] == [enzyme_a, enzyme_b]
    assert body["comparison_warnings"] == ["condition_grouped ranking does not compare records across groups"]


def test_create_property_auto_standardizes_convertible_units(client, db_session):
    headers = _auth_headers(client)
    enzyme_id = _enzyme_id(db_session, "UGT A")

    response = client.post(
        f"/enzymes/{enzyme_id}/properties",
        headers=headers,
        json={
            "property_type": "optimal_temperature",
            "value_original": "328.15",
            "unit_original": "K",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["value_standardized"] == "55"
    assert body["unit_standardized"] == "degC"
    assert body["standardization_status"] == "standardized"


def _auth_headers(client) -> dict[str, str]:
    client.post(
        "/auth/register",
        json={
            "email": "ranking@example.com",
            "password": "ranking-password",
            "display_name": "Ranking Engineer",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "ranking@example.com", "password": "ranking-password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _enzyme_id(db_session, name: str) -> str:
    from app.db.models import EnzymeEntry, EnzymeFamily, EnzymeModule

    family = db_session.query(EnzymeFamily).filter_by(
        module=EnzymeModule.ANTHRAQUINONE_GLYCOSYLTRANSFERASE
    ).one_or_none()
    if family is None:
        family = EnzymeFamily(
            module=EnzymeModule.ANTHRAQUINONE_GLYCOSYLTRANSFERASE,
            name="Anthraquinone glycosyltransferases",
        )
        db_session.add(family)
        db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name=name,
        organism="Streptomyces sp.",
        source="test",
    )
    db_session.add(enzyme)
    db_session.commit()
    return enzyme.id
