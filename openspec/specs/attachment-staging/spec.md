# attachment-staging Specification

## Purpose
TBD - created by archiving change gmail-ingestor. Update Purpose after archive.
## Requirements
### Requirement: 保存 staged attachment metadata
系統 SHALL 為每個已處理的 PDF 附件保存一筆 staging record，讓後續元件可以追溯該檔案的 Gmail 來源與處理結果。

#### Scenario: 成功建立 staging 紀錄
- **WHEN** 某個 PDF 附件下載成功
- **THEN** 系統會保存一筆 staging record，至少包含銀行代碼、Gmail message identifier、attachment identifier、message date、原始檔名、staged file path、status 與 created timestamp

#### Scenario: 失敗的 staging 紀錄保留錯誤脈絡
- **WHEN** 已辨識出候選 PDF 後，附件下載或檔案保存失敗
- **THEN** 系統會建立或更新 staging record，將 status 標記為失敗，並保存描述失敗原因的 error reason

### Requirement: 防止同一個 Gmail 附件重複 staging
系統 SHALL 在後續重跑時避免為同一個 Gmail message attachment 建立重複的 staging record 或重複 staged file。Dedupe 鍵 MUST 使用 stable 的 Gmail MIME part identifier（`gmail_message_id` + `gmail_part_id`），MUST NOT 使用 `gmail_attachment_id`（Gmail API 每次呼叫重新生成）。當既有記錄無 `gmail_part_id`（pre-migration 舊資料）時，系統 SHALL fallback 使用 `(gmail_message_id, original_filename)` 比對。當既有記錄的 status 為 `"failed"` 時，系統 SHALL 自動重試下載，而非跳過。

#### Scenario: 重跑時略過已成功 staged 的附件
- **WHEN** ingestion job 再次遇到相同 `gmail_message_id` 與 `gmail_part_id` 的 staging record，且 status 非 `"failed"`
- **THEN** 系統不會建立第二筆 staging record，並會在 job result 中將該附件標記為 skipped

#### Scenario: 重跑時自動重試 failed 附件
- **WHEN** ingestion job 再次遇到相同 `gmail_message_id` 與 `gmail_part_id` 的 staging record，且 status 為 `"failed"`
- **THEN** 系統 SHALL 自動重新下載該附件並更新 staging record，無需使用 `--force` 旗標

#### Scenario: 同一封郵件中的不同 MIME parts 可分別存在
- **WHEN** 某封 Gmail 郵件包含多個 PDF 附件（不同 `partId`）
- **THEN** 雖然它們共用同一個 `gmail_message_id`，但每個附件仍可各自擁有獨立的 staging record

#### Scenario: 既有資料無 part_id 時以檔名 fallback 略過
- **WHEN** ingestion job 再次遇到 `gmail_message_id` 已存在但 DB 中該列 `gmail_part_id` 為 NULL 的 staging record，且下載到的新附件 `original_filename` 與 DB 既有列相同
- **THEN** 系統 SHALL 視為已存在、標記為 skipped，且 MAY 於該次寫回 `gmail_part_id` 以完成漸進遷移

#### Scenario: Gmail API 變動 attachment_id 不影響 dedupe
- **WHEN** 同一封郵件的同一個附件在不同 Gmail API 呼叫中回傳不同的 `attachmentId`，但 `partId` 相同
- **THEN** 系統 SHALL 仍視為同一筆、skip 該附件，不會建立新的 staging record

### Requirement: 保留 staged 檔案供後續 parser 接手
系統 SHALL 保留已成功下載的 staged PDF 檔案，供後續 parser 使用，而不是在 ingestion run 結束時刪除。

#### Scenario: 後續解析流程透過 staged file reference 接手
- **WHEN** 後續處理步驟需要解析某個已匯入附件
- **THEN** 它可以直接從 staging storage 取得 staged file path 與 metadata，而不需重新向 Gmail 下載附件

### Requirement: Staging 附件資料表模型
系統 SHALL 維持 `StagedAttachment` 資料模型的既有欄位與唯一約束，新增 `gmail_part_id: str | None` 欄位以記錄 Gmail MIME part 的穩定識別碼，且 `created_at` 的 Python 端預設值 SHALL 為 timezone-aware 的 `datetime.now(UTC)`。新欄位 MUST 為 nullable 以支援 pre-migration 舊資料。

#### Scenario: 建立 staging 紀錄
- **WHEN** 建立一筆 `StagedAttachment`
- **THEN** `created_at` 會自動設定為 timezone-aware UTC datetime

#### Scenario: 新紀錄攜帶 part_id
- **WHEN** ingestion job 建立一筆由 Gmail attachment 來源的 `StagedAttachment`
- **THEN** `gmail_part_id` 欄位 SHALL 設定為對應 MIME part 的 `partId`（例如 `"1"`、`"0.1"`）

#### Scenario: 舊紀錄 part_id 可為空
- **WHEN** migration 套用到含有既有資料的 DB
- **THEN** 既有列的 `gmail_part_id` 欄位 SHALL 為 NULL，且系統不因此拒絕查詢或寫入

