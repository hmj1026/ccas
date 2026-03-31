# gmail-ingestion Specification

## Purpose
TBD - created by archiving change gmail-ingestor. Update Purpose after archive.
## Requirements
### Requirement: 依啟用中的銀行設定搜尋 Gmail 郵件
系統 SHALL 使用設定中的憑證路徑完成 Gmail API 驗證，並對每一筆啟用中的銀行設定依 `bank_configs.gmail_filter` 搜尋候選郵件。

#### Scenario: 為啟用中的銀行搜尋候選郵件
- **WHEN** 某筆銀行設定為啟用狀態，且具有非空的 `gmail_filter`
- **THEN** ingestion service 會用該 filter 查詢 Gmail，並回傳屬於該銀行的候選郵件

#### Scenario: 略過未啟用的銀行設定
- **WHEN** 某筆銀行設定被標記為未啟用
- **THEN** ingestion service 不會為該銀行執行 Gmail 查詢

### Requirement: 只處理候選郵件中的 PDF 附件
系統 SHALL 檢查每一封候選 Gmail 郵件，並只處理其中的 PDF 附件。

#### Scenario: 選出可下載的 PDF 附件
- **WHEN** 某封候選郵件包含一個或多個 PDF 附件
- **THEN** 每個 PDF 附件都會被選入下載流程

#### Scenario: 忽略非 PDF 附件
- **WHEN** 某封候選郵件包含非 PDF 的附件
- **THEN** 這些附件會被忽略，不會作為帳單 staging 檔案下載

### Requirement: 將 PDF 附件下載到可預期的 staging 路徑
系統 SHALL 將每個被選中的 PDF 附件下載到可預期的本地 staging 路徑，且該路徑需包含足夠資訊以追溯來源銀行與 Gmail 來源。

#### Scenario: 已下載附件具有穩定路徑
- **WHEN** 某個 PDF 附件下載成功
- **THEN** 該檔案會被存放到後端管理的 staging 目錄，並以可預期的路徑與檔名記錄下來供後續處理

#### Scenario: 同一封郵件的多個 PDF 分開保存
- **WHEN** 某封候選郵件包含多個 PDF 附件
- **THEN** 每個 PDF 都會以獨立 staged file 保存，不會互相覆蓋

