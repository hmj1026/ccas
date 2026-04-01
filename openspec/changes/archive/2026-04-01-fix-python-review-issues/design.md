## Context

CCAS 後端使用 Python 3.12 + FastAPI + SQLAlchemy (async) + SQLite。Code review 發現了 5 個 HIGH 等級和 8 個 MEDIUM 等級的問題，涵蓋資料庫連線管理、datetime 處理、exception handling、型別安全和程式碼重複。所有問題皆為既有程式碼的修正，不涉及新功能。

## Goals / Non-Goals

### Goals

- 修正所有 HIGH 等級問題（engine caching、datetime.utcnow、exception narrowing、response model、type annotation）
- 修正所有 MEDIUM 等級問題（DRY violation、assert -> ValueError、type hints、test lint）
- 維持既有測試通過率
- 不產生 breaking API 變更

### Non-Goals

- 不重構整體架構
- 不新增功能
- 不變更資料庫 schema（`created_at` default 由 Python ORM 端產生，非 DB column default）

## Approach

### 1. Engine / Session Factory Caching (`storage/database.py`)

**現況**: `get_engine()` 每次呼叫 `create_async_engine()`，`get_session_factory()` 每次建立新 `async_sessionmaker`。

**方案**: 加入 `@lru_cache(maxsize=1)`，與 `get_settings()` 一致。

```python
from functools import lru_cache

@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    ...

@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    ...
```

**風險**: 測試中需要 override engine 的場景。`get_session_factory(engine=...)` 的 `engine` 參數使其無法直接 cache（因為 unhashable）。解法：移除 `engine` 參數，改為內部呼叫 `get_engine()`；測試透過 `get_engine.cache_clear()` + mock 或 FastAPI dependency override。

### 2. Datetime UTC Migration (`storage/models.py`)

**現況**: `default=datetime.utcnow`（4 處）。

**方案**: 改為 `default=lambda: datetime.now(UTC)`。需 `from datetime import UTC`（Python 3.11+）。

不需 Alembic migration：default 由 Python 產生（callable），非 SQL `DEFAULT` 子句。

### 3. Exception Narrowing

#### 3a. `_process_attachment` (`ingestor/job.py`)

收窄為 `except (IngestError, OSError) as exc:`，並加入 `exc_info=True`。

#### 3b. `can_parse` (`parser/banks/ctbc_v1.py`)

收窄為 `except (pdfplumber.exceptions.PSException, OSError):`（pdfplumber 底層使用 pdfminer 的 PSException）。需確認 pikepdf 未使用；此 parser 用 pdfplumber。

#### 3c. `on_failure_handler` (`pipeline/worker.py`)

用 try/except 包裹 `asyncio.run(_mark())`，避免 handler 內的例外吞掉原始 pipeline 失敗資訊。

### 4. Response Model (`api/routers/pipeline.py`)

新增 Pydantic schema：

```python
class PipelineTriggerData(BaseModel):
    job_id: str

# endpoint 加入 response_model
@router.post("/trigger", response_model=ApiResponse[PipelineTriggerData])
```

### 5. Type Annotation Fixes

#### 5a. `PipelineOptions.from_dict` (`pipeline/options.py`)

`dict[str, object] | None` -> `Mapping[str, object] | None`。

#### 5b. `date_range` assert -> ValueError (`pipeline/options.py`)

```python
# Before
assert effective_year is not None
# After
if effective_year is None:
    raise ValueError("effective_year must not be None when month is set")
```

#### 5c. `_set_sqlite_wal` type hints (`storage/database.py`)

```python
def _set_sqlite_wal(
    dbapi_connection: DBAPIConnection,
    connection_record: ConnectionPoolEntry,
) -> None:
```

#### 5d. `on_failure_handler` type hints (`pipeline/worker.py`)

```python
def on_failure_handler(
    job: Job,
    connection: Redis,
    typ: type[BaseException],
    value: BaseException,
    traceback: TracebackType | None,
) -> None:
```

### 6. Extract `_fetch_bank_names` (`storage/queries.py`)

從 `bills.py`、`analytics.py`、`overview.py`、`reminders.py` 提取共用函式至新檔案 `storage/queries.py`：

```python
async def fetch_bank_names(session: AsyncSession) -> dict[str, str]:
    """查詢所有銀行的 code -> name 對照。"""
    ...
```

4 個呼叫端改為 `from ccas.storage.queries import fetch_bank_names`。

### 7. Test Lint Fixes

- `tests/unit/pipeline/test_filters.py`: 移除 unused imports（ruff --fix）
- `tests/unit/ingestor/test_force_safety.py`: ruff format

## Risks

| 風險 | 影響 | 緩解 |
|------|------|------|
| engine cache 導致測試隔離問題 | 測試間共用同一 engine | 測試 fixture 呼叫 `get_engine.cache_clear()` |
| pdfplumber exception 類型遺漏 | `can_parse` 對未預期錯誤回傳 exception 而非 False | 加入 fallback logging，review pdfplumber source |
| `datetime.now(UTC)` 與既有 naive datetime 資料不相容 | 查詢比對時可能 type mismatch | SQLite 儲存為 text，無 timezone info；SQLAlchemy 會正確序列化 |
