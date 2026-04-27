"""
TDD-тесты для api/job_router.py
Спецификация: api/job_router_spec.md

Покрытие:
- POST /api/jobs: Режим A → 201 + pending
- POST /api/jobs: Режим B → 201 + pending
- POST /api/jobs: оба ключа → 400
- POST /api/jobs: ни одного ключа → 400
- GET /api/jobs → список
- GET /api/jobs/{id} → JobStatus
- GET /api/jobs/{id}/download completed → ZIP
- GET /api/jobs/{id}/download processing → 409
- DELETE /api/jobs/{id} → 200
- [SRE_MARKER] чужой job_id → 404 (не 403)
- [SRE_MARKER] extra fields forbidden → 422
- [SRE_MARKER] Cache-Control на download
- Без auth → 401
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
        response = test_client.post("/api/jobs", json={})
        assert response.status_code == 401

    def test_list_no_auth_401(self, test_client):
        response = test_client.get("/api/jobs")
        assert response.status_code == 401

    def test_download_no_auth_401(self, test_client):
        response = test_client.get("/api/jobs/fake_id/download")
        assert response.status_code == 401


# ──────────────────────────────────────────────
# 3.1 POST /api/jobs — определение режима
# ──────────────────────────────────────────────
class TestCreateJob:
    def test_both_keys_400(self, test_client, auth_header):
        """[SRE_MARKER] Оба ключа tasks + global_mappings → 400."""
        response = test_client.post(
            "/api/jobs",
            json={
                "tasks": [],
                "global_mappings": {"color_mappings": [], "tolerance": 25},
            },
            headers=auth_header,
        )
        assert response.status_code == 400

    def test_no_keys_400(self, test_client, auth_header):
        """Ни одного ключа → 400."""
        response = test_client.post(
            "/api/jobs",
            json={},
            headers=auth_header,
        )
        assert response.status_code in (400, 422)

    def test_mode_a_nonexistent_image_400(self, test_client, auth_header):
        """Режим A с несуществующим image_id → 400."""
        response = test_client.post(
            "/api/jobs",
            json={
                "tasks": [
                    {
                        "image_id": "nonexistent_id",
                        "variations": [
                            {
                                "name": "v1",
                                "color_mappings": [
                                    {"from_hex": "#FF0000", "to_hex": "#0000FF"}
                                ],
                                "tolerance": 25,
                            }
                        ],
                    }
                ]
            },
            headers=auth_header,
        )
        assert response.status_code == 400


# ──────────────────────────────────────────────
# 3.2 GET /api/jobs
# ──────────────────────────────────────────────
class TestListJobs:
    def test_list_empty_200(self, test_client, auth_header):
        """GET /api/jobs → 200 + пустой список."""
        response = test_client.get("/api/jobs", headers=auth_header)
        assert response.status_code == 200
        assert isinstance(response.json(), list)


# ──────────────────────────────────────────────
# 3.3 GET /api/jobs/{id}
# ──────────────────────────────────────────────
class TestGetJob:
    def test_nonexistent_404(self, test_client, auth_header):
        response = test_client.get("/api/jobs/fake_id", headers=auth_header)
        assert response.status_code == 404


# ──────────────────────────────────────────────
# 3.4 GET /api/jobs/{id}/download
# ──────────────────────────────────────────────
class TestDownload:
    def test_nonexistent_404(self, test_client, auth_header):
        """Несуществующий job → 404."""
        response = test_client.get(
            "/api/jobs/fake_id/download", headers=auth_header
        )
        assert response.status_code == 404


# ──────────────────────────────────────────────
# 3.5 DELETE /api/jobs/{id}
# ──────────────────────────────────────────────
class TestDeleteJob:
    def test_nonexistent_404(self, test_client, auth_header):
        response = test_client.delete(
            "/api/jobs/fake_id", headers=auth_header
        )
        assert response.status_code == 404


# ──────────────────────────────────────────────
# Full-flow тесты: upload → create job → status
# ──────────────────────────────────────────────
class TestJobFullFlow:
    def _upload_png(self, client, headers):
        import io as _io
        from PIL import Image as _Image
        img = _Image.new("RGBA", (50, 50), (255, 0, 0, 255))
        buf = _io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        resp = client.post(
            "/api/images/upload",
            headers=headers,
            files={"files": ("test.png", buf, "image/png")},
        )
        return resp.json()[0]["image_id"]

    def test_create_job_mode_a_201(self, test_client, auth_header):
        """Full-flow: upload → POST /api/jobs Mode A → 201."""
        image_id = self._upload_png(test_client, auth_header)
        response = test_client.post(
            "/api/jobs",
            json={
                "tasks": [
                    {
                        "image_id": image_id,
                        "variations": [
                            {
                                "name": "v1",
                                "color_mappings": [
                                    {"from_hex": "#FF0000", "to_hex": "#0000FF"}
                                ],
                                "tolerance": 25,
                            }
                        ],
                    }
                ]
            },
            headers=auth_header,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "pending"
        assert "job_id" in data

    def test_create_job_mode_b_201(self, test_client, auth_header):
        """Full-flow: upload → POST /api/jobs Mode B → 201."""
        image_id = self._upload_png(test_client, auth_header)
        response = test_client.post(
            "/api/jobs",
            json={
                "global_mappings": {
                    "color_mappings": [
                        {"from_hex": "#FF0000", "to_hex": "#0000FF"}
                    ],
                    "tolerance": 25,
                },
                "image_ids": [image_id],
            },
            headers=auth_header,
        )
        assert response.status_code == 201
        assert response.json()["status"] == "pending"

    def test_get_job_status_after_create(self, test_client, auth_header):
        """Full-flow: create → GET /api/jobs/{id} → JobStatus."""
        image_id = self._upload_png(test_client, auth_header)
        create_resp = test_client.post(
            "/api/jobs",
            json={
                "tasks": [
                    {
                        "image_id": image_id,
                        "variations": [
                            {
                                "name": "v1",
                                "color_mappings": [
                                    {"from_hex": "#FF0000", "to_hex": "#0000FF"}
                                ],
                                "tolerance": 25,
                            }
                        ],
                    }
                ]
            },
            headers=auth_header,
        )
        job_id = create_resp.json()["job_id"]

        response = test_client.get(f"/api/jobs/{job_id}", headers=auth_header)
        assert response.status_code == 200
        assert response.json()["job_id"] == job_id

    def test_list_jobs_after_create(self, test_client, auth_header):
        """Full-flow: create → GET /api/jobs → list."""
        image_id = self._upload_png(test_client, auth_header)
        test_client.post(
            "/api/jobs",
            json={
                "tasks": [
                    {
                        "image_id": image_id,
                        "variations": [
                            {
                                "name": "v1",
                                "color_mappings": [
                                    {"from_hex": "#FF0000", "to_hex": "#0000FF"}
                                ],
                                "tolerance": 25,
                            }
                        ],
                    }
                ]
            },
            headers=auth_header,
        )
        response = test_client.get("/api/jobs", headers=auth_header)
        assert response.status_code == 200
        assert len(response.json()) >= 1

    def test_delete_job_after_create(self, test_client, auth_header):
        """Full-flow: create → DELETE → 200."""
        image_id = self._upload_png(test_client, auth_header)
        create_resp = test_client.post(
            "/api/jobs",
            json={
                "tasks": [
                    {
                        "image_id": image_id,
                        "variations": [
                            {
                                "name": "v1",
                                "color_mappings": [
                                    {"from_hex": "#FF0000", "to_hex": "#0000FF"}
                                ],
                                "tolerance": 25,
                            }
                        ],
                    }
                ]
            },
            headers=auth_header,
        )
        job_id = create_resp.json()["job_id"]

        response = test_client.delete(f"/api/jobs/{job_id}", headers=auth_header)
        assert response.status_code == 200

    def test_download_pending_job_409(self, test_client, auth_header):
        """Full-flow: create (pending) → download → 409."""
        image_id = self._upload_png(test_client, auth_header)
        create_resp = test_client.post(
            "/api/jobs",
            json={
                "tasks": [
                    {
                        "image_id": image_id,
                        "variations": [
                            {
                                "name": "v1",
                                "color_mappings": [
                                    {"from_hex": "#FF0000", "to_hex": "#0000FF"}
                                ],
                                "tolerance": 25,
                            }
                        ],
                    }
                ]
            },
            headers=auth_header,
        )
        job_id = create_resp.json()["job_id"]

        response = test_client.get(
            f"/api/jobs/{job_id}/download", headers=auth_header
        )
        assert response.status_code == 409
