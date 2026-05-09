## Why

Python code review 揭露了多個影響系統正確性與可維護性的問題：資料庫引擎在每次 request 時重建（並發下會耗盡 file descriptor）、ORM model 使用已在 Python 3.12 棄用的 `datetime.utcnow()`、exception handling 過於寬泛導致除錯困難、API endpoint 缺少 response model、型別標註不正確導致 pyright 報錯。這些問題需在進入下一階段功能開發前修正。

## What Changes

- `get_engine()` 和 `get_session_factory()` SHALL 加入 `@lru_cache` 快取，避免每次 request 建立新引擎與連線池。
- 所有 ORM model 的時間欄位預設值 SHALL 由 `datetime.utcnow` 改為 `datetime.now(UTC)`，確保新資料保存 timezone-aware timestamp。
- `_process_attachment` 與 `can_parse` 的例外處理 SHALL 收窄為具體例外類型，避免吞掉未預期錯誤。
- `trigger_pipeline` endpoint SHALL 加入 `response_model`，使回應契約可被明確驗證。
- `PipelineOptions.from_dict` 的輸入型別 SHALL 由 `dict` 擴充為 `Mapping`，並 MUST 通過 strict type checking。
- `date_range()` 的防護邏輯 SHALL 以明確的 `ValueError` 取代 `assert`。
- `_set_sqlite_wal` 和 `on_failure_handler` SHALL 補充型別標註，消除 review 指出的型別缺口。
- 重複的 `_fetch_bank_names` 邏輯 SHALL 提取為共用查詢函式，減少重複實作。
- 測試檔案的 unused imports 與格式問題 MUST 一併修正，避免品質檢查持續失敗。

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `database-schema` SHALL 將 ORM 時間欄位預設值由 `datetime.utcnow` 改為 `datetime.now(UTC)`。
- `error-handling-patterns` SHALL 收窄 ingestor 和 parser 的 exception 捕捉範圍，符合「精確區分」原則。
- `pipeline-options` SHALL 修正 `from_dict` 型別標註，並 SHALL 將 `date_range` 防護邏輯由 `assert` 改為 `ValueError`。

## Impact

- **ORM models** (`storage/models.py`) SHALL 在 4 個時間欄位上改用 timezone-aware default；此變更 MUST 不要求 Alembic migration，因為預設值由 Python 端提供而非 DB schema default。
- **Database layer** (`storage/database.py`) SHALL 改變 engine/session factory 生命週期；測試 MUST 確認 mock 與 override 機制仍正常。
- **Pipeline** (`pipeline/options.py`, `pipeline/worker.py`) SHALL 更新型別簽名；下游呼叫端 MUST 繼續相容。
- **API** (`api/routers/pipeline.py`) SHALL 維持既有 response shape，但 MUST 新增 Pydantic response model 約束。
- **Parser** (`parser/banks/ctbc_v1.py`) SHALL 收窄 exception 範圍，且 MUST 確認未遺漏實際會發生的例外類型。
- **Shared queries** SHALL 抽出共用函式供 3 個模組引用，避免重複查詢邏輯。
- **Tests** MUST 修正 unused imports 與格式問題，確保品質檢查可穩定通過。
