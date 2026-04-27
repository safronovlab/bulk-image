"""
In-memory хранилище статусов задач обработки (jobs).
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional


@dataclass
class JobStatusInternal:
    job_id: str
    session_id: str
    status: str
    progress: int
    total_tasks: int
    total_variations: int
    processed_variations: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result_path: Optional[str] = None


class TaskStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobStatusInternal] = {}
        self._lock = threading.Lock()

    def create_job(
        self, session_id: str, total_tasks: int, total_variations: int
    ) -> str:
        """Создать задачу, вернуть job_id."""
        with self._lock:
            # Лимит 1000 записей
            if len(self._jobs) >= 1000:
                # Удалить oldest completed/failed
                removable = [
                    (k, v)
                    for k, v in self._jobs.items()
                    if v.status in ("completed", "failed")
                ]
                if removable:
                    removable.sort(key=lambda x: x[1].created_at)
                    del self._jobs[removable[0][0]]

            job_id = uuid.uuid4().hex
            self._jobs[job_id] = JobStatusInternal(
                job_id=job_id,
                session_id=session_id,
                status="pending",
                progress=0,
                total_tasks=total_tasks,
                total_variations=total_variations,
                processed_variations=0,
                created_at=datetime.now(timezone.utc),
            )
            return job_id

    def get_job(self, job_id: str) -> Optional[JobStatusInternal]:
        with self._lock:
            return self._jobs.get(job_id)

    def get_jobs_by_session(self, session_id: str) -> list[JobStatusInternal]:
        with self._lock:
            jobs = [j for j in self._jobs.values() if j.session_id == session_id]
            jobs.sort(key=lambda j: j.created_at, reverse=True)
            return jobs

    def update_progress(self, job_id: str, processed_variations: int) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            # Защита от overflow
            clamped = min(processed_variations, job.total_variations)
            job.processed_variations = clamped
            job.status = "processing"
            if job.total_variations > 0:
                job.progress = round(clamped / job.total_variations * 100)
            else:
                job.progress = 100
            return True

    def complete_job(self, job_id: str, result_path: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job.status = "completed"
            job.progress = 100
            job.processed_variations = job.total_variations
            job.completed_at = datetime.now(timezone.utc)
            job.result_path = result_path
            return True

    def fail_job(self, job_id: str, error_message: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job.status = "failed"
            job.completed_at = datetime.now(timezone.utc)
            job.error = error_message
            return True

    def delete_job(self, job_id: str) -> bool:
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                return True
            return False

    def count_active_jobs(self, session_id: str) -> int:
        with self._lock:
            return sum(
                1
                for j in self._jobs.values()
                if j.session_id == session_id and j.status in ("pending", "processing")
            )

    def cleanup_expired(self, ttl_hours: int) -> int:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=ttl_hours)
        stale_pending_cutoff = now - timedelta(hours=1)
        stale_processing_cutoff = now - timedelta(hours=ttl_hours * 2)

        with self._lock:
            to_delete: list[str] = []
            for k, v in self._jobs.items():
                # Completed/failed older than TTL
                if v.status in ("completed", "failed"):
                    ref_time = v.completed_at or v.created_at
                    if ref_time < cutoff:
                        to_delete.append(k)
                # Stale pending > 1 hour
                elif v.status == "pending" and v.created_at < stale_pending_cutoff:
                    v.status = "failed"
                    v.error = "Stale pending job"
                    v.completed_at = now
                # Stale processing > 2×TTL
                elif v.status == "processing" and v.created_at < stale_processing_cutoff:
                    to_delete.append(k)

            for k in to_delete:
                del self._jobs[k]

        return len(to_delete)
