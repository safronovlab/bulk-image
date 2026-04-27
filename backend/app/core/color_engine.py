"""
Пиксельная замена цветов в изображении с поддержкой tolerance и антиалиасинг-блендинга.
"""

from __future__ import annotations

from typing import Sequence

import cv2
import numpy as np

from app.core.models import ColorMapping

MAX_DELTA_E: float = 50.0


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Конвертация HEX → (R, G, B)."""
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb_to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """Конвертация одного RGB-цвета → LAB (стандартный CIE LAB).

    Uses float32 conversion for full precision.
    """
    pixel = np.array([[[rgb[2] / 255.0, rgb[1] / 255.0, rgb[0] / 255.0]]], dtype=np.float32)
    lab_pixel = cv2.cvtColor(pixel, cv2.COLOR_BGR2LAB)
    l, a, b = lab_pixel[0, 0]
    return (float(l), float(a), float(b))


def replace_colors(
    image_rgba: np.ndarray,
    color_mappings: Sequence[ColorMapping],
    tolerance: int,
) -> np.ndarray:
    """
    Замена цветов в RGBA-изображении.

    tolerance: 0–100, maps to Delta-E threshold.
    tolerance=0 → exact match only
    tolerance=100 → very wide capture (Delta-E ≤ 100)
    """
    result = image_rgba.copy()

    if not color_mappings:
        return result

    rgb = result[:, :, :3]
    alpha = image_rgba[:, :, 3].copy()

    # Конвертировать RGB → BGR → LAB (float32, стандартный CIE LAB)
    bgr_float = rgb[:, :, ::-1].astype(np.float32) / 255.0
    lab_float = cv2.cvtColor(bgr_float, cv2.COLOR_BGR2LAB)

    # tolerance maps directly to Delta-E threshold
    # tolerance=0 → exact match, tolerance=50 → delta_e ≤ 50, tolerance=100 → delta_e ≤ 100
    tolerance_threshold = float(tolerance)

    for mapping in color_mappings:
        from_rgb = hex_to_rgb(mapping.from_hex)
        from_lab = rgb_to_lab(from_rgb)
        from_lab_arr = np.array(from_lab, dtype=np.float32)

        diff = lab_float - from_lab_arr
        delta_e = np.sqrt(np.sum(diff * diff, axis=2))

        mask = delta_e <= tolerance_threshold

        if not np.any(mask):
            del diff, delta_e, mask
            continue

        to_rgb = hex_to_rgb(mapping.to_hex)
        to_rgb_arr = np.array(to_rgb, dtype=np.float32)

        if tolerance == 0:
            result[mask, 0] = to_rgb[0]
            result[mask, 1] = to_rgb[1]
            result[mask, 2] = to_rgb[2]
        else:
            blend_factor = np.zeros_like(delta_e, dtype=np.float32)
            blend_factor[mask] = 1.0 - (delta_e[mask] / tolerance_threshold)

            blend_3d = blend_factor[:, :, np.newaxis]

            original_rgb = result[:, :, :3].astype(np.float32)
            new_rgb = original_rgb * (1.0 - blend_3d) + to_rgb_arr * blend_3d

            mask_3d = np.stack([mask, mask, mask], axis=2)
            clipped = np.clip(new_rgb, 0, 255).astype(np.uint8)
            result[:, :, :3] = np.where(mask_3d, clipped, result[:, :, :3])

            del blend_factor, blend_3d, new_rgb, mask_3d, clipped

        del diff, delta_e, mask

    result[:, :, 3] = alpha

    return result
