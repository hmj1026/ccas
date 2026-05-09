## 1. PipelineOptions 資料模型

- [x] 1.1 建立 `backend/src/ccas/pipeline/options.py`，實作 frozen dataclass `PipelineOptions(force, bank_code, year, month)` 及 `gmail_date_filter()` 方法
- [x] 1.2 撰寫 `backend/tests/unit/pipeline/test_options.py`，覆蓋預設值、各參數組合、日期邊界（閏年、12 月跨年、僅 month）

## 2. Ingestion 層 Force + Filter 支援

- [x] 2.1 在 `backend/src/ccas/ingestor/staging.py` 新增 `delete_staged_record(session, record)` 函式，刪除 DB 記錄
- [x] 2.2 修改 `backend/src/ccas/ingestor/job.py`：`run_ingestion_job(session, options=None)` 接受 options
- [x] 2.3 實作 bank_code 篩選：`_fetch_active_banks()` 接受 options，有 bank_code 時加 where 條件
- [x] 2.4 實作日期篩選：Gmail 查詢附加 `options.gmail_date_filter()` 子句
- [x] 2.5 實作 force 模式：`_process_attachment()` 中，force=True 時刪除舊記錄（含磁碟檔案）後重新下載
- [x] 2.6 撰寫 ingestion 相關的 unit / integration tests

## 3. Parse 層 Force 支援

- [x] 3.1 修改 `backend/src/ccas/parser/job.py`：`run_parse_job(session, options=None)` 接受 options
- [x] 3.2 實作 force 模式：已存在的 Bill（bank_code + billing_month）先刪除（cascade Transaction）再重新 parse
- [x] 3.3 撰寫 parse force 相關 tests

## 4. Pipeline Orchestrator 串接

- [x] 4.1 修改 `backend/src/ccas/pipeline/orchestrator.py`：`run_pipeline(session, options=None)` 傳遞 options 到 ingestion 和 parse 階段
- [x] 4.2 撰寫 orchestrator options 傳遞 tests

## 5. CLI 參數

- [x] 5.1 修改 `backend/src/ccas/pipeline/__main__.py`：加入 argparse，支援 `--force`、`--bank`、`--year`、`--month`
- [x] 5.2 建構 `PipelineOptions` 傳入 `run_pipeline()`

## 6. API 端點

- [x] 6.1 在 `backend/src/ccas/api/schemas.py` 新增 `PipelineTriggerRequest` Pydantic model
- [x] 6.2 修改 `backend/src/ccas/api/routers/pipeline.py`：`trigger_pipeline(body: PipelineTriggerRequest | None = None)` 接受 body
- [x] 6.3 修改 `backend/src/ccas/pipeline/worker.py`：`run_pipeline_sync(opts=None)` 反序列化為 `PipelineOptions`
- [x] 6.4 撰寫 API endpoint integration tests（空 body / 帶參數 body）

## 7. 驗證與文件

- [x] 7.1 執行完整測試套件，確認所有測試通過（`uv run pytest --cov`）
- [x] 7.2 執行 lint 與型別檢查（`ruff check .` + `ruff format --check .` + `pyright`）
- [x] 7.3 實際執行 `python -m ccas.pipeline --bank CTBC` 驗證 CTBC 流程
- [x] 7.4 實際執行 `python -m ccas.pipeline --force --bank CTBC` 驗證強制重下載
- [x] 7.5 更新 `docs/beginner-setup-guide.md` 加入 CLI 參數說明與 force 模式使用方式
