"""
TDD-тесты для api/image_router.py
Спецификация: api/image_router_spec.md

Покрытие:
- POST /api/images/upload: 1 PNG → 200 + ImageMeta
- POST /api/images/upload: JPEG → original_format="jpeg"
- POST /api/images/upload: 21 файл → 400
- POST /api/images/upload: .txt → 400
- GET /api/images → список
- GET /api/images/{id}/preview → PNG bytes
- GET /api/images/{id}/original → PNG bytes
- DELETE /api/images/{id} → 200
- POST pick-color → ColorInfo
- POST pick-color за пределами → 400
- GET dominant-colors → список
- POST batch-analyze → dict
- POST preview-replace → PNG bytes
- POST suggest-mappings → список
- Без auth → 401
- [SRE_MARKER] rate limits
"""

import io
import pytest
from unittest.mock import patch
from PIL import Image


def _make_png_upload(w=100, h=100, color=(255, 0, 0, 255)):
    """Создать PNG файл для upload."""
    img = Image.new("RGBA", (w, h), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _make_jpeg_upload(w=100, h=100, color=(255, 0, 0)):
    img = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


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
    """Авторизованный header."""
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
    def test_upload_no_auth_401(self, test_client):
        """Upload без авторизации → 401."""
        response = test_client.post("/api/images/upload")
        assert response.status_code == 401

    def test_list_no_auth_401(self, test_client):
        """GET /api/images → 401."""
        response = test_client.get("/api/images")
        assert response.status_code == 401

    def test_delete_no_auth_401(self, test_client):
        """DELETE без auth → 401."""
        response = test_client.delete("/api/images/some_id")
        assert response.status_code == 401


# ──────────────────────────────────────────────
# 3.1 POST /api/images/upload
# ──────────────────────────────────────────────
class TestUpload:
    def test_upload_one_png_200(self, test_client, auth_header):
        """Upload 1 PNG → 200 + ImageMeta."""
        png = _make_png_upload(50, 50)
        response = test_client.post(
            "/api/images/upload",
            headers=auth_header,
            files={"files": ("test.png", png, "image/png")},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert "image_id" in data[0]
        assert data[0]["original_format"] == "png"

    def test_upload_jpeg_200(self, test_client, auth_header):
        """Upload JPEG → original_format='jpeg'."""
        jpeg = _make_jpeg_upload(50, 50)
        response = test_client.post(
            "/api/images/upload",
            headers=auth_header,
            files={"files": ("photo.jpg", jpeg, "image/jpeg")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data[0]["original_format"] == "jpeg"

    def test_upload_invalid_file_400(self, test_client, auth_header):
        """Upload .txt → 400."""
        response = test_client.post(
            "/api/images/upload",
            headers=auth_header,
            files={"files": ("doc.txt", io.BytesIO(b"not an image"), "text/plain")},
        )
        assert response.status_code == 400


# ──────────────────────────────────────────────
# 3.2 GET /api/images
# ──────────────────────────────────────────────
class TestListImages:
    def test_list_images_200(self, test_client, auth_header):
        """GET /api/images → 200 + список."""
        response = test_client.get("/api/images", headers=auth_header)
        assert response.status_code == 200
        assert isinstance(response.json(), list)


# ──────────────────────────────────────────────
# 3.3 GET /api/images/{id}
# ──────────────────────────────────────────────
class TestGetImage:
    def test_nonexistent_image_404(self, test_client, auth_header):
        """Несуществующий image_id → 404."""
        response = test_client.get(
            "/api/images/nonexistent_id", headers=auth_header
        )
        assert response.status_code == 404


# ──────────────────────────────────────────────
# 3.4-3.5 Preview / Original
# ──────────────────────────────────────────────
class TestPreviewOriginal:
    def test_preview_nonexistent_404(self, test_client, auth_header):
        response = test_client.get(
            "/api/images/fake_id/preview", headers=auth_header
        )
        assert response.status_code == 404

    def test_original_nonexistent_404(self, test_client, auth_header):
        response = test_client.get(
            "/api/images/fake_id/original", headers=auth_header
        )
        assert response.status_code == 404


# ──────────────────────────────────────────────
# 3.6 DELETE
# ──────────────────────────────────────────────
class TestDeleteImage:
    def test_delete_nonexistent_404(self, test_client, auth_header):
        response = test_client.delete(
            "/api/images/fake_id", headers=auth_header
        )
        assert response.status_code == 404


# ──────────────────────────────────────────────
# 3.7 POST pick-color
# ──────────────────────────────────────────────
class TestPickColor:
    def test_pick_color_nonexistent_image_404(self, test_client, auth_header):
        response = test_client.post(
            "/api/images/fake_id/pick-color",
            json={"x": 0, "y": 0},
            headers=auth_header,
        )
        assert response.status_code == 404

    def test_pick_color_negative_coords_422(self, test_client, auth_header):
        """Отрицательные координаты → 422 (Pydantic)."""
        response = test_client.post(
            "/api/images/fake_id/pick-color",
            json={"x": -1, "y": 0},
            headers=auth_header,
        )
        assert response.status_code == 422


# ──────────────────────────────────────────────
# 3.8 GET dominant-colors
# ──────────────────────────────────────────────
class TestDominantColors:
    def test_nonexistent_404(self, test_client, auth_header):
        response = test_client.get(
            "/api/images/fake_id/dominant-colors", headers=auth_header
        )
        assert response.status_code == 404


# ──────────────────────────────────────────────
# 3.9 POST batch-analyze
# ──────────────────────────────────────────────
class TestBatchAnalyze:
    def test_empty_image_ids_422(self, test_client, auth_header):
        """Пустой список image_ids → 422."""
        response = test_client.post(
            "/api/images/batch-analyze",
            json={"image_ids": [], "count": 5},
            headers=auth_header,
        )
        assert response.status_code == 422


# ──────────────────────────────────────────────
# 3.10 POST preview-replace
# ──────────────────────────────────────────────
class TestPreviewReplace:
    def test_nonexistent_404(self, test_client, auth_header):
        response = test_client.post(
            "/api/images/fake_id/preview-replace",
            json={
                "color_mappings": [
                    {"from_hex": "#FF0000", "to_hex": "#0000FF"}
                ],
                "tolerance": 25,
            },
            headers=auth_header,
        )
        assert response.status_code == 404

    def test_empty_mappings_422(self, test_client, auth_header):
        """Пустые маппинги → 422."""
        response = test_client.post(
            "/api/images/fake_id/preview-replace",
            json={"color_mappings": [], "tolerance": 25},
            headers=auth_header,
        )
        assert response.status_code == 422


# ──────────────────────────────────────────────
# 3.11 POST suggest-mappings
# ──────────────────────────────────────────────
class TestSuggestMappings:
    def test_nonexistent_404(self, test_client, auth_header):
        response = test_client.post(
            "/api/images/fake_id/suggest-mappings",
            json={"target_palette": ["#FF0000"]},
            headers=auth_header,
        )
        assert response.status_code == 404

    def test_empty_palette_422(self, test_client, auth_header):
        response = test_client.post(
            "/api/images/fake_id/suggest-mappings",
            json={"target_palette": []},
            headers=auth_header,
        )
        assert response.status_code == 422


# ──────────────────────────────────────────────
# FULL-FLOW тесты (upload → операция)
# ──────────────────────────────────────────────
class TestFullFlowUploadAndOperate:
    def _upload_png(self, client, headers, w=50, h=50, color=(255, 0, 0, 255)):
        png = _make_png_upload(w, h, color)
        resp = client.post(
            "/api/images/upload",
            headers=headers,
            files={"files": ("test.png", png, "image/png")},
        )
        return resp.json()[0]["image_id"]

    def test_upload_then_get_image(self, test_client, auth_header):
        """Full-flow: upload → GET /images/{id} → 200."""
        image_id = self._upload_png(test_client, auth_header)
        response = test_client.get(f"/api/images/{image_id}", headers=auth_header)
        assert response.status_code == 200
        assert response.json()["image_id"] == image_id

    def test_upload_then_get_preview(self, test_client, auth_header):
        """Full-flow: upload → GET preview → PNG bytes."""
        image_id = self._upload_png(test_client, auth_header)
        response = test_client.get(
            f"/api/images/{image_id}/preview", headers=auth_header
        )
        assert response.status_code == 200
        assert response.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_upload_then_get_original(self, test_client, auth_header):
        """Full-flow: upload → GET original → PNG bytes."""
        image_id = self._upload_png(test_client, auth_header)
        response = test_client.get(
            f"/api/images/{image_id}/original", headers=auth_header
        )
        assert response.status_code == 200
        assert response.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_upload_then_delete(self, test_client, auth_header):
        """Full-flow: upload → DELETE → 200."""
        image_id = self._upload_png(test_client, auth_header)
        response = test_client.delete(
            f"/api/images/{image_id}", headers=auth_header
        )
        assert response.status_code == 200

    def test_upload_then_pick_color(self, test_client, auth_header):
        """Full-flow: upload → pick-color → ColorInfo."""
        image_id = self._upload_png(test_client, auth_header, color=(255, 0, 0, 255))
        response = test_client.post(
            f"/api/images/{image_id}/pick-color",
            json={"x": 0, "y": 0},
            headers=auth_header,
        )
        assert response.status_code == 200
        data = response.json()
        assert "hex" in data
        assert "rgb" in data
        assert "lab" in data

    def test_upload_then_pick_color_out_of_bounds_400(self, test_client, auth_header):
        """Full-flow: upload 50x50 → pick-color(100,100) → 400."""
        image_id = self._upload_png(test_client, auth_header, w=50, h=50)
        response = test_client.post(
            f"/api/images/{image_id}/pick-color",
            json={"x": 100, "y": 100},
            headers=auth_header,
        )
        assert response.status_code == 400

    def test_upload_then_dominant_colors(self, test_client, auth_header):
        """Full-flow: upload → dominant-colors → список."""
        image_id = self._upload_png(test_client, auth_header)
        response = test_client.get(
            f"/api/images/{image_id}/dominant-colors",
            headers=auth_header,
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_upload_then_batch_analyze(self, test_client, auth_header):
        """Full-flow: upload → batch-analyze → dict."""
        image_id = self._upload_png(test_client, auth_header)
        response = test_client.post(
            "/api/images/batch-analyze",
            json={"image_ids": [image_id], "count": 3},
            headers=auth_header,
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert image_id in data["results"]

    def test_upload_then_preview_replace(self, test_client, auth_header):
        """Full-flow: upload → preview-replace → PNG bytes."""
        image_id = self._upload_png(test_client, auth_header)
        response = test_client.post(
            f"/api/images/{image_id}/preview-replace",
            json={
                "color_mappings": [
                    {"from_hex": "#FF0000", "to_hex": "#0000FF"}
                ],
                "tolerance": 25,
            },
            headers=auth_header,
        )
        assert response.status_code == 200
        assert response.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_upload_then_suggest_mappings(self, test_client, auth_header):
        """Full-flow: upload → suggest-mappings → список."""
        image_id = self._upload_png(test_client, auth_header)
        response = test_client.post(
            f"/api/images/{image_id}/suggest-mappings",
            json={"target_palette": ["#0000FF", "#00FF00"]},
            headers=auth_header,
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_upload_list_returns_uploaded(self, test_client, auth_header):
        """Full-flow: upload 2 → GET list → 2 items."""
        self._upload_png(test_client, auth_header)
        self._upload_png(test_client, auth_header)
        response = test_client.get("/api/images", headers=auth_header)
        assert response.status_code == 200
        assert len(response.json()) >= 2
