## MODIFIED Requirements

### Requirement: 防止同一個 Gmail 附件重複 staging
系統 SHALL 在後續重跑時避免為同一個 Gmail message attachment 建立重複的 staging record 或重複 staged file。當既有記錄的 status 為 `"failed"` 時，系統 SHALL 自動重試下載，而非跳過。

#### Scenario: 重跑時略過已成功 staged 的附件
- **WHEN** ingestion job 再次遇到 Gmail message 與 attachment identity 已存在於 staging storage 的附件，且該記錄 status 非 `"failed"`
- **THEN** 系統不會建立第二筆 staging record，並會在 job result 中將該附件標記為 skipped

#### Scenario: 重跑時自動重試 failed 附件
- **WHEN** ingestion job 再次遇到 Gmail message 與 attachment identity 已存在於 staging storage 的附件，且該記錄 status 為 `"failed"`
- **THEN** 系統 SHALL 自動重新下載該附件並更新 staging record，無需使用 `--force` 旗標

#### Scenario: 同一封郵件中的不同附件可分別存在
- **WHEN** 某封 Gmail 郵件包含多個不同的 PDF 附件
- **THEN** 雖然它們共用同一個 Gmail message identifier，但每個附件仍可各自擁有獨立的 staging record
