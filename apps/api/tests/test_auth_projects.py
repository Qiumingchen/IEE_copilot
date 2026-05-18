from sqlalchemy import select

from app.db.models import Project, ProjectMember, ProjectMemberRole, User


def test_register_login_and_me(client):
    register_response = client.post(
        "/auth/register",
        json={
            "email": "engineer@example.com",
            "password": "correct-horse-battery-staple",
            "display_name": "Enzyme Engineer",
        },
    )

    assert register_response.status_code == 201
    assert register_response.json()["email"] == "engineer@example.com"

    login_response = client.post(
        "/auth/login",
        json={
            "email": "engineer@example.com",
            "password": "correct-horse-battery-staple",
        },
    )

    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert me_response.status_code == 200
    assert me_response.json()["email"] == "engineer@example.com"


def test_register_and_login_allow_local_development_email(client):
    register_response = client.post(
        "/auth/register",
        json={
            "email": "demo@iee.local",
            "password": "demo-password",
            "display_name": "IEE Demo Admin",
        },
    )

    assert register_response.status_code == 201
    assert register_response.json()["email"] == "demo@iee.local"

    login_response = client.post(
        "/auth/login",
        json={"email": "demo@iee.local", "password": "demo-password"},
    )

    assert login_response.status_code == 200
    assert login_response.json()["token_type"] == "bearer"


def test_create_and_list_projects_for_current_user(client):
    client.post(
        "/auth/register",
        json={
            "email": "owner@example.com",
            "password": "project-password",
            "display_name": "Project Owner",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "owner@example.com", "password": "project-password"},
    ).json()["access_token"]

    create_response = client.post(
        "/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "AQGT optimization",
            "description": "Improve glycosylation activity",
            "target_enzyme_module": "ANTHRAQUINONE_GLYCOSYLTRANSFERASE",
        },
    )

    assert create_response.status_code == 201
    assert create_response.json()["target_enzyme_module"] == "ANTHRAQUINONE_GLYCOSYLTRANSFERASE"

    list_response = client.get("/projects", headers={"Authorization": f"Bearer {token}"})

    assert list_response.status_code == 200
    assert [project["name"] for project in list_response.json()] == ["AQGT optimization"]


def test_member_does_not_see_non_owned_project_in_project_list(client, db_session):
    client.post(
        "/auth/register",
        json={
            "email": "owner-filter@example.com",
            "password": "owner-password",
            "display_name": "Owner",
        },
    )
    client.post(
        "/auth/register",
        json={
            "email": "member-filter@example.com",
            "password": "member-password",
            "display_name": "Member",
        },
    )
    owner_token = client.post(
        "/auth/login",
        json={"email": "owner-filter@example.com", "password": "owner-password"},
    ).json()["access_token"]
    member_token = client.post(
        "/auth/login",
        json={"email": "member-filter@example.com", "password": "member-password"},
    ).json()["access_token"]

    create_response = client.post(
        "/projects",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "Owner-only project"},
    )
    assert create_response.status_code == 201

    project = db_session.scalar(select(Project).where(Project.name == "Owner-only project"))
    member = db_session.scalar(select(User).where(User.email == "member-filter@example.com"))
    assert project is not None
    assert member is not None
    db_session.add(
        ProjectMember(
            project_id=project.id,
            user_id=member.id,
            role=ProjectMemberRole.MEMBER,
        )
    )
    db_session.commit()

    list_response = client.get("/projects", headers={"Authorization": f"Bearer {member_token}"})

    assert list_response.status_code == 200
    assert list_response.json() == []
