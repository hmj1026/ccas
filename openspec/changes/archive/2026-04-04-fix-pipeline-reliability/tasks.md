## 1. Docker RQ Worker 服務 (P1)

- [x] 1.1 在 `docker-compose.yaml` 新增 `worker` 服務：同 backend build context/target、共用 volumes/env_file/shared-env、depends_on backend(healthy)+redis(healthy)、command `uv run rq worker --url redis://redis:6379/0`、restart unless-stopped
- [x] 1.2 新增整合測試驗證 `docker compose config` 包含 worker 服務定義

## 2. Scheduler API URL 分離 (P2)

- [x] 2.1 在 `backend/src/ccas/config.py` Settings 新增 `scheduler_api_base_url: str = ""` 欄位
- [x] 2.2 修改 `backend/src/ccas/scheduler/jobs.py` `trigger_pipeline_via_api()`：優先使用 `scheduler_api_base_url`，空值 fallback 到 `http://{api_host}:{api_port}`
- [x] 2.3 在 `docker-compose.yaml` scheduler 服務 environment 加 `SCHEDULER_API_BASE_URL: "http://backend:8000"`
- [x] 2.4 更新 `.env.example` 新增 `SCHEDULER_API_BASE_URL=` 說明
- [x] 2.5 新增單元測試：mock get_settings() 驗證 URL 建構（有值 / 空值 fallback 兩種 case）

## 3. Failed 附件自動重試 (P1)

- [x] 3.1 修改 `backend/src/ccas/ingestor/job.py` `_process_attachment()` dedupe 邏輯：`existing.status == "failed"` 時不 skip，進入重新下載流程
- [x] 3.2 新增單元測試：status="failed" 記錄 → 驗證自動重試（不 skip）
- [x] 3.3 新增單元測試：status="staged" 記錄 → 驗證 skip（回歸保護）

## 4. MIME 遞迴解析 (P2)

- [x] 4.1 在 `backend/src/ccas/ingestor/gmail_client.py` 新增 `_collect_pdf_parts(message_id, part, message_date, out, depth=0)` 遞迴函式，depth limit=10
- [x] 4.2 修改 `_extract_pdf_attachments()` 呼叫 `_collect_pdf_parts()`，公開簽章不變
- [x] 4.3 新增單元測試：巢狀 payload（PDF 在第 2 層）→ 找到
- [x] 4.4 新增單元測試：扁平 payload → 仍正常（回歸保護）
- [x] 4.5 新增單元測試：超過 depth limit → 停止搜尋

## 5. Gmail 分頁 (P2)

- [x] 5.1 修改 `backend/src/ccas/ingestor/gmail_client.py` `search_messages()`：迴圈跟隨 `nextPageToken`，加 `_MAX_PAGES = 10` 安全限制
- [x] 5.2 新增單元測試：mock 兩頁回應 → 全部取回
- [x] 5.3 新增單元測試：無 nextPageToken → 單頁正常
- [x] 5.4 新增單元測試：超過 limit → warning log + 停止

## 6. 驗證

- [x] 6.1 `uv run ruff check . && uv run ruff format --check .` 通過
- [x] 6.2 `uv run pyright` 通過（無新增錯誤；既有 pytest import 與 parser type 問題為預先存在）
- [x] 6.3 `uv run pytest --cov --cov-report=term-missing` 全部通過且覆蓋率 ≥ 80%
