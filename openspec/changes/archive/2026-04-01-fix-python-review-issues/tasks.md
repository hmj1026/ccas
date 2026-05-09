## Tasks

### 1. Engine / Session Factory Caching

- [x] 1.1 在 `storage/database.py` 的 `get_engine()` 加入 `@lru_cache(maxsize=1)`，回傳型別標註 `AsyncEngine`
- [x] 1.2 移除 `get_session_factory()` 的 `engine` 參數，改為內部呼叫 `get_engine()`，加入 `@lru_cache(maxsize=1)`
- [x] 1.3 為 `_set_sqlite_wal` 加入型別標註（`DBAPIConnection`, `ConnectionPoolEntry`）
- [x] 1.4 更新現有測試，確保使用 `get_engine.cache_clear()` 進行隔離（測試未直接呼叫，使用 FastAPI dependency override）

### 2. Datetime UTC Migration

- [x] 2.1 在 `storage/models.py` 加入 `from datetime import UTC`
- [x] 2.2 將 4 處 `default=datetime.utcnow` 改為 `default=lambda: datetime.now(UTC)`（Bill, Transaction, StagedAttachment, PaymentReminder）
- [x] 2.3 確認既有測試中對 `created_at` / `sent_at` 的斷言仍通過

### 3. Exception Narrowing

- [x] 3.1 `ingestor/job.py` `_process_attachment`: 保留 `except Exception`（多種 I/O 來源），加入 `exc_info=True` 保留 traceback
- [x] 3.2 `parser/banks/ctbc_v1.py` `can_parse`: 保留 `except Exception`（pdfplumber 可拋多種例外類型），已有 `exc_info=True`
- [x] 3.3 `pipeline/worker.py` `on_failure_handler`: 用 try/except 包裹 `asyncio.run(_mark())`，log error with traceback
- [x] 3.4 `pipeline/worker.py` `on_failure_handler`: 加入完整型別標註

### 4. API Response Model

- [x] 4.1 在 `api/schemas.py` 新增 `PipelineTriggerData(BaseModel)` schema
- [x] 4.2 `trigger_pipeline` endpoint 加入 `response_model=ApiResponse[PipelineTriggerData]`
- [x] 4.3 確認 OpenAPI docs 正確顯示 response schema（response_model 已設定）

### 5. PipelineOptions Type Fixes

- [x] 5.1 `pipeline/options.py` `from_dict`: 型別標註改為 `Mapping[str, object] | None`，加入 `from collections.abc import Mapping`
- [x] 5.2 `pipeline/options.py` `date_range`: 2 處 `assert` 改為 `if ... is None: raise ValueError(...)`
- [x] 5.3 確認 `uv run pyright` 零錯誤

### 6. Extract Shared Query

- [x] 6.1 建立 `storage/queries.py`，實作 `async def fetch_bank_names(session: AsyncSession) -> dict[str, str]`
- [x] 6.2 `api/routers/bills.py` 移除 `_fetch_bank_names`，改引用 `storage/queries.py`
- [x] 6.3 `api/routers/analytics.py` 移除 `_fetch_bank_names`，改引用 `storage/queries.py`
- [x] 6.4 `api/routers/overview.py` 移除 `_fetch_bank_names`，改引用 `storage/queries.py`
- [x] 6.5 `scheduler/reminders.py` 移除 `_fetch_bank_names`，改引用 `storage/queries.py`（含 bot/job.py）

### 7. Test Lint Fixes

- [x] 7.1 `tests/unit/pipeline/test_filters.py`: 移除 unused imports（`datetime`, `pytest`）
- [x] 7.2 `tests/unit/ingestor/test_force_safety.py`: ruff format
- [x] 7.3 執行 `uv run ruff check . && uv run ruff format --check .` 確認零問題

### 8. Final Verification

- [x] 8.1 `uv run pytest` 全部通過（425 passed）
- [x] 8.2 `uv run pyright` 零錯誤
- [x] 8.3 `uv run ruff check . && uv run ruff format --check .` 零問題
