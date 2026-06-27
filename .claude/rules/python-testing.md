---
paths:
  - "tests/**/*.py"
  - "**/conftest.py"
---
# CCAS Testing Conventions

## Structure

- Directory-based separation: `tests/unit/`, `tests/integration/`, `tests/e2e/`
- No pytest marks; directory determines test type
- Fixtures in `conftest.py` at each test level

## Async Tests

- All test functions: `async def test_*()`
- asyncio_mode = "auto" (configured in pyproject.toml)

## Integration Tests

- In-memory SQLite: `create_async_engine("sqlite+aiosqlite:///:memory:")`
- Test client: `httpx.AsyncClient(transport=ASGITransport(app=app))`
- DB override: `app.dependency_overrides[get_db_session]`
- Seed helpers: `_seed_*()` functions create test data

```python
@pytest.fixture
async def client(app, db_session):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

## TDD Workflow

`ccas-tdd-red-check.sh` auto-runs `test_*.py` on Write to confirm RED. Coverage gate: `uv run pytest --cov --cov-report=term-missing`. For deeper TDD guidance use the `tdd-workflow` skill (npx `.agents/skills`).

## Type Safety in Tests

- Test fakes/stubs must inherit from the ABC they replace (nominal typing) to avoid pyright `reportArgumentType`
- Use `Sequence` instead of `list` for parameters needing only read-only collection access (`list` is invariant)
- See `tests/unit/parser/test_registry.py` `FakeParser(BankParser)` pattern as reference
