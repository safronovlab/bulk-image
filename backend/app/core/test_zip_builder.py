"""
TDD-тесты для core/zip_builder.py
Спецификация: core/zip_builder_spec.md

Покрытие:
- build_zip: один файл без вариаций
- build_zip: три файла с вариациями → папки
- build_zip: дублирующиеся имена → суффиксы
- build_zip: пустой список → валидный пустой ZIP
- build_zip: ZIP_STORED (без сжатия)
- [SRE_MARKER] Zip Slip: пути не содержат .. и не начинаются с /
- sanitize_filename: очистка спецсимволов
- sanitize_filename: кириллица/Unicode
- sanitize_filename: пустой результат → "unnamed"
- sanitize_filename: обрезка до 100 символов
"""

import io
import zipfile
import pytest


# ──────────────────────────────────────────────
# 2.2 sanitize_filename
# ──────────────────────────────────────────────
class TestSanitizeFilename:
    def test_normal_filename(self):
        from app.core.zip_builder import sanitize_filename
        assert sanitize_filename("skull_tee.png") == "skull_tee"

    def test_removes_extension(self):
        from app.core.zip_builder import sanitize_filename
        result = sanitize_filename("my_image.final.png")
        assert ".png" not in result

    def test_replaces_special_chars_with_underscore(self):
        from app.core.zip_builder import sanitize_filename
        result = sanitize_filename("hello world!@#$.png")
        # Only [a-zA-Z0-9_-] allowed
        assert all(c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in result)

    def test_cyrillic_replaced(self):
        """Кириллица → подчёркивания."""
        from app.core.zip_builder import sanitize_filename
        result = sanitize_filename("фотка_дизайн.png")
        assert all(c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in result)

    def test_multiple_underscores_collapsed(self):
        from app.core.zip_builder import sanitize_filename
        result = sanitize_filename("a___b___c.png")
        assert "__" not in result

    def test_trim_leading_trailing_underscores(self):
        from app.core.zip_builder import sanitize_filename
        result = sanitize_filename("___test___.png")
        assert not result.startswith("_")
        assert not result.endswith("_")

    def test_empty_result_becomes_unnamed(self):
        from app.core.zip_builder import sanitize_filename
        result = sanitize_filename("!!!.png")
        assert result == "unnamed"

    def test_truncate_to_100_chars(self):
        from app.core.zip_builder import sanitize_filename
        result = sanitize_filename("a" * 200 + ".png")
        assert len(result) <= 100

    def test_only_extension(self):
        from app.core.zip_builder import sanitize_filename
        result = sanitize_filename(".png")
        # After removing extension, empty → "unnamed"
        assert result == "unnamed" or len(result) > 0

    def test_dash_preserved(self):
        from app.core.zip_builder import sanitize_filename
        result = sanitize_filename("my-file-name.png")
        assert "-" in result


# ──────────────────────────────────────────────
# 2.1 build_zip
# ──────────────────────────────────────────────
class TestBuildZip:
    def _png_stub(self) -> bytes:
        """Минимальный PNG для тестов."""
        import io as _io
        from PIL import Image
        img = Image.new("RGBA", (2, 2), (255, 0, 0, 255))
        buf = _io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_single_file_no_variation(self):
        """Один файл без вариаций → {name}_recolored.png."""
        from app.core.zip_builder import build_zip

        results = [("skull_tee", None, self._png_stub())]
        zip_bytes = build_zip(results)

        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        names = zf.namelist()
        assert len(names) == 1
        assert "skull_tee_recolored.png" in names

    def test_multiple_files_no_variations(self):
        """20 файлов без вариаций."""
        from app.core.zip_builder import build_zip

        results = [(f"file_{i}", None, self._png_stub()) for i in range(3)]
        zip_bytes = build_zip(results)

        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        names = zf.namelist()
        assert len(names) == 3
        for i in range(3):
            assert f"file_{i}_recolored.png" in names

    def test_with_variations_creates_folders(self):
        """Файлы с вариациями → папки {name}/{variation}.png."""
        from app.core.zip_builder import build_zip

        results = [
            ("skull_tee", "Jordan_Blue", self._png_stub()),
            ("skull_tee", "Jordan_Red", self._png_stub()),
            ("stay_true", "Jordan_Blue", self._png_stub()),
        ]
        zip_bytes = build_zip(results)

        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        names = zf.namelist()
        assert "skull_tee/Jordan_Blue.png" in names
        assert "skull_tee/Jordan_Red.png" in names
        assert "stay_true/Jordan_Blue.png" in names

    def test_duplicate_names_suffixed(self):
        """Дублирующиеся имена получают суффикс _2."""
        from app.core.zip_builder import build_zip

        results = [
            ("same_name", None, self._png_stub()),
            ("same_name", None, self._png_stub()),
        ]
        zip_bytes = build_zip(results)

        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        names = zf.namelist()
        assert len(names) == 2
        # Должно быть два уникальных пути
        assert len(set(names)) == 2

    def test_empty_results_valid_zip(self):
        """Пустой список → валидный пустой ZIP."""
        from app.core.zip_builder import build_zip

        zip_bytes = build_zip([])
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        assert len(zf.namelist()) == 0

    def test_zip_stored_no_compression(self):
        """ZIP_STORED — без дополнительного сжатия."""
        from app.core.zip_builder import build_zip

        results = [("test", None, self._png_stub())]
        zip_bytes = build_zip(results)

        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        for info in zf.infolist():
            assert info.compress_type == zipfile.ZIP_STORED

    def test_zip_slip_no_dotdot(self):
        """[SRE_MARKER] Zip Slip: пути не содержат '..'."""
        from app.core.zip_builder import build_zip

        results = [("normal_file", None, self._png_stub())]
        zip_bytes = build_zip(results)

        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        for name in zf.namelist():
            assert ".." not in name
            assert not name.startswith("/")

    def test_zip_uses_forward_slashes(self):
        """Пути в ZIP используют /."""
        from app.core.zip_builder import build_zip

        results = [
            ("folder_test", "variation1", self._png_stub()),
        ]
        zip_bytes = build_zip(results)

        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        for name in zf.namelist():
            assert "\\" not in name  # no backslashes

    def test_output_is_valid_zip(self):
        """Результат можно открыть стандартным zipfile."""
        from app.core.zip_builder import build_zip

        results = [("test", "v1", self._png_stub())]
        zip_bytes = build_zip(results)

        # Не бросает исключений
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        assert zf.testzip() is None  # no corrupted files

    def test_png_content_preserved(self):
        """Содержимое PNG внутри ZIP совпадает с оригиналом."""
        from app.core.zip_builder import build_zip

        png = self._png_stub()
        results = [("test", None, png)]
        zip_bytes = build_zip(results)

        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        extracted = zf.read("test_recolored.png")
        assert extracted == png
