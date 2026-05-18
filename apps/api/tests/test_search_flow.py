def test_enzyme_search_creates_family_profile_job(client):
    client.post(
        "/auth/register",
        json={
            "email": "searcher@example.com",
            "password": "search-password",
            "display_name": "Search Engineer",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "searcher@example.com", "password": "search-password"},
    ).json()["access_token"]

    project_response = client.post(
        "/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "MTGase optimization",
            "target_enzyme_module": "MICROBIAL_TRANSGLUTAMINASE_MATURE",
        },
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    search_response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "query": "microbial transglutaminase",
            "project_id": project_id,
        },
    )

    assert search_response.status_code == 200
    body = search_response.json()
    assert body["enzyme"]["name"]
    assert body["job_id"]
    assert body["cache_status"] in {"hit", "miss_refreshed", "stale_refreshed"}
