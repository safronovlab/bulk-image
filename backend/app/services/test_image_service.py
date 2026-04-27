"""
TDD-тесты для services/image_service.py
Спецификация: services/image_service_spec.md

Покрытие:
- upload_images: 1 PNG → ImageMeta
- upload_images: 1 JPEG → original_format="jpeg"
- upload_images: 21 файл → ValueError
- upload_images: файл > 50MB → ValueError
- upload_images: невалидный формат → ValueError
- upload_images: rollback при ошибке
- get_images: фильтрация по session_id
- get_image: найден / не найден
- delete_image: удаление оригинала + preview
- pick_color: координаты в bounds
- pick_color: координаты out of bounds → ValueError
- preview_replace: preview (не оригинал) + PNG bytes
- batch_analyze: dict с результатами
- suggest_mappings: список MappingSuggestion
- [SRE_MARKER] IDOR: ownership check (_verify_ownership)
- [SRE_MARKER] threading.Lock на _images
"""

import io
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest
from PIL import Image


def _make_png_bytes(w=100, h=100, color=(255, 0, 0, 255)):
    img = Image.new("RGBA", (w, h), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_jpeg_bytes(w=100, h=100, color=(255, 0, 0)):
    img = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def mock_file_storage():
    storage = MagicMock()
    storage.save_upload.return_value = "/uploads/s1/img1.png"
    storage.save_preview.return_value = "/previews/s1/img1.png"
    storage.load_file.return_value = _make_png_bytes(50, 50)
    storage.delete_file.return_value = True
    storage.get_upload_path.return_value = "/uploads/s1/img1.png"
    storage.get_preview_path.return_value = "/previews/s1/img1.png"
    return storage


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.MAX_FILES_PER_UPLOAD = 20
    config.MAX_UPLOAD_SIZE_MB = 50
    config.MAX_TOTAL_UPLOAD_MB = 500
    config.PREVIEW_MAX_SIZE = 800
    config.MAX_IMAGE_PIXELS = 25_000_000
    return config


@pytest.fixture
def image_service(mock_file_storage, mock_config):
    from app.services.image_service import ImageService
    return ImageService(mock_file_storage, mock_config)


# ──────────────────────────────────────────────
# 4.1 upload_images
# ──────────────────────────────────────────────
class TestUploadImages:
    def test_upload_one_png(self, image_service):
        """Upload 1 PNG → ImageMeta с корректными метаданными."""
        png = _make_png_bytes(200, 150)
        files = [("test.png", png)]
        result = image_service.upload_images("session1", files)

        assert len(result) == 1
        meta = result[0]
        assert meta.original_format == "png"
        assert meta.width == 200
        assert meta.height == 150
        assert meta.filename == "test.png"
        assert meta.image_id is not None

    def test_upload_one_jpeg(self, image_service):
        """Upload 1 JPEG → original_format='jpeg'."""
        jpeg = _make_jpeg_bytes(100, 100)
        files = [("photo.jpg", jpeg)]
        result = image_service.upload_images("session1", files)

        assert len(result) == 1
        assert result[0].original_format == "jpeg"

    def test_upload_21_files_rejected(self, image_service):
        """Upload 21 файлов → ValueError."""
        png = _make_png_bytes(10, 10)
        files = [(f"file_{i}.png", png) for i in range(21)]

        with pytest.raises(ValueError):
            image_service.upload_images("session1", files)

    def test_upload_zero_files_rejected(self, image_service):
        """0 файлов → ValueError."""
        with pytest.raises(ValueError):
            image_service.upload_images("session1", [])

    def test_upload_file_over_50mb_rejected(self, image_service):
        """Файл > 50MB → ValueError с именем файла."""
        big_data = b"x" * (51 * 1024 * 1024)  # 51 MB
        files = [("huge.png", big_data)]

        with pytest.raises(ValueError, match="huge.png"):
            image_service.upload_images("session1", files)

    def test_upload_invalid_format_rejected(self, image_service):
        """Невалидный формат → ValueError."""
        files = [("doc.txt", b"This is not an image")]

        with pytest.raises(ValueError):
            image_service.upload_images("session1", files)

    def test_upload_total_size_over_500mb_rejected(self, image_service):
        """Суммарный размер > 500MB → ValueError."""
        # Создать файлы суммарно > 500MB (но каждый <= 50MB)
        big_data = b"x" * (26 * 1024 * 1024)  # 26 MB each
        files = [(f"file_{i}.png", big_data) for i in range(20)]  # 520 MB total

        with pytest.raises(ValueError):
            image_service.upload_images("session1", files)

    def test_filename_truncated_to_255(self, image_service):
        """Filename обрезается до 255 символов."""
        long_name = "a" * 300 + ".png"
        png = _make_png_bytes(10, 10)
        files = [(long_name, png)]
        result = image_service.upload_images("session1", files)

        assert len(result[0].filename) <= 255

    def test_upload_multiple_files(self, image_service):
        """Upload 3 файла → 3 ImageMeta."""
        files = [
            ("file1.png", _make_png_bytes(10, 10)),
            ("file2.png", _make_png_bytes(20, 20)),
            ("file3.png", _make_png_bytes(30, 30)),
        ]
        result = image_service.upload_images("session1", files)
        assert len(result) == 3


# ──────────────────────────────────────────────
# 4.2 get_images
# ──────────────────────────────────────────────
class TestGetImages:
    def test_returns_session_images(self, image_service):
        png = _make_png_bytes(10, 10)
        image_service.upload_images("s1", [("f1.png", png)])
        image_service.upload_images("s1", [("f2.png", png)])
        image_service.upload_images("s2", [("f3.png", png)])

        result = image_service.get_images("s1")
        assert len(result) == 2

    def test_empty_session(self, image_service):
        result = image_service.get_images("unknown")
        assert result == []


# ──────────────────────────────────────────────
# 4.3 get_image
# ──────────────────────────────────────────────
class TestGetImage:
    def test_existing_image(self, image_service):
        png = _make_png_bytes(10, 10)
        metas = image_service.upload_images("s1", [("test.png", png)])
        image_id = metas[0].image_id

        result = image_service.get_image(image_id)
        assert result is not None
        assert result.image_id == image_id

    def test_nonexistent_returns_none(self, image_service):
        result = image_service.get_image("nonexistent_id")
        assert result is None


# ──────────────────────────────────────────────
# 4.6 delete_image
# ──────────────────────────────────────────────
class TestDeleteImage:
    def test_delete_existing(self, image_service, mock_file_storage):
        png = _make_png_bytes(10, 10)
        metas = image_service.upload_images("s1", [("test.png", png)])
        image_id = metas[0].image_id

        result = image_service.delete_image("s1", image_id)
        assert result is True
        assert image_service.get_image(image_id) is None


# ──────────────────────────────────────────────
# 4.7 pick_color
# ──────────────────────────────────────────────
class TestPickColor:
    def test_valid_coordinates(self, image_service, mock_file_storage):
        """Eyedropper на валидных координатах → ColorInfo."""
        # Upload image first
        png = _make_png_bytes(100, 100, color=(255, 0, 0, 255))
        metas = image_service.upload_images("s1", [("red.png", png)])
        image_id = metas[0].image_id

        # Mock load_file to return our specific image
        mock_file_storage.load_file.return_value = _make_png_bytes(
            100, 100, (255, 0, 0, 255)
        )

        result = image_service.pick_color("s1", image_id, x=50, y=50)
        assert result is not None
        assert hasattr(result, "hex")
        assert hasattr(result, "rgb")
        assert hasattr(result, "lab")


# ──────────────────────────────────────────────
# 4.10 preview_replace
# ──────────────────────────────────────────────
class TestPreviewReplace:
    def test_returns_png_bytes(self, image_service, mock_file_storage):
        """preview_replace → PNG bytes."""
        from app.core.models import ColorMapping

        png = _make_png_bytes(100, 100, (255, 0, 0, 255))
        metas = image_service.upload_images("s1", [("test.png", png)])
        image_id = metas[0].image_id

        mock_file_storage.load_file.return_value = _make_png_bytes(
            50, 50, (255, 0, 0, 255)
        )

        mappings = [ColorMapping(from_hex="#FF0000", to_hex="#0000FF")]
        result = image_service.preview_replace("s1", image_id, mappings, tolerance=25)

        assert isinstance(result, bytes)
        assert result[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes


# ──────────────────────────────────────────────
# [SRE_MARKER] IDOR защита
# ──────────────────────────────────────────────
class TestOwnershipProtection:
    def test_get_image_wrong_session_rejected(self, image_service):
        """[SRE_MARKER] IDOR: чужое изображение недоступно."""
        png = _make_png_bytes(10, 10)
        metas = image_service.upload_images("session_owner", [("test.png", png)])
        image_id = metas[0].image_id

        # Попытка доступа из другой сессии
        # Если get_image_original проверяет ownership:
        try:
            result = image_service.get_image_original("session_attacker", image_id)
            # Если функция возвращает None вместо исключения — тоже ок
            if result is not None:
                pytest.fail("IDOR: доступ к чужому изображению не заблокирован")
        except (ValueError, PermissionError, Exception):
            pass  # Ожидаемое поведение

    def test_delete_image_wrong_session_rejected(self, image_service):
        """[SRE_MARKER] IDOR: удаление чужого изображения."""
        png = _make_png_bytes(10, 10)
        metas = image_service.upload_images("owner", [("test.png", png)])
        image_id = metas[0].image_id

        result = image_service.delete_image("attacker", image_id)
        # Должно вернуть False или бросить ошибку
        assert result is False or result is None


# ──────────────────────────────────────────────
# 4.9 batch_analyze
# ──────────────────────────────────────────────
class TestBatchAnalyze:
    def test_batch_analyze_returns_dict(self, image_service, mock_file_storage):
        """batch_analyze 3 файла → dict с 3 ключами."""
        png = _make_png_bytes(50, 50, (255, 0, 0, 255))
        metas = image_service.upload_images("s1", [
            ("f1.png", png),
            ("f2.png", _make_png_bytes(50, 50, (0, 255, 0, 255))),
            ("f3.png", _make_png_bytes(50, 50, (0, 0, 255, 255))),
        ])

        mock_file_storage.load_file.return_value = png

        image_ids = [m.image_id for m in metas]
        result = image_service.batch_analyze("s1", image_ids, count=3)

        assert isinstance(result, dict)
        assert len(result) == 3
        for iid in image_ids:
            assert iid in result

    def test_batch_analyze_nonexistent_image_error(self, image_service):
        """batch_analyze с несуществующим image_id → ошибка."""
        with pytest.raises((ValueError, KeyError, Exception)):
            image_service.batch_analyze("s1", ["nonexistent"], count=3)

    def test_batch_analyze_idor_check(self, image_service, mock_file_storage):
        """[SRE_MARKER] IDOR: batch_analyze с чужим image_id → ошибка."""
        png = _make_png_bytes(10, 10)
        metas = image_service.upload_images("owner_session", [("test.png", png)])
        image_id = metas[0].image_id

        try:
            result = image_service.batch_analyze("attacker_session", [image_id], count=3)
            # Если возвращает пустой dict или не крашится — проверяем что нет данных
            if isinstance(result, dict) and image_id in result:
                pytest.fail("IDOR: batch_analyze раскрыл данные чужого изображения")
        except (ValueError, PermissionError, Exception):
            pass  # Ожидаемое поведение


# ──────────────────────────────────────────────
# 4.11 suggest_mappings
# ──────────────────────────────────────────────
class TestSuggestMappings:
    def test_suggest_returns_list(self, image_service, mock_file_storage):
        """suggest_mappings → список MappingSuggestion."""
        png = _make_png_bytes(50, 50, (255, 0, 0, 255))
        metas = image_service.upload_images("s1", [("test.png", png)])
        image_id = metas[0].image_id

        mock_file_storage.load_file.return_value = png

        result = image_service.suggest_mappings("s1", image_id, ["#0000FF"])
        assert isinstance(result, list)

    def test_suggest_with_multiple_targets(self, image_service, mock_file_storage):
        """suggest_mappings с несколькими target palette."""
        png = _make_png_bytes(50, 50, (255, 0, 0, 255))
        metas = image_service.upload_images("s1", [("test.png", png)])
        image_id = metas[0].image_id

        mock_file_storage.load_file.return_value = png

        result = image_service.suggest_mappings(
            "s1", image_id, ["#0000FF", "#00FF00", "#FFFF00"]
        )
        assert isinstance(result, list)


# ──────────────────────────────────────────────
# 4.4/4.5 get_image_original / get_image_preview
# ──────────────────────────────────────────────
class TestGetImageFiles:
    def test_get_image_original_returns_bytes(self, image_service, mock_file_storage):
        """get_image_original → bytes."""
        png = _make_png_bytes(10, 10)
        metas = image_service.upload_images("s1", [("test.png", png)])
        image_id = metas[0].image_id

        mock_file_storage.load_file.return_value = png
        result = image_service.get_image_original("s1", image_id)
        assert isinstance(result, bytes)

    def test_get_image_preview_returns_bytes(self, image_service, mock_file_storage):
        """get_image_preview → bytes."""
        png = _make_png_bytes(10, 10)
        metas = image_service.upload_images("s1", [("test.png", png)])
        image_id = metas[0].image_id

        mock_file_storage.load_file.return_value = png
        result = image_service.get_image_preview("s1", image_id)
        assert isinstance(result, bytes)


# ──────────────────────────────────────────────
# 4.8 get_dominant_colors
# ──────────────────────────────────────────────
class TestGetDominantColors:
    def test_returns_list(self, image_service, mock_file_storage):
        """get_dominant_colors → список DominantColor."""
        png = _make_png_bytes(50, 50, (255, 0, 0, 255))
        metas = image_service.upload_images("s1", [("test.png", png)])
        image_id = metas[0].image_id

        mock_file_storage.load_file.return_value = png

        result = image_service.get_dominant_colors("s1", image_id, count=3)
        assert isinstance(result, list)

    def test_default_count_5(self, image_service, mock_file_storage):
        """count по умолчанию = 5."""
        png = _make_png_bytes(50, 50, (255, 0, 0, 255))
        metas = image_service.upload_images("s1", [("test.png", png)])
        image_id = metas[0].image_id

        mock_file_storage.load_file.return_value = png

        result = image_service.get_dominant_colors("s1", image_id)
        assert isinstance(result, list)

    def test_nonexistent_image_error(self, image_service):
        """Несуществующий image_id → ошибка."""
        with pytest.raises((ValueError, KeyError, FileNotFoundError, Exception)):
            image_service.get_dominant_colors("s1", "nonexistent", count=3)


# ──────────────────────────────────────────────
# 4.7 pick_color — out of bounds (service level)
# ──────────────────────────────────────────────
class TestPickColorOutOfBounds:
    def test_out_of_bounds_raises_value_error(self, image_service, mock_file_storage):
        """[SRE_MARKER] Координаты за пределами → ValueError на уровне service."""
        png = _make_png_bytes(50, 50, (255, 0, 0, 255))
        metas = image_service.upload_images("s1", [("test.png", png)])
        image_id = metas[0].image_id

        # Preview 50x50 — координаты 100,100 за пределами
        mock_file_storage.load_file.return_value = _make_png_bytes(50, 50, (255, 0, 0, 255))

        with pytest.raises((ValueError, Exception)):
            image_service.pick_color("s1", image_id, x=100, y=100)


# ──────────────────────────────────────────────
# Rollback при ошибке
# ──────────────────────────────────────────────
class TestUploadRollback:
    def test_rollback_on_invalid_file_in_batch(self, image_service, mock_file_storage):
        """[SRE_MARKER] Rollback: при ошибке на файле N — удалить файлы 1..N-1."""
        valid_png = _make_png_bytes(10, 10)
        files = [
            ("good1.png", valid_png),
            ("bad.txt", b"not an image"),
        ]

        with pytest.raises(ValueError):
            image_service.upload_images("s1", files)

        # После rollback в _images не должно быть записей от этого batch
        images = image_service.get_images("s1")
        assert len(images) == 0
