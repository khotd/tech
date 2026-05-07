from fastapi.testclient import TestClient

from backend.app import app


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_metrics_endpoint():
    with TestClient(app) as client:
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "dating_api_requests_total" in response.text


def test_photo_upload_without_profile():
    with TestClient(app) as client:
        response = client.post("/profile/photo/upload", json={"user_id": 999999, "file_id": "telegram-file-id"})
        assert response.status_code == 404


def test_photo_delete_without_profile():
    with TestClient(app) as client:
        response = client.post("/profile/photo/delete", json={"user_id": 999999, "photo_id": 1})
        assert response.status_code == 404
