from sqlalchemy import select

from app.db.models import AnalysisJob, JobStatus, User


def _auth_headers(client, email: str = "jobs@example.com") -> dict[str, str]:
    client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "jobs-password",
            "display_name": "Jobs Engineer",
        },
    )
    token = client.post(
        "/auth/login",
        json={"email": email, "password": "jobs-password"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_retry_failed_rosetta_job_requeues_and_clears_error(client, db_session, monkeypatch):
    headers = _auth_headers(client)
    user = db_session.scalar(select(User).where(User.email == "jobs@example.com"))
    assert user is not None
    job = AnalysisJob(
        job_type="rosetta_ddg",
        status=JobStatus.FAILED,
        parameters_json={"mutation_string": "L10A"},
        error_message="Rosetta executable missing",
        created_by=user.id,
    )
    db_session.add(job)
    db_session.commit()
    enqueued_job_ids = []

    class RosettaTask:
        @staticmethod
        def delay(job_id):
            enqueued_job_ids.append(job_id)

    monkeypatch.setattr("app.api.routes.jobs.run_rosetta_ddg", RosettaTask, raising=False)

    response = client.post(f"/jobs/{job.id}/retry", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == job.id
    assert body["status"] == "queued"
    assert body["error_message"] is None
    assert enqueued_job_ids == [job.id]


def test_retry_rejects_non_failed_job(client, db_session, monkeypatch):
    headers = _auth_headers(client, email="queued-jobs@example.com")
    user = db_session.scalar(select(User).where(User.email == "queued-jobs@example.com"))
    assert user is not None
    job = AnalysisJob(job_type="rosetta_ddg", status=JobStatus.QUEUED, created_by=user.id)
    db_session.add(job)
    db_session.commit()

    class RosettaTask:
        @staticmethod
        def delay(job_id):
            raise AssertionError(f"queued job should not be retried: {job_id}")

    monkeypatch.setattr("app.api.routes.jobs.run_rosetta_ddg", RosettaTask, raising=False)

    response = client.post(f"/jobs/{job.id}/retry", headers=headers)

    assert response.status_code == 409
    assert "only failed jobs can be retried" in response.json()["error"]["message"]
