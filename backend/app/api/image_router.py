"""
HTTP-обработка всех операций с изображениями.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.core.models import (
    BatchAnalyzeRequest,
    PickColorRequest,
    PreviewReplaceRequest,
    SuggestMappingsRequest,
)
from app.dependencies import (
    get_current_session,
    get_image_service,
    rate_limit_dominant_colors,
    rate_limit_pick_color,
    rate_limit_preview,
    rate_limit_suggest,
    rate_limit_upload,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/images", tags=["images"])


def _get_session(request: Request) -> str:
    """Auth dependency — runs before body parsing."""
    return get_current_session(request)


@router.post("/upload")
async def upload_images(
    request: Request,
    session_id: str = Depends(_get_session),
    files: list[UploadFile] = File(...),
):
    try:
        rate_limit_upload(session_id)
    except HTTPException:
        raise

    image_service = get_image_service()

    # Обработать файлы по одному
    file_tuples: list[tuple[str, bytes]] = []
    for f in files:
        content = await f.read()
        file_tuples.append((f.filename or "unnamed", content))

    try:
        metas = image_service.upload_images(session_id, file_tuples)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return [m.model_dump() for m in metas]


@router.get("")
def list_images(request: Request, session_id: str = Depends(_get_session)):
    image_service = get_image_service()
    metas = image_service.get_images(session_id)
    return [m.model_dump() for m in metas]


@router.get("/{image_id}")
def get_image(image_id: str, request: Request, session_id: str = Depends(_get_session)):
    image_service = get_image_service()
    meta = image_service.get_image(image_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Image not found")
    # Ownership check
    if not image_service._verify_ownership(session_id, image_id):
        raise HTTPException(status_code=404, detail="Image not found")
    return meta.model_dump()


@router.get("/{image_id}/preview")
def get_preview(image_id: str, request: Request, session_id: str = Depends(_get_session)):
    image_service = get_image_service()
    if not image_service._verify_ownership(session_id, image_id):
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        data = image_service.get_image_preview(session_id, image_id)
    except (FileNotFoundError, PermissionError):
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(content=data, media_type="image/png")


@router.get("/{image_id}/original")
def get_original(image_id: str, request: Request, session_id: str = Depends(_get_session)):
    image_service = get_image_service()
    if not image_service._verify_ownership(session_id, image_id):
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        data = image_service.get_image_original(session_id, image_id)
    except (FileNotFoundError, PermissionError):
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(content=data, media_type="image/png")


@router.delete("/{image_id}")
def delete_image(image_id: str, request: Request, session_id: str = Depends(_get_session)):
    image_service = get_image_service()
    if not image_service._verify_ownership(session_id, image_id):
        raise HTTPException(status_code=404, detail="Image not found")
    result = image_service.delete_image(session_id, image_id)
    if not result:
        raise HTTPException(status_code=404, detail="Image not found")
    return {"detail": "Image deleted"}


@router.post("/{image_id}/pick-color")
def pick_color(image_id: str, body: PickColorRequest, request: Request, session_id: str = Depends(_get_session)):
    rate_limit_pick_color(session_id)
    image_service = get_image_service()
    if not image_service._verify_ownership(session_id, image_id):
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        result = image_service.pick_color(session_id, image_id, body.x, body.y)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (FileNotFoundError, PermissionError):
        raise HTTPException(status_code=404, detail="Image not found")
    return result.model_dump()


@router.get("/{image_id}/dominant-colors")
async def dominant_colors(
    image_id: str, request: Request, count: int = 5, session_id: str = Depends(_get_session),
):
    rate_limit_dominant_colors(session_id)
    image_service = get_image_service()
    if not image_service._verify_ownership(session_id, image_id):
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        result = await asyncio.to_thread(
            image_service.get_dominant_colors, session_id, image_id, count
        )
    except (ValueError, FileNotFoundError, PermissionError):
        raise HTTPException(status_code=404, detail="Image not found")
    return [dc.model_dump() for dc in result]


@router.post("/batch-analyze")
async def batch_analyze(body: BatchAnalyzeRequest, request: Request, session_id: str = Depends(_get_session)):
    image_service = get_image_service()
    try:
        result = await asyncio.to_thread(
            image_service.batch_analyze, session_id, body.image_ids, body.count
        )
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Image not found")

    formatted = {}
    for iid, colors in result.items():
        formatted[iid] = {"dominant_colors": [dc.model_dump() for dc in colors]}
    return {"results": formatted}


@router.post("/{image_id}/preview-replace")
async def preview_replace(
    image_id: str, body: PreviewReplaceRequest, request: Request, session_id: str = Depends(_get_session),
):
    rate_limit_preview(session_id)
    image_service = get_image_service()
    if not image_service._verify_ownership(session_id, image_id):
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        png_bytes = await asyncio.to_thread(
            image_service.preview_replace,
            session_id,
            image_id,
            body.color_mappings,
            body.tolerance,
        )
    except (ValueError, FileNotFoundError, PermissionError):
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(content=png_bytes, media_type="image/png")


@router.post("/{image_id}/suggest-mappings")
async def suggest_mappings(
    image_id: str, body: SuggestMappingsRequest, request: Request, session_id: str = Depends(_get_session),
):
    rate_limit_suggest(session_id)
    image_service = get_image_service()
    if not image_service._verify_ownership(session_id, image_id):
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        result = await asyncio.to_thread(
            image_service.suggest_mappings,
            session_id,
            image_id,
            list(body.target_palette),
        )
    except (ValueError, FileNotFoundError, PermissionError):
        raise HTTPException(status_code=404, detail="Image not found")
    return [ms.model_dump() for ms in result]
