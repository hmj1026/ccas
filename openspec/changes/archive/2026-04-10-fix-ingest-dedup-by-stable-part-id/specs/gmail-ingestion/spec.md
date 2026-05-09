## MODIFIED Requirements

### Requirement: Force 模式繞過 ingestion 去重
當 `PipelineOptions.force = True` 時，系統 SHALL 在發現已存在的 `StagedAttachment` 記錄後，刪除該舊記錄（含磁碟檔案），重新下載附件並建立新的 staging 記錄。既有記錄的比對 MUST 使用 `(gmail_message_id, gmail_part_id)` 作為穩定鍵。

#### Scenario: Force 模式重新下載已存在的附件
- **WHEN** `force = True` 且某附件的 `(gmail_message_id, gmail_part_id)` 已存在於 `StagedAttachment`
- **THEN** 系統刪除舊的 `StagedAttachment` 記錄，重新從 Gmail 下載該附件，並建立新的 staging 記錄（status = "staged"）

#### Scenario: 非 Force 模式維持去重行為
- **WHEN** `force = False`（預設）且某附件已存在於 `StagedAttachment`
- **THEN** 系統跳過該附件，並將該附件計入 job result 的 skipped 計數

#### Scenario: Force 模式清理舊檔案
- **WHEN** `force = True` 且舊 `StagedAttachment` 記錄有對應的磁碟檔案
- **THEN** 系統在刪除 DB 記錄前先刪除磁碟上的舊 PDF 檔案

## ADDED Requirements

### Requirement: GmailAttachmentMeta 攜帶 MIME part identifier
系統 SHALL 在 `GmailAttachmentMeta` 中保存 Gmail MIME payload 的 `partId`，以便下游 staging 流程使用其作為 stable dedupe key。`_collect_pdf_parts()` 遞迴抓取 PDF parts 時 MUST 讀取 `part["partId"]` 並寫入 `GmailAttachmentMeta.part_id`。

#### Scenario: 從 Gmail API payload 擷取 partId
- **WHEN** `_collect_pdf_parts()` 辨識出一個 PDF part
- **THEN** 回傳的 `GmailAttachmentMeta` 的 `part_id` 欄位 SHALL 等於該 part 的 `partId`（例如 `"1"`、`"0.1"`）

#### Scenario: partId 缺失時退回安全預設
- **WHEN** 某個 PDF part 的 Gmail payload 沒有 `partId` 欄位（不預期但防禦性處理）
- **THEN** `GmailAttachmentMeta.part_id` SHALL 設為空字串，下游 staging 邏輯 SHALL 視同 fallback 行為（以 filename 比對）
