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
系統 SHALL 在後續重跑時避免為同一個 Gmail message attachment 建立重複的 staging record 或重複 staged file。

#### Scenario: 重跑時略過已 staged 的附件
- **WHEN** ingestion job 再次遇到 Gmail message 與 attachment identity 已存在於 staging storage 的附件
- **THEN** 系統不會建立第二筆 staging record，並會在 job result 中將該附件標記為 skipped 或 already ingested

#### Scenario: 同一封郵件中的不同附件可分別存在
- **WHEN** 某封 Gmail 郵件包含多個不同的 PDF 附件
- **THEN** 雖然它們共用同一個 Gmail message identifier，但每個附件仍可各自擁有獨立的 staging record

### Requirement: 保留 staged 檔案供後續 parser 接手
系統 SHALL 保留已成功下載的 staged PDF 檔案，供後續 parser 使用，而不是在 ingestion run 結束時刪除。

#### Scenario: 後續解析流程透過 staged file reference 接手
- **WHEN** 後續處理步驟需要解析某個已匯入附件
- **THEN** 它可以直接從 staging storage 取得 staged file path 與 metadata，而不需重新向 Gmail 下載附件

