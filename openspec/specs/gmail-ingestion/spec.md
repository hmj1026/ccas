# gmail-ingestion Specification

## Purpose
TBD - created by archiving change gmail-ingestor. Update Purpose after archive.
## Requirements
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

### Requirement: 將 PDF 附件下載到可預期的 staging 路徑
系統 SHALL 將每個被選中的 PDF 附件下載到可預期的本地 staging 路徑，且該路徑需包含足夠資訊以追溯來源銀行與 Gmail 來源。

#### Scenario: 已下載附件具有穩定路徑
- **WHEN** 某個 PDF 附件下載成功
- **THEN** 該檔案會被存放到後端管理的 staging 目錄，並以可預期的路徑與檔名記錄下來供後續處理

#### Scenario: 同一封郵件的多個 PDF 分開保存
- **WHEN** 某封候選郵件包含多個 PDF 附件
- **THEN** 每個 PDF 都會以獨立 staged file 保存，不會互相覆蓋

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

### Requirement: GmailAttachmentMeta 攜帶 MIME part identifier
系統 SHALL 在 `GmailAttachmentMeta` 中保存 Gmail MIME payload 的 `partId`，以便下游 staging 流程使用其作為 stable dedupe key。`_collect_pdf_parts()` 遞迴抓取 PDF parts 時 MUST 讀取 `part["partId"]` 並寫入 `GmailAttachmentMeta.part_id`。

#### Scenario: 從 Gmail API payload 擷取 partId
- **WHEN** `_collect_pdf_parts()` 辨識出一個 PDF part
- **THEN** 回傳的 `GmailAttachmentMeta` 的 `part_id` 欄位 SHALL 等於該 part 的 `partId`（例如 `"1"`、`"0.1"`）

#### Scenario: partId 缺失時退回安全預設
- **WHEN** 某個 PDF part 的 Gmail payload 沒有 `partId` 欄位（不預期但防禦性處理）
- **THEN** `GmailAttachmentMeta.part_id` SHALL 設為空字串，下游 staging 邏輯 SHALL 視同 fallback 行為（以 filename 比對）

### Requirement: 每銀行附件檔名黑名單 SHALL 過濾非帳單附件

系統 SHALL 提供 `ccas.ingestor.filters.should_skip_attachment(bank_code, filename)`，由 `ATTACHMENT_FILENAME_BLOCKLIST` 定義各銀行的檔名子字串黑名單，於 ingest 階段早期略過非帳單的 PDF，避免污染 staging DB 與下游 parser 統計。黑名單至少包含：

- `SINOPAC`: `("繳款聯",)`
- `TAISHIN`: `("PaymentSlip",)`
- `CATHAY`: `("繳款聯",)`

#### Scenario: TAISHIN PaymentSlip 命中黑名單
- **GIVEN** `bank_code="TAISHIN"`、`filename="TSB_PaymentSlip_202411.pdf"`
- **WHEN** `should_skip_attachment` 被呼叫
- **THEN** 回傳 `True`

#### Scenario: TAISHIN Estatement 不命中
- **GIVEN** `bank_code="TAISHIN"`、`filename="TSB_Creditcard_Estatement_202411.pdf"`
- **WHEN** `should_skip_attachment` 被呼叫
- **THEN** 回傳 `False`

#### Scenario: SINOPAC 繳款聯 命中黑名單
- **GIVEN** `bank_code="SINOPAC"`、`filename="永豐銀行信用卡繳款聯.pdf"`
- **WHEN** `should_skip_attachment` 被呼叫
- **THEN** 回傳 `True`

#### Scenario: CATHAY 繳款聯 命中黑名單
- **GIVEN** `bank_code="CATHAY"`、`filename="國泰世華115年03月信用卡繳款聯.pdf"`
- **WHEN** `should_skip_attachment` 被呼叫
- **THEN** 回傳 `True`

#### Scenario: CATHAY 帳單附件不受影響
- **GIVEN** `bank_code="CATHAY"`、`filename="信用卡電子帳單消費明細_11503.pdf"`
- **WHEN** `should_skip_attachment` 被呼叫
- **THEN** 回傳 `False`

