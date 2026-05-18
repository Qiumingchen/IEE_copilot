def test_not_found_uses_error_envelope(client):
    response = client.get("/not-a-real-route")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Not Found",
            "details": None,
        }
    }


def test_validation_error_uses_error_envelope(client):
    response = client.post(
        "/auth/login",
        json={"email": "not-an-email", "password": "demo-password"},
    )

    body = response.json()
    assert response.status_code == 422
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"] == "Request validation failed"
    assert isinstance(body["error"]["details"], list)
