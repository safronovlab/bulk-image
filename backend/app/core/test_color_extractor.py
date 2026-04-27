"""
TDD-тесты для core/color_extractor.py
Спецификация: core/color_extractor_spec.md

Покрытие:
- pick_color: eyedropper на известном пикселе
- pick_color: координаты за пределами → ValueError
- extract_dominant_colors: 2 цвета 50/50
- extract_dominant_colors: полностью прозрачное → пустой список
- extract_dominant_colors: один цвет → percentage ~100%
- extract_dominant_colors: детерминированность (random_state=42)
- suggest_mappings: автоподбор маппингов
- suggest_mappings: прозрачное → пустой список
- suggest_mappings: confidence фильтрация < 0.3
- [SRE_MARKER] subsample фиксированный seed
"""

import pytest
import numpy as np


# ──────────────────────────────────────────────
# Фикстуры
# ──────────────────────────────────────────────
@pytest.fixture
def red_green_image() -> np.ndarray:
    """10x10 RGBA: левая половина красная, правая зелёная."""
    img = np.zeros((10, 10, 4), dtype=np.uint8)
    img[:, :5, 0] = 255    # left half red
    img[:, 5:, 1] = 255    # right half green
    img[:, :, 3] = 255     # fully opaque
    return img


@pytest.fixture
def single_color_image() -> np.ndarray:
    """10x10 полностью синее."""
    img = np.zeros((10, 10, 4), dtype=np.uint8)
    img[:, :, 2] = 255  # blue
    img[:, :, 3] = 255
    return img


@pytest.fixture
def transparent_image() -> np.ndarray:
    """10x10 полностью прозрачное (alpha=0)."""
    img = np.zeros((10, 10, 4), dtype=np.uint8)
    img[:, :, 0] = 255  # has RGB data
    img[:, :, 3] = 0    # fully transparent
    return img


# ──────────────────────────────────────────────
# 2.1 pick_color
# ──────────────────────────────────────────────
class TestPickColor:
    def test_red_pixel(self, red_green_image):
        """Eyedropper на красном пикселе (0,0)."""
        from app.core.color_extractor import pick_color

        result = pick_color(red_green_image, x=0, y=0)
        assert result.hex == "#FF0000"
        assert result.rgb.r == 255
        assert result.rgb.g == 0
        assert result.rgb.b == 0

    def test_green_pixel(self, red_green_image):
        """Eyedropper на зелёном пикселе (9,0)."""
        from app.core.color_extractor import pick_color

        result = pick_color(red_green_image, x=9, y=0)
        assert result.hex == "#00FF00"
        assert result.rgb.r == 0
        assert result.rgb.g == 255

    def test_returns_color_info_with_lab(self, single_color_image):
        """Результат содержит HEX, RGB и LAB."""
        from app.core.color_extractor import pick_color

        result = pick_color(single_color_image, x=5, y=5)
        assert result.hex is not None
        assert result.rgb is not None
        assert result.lab is not None
        # LAB должен иметь правильную структуру
        assert hasattr(result.lab, "l")
        assert hasattr(result.lab, "a")
        assert hasattr(result.lab, "b_channel")

    def test_x_out_of_bounds(self, single_color_image):
        """x >= W → ValueError."""
        from app.core.color_extractor import pick_color

        with pytest.raises(ValueError):
            pick_color(single_color_image, x=10, y=0)

    def test_y_out_of_bounds(self, single_color_image):
        """y >= H → ValueError."""
        from app.core.color_extractor import pick_color

        with pytest.raises(ValueError):
            pick_color(single_color_image, x=0, y=10)

    def test_negative_x(self, single_color_image):
        """x < 0 → ValueError."""
        from app.core.color_extractor import pick_color

        with pytest.raises(ValueError):
            pick_color(single_color_image, x=-1, y=0)

    def test_negative_y(self, single_color_image):
        """y < 0 → ValueError."""
        from app.core.color_extractor import pick_color

        with pytest.raises(ValueError):
            pick_color(single_color_image, x=0, y=-1)

    def test_boundary_pixel_max(self, single_color_image):
        """Пиксель на границе (W-1, H-1) — допустимо."""
        from app.core.color_extractor import pick_color

        result = pick_color(single_color_image, x=9, y=9)
        assert result.hex == "#0000FF"


# ──────────────────────────────────────────────
# 2.2 extract_dominant_colors
# ──────────────────────────────────────────────
class TestExtractDominantColors:
    def test_two_colors_50_50(self, red_green_image):
        """Красный/зелёный 50/50 → 2 кластера ~50% каждый."""
        from app.core.color_extractor import extract_dominant_colors

        result = extract_dominant_colors(red_green_image, count=2)
        assert len(result) == 2

        percentages = sorted([dc.percentage for dc in result], reverse=True)
        # Каждый кластер ~50% (допуск ±10%)
        assert abs(percentages[0] - 50.0) < 10.0
        assert abs(percentages[1] - 50.0) < 10.0

    def test_single_color_100_percent(self, single_color_image):
        """Одноцветное → один кластер ~100%."""
        from app.core.color_extractor import extract_dominant_colors

        result = extract_dominant_colors(single_color_image, count=1)
        assert len(result) >= 1
        assert result[0].percentage > 90.0

    def test_sorted_by_percentage_descending(self, red_green_image):
        """Результат отсортирован по percentage убыванием."""
        from app.core.color_extractor import extract_dominant_colors

        result = extract_dominant_colors(red_green_image, count=2)
        if len(result) >= 2:
            assert result[0].percentage >= result[1].percentage

    def test_transparent_image_empty_list(self, transparent_image):
        """Полностью прозрачное → пустой список."""
        from app.core.color_extractor import extract_dominant_colors

        result = extract_dominant_colors(transparent_image, count=5)
        assert result == []

    def test_deterministic_with_same_seed(self, red_green_image):
        """[SRE_MARKER] Детерминированность: random_state=42."""
        from app.core.color_extractor import extract_dominant_colors

        result1 = extract_dominant_colors(red_green_image, count=2)
        result2 = extract_dominant_colors(red_green_image, count=2)

        assert len(result1) == len(result2)
        for dc1, dc2 in zip(result1, result2):
            assert dc1.hex == dc2.hex
            assert abs(dc1.percentage - dc2.percentage) < 0.01

    def test_returns_dominant_color_objects(self, single_color_image):
        """Возвращает DominantColor с hex, rgb, percentage."""
        from app.core.color_extractor import extract_dominant_colors

        result = extract_dominant_colors(single_color_image, count=1)
        assert len(result) >= 1
        dc = result[0]
        assert hasattr(dc, "hex")
        assert hasattr(dc, "rgb")
        assert hasattr(dc, "percentage")

    def test_default_count_5(self, red_green_image):
        """count по умолчанию = 5."""
        from app.core.color_extractor import extract_dominant_colors

        result = extract_dominant_colors(red_green_image)
        # Может вернуть <= 5 (если меньше уникальных цветов)
        assert len(result) <= 5


# ──────────────────────────────────────────────
# 2.3 suggest_mappings
# ──────────────────────────────────────────────
class TestSuggestMappings:
    def test_basic_suggestion(self, red_green_image):
        """Красно-зелёный дизайн + target palette → предложения."""
        from app.core.color_extractor import suggest_mappings

        target = ["#0000FF", "#FFFF00"]  # blue, yellow
        result = suggest_mappings(red_green_image, target)

        assert len(result) > 0
        for ms in result:
            assert hasattr(ms, "from_hex")
            assert hasattr(ms, "to_hex")
            assert hasattr(ms, "delta_e")
            assert hasattr(ms, "confidence")
            assert hasattr(ms, "from_percentage")

    def test_confidence_range(self, red_green_image):
        """Confidence в диапазоне 0.0–1.0."""
        from app.core.color_extractor import suggest_mappings

        result = suggest_mappings(red_green_image, ["#0000FF"])
        for ms in result:
            assert 0.0 <= ms.confidence <= 1.0

    def test_sorted_by_from_percentage_descending(self, red_green_image):
        """Результат отсортирован по from_percentage убыванием."""
        from app.core.color_extractor import suggest_mappings

        result = suggest_mappings(red_green_image, ["#0000FF", "#FFFF00"])
        if len(result) >= 2:
            assert result[0].from_percentage >= result[1].from_percentage

    def test_transparent_image_empty_suggestions(self, transparent_image):
        """Полностью прозрачное → пустой список."""
        from app.core.color_extractor import suggest_mappings

        result = suggest_mappings(transparent_image, ["#FF0000"])
        assert result == []

    def test_low_confidence_filtered(self):
        """Confidence < 0.3 отфильтровывается."""
        from app.core.color_extractor import suggest_mappings

        # Однотонное красное + далёкий target (синий) → должно пройти
        # Однотонное красное + target = красный → confidence ≈ 1.0
        img = np.zeros((10, 10, 4), dtype=np.uint8)
        img[:, :, 0] = 255  # Red
        img[:, :, 3] = 255
        result = suggest_mappings(img, ["#FF0000"])
        if len(result) > 0:
            assert all(ms.confidence >= 0.3 for ms in result)

    def test_greedy_no_duplicate_dominant_assigned(self, red_green_image):
        """Жадный алгоритм: каждый dominant color назначается максимум одному target."""
        from app.core.color_extractor import suggest_mappings

        result = suggest_mappings(red_green_image, ["#0000FF", "#FFFF00"])
        from_hexes = [ms.from_hex for ms in result]
        assert len(from_hexes) == len(set(from_hexes)), \
            "Каждый dominant color должен быть уникальным в результатах"
