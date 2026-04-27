"""
Создание и выполнение задач пакетной обработки (jobs).
"""

from __future__ import annotations

import gc
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional, Sequence, Union

from app.core import color_engine, image_converter, zip_builder
from app.core.models import (
    ColorMapping,
    GlobalMappings,
    JobCreateRequestA,
    JobCreateRequestB,
    JobStatus,
    JobTask,
    Variation,
)

logger = logging.getLogger(__name__)


class JobService:
    def __init__(
        self,
        file_storage: object,
        task_store: object,
        image_service: object,
        stop_event: threading.Event,
        config: object,
    ) -> None:
        self._file_storage = file_storage
        self._task_store = task_store
        self._image_service = image_service
        self._stop_event = stop_event
        self._config = config
        self._job_timeout = getattr(config, "JOB_TIMEOUT_SECONDS", 600)

    def _to_job_status(self, job: object) -> JobStatus:
        download_url = None
        if job.status == "completed":
            download_url = f"/api/jobs/{job.job_id}/download"
        return JobStatus(
            job_id=job.job_id,
            status=job.status,
            progress=job.progress,
            total_tasks=job.total_tasks,
            total_variations=job.total_variations,
            processed_variations=job.processed_variations,
            created_at=job.created_at.isoformat(),
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
            error=job.error,
            download_url=download_url,
        )

    def create_job(
        self,
        session_id: str,
        request: Union[JobCreateRequestA, JobCreateRequestB],
    ) -> JobStatus:
        # Проверить лимит
        max_concurrent = getattr(self._config, "MAX_CONCURRENT_JOBS", 5)
        active = self._task_store.count_active_jobs(session_id)
        if active >= max_concurrent:
            raise ValueError(f"Maximum concurrent jobs limit ({max_concurrent}) reached")

        # Нормализовать задачи
        if isinstance(request, JobCreateRequestA):
            tasks = list(request.tasks)
        else:
            # Mode B → нормализация в Mode A
            gm = request.global_mappings
            tasks = []
            for img_id in request.image_ids:
                variation = Variation(
                    name=gm.variation_name,
                    color_mappings=list(gm.color_mappings),
                    tolerance=gm.tolerance,
                )
                tasks.append(JobTask(image_id=img_id, variations=[variation]))

        # Валидация image_ids
        missing = []
        for task in tasks:
            if task.image_id not in self._image_service._images:
                missing.append(task.image_id)
        if missing:
            raise ValueError(f"Image IDs not found: {', '.join(missing)}")

        # Подсчёт
        total_tasks = len(tasks)
        total_variations = sum(len(t.variations) for t in tasks)

        job_id = self._task_store.create_job(session_id, total_tasks, total_variations)

        job = self._task_store.get_job(job_id)
        return self._to_job_status(job)

    def run_job(
        self,
        job_id: str,
        session_id: str,
        tasks: Sequence[JobTask],
    ) -> None:
        # Brief yield to ensure HTTP response is delivered before processing
        time.sleep(0.05)
        start_time = time.monotonic()
        processed_count = 0
        results: list[tuple[str, str | None, bytes]] = []

        try:
            for task in tasks:
                # Check stop event
                if self._stop_event.is_set():
                    self._task_store.fail_job(job_id, "Server shutdown")
                    return

                # Check timeout
                if time.monotonic() - start_time > self._job_timeout:
                    self._task_store.fail_job(job_id, "Job timeout exceeded")
                    return

                # Load original
                image_meta = self._image_service.get_image(task.image_id)
                original_filename = "unnamed"
                dpi = None
                if image_meta:
                    original_filename = zip_builder.sanitize_filename(image_meta.filename)
                    dpi = image_meta.dpi

                # Load from snapshot path (use session_id + image_id)
                upload_path = self._file_storage.get_upload_path(session_id, task.image_id)
                file_bytes = self._file_storage.load_file(upload_path)
                rgba, file_dpi, _ = image_converter.load_image(file_bytes)
                if file_dpi is not None:
                    dpi = file_dpi
                del file_bytes

                has_multiple_variations = len(task.variations) > 1

                for variation in task.variations:
                    if self._stop_event.is_set():
                        self._task_store.fail_job(job_id, "Server shutdown")
                        return

                    if time.monotonic() - start_time > self._job_timeout:
                        self._task_store.fail_job(job_id, "Job timeout exceeded")
                        return

                    result_rgba = color_engine.replace_colors(
                        rgba, variation.color_mappings, variation.tolerance
                    )
                    png_bytes = image_converter.save_image_png(result_rgba, dpi)
                    del result_rgba

                    var_name = variation.name if has_multiple_variations else None
                    results.append((original_filename, var_name, png_bytes))

                    processed_count += 1
                    self._task_store.update_progress(job_id, processed_count)

                del rgba
                gc.collect()

            # Build ZIP
            zip_bytes = zip_builder.build_zip(results)
            del results

            # Save result
            result_path = self._file_storage.save_result(job_id, zip_bytes)
            del zip_bytes

            self._task_store.complete_job(job_id, result_path)

        except Exception as e:
            logger.exception(f"Job {job_id} failed")
            # Sanitized error message
            error_msg = f"Processing failed: {type(e).__name__}"
            self._task_store.fail_job(job_id, error_msg)

    def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        job = self._task_store.get_job(job_id)
        if job is None:
            return None
        return self._to_job_status(job)

    def get_jobs(self, session_id: str) -> list[JobStatus]:
        jobs = self._task_store.get_jobs_by_session(session_id)
        return [self._to_job_status(j) for j in jobs]

    def get_result_zip(self, job_id: str) -> Optional[str]:
        job = self._task_store.get_job(job_id)
        if job is None:
            return None
        if job.status != "completed":
            return None
        if job.result_path and os.path.exists(job.result_path):
            return job.result_path
        return None

    def delete_job(self, job_id: str) -> bool:
        job = self._task_store.get_job(job_id)
        if job is None:
            return False
        if job.result_path:
            try:
                self._file_storage.delete_job_result(job_id)
            except Exception:
                pass
        return self._task_store.delete_job(job_id)
