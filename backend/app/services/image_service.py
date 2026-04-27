"""
Оркестрация всех операций с изображениями.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Optional, Sequence

from app.core import color_engine, color_extractor, image_converter
from app.core.models import ColorInfo, ColorMapping, DominantColor, ImageMeta, MappingSuggestion


class ImageService:
    def __init__(self, file_storage: object, config: object) -> None:
        self._file_storage = file_storage
        self._config = config
        self._images: dict[str, ImageMeta] = {}
        self._session_map: dict[str, str] = {}  # image_id → session_id
        self._lock = threading.Lock()

    def _verify_ownership(self, session_id: str, image_id: str) -> bool:
        with self._lock:
            return self._session_map.get(image_id) == session_id

    def upload_images(
        self, session_id: str, files: list[tuple[str, bytes]]
    ) -> list[ImageMeta]:
        max_files = getattr(self._config, "MAX_FILES_PER_UPLOAD", 20)
        max_size_mb = getattr(self._config, "MAX_UPLOAD_SIZE_MB", 50)
        max_total_mb = getattr(self._config, "MAX_TOTAL_UPLOAD_MB", 500)

        if not files or len(files) == 0:
            raise ValueError("At least 1 file required")
        if len(files) > max_files:
            raise ValueError(f"Maximum {max_files} files per upload")

        # Суммарный размер
        total_size = sum(len(content) for _, content in files)
        if total_size > max_total_mb * 1024 * 1024:
            raise ValueError(f"Total upload size exceeds {max_total_mb}MB limit")

        saved_ids: list[str] = []
        metas: list[ImageMeta] = []

        try:
            for filename, content in files:
                # Размер одного файла
                if len(content) > max_size_mb * 1024 * 1024:
                    raise ValueError(f"File '{filename}' exceeds {max_size_mb}MB limit")

                # Обрезать filename до 255
                if len(filename) > 255:
                    filename = filename[:255]

                # Загрузить и конвертировать
                rgba, dpi, fmt = image_converter.load_image(content)
                h, w = rgba.shape[:2]

                image_id = uuid.uuid4().hex

                # Сохранить оригинал как PNG
                png_bytes = image_converter.save_image_png(rgba, dpi)
                self._file_storage.save_upload(session_id, image_id, png_bytes)

                # Preview
                preview_rgba = image_converter.create_preview(
                    rgba, max_size=getattr(self._config, "PREVIEW_MAX_SIZE", 800)
                )
                preview_bytes = image_converter.save_image_png(preview_rgba, dpi)
                self._file_storage.save_preview(session_id, image_id, preview_bytes)

                meta = ImageMeta(
                    image_id=image_id,
                    filename=filename,
                    original_format=fmt,
                    width=w,
                    height=h,
                    dpi=dpi,
                    size_bytes=len(content),
                    uploaded_at=datetime.now(timezone.utc).isoformat(),
                )

                with self._lock:
                    self._images[image_id] = meta
                    self._session_map[image_id] = session_id

                saved_ids.append(image_id)
                metas.append(meta)

                # Освободить память
                del rgba, preview_rgba, png_bytes, preview_bytes

        except Exception:
            # Rollback
            for iid in saved_ids:
                try:
                    upload_path = self._file_storage.get_upload_path(session_id, iid)
                    self._file_storage.delete_file(upload_path)
                except Exception:
                    pass
                try:
                    preview_path = self._file_storage.get_preview_path(session_id, iid)
                    self._file_storage.delete_file(preview_path)
                except Exception:
                    pass
                with self._lock:
                    self._images.pop(iid, None)
                    self._session_map.pop(iid, None)
            raise

        return metas

    def get_images(self, session_id: str) -> list[ImageMeta]:
        with self._lock:
            return [
                m for iid, m in self._images.items()
                if self._session_map.get(iid) == session_id
            ]

    def get_image(self, image_id: str) -> Optional[ImageMeta]:
        with self._lock:
            return self._images.get(image_id)

    def get_image_original(self, session_id: str, image_id: str) -> bytes:
        if not self._verify_ownership(session_id, image_id):
            raise PermissionError("Access denied")
        path = self._file_storage.get_upload_path(session_id, image_id)
        return self._file_storage.load_file(path)

    def get_image_preview(self, session_id: str, image_id: str) -> bytes:
        if not self._verify_ownership(session_id, image_id):
            raise PermissionError("Access denied")
        path = self._file_storage.get_preview_path(session_id, image_id)
        return self._file_storage.load_file(path)

    def delete_image(self, session_id: str, image_id: str) -> bool:
        if not self._verify_ownership(session_id, image_id):
            return False
        try:
            upload_path = self._file_storage.get_upload_path(session_id, image_id)
            self._file_storage.delete_file(upload_path)
        except Exception:
            pass
        try:
            preview_path = self._file_storage.get_preview_path(session_id, image_id)
            self._file_storage.delete_file(preview_path)
        except Exception:
            pass
        with self._lock:
            self._images.pop(image_id, None)
            self._session_map.pop(image_id, None)
        return True

    def pick_color(self, session_id: str, image_id: str, x: int, y: int) -> ColorInfo:
        if not self._verify_ownership(session_id, image_id):
            raise PermissionError("Access denied")
        preview_path = self._file_storage.get_preview_path(session_id, image_id)
        preview_bytes = self._file_storage.load_file(preview_path)
        rgba, _, _ = image_converter.load_image(preview_bytes)
        # Пересчитать координаты (preview vs original)
        meta = self.get_image(image_id)
        if meta is not None:
            ph, pw = rgba.shape[:2]
            orig_w, orig_h = meta.width, meta.height
            px = int(x * pw / orig_w) if orig_w > 0 else x
            py = int(y * ph / orig_h) if orig_h > 0 else y
        else:
            px, py = x, y
        return color_extractor.pick_color(rgba, px, py)

    def get_dominant_colors(
        self, session_id: str, image_id: str, count: int = 5
    ) -> list[DominantColor]:
        if not self._verify_ownership(session_id, image_id):
            raise ValueError("Access denied")
        upload_path = self._file_storage.get_upload_path(session_id, image_id)
        file_bytes = self._file_storage.load_file(upload_path)
        rgba, _, _ = image_converter.load_image(file_bytes)
        return color_extractor.extract_dominant_colors(rgba, count)

    def batch_analyze(
        self, session_id: str, image_ids: list[str], count: int = 5
    ) -> dict[str, list[DominantColor]]:
        # IDOR check for all image_ids first
        for iid in image_ids:
            if not self._verify_ownership(session_id, iid):
                raise ValueError(f"Image {iid} not found or access denied")
            if self.get_image(iid) is None:
                raise ValueError(f"Image {iid} not found")

        results: dict[str, list[DominantColor]] = {}
        for iid in image_ids:
            results[iid] = self.get_dominant_colors(session_id, iid, count)
        return results

    def preview_replace(
        self,
        session_id: str,
        image_id: str,
        color_mappings: Sequence[ColorMapping],
        tolerance: int,
    ) -> bytes:
        if not self._verify_ownership(session_id, image_id):
            raise PermissionError("Access denied")
        preview_path = self._file_storage.get_preview_path(session_id, image_id)
        preview_bytes = self._file_storage.load_file(preview_path)
        rgba, _, _ = image_converter.load_image(preview_bytes)
        result_rgba = color_engine.replace_colors(rgba, color_mappings, tolerance)
        return image_converter.save_image_png(result_rgba, dpi=None)

    def suggest_mappings(
        self, session_id: str, image_id: str, target_palette: list[str]
    ) -> list[MappingSuggestion]:
        if not self._verify_ownership(session_id, image_id):
            raise PermissionError("Access denied")
        upload_path = self._file_storage.get_upload_path(session_id, image_id)
        file_bytes = self._file_storage.load_file(upload_path)
        rgba, _, _ = image_converter.load_image(file_bytes)
        return color_extractor.suggest_mappings(rgba, target_palette)
