"""
Создание ZIP-архива из обработанных изображений с правильной структурой папок.
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Sequence


def sanitize_filename(filename: str) -> str:
    """Очистка имени файла для безопасного использования в ZIP."""
    # Убрать расширение (всё после последней точки)
    if "." in filename:
        name = filename.rsplit(".", 1)[0]
    else:
        name = filename

    # Заменить все символы кроме [a-zA-Z0-9_-] на _
    name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)

    # Убрать множественные подчёркивания
    while "__" in name:
        name = name.replace("__", "_")

    # Trim _ с начала и конца
    name = name.strip("_")

    # Пустой → unnamed
    if not name:
        return "unnamed"

    # Обрезать до 100 символов
    return name[:100]


def build_zip(
    results: Sequence[tuple[str, str | None, bytes]],
) -> bytes:
    """
    Создание ZIP из результатов обработки.

    Args:
        results: список (original_filename, variation_name | None, png_bytes)

    Returns:
        bytes — содержимое ZIP-файла
    """
    buffer = io.BytesIO()
    used_paths: dict[str, int] = {}

    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as zf:
        for original_filename, variation_name, png_bytes in results:
            # Определить путь внутри ZIP
            if variation_name is None:
                path = f"{original_filename}_recolored.png"
            else:
                path = f"{original_filename}/{variation_name}.png"

            # Zip Slip защита
            assert not path.startswith("/"), "Path must not start with /"
            assert ".." not in path, "Path must not contain .."

            # Проверить уникальность
            if path in used_paths:
                used_paths[path] += 1
                base, ext = path.rsplit(".", 1)
                path = f"{base}_{used_paths[path]}.{ext}"
            else:
                used_paths[path] = 1

            zf.writestr(path, png_bytes)

    return buffer.getvalue()
