## Why

Gmail API 回傳的 `attachmentId` 並非穩定識別碼 — 每次呼叫 `messages.get()` 都會重新生成新的值。CCAS 目前以 `(gmail_message_id, gmail_attachment_id)` 作為 staging dedupe 鍵（`ingestor/staging.py:86-89`），這個鍵在重跑 pipeline 時永遠對不上既有紀錄，導致：

1. 每次執行 ingest（不論是否 `--force`）都會重新下載相同附件、寫入新的 staging record
2. `staged_attachments` 表快速膨脹（實測 CTBC 129 unique messages → 903 列，約 7 倍）
3. 「無 `--force` 應略過已處理」的冪等保證完全失效
4. 浪費 Gmail API 配額、磁碟空間與 pipeline 執行時間

此問題是阻斷全銀行 pipeline 端到端測試的 blocker，必須先修復才能推進其他銀行驗證。

## What Changes

- **BREAKING**: `StagedAttachment` dedupe 鍵從 `(gmail_message_id, gmail_attachment_id)` 改為 `(gmail_message_id, gmail_part_id)`，其中 `gmail_part_id` 來自 Gmail MIME payload 中 stable 的 `partId`（MIME tree 位置，例如 `"1"`、`"0.1.2"`）
- 新增 `StagedAttachment.gmail_part_id` 欄位（nullable，為既有資料留空以便漸進遷移）
- `GmailAttachmentMeta` 新增 `part_id: str` 欄位，`_collect_pdf_parts()` 從 Gmail API payload 擷取 `part["partId"]`
- `find_existing_staged()` 先以 `(message_id, part_id)` 查詢；若 `part_id` 為舊資料空值則 fallback 到 `(message_id, original_filename)` 比對
- 新增 `scripts/dedupe_staged_attachments.py` 一次性清理腳本：對每個 `(bank_code, gmail_message_id, original_filename)` 群組保留 `id` 最大（最新）的一列、刪除其餘，並支援 `--dry-run`
- 保留既有 `gmail_attachment_id` 欄位作為稽核用途，不在 dedupe 邏輯中使用

## Capabilities

### New Capabilities

無

### Modified Capabilities

- `attachment-staging`: dedupe 行為規格從「attachment identity」明確為「stable Gmail part identifier」；model 新增 `gmail_part_id` 欄位
- `gmail-ingestion`: 明確指定 `GmailAttachmentMeta` 必須攜帶 `part_id`，force 模式 dedupe 比對改用 part_id

## Impact

- **Code**:
  - `backend/src/ccas/ingestor/gmail_client.py`（`GmailAttachmentMeta`、`_collect_pdf_parts`）
  - `backend/src/ccas/ingestor/staging.py`（`find_existing_staged`、`create_staged_record`）
  - `backend/src/ccas/ingestor/job.py`（傳遞 `part_id` 至 staging 建立流程）
  - `backend/src/ccas/storage/models.py`（`StagedAttachment.gmail_part_id` 欄位）
- **DB Migration**: 新 Alembic revision 為 `staged_attachments` 增加 `gmail_part_id TEXT NULL` 與 index
- **Data cleanup**: 既有 CTBC/SINOPAC 冗餘紀錄需透過一次性腳本清理（`scripts/dedupe_staged_attachments.py`）
- **Tests**:
  - `backend/tests/unit/ingestor/` 新增 `find_existing_staged` fallback 行為測試
  - `backend/tests/integration/` 新增「同一 Gmail fixture 連跑兩次 ingest 第二次全 skip」測試
- **Behavior**:
  - 修復後首次 ingest：舊資料 part_id 為 NULL → fallback filename 比對 → skip 舊資料；同步寫入新 part_id 欄位
  - 之後 ingest：穩定以 part_id 匹配
  - `--force` 仍強制重下載（不受影響）
- **無外部 API 影響**（純內部 dedupe 邏輯重構）
