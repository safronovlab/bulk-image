"""
CRUD-операции с цветовыми пресетами (тонкая обёртка над preset_store).
"""

from __future__ import annotations

from typing import Optional

from app.core.models import Preset, PresetCreate


class PresetService:
    def __init__(self, preset_store: object) -> None:
        self._preset_store = preset_store

    def create_preset(self, request: PresetCreate) -> Preset:
        return self._preset_store.create_preset(
            name=request.name,
            colors=list(request.colors),
            source_image_url=request.source_image_url,
        )

    def get_all_presets(self) -> list[Preset]:
        return self._preset_store.get_all_presets()

    def get_preset(self, preset_id: str) -> Optional[Preset]:
        return self._preset_store.get_preset(preset_id)

    def update_preset(
        self,
        preset_id: str,
        name: Optional[str] = None,
        colors: Optional[list[str]] = None,
        source_image_url: Optional[str] = None,
    ) -> Optional[Preset]:
        return self._preset_store.update_preset(
            preset_id=preset_id,
            name=name,
            colors=colors,
            source_image_url=source_image_url,
        )

    def delete_preset(self, preset_id: str) -> bool:
        return self._preset_store.delete_preset(preset_id)
