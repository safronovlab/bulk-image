"""
TDD-тесты для core/image_converter.py
Спецификация: core/image_converter_spec.md

Покрытие:
- load_image: PNG RGBA → numpy + dpi + format
- load_image: JPEG RGB → RGBA конвертация, alpha=255
- load_image: JPEG без DPI → dpi=None
- load_image: невалидный файл → ValueError
- load_image: magic bytes валидация
- [SRE_MARKER] decompression bomb защита (MAX_IMAGE_PIXELS)
- save_image_png: numpy → PNG bytes с DPI
- save_image_png: без DPI
- create_preview: уменьшение по длинной стороне
- create_preview: маленькое изображение → копия без изменения
- detect_format: magic bytes
"""

import io
import pytest
import numpy as np
from PIL import Image


# ──────────────────────────────────────────────
# Хелперы для создания тестовых изображений
# ──────────────────────────────────────────────
def make_png_bytes(
    width: int = 100,
    height: int = 100,
    mode: str = "RGBA",
    dpi: int | None = 300,
    color: tuple = (255, 0, 0, 255),
) -> bytes:
    """Создать PNG-файл в виде bytes."""
    img = Image.new(mode, (width, height), color)
    buf = io.BytesIO()
    save_kwargs = {"format": "PNG"}
    if dpi:
        save_kwargs["dpi"] = (dpi, dpi)
    img.save(buf, **save_kwargs)
    return buf.getvalue()


def make_jpeg_bytes(
    width: int = 100,
    height: int = 100,
    dpi: int | None = 300,
    color: tuple = (255, 0, 0),
) -> bytes:
    """Создать JPEG-файл в виде bytes."""
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    save_kwargs = {"format": "JPEG"}
    if dpi:
        save_kwargs["dpi"] = (dpi, dpi)
    img.save(buf, **save_kwargs)
    return buf.getvalue()


# ──────────────────────────────────────────────
# 2.4 detect_format
# ──────────────────────────────────────────────
class TestDetectFormat:
    def test_png_magic_bytes(self):
        from app.core.image_converter import detect_format

        png_bytes = make_png_bytes()
        assert detect_format(png_bytes) == "png"

    def test_jpeg_magic_bytes(self):
        from app.core.image_converter import detect_format

        jpeg_bytes = make_jpeg_bytes()
        assert detect_format(jpeg_bytes) == "jpeg"

    def test_unknown_format(self):
        from app.core.image_converter import detect_format

        assert detect_format(b"not an image at all") is None

    def test_too_short(self):
        from app.core.image_converter import detect_format

        assert detect_format(b"AB") is None

    def test_empty_bytes(self):
        from app.core.image_converter import detect_format

        assert detect_format(b"") is None

    def test_txt_file(self):
        from app.core.image_converter import detect_format

        assert detect_format(b"Hello world, this is a text file.") is None


# ──────────────────────────────────────────────
# 2.1 load_image
# ──────────────────────────────────────────────
class TestLoadImage:
    def test_png_rgba_returns_correct_shape(self):
        """PNG RGBA → numpy (H, W, 4)."""
        from app.core.image_converter import load_image

        png = make_png_bytes(width=50, height=30, mode="RGBA")
        rgba, dpi, fmt = load_image(png)

        assert rgba.shape == (30, 50, 4)
        assert rgba.dtype == np.uint8
        assert fmt == "png"

    def test_png_dpi_extracted(self):
        """PNG с DPI=300 → dpi=300."""
        from app.core.image_converter import load_image

        png = make_png_bytes(dpi=300)
        _, dpi, _ = load_image(png)
        assert dpi == 300

    def test_jpeg_rgb_converted_to_rgba(self):
        """JPEG RGB → RGBA, alpha=255."""
        from app.core.image_converter import load_image

        jpeg = make_jpeg_bytes(width=40, height=20)
        rgba, dpi, fmt = load_image(jpeg)

        assert rgba.shape == (20, 40, 4)
        assert fmt == "jpeg"
        # Alpha-канал должен быть 255 (полностью непрозрачный)
        assert np.all(rgba[:, :, 3] == 255)

    def test_jpeg_dpi_extracted(self):
        """JPEG с DPI=72 → dpi=72."""
        from app.core.image_converter import load_image

        jpeg = make_jpeg_bytes(dpi=72)
        _, dpi, _ = load_image(jpeg)
        assert dpi == 72

    def test_jpeg_without_dpi(self):
        """JPEG без DPI metadata → dpi=None."""
        from app.core.image_converter import load_image

        # Создать JPEG без DPI
        jpeg = make_jpeg_bytes(dpi=None)
        _, dpi, _ = load_image(jpeg)
        assert dpi is None

    def test_invalid_format_raises_value_error(self):
        """Невалидный файл → ValueError."""
        from app.core.image_converter import load_image

        with pytest.raises(ValueError, match="[Uu]nsupported"):
            load_image(b"This is not an image file at all")

    def test_empty_bytes_raises_value_error(self):
        from app.core.image_converter import load_image

        with pytest.raises((ValueError, Exception)):
            load_image(b"")

    def test_png_palette_mode_converted(self):
        """PNG palette mode (P) → RGBA."""
        from app.core.image_converter import load_image

        img = Image.new("P", (10, 10))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        rgba, _, fmt = load_image(png_bytes)
        assert rgba.shape[2] == 4  # RGBA
        assert fmt == "png"

    def test_grayscale_jpeg_converted(self):
        """Grayscale JPEG → RGBA."""
        from app.core.image_converter import load_image

        img = Image.new("L", (10, 10), 128)
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        jpeg_bytes = buf.getvalue()

        rgba, _, fmt = load_image(jpeg_bytes)
        assert rgba.shape[2] == 4
        assert fmt == "jpeg"

    def test_decompression_bomb_rejected(self):
        """[SRE_MARKER] MAX_IMAGE_PIXELS: слишком большое → отклонение."""
        from app.core.image_converter import load_image

        # Создать «обманчивый» PNG с огромными размерами (пробуем 6000x6000 > 25M)
        # Для безопасности: если MAX_IMAGE_PIXELS = 25_000_000,
        # то 5001x5001 = 25_010_001 > лимита
        try:
            img = Image.new("RGB", (5001, 5001), (255, 0, 0))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            png_bytes = buf.getvalue()

            with pytest.raises((ValueError, Exception)):
                load_image(png_bytes)
        except MemoryError:
            pytest.skip("Недостаточно памяти для создания тестового изображения")

    def test_corrupted_png_raises_error(self):
        """Повреждённый PNG → ошибка."""
        from app.core.image_converter import load_image

        # Взять валидный PNG и повредить середину
        png = make_png_bytes()
        corrupted = png[:20] + b"\x00\x00\x00" + png[50:]
        with pytest.raises(Exception):
            load_image(corrupted)


# ──────────────────────────────────────────────
# 2.2 save_image_png
# ──────────────────────────────────────────────
class TestSaveImagePng:
    def test_returns_valid_png_bytes(self):
        """Выходные bytes — валидный PNG."""
        from app.core.image_converter import save_image_png

        rgba = np.zeros((10, 10, 4), dtype=np.uint8)
        rgba[:, :, 3] = 255
        result = save_image_png(rgba, dpi=None)

        assert isinstance(result, bytes)
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_png_with_dpi(self):
        """Сохранение с DPI=300 → DPI в метаданных."""
        from app.core.image_converter import save_image_png

        rgba = np.zeros((10, 10, 4), dtype=np.uint8)
        rgba[:, :, 3] = 255
        result = save_image_png(rgba, dpi=300)

        # Проверить DPI через Pillow
        img = Image.open(io.BytesIO(result))
        dpi_info = img.info.get("dpi")
        assert dpi_info is not None
        assert int(dpi_info[0]) == 300

    def test_png_without_dpi(self):
        """Сохранение без DPI → валидный PNG."""
        from app.core.image_converter import save_image_png

        rgba = np.zeros((10, 10, 4), dtype=np.uint8)
        rgba[:, :, 3] = 255
        result = save_image_png(rgba, dpi=None)

        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_roundtrip_pixel_values(self):
        """Save → Load: пиксельные значения сохраняются."""
        from app.core.image_converter import save_image_png

        rgba = np.zeros((5, 5, 4), dtype=np.uint8)
        rgba[2, 3] = [128, 64, 32, 200]
        result = save_image_png(rgba, dpi=None)

        img = Image.open(io.BytesIO(result))
        arr = np.array(img)
        assert arr[2, 3, 0] == 128
        assert arr[2, 3, 1] == 64
        assert arr[2, 3, 2] == 32
        assert arr[2, 3, 3] == 200


# ──────────────────────────────────────────────
# 2.3 create_preview
# ──────────────────────────────────────────────
class TestCreatePreview:
    def test_downscale_landscape(self):
        """4000x3000 → max_size=800 → 800x600."""
        from app.core.image_converter import create_preview

        rgba = np.zeros((3000, 4000, 4), dtype=np.uint8)
        result = create_preview(rgba, max_size=800)

        assert result.shape[1] == 800  # width
        assert result.shape[0] == 600  # height
        assert result.shape[2] == 4

    def test_downscale_portrait(self):
        """3000x4000 → max_size=800 → 600x800."""
        from app.core.image_converter import create_preview

        rgba = np.zeros((4000, 3000, 4), dtype=np.uint8)
        result = create_preview(rgba, max_size=800)

        assert result.shape[0] == 800  # height
        assert result.shape[1] == 600  # width

    def test_small_image_no_resize(self):
        """400x300 ≤ max_size=800 → без изменений."""
        from app.core.image_converter import create_preview

        rgba = np.zeros((300, 400, 4), dtype=np.uint8)
        rgba[10, 20] = [100, 200, 50, 255]
        result = create_preview(rgba, max_size=800)

        assert result.shape == (300, 400, 4)

    def test_square_image(self):
        """1000x1000 → 800x800."""
        from app.core.image_converter import create_preview

        rgba = np.zeros((1000, 1000, 4), dtype=np.uint8)
        result = create_preview(rgba, max_size=800)

        assert result.shape[0] == 800
        assert result.shape[1] == 800

    def test_output_dtype_uint8(self):
        from app.core.image_converter import create_preview

        rgba = np.zeros((2000, 2000, 4), dtype=np.uint8)
        result = create_preview(rgba, max_size=800)
        assert result.dtype == np.uint8

    def test_default_max_size_800(self):
        """Значение по умолчанию max_size=800."""
        from app.core.image_converter import create_preview

        rgba = np.zeros((1600, 1600, 4), dtype=np.uint8)
        result = create_preview(rgba)
        assert max(result.shape[0], result.shape[1]) == 800

    def test_exact_max_size_no_resize(self):
        """Изображение ровно 800x800 — без resize."""
        from app.core.image_converter import create_preview

        rgba = np.zeros((800, 800, 4), dtype=np.uint8)
        result = create_preview(rgba, max_size=800)
        assert result.shape == (800, 800, 4)
