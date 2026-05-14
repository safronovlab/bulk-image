# Bulk Recolor

**Pixel-perfect batch recoloring for PNG and JPEG designs.**

Production tool for apparel, sneaker, and POD brands. Upload designs, define a palette, recolor up to 20 designs in one shot. Per-region click-fix when an algorithm misses an edge.

Three failure modes a typical Photoshop bucket flow leaves on the table, all fixed here:

1. **Whole-image bleed.** Connected-region flood fill (`cv2.floodFill`) replaces global hex matching.
2. **Dotted / fringe artifacts on edges.** Edge-aware blending respects anti-aliased boundary pixels.
3. **Cross-design hex drift.** LAB-space K-means clustering plus Delta-E 2000 palette mapping with a configurable threshold.

Full technical design: [docs/architecture.md](docs/architecture.md). Functional contract: [docs/scope.md](docs/scope.md).

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, OpenCV, scikit-learn, scikit-image, Pillow, NumPy, RQ, Redis, Pydantic v2 |
| Frontend | React 19, Vite 8, Tailwind CSS v4, Web Workers |
| Infra | Docker Compose, nginx static + reverse proxy, Redis broker, RQ worker process |
| Tooling | uv, pytest (~320 tests), mypy strict, ruff, bandit, pre-commit hooks |

---

## Highlights

```
~320  tests                unit + integration + acceptance
<60s  end-to-end batch     20 designs on a 2 GB VPS
<200ms click-fix latency   single connected region
3     algorithms shipped   each with regression tests on prior failures
```

---

## Quick start

Requires Docker (OrbStack or Docker Desktop).

```bash
# 1. Create .env at repo root
cat > .env <<'EOF'
AUTH_USERNAME=admin
AUTH_PASSWORD=your-strong-password
CORS_ORIGINS=["http://localhost:8080"]
EOF

# 2. Boot the full stack
docker compose up -d --build

# 3. Open the app
open http://localhost:8080
```

Tear down (and drop volumes):

```bash
docker compose down -v
```

---

## Development

### Backend

```bash
cd backend
uv sync                              # install pinned deps
uv run pytest -q                     # run tests (~320 collected)
uv run uvicorn app.main:app --reload # local API on :8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev      # Vite dev server on :5173, proxies /api → :8000
npm run build    # production bundle to dist/
npm test         # vitest
```

### Worker

```bash
cd backend
uv run python -m app.worker          # RQ worker, requires Redis on :6379
```

---

## Layout

```
.
├── backend/
│   ├── app/
│   │   ├── api/             FastAPI routers (auth, image, palette, job)
│   │   ├── core/            Pure-domain engine: cluster_detector, flood_fill,
│   │   │                    edge_aware_recolor, palette_mapper, recolor_engine,
│   │   │                    models, zip_builder
│   │   ├── services/        I/O boundary: image_service, palette_service, job_service
│   │   ├── infrastructure/  Storage (filesystem) + Redis queue + auth provider
│   │   ├── config.py        Pydantic Settings (BULK_RECOLOR_* env keys)
│   │   ├── dependencies.py  FastAPI DI wiring
│   │   ├── main.py          App + lifespan composition root
│   │   └── worker.py        RQ entry point
│   ├── tests/
│   │   ├── unit/            mirror app/ structure
│   │   ├── integration/     end-to-end + acceptance criteria
│   │   └── fixtures/        canonical PNGs + snapshots
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api.js           Single API client (mirrors API surface below)
│   │   ├── App.jsx          Tabs + auth gate
│   │   ├── components/      UploadTab, ColorStudioTab, BatchProcessTab,
│   │   │                    PalettePanel, ClickFixCanvas, JobsPanel, LoginPage
│   │   ├── lib/             colorMath (RGB ↔ LAB ↔ Delta-E)
│   │   └── workers/         preview.worker (instant client-side palette preview)
│   └── Dockerfile           multi-stage: vite build → nginx static + /api proxy
├── docs/
│   ├── architecture.md      Module + algorithm reference
│   └── scope.md             Functional + acceptance criteria
├── example/                 Sample PNG / JPEG fixtures
├── docker-compose.yml       backend + worker + redis + frontend
└── .env                     local secrets (gitignored)
```

---

## API surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/login` | Issue session token |
| POST | `/api/auth/logout` | Revoke session |
| POST | `/api/images/upload` | Upload single PNG / JPEG, returns `image_id` and clusters |
| GET | `/api/images/{id}/preview` | Bytes (`?t=<token>` query auth for `<img>` tags) |
| GET | `/api/images/{id}/clusters` | K-means cluster preview |
| POST | `/api/images/{id}/click-fix/preview` | Mask PNG for a connected region |
| POST | `/api/images/{id}/click-fix` | Commit recolor of one region |
| DELETE | `/api/images/{id}` | Remove from session |
| POST | `/api/palettes` | Create palette |
| GET | `/api/palettes/current` | Active session palette |
| POST | `/api/jobs/recolor` | Enqueue batch recolor over `image_ids` × palette |
| GET | `/api/jobs/{id}` | Status and progress |
| GET | `/api/jobs/{id}/download` | Result ZIP |
| DELETE | `/api/jobs/{id}` | Cancel and cleanup |

Full request and response shapes: [docs/architecture.md](docs/architecture.md).

---

## Production deploy

The compose file boots a minimal single-host stack. For a production VPS:

1. Provision Ubuntu 24.04, install Docker and Docker Compose.
2. `git clone` and create `.env` with a strong `AUTH_PASSWORD` and the public URL in `CORS_ORIGINS`.
3. Put the frontend container behind nginx with Let's Encrypt, or run Caddy / Traefik in front of compose.
4. Schedule daily cleanup of `bulk_color_data:/uploads/*` and `:/results/*` older than `FILE_TTL_HOURS`.
5. Configure log rotation on the Docker logging driver (already capped to 10 MB × 3 files in `docker-compose.yml`).

Memory: 2 GB RAM minimum recommended. Peak under 1.5 GB during a 20-design batch.

---

## Author

Built by Oleg Safronov. Senior Backend, AI Integration.
Portfolio: [github.com/safronovlab](https://github.com/safronovlab)

---

## License

Showcase repository. The codebase is published for portfolio review. No external license is currently issued.
