## MODIFIED Requirements

### Requirement: 依啟用中的銀行設定搜尋 Gmail 郵件
系統 SHALL 使用設定中的憑證路徑完成 Gmail API 驗證，並對每一筆啟用中的銀行設定依 `bank_configs.gmail_filter` 搜尋候選郵件。當 `PipelineOptions.bank_code` 有值時，SHALL 只處理該指定銀行。當 `PipelineOptions.year` 或 `PipelineOptions.month` 有值時，SHALL 將 `gmail_date_filter()` 產生的日期子句附加到 Gmail 查詢條件。

當 Gmail API 回傳 `nextPageToken` 時，系統 SHALL 持續請求後續分頁，直到所有符合條件的郵件都被取回，或達到安全分頁上限（預設 10 頁）。達到上限時 SHALL 記錄 WARNING 級別日誌。

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

#### Scenario: 搜尋結果跨多頁時取回所有郵件
- **WHEN** Gmail API 回傳第一頁結果且包含 `nextPageToken`
- **THEN** 系統 SHALL 繼續請求後續分頁，直到 `nextPageToken` 不再出現，將所有頁面的郵件合併後處理

#### Scenario: 分頁數達到安全上限時停止
- **WHEN** 分頁請求達到安全上限（預設 10 頁）
- **THEN** 系統 SHALL 停止分頁、記錄 WARNING 日誌，並以已取回的郵件繼續處理

### Requirement: 只處理候選郵件中的 PDF 附件
系統 SHALL 檢查每一封候選 Gmail 郵件，並只處理其中的 PDF 附件。系統 SHALL 遞迴搜尋所有 MIME 層級的 parts，以支援巢狀 multipart 結構中的 PDF 附件。遞迴深度 SHALL 限制為 10 層。

#### Scenario: 選出可下載的 PDF 附件
- **WHEN** 某封候選郵件包含一個或多個 PDF 附件
- **THEN** 每個 PDF 附件都會被選入下載流程

#### Scenario: 忽略非 PDF 附件
- **WHEN** 某封候選郵件包含非 PDF 的附件
- **THEN** 這些附件會被忽略，不會作為帳單 staging 檔案下載

#### Scenario: 巢狀 MIME 結構中的 PDF 附件被正確擷取
- **WHEN** 某封候選郵件的 PDF 附件位於巢狀 multipart 結構內（例如 multipart/mixed > multipart/related > application/pdf）
- **THEN** 系統 SHALL 遞迴搜尋所有 MIME parts 並擷取該 PDF 附件

#### Scenario: 超過遞迴深度限制時停止搜尋
- **WHEN** MIME 結構巢狀深度超過 10 層
- **THEN** 系統 SHALL 停止搜尋更深層的 parts，不會造成無限遞迴
