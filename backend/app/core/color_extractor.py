"""
Извлечение цветовой информации из изображения — eyedropper, dominant colors, suggest-mappings.
"""

from __future__ import annotations

from typing import Sequence

import cv2
import numpy as np
from sklearn.cluster import KMeans

from app.core.color_engine import MAX_DELTA_E, hex_to_rgb, rgb_to_lab
from app.core.models import ColorInfo, ColorLAB, ColorRGB, DominantColor, MappingSuggestion

# Practical max Delta-E for confidence scoring.
_CONFIDENCE_MAX_DELTA_E = 150.0


def pick_color(image_rgba: np.ndarray, x: int, y: int) -> ColorInfo:
    """Eyedropper — получить цвет пикселя по координатам."""
    h, w = image_rgba.shape[:2]
    if x < 0 or x >= w or y < 0 or y >= h:
        raise ValueError(f"Coordinates ({x}, {y}) out of bounds (W={w}, H={h})")

    pixel = image_rgba[y, x]
    r, g, b = int(pixel[0]), int(pixel[1]), int(pixel[2])
    hex_color = f"#{r:02X}{g:02X}{b:02X}"
    l, a, b_ch = rgb_to_lab((r, g, b))

    return ColorInfo(
        hex=hex_color,
        rgb=ColorRGB(r=r, g=g, b=b),
        lab=ColorLAB(l=l, a=a, b_channel=b_ch),
    )


def extract_dominant_colors(
    image_rgba: np.ndarray, count: int = 5
) -> list[DominantColor]:
    """K-Means кластеризация для определения основных цветов."""
    h, w = image_rgba.shape[:2]
    pixels = image_rgba.reshape(-1, 4)

    # Отфильтровать прозрачные пиксели (alpha >= 128)
    opaque_mask = pixels[:, 3] >= 128
    opaque_pixels = pixels[opaque_mask]

    if len(opaque_pixels) == 0:
        return []

    # Извлечь RGB
    rgb_pixels = opaque_pixels[:, :3]

    # Subsample если > 50000
    rng = np.random.default_rng(42)
    if len(rgb_pixels) > 50000:
        indices = rng.choice(len(rgb_pixels), size=50000, replace=False)
        rgb_pixels = rgb_pixels[indices]

    # Конвертировать RGB → BGR → LAB (float32 for full CIE LAB precision)
    bgr_pixels = rgb_pixels[:, ::-1].copy()
    bgr_float = bgr_pixels.reshape(1, -1, 3).astype(np.float32) / 255.0
    lab_image = cv2.cvtColor(bgr_float, cv2.COLOR_BGR2LAB)
    lab_pixels = lab_image.reshape(-1, 3)
    # lab_pixels is already standard CIE LAB: L [0..100], a/b [-127..127]

    # KMeans
    actual_count = min(count, len(lab_pixels))
    if actual_count < 1:
        return []

    kmeans = KMeans(
        n_clusters=actual_count,
        n_init=10,
        max_iter=300,
        random_state=42,
    )
    kmeans.fit(lab_pixels)

    labels = kmeans.labels_
    total = len(labels)
    results: list[DominantColor] = []

    for i in range(actual_count):
        cluster_count = int(np.sum(labels == i))
        percentage = cluster_count / total * 100.0

        # Центроид LAB → RGB (via float32 path)
        center_lab = kmeans.cluster_centers_[i]
        lab_pixel = np.array([[[center_lab[0], center_lab[1], center_lab[2]]]], dtype=np.float32)
        bgr_pixel = cv2.cvtColor(lab_pixel, cv2.COLOR_LAB2BGR)
        # Clip and convert to uint8
        bgr_uint8 = np.clip(bgr_pixel * 255.0, 0, 255).astype(np.uint8)
        b_val, g_val, r_val = int(bgr_uint8[0, 0, 0]), int(bgr_uint8[0, 0, 1]), int(bgr_uint8[0, 0, 2])

        hex_color = f"#{r_val:02X}{g_val:02X}{b_val:02X}"
        results.append(
            DominantColor(
                hex=hex_color,
                rgb=ColorRGB(r=r_val, g=g_val, b=b_val),
                percentage=round(percentage, 2),
            )
        )

    results.sort(key=lambda dc: dc.percentage, reverse=True)
    return results


def suggest_mappings(
    image_rgba: np.ndarray, target_palette: Sequence[str]
) -> list[MappingSuggestion]:
    """Автоматический подбор маппингов из dominant colors к target palette."""
    dominant = extract_dominant_colors(image_rgba, count=10)
    if not dominant:
        return []

    dominant_labs: list[tuple[float, float, float]] = []
    for dc in dominant:
        dominant_labs.append(rgb_to_lab((dc.rgb.r, dc.rgb.g, dc.rgb.b)))

    target_labs: list[tuple[float, float, float]] = []
    for hex_c in target_palette:
        rgb = hex_to_rgb(hex_c)
        target_labs.append(rgb_to_lab(rgb))

    used_dominant_indices: set[int] = set()
    suggestions: list[MappingSuggestion] = []

    for t_idx, t_lab in enumerate(target_labs):
        best_d_idx: int | None = None
        best_delta_e = float("inf")

        for d_idx, d_lab in enumerate(dominant_labs):
            if d_idx in used_dominant_indices:
                continue
            de = float(np.sqrt(
                (d_lab[0] - t_lab[0]) ** 2
                + (d_lab[1] - t_lab[1]) ** 2
                + (d_lab[2] - t_lab[2]) ** 2
            ))
            if de < best_delta_e:
                best_delta_e = de
                best_d_idx = d_idx

        if best_d_idx is None:
            continue

        confidence = max(0.0, 1.0 - (best_delta_e / _CONFIDENCE_MAX_DELTA_E))
        if confidence < 0.3:
            continue

        used_dominant_indices.add(best_d_idx)
        dc = dominant[best_d_idx]

        suggestions.append(
            MappingSuggestion(
                from_hex=dc.hex,
                to_hex=target_palette[t_idx],
                delta_e=round(best_delta_e, 2),
                confidence=round(confidence, 4),
                from_percentage=dc.percentage,
            )
        )

    suggestions.sort(key=lambda s: s.from_percentage, reverse=True)
    return suggestions
