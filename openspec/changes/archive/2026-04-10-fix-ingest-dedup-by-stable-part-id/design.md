## Context

### 問題根因
Gmail API 的 `messages.get(format="full")` 回傳每個 MIME part 時，都會在 `body.attachmentId` 欄位放一個 opaque token；但這個 token **每次呼叫都會重新產生**（Google 未文件化為穩定，實務觀察 token 前綴固定為 `ANGjdJ`，後接隨機字串）。CCAS 過去誤把它當作穩定鍵，導致 dedupe 失效、`staged_attachments` 表膨脹（CTBC 實測 129 unique messages 產生 903 列，約 7 倍膨脹）。

Gmail API 另有一個欄位 `partId`（例如 `"0"`、`"1"`、`"0.1.2"`），代表該 part 在 MIME tree 中的位置。這個欄位是純粹的結構性索引，對同一封郵件永遠相同，是自然的穩定鍵。

### 現況
- `GmailAttachmentMeta` 已擷取 `message_id`、`attachment_id`、`filename`、`size`，但未擷取 `partId`
- `StagedAttachment` model 有 `gmail_message_id`、`gmail_attachment_id` 欄位與 unique index
- `find_existing_staged()` 查詢 `(message_id, attachment_id)`
- 既有 DB 已有大量冗餘資料需清理

## Goals / Non-Goals

**Goals**
- 修復 ingest 冪等性：無 `--force` 重跑時，已處理附件必須 skip
- 保留 `gmail_attachment_id` 欄位作為稽核歷史（不 drop），但從 dedupe 邏輯中移除依賴
- 既有 DB 資料可漸進遷移，不需一次性重跑所有附件
- 清理既有冗餘列（目標：CTBC 903→129，SINOPAC 依實際 unique 數）

**Non-Goals**
- 不重構 `staged_attachments` 表結構（僅 ADD COLUMN）
- 不變更 decrypt/parse/classify/notify 階段的冪等邏輯
- 不處理 `staged_path` 在 Docker/本地之間不一致的問題（另一個議題）
- 不變更 `--force` 行為

## Decisions

### D1. 使用 Gmail MIME `partId` 作為 stable key
**選擇**：新增 `StagedAttachment.gmail_part_id: str | None` 欄位，dedupe 鍵改為 `(gmail_message_id, gmail_part_id)`。

**替代方案**：
- **(message_id, filename)**：如果同一信件有兩個同名 PDF（罕見但可能）會誤判；寄件方改檔名也會破壞
- **(message_id, filename, size)**：需要加 size 欄位，收益不比 partId 好
- **message-level hash**：overkill，計算成本高

`partId` 勝出原因：
1. Gmail API 原生欄位，不需自己算
2. 純結構性，不受檔名/大小變動影響
3. 語意清晰（「這封信的第幾個 part」）

### D2. 漸進遷移：fallback 到 filename
**選擇**：`find_existing_staged()` 先以 `(message_id, part_id)` 查詢；若 part_id 為空字串或 None，fallback 到 `(message_id, filename)` 比對。

**理由**：Migration 套用後，舊資料的 `gmail_part_id` 欄位為 NULL。若強制所有查詢都必須帶 part_id，首次 ingest 會把舊資料全部當成「不存在」而重新下載，等於一次性洗資料。fallback 策略讓舊資料能即刻被辨識、skip，同時 opportunistically 在命中時 backfill `gmail_part_id`（減少未來 fallback 開銷）。

**權衡**：fallback 路徑有理論上的 filename collision 風險，但只限於「舊資料 + 同信多同名 PDF」這個極窄的交集，實務可接受。

### D3. 資料清理用獨立腳本，不藏在 migration 內
**選擇**：新增 `scripts/dedupe_staged_attachments.py`，支援 `--dry-run`，預設保留每個 `(bank_code, gmail_message_id, original_filename)` 群組中 `id` 最大（最新）的一列。

**理由**：
- Alembic migration 應只處理 schema，不處理資料清理（pytest 與本地開發每次都會跑 migration，資料清理不該重複執行）
- `--dry-run` 讓使用者先確認影響範圍
- 用 `id` 最大（而非某個 status 優先級）保留最新狀態，避免把後來成功重試的紀錄誤刪

### D4. 保留 `gmail_attachment_id` 欄位
**選擇**：欄位保留、不改 nullable 設定、不 drop。

**理由**：仍用於除錯稽核、可能用於未來 re-download 的 Gmail API 呼叫（但不再參與 dedupe 決策）。

## Implementation Plan

### Phase 1: Schema & metadata（無行為改變）
1. `GmailAttachmentMeta` 加 `part_id: str = ""` 欄位
2. `_collect_pdf_parts()` 從 `part.get("partId", "")` 抓取
3. Alembic migration：`ALTER TABLE staged_attachments ADD COLUMN gmail_part_id TEXT NULL`；加上 index `idx_staged_attachments_message_part`

### Phase 2: Dedupe 邏輯切換
1. `find_existing_staged(session, message_id, part_id, filename)` 簽章擴充
2. 主查詢：`(gmail_message_id=?, gmail_part_id=?)` 且 `part_id != ""`
3. Fallback：若 part_id 為空、或主查詢無結果 → 查 `(gmail_message_id=?, original_filename=?, gmail_part_id IS NULL)`
4. 命中 fallback 時，在呼叫端 opportunistically `UPDATE` 該列的 `gmail_part_id`（backfill）
5. `create_staged_record()` 新增 `part_id` 參數

### Phase 3: Job 串接
1. `_process_attachment()` 傳 `attachment.part_id` 至 `find_existing_staged` 與 `create_staged_record`
2. `_process_web_fetch()` 維持 `synthetic_attachment_id` 邏輯，但 `part_id` 設為 `f"web:{message_id}"`（讓 web fetch 也走 part_id 路徑）

### Phase 4: 清理腳本
1. `scripts/dedupe_staged_attachments.py`：
   - 查詢所有 `(bank_code, gmail_message_id, original_filename)` 群組中 count > 1 的列
   - 保留每組 `id` 最大者
   - `--dry-run` 列印預計刪除數；無 flag 則實際刪除
   - 同時清理對應的磁碟檔案（若只有該筆紀錄引用）

### Phase 5: Tests
- Unit: `find_existing_staged` 主查詢 / fallback / 無命中三種路徑
- Unit: `_collect_pdf_parts` 回傳帶 `part_id` 的 meta
- Integration: mock Gmail API 回傳同 partId 不同 attachmentId，連跑兩次 ingest → 第二次 skip

## Risks / Trade-offs

| Risk | Likelihood | Mitigation |
|---|---|---|
| 既有 unique constraint 在 `(message_id, attachment_id)` 上導致 migration 衝突 | 中 | 檢查現有 model，若有則在 migration 中 drop 該 constraint，改加 `(message_id, part_id)` partial unique |
| Fallback 階段同信件同名 PDF collision | 極低 | 實測資料顯示無此情況；若發生會合併為一列但原始檔案保留 |
| Gmail API 部分 message payload 沒有 partId | 極低 | `part.get("partId", "")` 退回空字串，走 filename fallback |
| 清理腳本誤刪磁碟檔案 | 中 | 預設 `--dry-run`；磁碟刪除只在「沒有其他 staged row 引用該路徑」時執行 |

## Migration Plan

1. **Dev DB**：套用新 migration、跑清理腳本 `--dry-run` 確認、實際清理、跑一次無 `--force` pipeline 驗證 skip
2. **Production/Docker**：同上順序，清理腳本作為 release note 一部分

## Open Questions

無（已釐清 partId 行為與 fallback 策略）
