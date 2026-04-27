"""
Точка входа FastAPI-приложения. Composition Root, CORS, роутеры, lifespan.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Composition Root
# ──────────────────────────────────────────────
def _create_services():
    """Create all services from config. Returns dict of instances."""
    try:
        from app.config import Settings
        # Load .env only if it exists and env vars don't already contain AUTH_USERNAME
        # (tests set env vars directly via patch.dict)
        env_file = None
        if os.path.exists(".env") and "AUTH_USERNAME" not in os.environ:
            env_file = ".env"
        config = Settings(_env_file=env_file)
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    stop_event = threading.Event()

    from app.infrastructure.file_storage import FileStorage
    from app.infrastructure.auth_provider import AuthProvider
    from app.infrastructure.task_store import TaskStore
    from app.infrastructure.preset_store import PresetStore
    from app.services.image_service import ImageService
    from app.services.job_service import JobService
    from app.services.preset_service import PresetService

    file_storage = FileStorage(config)
    auth_provider = AuthProvider(config)
    task_store = TaskStore()
    preset_store = PresetStore(config)
    image_service = ImageService(file_storage, config)
    job_service = JobService(file_storage, task_store, image_service, stop_event, config)
    preset_service = PresetService(preset_store)

    # Inject into dependencies module
    from app import dependencies
    dependencies.init_services(image_service, job_service, preset_service, auth_provider)

    return {
        "config": config,
        "stop_event": stop_event,
        "file_storage": file_storage,
        "auth_provider": auth_provider,
        "task_store": task_store,
        "preset_store": preset_store,
        "image_service": image_service,
        "job_service": job_service,
        "preset_service": preset_service,
    }


# Module-level init
_services = _create_services()


# ──────────────────────────────────────────────
# Lifespan
# ──────────────────────────────────────────────
async def _periodic_cleanup() -> None:
    config = _services["config"]
    interval = config.CLEANUP_INTERVAL_HOURS * 3600
    while True:
        try:
            await asyncio.sleep(interval)
            try:
                files_cleaned = _services["file_storage"].cleanup_expired()
                jobs_cleaned = _services["task_store"].cleanup_expired(config.FILE_TTL_HOURS)
                tokens_cleaned = _services["auth_provider"].cleanup_expired_tokens()
                logger.info(
                    f"Cleanup: files={files_cleaned} jobs={jobs_cleaned} tokens={tokens_cleaned}"
                )
            except Exception:
                logger.exception("Error during periodic cleanup")
        except asyncio.CancelledError:
            break


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _services
    _services = _create_services()

    logger.info("Starting Bulk Image Color Replacement API v2.0.0")
    cleanup_task = asyncio.create_task(_periodic_cleanup())

    def _on_done(task: asyncio.Task) -> None:
        if task.cancelled():
            logger.info("Cleanup task cancelled")
        elif task.exception():
            logger.error(f"Cleanup task failed: {task.exception()}")

    cleanup_task.add_done_callback(_on_done)

    yield

    logger.info("Shutting down...")
    _services["stop_event"].set()

    cleanup_task.cancel()
    try:
        await asyncio.wait_for(asyncio.shield(cleanup_task), timeout=5.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass

    task_store = _services["task_store"]
    with task_store._lock:
        for job in task_store._jobs.values():
            if job.status == "processing":
                job.status = "failed"
                job.error = "Server shutdown"

    logger.info("Shutdown complete")


# ──────────────────────────────────────────────
# Middleware: Request body size limit (10MB for JSON)
# ──────────────────────────────────────────────
MAX_BODY_SIZE = 10_485_760


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path == "/api/images/upload":
            return await call_next(request)

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_BODY_SIZE:
                    return Response(
                        content='{"detail":"Request body too large"}',
                        status_code=413,
                        media_type="application/json",
                    )
            except ValueError:
                pass

        return await call_next(request)


# ──────────────────────────────────────────────
# FastAPI App
# ──────────────────────────────────────────────
app = FastAPI(
    title="Bulk Image Color Replacement API",
    version="2.0.0",
    description="Tool for bulk PNG/JPEG color replacement with design variations",
    lifespan=lifespan,
)

app.add_middleware(BodySizeLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_services["config"].CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

from app.api.auth_router import router as auth_router
from app.api.image_router import router as image_router
from app.api.job_router import router as job_router
from app.api.preset_router import router as preset_router

app.include_router(auth_router)
app.include_router(image_router)
app.include_router(job_router)
app.include_router(preset_router)


@app.get("/api/health")
def health():
    return {"status": "healthy", "version": "2.0.0"}
