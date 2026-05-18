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
