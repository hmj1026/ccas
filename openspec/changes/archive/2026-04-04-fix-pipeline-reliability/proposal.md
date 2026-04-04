## Why

Codex 對抗性審查發現 5 個流水線可靠性缺陷（2×P1 + 3×P2），經程式碼驗證全部屬實。在 Docker 部署環境下，pipeline 完全無法執行（無 RQ worker 消費佇列、scheduler URL 不可達）；在任何環境下，暫時性下載失敗會永久遺失帳單、Gmail 分頁與巢狀 MIME 結構中的 PDF 會被靜默丟棄。這些問題必須在進入生產前修復。

## What Changes

- 在 `docker-compose.yaml` 新增 RQ worker 服務，消費 pipeline 佇列任務
- 分離 scheduler 呼叫 API 的 URL 設定（`SCHEDULER_API_BASE_URL`），使 Docker 內 scheduler 可正確路由至 backend
- 修改附件 staging dedupe 邏輯，讓 `status="failed"` 的記錄在下次執行時自動重試
- Gmail `search_messages()` 跟隨 `nextPageToken` 分頁，取回所有符合條件的郵件
- `_extract_pdf_attachments()` 改為遞迴解析，支援巢狀 MIME 結構中的 PDF 附件

## Capabilities

### New Capabilities

（無新增 capability）

### Modified Capabilities

- `docker-deployment`: 新增 RQ worker 服務定義，確保佇列任務被消費
- `scheduler-jobs`: 新增 `SCHEDULER_API_BASE_URL` 設定，分離 server bind address 與 client request URL
- `attachment-staging`: failed 記錄自動重試，不再需要 `--force` 才能重新下載
- `gmail-ingestion`: 支援 Gmail 分頁（nextPageToken）與遞迴 MIME 解析

## Impact

- **Docker 部署**：`docker-compose.yaml` 新增 worker 服務、scheduler 新增環境變數
- **設定**：`config.py` 新增 `scheduler_api_base_url` 欄位、`.env.example` 同步更新
- **Ingestor**：`job.py` dedupe 分支邏輯修改、`gmail_client.py` 分頁迴圈與遞迴函式重構
- **測試**：各修正點均需新增/更新單元測試
