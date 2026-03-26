## ADDED Requirements

### Requirement: Python backend project initialization
The system SHALL have a Python 3.12+ backend project managed by uv, with a `backend/` directory containing a `pyproject.toml` that declares all required dependencies (fastapi, uvicorn, sqlalchemy, alembic, pydantic-settings, pdfplumber, pikepdf, tabula-py, python-telegram-bot, google-api-python-client, apscheduler).

#### Scenario: Backend project is runnable
- **WHEN** a developer clones the repo and runs `cd backend && uv sync`
- **THEN** all Python dependencies are installed and `uv run python -c "import ccas"` succeeds

#### Scenario: Backend dev server starts
- **WHEN** a developer runs `uv run uvicorn ccas.api.app:create_app --factory`
- **THEN** FastAPI starts on port 8000 and the `/health` endpoint returns `{"status": "ok"}`

### Requirement: React frontend project initialization
The system SHALL have a React + TypeScript frontend project managed by pnpm, with a `frontend/` directory containing Vite, Tailwind CSS, and shadcn/ui configured.

#### Scenario: Frontend project is runnable
- **WHEN** a developer runs `cd frontend && pnpm install`
- **THEN** all Node dependencies are installed and `pnpm dev` starts the Vite dev server on port 5173

#### Scenario: Frontend build succeeds
- **WHEN** a developer runs `pnpm build`
- **THEN** the build completes without errors and produces output in `frontend/dist/`

### Requirement: Directory structure matches spec architecture
The system SHALL organize backend source code under `backend/src/ccas/` with subdirectories: `ingestor/`, `parser/`, `storage/`, `classifier/`, `bot/`, `api/`, `scheduler/`. Each subdirectory SHALL contain an `__init__.py` file.

#### Scenario: All module directories exist
- **WHEN** the project is initialized
- **THEN** all 7 module directories exist under `backend/src/ccas/` and are importable Python packages

### Requirement: Docker Compose orchestration
The system SHALL provide a `docker-compose.yaml` at the project root with two services: `backend` (Python/FastAPI on port 8000) and `frontend` (Vite dev server on port 5173), sharing a named volume `ccas-data` mounted at `/data` in the backend container.

#### Scenario: Full stack starts with docker compose
- **WHEN** a developer runs `docker compose up`
- **THEN** both backend and frontend services start, and the backend `/health` endpoint is reachable at `http://localhost:8000/health`

#### Scenario: Data persists across restarts
- **WHEN** `docker compose down` is run followed by `docker compose up`
- **THEN** the SQLite database file at `/data/ccas.db` retains its data from the previous session

### Requirement: Backend Dockerfile
The backend Dockerfile SHALL use a Python 3.12 base image, install uv, copy `pyproject.toml` and `uv.lock`, install dependencies, and copy source code. The entrypoint SHALL run uvicorn.

#### Scenario: Backend Docker image builds
- **WHEN** `docker build ./backend` is executed
- **THEN** the image builds successfully and `docker run <image> python -c "import ccas"` succeeds

### Requirement: Frontend Dockerfile
The frontend Dockerfile SHALL use a Node 22 base image, install pnpm, copy `package.json` and `pnpm-lock.yaml`, install dependencies, and copy source code. The entrypoint SHALL run the Vite dev server with host binding to `0.0.0.0`.

#### Scenario: Frontend Docker image builds
- **WHEN** `docker build ./frontend` is executed
- **THEN** the image builds successfully and the dev server starts
