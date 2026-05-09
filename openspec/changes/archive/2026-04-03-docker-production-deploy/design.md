## Context

The backend Dockerfile has a proper production stage with tesseract-ocr, non-root user, and health checks. However `docker-compose.yaml` pairs this production backend with a dev-mode frontend (Vite on port 5173), the nginx config has no API reverse proxy, and there is no strategy for mounting Gmail credentials into containers. The system works locally but cannot be deployed to a remote server.

## Goals / Non-Goals

**Goals:**
- Production-ready Docker Compose that works with a single `docker compose -f docker-compose.yaml up`
- Dev mode preserved via `docker-compose.override.yml` (auto-merged by Docker Compose)
- OCR available in all Docker environments (dev and production)
- Clear deployment documentation

**Non-Goals:**
- Kubernetes / cloud-specific orchestration
- TLS termination (handled by external reverse proxy)
- PostgreSQL migration (SQLite WAL is sufficient for current scale)
- CTBC parser improvements (separate future changes)

## Decisions

### D1: Base + Override split

`docker-compose.yaml` becomes the production configuration. A new `docker-compose.override.yml` provides dev overrides.

- `docker compose up` auto-merges the override file (dev mode, unchanged developer experience)
- `docker compose -f docker-compose.yaml up` uses only the base (production mode)

**Alternative considered**: Docker Compose profiles (`--profile dev`). Rejected because the override pattern is the Docker Compose convention and requires zero extra flags for dev mode.

### D2: nginx `/api` reverse proxy

Add a `location /api/` block to `frontend/nginx.conf` that proxies to `http://backend:8000`. Uses Docker Compose internal DNS (service name `backend`).

This means the frontend and backend share the same origin in production, eliminating CORS issues for same-domain deployments.

### D3: Credential bind mounts

Gmail OAuth credentials are bind-mounted from the host `./credentials/` directory:
- `credentials.json` -- read-only (OAuth client config)
- `token.json` -- writable (Gmail API refreshes the token)

The `credentials/` directory is gitignored. The existing `Settings` defaults (`/data/credentials.json`, `/data/token.json`) align with the mount paths.

### D4: Tesseract in dev stage

Add `tesseract-ocr` and `tesseract-ocr-chi-tra` to the Dockerfile `dev` stage. The ~80MB size increase is acceptable for dev containers. This ensures OCR works consistently in all Docker environments.

### D5: OCR startup logging

Add an explicit tesseract check in `docker-entrypoint.sh` that logs availability before starting the application. Operators can verify OCR is functional from container logs without running the pipeline.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Override pattern changes nothing for existing devs | `docker compose up` behavior is identical; override restores current dev configuration exactly |
| nginx returns 502 if backend not ready | Acceptable; backend has health check and `depends_on` with `service_healthy` on redis |
| Dev image grows ~80MB with tesseract | Acceptable trade-off for consistent OCR |
| SQLite in production with named volume | WAL mode handles concurrent reads; single-writer is fine for this workload; backup via `sqlite3 .backup` |
| Credential files must exist on host | Documented in deployment guide; entrypoint validates env vars |
