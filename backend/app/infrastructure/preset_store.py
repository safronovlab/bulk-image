"""
Persistent хранилище цветовых пресетов в JSON-файле.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.core.models import Preset

logger = logging.getLogger(__name__)


class PresetStore:
    def __init__(self, config: object) -> None:
        self._path = str(getattr(config, "PRESETS_PATH", "/app/data/presets.json"))
        self._lock = threading.Lock()
        self._cache: Optional[list[dict]] = None
        self._ensure_file()

    def _ensure_file(self) -> None:
        """Создать JSON-файл если не существует или восстановить при повреждении."""
        parent = os.path.dirname(self._path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        if not os.path.exists(self._path):
            self._write_json([])
            self._cache = []
            return

        try:
            data = self._read_json_raw()
            self._cache = data
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Corrupted presets file: {e}")
            # Backup с timestamp
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            backup_path = f"{self._path}.bak.{ts}"
            try:
                os.rename(self._path, backup_path)
            except OSError:
                pass
            # Очистка старых backup (макс 5)
            self._cleanup_backups()
            self._write_json([])
            self._cache = []

    def _cleanup_backups(self) -> None:
        parent = os.path.dirname(self._path) or "."
        base = os.path.basename(self._path)
        try:
            backups = sorted(
                [f for f in os.listdir(parent) if f.startswith(base + ".bak.")],
                reverse=True,
            )
            for old in backups[5:]:
                try:
                    os.remove(os.path.join(parent, old))
                except OSError:
                    pass
        except OSError:
            pass

    def _read_json_raw(self) -> list[dict]:
        with open(self._path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("Expected JSON array")
        return data

    def _write_json(self, data: list[dict]) -> None:
        """Atomic write с уникальным tmp."""
        tmp_path = f"{self._path}.tmp.{uuid.uuid4().hex}"
        content = json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, self._path)
        self._cache = data

    def _to_preset(self, d: dict) -> Preset:
        return Preset(
            preset_id=d["preset_id"],
            name=d["name"],
            colors=d["colors"],
            source_image_url=d.get("source_image_url"),
            created_at=d["created_at"],
        )

    def create_preset(
        self,
        name: str,
        colors: list[str],
        source_image_url: Optional[str],
    ) -> Preset:
        with self._lock:
            data = self._cache if self._cache is not None else self._read_json_raw()

            # Лимит 100
            if len(data) >= 100:
                raise ValueError("Maximum number of presets (100) reached")

            # Уникальность имени (case-insensitive)
            lower_name = name.lower()
            for p in data:
                if p["name"].lower() == lower_name:
                    raise ValueError(f"Preset with name '{name}' already exists")

            preset_id = uuid.uuid4().hex
            now = datetime.now(timezone.utc).isoformat()

            record = {
                "preset_id": preset_id,
                "name": name,
                "colors": colors,
                "source_image_url": source_image_url,
                "created_at": now,
            }
            data.append(record)
            self._write_json(data)

            return self._to_preset(record)

    def get_all_presets(self) -> list[Preset]:
        with self._lock:
            data = self._cache if self._cache is not None else self._read_json_raw()
        # Сортировка: новые первыми
        data_sorted = sorted(data, key=lambda p: p["created_at"], reverse=True)
        return [self._to_preset(d) for d in data_sorted]

    def get_preset(self, preset_id: str) -> Optional[Preset]:
        with self._lock:
            data = self._cache if self._cache is not None else self._read_json_raw()
        for d in data:
            if d["preset_id"] == preset_id:
                return self._to_preset(d)
        return None

    def update_preset(
        self,
        preset_id: str,
        name: Optional[str] = None,
        colors: Optional[list[str]] = None,
        source_image_url: Optional[str] = None,
    ) -> Optional[Preset]:
        with self._lock:
            data = self._cache if self._cache is not None else self._read_json_raw()

            target = None
            for d in data:
                if d["preset_id"] == preset_id:
                    target = d
                    break

            if target is None:
                return None

            # Уникальность нового имени
            if name is not None and name.lower() != target["name"].lower():
                for d in data:
                    if d["preset_id"] != preset_id and d["name"].lower() == name.lower():
                        raise ValueError(f"Preset with name '{name}' already exists")
                target["name"] = name

            if colors is not None:
                target["colors"] = colors

            if source_image_url is not None:
                target["source_image_url"] = source_image_url

            self._write_json(data)
            return self._to_preset(target)

    def delete_preset(self, preset_id: str) -> bool:
        with self._lock:
            data = self._cache if self._cache is not None else self._read_json_raw()
            original_len = len(data)
            data = [d for d in data if d["preset_id"] != preset_id]

            if len(data) == original_len:
                return False

            self._write_json(data)
            return True
