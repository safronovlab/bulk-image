"""
HTTP-обработка CRUD-операций с цветовыми пресетами.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.models import PresetCreate, PresetUpdate
from app.dependencies import get_current_session, get_preset_service

router = APIRouter(prefix="/api/presets", tags=["presets"])


def _get_session(request: Request) -> str:
    return get_current_session(request)


@router.post("", status_code=201)
def create_preset(body: PresetCreate, request: Request, session_id: str = Depends(_get_session)):
    preset_service = get_preset_service()
    try:
        preset = preset_service.create_preset(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return preset.model_dump()


@router.get("")
def list_presets(request: Request, session_id: str = Depends(_get_session)):
    preset_service = get_preset_service()
    presets = preset_service.get_all_presets()
    return [p.model_dump() for p in presets]


@router.get("/{preset_id}")
def get_preset(preset_id: str, request: Request, session_id: str = Depends(_get_session)):
    preset_service = get_preset_service()
    preset = preset_service.get_preset(preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="Preset not found")
    return preset.model_dump()


@router.put("/{preset_id}")
def update_preset(preset_id: str, body: PresetUpdate, request: Request, session_id: str = Depends(_get_session)):
    preset_service = get_preset_service()
    try:
        preset = preset_service.update_preset(
            preset_id=preset_id,
            name=body.name,
            colors=list(body.colors) if body.colors is not None else None,
            source_image_url=body.source_image_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if preset is None:
        raise HTTPException(status_code=404, detail="Preset not found")
    return preset.model_dump()


@router.delete("/{preset_id}")
def delete_preset(preset_id: str, request: Request, session_id: str = Depends(_get_session)):
    preset_service = get_preset_service()
    result = preset_service.delete_preset(preset_id)
    if not result:
        raise HTTPException(status_code=404, detail="Preset not found")
    return {"detail": "Preset deleted"}
