## Why

Pipeline 目前有完善的三層去重機制（ingestion / parse / notify），預設行為正確地避免 API 浪費。但當使用者更新了銀行密碼、修正了 parser、或需要重新處理特定月份帳單時，**沒有任何方式繞過去重來強制重新下載與重新解析**。同時 CLI 和 API 都不支援按銀行、月份、年份篩選，每次都必須處理所有銀行的所有郵件。

## What Changes

- 新增 `PipelineOptions` frozen dataclass，作為 pipeline 參數的統一載體
- CLI (`python -m ccas.pipeline`) 加入 `--force`、`--bank`、`--year`、`--month` 參數
- API (`POST /api/pipeline/trigger`) 接受 JSON body 傳入相同參數
- Ingestion 層在 force 模式下刪除已存在的 `StagedAttachment` 記錄後重新下載
- Parse 層在 force 模式下刪除已存在的 `Bill`（cascade 刪除 Transactions）後重新解析
- 日期篩選透過 Gmail 查詢語法 `after:/before:` 在 API 層面過濾，減少不必要的資料傳輸

## Capabilities

### New Capabilities

- `pipeline-options`: Pipeline 執行參數模型（force / bank / year / month）與 Gmail 日期篩選邏輯

### Modified Capabilities

- `pipeline-orchestration`: 接受並傳遞 `PipelineOptions` 到各階段
- `gmail-ingestion`: 支援 force 模式（刪除舊記錄重下載）與 bank/date 篩選
- `parse-orchestration`: 支援 force 模式（刪除舊 Bill 重解析）

## Impact

- **CLI**: `backend/src/ccas/pipeline/__main__.py` 新增 argparse
- **API**: `backend/src/ccas/api/routers/pipeline.py` 新增 request body schema
- **Schemas**: `backend/src/ccas/api/schemas.py` 新增 `PipelineTriggerRequest`
- **Pipeline**: `orchestrator.py`、`worker.py` 傳遞 options
- **Ingestion**: `job.py`、`staging.py` 實作 force + filter
- **Parser**: `job.py` 實作 force 模式
- **測試**: 新增 unit/integration tests
- **文件**: 更新 `docs/beginner-setup-guide.md`
