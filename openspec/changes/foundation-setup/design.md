## Context

CCAS is a greenfield project with a finalized spec (`docs/notion.md`) but zero code. The system consists of a Python backend (Gmail ingestor, PDF parser, classifier, Telegram bot, REST API) and a React frontend (dashboard). This foundation change establishes the project scaffold, database schema, configuration system, and test infrastructure that all subsequent feature changes depend on.

Current state: only OpenSpec workflow files and documentation exist. No `backend/` or `frontend/` directories.

## Goals / Non-Goals

**Goals:**
- Runnable backend and frontend with `docker compose up`
- All 4 database tables created and migrated via Alembic
- Backend tests runnable with `uv run pytest` (with coverage)
- Frontend tests runnable with `pnpm test` (with coverage)
- Environment-based configuration with `.env` support
- Clear directory structure that maps to the spec's module architecture

**Non-Goals:**
- No feature implementation (no parser, ingestor, bot, or API routes)
- No production deployment configuration (CI/CD, cloud hosting)
- No seed data or sample PDF fixtures
- No frontend pages or components beyond a health-check placeholder
- No Telegram or Gmail integration

## Decisions

### D1: uv over Poetry for Python dependency management

**Choice**: uv

**Rationale**: 10-100x faster than Poetry for dependency resolution and installation. Native lockfile support. Growing ecosystem adoption in 2025-2026. Single binary, no Python bootstrap needed.

**Alternatives considered**:
- Poetry: mature but slow, complex resolver
- pip + requirements.txt: no lockfile, no project metadata standard

### D2: Monorepo with backend/ and frontend/ directories

**Choice**: Single repo, two top-level directories (`backend/`, `frontend/`)

**Rationale**: Simplest structure for a 1-person project. Shared Docker Compose. Easy to navigate. No need for monorepo tooling (nx, turborepo).

**Alternatives considered**:
- Separate repos: unnecessary overhead for 1 developer
- Flat structure: mixing Python and Node configs causes confusion

### D3: SQLAlchemy 2.0 with Alembic for database

**Choice**: SQLAlchemy 2.0 ORM + Alembic migrations

**Rationale**: Type-safe query building, async-ready (for future FastAPI async routes), auto-migration generation from model changes. Industry standard.

**Alternatives considered**:
- Raw sqlite3: no migration support, SQL scattered in code, harder to test
- Tortoise ORM: less mature, smaller ecosystem
- SQLModel: built on SQLAlchemy but adds complexity with Pydantic integration overlap

### D4: SQLite stored in a Docker volume

**Choice**: Single SQLite file at `/data/ccas.db` inside a named Docker volume

**Rationale**: Zero-config database, perfect for single-user personal tool. Named volume persists across container restarts. Easy to backup (copy one file).

**Alternatives considered**:
- PostgreSQL: overkill for single-user, requires separate container
- Bind mount: works but volume is more portable

### D5: pydantic-settings for configuration

**Choice**: pydantic-settings with `.env` file

**Rationale**: Type-safe settings with validation at startup. Auto-loads from environment variables and `.env` files. Integrates naturally with FastAPI (also Pydantic-based).

**Alternatives considered**:
- python-dotenv + manual parsing: no validation, no type safety
- dynaconf: more features than needed, extra dependency

### D6: React + Vite + shadcn/ui for frontend

**Choice**: React 19 + Vite + TypeScript + Tailwind CSS + shadcn/ui + Recharts

**Rationale**: shadcn/ui provides copy-paste components (not a dependency), Recharts integrates natively with React. Vite is the standard React build tool. Largest ecosystem for dashboard components.

**Alternatives considered**:
- Vue 3 + Naive UI: simpler API but smaller component ecosystem for dashboards
- Svelte: smallest ecosystem, fewer chart options
- Next.js: SSR unnecessary for a personal dashboard tool

### D7: Docker Compose with 2 services

**Choice**: `backend` (Python/FastAPI) + `frontend` (Node/Vite dev server) containers, shared volume for SQLite

**Rationale**: Consistent dev environment, mirrors production. Frontend proxies API calls to backend via Docker networking.

```yaml
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    volumes: ["ccas-data:/data"]
  frontend:
    build: ./frontend
    ports: ["5173:5173"]
volumes:
  ccas-data:
```

## Risks / Trade-offs

**SQLite concurrency** -- SQLite has limited concurrent write support. For a single-user tool with one scheduler process, this is acceptable. If multi-user access is ever needed, migrate to PostgreSQL.
- Mitigation: Use WAL mode (`PRAGMA journal_mode=WAL`) for better read concurrency.

**uv ecosystem maturity** -- uv is newer than Poetry. Some edge cases with complex dependency trees may arise.
- Mitigation: uv has strong backing (Astral/Ruff team), active development. Fallback to pip if needed.

**SQLite in Docker volume** -- Volume data is tied to the Docker host. Losing the volume loses all data.
- Mitigation: Document backup procedure (copy volume or SQLite file). Consider periodic backup job in future.

**Frontend dev server in Docker** -- HMR through Docker can be slower than native dev.
- Mitigation: Configure Vite HMR with `server.watch.usePolling` if needed. Developers can also run frontend natively with `pnpm dev`.

## Open Questions

- Should Alembic use async engine or sync? (Decision: start with sync, migrate to async when adding async routes)
- Should `.env.example` be committed with placeholder values? (Decision: yes, for documentation)
