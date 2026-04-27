# Bulk Image Color Replacement Tool — Backend API

REST API for bulk PNG/JPEG color replacement with design variations. Built for sneaker-matching tee design workflows.

## Quick Start

```bash
# 1. Copy env file and set credentials
cp .env.example .env
# Edit .env: set AUTH_USERNAME and AUTH_PASSWORD

# 2. Build and run with Docker
docker build -t bulk-color-tool .
docker run -d -p 8000:8000 --env-file .env -v bulk_data:/app/data bulk-color-tool

# 3. Check health
curl http://localhost:8000/api/health
```

## API Endpoints (24 total)

### Auth
- `POST /api/auth/login` — Login, get Bearer token
- `POST /api/auth/logout` — Invalidate token

### Images
- `POST /api/images/upload` — Upload up to 20 PNG/JPEG files
- `GET /api/images` — List uploaded images
- `GET /api/images/{id}` — Image metadata
- `GET /api/images/{id}/preview` — Preview PNG (800px)
- `GET /api/images/{id}/original` — Original PNG
- `DELETE /api/images/{id}` — Delete image
- `POST /api/images/{id}/pick-color` — Eyedropper (x,y → HEX)
- `GET /api/images/{id}/dominant-colors` — K-Means dominant colors
- `POST /api/images/batch-analyze` — Batch dominant colors
- `POST /api/images/{id}/suggest-mappings` — Auto-suggest color mappings
- `POST /api/images/{id}/preview-replace` — Preview color replacement

### Jobs
- `POST /api/jobs` — Create batch processing job
- `GET /api/jobs` — List jobs
- `GET /api/jobs/{id}` — Job status + progress
- `GET /api/jobs/{id}/download` — Download result ZIP
- `DELETE /api/jobs/{id}` — Cancel/delete job

### Presets
- `POST /api/presets` — Save color preset
- `GET /api/presets` — List presets
- `GET /api/presets/{id}` — Get preset
- `PUT /api/presets/{id}` — Update preset
- `DELETE /api/presets/{id}` — Delete preset

### Health
- `GET /api/health` — Healthcheck

## Architecture

Clean Architecture with 4 layers:
- **API** — FastAPI routers (thin HTTP layer)
- **Services** — Orchestration (connects core + infrastructure)
- **Core** — Pure business logic (zero I/O dependencies)
- **Infrastructure** — File system, auth, task store, preset store

See `ARCHITECTURE_FINAL.md` for full documentation.

## Tech Stack

- Python 3.12
- FastAPI + Uvicorn
- OpenCV (headless) — LAB color space, Delta-E
- Pillow — Image I/O, DPI preservation
- NumPy — Vectorized pixel operations
- scikit-learn — K-Means clustering
- Docker — Single container deployment
