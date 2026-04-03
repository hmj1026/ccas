# docker-deployment Specification

## Purpose
TBD - created by archiving change docker-production-deploy. Update Purpose after archive.
## Requirements
### Requirement: Production Docker Compose configuration

The system SHALL provide a `docker-compose.yaml` that serves as the production configuration, using the `production` target for both backend and frontend services.

#### Scenario: Production mode startup

- **WHEN** an operator runs `docker compose -f docker-compose.yaml up`
- **THEN** the frontend SHALL serve static files via nginx on port 80, the backend SHALL run uvicorn on port 8000, and all services SHALL start with `restart: unless-stopped`

#### Scenario: Frontend serves API requests via reverse proxy

- **WHEN** a browser requests `/api/*` from the frontend origin
- **THEN** nginx SHALL proxy the request to `http://backend:8000` with proper forwarding headers (`Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`)

#### Scenario: Frontend serves SPA routes

- **WHEN** a browser requests any non-API, non-asset path
- **THEN** nginx SHALL fall back to `index.html` for client-side routing

### Requirement: Credential file mounting

The system SHALL support mounting Gmail OAuth credentials from the host into backend containers via bind mounts.

#### Scenario: Credentials available in container

- **WHEN** `docker-compose.yaml` includes bind mounts for `./credentials/credentials.json` and `./credentials/token.json`
- **THEN** the backend container SHALL have these files accessible at `/data/credentials.json` (read-only) and `/data/token.json` (writable)

#### Scenario: Credentials directory gitignored

- **WHEN** a developer checks `.gitignore`
- **THEN** the `credentials/` directory SHALL be listed to prevent accidental commits

### Requirement: OCR available in all Docker environments

The system SHALL install `tesseract-ocr` and `tesseract-ocr-chi-tra` in both the `dev` and `production` stages of `backend/Dockerfile`.

#### Scenario: OCR works in dev Docker

- **WHEN** the backend runs from the `dev` Docker target
- **THEN** `is_ocr_available()` SHALL return `True`

#### Scenario: OCR works in production Docker

- **WHEN** the backend runs from the `production` Docker target
- **THEN** `is_ocr_available()` SHALL return `True`

### Requirement: OCR availability logged at startup

The system SHALL log the tesseract OCR availability status during container startup, before the application begins serving requests.

#### Scenario: Tesseract available

- **WHEN** the container starts and `tesseract` is found in PATH
- **THEN** the startup log SHALL include an INFO-level message indicating OCR is available

#### Scenario: Tesseract not available

- **WHEN** the container starts and `tesseract` is not found in PATH
- **THEN** the startup log SHALL include a WARNING-level message indicating OCR is unavailable with installation hints

### Requirement: Production deployment documentation

The system SHALL provide a `docs/deployment-guide.md` covering prerequisites, credential setup, environment configuration, first launch, health verification, and backup strategy.

#### Scenario: Operator follows deployment guide

- **WHEN** an operator follows `docs/deployment-guide.md` on a fresh server with Docker installed
- **THEN** all 5 services (backend, scheduler, bot, frontend, redis) SHALL start successfully and pass health checks

