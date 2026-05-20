from sqlalchemy import select

from app.db.models import (
    CurationStatus,
    EnzymeEntry,
    EnzymeFamily,
    EnzymeModule,
    Project,
    User,
    UserExperiment,
    Visibility,
    VisibilityRequest,
)


def _auth_headers(client, email: str) -> dict[str, str]:
    client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "visibility-password",
            "display_name": "Visibility Engineer",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": email, "password": "visibility-password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _user(db_session, email: str) -> User:
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    return user


def _project(db_session, owner: User, name: str = "Visibility project") -> Project:
    project = Project(owner_user_id=owner.id, name=name, description=None)
    db_session.add(project)
    db_session.flush()
    return project


def _enzyme(db_session) -> EnzymeEntry:
    family = EnzymeFamily(
        module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        name="Mature microbial transglutaminases",
    )
    db_session.add(family)
    db_session.flush()
    enzyme = EnzymeEntry(
        family_id=family.id,
        name="mTG visibility test",
        organism="Streptomyces mobaraensis",
        source="test",
    )
    db_session.add(enzyme)
    db_session.flush()
    return enzyme


def _experiment(
    db_session,
    project: Project,
    owner: User,
    enzyme: EnzymeEntry,
    *,
    variant_name: str,
    visibility: Visibility = Visibility.PRIVATE,
    curation_status: CurationStatus = CurationStatus.UNREVIEWED,
) -> UserExperiment:
    experiment = UserExperiment(
        project_id=project.id,
        enzyme_entry_id=enzyme.id,
        variant_name=variant_name,
        mutation_string="WT",
        sequence=None,
        measured_property="specific_activity",
        measured_value="100",
        unit="U/mg",
        assay_condition_json={"substrate": "casein"},
        visibility=visibility,
        curation_status=curation_status,
        created_by=owner.id,
    )
    db_session.add(experiment)
    db_session.commit()
    db_session.refresh(experiment)
    return experiment


def test_project_owner_can_list_project_experiments(client, db_session):
    headers = _auth_headers(client, "visibility-owner@example.com")
    owner = _user(db_session, "visibility-owner@example.com")
    project = _project(db_session, owner)
    enzyme = _enzyme(db_session)
    experiment = _experiment(
        db_session,
        project,
        owner,
        enzyme,
        variant_name="WT control",
    )

    response = client.get(
        f"/projects/{project.id}/experiments",
        headers=headers,
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [experiment.id]
    assert response.json()[0]["visibility"] == "private"


def test_non_owner_cannot_list_private_project_experiments(client, db_session):
    owner_headers = _auth_headers(client, "visibility-owner-private@example.com")
    _ = owner_headers
    owner = _user(db_session, "visibility-owner-private@example.com")
    project = _project(db_session, owner)
    enzyme = _enzyme(db_session)
    _experiment(db_session, project, owner, enzyme, variant_name="Private WT")
    other_headers = _auth_headers(client, "visibility-other@example.com")

    response = client.get(
        f"/projects/{project.id}/experiments",
        headers=other_headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "project not found"


def test_public_experiments_list_only_public_approved_records(client, db_session):
    headers = _auth_headers(client, "visibility-reader@example.com")
    owner = _user(db_session, "visibility-reader@example.com")
    project = _project(db_session, owner)
    enzyme = _enzyme(db_session)
    approved = _experiment(
        db_session,
        project,
        owner,
        enzyme,
        variant_name="Approved public",
        visibility=Visibility.PUBLIC,
        curation_status=CurationStatus.APPROVED,
    )
    _experiment(
        db_session,
        project,
        owner,
        enzyme,
        variant_name="Unreviewed public",
        visibility=Visibility.PUBLIC,
        curation_status=CurationStatus.UNREVIEWED,
    )
    _experiment(
        db_session,
        project,
        owner,
        enzyme,
        variant_name="Private approved",
        visibility=Visibility.PRIVATE,
        curation_status=CurationStatus.APPROVED,
    )

    response = client.get("/experiments/public", headers=headers)

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [approved.id]
    assert response.json()[0]["curation_status"] == "approved"


def test_owner_can_create_visibility_request_for_private_experiment(client, db_session):
    headers = _auth_headers(client, "visibility-requester@example.com")
    owner = _user(db_session, "visibility-requester@example.com")
    project = _project(db_session, owner)
    enzyme = _enzyme(db_session)
    experiment = _experiment(
        db_session,
        project,
        owner,
        enzyme,
        variant_name="Private upload",
    )

    response = client.post(
        f"/experiments/{experiment.id}/visibility-requests",
        headers=headers,
        json={"requested_visibility": "public"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["target_id"] == experiment.id
    assert body["requested_visibility"] == "public"
    assert body["status"] == "pending"
    request = db_session.scalar(
        select(VisibilityRequest).where(VisibilityRequest.target_id == experiment.id)
    )
    assert request is not None
    assert request.requested_by == owner.id


def test_visibility_request_is_idempotent_for_existing_pending_request(client, db_session):
    headers = _auth_headers(client, "visibility-request-repeat@example.com")
    owner = _user(db_session, "visibility-request-repeat@example.com")
    project = _project(db_session, owner)
    enzyme = _enzyme(db_session)
    experiment = _experiment(
        db_session,
        project,
        owner,
        enzyme,
        variant_name="Private repeat upload",
    )

    first_response = client.post(
        f"/experiments/{experiment.id}/visibility-requests",
        headers=headers,
        json={"requested_visibility": "public"},
    )
    second_response = client.post(
        f"/experiments/{experiment.id}/visibility-requests",
        headers=headers,
        json={"requested_visibility": "public"},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 200
    assert second_response.json()["id"] == first_response.json()["id"]
    requests = list(
        db_session.scalars(
            select(VisibilityRequest).where(VisibilityRequest.target_id == experiment.id)
        )
    )
    assert len(requests) == 1


def test_non_owner_cannot_create_visibility_request(client, db_session):
    owner_headers = _auth_headers(client, "visibility-request-owner@example.com")
    _ = owner_headers
    owner = _user(db_session, "visibility-request-owner@example.com")
    project = _project(db_session, owner)
    enzyme = _enzyme(db_session)
    experiment = _experiment(db_session, project, owner, enzyme, variant_name="Private upload")
    other_headers = _auth_headers(client, "visibility-request-other@example.com")

    response = client.post(
        f"/experiments/{experiment.id}/visibility-requests",
        headers=other_headers,
        json={"requested_visibility": "public"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "experiment not found"
