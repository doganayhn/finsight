def test_health_returns_ok_without_database(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_frontend_origin_is_allowed(client):
    response = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unconfigured_origin_is_not_allowed(client):
    response = client.get("/api/v1/health", headers={"Origin": "https://untrusted.invalid"})
    assert "access-control-allow-origin" not in response.headers
