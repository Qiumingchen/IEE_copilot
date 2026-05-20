from sqlalchemy import select

from app.db.models import (
    AuditLog,
    CurationStatus,
    EnzymeEntry,
    EnzymeFamily,
    EnzymeModule,
    Project,
    User,
    UserExperiment,
    UserRole,
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


def _set_role(db_session, user: User, role: UserRole) -> User:
    user.role = role
    db_session.commit()
    db_session.refresh(user)
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
    db_session.refresh(experiment)
    assert experiment.curation_status == CurationStatus.PENDING


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


def test_regular_user_cannot_list_pending_visibility_requests(client, db_session):
    headers = _auth_headers(client, "curation-regular@example.com")

    response = client.get("/curation/visibility-requests", headers=headers)

    assert response.status_code == 403
    assert response.json()["error"]["message"] == "curator role required"


def test_curator_can_list_pending_visibility_requests(client, db_session):
    owner_headers = _auth_headers(client, "curation-owner@example.com")
    owner = _user(db_session, "curation-owner@example.com")
    project = _project(db_session, owner)
    enzyme = _enzyme(db_session)
    experiment = _experiment(db_session, project, owner, enzyme, variant_name="Pending public")
    create_response = client.post(
        f"/experiments/{experiment.id}/visibility-requests",
        headers=owner_headers,
        json={"requested_visibility": "public"},
    )
    curator_headers = _auth_headers(client, "curation-curator@example.com")
    curator = _user(db_session, "curation-curator@example.com")
    _set_role(db_session, curator, UserRole.CURATOR)

    response = client.get("/curation/visibility-requests", headers=curator_headers)

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [create_response.json()["id"]]
    assert response.json()[0]["experiment"]["id"] == experiment.id


def test_curator_can_approve_visibility_request_and_audit_it(client, db_session):
    owner_headers = _auth_headers(client, "curation-approve-owner@example.com")
    owner = _user(db_session, "curation-approve-owner@example.com")
    project = _project(db_session, owner)
    enzyme = _enzyme(db_session)
    experiment = _experiment(db_session, project, owner, enzyme, variant_name="Approve public")
    request_id = client.post(
        f"/experiments/{experiment.id}/visibility-requests",
        headers=owner_headers,
        json={"requested_visibility": "public"},
    ).json()["id"]
    curator_headers = _auth_headers(client, "curation-approve-curator@example.com")
    curator = _user(db_session, "curation-approve-curator@example.com")
    _set_role(db_session, curator, UserRole.CURATOR)

    response = client.post(
        f"/curation/visibility-requests/{request_id}/approve",
        headers=curator_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    db_session.refresh(experiment)
    assert experiment.visibility == Visibility.PUBLIC
    assert experiment.curation_status == CurationStatus.APPROVED
    audit = db_session.scalar(
        select(AuditLog).where(
            AuditLog.action == "visibility_request.approve",
            AuditLog.target_id == request_id,
        )
    )
    assert audit is not None
    assert audit.actor_user_id == curator.id


def test_curator_can_reject_visibility_request_with_comment_and_audit_it(client, db_session):
    owner_headers = _auth_headers(client, "curation-reject-owner@example.com")
    owner = _user(db_session, "curation-reject-owner@example.com")
    project = _project(db_session, owner)
    enzyme = _enzyme(db_session)
    experiment = _experiment(db_session, project, owner, enzyme, variant_name="Reject public")
    request_id = client.post(
        f"/experiments/{experiment.id}/visibility-requests",
        headers=owner_headers,
        json={"requested_visibility": "public"},
    ).json()["id"]
    curator_headers = _auth_headers(client, "curation-reject-curator@example.com")
    curator = _user(db_session, "curation-reject-curator@example.com")
    _set_role(db_session, curator, UserRole.CURATOR)

    response = client.post(
        f"/curation/visibility-requests/{request_id}/reject",
        headers=curator_headers,
        json={"review_comment": "Missing raw assay condition."},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["review_comment"] == "Missing raw assay condition."
    db_session.refresh(experiment)
    assert experiment.visibility == Visibility.PRIVATE
    assert experiment.curation_status == CurationStatus.REJECTED
    audit = db_session.scalar(
        select(AuditLog).where(
            AuditLog.action == "visibility_request.reject",
            AuditLog.target_id == request_id,
        )
    )
    assert audit is not None
    assert audit.metadata_json == {"review_comment": "Missing raw assay condition."}


def test_reject_visibility_request_requires_comment(client, db_session):
    owner_headers = _auth_headers(client, "curation-reject-empty-owner@example.com")
    owner = _user(db_session, "curation-reject-empty-owner@example.com")
    project = _project(db_session, owner)
    enzyme = _enzyme(db_session)
    experiment = _experiment(db_session, project, owner, enzyme, variant_name="Reject empty")
    request_id = client.post(
        f"/experiments/{experiment.id}/visibility-requests",
        headers=owner_headers,
        json={"requested_visibility": "public"},
    ).json()["id"]
    curator_headers = _auth_headers(client, "curation-reject-empty-curator@example.com")
    curator = _user(db_session, "curation-reject-empty-curator@example.com")
    _set_role(db_session, curator, UserRole.CURATOR)

    response = client.post(
        f"/curation/visibility-requests/{request_id}/reject",
        headers=curator_headers,
        json={"review_comment": "   "},
    )

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "review_comment is required"
