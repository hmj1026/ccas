## ADDED Requirements

### Requirement: pytest configuration for backend
The system SHALL configure pytest via `pyproject.toml` with test directories at `backend/tests/unit/` and `backend/tests/integration/`. Coverage reporting SHALL be enabled targeting the `ccas` package with a minimum threshold of 80%.

#### Scenario: pytest discovers and runs tests
- **WHEN** `uv run pytest` is executed from the `backend/` directory
- **THEN** pytest discovers tests in `tests/unit/` and `tests/integration/` and executes them

#### Scenario: Coverage report generated
- **WHEN** `uv run pytest --cov=ccas --cov-report=term-missing` is executed
- **THEN** a coverage report is displayed showing line-by-line coverage for all `ccas` modules

### Requirement: Backend test directory structure
The system SHALL organize backend tests into `tests/unit/` (pure unit tests, no database or external services) and `tests/integration/` (tests with database fixtures). Each test directory SHALL contain an `__init__.py` and a `conftest.py`.

#### Scenario: Unit test directory exists with conftest
- **WHEN** the project is initialized
- **THEN** `backend/tests/unit/conftest.py` exists and is importable

#### Scenario: Integration test directory exists with conftest
- **WHEN** the project is initialized
- **THEN** `backend/tests/integration/conftest.py` exists and is importable

### Requirement: Database fixture for integration tests
The integration test `conftest.py` SHALL provide a `db_session` fixture that creates an in-memory SQLite database, runs Alembic migrations, yields a SQLAlchemy session, and rolls back after each test.

#### Scenario: Integration test gets clean database
- **WHEN** an integration test uses the `db_session` fixture
- **THEN** a fresh in-memory database with all tables is available, and changes are rolled back after the test

### Requirement: Smoke test for backend health endpoint
The system SHALL include a smoke test that verifies the FastAPI `/health` endpoint returns status 200 with `{"status": "ok"}`.

#### Scenario: Health endpoint test passes
- **WHEN** `uv run pytest tests/integration/test_health.py` is executed
- **THEN** the test passes confirming the health endpoint works

### Requirement: vitest configuration for frontend
The system SHALL configure vitest via `vite.config.ts` for the frontend project. Test files SHALL follow the `*.test.tsx` or `*.test.ts` naming convention.

#### Scenario: vitest discovers and runs tests
- **WHEN** `pnpm test` is executed from the `frontend/` directory
- **THEN** vitest discovers and runs all test files

### Requirement: Smoke test for frontend
The system SHALL include a smoke test that verifies the React App component renders without crashing.

#### Scenario: App render test passes
- **WHEN** `pnpm test` is executed
- **THEN** the smoke test passes confirming the App component renders
