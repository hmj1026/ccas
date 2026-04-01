## MODIFIED Requirements

### Requirement: 依啟用中的銀行設定搜尋 Gmail 郵件
系統 SHALL 使用設定中的憑證路徑完成 Gmail API 驗證，並對每一筆啟用中的銀行設定依 `bank_configs.gmail_filter` 搜尋候選郵件。當 `PipelineOptions.bank_code` 有值時，SHALL 只處理該指定銀行。當 `PipelineOptions.year` 或 `PipelineOptions.month` 有值時，SHALL 將 `gmail_date_filter()` 產生的日期子句附加到 Gmail 查詢條件。

#### Scenario: 為啟用中的銀行搜尋候選郵件
- **WHEN** 某筆銀行設定為啟用狀態，且具有非空的 `gmail_filter`
- **THEN** ingestion service 會用該 filter 查詢 Gmail，並回傳屬於該銀行的候選郵件

#### Scenario: 略過未啟用的銀行設定
- **WHEN** 某筆銀行設定被標記為未啟用
- **THEN** ingestion service 不會為該銀行執行 Gmail 查詢

#### Scenario: 依 bank_code 篩選
- **WHEN** `PipelineOptions.bank_code = "CTBC"` 且有多筆啟用中的銀行設定
- **THEN** ingestion service 只處理 `bank_code = "CTBC"` 的銀行設定，略過其他銀行

#### Scenario: 依日期篩選 Gmail 查詢
- **WHEN** `PipelineOptions.year = 2026` 且 `PipelineOptions.month = 3`
- **THEN** Gmail 查詢條件附加 `after:2026/02/28 before:2026/04/01`，只搜尋該月份的郵件

## ADDED Requirements

### Requirement: Force 模式繞過 ingestion 去重
當 `PipelineOptions.force = True` 時，系統 SHALL 在發現已存在的 `StagedAttachment` 記錄後，刪除該舊記錄（含磁碟檔案），重新下載附件並建立新的 staging 記錄。

#### Scenario: Force 模式重新下載已存在的附件
- **WHEN** `force = True` 且某附件的 `(gmail_message_id, gmail_attachment_id)` 已存在於 `StagedAttachment`
- **THEN** 系統刪除舊的 `StagedAttachment` 記錄，重新從 Gmail 下載該附件，並建立新的 staging 記錄（status = "staged"）

#### Scenario: 非 Force 模式維持去重行為
- **WHEN** `force = False`（預設）且某附件已存在於 `StagedAttachment`
- **THEN** 系統跳過該附件，行為與變更前完全一致

#### Scenario: Force 模式清理舊檔案
- **WHEN** `force = True` 且舊 `StagedAttachment` 記錄有對應的磁碟檔案
- **THEN** 系統在刪除 DB 記錄前先刪除磁碟上的舊 PDF 檔案
