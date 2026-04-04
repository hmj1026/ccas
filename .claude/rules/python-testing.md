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

1. Write test first (RED) -- hook auto-runs on `Write test_*.py`
2. Confirm it fails
3. Write minimal implementation (GREEN)
4. Refactor
5. Verify coverage: `uv run pytest --cov --cov-report=term-missing`

## Type Safety in Tests

- Test fakes/stubs 必須繼承被替代的 ABC（nominal typing），避免 pyright `reportArgumentType`
- 函式參數若只需 read-only 存取集合，用 `Sequence` 而非 `list`（`list` 是 invariant）
- 參考 `tests/unit/parser/test_registry.py` 的 `FakeParser(BankParser)` 寫法
