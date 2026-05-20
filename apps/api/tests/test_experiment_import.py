import pytest
from sqlalchemy import select

from app.db.models import EnzymeEntry, EnzymeFamily, EnzymeModule, ProteinSequence, UserExperiment
from app.services.experiment_import import (
    ExperimentImportError,
    parse_experiment_csv,
    validate_experiment_rows,
)


def test_parse_experiment_csv_returns_fields_and_expands_property_columns():
    csv_text = "\n".join(
        [
            "variant_name,mutation_string,specific_activity,opt_temperature,substrate,assay_temperature,assay_pH",
            "L10A variant,L10A,125.4,55,casein,37,7.5",
        ]
    )

    parsed = parse_experiment_csv(csv_text)
    validated = validate_experiment_rows(parsed.rows, engineering_sequence="M" * 9 + "L" + "A")

    assert parsed.fields == [
        "variant_name",
        "mutation_string",
        "specific_activity",
        "opt_temperature",
        "substrate",
        "assay_temperature",
        "assay_pH",
    ]
    assert len(validated.records) == 2
    assert validated.records[0].variant_name == "L10A variant"
    assert validated.records[0].mutation_string == "L10A"
    assert validated.records[0].measured_property == "specific_activity"
    assert validated.records[0].measured_value == "125.4"
    assert validated.records[0].visibility == "private"
    assert validated.records[0].assay_condition_json == {
        "substrate": "casein",
        "assay_temperature": "37",
        "assay_pH": "7.5",
    }
    assert validated.records[1].measured_property == "opt_temperature"
    assert validated.records[1].measured_value == "55"


def test_validate_experiment_rows_accepts_generic_property_value_columns():
    parsed = parse_experiment_csv(
        "\n".join(
            [
                "variant_name,mutation_string,measured_property,measured_value,unit,visibility",
                "WT control,WT,relative_activity,100,%,public",
            ]
        )
    )

    validated = validate_experiment_rows(parsed.rows, engineering_sequence="ACD")

    assert len(validated.records) == 1
    assert validated.records[0].variant_name == "WT control"
    assert validated.records[0].mutation_string == "WT"
    assert validated.records[0].measured_property == "relative_activity"
    assert validated.records[0].measured_value == "100"
    assert validated.records[0].unit == "%"
    assert validated.records[0].visibility == "public"


def test_validate_experiment_rows_reports_missing_measurement_columns():
    parsed = parse_experiment_csv(
        "\n".join(
            [
                "variant_name,mutation_string,substrate",
                "No value,L10A,casein",
            ]
        )
    )

    with pytest.raises(ExperimentImportError) as exc_info:
        validate_experiment_rows(parsed.rows, engineering_sequence="M" * 9 + "L")

    assert "row 2" in str(exc_info.value)
    assert "at least one measurement" in str(exc_info.value)


def test_validate_experiment_rows_reports_wildtype_mismatch_against_parent_sequence():
    parsed = parse_experiment_csv(
        "\n".join(
            [
                "variant_name,mutation_string,specific_activity",
                "Bad mutant,G2A,20",
            ]
        )
    )

    with pytest.raises(ExperimentImportError) as exc_info:
        validate_experiment_rows(parsed.rows, engineering_sequence="ACD")

    assert "row 2" in str(exc_info.value)
    assert "expected G at position 2 but found C" in str(exc_info.value)


def _auth_headers(client, email: str = "experiment-import@example.com") -> dict[str, str]:
    client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "experiment-password",
            "display_name": "Experiment Engineer",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": email, "password": "experiment-password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _project_id(client, headers: dict[str, str]) -> str:
    response = client.post(
        "/projects",
        headers=headers,
        json={"name": "Wet-lab upload"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _enzyme_id(db_session) -> str:
    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="mTG test",
        organism="Streptomyces mobaraensis",
        source="test",
    )
    db_session.add(enzyme)
    db_session.flush()
    db_session.add(
        ProteinSequence(
            enzyme_entry_id=enzyme.id,
            sequence="M" * 9 + "L" + "A",
            mature_sequence="M" * 9 + "L" + "A",
            is_engineering_target=True,
            source="test",
            checksum="experiment-import-checksum",
        )
    )
    db_session.commit()
    return enzyme.id


def test_preview_experiment_import_returns_fields_and_validated_records(client, db_session):
    headers = _auth_headers(client)
    project_id = _project_id(client, headers)
    enzyme_id = _enzyme_id(db_session)

    response = client.post(
        f"/enzymes/{enzyme_id}/experiments/import-preview",
        headers=headers,
        json={
            "project_id": project_id,
            "csv_text": "\n".join(
                [
                    "variant_name,mutation_string,specific_activity,visibility",
                    "L10A variant,L10A,125.4,",
                ]
            ),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["fields"] == [
        "variant_name",
        "mutation_string",
        "specific_activity",
        "visibility",
    ]
    assert body["record_count"] == 1
    assert body["records"][0]["mutation_string"] == "L10A"
    assert body["records"][0]["measured_property"] == "specific_activity"
    assert body["records"][0]["visibility"] == "private"


def test_import_experiment_csv_persists_user_experiments(client, db_session):
    headers = _auth_headers(client, "experiment-save@example.com")
    project_id = _project_id(client, headers)
    enzyme_id = _enzyme_id(db_session)

    response = client.post(
        f"/enzymes/{enzyme_id}/experiments/import",
        headers=headers,
        json={
            "project_id": project_id,
            "csv_text": "\n".join(
                [
                    "variant_name,mutation_string,specific_activity,opt_temperature,substrate",
                    "L10A variant,L10A,125.4,55,casein",
                ]
            ),
        },
    )

    assert response.status_code == 201
    assert response.json()["created_count"] == 2
    experiments = list(
        db_session.scalars(
            select(UserExperiment)
            .where(UserExperiment.project_id == project_id)
            .order_by(UserExperiment.measured_property)
        )
    )
    assert [experiment.measured_property for experiment in experiments] == [
        "opt_temperature",
        "specific_activity",
    ]
    assert experiments[0].assay_condition_json == {"substrate": "casein"}
    assert experiments[0].visibility.value == "private"


def test_import_experiment_csv_rejects_project_owned_by_another_user(client, db_session):
    owner_headers = _auth_headers(client, "experiment-owner@example.com")
    project_id = _project_id(client, owner_headers)
    other_headers = _auth_headers(client, "experiment-other@example.com")
    enzyme_id = _enzyme_id(db_session)

    response = client.post(
        f"/enzymes/{enzyme_id}/experiments/import",
        headers=other_headers,
        json={
            "project_id": project_id,
            "csv_text": "\n".join(
                [
                    "variant_name,mutation_string,specific_activity",
                    "L10A variant,L10A,125.4",
                ]
            ),
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "project not found"


def test_preview_experiment_import_returns_validation_error_for_mutation_mismatch(
    client, db_session
):
    headers = _auth_headers(client, "experiment-invalid@example.com")
    project_id = _project_id(client, headers)
    enzyme_id = _enzyme_id(db_session)

    response = client.post(
        f"/enzymes/{enzyme_id}/experiments/import-preview",
        headers=headers,
        json={
            "project_id": project_id,
            "csv_text": "\n".join(
                [
                    "variant_name,mutation_string,specific_activity",
                    "Bad mutant,G2A,20",
                ]
            ),
        },
    )

    assert response.status_code == 422
    assert "expected G at position 2 but found M" in response.json()["error"]["message"]
