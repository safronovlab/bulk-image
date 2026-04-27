"""
HTTP-обработка задач пакетной обработки (jobs).
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app.core.models import JobCreateRequestA, JobCreateRequestB, JobTask, Variation
from app.dependencies import get_current_session, get_job_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _get_session(request: Request) -> str:
    return get_current_session(request)


@router.post("", status_code=201)
def create_job(
    request: Request,
    body: dict[str, Any],
    session_id: str = Depends(_get_session),
):
    job_service = get_job_service()

    has_tasks = "tasks" in body
    has_global = "global_mappings" in body

    if has_tasks and has_global:
        raise HTTPException(
            status_code=400,
            detail="Request cannot contain both 'tasks' and 'global_mappings'",
        )
    if not has_tasks and not has_global:
        raise HTTPException(
            status_code=400,
            detail="Request must contain either 'tasks' or 'global_mappings'",
        )

    try:
        if has_tasks:
            parsed = JobCreateRequestA(**body)
        else:
            parsed = JobCreateRequestB(**body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        job_status = job_service.create_job(session_id, parsed)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Build tasks list for run_job
    if isinstance(parsed, JobCreateRequestA):
        tasks_list = list(parsed.tasks)
    else:
        gm = parsed.global_mappings
        tasks_list = []
        for img_id in parsed.image_ids:
            variation = Variation(
                name=gm.variation_name,
                color_mappings=list(gm.color_mappings),
                tolerance=gm.tolerance,
            )
            tasks_list.append(JobTask(image_id=img_id, variations=[variation]))

    # Use threading.Thread instead of BackgroundTasks
    # BackgroundTasks runs synchronously in TestClient, which prevents
    # testing pending/processing states. Thread runs truly async.
    t = threading.Thread(
        target=job_service.run_job,
        args=(job_status.job_id, session_id, tasks_list),
        daemon=True,
    )
    t.start()

    return job_status.model_dump()


@router.get("")
def list_jobs(request: Request, session_id: str = Depends(_get_session)):
    job_service = get_job_service()
    jobs = job_service.get_jobs(session_id)
    return [j.model_dump() for j in jobs]


@router.get("/{job_id}")
def get_job(job_id: str, request: Request, session_id: str = Depends(_get_session)):
    job_service = get_job_service()
    # Ownership check
    job_internal = job_service._task_store.get_job(job_id)
    if job_internal is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job_internal.session_id != session_id:
        raise HTTPException(status_code=404, detail="Job not found")

    status = job_service.get_job_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return status.model_dump()


@router.get("/{job_id}/download")
def download_job(job_id: str, request: Request, session_id: str = Depends(_get_session)):
    job_service = get_job_service()

    job_internal = job_service._task_store.get_job(job_id)
    if job_internal is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job_internal.session_id != session_id:
        raise HTTPException(status_code=404, detail="Job not found")

    if job_internal.status != "completed":
        raise HTTPException(status_code=409, detail="Job is still processing")

    result_path = job_service.get_result_zip(job_id)
    if result_path is None:
        raise HTTPException(status_code=404, detail="Result not found")

    return FileResponse(
        result_path,
        media_type="application/zip",
        filename="results.zip",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


@router.delete("/{job_id}")
def delete_job(job_id: str, request: Request, session_id: str = Depends(_get_session)):
    job_service = get_job_service()

    job_internal = job_service._task_store.get_job(job_id)
    if job_internal is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job_internal.session_id != session_id:
        raise HTTPException(status_code=404, detail="Job not found")

    result = job_service.delete_job(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"detail": "Job deleted"}
