## Why

The current `docker-compose.yaml` uses a production backend (with tesseract-ocr) but a dev frontend (Vite dev server), and `nginx.conf` lacks an `/api` reverse proxy. There is no credential mounting strategy and no deployment documentation. The system cannot be deployed to a remote server as-is.

## What Changes

- Split Docker Compose into base (production, no frontend) and override (dev, with Vite frontend)
- Install tesseract-ocr in the Dockerfile dev stage for consistent OCR across all environments
- Add credential file bind mount strategy for Gmail OAuth tokens
- Log OCR availability at container startup
- Create production deployment documentation

## Capabilities

### New Capabilities

- `docker-deployment`: Production Docker Compose configuration, nginx API proxy, credential mounting, and deployment guide

### Modified Capabilities

- `local-dev-startup`: Dev workflow changes from direct `docker compose up` to override-based pattern; dev mode now includes tesseract for OCR consistency

## Impact

- `docker-compose.yaml` -- restructured as production base (backend, scheduler, bot, redis only)
- `docker-compose.override.yml` -- new file for dev overrides (adds frontend with Vite)
- `backend/Dockerfile` -- dev stage gains tesseract packages (+80MB)
- `scripts/docker-entrypoint.sh` -- gains OCR status check
- `.env.example` -- FRONTEND_ORIGINS updated for production
- `docs/deployment-guide.md` -- new file
- `docs/developer-guide.md`, `docs/user-guide.md` -- updated

## Future Directions

Two known CTBC parser improvements are out of scope for this change:

1. **`ctbc-merchant-image-filter`**: `_find_merchant_images()` filters by x-position (120-135) and width (>30), but section title images ("消費暨收費摘要表") may match. Sequential matching via `used_indices` causes the first 1-2 transactions to pair with the wrong image. Fix: add y-position/height filtering.

2. **`ctbc-ocr-preprocessing`**: Current OCR uses raw 300 DPI + `--psm 7`. Accuracy can improve via image preprocessing (enlargement, binarization, contrast enhancement) and confidence thresholds.
