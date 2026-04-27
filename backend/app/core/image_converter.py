"""
Конвертация входных изображений в единый формат RGBA numpy-массив + извлечение/сохранение DPI metadata.
"""

from __future__ import annotations

import io
import struct
import zlib
from typing import Optional

import numpy as np
from PIL import Image

MAX_IMAGE_PIXELS = 25_000_000


def detect_format(file_bytes: bytes) -> Optional[str]:
    """Определение формата по magic bytes."""
    if len(file_bytes) < 3:
        return None
    if file_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if file_bytes[:3] == b"\xFF\xD8\xFF":
        return "jpeg"
    return None


def load_image(file_bytes: bytes) -> tuple[np.ndarray, Optional[int], str]:
    """
    Загрузка файла → (RGBA numpy, dpi, format).
    """
    if not file_bytes:
        raise ValueError("Empty file")

    fmt = detect_format(file_bytes)
    if fmt is None:
        raise ValueError("Unsupported image format. Only PNG and JPEG are accepted.")

    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

    buffer = io.BytesIO(file_bytes)
    try:
        img = Image.open(buffer)
    except Exception as e:
        raise ValueError(f"Failed to open image: {e}") from e

    w, h = img.size
    if w * h > MAX_IMAGE_PIXELS:
        img.close()
        del buffer
        raise ValueError(
            f"Image too large: {w}x{h} = {w * h} pixels exceeds limit of {MAX_IMAGE_PIXELS}"
        )

    try:
        img.load()
    except Exception as e:
        img.close()
        del buffer
        raise ValueError(f"Corrupted image file: {e}") from e

    # Извлечь DPI
    dpi: Optional[int] = None
    dpi_info = img.info.get("dpi")
    if dpi_info is not None:
        try:
            raw_dpi = dpi_info[0]
            dpi = round(raw_dpi)
        except (TypeError, IndexError, ValueError):
            dpi = None

    # Конвертировать в RGBA
    if img.mode == "RGBA":
        pass
    elif img.mode == "RGB":
        img = img.convert("RGBA")
    elif img.mode == "P":
        img = img.convert("RGBA")
    elif img.mode == "L":
        img = img.convert("RGBA")
    else:
        img = img.convert("RGB").convert("RGBA")

    rgba_array = np.array(img, dtype=np.uint8)

    img.close()
    del buffer

    return rgba_array, dpi, fmt


def _make_phys_chunk(dpi: int) -> bytes:
    """Create a PNG pHYs chunk with exact DPI (pixels per meter)."""
    # 1 inch = 0.0254 meters, so pixels_per_meter = dpi / 0.0254
    import math; ppm = math.ceil(dpi / 0.0254)
    # pHYs: 4 bytes X ppm + 4 bytes Y ppm + 1 byte unit (1 = meter)
    data = struct.pack(">IIB", ppm, ppm, 1)
    chunk_type = b"pHYs"
    chunk = struct.pack(">I", len(data)) + chunk_type + data
    crc = struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    return chunk + crc


def save_image_png(image_rgba: np.ndarray, dpi: Optional[int] = None) -> bytes:
    """Сохранение numpy RGBA → PNG bytes с DPI."""
    img = Image.fromarray(image_rgba, mode="RGBA")
    buffer = io.BytesIO()

    save_kwargs: dict = {"format": "PNG", "compress_level": 3}
    # Don't pass dpi to Pillow — we'll inject pHYs chunk manually for exact value
    img.save(buffer, **save_kwargs)
    png_bytes = buffer.getvalue()

    del img
    del buffer

    if dpi is not None:
        # Inject pHYs chunk right after IHDR (first chunk after signature)
        # PNG structure: 8-byte signature + chunks
        # IHDR is always first chunk: 4 bytes length + 4 bytes type + data + 4 bytes CRC
        sig = png_bytes[:8]
        # Read IHDR chunk length
        ihdr_len = struct.unpack(">I", png_bytes[8:12])[0]
        # IHDR chunk: 4 (length) + 4 (type) + ihdr_len (data) + 4 (crc)
        ihdr_end = 8 + 4 + 4 + ihdr_len + 4
        phys_chunk = _make_phys_chunk(dpi)
        png_bytes = sig + png_bytes[8:ihdr_end] + phys_chunk + png_bytes[ihdr_end:]

    return png_bytes


def create_preview(
    image_rgba: np.ndarray, max_size: int = 800
) -> np.ndarray:
    """Создание уменьшенной копии для превью."""
    h, w = image_rgba.shape[:2]

    if max(h, w) <= max_size:
        return image_rgba.copy()

    scale = max_size / max(h, w)
    new_w = int(w * scale)
    new_h = int(h * scale)

    img_pil = Image.fromarray(image_rgba, mode="RGBA")
    resized = img_pil.resize((new_w, new_h), Image.LANCZOS)
    result = np.array(resized, dtype=np.uint8)

    del img_pil
    del resized

    return result
