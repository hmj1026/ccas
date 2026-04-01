---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
# CCAS Python Conventions

## Tooling

- **Formatter/Linter**: ruff (line-length 88, target py312)
- **Type checker**: pyright (strict mode)
- **Test runner**: pytest with pytest-asyncio (asyncio_mode = "auto")
- **Package manager**: uv

## Async-First

All code is fully async. Never use sync DB access or sync HTTP calls.

- FastAPI endpoints: `async def`
- DB sessions: `AsyncSession` via `async_sessionmaker`
- Engine: `create_async_engine("sqlite+aiosqlite://...")`
- Queries: `await session.execute(stmt)` with `select()` statements

## Error Handling

- All domain errors inherit from `CcasError` (defined in `ccas.errors`)
- Stage-specific: `IngestError`, `DecryptError`, `ParseError`, `ClassifyError`, `NotifyError`
- Format: `raise ParseError("description", "reason", bank_code="CTBC")`
- HTTP errors: `raise HTTPException(status_code=..., detail="...")`
- Never use bare `except Exception`; catch specific types

## Logging

- Use `logging.getLogger(__name__)` -- never `print()`
- JSON structured logging via `ccas.log.configure_logging()`
- Secrets are auto-redacted by `RedactingFilter`
- Pattern: `logger.error("msg", extra={"key": val})`

## Configuration

- All config via `ccas.config.Settings` (pydantic-settings, loads `../.env`)
- Access via `get_settings()` (lru_cache singleton)
- New env vars: add to `Settings` class + `.env.example`

## SQLAlchemy Models

- Inherit from `Base` (DeclarativeBase)
- Always set `__tablename__`
- Use `Mapped[T]` with `mapped_column()` for all columns
- Relationships: `relationship()` with `back_populates`
- Constraints in `__table_args__` tuple
- After model changes: `uv run alembic revision --autogenerate -m "<description>"`

## API Response Format

All endpoints use the unified envelope:

- Success: `ApiResponse[T](data=result)` -> `{"success": true, "data": T, "message": ""}`
- Paginated: `PaginatedResponse[T]` -> adds `pagination` field
- Error: `{"success": false, "message": "reason", "data": null}`
- Always use `response_model=ApiResponse[T]` or `PaginatedResponse[T]`

## FastAPI Patterns

- Auth: `Depends(verify_token)` applied globally via router dependencies
- DB: `Depends(get_db_session)` yields async session
- Query params: annotate with `Query()` including validators
- CORS: configured in `create_app()` app factory

## Imports

- Absolute imports: `from ccas.storage.models import Bill`
- Standard library -> third-party -> local (enforced by ruff isort rules)

## Testing

- Directory-based separation: `tests/unit/`, `tests/integration/`, `tests/e2e/`
- No pytest marks; directory structure determines test type
- Integration tests: in-memory SQLite via `create_async_engine("sqlite+aiosqlite:///:memory:")`
- Test client: `httpx.AsyncClient(transport=ASGITransport(app=app))`
- DB override: `app.dependency_overrides[get_db_session]`
- All test functions: `async def test_*()`
- Fixtures in `conftest.py` at each test level
- Seeding: helper `_seed_*()` functions create test data

## Language

- All user-facing responses in Traditional Chinese
- Code, comments, and docstrings in English
