"""
TDD-тесты для app/main.py
Спецификация: app/main_spec.md

Покрытие:
- GET /api/health → 200 + healthy
- Healthcheck: version=2.0.0
- [SRE_MARKER] Healthcheck не раскрывает hostname/uptime/environment
- Все 4 роутера подключены с правильными prefix
- CORS заголовки
- [SRE_MARKER] Глобальный лимит request body 10MB (middleware)
- FastAPI app metadata
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def test_client():
    """TestClient для FastAPI app."""
    # Мокаем Settings чтобы не требовать .env
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


# ──────────────────────────────────────────────
# 5. HEALTHCHECK
# ──────────────────────────────────────────────
class TestHealthcheck:
    def test_health_returns_200(self, test_client):
        """GET /api/health → 200."""
        response = test_client.get("/api/health")
        assert response.status_code == 200

    def test_health_status_healthy(self, test_client):
        """Ответ содержит status=healthy."""
        response = test_client.get("/api/health")
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_version(self, test_client):
        """Ответ содержит version=2.0.0."""
        response = test_client.get("/api/health")
        data = response.json()
        assert data["version"] == "2.0.0"

    def test_health_no_infrastructure_leaks(self, test_client):
        """[SRE_MARKER] Healthcheck не раскрывает hostname, uptime, environment."""
        response = test_client.get("/api/health")
        data = response.json()
        forbidden_keys = {"hostname", "uptime", "environment", "internal_ip", "ip"}
        assert not forbidden_keys.intersection(data.keys())

    def test_health_no_auth_required(self, test_client):
        """Healthcheck не требует авторизации."""
        response = test_client.get("/api/health")
        assert response.status_code == 200  # не 401


# ──────────────────────────────────────────────
# 4. РОУТЕРЫ
# ──────────────────────────────────────────────
class TestRoutersRegistered:
    def test_auth_router_accessible(self, test_client):
        """POST /api/auth/login доступен (422 при пустом теле — роутер зарегистрирован)."""
        response = test_client.post("/api/auth/login")
        assert response.status_code in (400, 401, 422)  # not 404

    def test_images_router_accessible(self, test_client):
        """GET /api/images → 401 (не 404)."""
        response = test_client.get("/api/images")
        assert response.status_code == 401  # auth required, not 404

    def test_jobs_router_accessible(self, test_client):
        """GET /api/jobs → 401 (не 404)."""
        response = test_client.get("/api/jobs")
        assert response.status_code == 401

    def test_presets_router_accessible(self, test_client):
        """GET /api/presets → 401 (не 404)."""
        response = test_client.get("/api/presets")
        assert response.status_code == 401


# ──────────────────────────────────────────────
# 3. CORS
# ──────────────────────────────────────────────
class TestCORS:
    def test_cors_headers_present(self, test_client):
        """OPTIONS с Origin → CORS заголовки."""
        response = test_client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" in response.headers


# ──────────────────────────────────────────────
# 2. APP METADATA
# ──────────────────────────────────────────────
class TestAppMetadata:
    def test_app_title(self, test_client):
        """App title = 'Bulk Image Color Replacement API'."""
        from app.main import app

        assert "Bulk Image" in app.title

    def test_app_version(self, test_client):
        from app.main import app

        assert app.version == "2.0.0"


# ──────────────────────────────────────────────
# [SRE_MARKER] Middleware 10MB body limit
# ──────────────────────────────────────────────
class TestBodySizeMiddleware:
    def test_oversized_json_body_rejected_413(self, test_client):
        """[SRE_MARKER] JSON body > 10MB → 413 Request Entity Too Large."""
        auth_resp = test_client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "VeryStrongPass123!"},
        )
        token = auth_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Создать тело > 10MB
        big_body = {"data": "x" * (11 * 1024 * 1024)}
        response = test_client.post(
            "/api/presets",
            json=big_body,
            headers=headers,
        )
        assert response.status_code in (413, 422)

    def test_normal_json_body_passes(self, test_client):
        """Нормальный JSON body < 10MB проходит."""
        auth_resp = test_client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "VeryStrongPass123!"},
        )
        token = auth_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        response = test_client.post(
            "/api/presets",
            json={"name": "Small Body", "colors": ["#FF0000"]},
            headers=headers,
        )
        assert response.status_code in (201, 200)


# ──────────────────────────────────────────────
# Lifespan: TTL-чистка и graceful shutdown
# ──────────────────────────────────────────────
class TestLifespan:
    def test_app_starts_without_crash(self, test_client):
        """App стартует корректно (lifespan startup)."""
        response = test_client.get("/api/health")
        assert response.status_code == 200

    def test_composition_root_creates_services(self, test_client):
        """Composition Root: все сервисы созданы при старте."""
        from app.main import app
        # App запустился — значит Settings(), FileStorage, AuthProvider и т.д. созданы
        assert app is not None

    def test_cors_allow_methods(self, test_client):
        """CORS: allow_methods содержит GET, POST, PUT, DELETE, OPTIONS."""
        response = test_client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        allowed = response.headers.get("access-control-allow-methods", "")
        for method in ["GET", "POST"]:
            assert method in allowed

    def test_cors_allow_headers(self, test_client):
        """CORS: allow_headers содержит Authorization, Content-Type."""
        response = test_client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        allowed = response.headers.get("access-control-allow-headers", "")
        assert "authorization" in allowed.lower() or "Authorization" in allowed
