## Task Group 1: Docker Compose restructure

- [x] 1.1 Modify `docker-compose.yaml`: change frontend `target: dev` to `target: production`, change port from `5173:5173` to `80:80`, add credential bind mounts to backend/scheduler/bot, add `restart: unless-stopped` to frontend
- [x] 1.2 Create `docker-compose.override.yml`: override frontend to `target: dev` with port `5173:5173` and source bind mount, override backend to `target: dev` with source bind mount for hot reload
- [x] 1.3 Add `credentials/` to `.gitignore`

## Task Group 2: nginx production proxy

- [x] 2.1 Add `location /api/` proxy_pass block to `frontend/nginx.conf` with proxy headers
- [x] 2.2 Update `FRONTEND_ORIGINS` in `.env.example` to include `http://localhost` (production origin)

## Task Group 3: Backend Dockerfile + OCR

- [x] 3.1 Add `tesseract-ocr` and `tesseract-ocr-chi-tra` installation to the `dev` stage in `backend/Dockerfile`
- [x] 3.2 Add OCR availability check to `scripts/docker-entrypoint.sh` that logs tesseract status at startup

## Task Group 4: Documentation

- [x] 4.1 Create `docs/deployment-guide.md` with: prerequisites, credential setup, environment configuration, first launch, health verification, backup strategy
- [x] 4.2 Update `docs/developer-guide.md`: explain base + override pattern, dev vs production Docker mode, note dev mode now includes OCR
- [x] 4.3 Update `docs/user-guide.md`: distinguish dev mode (`docker compose up`) from production mode (`docker compose -f docker-compose.yaml up`)
