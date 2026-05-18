from datetime import datetime, timedelta

from sqlalchemy import select

from app.db.models import SearchCacheRecord


def test_enzyme_search_creates_family_profile_job(client, monkeypatch):
    enqueued_job_ids = []

    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            enqueued_job_ids.append(job_id)

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_placeholder_analysis",
        PlaceholderTask,
        raising=False,
    )

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
    assert enqueued_job_ids == [body["job_id"]]


def test_enzyme_search_reuses_fresh_search_cache(client, db_session, monkeypatch):
    enqueued_job_ids = []

    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            enqueued_job_ids.append(job_id)

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_placeholder_analysis",
        PlaceholderTask,
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "cache-searcher@example.com",
            "password": "search-password",
            "display_name": "Cache Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "cache-searcher@example.com", "password": "search-password"},
    ).json()["access_token"]

    first_response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "P12345"},
    )
    second_response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "P12345"},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["cache_status"] == "miss_refreshed"
    assert second_response.json()["cache_status"] == "hit"
    assert second_response.json()["enzyme"]["id"] == first_response.json()["enzyme"]["id"]

    cache_records = list(
        db_session.scalars(
            select(SearchCacheRecord).where(SearchCacheRecord.normalized_query == "P12345")
        )
    )
    assert len(cache_records) == 1
    assert cache_records[0].payload_json["enzyme_entry_id"] == first_response.json()["enzyme"]["id"]
    assert enqueued_job_ids == [first_response.json()["job_id"], second_response.json()["job_id"]]


def test_enzyme_search_refreshes_stale_search_cache(client, db_session, monkeypatch):
    class PlaceholderTask:
        @staticmethod
        def delay(job_id):
            return None

    monkeypatch.setattr(
        "app.api.routes.enzymes.run_placeholder_analysis",
        PlaceholderTask,
        raising=False,
    )

    client.post(
        "/auth/register",
        json={
            "email": "stale-cache-searcher@example.com",
            "password": "search-password",
            "display_name": "Stale Cache Searcher",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": "stale-cache-searcher@example.com", "password": "search-password"},
    ).json()["access_token"]

    first_response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "P67890"},
    )
    assert first_response.status_code == 200

    cache_record = db_session.scalar(
        select(SearchCacheRecord).where(SearchCacheRecord.normalized_query == "P67890")
    )
    assert cache_record is not None
    cache_record.last_refreshed_at = datetime.utcnow() - timedelta(days=16)
    db_session.commit()

    second_response = client.post(
        "/enzymes/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "P67890"},
    )

    assert second_response.status_code == 200
    assert second_response.json()["cache_status"] == "stale_refreshed"
    db_session.refresh(cache_record)
    assert cache_record.last_refreshed_at > datetime.utcnow() - timedelta(days=1)
