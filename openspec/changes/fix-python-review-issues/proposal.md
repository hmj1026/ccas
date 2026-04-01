## Why

Python code review 揭露了多個影響系統正確性與可維護性的問題：資料庫引擎在每次 request 時重建（並發下會耗盡 file descriptor）、ORM model 使用已在 Python 3.12 棄用的 `datetime.utcnow()`、exception handling 過於寬泛導致除錯困難、API endpoint 缺少 response model、型別標註不正確導致 pyright 報錯。這些問題需在進入下一階段功能開發前修正。

## What Changes

- 為 `get_engine()` 和 `get_session_factory()` 加入 `@lru_cache` 快取，避免每次 request 建立新引擎與連線池
- 將所有 ORM model 的 `datetime.utcnow` 替換為 `datetime.now(UTC)`（timezone-aware）
- 收窄 `_process_attachment` 與 `can_parse` 的 exception 捕捉範圍，改為具體例外類型
- 為 `trigger_pipeline` endpoint 加入 `response_model`
- 修正 `PipelineOptions.from_dict` 型別標註（`dict` -> `Mapping`）
- 將 `date_range()` 中的 `assert` 替換為明確的 `ValueError`
- 為 `_set_sqlite_wal` 和 `on_failure_handler` 補充型別標註
- 將重複的 `_fetch_bank_names` 提取為共用查詢函式
- 修正測試檔案的 unused imports 和格式問題

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `database-schema`: `created_at` 欄位預設值從 `datetime.utcnow` 改為 `datetime.now(UTC)`（timezone-aware）
- `error-handling-patterns`: 收窄 ingestor 和 parser 的 exception 捕捉範圍，符合「精確區分」原則
- `pipeline-options`: `from_dict` 型別標註修正、`date_range` 防護邏輯從 assert 改為 ValueError

## Impact

- **ORM models** (`storage/models.py`): 4 處 `created_at` default 變更；需產生 Alembic migration（但因 SQLite 不支援 ALTER COLUMN default，且 default 由 Python 端產生而非 DB 端，無 migration 需求）
- **Database layer** (`storage/database.py`): engine/session factory 生命週期改變，測試需確認 mock/override 機制仍正常
- **Pipeline** (`pipeline/options.py`, `pipeline/worker.py`): 型別簽名變更，下游呼叫端需配合
- **API** (`api/routers/pipeline.py`): response 格式不變，但新增 Pydantic model 約束
- **Parser** (`parser/banks/ctbc_v1.py`): exception 範圍收窄，理論上行為不變但需確認無遺漏的例外類型
- **Shared queries**: 新增 `storage/queries.py`（或類似位置）的共用函式，3 個模組改為引用
- **Tests**: 修正 unused imports 和格式（auto-fixable）
