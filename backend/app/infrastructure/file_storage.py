"""
Адаптер к файловой системе. Сохранение, загрузка, удаление файлов, TTL-чистка.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Optional


class FileStorage:
    def __init__(self, config: object) -> None:
        self._upload_dir = str(getattr(config, "UPLOAD_DIR", "/app/data/uploads"))
        self._preview_dir = str(getattr(config, "PREVIEW_DIR", "/app/data/previews"))
        self._result_dir = str(getattr(config, "RESULT_DIR", "/app/data/results"))
        self._file_ttl_hours = int(getattr(config, "FILE_TTL_HOURS", 24))
        self._max_total_upload_mb = int(getattr(config, "MAX_TOTAL_UPLOAD_MB", 500))

        for d in (self._upload_dir, self._preview_dir, self._result_dir):
            os.makedirs(d, exist_ok=True)

    def _allowed_dirs(self) -> list[Path]:
        return [
            Path(self._upload_dir).resolve(),
            Path(self._preview_dir).resolve(),
            Path(self._result_dir).resolve(),
        ]

    def _check_path_traversal(self, file_path: str) -> None:
        resolved = Path(file_path).resolve()
        for allowed in self._allowed_dirs():
            if resolved == allowed or str(resolved).startswith(str(allowed) + os.sep):
                return
        raise PermissionError("Access denied: path outside allowed directories")

    def _check_symlink(self, file_path: str) -> None:
        if os.path.islink(file_path):
            raise PermissionError("Symlinks are not allowed")

    def _check_disk_space(self) -> None:
        try:
            usage = shutil.disk_usage(self._upload_dir)
            min_free = self._max_total_upload_mb * 2 * 1024 * 1024
            if usage.free < min_free:
                raise IOError("Insufficient disk space")
        except (OSError, AttributeError):
            pass

    def _atomic_write(self, final_path: str, data: bytes) -> None:
        self._check_disk_space()
        tmp_path = final_path + ".tmp"
        with open(tmp_path, "wb") as f:
            f.write(data)
        os.replace(tmp_path, final_path)

    def save_upload(self, session_id: str, image_id: str, png_bytes: bytes) -> str:
        session_dir = os.path.join(self._upload_dir, session_id)
        os.makedirs(session_dir, exist_ok=True)
        file_path = os.path.join(session_dir, f"{image_id}.png")
        self._atomic_write(file_path, png_bytes)
        return file_path

    def save_preview(self, session_id: str, image_id: str, png_bytes: bytes) -> str:
        session_dir = os.path.join(self._preview_dir, session_id)
        os.makedirs(session_dir, exist_ok=True)
        file_path = os.path.join(session_dir, f"{image_id}.png")
        self._atomic_write(file_path, png_bytes)
        return file_path

    def save_result(self, job_id: str, zip_bytes: bytes) -> str:
        job_dir = os.path.join(self._result_dir, job_id)
        os.makedirs(job_dir, exist_ok=True)
        file_path = os.path.join(job_dir, "results.zip")
        self._atomic_write(file_path, zip_bytes)
        return file_path

    def load_file(self, file_path: str) -> bytes:
        self._check_path_traversal(file_path)
        self._check_symlink(file_path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        with open(file_path, "rb") as f:
            return f.read()

    def delete_file(self, file_path: str) -> bool:
        # Detect path traversal attempts (contains "..")
        if ".." in file_path:
            raise PermissionError("Path traversal detected")
        if not os.path.exists(file_path):
            return False
        self._check_path_traversal(file_path)
        os.remove(file_path)
        return True








    def delete_session_files(self, session_id: str) -> int:
        count = 0
        for base_dir in (self._upload_dir, self._preview_dir):
            session_dir = os.path.join(base_dir, session_id)
            if os.path.isdir(session_dir):
                files = list(Path(session_dir).rglob("*"))
                count += len([f for f in files if f.is_file()])
                shutil.rmtree(session_dir, ignore_errors=True)
        return count

    def delete_job_result(self, job_id: str) -> bool:
        job_dir = os.path.join(self._result_dir, job_id)
        if os.path.isdir(job_dir):
            shutil.rmtree(job_dir, ignore_errors=True)
            return True
        return False

    def get_upload_path(self, session_id: str, image_id: str) -> str:
        return os.path.join(self._upload_dir, session_id, f"{image_id}.png")

    def get_preview_path(self, session_id: str, image_id: str) -> str:
        return os.path.join(self._preview_dir, session_id, f"{image_id}.png")

    def cleanup_expired(self) -> int:
        count = 0
        cutoff = time.time() - self._file_ttl_hours * 3600
        tmp_cutoff = time.time() - 3600

        for base_dir in (self._upload_dir, self._preview_dir, self._result_dir):
            if not os.path.isdir(base_dir):
                continue
            for entry in os.listdir(base_dir):
                entry_path = os.path.join(base_dir, entry)
                if not os.path.isdir(entry_path):
                    if entry.endswith(".tmp"):
                        try:
                            mtime = os.path.getmtime(entry_path)
                            if mtime < tmp_cutoff:
                                os.remove(entry_path)
                        except OSError:
                            pass
                    continue

                newest = 0.0
                try:
                    for f in Path(entry_path).rglob("*"):
                        if f.is_file():
                            if str(f).endswith(".tmp"):
                                try:
                                    mtime = os.path.getmtime(str(f))
                                    if mtime < tmp_cutoff:
                                        os.remove(str(f))
                                except OSError:
                                    pass
                                continue
                            try:
                                mtime = os.path.getmtime(str(f))
                                newest = max(newest, mtime)
                            except OSError:
                                pass
                except OSError:
                    pass

                if newest == 0.0:
                    try:
                        newest = os.path.getmtime(entry_path)
                    except OSError:
                        continue

                if newest < cutoff:
                    shutil.rmtree(entry_path, ignore_errors=True)
                    count += 1

        return count
