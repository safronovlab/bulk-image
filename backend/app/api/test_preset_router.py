"""
TDD-тесты для api/preset_router.py
Спецификация: api/preset_router_spec.md

Покрытие:
- POST /api/presets → 201 + Preset
- POST дубликат имени → 400
- GET /api/presets → список
- GET /api/presets/{id} → конкретный
- GET несуществующий → 404
- PUT /api/presets/{id} → обновлённый
- DELETE → 200
- DELETE несуществующий → 404
- Без авторизации → 401
- [SRE_MARKER] SSRF: source_image_url с localhost → 400
- [SRE_MARKER] SSRF: source_image_url с приватным IP → 400
"""

import pytest
from unittest.mock import patch


@pytest.fixture
def test_client():
    with patch.dict(
        "os.environ",
        {
            "AUTH_USERNAME": "admin",
            "AUTH_PASSWORD": "VeryStrongPass123!",
            "CORS_ORIGINS": '["http://localhost:3000"]',
            "UPLOAD_DIR": "/tmp/test_uploads",
            "PREVIEW_DIR": "/tmp/test_previews",
            "RESULT_DIR": "/tmp/test_results",
            "PRESETS_PATH": "/tmp/test_presets.json",
        },
    ):
        from app.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        yield client


@pytest.fixture
def auth_header(test_client) -> dict:
    resp = test_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "VeryStrongPass123!"},
    )
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


# ──────────────────────────────────────────────
# Без авторизации
# ──────────────────────────────────────────────
class TestNoAuth:
    def test_create_no_auth_401(self, test_client):
        response = test_client.post(
            "/api/presets",
            json={"name": "Test", "colors": ["#FF0000"]},
        )
        assert response.status_code == 401

    def test_list_no_auth_401(self, test_client):
        response = test_client.get("/api/presets")
        assert response.status_code == 401

    def test_get_no_auth_401(self, test_client):
        response = test_client.get("/api/presets/some_id")
        assert response.status_code == 401

    def test_update_no_auth_401(self, test_client):
        response = test_client.put(
            "/api/presets/some_id",
            json={"name": "New Name"},
        )
        assert response.status_code == 401

    def test_delete_no_auth_401(self, test_client):
        response = test_client.delete("/api/presets/some_id")
        assert response.status_code == 401


# ──────────────────────────────────────────────
# 3.1 POST /api/presets
# ──────────────────────────────────────────────
class TestCreatePreset:
    def test_create_201(self, test_client, auth_header):
        """POST → 201 + Preset с id и created_at."""
        response = test_client.post(
            "/api/presets",
            json={
                "name": "Jordan Retro",
                "colors": ["#0C56A0", "#000000", "#FFFFFF"],
            },
            headers=auth_header,
        )
        assert response.status_code == 201
        data = response.json()
        assert "preset_id" in data
        assert "created_at" in data
        assert data["name"] == "Jordan Retro"

    def test_create_with_source_url(self, test_client, auth_header):
        response = test_client.post(
            "/api/presets",
            json={
                "name": "With URL",
                "colors": ["#FF0000"],
                "source_image_url": "https://example.com/shoe.jpg",
            },
            headers=auth_header,
        )
        assert response.status_code == 201
        assert response.json()["source_image_url"] == "https://example.com/shoe.jpg"

    def test_create_duplicate_name_400(self, test_client, auth_header):
        """Дубликат имени → 400."""
        test_client.post(
            "/api/presets",
            json={"name": "Duplicate", "colors": ["#FF0000"]},
            headers=auth_header,
        )
        response = test_client.post(
            "/api/presets",
            json={"name": "Duplicate", "colors": ["#00FF00"]},
            headers=auth_header,
        )
        assert response.status_code == 400

    def test_create_invalid_hex_422(self, test_client, auth_header):
        """Невалидный HEX → 422."""
        response = test_client.post(
            "/api/presets",
            json={"name": "Invalid", "colors": ["not-hex"]},
            headers=auth_header,
        )
        assert response.status_code == 422

    def test_create_empty_colors_422(self, test_client, auth_header):
        """Пустой массив colors → 422."""
        response = test_client.post(
            "/api/presets",
            json={"name": "Empty", "colors": []},
            headers=auth_header,
        )
        assert response.status_code == 422


# ──────────────────────────────────────────────
# 3.2 GET /api/presets
# ──────────────────────────────────────────────
class TestListPresets:
    def test_list_200(self, test_client, auth_header):
        response = test_client.get("/api/presets", headers=auth_header)
        assert response.status_code == 200
        assert isinstance(response.json(), list)


# ──────────────────────────────────────────────
# 3.3 GET /api/presets/{id}
# ──────────────────────────────────────────────
class TestGetPreset:
    def test_nonexistent_404(self, test_client, auth_header):
        response = test_client.get(
            "/api/presets/nonexistent_id", headers=auth_header
        )
        assert response.status_code == 404

    def test_get_existing(self, test_client, auth_header):
        # Create first
        create_resp = test_client.post(
            "/api/presets",
            json={"name": "GetTest", "colors": ["#FF0000"]},
            headers=auth_header,
        )
        preset_id = create_resp.json()["preset_id"]

        response = test_client.get(
            f"/api/presets/{preset_id}", headers=auth_header
        )
        assert response.status_code == 200
        assert response.json()["name"] == "GetTest"


# ──────────────────────────────────────────────
# 3.4 PUT /api/presets/{id}
# ──────────────────────────────────────────────
class TestUpdatePreset:
    def test_update_name_200(self, test_client, auth_header):
        create_resp = test_client.post(
            "/api/presets",
            json={"name": "ToUpdate", "colors": ["#FF0000"]},
            headers=auth_header,
        )
        preset_id = create_resp.json()["preset_id"]

        response = test_client.put(
            f"/api/presets/{preset_id}",
            json={"name": "Updated Name"},
            headers=auth_header,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    def test_update_nonexistent_404(self, test_client, auth_header):
        response = test_client.put(
            "/api/presets/fake_id",
            json={"name": "Nope"},
            headers=auth_header,
        )
        assert response.status_code == 404


# ──────────────────────────────────────────────
# 3.5 DELETE /api/presets/{id}
# ──────────────────────────────────────────────
class TestDeletePreset:
    def test_delete_existing_200(self, test_client, auth_header):
        create_resp = test_client.post(
            "/api/presets",
            json={"name": "ToDelete", "colors": ["#FF0000"]},
            headers=auth_header,
        )
        preset_id = create_resp.json()["preset_id"]

        response = test_client.delete(
            f"/api/presets/{preset_id}", headers=auth_header
        )
        assert response.status_code == 200

    def test_delete_nonexistent_404(self, test_client, auth_header):
        response = test_client.delete(
            "/api/presets/nonexistent_id", headers=auth_header
        )
        assert response.status_code == 404


# ──────────────────────────────────────────────
# [SRE_MARKER] SSRF-валидация source_image_url
# ──────────────────────────────────────────────
class TestSSRFProtection:
    def test_localhost_rejected(self, test_client, auth_header):
        """[SRE_MARKER] SSRF: localhost → 422 (Pydantic) или 400."""
        response = test_client.post(
            "/api/presets",
            json={
                "name": "SSRF Test 1",
                "colors": ["#FF0000"],
                "source_image_url": "https://localhost/evil",
            },
            headers=auth_header,
        )
        assert response.status_code in (400, 422)

    def test_private_ip_10_rejected(self, test_client, auth_header):
        """[SRE_MARKER] SSRF: 10.0.0.1 → 422/400."""
        response = test_client.post(
            "/api/presets",
            json={
                "name": "SSRF Test 2",
                "colors": ["#FF0000"],
                "source_image_url": "https://10.0.0.1/secret",
            },
            headers=auth_header,
        )
        assert response.status_code in (400, 422)

    def test_private_ip_192_rejected(self, test_client, auth_header):
        """[SRE_MARKER] SSRF: 192.168.x.x → 422/400."""
        response = test_client.post(
            "/api/presets",
            json={
                "name": "SSRF Test 3",
                "colors": ["#FF0000"],
                "source_image_url": "https://192.168.1.1/admin",
            },
            headers=auth_header,
        )
        assert response.status_code in (400, 422)

    def test_http_scheme_rejected(self, test_client, auth_header):
        """[SRE_MARKER] SSRF: http:// → 422/400 (только https)."""
        response = test_client.post(
            "/api/presets",
            json={
                "name": "SSRF Test 4",
                "colors": ["#FF0000"],
                "source_image_url": "http://example.com/image.jpg",
            },
            headers=auth_header,
        )
        assert response.status_code in (400, 422)

    def test_link_local_rejected(self, test_client, auth_header):
        """[SRE_MARKER] SSRF: 169.254.x.x (AWS metadata)."""
        response = test_client.post(
            "/api/presets",
            json={
                "name": "SSRF Test 5",
                "colors": ["#FF0000"],
                "source_image_url": "https://169.254.169.254/latest/meta-data/",
            },
            headers=auth_header,
        )
        assert response.status_code in (400, 422)
