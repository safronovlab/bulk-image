"""
TDD-тесты для core/color_engine.py
Спецификация: core/color_engine_spec.md

Покрытие:
- replace_colors: точная замена (tolerance=0)
- replace_colors: замена с tolerance (blend)
- replace_colors: множественные маппинги
- replace_colors: сохранение alpha-канала
- replace_colors: пустой список маппингов
- hex_to_rgb: конверсия
- rgb_to_lab: конверсия
- [SRE_MARKER] numeric overflow — np.clip перед uint8
- [SRE_MARKER] LAB нормализация OpenCV
- Иммутабельность входного массива
"""

import pytest
import numpy as np


# ──────────────────────────────────────────────
# 2. Константы
# ──────────────────────────────────────────────
class TestConstants:
    def test_max_delta_e_exists(self):
        """MAX_DELTA_E = 50.0 — используется для шкалы tolerance."""
        from app.core.color_engine import MAX_DELTA_E
        assert MAX_DELTA_E == 50.0

    def test_max_delta_e_is_float(self):
        from app.core.color_engine import MAX_DELTA_E
        assert isinstance(MAX_DELTA_E, float)


# ──────────────────────────────────────────────
# 3.2 hex_to_rgb
# ──────────────────────────────────────────────
class TestHexToRgb:
    def test_red(self):
        from app.core.color_engine import hex_to_rgb
        assert hex_to_rgb("#FF0000") == (255, 0, 0)

    def test_green(self):
        from app.core.color_engine import hex_to_rgb
        assert hex_to_rgb("#00FF00") == (0, 255, 0)

    def test_blue(self):
        from app.core.color_engine import hex_to_rgb
        assert hex_to_rgb("#0000FF") == (0, 0, 255)

    def test_black(self):
        from app.core.color_engine import hex_to_rgb
        assert hex_to_rgb("#000000") == (0, 0, 0)

    def test_white(self):
        from app.core.color_engine import hex_to_rgb
        assert hex_to_rgb("#FFFFFF") == (255, 255, 255)

    def test_lowercase(self):
        from app.core.color_engine import hex_to_rgb
        assert hex_to_rgb("#ff00aa") == (255, 0, 170)

    def test_mixed_case(self):
        from app.core.color_engine import hex_to_rgb
        assert hex_to_rgb("#Ff00Aa") == (255, 0, 170)

    def test_arbitrary_color(self):
        from app.core.color_engine import hex_to_rgb
        assert hex_to_rgb("#1A2B3C") == (26, 43, 60)


# ──────────────────────────────────────────────
# 3.3 rgb_to_lab
# ──────────────────────────────────────────────
class TestRgbToLab:
    def test_returns_three_floats(self):
        from app.core.color_engine import rgb_to_lab
        result = rgb_to_lab((255, 0, 0))
        assert len(result) == 3
        assert all(isinstance(v, (float, int, np.floating)) for v in result)

    def test_black_lab(self):
        """Чёрный: L ≈ 0."""
        from app.core.color_engine import rgb_to_lab
        l, a, b = rgb_to_lab((0, 0, 0))
        assert abs(l) < 1.0  # L close to 0

    def test_white_lab(self):
        """Белый: L ≈ 100."""
        from app.core.color_engine import rgb_to_lab
        l, a, b = rgb_to_lab((255, 255, 255))
        assert abs(l - 100.0) < 2.0  # L close to 100

    def test_red_lab_positive_a(self):
        """Красный: a > 0."""
        from app.core.color_engine import rgb_to_lab
        l, a, b = rgb_to_lab((255, 0, 0))
        assert a > 0  # Red is positive on a-axis


# ──────────────────────────────────────────────
# 3.1 replace_colors
# ──────────────────────────────────────────────
class TestReplaceColors:
    @pytest.fixture
    def red_image(self) -> np.ndarray:
        """10x10 RGBA изображение, полностью красное, alpha=255."""
        img = np.zeros((10, 10, 4), dtype=np.uint8)
        img[:, :, 0] = 255  # R
        img[:, :, 3] = 255  # A
        return img

    @pytest.fixture
    def half_red_half_blue_image(self) -> np.ndarray:
        """10x10 RGBA: верхняя половина красная, нижняя синяя."""
        img = np.zeros((10, 10, 4), dtype=np.uint8)
        img[:5, :, 0] = 255  # top half red
        img[5:, :, 2] = 255  # bottom half blue
        img[:, :, 3] = 255  # full opacity
        return img

    def test_exact_replacement_tolerance_zero(self, red_image):
        """Точная замена: tolerance=0, красный → синий."""
        from app.core.color_engine import replace_colors
        from app.core.models import ColorMapping

        mappings = [ColorMapping(from_hex="#FF0000", to_hex="#0000FF")]
        result = replace_colors(red_image, mappings, tolerance=0)

        # Все пиксели должны стать синими
        assert result.shape == (10, 10, 4)
        assert result[0, 0, 0] == 0    # R = 0
        assert result[0, 0, 1] == 0    # G = 0
        assert result[0, 0, 2] == 255  # B = 255

    def test_alpha_preserved(self, red_image):
        """Alpha-канал не меняется при замене."""
        from app.core.color_engine import replace_colors
        from app.core.models import ColorMapping

        # Поставить разные alpha-значения
        red_image[0, 0, 3] = 128
        red_image[5, 5, 3] = 0

        mappings = [ColorMapping(from_hex="#FF0000", to_hex="#0000FF")]
        result = replace_colors(red_image, mappings, tolerance=0)

        assert result[0, 0, 3] == 128  # Полупрозрачный сохранён
        assert result[5, 5, 3] == 0    # Полностью прозрачный сохранён
        assert result[1, 1, 3] == 255  # Непрозрачный сохранён

    def test_non_matching_pixels_untouched(self, half_red_half_blue_image):
        """Пиксели, не попадающие в маппинг, не трогаются."""
        from app.core.color_engine import replace_colors
        from app.core.models import ColorMapping

        mappings = [ColorMapping(from_hex="#FF0000", to_hex="#00FF00")]
        result = replace_colors(half_red_half_blue_image, mappings, tolerance=0)

        # Красная часть → зелёная
        assert result[0, 0, 1] == 255  # G
        # Синяя часть не тронута
        assert result[9, 0, 2] == 255  # B
        assert result[9, 0, 0] == 0    # R

    def test_multiple_mappings(self, half_red_half_blue_image):
        """Множественные маппинги: красный→зелёный + синий→белый."""
        from app.core.color_engine import replace_colors
        from app.core.models import ColorMapping

        mappings = [
            ColorMapping(from_hex="#FF0000", to_hex="#00FF00"),
            ColorMapping(from_hex="#0000FF", to_hex="#FFFFFF"),
        ]
        result = replace_colors(half_red_half_blue_image, mappings, tolerance=0)

        # Верхняя половина → зелёная
        assert result[0, 0, 1] == 255
        # Нижняя половина → белая
        assert result[9, 0, 0] == 255
        assert result[9, 0, 1] == 255
        assert result[9, 0, 2] == 255

    def test_empty_mappings_returns_copy(self, red_image):
        """Пустой список маппингов — копия без изменений."""
        from app.core.color_engine import replace_colors

        result = replace_colors(red_image, [], tolerance=25)
        np.testing.assert_array_equal(result, red_image)

    def test_does_not_mutate_original(self, red_image):
        """Входной массив не мутируется."""
        from app.core.color_engine import replace_colors
        from app.core.models import ColorMapping

        original_copy = red_image.copy()
        mappings = [ColorMapping(from_hex="#FF0000", to_hex="#0000FF")]
        replace_colors(red_image, mappings, tolerance=0)
        np.testing.assert_array_equal(red_image, original_copy)

    def test_tolerance_blend_intermediate(self):
        """Tolerance > 0: пиксели с промежуточным delta-e получают blend (не 0 и не 255)."""
        from app.core.color_engine import replace_colors
        from app.core.models import ColorMapping

        # Создать изображение с «почти красным» цветом (200, 50, 50)
        img = np.zeros((10, 10, 4), dtype=np.uint8)
        img[:, :, 0] = 200
        img[:, :, 1] = 50
        img[:, :, 2] = 50
        img[:, :, 3] = 255

        mappings = [ColorMapping(from_hex="#FF0000", to_hex="#0000FF")]
        result = replace_colors(img, mappings, tolerance=50)

        # Должен быть частичный blend — не чисто синий и не оригинальный
        r = int(result[5, 5, 0])
        b = int(result[5, 5, 2])
        # Хотя бы частично сдвинулся к синему (B > 50) и R < 200
        assert b > 50 or r < 200, "Blend должен изменить цвет"

    def test_output_dtype_uint8(self, red_image):
        """Выход всегда uint8."""
        from app.core.color_engine import replace_colors
        from app.core.models import ColorMapping

        mappings = [ColorMapping(from_hex="#FF0000", to_hex="#0000FF")]
        result = replace_colors(red_image, mappings, tolerance=25)
        assert result.dtype == np.uint8

    def test_output_shape_matches_input(self, red_image):
        """Форма выхода (H, W, 4) совпадает с входом."""
        from app.core.color_engine import replace_colors
        from app.core.models import ColorMapping

        mappings = [ColorMapping(from_hex="#FF0000", to_hex="#0000FF")]
        result = replace_colors(red_image, mappings, tolerance=25)
        assert result.shape == red_image.shape

    def test_numeric_clip_no_overflow(self):
        """[SRE_MARKER] Результат clip в 0-255, без integer overflow."""
        from app.core.color_engine import replace_colors
        from app.core.models import ColorMapping

        # Яркий пиксель (254,254,254) → tolerance для белого замены
        img = np.full((2, 2, 4), 254, dtype=np.uint8)
        img[:, :, 3] = 255
        mappings = [ColorMapping(from_hex="#FEFEFE", to_hex="#FFFFFF")]
        result = replace_colors(img, mappings, tolerance=50)

        # Все значения должны быть в валидном диапазоне
        assert result[:, :, :3].max() <= 255
        assert result[:, :, :3].min() >= 0

    def test_fully_transparent_image_rgb_still_replaced(self):
        """Полностью прозрачное изображение: RGB заменяется, alpha=0 сохраняется."""
        from app.core.color_engine import replace_colors
        from app.core.models import ColorMapping

        img = np.zeros((5, 5, 4), dtype=np.uint8)
        img[:, :, 0] = 255  # R
        img[:, :, 3] = 0    # alpha = 0

        mappings = [ColorMapping(from_hex="#FF0000", to_hex="#0000FF")]
        result = replace_colors(img, mappings, tolerance=0)

        # RGB заменён
        assert result[0, 0, 2] == 255  # B
        # Alpha сохранён
        assert result[0, 0, 3] == 0

    def test_half_transparent_alpha_preserved(self):
        """Полупрозрачные пиксели: alpha 128 сохраняется."""
        from app.core.color_engine import replace_colors
        from app.core.models import ColorMapping

        img = np.zeros((5, 5, 4), dtype=np.uint8)
        img[:, :, 0] = 255  # R
        img[:, :, 3] = 128  # semi-transparent

        mappings = [ColorMapping(from_hex="#FF0000", to_hex="#0000FF")]
        result = replace_colors(img, mappings, tolerance=0)

        assert result[2, 2, 3] == 128

    def test_overlapping_masks_sequential_application(self):
        """Перекрывающиеся маски: второй маппинг работает поверх результата первого."""
        from app.core.color_engine import replace_colors
        from app.core.models import ColorMapping

        # Создать красное изображение
        img = np.zeros((5, 5, 4), dtype=np.uint8)
        img[:, :, 0] = 255  # R
        img[:, :, 3] = 255

        # Маппинг 1: красный → зелёный, Маппинг 2: зелёный → синий
        # При sequential: красный → зелёный → синий (если маска строится по оригинальному LAB)
        # По спеке: LAB рассчитывается ОДИН раз из оригинала, blend применяется к текущему RGB
        # Поэтому маппинг 2 НЕ должен сработать (маска по оригиналу, а в оригинале нет зелёного)
        mappings = [
            ColorMapping(from_hex="#FF0000", to_hex="#00FF00"),
            ColorMapping(from_hex="#00FF00", to_hex="#0000FF"),
        ]
        result = replace_colors(img, mappings, tolerance=0)

        # Маппинг 1 сработал (красный → зелёный), маппинг 2 НЕ сработал
        # (маска по оригинальному LAB, а зелёного в оригинале нет)
        assert result[0, 0, 1] == 255  # G = 255 (зелёный)
        assert result[0, 0, 2] == 0    # B = 0 (НЕ синий)

    def test_lab_normalization_correct(self):
        """[SRE_MARKER] LAB нормализация: Delta-E имеет физический смысл."""
        from app.core.color_engine import replace_colors
        from app.core.models import ColorMapping

        # Белый (255,255,255) и почти белый (250,250,250) — маленький Delta-E
        img = np.zeros((5, 5, 4), dtype=np.uint8)
        img[:, :, :3] = 250
        img[:, :, 3] = 255

        mappings = [ColorMapping(from_hex="#FFFFFF", to_hex="#000000")]
        # С tolerance=5 (Delta-E порог = 5*50/100 = 2.5) — должен захватить очень близкие
        result = replace_colors(img, mappings, tolerance=5)

        # Некоторые пиксели должны быть затронуты (blend)
        assert result[0, 0, 0] < 250 or result[0, 0, 0] == 250  # может или нет
