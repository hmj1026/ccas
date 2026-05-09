# ingestion-job-hook Specification

## Purpose
TBD - created by archiving change gmail-ingestor. Update Purpose after archive.
## Requirements
### Requirement: 提供單一 ingestion job 入口
系統 SHALL 提供一個 job-level 單一入口，用於對所有符合條件的銀行設定執行一次 Gmail ingestion batch。

#### Scenario: 批次工作處理所有符合條件的銀行
- **WHEN** ingestion job 被觸發
- **THEN** 它會巡覽所有啟用中且具有有效 Gmail filter 的銀行設定，並對每一筆執行 Gmail ingestion 流程

### Requirement: 單筆失敗後仍持續批次處理
系統 SHALL 在同一次 ingestion run 中，即使單一郵件或單一附件失敗，也持續處理其他銀行、郵件與附件。

#### Scenario: 某個附件失敗但批次繼續
- **WHEN** 某個候選 PDF 附件下載失敗
- **THEN** job 會為該附件記錄失敗結果，並繼續處理剩餘附件與其他銀行

#### Scenario: 某家銀行查詢失敗但其他銀行繼續
- **WHEN** 某筆銀行設定的 Gmail 查詢失敗
- **THEN** job 會記錄該銀行層級的失敗，並繼續處理其他啟用中的銀行設定

### Requirement: 回傳 ingestion batch 摘要
系統 SHALL 為每次 ingestion run 回傳結構化摘要，至少包含成功下載、略過重複與失敗的統計數量。

#### Scenario: 批次摘要回報處理結果
- **WHEN** 一次 ingestion batch 完成
- **THEN** job 會回傳包含已處理銀行數、候選郵件數、已 staged 附件數、略過重複數與失敗數的結構化摘要

