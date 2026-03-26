## Why

CCAS has a complete system spec (`docs/notion.md`) but no runnable code. Before building any feature (parser, ingestor, bot, dashboard), the project needs a working foundation: Python backend scaffold, React frontend scaffold, database schema, Docker orchestration, and test infrastructure. Without this, no feature work can begin.

## What Changes

- Initialize Python 3.12+ backend project with uv, FastAPI, SQLAlchemy, and pytest
- Initialize React + Vite + TypeScript frontend project with pnpm, Tailwind, shadcn/ui, and vitest
- Create SQLAlchemy ORM models for all 4 tables (bills, transactions, categories, bank_configs) with Alembic migrations
- Set up Docker Compose to orchestrate backend + frontend with shared SQLite volume
- Configure pydantic-settings for environment-based configuration (.env)
- Establish test infrastructure: pytest (backend) + vitest (frontend) with coverage configs
- Create project directory structure matching the spec architecture

## Capabilities

### New Capabilities

- `project-scaffold`: Python backend + React frontend project initialization, directory structure, dependency management (uv, pnpm), and Docker Compose orchestration
- `database-schema`: SQLAlchemy ORM models for bills, transactions, categories, and bank_configs tables with Alembic migration support
- `app-config`: Centralized configuration management via pydantic-settings, .env files, and environment variable loading
- `test-infrastructure`: pytest and vitest setup with coverage reporting, fixture patterns, and test directory conventions

### Modified Capabilities

(none -- this is a greenfield project)

## Impact

- **New files**: ~30 files across backend/, frontend/, docker-compose.yaml
- **Dependencies**: Python packages (fastapi, sqlalchemy, alembic, pydantic-settings, pytest, pytest-cov), Node packages (react, vite, tailwindcss, shadcn/ui, vitest)
- **Infrastructure**: Docker Compose with 2 services (backend, frontend), shared volume for SQLite
- **Dev workflow**: `uv run pytest` for backend tests, `pnpm test` for frontend tests, `docker compose up` for full stack
