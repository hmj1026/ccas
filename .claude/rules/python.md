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

## Imports

- Absolute imports: `from ccas.storage.models import Bill`
- Standard library -> third-party -> local (enforced by ruff isort rules)

## Language

- All user-facing responses in Traditional Chinese
- Code, comments, and docstrings in English

---

> For database/model conventions, see `python-db.md` (active when editing models or migrations).
> For testing conventions, see `python-testing.md` (active when editing tests/).
> For API/FastAPI conventions, see `python-api.md` (active when editing routers/).
