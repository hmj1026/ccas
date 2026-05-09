# Tasks

## T1: GmailAttachmentMeta 與 PDF part 擷取加入 part_id
- [x] T1.1 `backend/src/ccas/ingestor/gmail_client.py` — `GmailAttachmentMeta` dataclass 新增 `part_id: str = ""` 欄位（排在 `attachment_id` 後）
- [x] T1.2 `_collect_pdf_parts()` 從 `part.get("partId", "")` 抓取並傳入 `GmailAttachmentMeta`
- [x] T1.3 Unit test `backend/tests/unit/ingestor/test_gmail_client.py` — 用 fixture payload 驗證 `part_id` 被正確擷取（根層 `"1"`、巢狀 `"0.1"`）

## T2: StagedAttachment model 與 Alembic migration
- [x] T2.1 `backend/src/ccas/storage/models.py` — `StagedAttachment` 新增 `gmail_part_id: Mapped[str | None] = mapped_column(Text, nullable=True)`；更新 class docstring 描述新 dedupe 鍵
- [x] T2.2 `__table_args__`：移除 `uq_staged_gmail_attachment`（舊 constraint on attachment_id），新增 `UniqueConstraint("gmail_message_id", "gmail_part_id", name="uq_staged_gmail_message_part")`
- [x] T2.3 `cd backend && uv run alembic revision --autogenerate -m "add-staged-attachment-gmail-part-id"` 產出 migration；手動審核並在 upgrade 內加 `op.create_index("ix_staged_gmail_message_part", "staged_attachments", ["gmail_message_id", "gmail_part_id"])`
- [x] T2.4 驗證 migration 可以順利 upgrade 與 downgrade（downgrade 須 drop column、drop unique、重建舊 unique）

## T3: find_existing_staged 雙路徑查詢
- [x] T3.1 `backend/src/ccas/ingestor/staging.py` — `find_existing_staged` 簽章改為 `(session, message_id, part_id, original_filename)`
- [x] T3.2 主查詢：`(gmail_message_id=?, gmail_part_id=?)`；若 part_id 為空字串則跳過主查詢
- [x] T3.3 Fallback：若主查詢無命中，查 `(gmail_message_id=?, original_filename=?, gmail_part_id IS NULL)`
- [x] T3.4 命中 fallback 時，回傳結果並由呼叫端決定是否 backfill（本函式 SHALL NOT 直接寫入）
- [x] T3.5 新增 `backfill_part_id(session, staged_row, part_id)` helper 寫回 `gmail_part_id`
- [x] T3.6 `create_staged_record()` 新增 `part_id: str = ""` 參數並寫入新欄位
- [x] T3.7 Unit tests `backend/tests/unit/ingestor/test_staging.py`：
  - [x] 主查詢命中（有 part_id）
  - [x] Fallback 命中（part_id 為 NULL、filename 匹配）
  - [x] 兩者皆不命中（None）
  - [x] backfill_part_id 正確寫入
  - [x] 主查詢優先於 fallback（同 message_id 但不同 part_id 的記錄存在時）

## T4: ingestor job 串接 part_id
- [x] T4.1 `backend/src/ccas/ingestor/job.py` — `_process_attachment()`：
  - [x] 呼叫 `find_existing_staged(session, attachment.message_id, attachment.part_id, attachment.filename)`
  - [x] 命中 fallback（existing 存在但 `gmail_part_id is None`）時，在 skip 分支呼叫 `backfill_part_id(session, existing, attachment.part_id)`
  - [x] `create_staged_record()` 傳入 `part_id=attachment.part_id`
- [x] T4.2 `_process_web_fetch()`：將 synthetic part_id 設為 `f"web:{message_id}"`，其餘比照 T4.1
- [x] T4.3 Integration test `backend/tests/integration/test_ingestor_dedup.py`：
  - [x] Fake Gmail service 第一次回傳 attachment_id=`A1` / part_id=`1`，第二次回傳 attachment_id=`A2` / part_id=`1`（模擬 Gmail 行為）
  - [x] 第一次 ingest：`staged=1, skipped=0`
  - [x] 第二次 ingest（無 force）：`staged=0, skipped=1`
  - [x] 驗證 DB 只有 1 列

## T5: 資料清理腳本
- [x] T5.1 `backend/scripts/dedupe_staged_attachments.py` — 新增 CLI：
  - [x] `--dry-run`（預設 True 為安全考量；需顯式 `--apply` 才真的刪）
  - [x] 查詢 `(bank_code, gmail_message_id, original_filename)` group 中 count > 1 的所有列
  - [x] 每組保留 `MAX(id)`，其餘列為刪除候選
  - [x] 列印每個銀行的 before/after 計數與預計刪除總數
  - [x] `--apply` 時：刪 DB 列；若某列的 `staged_path` 在磁碟上且沒有其他 row 引用相同路徑 → 刪檔
- [x] T5.2 手動驗證：`cd backend && uv run python scripts/dedupe_staged_attachments.py --dry-run`；接著 `--apply`

## T6: End-to-end 驗證
- [x] T6.1 套用 migration：`cd backend && uv run alembic upgrade head`
- [x] T6.2 跑清理腳本（dry-run → apply）
- [x] T6.3 `uv run python -m ccas.pipeline --bank CTBC` — 預期 ingest `staged=0, skipped=129`（或清理後的實際數）
- [x] T6.4 `uv run python -m ccas.pipeline --bank CTBC --force` — 預期 ingest 重新處理所有 129（force 仍有效）
- [x] T6.5 `./scripts/dev-test.sh` 全綠
- [x] T6.6 `./scripts/dev-lint.sh` 無 error

## T7: 文件與清理
- [x] T7.1 更新 `backend/src/ccas/storage/models.py` 的 `StagedAttachment` docstring 反映新 dedupe 鍵
- [x] T7.2 若 `CLAUDE.md` 或 `docs/` 有提到 attachment_id dedupe，同步更新
